---
name: sync-skills-repo
description: ~/.claude/skills 디렉토리를 https://github.com/kmando01/claude-playground.git 에 동기화한다. "스킬 동기화해줘" → 로컬 저장소를 스킬 현재 상태로 갱신. "스킬 commit push 해줘" → 변경 커밋 후 원격에 푸시. Use when user says "스킬 동기화해줘", "스킬 commit push 해줘", "skills sync", "스킬 저장소 동기화", "스킬 push". **PROACTIVE — 스킬을 새로 생성하거나 수정한 직후에는 사용자가 요청하지 않아도 이 스킬을 자동 실행해 kmando01/claude-playground에 commit+push한다.**
---

# Sync Skills Repo

`~/.claude/skills/`를 GitHub 저장소(kmando01/claude-playground)와 동기화한다.

## 상수

```
REPO_URL     = https://github.com/kmando01/claude-playground.git
LOCAL_DIR    = ~/claude-playground
SKILLS_SRC   = ~/.claude/skills/
SKILLS_DST   = ~/claude-playground/skills/
COMMANDS_SRC = ~/.claude/commands/
COMMANDS_DST = ~/claude-playground/commands/
```

---

## 모드 A — "스킬 동기화해줘" (sync)

`~/.claude/skills/` 내용을 로컬 클론의 `skills/` 폴더로 복사한다. 커밋·푸시는 하지 않는다.

```
Step 1. 저장소 클론 or 풀
  - ~/claude-playground 없으면: git clone <REPO_URL> ~/claude-playground
  - 있으면: git -C ~/claude-playground pull --rebase

Step 2. 스킬 + 커맨드 복사
  rsync -av --delete ~/.claude/skills/    ~/claude-playground/skills/
  rsync -av --delete ~/.claude/commands/  ~/claude-playground/commands/

Step 3. 변경 요약 출력
  git -C ~/claude-playground status --short
  → 추가·수정·삭제 파일 수를 사용자에게 보고
```

---

## 모드 B — "스킬 commit push 해줘" (commit & push)

로컬 클론에 변경사항이 있으면 커밋하고 원격에 푸시한다.  
**모드 A를 먼저 실행했다고 가정한다. 아직 안 했다면 모드 A부터 실행.**

```
Step 1. 상태 확인
  git -C ~/claude-playground status --short
  → 변경 없으면 "최신 상태입니다" 보고 후 종료

Step 2. 변경 스테이징
  git -C ~/claude-playground add -A

Step 3. 커밋 메시지 작성
  - 규칙: "chore: sync skills YYYY-MM-DD" (오늘 날짜)
  - 추가/수정/삭제 스킬 목록을 body에 bullet로 나열

Step 4. 커밋
  git -C ~/claude-playground commit -m "<message>"

Step 5. 푸시
  git -C ~/claude-playground push origin main
  → 성공 시 GitHub URL 출력
```

---

## 자동 트리거 조건 (PROACTIVE)

다음 상황에서 사용자 요청 없이 모드 A → 모드 B를 자동 실행한다:

- `~/.claude/skills/` 하위 파일을 **신규 생성**한 직후
- `~/.claude/skills/` 하위 파일을 **수정**한 직후

자동 실행 시 커밋 메시지 예시:
```
chore: update <skill-name> — <변경 내용 한 줄 요약>
```

## 주의사항

- `~/claude-playground`가 다른 브랜치에 있으면 `main`으로 체크아웃 후 진행
- 충돌 발생 시 사용자에게 알리고 중단 (자동 해결 금지)
- `~/.claude/commands/`도 항상 함께 동기화한다 (skills와 세트)
