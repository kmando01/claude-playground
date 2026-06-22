---
name: agents-reference
description: Agent 오케스트레이션 상세 레퍼런스. 사용 가능 에이전트 테이블, 자동 트리거 조건, /code-review 연동 에이전트, refactor-cleaner 실행 규칙, 병렬 실행 예제 포함. 에이전트 사용 시 참조.
---

# Agent 오케스트레이션 레퍼런스

## 사용 가능 Agents

| Agent | 용도 | 사용 시점 |
|-------|------|----------|
| planner | 구현 계획 | 복잡한 기능, 리팩토링 |
| architect | 시스템 설계 | 아키텍처 결정 |
| tdd-guide | TDD 개발 | 새 기능, 버그 수정 |
| code-reviewer | 코드 품질 분석 | `/code-review` Phase 3에서 병렬 실행 |
| security-reviewer | 보안 분석 | `/code-review` Phase 3에서 병렬 실행 |
| build-error-resolver | 빌드 오류 | 빌드 실패 시 |
| refactor-cleaner | 코드 정리 (Opus) | `/code-review` 완료 + **사용자 승인 후** |
| design-reviewer | 설계 검증 + ADR 생성 | 기능 설계 후, 아키텍처 변경 시 |
| doc-updater | 문서화 | 문서 업데이트 시 |

## 자동 트리거 Agent

| Agent | 트리거 | 모델 |
|-------|--------|------|
| tdd-guide | 새 기능, 버그 수정 시 | 기본 |
| planner | 복잡한 기능 요청 시 | 기본 |
| architect | 아키텍처 결정 시 | 기본 |

## /code-review 연동 Agent

`/code-review` 워크플로우 내에서만 실행된다. 단독 자동 트리거 없음.

| Agent | 실행 시점 | 자동 여부 |
|-------|----------|----------|
| code-reviewer | Phase 3 (변경사항 분석) | `/code-review` 내 자동 |
| security-reviewer | Phase 3 (변경사항 분석) | `/code-review` 내 자동 |
| refactor-cleaner | Phase 7 완료 후 | **사용자 승인 필수** |

## refactor-cleaner 실행 규칙

- `/code-review` Phase 7(승인된 이슈 수정) 완료 후 **사용자 확인을 받은 뒤** 실행
- **자동 실행 금지** — 사용자가 명시적으로 요청해야 실행
- 데드 코드 제거, 중복 통합, 구조 개선 수행
- 리팩토링 후 테스트 통과 확인 필수
- 리팩토링 결과는 사용자에게 변경 사항 요약 보고

## 병렬 실행 예제

```
# GOOD: 병렬 실행
1. Agent 1: 보안 분석
2. Agent 2: 코드 품질 검사

# BAD: 불필요한 순차 실행
```
