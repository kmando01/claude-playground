---
name: hikaricp-pool-sizing
description: HikariCP pool size 및 관련 설정 변경 시 4 Layer 근거(이론·인프라·메트릭·검증)를 체계적으로 산정하고 변경 보고서를 작성한다. "장애가 나서 늘렸다" 수준의 변경을 방지. Use when: "pool 늘려야 하나?", "hikaricp 설정 변경", "connection pool 튜닝", "DB connection 부족", "pool size 근거", "HikariCP". Triggers on hikaricp, pool, connection, maximumPoolSize, minimumIdle.
---

# HikariCP Pool Size 변경 스킬

## 핵심 원칙

> **수치 변경 = 4 Layer 근거 필수.** 하나만으로는 변경 보고서 작성 불가.

**판단 순서 (가이드 §Layer3 준수):**
1. `pending > 0` 확인 → pool 문제 의심
2. **`usage_seconds`(점유 시간) 먼저 확인** → 길면 쿼리/외부호출 코드 수정 먼저
3. usage 정상인데 pending 있음 → 그제서야 pool size 증설

## 4 Layer 계산 프로세스

### Layer 1: 이론적 산정

```
# HikariCP 공식 (DB 서버 기준)
connections = (core_count × 2) + effective_spindle_count

# Little's Law (실측 기반)
connections = peak_TPS × avg_usage_seconds × safety_factor(1.5~2.0)

→ 최종: max(HikariCP공식, Little's Law) 선택
```

**실행 명령:**
```bash
# DB 코어 수
docker exec {db-container} nproc

# Usage time (Grafana 패널 또는 Prometheus)
curl "http://localhost:9090/api/v1/query?query=avg_over_time(rate(hikaricp_connections_usage_seconds_sum[10s])[Xh:10s])*1000"
```

### Layer 2: 인프라 제약 검증

```
(instances_max × pool_size) + (관리/모니터링 커넥션)
  + 안전여유(20%) ≤ DB max_connections

→ 여유 20% 미만이면 pool 못 늘림 → DB max_connections 먼저 상향
```

**실행 명령:**
```bash
# MySQL max_connections
mysql -e "SHOW VARIABLES LIKE 'max_connections';"

# PostgreSQL
psql -c "SHOW max_connections;"
```

### Layer 3: 메트릭 증거 (Grafana 캡처 필수)

```bash
# Prometheus 수치 수집
BASE="http://localhost:9090/api/v1/query?query="

# 핵심 5개 메트릭
pending_max   = max_over_time(hikaricp_connections_pending[Xh])
acquire_p99   = histogram_quantile(0.99, hikaricp_connections_acquire_seconds_bucket)
usage_p99     = histogram_quantile(0.99, hikaricp_connections_usage_seconds_bucket)
active_ratio  = hikaricp_connections_active / hikaricp_connections_max
timeout_total = hikaricp_connections_timeout_total

# Grafana 패널 캡처 (renderer 설치 후)
curl "http://localhost:3000/render/d-solo/{uid}?panelId={id}&from=now-Xm&to=now&width=1200&height=400" -o panel.png
```

**변경 트리거:**
| 메트릭 | 트리거 |
|---|---|
| pending > 0 지속 | pool 부족 또는 쿼리 지연 |
| acquire p99 > 100ms | pool 경합 심각 |
| active/max > 90% | pool 포화 |
| timeout_total > 0 | 즉시 분석 필요 |

### Layer 4: 검증 계획 (변경 전 선언)

```
성공 기준: pending = 0, acquire p99 < 50ms
롤백 트리거: timeout_total > 0 OR DB CPU > 85%
관찰 기간: 최소 1 비즈니스 사이클
검증 방법: 변경 전후 동일 부하 테스트 + Grafana 캡처 비교
```

## 변경 보고서 작성

스킬 실행 시 아래 순서로 보고서를 작성한다:

1. **메트릭 수집** → Prometheus 쿼리 + Grafana 패널 캡처
2. **4 Layer 계산** → 위 공식 적용
3. **application.yml 수정** → 주석에 4 Layer 근거 인라인으로
4. **보고서 작성** → `docs/perf-reports/{date}-pool-change/REPORT.md`
5. **부하 테스트 재실행** → 변경 전후 Grafana 비교 캡처

## 설정 변경 인라인 주석 템플릿

```yaml
hikari:
  maximum-pool-size: 50   # 변경: 10 → 50
  minimum-idle: 50        # HikariCP 권장: 고정 풀(스파이크 대응)
  # 변경 근거 (4 Layer):
  # L1: Little's Law=90 / HikariCP공식=25 → max=90, 단계적으로 50 적용
  # L2: MySQL max_connections=300, 1×50+관리15=65 → 여유 57% ✅
  # L3: Grafana pending_max=189, acquire_max=440ms, usage=5~20ms(정상)
  # L4: 성공기준 pending=0, Phase1 P95<200ms. 미달 시 75→100 단계 상향
```

## 가상 스레드 환경 특수 고려사항 ★ (신규)

> 가상 스레드는 메모리 병목을 없애지만 **커넥션 풀이 새로운 천장**이 된다.

### 핵심 위험

플랫폼 스레드: OS 스레드 수 제한(~수백)이 자연스러운 동시성 상한선 역할.
가상 스레드: 스레드 수 제한 없음 → 수만 개가 동시에 커넥션을 요구 → pool 포화가 훨씬 빠르게 옴.

**실측 증거 (pool=5, vthreads=400, query 10ms)**:
```
vthreads=10  → p99 344ms   (허용 범위)
vthreads=50  → p99 2,106ms (p50은 12ms로 "정상처럼 보임")
vthreads=400 → p99 4,704ms (HikariCP connectionTimeout에 수렴)
```

### 가상 스레드용 pool_size 산정

```
기존 공식 (플랫폼 스레드):
  pool_size = peak_TPS × avg_query_seconds

가상 스레드 환경 추가 고려:
  concurrent_vthreads = 예상 최대 동시 요청 수 (플랫폼보다 훨씬 클 수 있음)
  pool_size ≥ concurrent_vthreads × avg_query_seconds / target_p99_seconds
```

### 모니터링 포인트

```bash
# HikariCP pending이 0인데 p99가 이상하면 vthread 경합 의심
hikaricp_connections_pending  → > 0 지속이면 pool 부족
hikaricp_connections_acquire_seconds (p99) → 100ms 초과 시 즉시 조사
```

### connectionTimeout 설정 (가상 스레드 환경)

```yaml
hikari:
  # 가상 스레드: 동시 요청이 많아 대기가 길어질 수 있음
  # 너무 짧으면 pool 경합 시 ConnectionTimeoutException 폭발
  connection-timeout: 30000  # 30s (기본값 유지 권장)
  # pool_size를 적절히 키우는 것이 우선 — timeout 늘리기는 임시방편
```

## 안티패턴 (변경 금지 패턴)

```
❌ "장애 났으니까 늘렸다" — usage_seconds 분석 없이 size만 키움
❌ "넉넉히 100으로" — DB 부담, 다른 서비스 압박
❌ minimumIdle = 0 + 스파이크 환경 — 커넥션 생성 지연으로 SLA 위반
❌ 트랜잭션 안에서 외부 API 호출 + pool 증설 — 점유 시간이 문제
❌ 캡처 없이 수치만 보고서에 기재
```

## 참고

- HikariCP wiki: About Pool Sizing
- HikariCP wiki: MySQL/PostgreSQL Configuration
- 관련 스킬: `perf-tuning-cycle` (부하 테스트), `static-perf-analysis` (코드 분석)
