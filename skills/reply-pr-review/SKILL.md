---
name: reply-pr-review
description: Use when replying to inline PR review comments on GitHub Enterprise — fetching unresolved threads, marking implemented items with commit hyperlinks, and explaining skipped items
---

# PR Review 답글 달기

GitHub Enterprise PR의 인라인 리뷰 코멘트 스레드에 답글을 다는 절차.

## 1. 코멘트 조회

```bash
gh api repos/{OWNER}/{REPO}/pulls/{PR_NUMBER}/comments \
  --hostname {GHE_HOSTNAME}
```

반환된 JSON에서 필요한 필드:
- `id` — 답글 대상 comment ID
- `body` — 코멘트 내용
- `user.login` — 작성자 (bot인지 사람인지 구분)
- `in_reply_to_id` — 이미 답글인 경우 원본 ID

파싱 예시:
```bash
gh api repos/OWNER/REPO/pulls/1/comments \
  --hostname github.example.com | python3 -c "
import json, sys
for c in json.load(sys.stdin):
    print(c['id'], c['user']['login'], c['body'][:80])
"
```

## 2. 답글 달기

```bash
gh api repos/{OWNER}/{REPO}/pulls/{PR_NUMBER}/comments/{COMMENT_ID}/replies \
  --hostname {GHE_HOSTNAME} \
  -X POST \
  -f body="답글 내용"
```

> ⚠️ `/pulls/comments/{id}/replies` (PR number 없는 경로)는 404. 반드시 `/pulls/{PR_NUMBER}/comments/{id}/replies` 사용.

## 3. 답글 포맷

**반영한 경우:**
```
반영 ([{SHORT_SHA}]({COMMIT_URL})) — 무엇을 어떻게 변경했는지 한 줄 설명.
```

예:
```
반영 ([a977f20](https://github.example.com/org/repo/commit/a977f20)) — `CompletableFuture.supplyAsync`에 virtual thread executor 주입.
```

**스킵한 경우:**
```
Skip — 이유를 구체적으로 한 줄 설명.
```

예:
```
Skip — `CommonResource` 엔티티에 `eventKey` 필드가 없어 스키마 변경 필요. 별도 작업으로 처리 예정.
```

## 4. 전체 흐름

```
1. gh api ...pulls/{N}/comments 로 전체 코멘트 조회
2. 각 코멘트 분류:
   - 이미 답글 달린 것 (in_reply_to_id 있음) → 스킵
   - bot 코멘트 → 기술적으로 평가 후 반영/스킵 결정
   - 사람 코멘트 → 신뢰하되 코드베이스 확인 후 반영
3. 반영할 항목 → 코드 수정 → commit → 답글 (commit 링크 포함)
4. 스킵할 항목 → 답글 (이유 명시)
5. 답글은 top-level PR comment 아닌 해당 스레드에 달기
```

## 5. 주의사항

- bot 리뷰(cursor-enterprise 등)는 제안이지 명령이 아님. 스키마 변경·YAGNI 범위 초과는 스킵 가능
- 반영 답글의 commit URL은 짧은 SHA(7자)로 하이퍼링크 처리
- 여러 코멘트 처리 시 반영/스킵 모두 병렬로 답글 달 수 있음
