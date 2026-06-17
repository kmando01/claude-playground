---
name: perf-bench
description: "kakaopay-coupon 전용 성능 벤치마크 AI 오케스트레이터. 어댑터 프로파일 + 목표 RPS를 받아 빌드→웜업→k6→병렬 메트릭 캡처(subagent)→REPORT.md까지 한 사이클을 자동 실행. Use when: '어댑터 테스트 돌려줘', 'redis 100K 테스트', '/perf-bench', 'A/B 비교 테스트', '성능 라운드 실행'. 반드시 kakaopay-coupon 프로젝트 루트(/Users/mando/kakaopay-coupon)에서 실행."
---

# perf-bench — kakaopay-coupon 자동 벤치마크

> kakaopay-coupon 전용. 스트레스 테스트 방법론(`stress-test-methodology` 스킬)의 Section 5 AI 자동화 패턴을 구현한다.

---

## Step 0: 입력 파싱

사용자 메시지에서 다음을 추출한다:

| 파라미터 | 기본값 | 예시 |
|---|---|---|
| `ADAPTER` | redis | `redis`, `mysql-atomic`, `skip-locked`, `mongo`, `mysql` |
| `TARGET_RPS` | 3000 | `3000`, `10000`, `50000`, `100000` |
| `LABEL` | `{ADAPTER}-{TARGET_RPS}rps` | 자동 생성 |
| `A/B 비교` | 없음 | "redis vs skip-locked 비교" |

**빠른 추출 규칙:**
- "redis 100K" → ADAPTER=redis, TARGET_RPS=100000
- "skip-locked 30K" → ADAPTER=skip-locked, TARGET_RPS=30000
- "기본값" / 미입력 → ADAPTER=redis, TARGET_RPS=3000

---

## Step 1: 사전 검증 (GATE) — Prometheus·Grafana 기동 확인 필수

> ⛔ **Prometheus·Grafana 없이 테스트 시작 금지.**
> 테스트 중에만 존재하는 시계열 지표(HikariCP pending 급등, acquire time 폭발, TPS 곡선)는
> 테스트가 끝나면 영영 사라진다. 캡처는 k6 실행 중에만 가능하고, 그러려면 Prometheus가
> 먼저 떠서 메트릭을 수집하고 있어야 한다. **이 순서를 뒤집으면 숫자만 있고 증거 없는 보고서가 된다.**

```bash
# ── 1. Prometheus·Grafana 기동 (테스트 전 필수) ──────────────────
docker compose up -d prometheus grafana
until curl -sf http://localhost:9090/-/healthy 2>/dev/null; do sleep 2; done && echo "✅ Prometheus"
until curl -sf http://localhost:3000/api/health 2>/dev/null | grep -q ok; do sleep 2; done && echo "✅ Grafana"

# ── 2. 앱이 이미 떠 있다면 Prometheus가 메트릭을 수집 중인지 확인 ──
curl -sf http://localhost:9090/api/v1/query \
  --data-urlencode 'query=hikaricp_connections_pending' 2>/dev/null \
  | python3 -c "import sys,json; r=json.load(sys.stdin); print('Prometheus 수집 중 ✅' if r['data']['result'] else '앱 미기동 or scrape 안 됨 — Step 2에서 기동')"
```

> Prometheus scrape interval 기본 15s. 앱 기동 후 30s 이상 대기 후 k6 시작할 것.

사전 검증 실패 시: `docker compose up -d prometheus grafana` 후 재확인.

---

## Step 2: 앱 빌드 & 기동 (/deploy-target)

```bash
cd /Users/mando/kakaopay-coupon

# 기존 앱 종료
pkill -f "kakaopay-coupon.*jar" 2>/dev/null || true
sleep 2

# Gradle 빌드
JAVA25="/Users/mando/.gradle/jdks/eclipse_adoptium-25-aarch64-os_x.2/jdk-25+36/Contents/Home/bin/java"
./gradlew bootJar -q

# 배포 이미지(JAR) 다이제스트 기록 — AI 자동화 검증 핵심
JAR_MD5=$(md5 -q build/libs/kakaopay-coupon-0.0.1-SNAPSHOT.jar)
echo "JAR digest: $JAR_MD5"

# 기동
nohup $JAVA25 \
  -Xms512m -Xmx1g \
  -jar build/libs/kakaopay-coupon-0.0.1-SNAPSHOT.jar \
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

> ⚠️ **워밍업 핵심 원칙**: sold-out(거절) 경로만 타는 워밍업은 발급 성공 경로(INSERT/findAndModify)를
> JIT 컴파일하지 못한다. **발급 성공 경로를 3사이클 완전 소화**해야 Cold start 노이즈 없는 수치를 얻는다.
> 자세한 배경: `stress-test-methodology` § 1.3

```bash
cd /Users/mando/kakaopay-coupon

# ── 풀패스 워밍업 (3사이클) ────────────────────────────────────
# 각 사이클: reset → 발급 경로 limit까지 소진 → 반복
# 목적: coupon INSERT / MongoDB findAndModify+INSERT / Redis INCR 모두 JIT 컴파일

K6_FULL_WARMUP='
import http from "k6/http";
export const options = { scenarios: { w: {
  executor: "ramping-arrival-rate", startRate: 500, timeUnit: "1s",
  preAllocatedVUs: 100, maxVUs: 1000,
  stages: [
    { duration: "3s",  target: 3000 },
    { duration: "10s", target: 3000 },
    { duration: "2s",  target: 0 },
  ],
}}};
export default function () {
  http.post("http://localhost:8080/api/v1/events/1/coupons", null,
    { headers: { "X-User-Id": String(__VU * 100000 + __ITER + 9000000) } });
}'

for CYCLE in 1 2 3; do
  bash perf-test/reset-test-data.sh {ADAPTER_TYPE}
  echo "$K6_FULL_WARMUP" | k6 run --quiet -
  echo "  사이클 $CYCLE/3 완료"
done

# 판정: 사이클 1 avg >> 사이클 2 avg 이면 워밍업 미완 — 사이클 추가
# 수렴 확인 후 본 측정용 리셋
bash perf-test/reset-test-data.sh {ADAPTER_TYPE}
echo "✅ 풀패스 워밍업 완료"
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
  perf-test/load.js

echo "테스트 종료: $(date '+%Y-%m-%d %H:%M:%S')"
END_TS=$(date +%s)
ELAPSED=$((END_TS - START_TS))
echo "소요: ${ELAPSED}초 → 캡처 윈도우: now-$((ELAPSED/60 + 3))m"
```

**k6 종료 직후 즉시 Step 5로 이동. 지표는 `now-8m` 안에만 있다.**

> ⛔ **캡처 생략 절대 금지 — 반복된 실수 경고**
>
> 이 경고는 실제로 두 번 반복된 실수(2026-06-15)에서 비롯됐다:
> - 25 라운드를 bash 루프로 자동화하면서 capture-metrics.sh를 한 번도 호출하지 않음
> - Prometheus를 테스트 후에 기동 → 시계열 데이터 없음 → metrics-summary.json 전부 null
> - Grafana 패널 PNG 0개, L2/L3/L4 지표 없는 보고서 완성
>
> **캡처 없는 보고서는 "병목이 어디다"를 주장만 하고 증명하지 못한다.**
> k6 루프 안에서 각 라운드 직후 capture-metrics.sh를 호출하는 구조로 작성해야 한다.
>
> ```bash
> # ✅ 올바른 자동화 구조
> for ADAPTER in redis mysql-atomic; do
>   start_app "$ADAPTER"
>   full_path_warmup "$ADAPTER"        # 발급 경로 3사이클
>   for RPS in 3000 10000; do
>     reset_data "$ADAPTER"
>     k6 run ... &                     # 백그라운드 실행
>     K6_PID=$!
>     sleep 18                         # 피크 구간 도달 대기
>     bash capture-metrics.sh "$ADAPTER-${RPS}rps" 2  # ← 피크 중 즉시 캡처
>     wait $K6_PID                     # k6 완료 대기
>   done
> done
>
> # ❌ 잘못된 구조 (캡처 없는 루프)
> for RPS in 3000 10000 30000; do
>   RESULT=$(k6 run ...)               # 캡처 없이 다음으로 넘어감
>   echo "$RESULT" > raw.txt
> done
> ```

---

## Step 5: 병렬 메트릭 캡처 (/capture-metrics) — AI 자동화 핵심

**k6 종료 후 즉시 실행.** 스크립트를 직접 호출하거나 subagent를 병렬로 띄운다.

### 옵션 A: 스크립트 직접 실행 (빠른 방법)

```bash
bash perf-test/capture-metrics.sh {LABEL} 8
```

`capture-metrics.sh`가 Prometheus 쿼리 + Grafana 패널 11개를 순차 수집.

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

**PNG < 8개**: Grafana renderer가 떠있는지 확인 후 capture-metrics.sh 재실행.
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
| `perf-test/capture-metrics.sh` | Prometheus+Grafana 자동 캡처 스크립트 |
