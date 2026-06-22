---
name: project-init
description: >
  코드베이스를 분석해 .claude/project-context.md를 생성한다.
  스킬들이 Step 0에서 이 파일을 읽어 프로젝트 특화 동작을 수행한다.
  Use when starting a new project, or when project-context.md is missing/outdated.
  Triggers on "프로젝트 초기화", "project-init", "컨텍스트 파일 만들어줘", "/project-init".
---

# 프로젝트 컨텍스트 초기화

새 프로젝트에서 스킬들이 프로젝트 특화 동작을 하도록 `.claude/project-context.md`를 생성한다.

## Step 1: 코드베이스 탐색

다음을 분석한다.

```bash
# 모듈 구조
ls -d */ | grep -E "(api|service|consumer|domain|infra|client|common|batch)"

# 포트 설정
grep -r "server.port" --include="*.yml" --include="*.yaml"

# 기술 스택
cat build.gradle.kts settings.gradle.kts 2>/dev/null | head -50
```

확인 항목:
- 모듈 목록과 각 모듈의 역할
- API 서버 포트
- Kafka 토픽 (docker-compose.yml 또는 KafkaConfig)
- Redis 키 패턴 (기존 코드에서 추출)
- 주요 도메인 엔티티

## Step 2: 성능 목표 확인

ADR 또는 기획 문서에서 목표를 찾는다.

```bash
find docs -name "*.md" | xargs grep -l "TPS\|DAU\|보관\|retention" 2>/dev/null | head -5
```

없으면 사용자에게 질문:
- "일 예상 건수 또는 목표 TPS가 있나요?"
- "SLO 기준이 있나요? (p95, 에러율)"

## Step 3: 모니터링 설정 확인

```bash
# Grafana 대시보드 UID
grep -r "dashboard" --include="*.json" --include="*.yml" .grafana/ provisioning/ 2>/dev/null | head -10

# Prometheus 애플리케이션명
grep -r "application.name\|spring.application.name" --include="*.yml" | head -5
```

Grafana UID를 찾을 수 없으면: "Grafana 대시보드 UID를 알고 있으신가요? (성능 테스트 캡처에 필요)"

## Step 4: project-context.md 생성

탐색 결과를 바탕으로 `.claude/project-context.md`를 생성한다.

**파일 구조 템플릿**:

```markdown
# Project Context

## Project
name: {project-name}
description: {brief description}
primary-language: {Kotlin/Java/...}
framework: Spring Boot

## Modules
{module}: {path} (port: {port})
...

## Domains
primary: {main-domain}
key-entities: {Entity1, Entity2}

## Redis Key Patterns
{purpose}: "{pattern}"

## Kafka Topics        ← Kafka 없으면 이 섹션 생략
{role}: {topic-name} ({N} partitions)
consumer-group: {group}
consumer-concurrency: {N}

## Performance Targets
write-tps-avg: {N}
write-tps-peak: {N}
read-tps-avg: {N}
read-tps-peak: {N}
local-write-tps: {N}   # 로컬 환경 기준
local-read-tps: {N}
slo-p95: {N}ms
slo-p99: {N}ms
slo-error-rate: {N}%
slo-consumer-lag: {N}  ← Kafka 있는 경우만

---

## [code-review]          ← 프로젝트 특화 코드 리뷰 체크리스트
    ### 프로젝트 특화 체크리스트
    | 카테고리 | 심각도 | 검사 항목 |
    |----------|--------|----------|
    | {핵심 패턴 준수} | CRITICAL | ... |

    ## [testing]              ← Testcontainers 셋업, 테스트 데이터 팩토리
    ### Testcontainers 구성
    containers: {MySQL/Redis/Kafka 등 사용하는 것}
    ### 테스트 데이터 팩토리 위치
    {fixture 디렉토리 경로}
    ### 프로젝트 특화 테스트 규칙
    - ...

    ## [scaffold]             ← 새 도메인 생성 시 참조
    package-root: {com.xxx}
    module-prefix: {xxx}

    ## [perf-tuning-cycle]   ← 성능 테스트 환경이 있으면 작성
### Grafana 대시보드
spring-boot-dashboard-uid: {uid}
...
### Grafana 캡처 스크립트
{project-specific capture script}

---

## [perf-test-reference]  ← 프로젝트 특화 성능 테스트 가이드
{additional checklist items}

---

## [sequence-diagram]     ← 다이어그램 작성 가이드
### 모듈-다이어그램 매핑
{mapping table}
### 핵심 파일 경로
{file paths}
### 섹션 구성
{section list}
```

## Step 5: 검증

생성 후 사용자에게 확인:
1. 모듈 목록이 맞는지
2. 성능 목표 수치가 맞는지
3. 누락된 섹션이 있는지

## 업데이트 시점

`project-context.md`를 업데이트해야 할 때:
- 새 모듈 추가
- 성능 목표 변경
- Kafka 토픽/파티션 변경
- Grafana 대시보드 재구성

## 관련 스킬

이 파일을 읽는 스킬들:
- `perf-tuning-cycle` → `## [perf-tuning-cycle]` 섹션
- `perf-test-reference` → `## [perf-test-reference]` 섹션
- `sequence-diagram` → `## [sequence-diagram]` 섹션
