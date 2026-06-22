# 문서 타입별 템플릿

## 1. 설계 고민 포인트 (design-why 형식)

**위치**: `docs/design-considerations/{topic}.md`
**인덱스**: `docs/design-considerations/README.md`의 D-N 테이블

```markdown
## D-{N}. {질문형 제목 — "왜 X인가?" 또는 "X하면 Y 아닌가?"}

{답변 — 명확한 근거와 함께}

{필요 시 코드/설정/비교표}

### 기각된 대안
| 대안 | 기각 사유 |
|------|-----------|
| ...  | ...       |

---
**관련**: ADR-{N} | `src/...` | D-{M}
```

**README.md 인덱스 형식**:
```markdown
| ID  | 주제 | 파일 | 한줄 요약 |
|-----|------|------|-----------|
| D-1 | ... | ... | ... |
```

---

## 2. 결정 기록

**위치**: `docs/decisions/YYYY-MM-DD-{slug}.md`
**인덱스**: `docs/decisions/README.md`

```markdown
---
date: YYYY-MM-DD
topic: {한 줄 주제}
status: accepted
---

## 결정

{한 문장 요약}

## 배경

{왜 이 결정이 필요했는가. 어떤 문제나 압박이 있었는가}

## 선택한 방향

{무엇을 선택했는가 + 선택 근거 (숫자/측정치 포함)}

## 기각된 대안

| 대안 | 기각 사유 |
|------|-----------|
| ...  | ...       |

## 예상 결과

{이 결정으로 기대하는 변화. 나중에 검증 가능해야 함}

## 관련

- ADR, 코드 경로, 커밋 링크
```

---

## 3. 솔루션 (compound 형식)

**위치**: `docs/solutions/YYYY-MM-DD-{slug}.md`
**인덱스**: `docs/solutions/README.md`
**참고**: `/design` Step 0에서 `tags`/`trigger`로 자동 매칭됨

```markdown
---
title: {제목}
date: YYYY-MM-DD
tags: [kafka, resilience, hikari, ...]
trigger: [키워드1, 키워드2]
---

## 문제

{어떤 증상이 있었는가. 에러 메시지, 측정치 포함}

## 원인

{근본 원인. "왜 발생했는가"}

## 해결

{어떻게 해결했는가. 핵심 변경 코드/설정 포함}

## 교훈

{다음에 이 상황을 다시 만나면 바로 할 행동}

## 관련

- ADR, decisions/, 커밋 링크, 코드 경로
```

---

## 4. 일반 문서

**위치**: `docs/{category}/{name}.md`
**카테고리 예시**: `runbook/`, `onboarding/`, `api/`, `infra/`

```markdown
# {제목}

> {한 줄 요약}

## 개요

{무엇에 관한 문서인가}

## 내용

{본문}

## 관련 자료

- 링크
```

---

## 5. ADR

→ `adr-template` 스킬 참조 (docs/adr/ 위치, 번호 자동 부여)
