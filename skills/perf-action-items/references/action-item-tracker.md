# Action Item 보고서 템플릿

## 개별 Item 보고서 형식

`docs/perf-reports/{date}-action-{id}/REPORT.md` 작성 시 사용.

```markdown
# Action Item {ID}: {제목}

- **일시**: YYYY-MM-DD
- **브랜치**: `{branch}`
- **베이스라인**: {이전 보고서 링크}
- **유형**: 코드 변경 / 설정 변경 / 확인만 / 테스트만

## 변경 내용

| 항목 | Before | After |
|------|--------|-------|
| {설정/코드} | {이전 값} | {변경 값} |

### 변경 파일
- `path/to/file1.kt` — {변경 설명}
- `path/to/file2.yml` — {변경 설명}

## 성능 테스트 결과

### k6 Load Test

| 지표 | 베이스라인 | 이번 결과 | 변화 |
|------|-----------|----------|------|
| 총 TPS | | | |
| p90 | | | |
| p95 | | | |
| p99 | | | |
| avg | | | |
| 에러율 | | | |

### 내부 지표 (Prometheus)

| 지표 | 베이스라인 | 이번 결과 | 변화 |
|------|-----------|----------|------|
| HikariCP Pending max | | | |
| HikariCP Active max | | | |
| GC pause rate | | | |
| Heap used max | | | |

## 판정

- **결과**: 개선 / 무효 / 악화
- **근거**: {수치 기반 판단 이유}
- **액션**: 유지 + 커밋 / 롤백 / 사용자 판단

## 캡처 파일

**CRITICAL: 모든 주장은 캡처 파일로 증거를 남긴다. 텍스트 수치만 보고서에 쓰지 않는다.**

### Grafana PNG (성능 테스트 시)
- `hikaricp-api.png`
- `http-response-time-api.png`
- `http-request-count-api.png`
- `gc-api.png`

### Before/After 비교 시 (코드 변경 항목)
- `before/` — 변경 전 캡처 (Grafana PNG 또는 터미널 출력 .txt)
- `after/` — 변경 후 캡처

### OS/인프라 레벨 검증 시
- `{before|after}-netstat.txt` — netstat 소켓 상태 (TIME_WAIT 등)
- `{before|after}-sql-log.txt` — Hibernate SQL/통계 출력
- `{before|after}-metrics.txt` — Prometheus 쿼리 결과

### 캡처 원칙
1. **Before 없이 After만 캡처하지 않는다** — 비교 불가
2. **Grafana가 아닌 지표도 캡처한다** — netstat, SQL 로그, Redis 등 OS/인프라 레벨
3. **캡처 파일을 REPORT.md에 참조한다** — 파일명과 의미 명시
```

## 확인만 유형 보고서 형식

코드 리뷰로 결론 내는 항목 (성능 테스트 불필요).

```markdown
# Action Item {ID}: {제목}

- **일시**: YYYY-MM-DD
- **유형**: 확인만

## 분석 결과

{코드 분석 내용}

### 호출 흐름
{관련 코드 경로, 메서드, 트랜잭션 범위 등}

## 캡처 파일
- `sql-log.txt` — Hibernate SQL/통계 출력 (해당 시)
- `metrics.txt` — Prometheus 쿼리 결과 (해당 시)

## 결론

- **상태**: DONE (문제 없음) / DONE (문제 발견 → 별도 Action Item 생성)
- **근거**: {분석 근거 — 반드시 캡처 파일 참조}
```

## Action Items 상태 값

| 상태 | 의미 |
|------|------|
| TODO | 미착수 |
| IN_PROGRESS | 진행 중 (변경 적용됨, 테스트 전) |
| DONE | 완료 (개선 확인 또는 확인만 완료) |
| REVERTED | 악화/무효로 롤백됨 |
| N/A | 해당 없음 (환경 변경 등으로 무의미해짐) |
| DEFERRED | 현재 우선순위 밖, 다음 라운드에서 검토 |

## INDEX.md 업데이트 형식

```markdown
### N. [action-{id}](./YYYY-MM-DD-action-{id}/REPORT.md) -- {제목}

**변경**: {Before → After 한 줄 요약}
**결과**: {판정} -- {핵심 수치 변화}
**누적 효과**: p95 {baseline}ms → {current}ms ({ratio}x)
```

## 누적 추적 테이블

전체 진행 상황을 한눈에 보기 위한 테이블. INDEX.md 상단에 유지.

```markdown
## Action Items 진행 현황

| ID | 항목 | 상태 | 판정 | p95 변화 | 보고서 |
|----|------|------|------|----------|--------|
| A3 | HTTP 클라이언트 풀 | DONE | 개선 | 56→45ms | [링크] |
| A6 | @Transactional 확인 | DONE | N/A | - | [링크] |
| B1 | Stress 5K TPS | TODO | - | - | - |
```
