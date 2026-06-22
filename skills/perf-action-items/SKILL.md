---
name: perf-action-items
description: "성능 튜닝 Action Items를 하나씩 누적 적용하면서 각각 성능 테스트로 영향도를 검증하는 워크플로우. Use when user says '/perf-action', 'Action Items 진행', '성능 개선 하나씩', or after performance report with TODO action items."
---

# 성능 Action Items 순차 검증 (Perf Action Items)

Action Items를 **하나씩** 적용하고, 매번 성능 테스트로 효과를 증명한다.
핵심 원칙: **One Knob at a Time** — 한 번에 하나만 바꾸고, 측정하고, 판단한다.

## 전체 흐름

```
Step 0: Action Items 큐 로드 (보고서에서 TODO 수집)
  ↓
Step 1: 다음 Item 선택 (우선순위 기반)
  ↓
Step 2: 변경 유형 판별 (코드 변경 vs 확인만)
  ↓
Step 2.5: 근본 원인 분석 (CRITICAL — 숫자 조정 전 필수)
  ↓
Step 3: 변경 적용 (단일 변수만)
  ↓
Step 4: 성능 테스트 실행 (perf-tuning-cycle 스킬)
  ↓
Step 5: 판정 (개선/무효/악화)
  ↓
Step 6: 기록 + 다음 Item으로 (→ Step 1)
```

## Step 0: Action Items 큐 로드

1. `docs/perf-reports/INDEX.md`에서 최신 보고서 확인
2. 최신 보고서의 Action Items에서 **TODO** 상태인 항목 수집
3. 우선순위 테이블 기준으로 정렬
4. 현재 큐를 사용자에게 보여주고 순서 확인

```
[큐 예시]
1. A3 SimpleClientHttpRequestFactory 교체 (High/Low) ← 다음
2. A6 @Transactional 외부 호출 확인 (High/Low)
3. B1 Stress 테스트 5K TPS (High/Low)
...
```

## Step 1: 다음 Item 선택

우선순위 테이블에서 다음 TODO 항목을 선택한다.
사용자에게 확인: "다음은 [A3: SimpleClientHttpRequestFactory 교체]입니다. 진행할까요?"

## Step 2: 변경 유형 판별

| 유형 | 설명 | 예시 | 다음 단계 |
|------|------|------|-----------|
| **확인만** | 코드 리뷰로 결론 | A6: @Transactional 외부 호출 | → 코드 분석 → **분석 보고서 작성** → Step 6 |
| **설정 변경** | application.yml 등 수정 | HikariCP pool 조정 | → Step 3 |
| **코드 변경** | 소스 코드 수정 | A3: HTTP 클라이언트 교체 | → Step 3 |
| **테스트만** | 기존 설정의 한계 측정 | B1: Stress 5K TPS | → Step 4 직행 |

### 모든 유형 공통: 모니터링 지표 캡처 필수 (CRITICAL)

**유형에 관계없이, 보고서 작성 시 관련 모니터링 지표를 반드시 캡처한다.**

1. 해당 Item과 관련된 Grafana 패널 / Prometheus 쿼리를 식별
2. 현재 상태를 캡처하여 `docs/perf-reports/{date}-action-{id}/` 에 저장
3. 지표가 Prometheus에 노출되지 않으면 → **노출 안됨을 확인하고 기록** (그 자체가 발견사항)
4. 보고서에 캡처 파일을 참조하며, 캡처 불가 시 사유를 명시

| 유형 | 캡처 예시 |
|------|-----------|
| 확인만 | 관련 지표의 **현재 상태** (CB state, consumer lag, pool usage 등) |
| 설정 변경 | **Before/After** Grafana 패널 PNG |
| 코드 변경 | **Before/After** Grafana 패널 PNG + OS 레벨 (netstat 등) |
| 테스트만 | 테스트 중 Grafana 패널 PNG + Prometheus 수치 |

**안티패턴**: 캡처 없이 "확인함, 문제 없음" → BLOCK.

### "확인만" 유형 보고서 규칙

**성능 테스트는 불필요하지만, 분석 보고서 + 모니터링 캡처는 필수다.**

`docs/perf-reports/{date}-action-{id}/REPORT.md`에 반드시 포함:
1. **분석 대상**: 코드/설정 파일 경로 + 관련 스니펫 (증거)
2. **모니터링 캡처**: 관련 지표 현재 상태 (Grafana PNG 또는 Prometheus 쿼리 결과)
3. **분석 과정**: 어떤 논리로, 어떤 공식/수치로 판단했는지
4. **위험 시나리오 계산**: worst case 수치 계산 필수 (공식 위반 여부)
5. **판정 + 근거**: N/A면 왜 안전한지, 조치 필요면 구체적 권장값
6. **후속 조치**: 설정 변경이 필요하면 별도 Action Item으로 등록

## Step 2.5: 근본 원인 분석 (CRITICAL)

**설정값 조정(pool, threads 등) 전에 반드시 수행. 숫자를 올리는 것은 답이 아니다.**

### 원칙: 모든 설정값은 실측 데이터에서 역산한다

임의의 숫자를 넣지 않는다. 목표 TPS + 실측 시간에서 계산한다.

### 핵심 공식 (Little's Law)

```
pool    = target_TPS × T_db / 1000
threads = target_TPS × T_req / 1000
```

- `T_db`: 커넥션 점유 시간. 실측: `hikaricp_connections_usage_seconds`
- `T_req`: 전체 요청 처리 시간. 실측: `http_server_requests_seconds`

### 분석 프로세스

1. **현상 관찰** → 2. **관계 파악** (공식이 맞는가?) → 3. **실측 수집** (Load에서 T_db, T_req) → 4. **역산** → 5. **근본 질문** (pool 부족? threads 과다? 쿼리 느림?)

**안티패턴**: "Pending 높으니 pool 올리자" = Death Spiral. 임의의 숫자 금지.

상세 공식, 예시, 안티패턴 사례는 `references/root-cause-analysis.md` 참조.

## Step 3: 변경 적용 (단일 변수 원칙)

**CRITICAL: 이 Item과 관련된 변경만 한다. 다른 개선은 절대 함께 하지 않는다.**

1. 변경 전 상태 기록 (Before)
2. 변경 적용
3. 빌드 성공 확인 (`./gradlew build`)
4. 변경 사항 요약을 사용자에게 보여줌

```
[변경 요약]
Item: A3 - SimpleClientHttpRequestFactory → HttpComponentsClientHttpRequestFactory
Before: SimpleClientHttpRequestFactory (커넥션 풀 없음)
After: HttpComponentsClientHttpRequestFactory (maxTotal=100, maxPerRoute=20)
파일: alarm-client-external/.../RestClientConfig.kt, build.gradle.kts
```

## Step 4: 성능 테스트 실행

`perf-tuning-cycle` 스킬의 단일 사이클을 실행한다:

1. **DB/Redis 클린** (매 테스트 전 필수)
2. **Smoke 테스트** → 100% 통과 확인
3. **Load 테스트** → summary 보존
4. **⛔ Grafana 캡처 즉시 실행** → load 완료 직후 `perf-tuning-cycle` Step 1.5 명령 실행
5. **Prometheus 지표** → 숫자 기록

캡처 디렉토리: `docs/perf-reports/{date}-action-{id}/`

### ⛔ load 완료 직후 반드시 실행 (분석보다 먼저)

**캡처 스크립트**: `.claude/project-context.md → [perf-tuning-cycle]` 섹션의 "Grafana 캡처 스크립트"를 실행한다.

```bash
DIR="docs/perf-reports/{date}-action-{id}"
mkdir -p "$DIR"

# project-context.md의 캡처 스크립트 실행 (DIR 변수 위에서 설정 후)

cp perf-test/results/{date}-action-{id}/k6-summary.json "$DIR/"

# 캡처 확인 — 5개 미만이면 Step 5 진입 금지
COUNT=$(ls "$DIR"/*.png 2>/dev/null | wc -l)
echo "PNG 캡처 수: $COUNT"
[ "$COUNT" -ge 5 ] && echo "✅ 캡처 완료 — Step 5 진행 가능" || echo "⛔ 캡처 부족 — 재실행 필요"
```

## Step 5: 판정

직전 결과(또는 베이스라인)와 비교하여 판정한다.

| 판정 | 기준 | 액션 |
|------|------|------|
| **개선** | p95 개선 OR 내부 지표 개선 (Pending 감소 등) | 변경 유지 + 커밋 |
| **무효** | 유의미한 차이 없음 (p95 +-5% 이내) | 판단 필요 — 유지 or 롤백 |
| **악화** | p95 악화 OR 에러율 증가 OR 내부 지표 악화 | **즉시 롤백** |

**무효 판정 시**: 사용자에게 판단 요청.
- 코드 품질/안정성 향상이면 유지할 수 있음 (예: 커넥션 풀 도입은 성능 무효여도 안정성 향상)
- 복잡성만 증가하면 롤백

## Step 5.5: 캡처 게이트 (BLOCK — 이 게이트를 통과해야 Step 6 진입 가능)

**보고서 작성 전에 반드시 이 체크리스트를 통과해야 한다. 하나라도 미충족 시 Step 6 진입 금지.**

```
□ Grafana 패널 PNG 저장했는가?
  - 설정/코드 변경: Before + After 둘 다
  - 확인만/테스트만: 현재 상태 캡처
  - 관련 패널: HikariCP, HTTP Response Time, 해당 항목 관련 패널
  - 캡처 불가 시: "미노출" 사유를 .txt로 기록

□ Prometheus 지표 텍스트 저장했는가?
  - curl actuator/prometheus 결과에서 관련 지표 추출 → .txt 저장

□ 보고서 디렉토리에 파일이 존재하는가?
  - ls docs/perf-reports/{date}-action-{id}/ 에 .png 또는 .txt가 있어야 함
  - 보고서 REPORT.md만 있고 캡처 파일이 없으면 → BLOCK
```

**왜 이 게이트가 필요한가**: 분석과 보고서 작성에 집중하면 캡처를 잊는다.
캡처는 보고서 작성 "전에" 해야 한다. 보고서는 캡처를 참조하는 것이지, 캡처 없이 작성하는 게 아니다.

## Step 6: 기록 + 다음

**Step 5.5 캡처 게이트를 통과한 후에만 진입한다.**

1. **보고서 작성**: `docs/perf-reports/{date}-action-{id}/REPORT.md`
   - 캡처 파일을 보고서에서 참조 (파일명 + 의미 명시)
   - 상세 형식은 `references/action-item-tracker.md` 참조
2. **최신 보고서 Action Items 상태 업데이트**: TODO → DONE/REVERTED/N/A
3. **INDEX.md 업데이트**: 히스토리에 추가
4. **커밋** (개선/유지 판정 시)
5. 다음 TODO 항목으로 → Step 1

## 중단/재개

- 언제든 중단 가능. 각 Item은 독립적으로 기록됨
- 재개 시: Step 0에서 TODO 항목 다시 수집하면 이어서 진행

## 체크리스트

- [ ] 최신 보고서에서 TODO Action Items 수집됨
- [ ] 우선순위 순서대로 진행
- [ ] **한 번에 하나만** 변경 (단일 변수 원칙)
- [ ] 매 테스트 전 DB/Redis 클린 상태
- [ ] 판정 기준에 따라 유지/롤백 결정
- [ ] **Step 5.5 캡처 게이트 통과** — Grafana PNG + Prometheus .txt 저장 확인
- [ ] **보고서 디렉토리에 캡처 파일 존재** — REPORT.md만 있으면 BLOCK
- [ ] **확인만 유형**: 코드 스니펫 + worst case 수치 계산 + Grafana/Prometheus 캡처
- [ ] 각 Item마다 보고서 기록 (캡처 파일 참조 포함)
- [ ] Action Items 상태 업데이트됨

## 관련 스킬

| 스킬 | 용도 | 언제 참조 |
|------|------|-----------|
| `perf-tuning-cycle` | 각 사이클 실행 (테스트→캡처→분석) | Step 4 |
| `static-perf-analysis` | 코드 변경 전 사전 분석 | Step 2 (확인만 유형) |
| `perf-test-reference` | k6 스크립트, thresholds | Step 4 |
