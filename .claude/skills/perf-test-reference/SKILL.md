---
name: perf-test-reference
description: 성능 테스트 가이드. 목표 설정, 변수 분리 원칙, k6 ramping-arrival-rate 템플릿, 실행 프로토콜, 결과 분석 프레임워크, 보고서 템플릿 포함. /perf-test, /perf-cycle, /perf-action 실행 시 참조.
---

# 성능 테스트 가이드

> 이전 테스트에서 발견된 문제점(변수 미분리, 수치 불일치, 목표 근거 부재)을 반면교사로 삼아,
> **재현 가능하고 신뢰할 수 있는** 성능 테스트를 수행하기 위한 가이드.

## 핵심 원칙

### 1. 목표 먼저 (No Goal = No PASS/FAIL)
- MUST: 테스트 전에 TPS 목표, SLO(p95/p99/에러율/consumer lag) 정의
- MUST: 트래픽 근거 명시 (실 데이터 or DAU 기반 산출 공식 기록)
- MUST: read/write 비율 근거 명시

### 2. 변수 분리 (Single Variable Principle)
- MUST: **한 라운드에 1개 변수만 변경**. 기여도 분리 불가능한 동시 변경 금지
- 예외: 논리적으로 분리 불가능한 경우(파티션 6 + concurrency 6) 묶되 이유 기록
- NEVER: 이전 라운드와 k6 스크립트가 다르면 직접 비교 금지

### 3. 동일 조건 보장 (Fair Comparison)
- MUST: 매 라운드 시작 전 — setup-reset-data.sh (TRUNCATE + FLUSH) + JVM warm-up
- MUST: k6 스크립트 동일, 인프라 상태 동일 (컨테이너 재시작)
- MUST: 외부 의존성 동일 (mock 서버 설정값)

### 4. ramping-arrival-rate executor
- MUST: `ramping-arrival-rate` 사용 — "초당 N 요청" 정밀 제어
- NEVER: `ramping-vus` + `sleep()`으로 TPS 측정 (VU 처리시간에 따라 실제 TPS 변동)
- MUST: `dropped_iterations` threshold 설정 — VU 부족 감지
- 공식 문서: https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ramping-arrival-rate/

### 4-1. k6 발급 정확성 집계 — body.status 체크 필수

SoldOut / AlreadyApplied 도 HTTP 200을 반환하는 API에서 `res.status === 200`으로 발급을 세면 모두 "성공"으로 잘못 집계된다.

```javascript
// ✅ 올바른 패턴 — response body의 status 필드로 구분
const issued  = new Counter("coupon_issued");
const soldOut = new Counter("coupon_sold_out");

export default function () {
  const res = http.post(URL, null, { headers });
  let s = "";
  try { s = JSON.parse(res.body).status; } catch(e) {}
  if      (s === "ISSUED")    issued.add(1);
  else if (s === "SOLD_OUT")  soldOut.add(1);
}
```

k6 결과에서 `coupon_issued` 카운터로 발급 정확성(= 1000건) 검증.

### 4-2. summaryTrendStats — p99 포함 명시

기본값에 p99가 없어 Parse 시 None 오류 발생. 항상 명시한다.

```javascript
export const options = {
  summaryTrendStats: ["avg","min","med","max","p(90)","p(95)","p(99)"],
  ...
};
```

### 5. write/read 시나리오 분리
- MUST: 시나리오별 독립 latency 메트릭 (`write_latency`, `read_latency`)
- MUST: `Math.random()` 분기 대신 `scenarios` 블록으로 분리

### 6. 절대값 vs 상대값
- MUST: Docker Compose 환경 절대값에 반드시 **"로컬 Docker Compose 환경 기준"** 단서
- MUST: 상대적 개선 비율을 주 지표로 사용

### 7. 에러 분석
- MUST: 에러율 0.01%라도 HTTP status별 분류 + 원인 기록

## Step 0: 프로젝트 컨텍스트 확인

`.claude/project-context.md`의 `## [perf-test-reference]` 섹션이 있으면 읽는다.
- 추가 SLO (Consumer lag 등 프로젝트 특화 지표)
- 목표 TPS 산출 공식
- 프로젝트 특화 체크리스트 항목 (OSIV 실험, CDC 여부 등)

## SLO 기본값

| 지표 | 임계치 | 근거 |
|------|--------|------|
| p95 응답시간 | ≤ 200ms | 사용자 체감 한계 |
| p99 응답시간 | ≤ 500ms | 이상치 허용 범위 |
| 에러율 | ≤ 0.1% | 서비스 품질 기준 |

> 프로젝트 추가 SLO (Consumer lag 등): `.claude/project-context.md → [perf-test-reference]` 섹션

## 실행 프로토콜

```
1. 환경 준비: docker-compose up → 헬스체크 → setup-reset-data.sh → JVM warm-up
2. 테스트: Grafana 오픈 + 시작 시각 기록 → k6 run → 종료 시각 기록
3. 수집: k6 summary JSON + Grafana 캡처 + ss -s + docker stats + consumer lag
4. 분석: 결과 보고서 템플릿 작성 (references/report-template.md)
```

### 라운드 간 규칙
```
Round N 완료 → 결과 분석 → 변경 1개 결정 + 기록 →
docker-compose down → 변경 적용 → up → reset → warm-up → Round N+1
```

## 병목 분석 순서

```
k6 p95 높음 → 어떤 엔드포인트? →
  HikariCP Pending > 0? → Tomcat:HikariCP 비율 →
  Tomcat busy = max? → TPS 한계/scale-out →
  Consumer lag 증가? → concurrency/파티션/외부 API →
  CPU > 80%? Memory > 90%? → scale-up →
  Slow query? → EXPLAIN/인덱스 →
  Redis latency spike? → 커넥션 풀 →
  → async-profiler/JFR
```

## 체크리스트 (빠른 참조)

### 테스트 전
- [ ] 목표 TPS 산출 근거, read/write 비율 근거
- [ ] SLO 정의 (p95, p99, 에러율, consumer lag)
- [ ] k6 스크립트 + Docker Compose git 커밋
- [ ] 호스트 머신 스펙 기록

### 라운드 시작 전
- [ ] 이전 대비 **1개 변수만** 변경 + 변경 이유 기록
- [ ] setup-reset-data.sh + JVM warm-up
- [ ] k6 스크립트 이전 라운드와 동일 확인

### 라운드 종료 후
- [ ] k6 summary JSON 저장 + Grafana 캡처(테스트 시간 범위)
- [ ] 에러 HTTP status별 분류
- [ ] 결과 보고서 작성 + 다음 변경 계획

### 최종 보고 전
- [ ] 변수 분리 확인 + "로컬 Docker Compose" 단서
- [ ] Consumer lag 변화 기록

## InnoDB 락 경합 델타 측정

어댑터 비교 시 `Innodb_row_lock_waits` 증가량으로 실제 락 경합을 정량화한다.

```bash
# 1. 테스트 전 스냅샷 (임시파일 방식 — pipe+heredoc 충돌 버그 회피)
TMP=$(mktemp)
mysql -h 127.0.0.1 -P 3306 -ucoupon -pcoupon coupon_db \
  -e "SHOW GLOBAL STATUS;" 2>/dev/null > "$TMP"
python3 - <<PYEOF
import json
rows = {}
with open("$TMP") as f:
    for line in f:
        parts = line.strip().split('\t')
        if len(parts) == 2: rows[parts[0]] = parts[1]
keys = ["Innodb_row_lock_waits","Innodb_row_lock_time","Innodb_row_lock_time_avg",
        "Innodb_rows_inserted","Queries"]
json.dump({k: int(rows.get(k,0) or 0) for k in keys},
          open("/tmp/mysql-before.json","w"), indent=2)
PYEOF
rm -f "$TMP"

# 2. k6 실행

# 3. 테스트 후 스냅샷 (동일 방식)
# ... (before → after delta 계산)

# 4. delta 해석
# lock_waits 0 = MySQL 경합 없음 (Redis/MongoDB 어댑터)
# lock_waits 급증 = events row hotspot (FOR UPDATE, Atomic UPDATE)
# 이론 TPS 천장: pool_size / lock_hold_time_sec
```

**주의**: pipe + heredoc 충돌로 모든 값이 0으로 찍히면 임시파일 방식으로 전환 (perf-bench 스킬 BUG-2 참조).

## 어댑터 공정 비교 원칙

MongoDB 벤치는 반드시 **MongoDB Full-Stack 프로파일** (`bench-mongo-full`) 사용:

| 프로파일 | coupon_issues 저장소 | 공정 여부 |
|---|---|---|
| `bench-mongo` | MySQL | ❌ HikariCP 병목 동일 |
| `bench-mongo-full` | MongoDB | ✅ MySQL writes = 0 |

## 상세 가이드

| 문서 | 내용 |
|------|------|
| `references/k6-templates.md` | k6 스크립트 템플릿 (load/stress), 디렉토리 구조 |
| `references/monitoring.md` | 필수 수집 지표, Grafana 대시보드 구성 |
| `references/report-template.md` | 라운드별 결과 보고서 템플릿 |
| `.claude/project-context.md` | **프로젝트 특화**: TPS 목표/SLO/체크리스트 (OSIV, CDC, poll 공식 등) |
