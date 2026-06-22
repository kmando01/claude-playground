---
name: pr-description
description: >
  PR 설명 작성 가이드. "왜 바꿨는가"에 집중하고 diff 반복을 금지한다.
  Use when creating pull requests, writing PR descriptions, or when user says
  "PR 작성", "PR 설명", "PR 만들어줘", "/pr".
---

# PR Description Writing

## 핵심 철학

> PR 설명은 코드 변경 목록이 아니라 **스토리**다.
> diff에서 볼 수 없는 정보를 전달하는 것이 PR 설명의 역할이다.

## 금지 사항 (NEVER)

- NEVER: diff에서 보이는 내용 반복 ("Added X class", "Modified Y method", "Updated Z config")
- NEVER: 파일/클래스/메서드 목록 나열 (Affected Classes, Changed Files 섹션)
- NEVER: 커밋 메시지를 그대로 복붙한 "커밋 내역" 섹션
- NEVER: 기술적 세부사항만 나열하고 의도/맥락 누락
- NEVER: AI가 diff를 요약한 듯한 기계적 톤
- NEVER: "가장 단순한", "완벽한" 등 자기 평가 표현 — 리뷰어가 판단할 몫

## 필수 구조

Breaking Change 유무에 따라 구조가 달라진다:

**Breaking Change 없는 경우:**
`Problem → Solution → Design Decisions → Tradeoffs → Verification → Impact`

**Breaking Change 있는 경우:**
`Problem (⚠️ 경고 한 줄) → Impact → Solution → Design Decisions → Tradeoffs → Verification`

> Breaking Change는 리뷰어가 가장 먼저 봐야 할 정보다. Impact를 앞으로 당긴다.

---

### Problem (왜 이 변경이 필요한가)

- 구체적 시나리오 제시 — "무엇이 불편했는가", "무엇이 불가능했는가"
- 수치는 **추정과 실측을 명확히 구분**: "P99 3초 예상 (규모 추정 기반, 실측 아님)" vs "E2-2b 실험에서 434MB 확인"
- Breaking Change 있으면 Problem 상단에 `⚠️ 이 PR은 Breaking Change를 포함합니다` 한 줄

### Impact (이 변경의 영향)

- Breaking Changes — `⚠️` 명시, 변경 전/후 스키마
- 새로 가능해진 것, 성능/호환성 영향
- 스키마 비호환 시: 학습 프로젝트라도 "프로덕션이라면 어떻게" 한 줄 추가
  - 예: "프로덕션이라면 optional 필드 + 버전 헤더로 backward compatible 처리 필요"

### Solution (어떻게 해결했는가 — 접근법 수준)

- "X 클래스를 추가했다" (X) → "X 패턴을 도입해서 Y를 달성했다" (O)
- 코드가 아닌 아이디어 수준의 설명

### Design Decisions (왜 이 접근법을 선택했는가)

- diff에서 절대 알 수 없는 정보 = 설계 의도
- "왜 A 대신 B를 선택했는가", 대안을 기각한 이유 포함

### Tradeoffs (무엇을 포기했는가)

Design Decisions에 "왜 이걸 골랐는지"가 있다면, Tradeoffs에는 **"무엇을 포기했는지"**가 있어야 한다.

- 기능 제약 (예: 커서 페이징 → N번째 페이지 직접 이동 불가)
- 정합성 희생 (예: 캐시 TTL 1분 → 새 데이터 최대 1분 미반영)
- 수용 가능한 이유도 함께 명시

### Verification (어떻게 검증했는가)

- 어떤 테스트가 있는지 명시
- **미검증 부분도 솔직하게** — "X의 통합 테스트 없음, 이 PR에서 가장 검증이 부족한 부분"
- 수동 검증 스크립트가 있으면 이름과 용도 기재

---

## 자가 검증 체크리스트

| 체크 | 질문 | 통과 기준 |
|------|------|----------|
| diff 중복 | "이 내용이 코드 diff에서 보이는가?" | 보인다면 삭제하거나 "왜"를 추가 |
| WHY | "왜 이렇게 했는지 설명했는가?" | 설계 결정의 근거가 명시됨 |
| 추정/실측 | "수치가 추정인지 실측인지 구분했는가?" | 혼동 여지 없이 명시 |
| Breaking Change | "Impact가 적절한 위치에 있는가?" | Breaking Change 있으면 앞으로 |
| Tradeoffs | "포기한 것을 명시했는가?" | 기능 제약, 정합성 희생 포함 |
| Verification | "미검증 부분을 솔직하게 밝혔는가?" | 없으면 없다고 명시 |
| 미래 독자 | "6개월 후 이 PR만 보고 맥락을 이해할 수 있는가?" | 배경 지식 없이도 이해 가능 |

## 적용 순서

1. `git log base..HEAD`와 `git diff base...HEAD --stat`으로 변경 범위 파악
2. Breaking Change 유무 확인 → 구조 선택
3. **Problem** 작성 (수치는 추정/실측 구분)
4. Breaking Change 있으면 **Impact**를 Problem 바로 다음에 배치
5. **Solution** → **Design Decisions** → **Tradeoffs** → **Verification** 순으로 작성
6. 자가 검증 체크리스트 통과 확인
7. 자기 평가 표현("가장", "완벽한") 남아있으면 삭제
