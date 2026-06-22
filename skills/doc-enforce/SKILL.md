---
name: doc-enforce
description: 중요한 결정·설계 고민·지식을 .md 파일로 강제 기록한다. 대화에서 논의되고 소멸되는 지식을 방지한다. Use when user says "/doc", "문서화", "문서로 남겨줘", "기록해줘", "정리해줘", "wiki에", "wiki 내용", "문서로 만들어줘", or when significant design decisions, lessons learned, architecture choices, or "왜 이렇게 했는지" arise in discussion. Also auto-triggers: after /design completes, when important tradeoffs are discussed, when user mentions writing to wiki.
---

# doc-enforce — 지식 소멸 방지, 강제 문서화

> **핵심 원칙**: 대화에서 중요한 것이 결정되면, 그 자리에서 .md로 기록한다.
> Wiki, 노션, 채팅에만 남은 지식은 **존재하지 않는 것**이다.

---

## Phase 1: 문서 타입 선택

주제/내용을 분석해 자동으로 타입을 결정한다. 명확하지 않으면 1개 질문으로 확인.

| 타입 | 판단 기준 | 저장 위치 |
|------|-----------|-----------|
| **설계 고민** | "왜 X인가?", "X 대신 Y 아닌가?" 형태의 의문·결정 | `docs/design-considerations/` |
| **결정 기록** | 기술 선택, 전략 변경, 트레이드오프 선택 | `docs/decisions/` |
| **솔루션** | 문제 해결 과정, 삽질 교훈, 패턴 발견 | `docs/solutions/` |
| **ADR** | 아키텍처 수준 결정 (되돌리기 어려운 큰 결정) | `docs/adr/` |
| **일반 문서** | 가이드, 운영 절차, 온보딩, 개념 정리 | `docs/` |

**우선순위**: 설계 고민 > 결정 기록 > 솔루션 > 일반 문서
(하나의 내용이 여러 타입에 걸치면 가장 구체적인 타입 선택)

---

## Phase 2: 중복 확인

```
Grep로 기존 파일에서 키워드 매칭
→ 80% 이상 겹치면: 기존 파일에 항목 추가 제안
→ 겹치지 않으면: 새 파일 생성
```

---

## Phase 3: 파일 생성

### 3-1. 파일명 규칙

| 타입 | 형식 | 예시 |
|------|------|------|
| 설계 고민 | `{topic}.md` | `kafka-consumer.md` |
| 결정 기록 / 솔루션 | `YYYY-MM-DD-{slug}.md` | `2026-03-14-retry-strategy.md` |
| 일반 문서 | `{kebab-case}.md` | `deployment-guide.md` |

### 3-2. 작성 형식

**타입별 상세 템플릿** → `references/doc-types.md` 참조

**모든 타입 공통 원칙**:
1. **질문형/동사형 제목**: "왜 X인가?", "X 전략 결정", "Y 문제 해결"
2. **근거 필수**: 숫자, 코드, 비교표 등 객관적 근거
3. **대안 기각 사유**: 선택하지 않은 대안이 있으면 왜 기각했는지 명시
4. **링크**: 관련 ADR, solutions/, 코드 경로 연결

---

## Phase 4: 인덱스 업데이트

해당 디렉토리의 `README.md`에 새 항목을 테이블에 추가한다.
`README.md`가 없으면 자동 생성.

```markdown
| ID/날짜 | 주제 | 파일 | 한줄 요약 |
|---------|------|------|-----------|
| D-7     | CB threshold 45% 근거 | resilience.md | steady-state 35% + 10%p 여유 |
```

---

## Phase 5: 완료 알림

```
✅ 문서화 완료
   타입: 설계 고민
   파일: docs/design-considerations/resilience.md
   항목: D-7 "CB threshold를 45%로 설정한 이유"
   → /design 시 자동 참조됩니다.
```

---

## 자동 트리거 조건

| 상황 | 행동 |
|------|------|
| `/design` Step 6(독립 리뷰) 통과 후 | 설계 고민 포인트 문서화 여부 확인 |
| `/plan` 완료 후 | 주요 결정사항 문서화 여부 확인 |
| 대화에서 중요한 트레이드오프가 논의될 때 | 즉시 `/doc`으로 기록 제안 |
| 사용자가 wiki/노션 언급 시 | ".md로도 저장하겠습니다" 제안 |

---

## Integration

| 스킬/커맨드 | 연동 방식 |
|-------------|-----------|
| `design-why` | 설계 고민 타입은 동일 워크플로우 (design-why 대체 가능) |
| `compound` | 솔루션 타입은 compound와 동일 위치 (`docs/solutions/`) |
| `/design` | Step 0에서 `docs/design-considerations/` 자동 참조 |
| `adr-template` | ADR 타입은 adr-template 스킬 참조 |
