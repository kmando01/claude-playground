---
name: api-smoke-test
description: API 엔드포인트의 성공/실패 케이스를 curl로 검증하는 스모크 테스트 스크립트를 생성하고 실행한다
user_invocable: true
---

# API Smoke Test

API 엔드포인트가 실제로 동작하는지 curl 기반 스모크 테스트를 작성하고 실행한다.

## When to Use

- 새 API 엔드포인트를 구현한 후
- 기존 API를 수정한 후
- 배포 전 빠른 검증이 필요할 때
- `/api-smoke-test` 또는 `/smoke-test`로 호출

## Process

### 1. 대상 파악

테스트 대상 엔드포인트를 파악한다. 사용자가 지정하지 않으면:
- 최근 커밋에서 변경된 Controller 파일을 찾는다
- Swagger docs 인터페이스에서 엔드포인트 목록을 추출한다

### 2. 테스트 케이스 설계

각 엔드포인트에 대해 최소 다음을 포함한다:

**성공 케이스:**
- 정상 요청 → 기대 상태 코드 + 응답 본문 검증

**실패 케이스:**
- 필수 파라미터 누락 → 400
- 잘못된 인증 → 401/403
- 존재하지 않는 리소스 → 404
- 잘못된 Content-Type → 415
- Validation 실패 → 400 + 에러 메시지

**경계 케이스:**
- 빈 문자열, 최대 길이 초과
- redirect 검증 (302/303 → Location 헤더)
- 쿠키 설정/삭제 검증
- 일회성 토큰 재사용 → 실패 확인

### 3. 스크립트 작성 규칙

```bash
# 파일 위치: scripts/api-test/test-{도메인}.sh
# 실행 권한: chmod +x

# 필수 구조:
#!/bin/bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8080}"
PASS=0
FAIL=0
TOTAL=0

# 색상 상수
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# assert 함수 (아래 참조)

# 테스트 케이스들

# 결과 요약 + exit code
```

### 4. Assert 함수

```bash
# HTTP 상태 코드 검증
assert_status() {
    local test_name="$1"
    local expected="$2"
    local actual="$3"
    local body="${4:-}"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" -eq "$expected" ]; then
        echo -e "${GREEN}[PASS]${NC} $test_name (HTTP $actual)"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}[FAIL]${NC} $test_name (expected $expected, got $actual)"
        [ -n "$body" ] && echo "       Response: $(echo "$body" | head -3)"
        FAIL=$((FAIL + 1))
    fi
}

# 응답 본문 내용 검증
assert_contains() {
    local test_name="$1"
    local expected="$2"
    local body="$3"
    TOTAL=$((TOTAL + 1))
    if echo "$body" | grep -q "$expected"; then
        echo -e "${GREEN}[PASS]${NC} $test_name (contains '$expected')"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}[FAIL]${NC} $test_name (missing '$expected')"
        echo "       Response: $(echo "$body" | head -3)"
        FAIL=$((FAIL + 1))
    fi
}

# Redirect 검증 (상태 코드 + Location 헤더)
assert_redirect() {
    local test_name="$1"
    local expected_status="$2"
    local expected_location_contains="$3"
    local actual_status="$4"
    local actual_location="$5"
    TOTAL=$((TOTAL + 1))
    if [ "$actual_status" -eq "$expected_status" ] && \
       echo "$actual_location" | grep -q "$expected_location_contains"; then
        echo -e "${GREEN}[PASS]${NC} $test_name (HTTP $actual_status → $expected_location_contains)"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}[FAIL]${NC} $test_name (status=$actual_status, location=$actual_location)"
        FAIL=$((FAIL + 1))
    fi
}
```

### 5. curl 패턴

```bash
# 상태 코드 + 본문 함께 캡처
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$URL" -H "..." -d '...')
BODY=$(echo "$RESPONSE" | head -n -1)
STATUS=$(echo "$RESPONSE" | tail -1)

# Redirect URL 캡처 (따라가지 않음)
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}\n%{redirect_url}" -X GET "$URL")
STATUS=$(echo "$RESPONSE" | head -1)
LOCATION=$(echo "$RESPONSE" | tail -1)

# 헤더 포함 캡처 (쿠키 검증용)
RESPONSE=$(curl -s -D - -o /dev/null -w "\n%{http_code}" -X POST "$URL" -d "...")
STATUS=$(echo "$RESPONSE" | tail -1)
HEADERS=$(echo "$RESPONSE" | head -n -1)
```

### 6. 환경변수 패턴

인증이 필요한 테스트는 환경변수로 토큰/계정을 주입한다:

```bash
ADMIN_TOKEN="${ADMIN_TOKEN:-}"
TEST_EMAIL="${TEST_EMAIL:-}"
TEST_PASSWORD="${TEST_PASSWORD:-}"

if [ -n "$ADMIN_TOKEN" ]; then
    # 인증 필요한 테스트 실행
else
    echo -e "${YELLOW}[SKIP]${NC} 인증 필요: export ADMIN_TOKEN=<토큰>"
fi
```

### 7. 실행 및 결과

```bash
# 로컬
./scripts/api-test/test-auth-api.sh

# 특정 서버
./scripts/api-test/test-auth-api.sh https://be.dev.eeos.store

# 인증 포함
ADMIN_TOKEN=xxx TEST_EMAIL=user@test.com TEST_PASSWORD=pass \
  ./scripts/api-test/test-auth-api.sh

# 결과 예시:
# [PASS] 1-1. WEB 클라이언트 등록 (HTTP 201)
# [FAIL] 2-3. response_type=token → 400 (expected 400, got 200)
# 결과: PASS=15 / FAIL=1 / TOTAL=16
```

### 8. 결과 요약

```bash
echo ""
echo "======================================"
echo -e " 결과: ${GREEN}PASS=$PASS${NC} / ${RED}FAIL=$FAIL${NC} / TOTAL=$TOTAL"
echo "======================================"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
```

`exit 1`로 CI에서도 실패를 감지할 수 있다.

## 기존 테스트 스크립트

| 파일 | 대상 |
|------|------|
| `scripts/api-test/test-auth-api.sh` | Web/App 인증 분리 전체 플로우 |

## Common Mistakes

| 실수 | 해결 |
|------|------|
| `-L` 옵션으로 redirect 따라감 | redirect 테스트 시 `-L` 제거, `-o /dev/null -w` 사용 |
| 상태 코드를 본문과 분리 못 함 | `-w "\n%{http_code}"` + `tail -1` 패턴 사용 |
| 쿠키 검증 누락 | `-D -` 로 헤더 캡처 |
| 인증 토큰 하드코딩 | 환경변수 패턴 사용 |
| form-urlencoded를 JSON으로 보냄 | Content-Type 확인, `-d` vs `-d '{"json"}'` |
