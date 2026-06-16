---
name: runbook
description: 프로젝트 실행 방법 섹션을 fresh-clone 관점으로 작성하고, 문서에 쓴 명령어·파일·경로가 실제 repo와 일치하는지 검증한다. 문서와 코드가 따로 놀면 외부에서 실행 불가능한 구조가 된다. 과제 제출·오픈소스 공개·팀 공유 전에 사용. 트리거: "실행 방법 만들어줘", "README 실행 섹션", "제출 전 확인", "fresh clone 검증", "문서 코드 일치 확인", "runbook", "/runbook"
---

# Runbook

문서에 쓰인 실행 방법과 실제 repo가 일치하는지 검증하고, 필요하면 작성까지 한다.

**핵심 원칙:** README는 fresh clone한 사람 기준으로 검증한다. 로컬에서 되는 것과 repo에서 되는 것은 다르다.

## Step 1: Repo 스캔

```bash
git status --short          # untracked 파일 목록
git ls-files | head -50     # 실제 커밋된 파일 확인
```

untracked 파일 중 아래에 해당하면 **즉시 Step 3으로** 넘어가 커밋한다:
- `docs/` 하위 파일 — README가 링크하든 안 하든 **무조건 커밋 대상**
- README나 docker-compose.yml이 참조하는 경로

## Step 2: 체크리스트 검증

**상세 체크리스트: `references/checklist.md` 참조**

5개 영역을 순서대로 점검:

| 영역 | 핵심 확인 |
|------|-----------|
| A. 필수 파일 | `gradlew`, `gradle/wrapper/`, `docker-compose.yml` 커밋 여부 |
| B. Volume 마운트 | docker-compose volumes 대상 경로가 `git ls-files`에 존재 |
| C. README 명령어 | `./스크립트`, 포트, curl 예시가 실제와 일치 |
| D. 환경변수 | 기본값 없는 `${VAR}` 는 README에 설정법 안내 |
| E. Fresh Clone | `/tmp`에 실제 clone → 기동 → **curl 응답 확인** |

> **존재 확인 ≠ 동작 확인.** A~D는 정적 점검이다. E를 생략하면 runbook이 아니다.

불일치 발견 시 → **질문 없이 즉시 Step 3 실행**

## Step 3: 불일치 수정

### 미커밋 파일 추가
```bash
git add <누락된 파일/디렉토리>
GIT_COMMITTER_DATE="<마지막커밋시각>" \
  git commit --amend --no-edit --date="<마지막커밋시각>"
git push --force-with-lease
```

마지막 커밋 시각 확인:
```bash
git log -1 --pretty=format:"%ad" --date=format:"%Y-%m-%dT%H:%M:%S+09:00"
```

### README 수정
- 존재하지 않는 파일을 참조하면 경로 수정 또는 파일 생성
- 포트 번호 불일치 → `application.yml` 값으로 통일
- curl 예시 엔드포인트 불일치 → Controller 실제 경로로 수정

## Step 4: 실행 방법 섹션 작성 (README에 없거나 부실할 때)

fresh clone 관점의 5단계 구조:

```markdown
## 실행 방법

### 사전 요구사항
- JDK XX (버전 명시)
- Docker / Docker Compose

### 1) 인프라 기동
\`\`\`bash
docker compose up -d
\`\`\`

### 2) 앱 실행
\`\`\`bash
./gradlew :<module>:bootRun
\`\`\`

### 3) 동작 확인
\`\`\`bash
curl http://localhost:<port>/...
\`\`\`
```

**금지 패턴:**
- 로컬에만 있는 파일 참조 (`./gradlew`인데 gradlew 미커밋)
- 환경변수 설정법 누락
- 포트를 `application.yml`과 다르게 기재

## 완료 체크리스트

```
□ git status --short 에 실행 관련 파일이 untracked 없음
□ /tmp clone → docker compose up -d 에러 없음
□ /tmp clone → ./gradlew bootRun → "Started" 로그 확인
□ README curl 예시 → 실제 응답(200) 확인
□ 모든 문서 링크가 git ls-files에 존재
□ 환경변수 설정법 README에 안내됨
```
