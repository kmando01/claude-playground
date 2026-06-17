---
name: perf-tuning-cycle
description: "성능 튜닝 전체 사이클. 변경 적용 후 테스트 → 즉시 캡처 → 분석 → 보고서까지 한 바퀴. Use when user says '성능 테스트 돌려', '성능 사이클', '지표 캡처', '/perf-cycle', or after applying performance-related config/code changes."
---

# 성능 튜닝 사이클

코드/설정 변경 후 **테스트 → 캡처 → 분석 → 제안**을 한 사이클로 실행한다.
변경만 하고 끝내지 않는다. 항상 테스트로 증명하고 캡처로 기록한다.

## ⭐ 철칙 1: 지표 기반 주장 (추측 금지)

```
모든 병목·분석·결론은 Grafana/Prometheus 캡처 또는 수치를 첨부해야 한다.
캡처 없는 주장은 "추측"이며 보고서에 기재 불가.
```

**실행 원칙:**
1. 부하 테스트 후 → 즉시 Grafana 캡처 (Step 1.5, BLOCKING)
2. Grafana 캡처 실패 시 → Prometheus API로 수치 직접 쿼리해 텍스트로 증명
3. "~할 것이다", "~일 것이다" 표현 금지 — "HikariCP Pending 최대 189개(Prometheus)" 처럼 수치로

**Connection Pool 분석 예시 (올바른 방식):**
```bash
# 추측 ❌: "pool이 부족할 것이다"
# 증명 ✅: Prometheus에서 직접 확인
curl http://localhost:9090/api/v1/query?query=max_over_time(hikaricp_connections_pending[2h])
# → HikariCP Pending 최대: 189 (pool=10 대비 18.9배)
```

**Pool 최적화 기준 (지표 기반):**
- `hikaricp_connections_pending > 0` 지속 → pool 부족 확실
- `hikaricp_connections_acquire_seconds` p95 > 100ms → pool 경합 심각
- 공식: `maximumPoolSize = 목표 TPS × 평균 응답시간(초) × 1.2(여유)`

## ⭐ 철칙 2: Grafana 캡처 방법 (항상 이미지로)

**Grafana Image Renderer 없이는 캡처 불가.** docker-compose에 renderer 추가 필수:

```yaml
grafana:
  environment:
    GF_RENDERING_SERVER_URL: http://renderer:8081/render
    GF_RENDERING_CALLBACK_URL: http://grafana:3000/
renderer:
  image: grafana/grafana-image-renderer:latest
  ports: ["8081:8081"]
```

**패널별 캡처 명령 (부하 테스트 완료 직후 실행):**
```bash
BASE="http://localhost:3000/render/d-solo/{대시보드-uid}/{대시보드-slug}"
TIME="from=now-Xm&to=now&width=1200&height=400"

# 핵심 4개 패널 (항상 캡처)
curl -s -o "perf-reports/{label}/hikaricp-pending.png"  "$BASE?panelId=3&$TIME"
curl -s -o "perf-reports/{label}/hikaricp-acquire.png"  "$BASE?panelId=4&$TIME"
curl -s -o "perf-reports/{label}/http-tps.png"          "$BASE?panelId=1&$TIME"
curl -s -o "perf-reports/{label}/http-latency.png"      "$BASE?panelId=2&$TIME"
```

**Playwright 스크린샷이 폰트 로딩 타임아웃으로 실패할 때**: render API로 대체.
**캡처 실패 시**: `curl http://localhost:9090/api/v1/query?query=...` Prometheus API로 수치를 직접 텍스트로 기록 (캡처 없는 주장은 보고서 기재 불가).

## 전체 흐름

```
Step 0: 사전 검증 (GATE)
  ↓
Step 1: 성능 테스트 (smoke → load)
  ↓
⛔ Step 1.5: 캡처 즉시 실행 (load 완료 직후 — 분석보다 먼저)
  ↓
Step 2: 분석 (Hidden Behavior + Bottleneck)
  ↓
Step 3: 보고서 + Action Items
  ↓
Step 4: 진단 (다음 단계 진행 GATE)
```

### A/B 비교 사이클

```
Step 0 → reset → Step 1A(BEFORE) → Step 1.5 캡처 → reset → Step 1B(AFTER) → Step 1.5 캡처 → Step 2 비교 분석
```

---

## Step 0: 프로젝트 컨텍스트 로드

`.claude/project-context.md`의 `## [perf-tuning-cycle]` 섹션이 있으면 읽는다.
- Grafana 대시보드 UID, 패널 ID, 캡처 스크립트를 이 섹션에서 가져온다.
- 없으면 Step 1 이후 단계에서 범용 방식(Grafana URL 직접 구성)으로 진행한다.

## Step 0.5: 사전 검증 (GATE)

**메트릭 미수집 + 환경 오염 상태에서 테스트 돌리면 분석 불가. 통과해야 Step 1 진행.**

```bash
# 1. HikariCP 메트릭 노출 확인
curl -sf http://localhost:{api-port}/actuator/prometheus | grep hikaricp_connections{

# 2. 환경 초기화 (DB + Redis flush, Kafka offset)
bash perf-test/setup-reset-data.sh

# 3. Kafka 있는 경우: lag = 0 확인
# project-context.md의 kafka consumer-group, work topic 참조
```

> **⚠️ 앱 재시작 시 강화 웜업 필수**: 표준 smoke(50 TPS×3min)는 JVM JIT 임계치 미달.
> 재시작 후엔 smoke 완료 후 100 TPS로 2분 추가 웜업.
> 프로젝트별 웜업 절차: `project-context.md → [perf-tuning-cycle]` 섹션

---

## Step 1: 성능 테스트 실행

```bash
# smoke — JVM warm-up, 100% 통과 확인
docker compose --profile test run --rm k6 run /scripts/k6-smoke.js

# load — 결과 저장
mkdir -p perf-test/results/{label}
docker compose --profile test run --rm \
  -v "$(pwd)/perf-test/results:/scripts/results" \
  k6 run \
  --out experimental-prometheus-rw \
  --summary-export=/scripts/results/{label}/k6-summary.json \
  /scripts/k6-load.js
```

> 로컬 Docker Compose 절대값 보고 시 **"로컬 환경 기준"** 단서 필수.
> 프로젝트별 TPS 목표, 볼륨 경로: `references/alarm-project.md`

---

## ⛔ Step 1.5: 캡처 즉시 실행 (BLOCKING)

**load 완료 직후 — 데이터는 `now-6m` 안에만 있다. 분석보다 캡처가 먼저.**

```bash
DIR="docs/perf-reports/{date}-{label}" && mkdir -p "$DIR"
```

**캡처 스크립트**: `.claude/project-context.md → [perf-tuning-cycle]` 섹션의 "Grafana 캡처 스크립트" 실행

```bash
# 캡처 완료 확인 — 5개 미만이면 재실행
ls "$DIR"/*.png | wc -l   # → 5 이상
cp perf-test/results/{label}/k6-summary.json "$DIR/"
```

> 다른 프로젝트: Grafana `d-solo` + `panelId` 방식으로 직접 캡처. 전체 대시보드 URL 사용 금지(collapsed 패널 N/A).

---

## Step 2: 분석

두 가지 관점으로 분석한다. 상세 체크리스트: `references/analysis-guide.md`

| 관점 | 확인 내용 |
|------|----------|
| **Hidden Behavior** | TPS 드롭, 레이턴시 스파이크, 간헐적 timeout 등 이상 현상 → 프레임워크 내부 동작 추론 |
| **Bottleneck** | 목표 TPS vs 설정값 수치적 불일치 → Prometheus 메트릭으로 근거 |

교차 분석 패턴 (`references/analysis-guide.md`):
`p95 높음 + HikariCP pending 높음` → OSIV 또는 pool size
`TPS 정체 + consumer lag 증가` → consumer 처리량 < 유입량

---

## Step 3: 보고서 + Action Items

`docs/perf-reports/{date}-{label}/REPORT.md` 생성.
보고서 템플릿 + Action Items 형식: `references/report-template.md`

이전 보고서 Action Items 상태 업데이트 (TODO → DONE/REVERTED/N/A) 필수.

---

## Step 4: 진단 (다음 단계 진행 GATE)

**처방 전 "왜 그 처방인가"를 숫자로 증명해야 한다.**

진단 항목: HikariCP acquire/usage 시간, 트랜잭션 경계 정적 분석, Consumer 파이프라인 상태
상세 진단 절차 + DIAGNOSIS.md 템플릿: `references/diagnosis-guide.md`

**DIAGNOSIS.md 없으면 다음 설계/구현 진행 금지.**

---

## 관련 스킬 / 참조

| 문서 | 용도 |
|------|------|
| `.claude/project-context.md` | **프로젝트 특화**: Grafana UID/panelId/캡처 스크립트/Prometheus 쿼리/TPS 목표 |
| `references/analysis-guide.md` | Hidden Behavior + Bottleneck 체크리스트, 교차 분석 패턴 |
| `references/diagnosis-guide.md` | Step 4 진단 절차, DIAGNOSIS.md 템플릿 |
| `references/report-template.md` | REPORT.md + Action Items 형식 |
| `perf-test-reference` 스킬 | k6 스크립트 템플릿, thresholds |
| `static-perf-analysis` 스킬 | 테스트 전 코드 정적 분석 |
