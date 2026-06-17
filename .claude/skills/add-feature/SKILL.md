---
name: add-feature
description: Use when adding a new feature or domain to an existing Spring Boot service, or when the user says "~~ 기능 추가해줘" or "~~ 도메인 추가해줘"
---

# Add Feature

기존 Spring Boot 서비스에 새 기능/도메인을 TDD로 추가한다.
build-api-service보다 가벼운 플로우.

**핵심 원칙:** ADR 기록 → TDD 구현 → 검증

## Process

### Step 1: 기능 분석

$ARGUMENTS에서 추가할 기능을 파악:

```
- 새 엔티티가 필요한가? 기존 엔티티 수정인가?
- 기존 도메인과의 관계는?
- 새 API 엔드포인트 목록
- 기존 코드에 영향 범위
```

사용자에게 정리 결과를 보여주고 **승인 후** 진행.

### Step 2: ADR 작성 (필요 시)

아키텍처 수준의 결정이 있으면 `docs/adr/`에 기록.
단순 CRUD 추가면 스킵.

**ADR이 필요한 경우:**
- 새로운 외부 연동
- 기존 패턴과 다른 접근
- 성능에 영향을 주는 변경

### Step 3: TDD 구현

**REQUIRED SUB-SKILL:** Use superpowers:test-driven-development

```
1. 테스트 작성 (RED)    → 실패하는 테스트 먼저
2. 최소 구현 (GREEN)    → 테스트 통과하는 최소 코드
3. 리팩토링 (REFACTOR)  → 코드 정리
4. ./gradlew test       → 전체 통과 확인
```

**새 도메인이면:**
Entity → Repository → DTO → Service → Controller 순서

**기존 도메인 수정이면:**
테스트 추가 → 코드 수정 → 기존 테스트도 통과 확인

### Step 4: 검증

**REQUIRED SUB-SKILL:** Use superpowers:verification-before-completion

```bash
./gradlew test    # 새 테스트 + 기존 테스트 모두 통과
```

## Common Mistakes

| 실수 | 해결 |
|------|------|
| 기존 테스트 깨뜨림 | 수정 전 전체 테스트 먼저 실행 |
| 기존 패턴과 다른 스타일 | 프로젝트 기존 코드 패턴 따름 |
| 테스트 없이 기능 추가 | TDD 필수 |
