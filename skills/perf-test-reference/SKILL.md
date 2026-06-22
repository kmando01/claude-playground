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
- MUST: 매 라운드 시작 전 — reset-test-data.sh (TRUNCATE + FLUSH) + JVM warm-up
- MUST: k6 스크립트 동일, 인프라 상태 동일 (컨테이너 재시작)
- MUST: 외부 의존성 동일 (mock 서버 설정값)

### 4. ramping-arrival-rate executor
- MUST: `ramping-arrival-rate` 사용 — "초당 N 요청" 정밀 제어
- NEVER: `ramping-vus` + `sleep()`으로 TPS 측정 (VU 처리시간에 따라 실제 TPS 변동)
- MUST: `dropped_iterations` threshold 설정 — VU 부족 감지
- 공식 문서: https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ramping-arrival-rate/

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
1. 환경 준비: docker-compose up → 헬스체크 → reset-test-data.sh → JVM warm-up
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
- [ ] reset-test-data.sh + JVM warm-up
- [ ] k6 스크립트 이전 라운드와 동일 확인

### 라운드 종료 후
- [ ] k6 summary JSON 저장 + Grafana 캡처(테스트 시간 범위)
- [ ] 에러 HTTP status별 분류
- [ ] 결과 보고서 작성 + 다음 변경 계획

### 최종 보고 전
- [ ] 변수 분리 확인 + "로컬 Docker Compose" 단서
- [ ] Consumer lag 변화 기록

## 상세 가이드

| 문서 | 내용 |
|------|------|
| `references/k6-templates.md` | k6 스크립트 템플릿 (load/stress), 디렉토리 구조 |
| `references/monitoring.md` | 필수 수집 지표, Grafana 대시보드 구성 |
| `references/report-template.md` | 라운드별 결과 보고서 템플릿 |
| `.claude/project-context.md` | **프로젝트 특화**: TPS 목표/SLO/체크리스트 (OSIV, CDC, poll 공식 등) |
