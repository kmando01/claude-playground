---
name: kafka-lab
description: >
  Kafka Labs 실험 진행 도우미. 실험 전 사전 검증, 로그 실시간 해석, REPORT.md 작성까지 전 과정을 지원한다.
  Use when: 사용자가 Kafka lab 실험을 진행하거나, 로그를 보여주며 해석을 요청하거나,
  "report 채워줘", "이 로그 해석해줘", "lab 실험", "결과 정리", "commands.sh 확인해줘"라고 말할 때.
  Also triggers on: REPORT.md 또는 commands.sh 파일이 열려있을 때 실험 관련 질문.
---

# Kafka Lab 실험 진행 스킬

## Step 1: 현재 Lab 상태 파악

실험 시작 전 확인:
- 어떤 Lab인지 (lab2-1 ~ lab3-4)
- commands.sh, REPORT.md 읽기 → 순서와 빈 섹션 파악
- 필요한 Spring Profile 존재 여부 확인

## Step 2: 실험 전 사전 검증

→ `references/prereq-checklist.md` 체크리스트 실행

문제 발견 시 → 즉시 수정 제안, 사용자 확인 후 진행

## Step 3: 실험 실행 안내

사용자가 직접 명령어를 실행. Claude는:
- 각 명령어가 **무엇을 확인하는지** 먼저 설명
- 예상 결과를 미리 제시
- 실험 순서상 주의사항 안내

## Step 4: 로그 해석

사용자가 로그를 붙여넣으면:
→ `references/log-patterns.md` 참조하여 핵심 필드 추출

1. errorCode, partition, offset, ISR, retrying, elapsed 확인
2. 예상 결과와 비교
   - 일치 → 간단히 확인
   - 불일치 → Step 5로

## Step 5: 예상 밖 동작 분석

→ `references/investigation-guide.md` 참조

1. 가설 제시 (가능성 높은 순서)
2. 공식 문서/소스 코드 근거 확인
3. 틀린 분석은 즉시 수정 + 메모리 업데이트

## Step 6: REPORT.md / 실증 노트 작성

원칙:
- **실제 실행한 로그만** 기재 (미실행 섹션은 빈칸 유지)
- 로그는 생략(`...`) 없이 전체 기재
- 인라인 질문은 답변으로 교체
- 예상과 다른 결과 → 차이와 원인까지 기록

작성 후 체크:
- [ ] 로그 기반 관찰 vs 추정 구분
- [ ] 공식 문서 링크 첨부 (중요 설정값)

## Step 7: git commit + push (보고서 작성 후 항상 실행)

보고서/실증 노트 작성이 완료되면 **사용자가 요청하지 않아도** 바로 commit + push까지 진행한다.

```bash
# 반드시 절대 경로로 cd 먼저 — git 명령은 working directory 기준으로 실행됨
cd /절대/경로/프로젝트 && git add . && git commit -m "docs: ..." && git push
```

주의:
- `git add <file>` 단독 실행 금지 → 현재 shell의 cwd가 프로젝트 디렉토리가 아니면 `fatal: not a git repository` 발생
- 항상 `cd 절대경로 && git ...` 패턴 사용
- 레포가 없으면 `gh repo create`로 먼저 생성 후 진행

## 관련 스킬

| 상황 | 스킬 |
|------|------|
| 커밋/푸시 | `commit` |

## 완료 체크리스트

- [ ] commands.sh 사전 검증 완료
- [ ] 실험 전 예상 결과 안내
- [ ] 로그 기반으로 REPORT.md 채움
- [ ] 예상 밖 동작 → 공식 문서 근거로 설명
- [ ] 미실행 섹션 명확히 표시
- [ ] git commit + push 완료
