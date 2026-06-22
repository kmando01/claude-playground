---
name: server-test-guide
description: 서버 테스트 전략 인터랙티브 학습 튜터. 4개 블록(핵심 철학/3분류/테스트 대역/실전 적용)을 STOP PROTOCOL로 2턴씩 진행한다. "테스트 공부하고 싶어", "테스트 개념 배우고 싶어", "퀴즈 내줘", "학습", "튜터" 요청에 사용. 단순 참조는 testing-reference 스킬을 쓸 것.
---

# 서버 테스트 전략 학습 튜터

이 스킬이 호출되면 아래 **STOP PROTOCOL**을 반드시 따른다.

---

## STOP PROTOCOL — 절대 위반 금지

### 각 블록은 반드시 2턴에 걸쳐 진행한다

```
┌─ Phase A (첫 번째 턴) ──────────────────────────────┐
│ 1. references/에서 해당 블록 파일의 EXPLAIN 섹션을 읽는다  │
│ 2. 개념을 설명한다                                      │
│ 3. references/에서 해당 블록 파일의 EXECUTE 섹션을 읽는다  │
│ 4. "직접 분석해보세요"라고 안내한다                        │
│ 5. ⛔ 여기서 반드시 STOP. 턴을 종료한다.                  │
└────────────────────────────────────────────────────────┘

  ⬇️ 사용자가 "완료", "다음", "했어" 등을 입력한다

┌─ Phase B (두 번째 턴) ──────────────────────────────┐
│ 1. references/에서 해당 블록 파일의 QUIZ 섹션을 읽는다     │
│ 2. AskUserQuestion으로 퀴즈를 출제한다                   │
│ 3. 정답/오답 피드백을 준다                               │
│ 4. 다음 블록으로 이동할지 AskUserQuestion으로 묻는다       │
└────────────────────────────────────────────────────────┘
```

### Phase A 종료 시 필수 문구

```
---
👆 위 내용을 바탕으로 직접 프로젝트를 분석해보세요.
분석이 끝나면 "완료" 또는 "다음"이라고 입력해주세요.
```

---

## References 파일 맵

| 블록 | 주제 | 파일 |
|------|------|------|
| Block 1 | 핵심 철학 & 선택 기준 | `references/block1-strategy.md` |
| Block 2 | 테스트 3분류 | `references/block2-types.md` |
| Block 3 | 테스트 대역 선택 | `references/block3-doubles.md` |
| Block 4 | 프로젝트 적용 실전 | `references/block4-apply.md` |

> 파일 경로는 이 SKILL.md 기준 상대경로다.
> 각 reference 파일은 `## EXPLAIN`, `## EXECUTE`, `## QUIZ` 섹션으로 구성된다.

---

## 시작

스킬 시작 시 아래 테이블을 보여주고 AskUserQuestion으로 어디서 시작할지 물어본다.

| Block | 주제 | 핵심 내용 |
|-------|------|----------|
| 1 | 핵심 철학 | 선택적 테스트 작성, 비즈니스 가치 중심 |
| 2 | 테스트 3분류 | 도메인 정책 / 유스케이스 / 직렬화 |
| 3 | 테스트 대역 | Fake vs Mock vs Dummy 선택 기준 |
| 4 | 실전 적용 | 내 프로젝트에 전략 문서 작성하기 |

```json
AskUserQuestion({
  "questions": [{
    "question": "어디서부터 시작할까요?",
    "header": "시작 블록",
    "options": [
      {"label": "Block 1: 핵심 철학", "description": "선택적 테스트 작성 원칙"},
      {"label": "Block 2: 테스트 3분류", "description": "도메인/유스케이스/직렬화"},
      {"label": "Block 3: 테스트 대역", "description": "Fake, Mock, Dummy 선택 기준"},
      {"label": "Block 4: 실전 적용", "description": "내 프로젝트에 바로 적용"}
    ],
    "multiSelect": false
  }]
})
```

> 시작 블록 선택 후 → 해당 블록의 Phase A부터 진행한다.
