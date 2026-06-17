---
name: commit
description: Git commit 워크플로우. 변경 사항을 분석하고 Conventional Commits 형식으로 커밋한다. Use when user says "커밋", "커밋해줘", "commit", "/commit", or asks to commit changes.
---

# Commit

변경 사항을 분석하고, Conventional Commits 한국어 메시지로 커밋한다.

## 규칙

- **title만** 작성한다. body 없음, Co-Authored-By 없음.
- 형식: `type: 한국어 설명`
- type: `feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `perf`, `style`, `ci`
- 설명은 **간결하게** (50자 이내 권장)
- HEREDOC으로 메시지 전달

## 워크플로우

```
1. git status      → 변경 파일 파악
2. git diff        → staged + unstaged 변경 내용 확인
3. git log -5      → 최근 커밋 스타일 참고
4. 사용자에게 스테이징 대상 확인 (모호한 경우)
5. git add <files> → 관련 파일만 명시적으로 스테이징
6. git diff --cached --stat → 스테이징 확인
7. git commit      → 커밋 생성
8. git status      → 결과 검증
```

## 커밋 메시지 예시

```
feat: alarm-consumer Kafka Consumer 구현
fix: Redis 연결 타임아웃 처리 누락 수정
refactor: domain 순수성 확보 및 모듈 설정 개선
chore: Gradle 의존성 버전 업데이트
test: NotificationProcessor 단위 테스트 추가
docs: API 명세 업데이트
```

## 커밋 형식

```bash
git commit -m "$(cat <<'EOF'
type: 한국어 설명
EOF
)"
```

## 주의사항

- `.env`, credentials 등 민감 파일은 커밋하지 않는다
- `git add -A`나 `git add .` 사용 금지 — 파일을 명시적으로 지정
- 변경 사항이 없으면 빈 커밋을 만들지 않는다
- 사용자가 제외를 요청한 파일은 반드시 제외