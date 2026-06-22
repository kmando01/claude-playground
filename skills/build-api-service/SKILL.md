---
name: build-api-service
description: Use when building a new Spring Boot API service from scratch, or when the user says something like "~~ 서비스 만들어줘"
---

# Build API Service

Spring Boot REST API 서비스를 아이디어에서 완성까지 구축하는 오케스트레이터.

**핵심 원칙:** 기획 → 설계(ADR) → 계획 → 인프라 → TDD 구현 → 검증

각 단계의 세부 사항은 전문 스킬에 위임한다.

## Process

### Step 1: 기획

**REQUIRED SUB-SKILL:** Use superpowers:brainstorming

$ARGUMENTS에서 서비스 아이디어를 파악하고 사용자와 토론:
- 해결하는 문제, 대상 사용자, MVP 범위
- 핵심 엔티티 + 관계 + API 엔드포인트
- 인증/인가, 외부 연동 필요 여부

**합의 후** 다음 단계로.

### Step 2: 설계 - ADR

주요 아키텍처 결정을 `docs/adr/`에 기록.

```markdown
# ADR-001: {결정 제목}

## Status
Accepted

## Context
어떤 상황에서 이 결정이 필요했는가

## Decision
무엇을 결정했는가

## Consequences
이 결정으로 인한 장단점
```

번호 순차 증가. 변경 시 기존 ADR은 `Superseded by ADR-XXX`.

### Step 3: 구현 계획

**REQUIRED SUB-SKILL:** Use superpowers:writing-plans

- 도메인별 구현 순서 (의존성 기준)
- features.json 생성 (하네스 패턴)

### Step 4: 로컬 인프라

프로젝트 초기화 + Docker 환경 구성.
**세부 사항은 setup-infra 스킬 참조.**

### Step 5: TDD 구현

**REQUIRED SUB-SKILL:** Use superpowers:test-driven-development
**REQUIRED SUB-SKILL:** Use superpowers:executing-plans

각 도메인을 TDD로 구현. RED → GREEN → REFACTOR.
**테스트 규칙은 test-conventions 스킬 참조.**

### Step 6: 검증 & 완료

**REQUIRED SUB-SKILL:** Use superpowers:verification-before-completion
**REQUIRED SUB-SKILL:** Use superpowers:finishing-a-development-branch

#### 외부 실행 가능성 체크리스트 (push/제출 전 필수)

`git status --short`로 untracked 파일 확인 후 아래를 점검한다.

```
□ gradlew / gradlew.bat 커밋됐는가?
  → 없으면 README의 ./gradlew 명령이 fresh clone에서 즉시 실패
□ docker-compose.yml의 모든 volumes 경로가 커밋됐는가?
  → grep "volumes:" docker-compose.yml 으로 마운트 대상 추출 후 git ls-files로 확인
□ README에 언급한 파일/디렉토리가 실제 repo에 존재하는가?
  → docs/ 링크, config 파일, 스크립트 등
□ fresh clone 관점으로 README 명령을 위에서부터 한 줄씩 따라갔을 때 막히는 곳이 없는가?
```

위반 시: `git add <누락 파일>` → `git commit --amend --no-edit` 또는 별도 커밋.

## Quick Reference

```
Entity:     data class 금지, var 허용 (JPA), fromRequest/toResponse
DTO:        data class 필수, val only, @field: validation
Repository: JpaRepository<Entity, Long> 상속만
Service:    Constructor injection, orElseThrow
Controller: @Valid @RequestBody, ResponseEntity 래핑
ADR:        docs/adr/ADR-NNN-제목.md
```
