---
name: econovation-pr
description: econovation GitHub 레포(auth-common, EEOS-BE, econo-passport)에 표준 형식으로 PR을 생성하거나 수정한다. 트리거: "PR 올려줘", "PR 만들어줘", "PR description 써줘", "PR 수정해줘"
---

# Econovation PR 스킬

## PR 형식 규칙

모든 PR은 아래 세 섹션만 가진다. 코드 변경 목록, 파일 목록은 절대 쓰지 않는다.

```markdown
## 개요

[이 PR이 왜 존재하는지, 무엇을 바꾸는지 2~4문장]

관련 PR: [링크] (있을 경우)
인증 흐름 다이어그램: [링크] (인증 관련 PR일 경우)

---

## 영향 범위

[프론트엔드 / 백엔드 / 운영 관점에서 무엇이 달라지는지]
[memberId 등 서비스 설계 원칙에 영향을 주면 명시]

---

## 배포 전 필수 확인

- [항목1]
- [항목2]
```

## 레포별 체크리스트

### auth-common
- `COOKIE_DOMAIN=.econovation.kr` 환경 변수 필수 여부
- `RSA_PRIVATE_KEY`, `RSA_PUBLIC_KEY` 환경 변수 필수 여부
- 내부 서비스 직접 외부 노출 금지 (X-User-Passport 위조 가능)
- 회원 데이터 이관: `scripts/migrate-eeos-members.py --dry-run` 후 실행

### EEOS-BE
- auth-common PR이 먼저 배포되어야 함
- DB 마이그레이션 포함 여부 → 포함 시 **왜 해당 테이블이 DROP/변경되는지** 반드시 명시
- 회원 데이터 이관 스크립트:
  ```bash
  python scripts/migrate-eeos-members.py --dry-run
  python scripts/migrate-eeos-members.py
  ```
- 프론트엔드에서 제거된 엔드포인트 사용 여부 확인

### econo-passport
- JitPack 배포는 태그(`v1.x.x`) 기준
- api-gateway(auth-common)가 먼저 배포되어야 라이브러리가 동작함
- 각 서비스 DB는 여전히 `memberId`를 FK로 보관해야 함을 영향 범위에 명시

## 브랜치 전략

- auth-common: `feat/*` → `feat/member-auth` (PR base)
- EEOS-BE: `SM/feat/*` → `develop` (PR base)
- econo-passport: `feat/*` → `develop` → `main` (PR base: develop)

## 실행 절차

1. 현재 브랜치와 변경 사항 파악
   ```bash
   gh pr view --json title,body,headRefName,baseRefName
   ```

2. 레포 확인 후 해당 체크리스트 적용

3. PR 생성 또는 수정
   ```bash
   # 생성
   gh pr create --base <base> --title "[타입] 제목" --body "..."

   # 수정
   gh pr edit <number> --body "..."
   ```

4. 인증 관련 PR이면 다이어그램 링크 포함
   - https://github.com/JNU-econovation/auth-common/blob/feat/member-auth/docs/SEQUENCE-DIAGRAMS.md
