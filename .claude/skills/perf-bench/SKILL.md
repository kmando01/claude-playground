---
name: perf-bench
description: "kakaopay-coupon 전용 성능 벤치마크 AI 오케스트레이터. 어댑터 프로파일 + 목표 RPS를 받아 빌드→웜업→k6→병렬 메트릭 캡처(subagent)→REPORT.md까지 한 사이클을 자동 실행. Use when: '어댑터 테스트 돌려줘', 'redis 100K 테스트', '/perf-bench', 'A/B 비교 테스트', '성능 라운드 실행'. 반드시 kakaopay-coupon 프로젝트 루트(/Users/mando/kakaopay-coupon)에서 실행."
---

# perf-bench — kakaopay-coupon 자동 벤치마크

> kakaopay-coupon 전용. 스트레스 테스트 방법론(`stress-test-methodology` 스킬)의 Section 5 AI 자동화 패턴을 구현한다.

---

## ⚠️ 알려진 버그 & 필수 패치

이 섹션은 과거 세션에서 발견된 버그다. 아래 패턴을 그대로 복사하지 말고 수정본을 사용한다.

### [BUG-1] k6 발급 정확성 집계 오류 — HTTP 200으로 판단 금지

`SoldOut`/`AlreadyApplied`도 HTTP 200을 반환한다. `res.status === 200` 집계는 전부 "발급 성공"으로 카운팅된다.

```javascript
// ❌ 잘못된 패턴
if (res.status === 200) issued.add(1);

// ✅ 올바른 패턴
let s = ""; try { s = JSON.parse(res.body).status; } catch(e) {}
if (s === "ISSUED") issued.add(1);
else if (s === "SOLD_OUT") soldOut.add(1);
```

### [BUG-2] mysql_snapshot — pipe + heredoc stdin 충돌

`mysql ... | python3 - <<'PYEOF'` 에서 heredoc이 stdin을 선점해 mysql 데이터가 python3에 도달하지 않는다. 결과: 모든 InnoDB 지표가 0으로 기록됨.

```bash
# ❌ 잘못된 패턴
mysql -e "SHOW GLOBAL STATUS;" 2>/dev/null | python3 - "$OUT" <<'PYEOF'
import sys, json
for line in sys.stdin: ...  # stdin이 비어 있어 아무 것도 읽지 못함
PYEOF

# ✅ 올바른 패턴 (임시파일 경유)
TMP=$(mktemp); mysql -e "SHOW GLOBAL STATUS;" 2>/dev/null > "$TMP" || true
python3 - <<PYEOF
import json
rows = {}
with open("$TMP") as f:
    for line in f:
        parts = line.strip().split('\t')
        if len(parts) == 2: rows[parts[0]] = parts[1]
json.dump({k: int(rows.get(k,0) or 0) for k in keys}, open("$OUT","w"), indent=2)
PYEOF
rm -f "$TMP"
```

### [BUG-3] MongoDB 어댑터 — 공정 비교 시 bench-mongo-full 사용

`bench-mongo`는 **카운터만** MongoDB, `coupon_issues`는 여전히 MySQL → HikariCP 동일 병목 → 불공정 비교.
공정한 비교를 위해선 `bench-mongo-full` 사용 (coupon_issues도 MongoDB, MySQL rows_inserted=0 확인됨).

| 프로파일 | 설명 | 비고 |
|---|---|---|
| `bench-mongo` | 카운터(coupon_counters)만 MongoDB | **불공정** — coupon_issues는 MySQL |
| `bench-mongo-full` | 카운터 + coupon_issues 모두 MongoDB | **공정 비교** |

### [BUG-4] 멀티모듈 전환 후 JAR 경로 변경

```bash
# ❌ 구 경로 (단일모듈)
JAR="build/libs/kakaopay-coupon-0.0.1-SNAPSHOT.jar"

# ✅ 현재 경로 (멀티모듈)
JAR="coupon-api/build/libs/coupon-api.jar"
```

---

## Step 0: 입력 파싱

사용자 메시지에서 다음을 추출한다:

| 파라미터 | 기본값 | 예시 |
|---|---|---|
| `ADAPTER` | redis | `redis`, `mysql-atomic`, `skip-locked`, `mongo-full`, `mysql` |
| `TARGET_RPS` | 3000 | `3000`, `10000`, `50000`, `100000` |
| `LABEL` | `{ADAPTER}-{TARGET_RPS}rps` | 자동 생성 |
| `A/B 비교` | 없음 | "redis vs mongo-full 비교" |

**어댑터 → Spring Profile 매핑:**

| ADAPTER 입력 | Spring Profile | 설명 |
|---|---|---|
| `redis` | `bench-redis` | Redis INCR + MySQL coupon_issues |
| `mysql-atomic` | `bench-mysql-atomic` | MySQL UPDATE atomic |
| `mysql` / `for-update` | `bench-mysql-for-update` | MySQL SELECT FOR UPDATE |
| `skip-locked` | `bench-skip-locked` | MySQL SKIP LOCKED |
| `mongo` | `bench-mongo` | MongoDB 카운터만 (불공정, 비교 목적 외 비권장) |
| `mongo-full` | `bench-mongo-full` | MongoDB 풀스택 (공정 비교) |

**빠른 추출 규칙:**
- "redis 100K" → ADAPTER=redis, TARGET_RPS=100000
- "skip-locked 30K" → ADAPTER=skip-locked, TARGET_RPS=30000
- "기본값" / 미입력 → ADAPTER=redis, TARGET_RPS=3000

---

## Step 1: 사전 검증 (GATE)

```bash
# 인프라 기동 확인
docker compose -f /Users/mando/kakaopay-coupon/docker-compose.yml ps | grep -E "Up|running"

# Prometheus 메트릭 수집 확인 (앱이 실행 중인 경우)
curl -sf http://localhost:8080/actuator/prometheus | grep -c "hikaricp_connections" 2>/dev/null || echo "앱 미기동 — Step 2에서 기동"

# Redis 연결 확인 (redis 어댑터)
docker exec coupon-redis redis-cli ping 2>/dev/null || echo "Redis 확인 필요"
```

사전 검증 실패 시: `docker compose up -d` 후 재확인.

---

## Step 2: 앱 빌드 & 기동 (/deploy-target)

```bash
cd /Users/mando/kakaopay-coupon

# 기존 앱 종료
kill -9 $(lsof -ti:8080) 2>/dev/null || true
sleep 8

# Gradle 빌드 (멀티모듈: coupon-api 모듈 빌드)
JAVA25="/Users/mando/.gradle/jdks/eclipse_adoptium-25-aarch64-os_x.2/jdk-25+36/Contents/Home/bin/java"
./gradlew :coupon-api:bootJar -x test -q

# 배포 이미지(JAR) 다이제스트 기록 — 캐시 여부 확인
JAR="coupon-api/build/libs/coupon-api.jar"   # [BUG-4] 멀티모듈 경로
JAR_MD5=$(md5 -q $JAR)
echo "JAR: $JAR  digest: $JAR_MD5"

# 기동 (Spring Profile: 어댑터 매핑표 참조)
nohup $JAVA25 \
  -Xms256m -Xmx512m \
  -jar $JAR \
  --spring.profiles.active=bench-{ADAPTER} \
  > /tmp/coupon-app.log 2>&1 &
APP_PID=$!
echo "App PID: $APP_PID"

# 헬스체크 대기 (최대 30초)
for i in $(seq 1 30); do
  curl -sf http://localhost:8080/actuator/health > /dev/null 2>&1 && echo "✅ 앱 준비됨 (${i}초)" && break
  sleep 1
done
```

**검증 포인트**: JAR_MD5를 이전 라운드와 비교. 같으면 빌드 캐시 의심 → 강제 재빌드.

---

## Step 3: 데이터 초기화 & 웜업

```bash
cd /Users/mando/kakaopay-coupon

# 어댑터에 맞게 초기화
bash perf-test/setup-reset-data.sh {ADAPTER_TYPE}
# ADAPTER_TYPE 매핑: redis→redis, mysql-atomic/mysql/skip-locked→mysql, mongo→mongo

# 웜업 — JVM JIT 안정화
k6 run perf-test/k6-smoke.js --quiet
echo "smoke 완료 → 웜업용 200 RPS 1분"
k6 run -e TARGET_RPS=200 perf-test/k6-load.js --duration 60s --quiet

# 웜업 후 카운터 재초기화
bash perf-test/setup-reset-data.sh {ADAPTER_TYPE}
```

---

## Step 4: k6 부하 테스트 (/run-stress)

```bash
LABEL="{ADAPTER}-{TARGET_RPS}rps-$(date +%Y%m%d-%H%M)"
mkdir -p docs/perf-reports/$LABEL perf-test/results

# 테스트 시작 시각 기록
START_TS=$(date +%s)
echo "테스트 시작: $(date '+%Y-%m-%d %H:%M:%S')"

k6 run \
  -e ADAPTER={ADAPTER} \
  -e TARGET_RPS={TARGET_RPS} \
  --summary-export=perf-test/results/$LABEL-summary.json \
  perf-test/k6-load.js

echo "테스트 종료: $(date '+%Y-%m-%d %H:%M:%S')"
END_TS=$(date +%s)
ELAPSED=$((END_TS - START_TS))
echo "소요: ${ELAPSED}초 → 캡처 윈도우: now-$((ELAPSED/60 + 3))m"
```

**k6 종료 직후 즉시 Step 5로 이동. 지표는 `now-8m` 안에만 있다.**

---

## Step 5: 병렬 메트릭 캡처 (/capture-metrics) — AI 자동화 핵심

**k6 종료 후 즉시 실행.** 스크립트를 직접 호출하거나 subagent를 병렬로 띄운다.

### 옵션 A: 스크립트 직접 실행 (빠른 방법)

```bash
bash perf-test/metrics-capture.sh {LABEL} 8
```

`metrics-capture.sh`가 Prometheus 쿼리 + Grafana 패널 11개를 순차 수집.

### 옵션 B: Subagent 병렬 캡처 (컨텍스트 보호 + 속도)

**Agent 1 (L1 Endpoint + 기본 지표)**:
```
Prometheus http://localhost:9090에서 다음 메트릭을 쿼리하고 결과를 JSON으로 반환하라:
- http_server_requests_seconds (P95, P99, count rate) — 쿼리 범위 last 8m
- coupon_issued, coupon_sold_out, coupon_error_5xx counter
Grafana render API로 다음 패널을 /tmp/perf-L1/ 에 저장:
- panelId=1 (TPS), panelId=2 (latency), panelId=7 (error rate)
대시보드 UID: coupon-bench, from=now-8m, to=now
```

**Agent 2 (L2 시스템 자원)**:
```
Prometheus http://localhost:9090에서 다음 메트릭을 쿼리하고 결과를 JSON으로 반환하라:
- hikaricp_connections_pending max_over_time[8m]
- hikaricp_connections_acquire_seconds histogram
- tomcat_threads_busy_threads max_over_time[8m]
Grafana render API로 다음 패널을 /tmp/perf-L2/ 에 저장:
- panelId=3 (HikariCP active), panelId=4 (acquire time), panelId=8 (Tomcat threads)
대시보드 UID: coupon-bench, from=now-8m, to=now
```

**Agent 3 (L3 JVM + 어댑터 전용)**:
```
Prometheus http://localhost:9090에서 다음 메트릭을 쿼리하고 결과를 JSON으로 반환하라:
- jvm_memory_used_bytes{area='heap'} max_over_time[8m]
- jvm_gc_pause_seconds_max max_over_time[8m]
- coupon_port_acquire_seconds (어댑터별 P95)
Grafana render API로 다음 패널을 /tmp/perf-L3/ 에 저장:
- panelId=5 (heap), panelId=6 (GC), panelId=10 (port acquire), panelId=11 (MySQL 단계), panelId=12 (Redis INCR)
대시보드 UID: coupon-bench, from=now-8m, to=now
```

3개 Agent를 동시에 띄우고(병렬), 모두 완료되면 Step 6으로.

**subagent 사용 시점 판단:**
- 단일 라운드 빠른 확인 → 옵션 A (스크립트)
- A/B 비교 또는 메인 컨텍스트 보호 필요 → 옵션 B (subagent)

---

## Step 6: 캡처 검증

```bash
# PNG 파일 수 확인
ls docs/perf-reports/$LABEL/*.png | wc -l   # → 8 이상 기대

# 메트릭 요약 확인
cat docs/perf-reports/$LABEL/metrics-summary.json
```

**PNG < 8개**: Grafana renderer가 떠있는지 확인 후 metrics-capture.sh 재실행.
**metrics-summary.json 없음**: Prometheus 쿼리가 실패한 것 → 앱이 기동 중인지 확인.

---

## Step 7: REPORT.md 생성 (/make-report)

`docs/perf-reports/{LABEL}/REPORT.md`에 다음 구조로 작성:

```markdown
# 성능 테스트 보고서

## 테스트 환경
- 어댑터: {ADAPTER}
- 목표 RPS: {TARGET_RPS}
- 실행 시각: {datetime}
- 로컬 Docker Compose 환경 기준 (운영 환경과의 차이: [명시])

## L1. Endpoint 지표 (정상/비정상 판정)
| 지표 | 실측값 | SLO | 판정 |
|------|--------|-----|------|
| P95 응답시간 | {p95}ms | ≤500ms | ✅/❌ |
| P99 응답시간 | {p99}ms | ≤1000ms | ✅/❌ |
| 5xx 에러율 | {err}% | ≤0.1% | ✅/❌ |
| 발급 정확성 | {issued}건 | 정확히 1000 | ✅/❌ |

## L2. 시스템 자원 (이상 없으면 L3 생략)
- HikariCP Pending 최대: {pending} (pool=50)
- Tomcat Active 스레드 최대: {tomcat_active}

## L3. JVM (이상 없으면 L4 생략)
- Heap Max: {heap_max}MB
- GC Pause Max: {gc_max}ms

## 어댑터 전용 지표
- Port 획득 P95: {port_p95}ms
- [Redis INCR / MySQL 단계별 / MongoDB 명령]

## 결론 및 다음 단계
[숫자 기반 결론. "문제없음" 한 줄 금지]
```

---

## A/B 비교 모드

"redis vs skip-locked 비교" 요청 시:

```
Step 2~6을 ADAPTER=redis로 실행 → LABEL_A 생성
Step 3~6을 ADAPTER=skip-locked로 실행 → LABEL_B 생성
Step 7에서 두 LABEL의 metrics-summary.json을 읽어 비교표 생성
```

비교표 형식:
```markdown
| 지표 | redis | skip-locked | 차이 |
|------|-------|-------------|------|
| P95 | 495ms | 951ms | redis 48% 빠름 |
```

---

## 참조

| 문서/스킬 | 내용 |
|---|---|
| `stress-test-methodology` 스킬 | 방법론 철학, 레이어 분석, AI 활용 원칙 |
| `perf-tuning-cycle` 스킬 | 변경 후 단일 사이클 (이 스킬의 상위) |
| `perf-test-reference` 스킬 | k6 스크립트, SLO, 실행 프로토콜 |
| `.claude/project-context.md` | Grafana UID/panelId, Prometheus 쿼리, 어댑터 설정 |
| `perf-test/metrics-capture.sh` | Prometheus+Grafana 자동 캡처 스크립트 |
