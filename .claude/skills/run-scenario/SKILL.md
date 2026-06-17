---
name: run-scenario
description: "kakaopay-coupon 시나리오 실행 오케스트레이터. harness/coupon-event-domain.md를 읽어 HC 검증·SLO 판정·이상패턴 대응을 자동 적용. 사용자는 시나리오 ID만 입력하면 됨. Use when: '/run-scenario A', '/run-scenario B', '시나리오 A 실행', '시나리오 B 돌려줘'. kakaopay-coupon 프로젝트(/Users/mando/kakaopay-coupon)에서만 유효."
---

# run-scenario — 도메인 하네스 기반 자동 실행

> **핵심 원칙**: 판정 기준은 프롬프트에 적지 않는다.
> `harness/coupon-event-domain.md`에서 자동으로 읽어온다.

---

## Step 0: 하네스 로드

**반드시 먼저 실행.** 나머지 모든 단계의 판단 근거가 된다.

```
Read /Users/mando/kakaopay-coupon/harness/coupon-event-domain.md
```

로드 후 추출:
- `SCENARIOS` 섹션에서 해당 시나리오 ID의 k6 파라미터
- `SLO` 섹션에서 통과 기준
- `HC` 섹션에서 검증 쿼리
- `ANOMALY` 섹션에서 이상 패턴 목록

---

## Step 1: 입력 파싱

### 시나리오 ID를 모를 때 → 메뉴 출력 후 대기

사용자가 ID를 지정하지 않았거나 "뭐가 있어?", "목록 보여줘" 등을 입력하면
아래 메뉴를 출력하고 선택을 기다린다:

```
어떤 시나리오를 실행할까요?

  A — 정확성 검증      발급 수가 정확히 1,000건인지, 중복 발급이 없는지 확인
  B — 버스트 흡수      10만 트래픽 집중 처리. 5xx 비율·응답 시간 측정
  C — 중복 요청 방지   같은 UserId로 여러 번 요청해도 1건만 발급되는지 확인
  D — 마감 후 차단     1,000건 소진 후 추가 요청이 정상 거절되는지 확인
  E — 오픈 전 차단     이벤트 시작 전 요청이 거절되는지 확인
  F — 멀티 인스턴스    서버 여러 대일 때도 발급 수가 정확한지 확인
  G — 이벤트 조회 부하 GET /events 캐시 없는 상태에서 MySQL 부하 측정

→ "A 실행해줘" 또는 "정확성 테스트" 처럼 말하면 됩니다.
```

### 자연어 → 시나리오 ID 매핑

사용자가 ID 대신 설명으로 말해도 자동 매핑:

| 입력 예시 | 매핑 |
|---|---|
| "정확성", "1000건 맞는지", "중복 없는지" | A |
| "버스트", "10만", "대용량", "부하" | B |
| "멱등성", "중복 요청", "같은 유저 여러 번" | C |
| "마감 후", "소진 이후", "품절 후" | D |
| "오픈 전", "시작 전", "시간 전" | E |
| "멀티 인스턴스", "여러 서버", "다중 서버" | F |
| "읽기", "조회", "GET", "pre-event", "캐시" | G |

### 추출 대상

| 파라미터 | 방법 |
|---|---|
| `SCENARIO_ID` | ID 직접 입력 또는 자연어 매핑 |
| `ADAPTER` | 언급 없으면 redis (기본값) |
| `SPECIAL` | "이번 라운드만의 조건" (없으면 하네스 기본값 사용) |

---

## Step 2: 배포 검증 (deploy_verify)

하네스 `VERIFY.배포 후 검증` 단계 실행:

```bash
cd /Users/mando/kakaopay-coupon

# JAR digest 기록 (이미지 캐시 방지 — 패턴 3 대응)
JAR_DIGEST=$(md5 -q build/libs/kakaopay-coupon-*.jar 2>/dev/null || echo "빌드 필요")
echo "JAR digest: $JAR_DIGEST"

# 헬스체크
curl -sf http://localhost:8080/actuator/health | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print('UP' if d['status']=='UP' else 'DOWN')"

# Prometheus 메트릭 수집 확인
curl -sf http://localhost:8080/actuator/prometheus | grep -c "hikaricp_connections{"
```

**헬스체크 실패 시**: 앱 기동 먼저 (`perf-bench` 스킬 Step 2 참조).
**digest 이전 라운드와 동일 시**: 경고 출력 후 사용자 확인.

---

## Step 3: 환경 초기화

하네스 `VERIFY.부하 시작 전 검증` 실행:

```bash
# 어댑터에 맞게 초기화
bash perf-test/reset-test-data.sh {ADAPTER_TYPE}

# 연기 smoke 테스트 (JVM 웜업)
k6 run perf-test/smoke.js --quiet
bash perf-test/reset-test-data.sh {ADAPTER_TYPE}  # smoke 후 재초기화
```

---

## Step 4: k6 실행

하네스 `SCENARIOS.{ID}` 섹션의 파라미터로 실행:

```bash
LABEL="{SCENARIO_ID}-{ADAPTER}-$(date +%Y%m%d-%H%M)"
mkdir -p perf-test/results docs/perf-reports/$LABEL

k6 run \
  -e SCENARIO={k6_SCENARIO}    \  # 하네스에서 읽어온 값
  -e ADAPTER={ADAPTER}          \
  -e TARGET_RPS={TARGET_RPS}    \  # 하네스에서 읽어온 값
  --summary-export=perf-test/results/$LABEL-summary.json \
  perf-test/load.js
```

**k6 종료 직후 즉시 Step 5로.** 지표는 now-8m 안에만 있다.

---

## Step 5: 메트릭 캡처

```bash
bash perf-test/capture-metrics.sh $LABEL 8
```

11개 Grafana 패널 + metrics-summary.json 자동 저장.

---

## Step 6: HC 검증 (가장 중요)

하네스 `VERIFY.테스트 종료 후 HC 검증` 실행:

```bash
bash perf-test/verify-hc.sh 1 {ADAPTER}
```

**HC 검증 결과 저장:**
```bash
bash perf-test/verify-hc.sh 1 {ADAPTER} > docs/perf-reports/$LABEL/hc-verify.txt 2>&1
HC_EXIT=$?
```

- `HC_EXIT=0`: 전부 PASS → Step 7 진행
- `HC_EXIT=1`: 하나라도 FAIL → **전체 FAIL 판정. 리포트 작성 후 종료**

---

## Step 7: 이상 패턴 감지

하네스 `ANOMALY` 섹션의 각 패턴을 metrics-summary.json + hc-verify.txt와 대조:

| 체크 항목 | 데이터 소스 |
|---|---|
| 발급 수 ≠ 1000 | hc-verify.txt HC-01 |
| 클라이언트 0% + 서버 에러 증가 | hc-verify.txt 교차 검증 |
| 비교군·대조군 결과 3% 이내 | 이전 라운드 비교 (있을 때) |
| 거절 응답 > 성공 응답 속도 | metrics-summary.json 별도 쿼리 필요 |
| heap 우상향 | metrics-summary.json L3_jvm.heap_used_max_mb 추세 |
| RPS 비선형 흔들림 | k6 summary dropped_iterations |

감지된 패턴은 해당 ANOMALY 섹션의 **대응 액션을 그대로 인용**한다.

---

## Step 7.5: 이전 라운드 대비 비교 (변경 전 수치 강제 확보)

**"변경 전 수치 없이는 좋아졌다고 말할 수 없다" — 5원칙 2번 기계적 강제**

```bash
bash perf-test/compare-metrics.sh {LABEL}
# PREV_LABEL 생략 시 → docs/perf-reports/ 에서 가장 최근 라운드 자동 탐색
# 첫 라운드면 "기준선 수립"으로 기록
```

**출력**: `docs/perf-reports/{LABEL}/comparison.md`

| 판정 | 의미 | 다음 액션 |
|---|---|---|
| ✅ 개선 (≤-5%) | 변경이 효과 있음 | REPORT에 근거로 활용 |
| ➡️ 유지 (-5%~+5%) | 변경이 성능 중립 | 기능 변경이면 OK |
| ⚠️ 주의 (+5%~+20%) | 소폭 악화 | 원인 파악 후 허용 여부 판단 |
| ❌ 악화 (>+20%) | 성능 회귀 | L1→L4 레이어 분석 진입 필수 |

**❌ 악화 감지 시** → 즉시 화이트박스 분석 자동 실행:

```bash
# compare-metrics.sh 가 exit 1 반환 시 연속 실행
bash perf-test/compare-metrics.sh {LABEL}
COMPARE_EXIT=$?

if [ $COMPARE_EXIT -eq 1 ]; then
  echo "❌ 성능 악화 감지 — 화이트박스 분석 진입 (L3→L4)"
  bash perf-test/profile-on-degradation.sh {LABEL}
fi
```

분석 결과는 `docs/perf-reports/{LABEL}/` 에 저장:
- `profile-threads.txt` — BLOCKED/WAITING 스레드 즉시 확인
- `profile-heap-histo.txt` — 클래스별 객체 수
- `profile-cpu.jfr` — JMC / IntelliJ Profiler로 열어 플레임 그래프 확인
- `profile-summary.md` — 요약 + 다음 액션

REPORT.md 전체 판정도 자동으로 FAIL로 설정.

## Step 8: REPORT.md 생성

하네스 `REPORT_FORMAT` 구조로 작성:

`docs/perf-reports/{LABEL}/REPORT.md`

```markdown
# 시나리오 {ID} 결과 — {ADAPTER} @ {TARGET_RPS} RPS
실행: {datetime}  |  환경: 로컬 Docker Compose (단일 인스턴스)

## HC 검증
[hc-verify.txt 결과 전부 포함 — 8개 각각 PASS/FAIL]

## L1 성능 판정
[metrics-summary.json + SLO 비교표]

## 이상 패턴 감지
[감지된 패턴 + ANOMALY 대응 액션 인용]
[없으면: "감지된 이상 패턴 없음"]

## 전체 판정
PASS / FAIL  — 근거: [구체적 수치]
```

**금지 표현**: "전반적으로 정상", "큰 문제 없음", "괜찮아 보임"
**필수**: HC 8개 각각 명시, 수치 기반 결론

---

## 빠른 참조 — 시나리오 ID → k6 파라미터

> 아래는 하네스 SCENARIOS 섹션의 요약. 하네스가 갱신되면 이 표는 무시하고 하네스를 읽을 것.

| ID | SCENARIO | TARGET_RPS | 핵심 판정 |
|---|---|---|---|
| A | burst | 10000 | 발급 정확히 1000, HC-01·02 |
| B | burst | 100000 | 5xx ≤ 0.1%, 시스템 한계 기록 |
| C | burst | 1000 (중복) | HC-02, 동일 UserId row ≤ 1 |
| D | burst + 추가 | 5000 추가 | 마감 후 HC-01 유지 |
| E | burst | - | 오픈 전 거절, HC-05 |
| F | burst | 10000 (3인스턴스) | HC-07, 순번 충돌 없음 |
| G | pre-event | 3000 | read_event P95 ≤ 200ms |

---

## 참조

| 파일/스킬 | 역할 |
|---|---|
| `harness/coupon-event-domain.md` | **SSOT** — HC, SLO, 시나리오, 이상패턴 |
| `perf-test/verify-hc.sh` | HC-01~06 자동 SQL 검증 |
| `perf-test/capture-metrics.sh` | Prometheus+Grafana 캡처 |
| `perf-bench` 스킬 | 단일 라운드 전체 사이클 (이 스킬의 하위 레이어) |
| `perf-tuning-cycle` 스킬 | 변경 적용 후 반복 사이클 |
