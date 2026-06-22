---
name: coding-style-reference
description: Kotlin 코딩 스타일 상세 레퍼런스. Kotlin 스타일 가이드(data class, sealed class, 확장 함수, scope 함수, when 표현식), 코드 품질 체크리스트, 돌아가는 코드 검증 패턴 포함. 코드 작성/리뷰 시 참조.
---

# Coding Style 레퍼런스

## Kotlin 스타일 가이드

### DTO/Value Object
- data class로 표현
- copy()로 불변 변경

### 상태/에러/결과 표현
- sealed class/interface 활용
- when 표현식으로 분기 처리 (sealed class와 함께)

### 유틸리티
- 확장 함수로 구현
- scope 함수 적절히 활용:
  - `let`: null 체크 후 변환
  - `run`: 객체 설정 후 결과 반환
  - `apply`: 객체 초기화 (Builder 패턴 대체)
  - `also`: 부수 효과 (로깅 등)

## 코드 품질 체크리스트

작업 완료 전 반드시 확인:
- [ ] 가독성 좋고 이름이 적절한가
- [ ] 함수 크기 적정 (<50줄)
- [ ] 파일 크기 적정 (<800줄)
- [ ] 깊은 중첩 없음 (>4단계)
- [ ] 적절한 에러 처리
- [ ] 디버그 구문 없음 (println)
- [ ] 하드코딩 값 없음 (상수/설정 사용)
- [ ] 불변 패턴 사용

---

## 돌아가는 코드 검증 패턴

**단위 테스트 통과 ≠ 돌아가는 코드.** 구현 완료 후 실제 docker-compose 환경에서 기동 + API 호출로 검증해야 한다.

### 검증 스크립트 (`scripts/verify-api.sh`)

docker-compose 풀 환경(실제 MySQL, Redis, Kafka)에서 실제 설정값으로 API를 검증한다. 실패 시 `exit 1`로 CI에서도 사용 가능.

```bash
#!/bin/bash
# scripts/verify-api.sh — PR 전 실행 필수
set -euo pipefail

BASE_URL="${1:-http://localhost:8080}"

echo "=== Health Check ==="
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/actuator/health")
[ "$STATUS" -eq 200 ] && echo "✅ 200 OK" || { echo "❌ Expected 200, got $STATUS"; exit 1; }

echo "=== POST 알림 발송 → 201 ==="
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/v1/notifications" \
  -H "X-User-Id: verify-user" -H "Idempotency-Key: verify-$(date +%s)" \
  -H "Content-Type: application/json" \
  -d '{"channel":"SMS","recipient":"010-0000-0000","title":"test","content":"test"}')
[ "$STATUS" -eq 201 ] && echo "✅ 201 Created" || { echo "❌ Expected 201, got $STATUS"; exit 1; }

echo "=== GET 알림 목록 → 200 ==="
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/v1/notifications" \
  -H "X-User-Id: verify-user")
[ "$STATUS" -eq 200 ] && echo "✅ 200 OK" || { echo "❌ Expected 200, got $STATUS"; exit 1; }

echo "=== 잘못된 커서 → 400 ==="
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/v1/notifications?cursor=garbage" \
  -H "X-User-Id: verify-user")
[ "$STATUS" -eq 400 ] && echo "✅ 400 Bad Request" || { echo "❌ Expected 400, got $STATUS"; exit 1; }

echo ""
echo "모든 검증 통과 ✅"
```

### 검증 대상 (최소)

| 시나리오 | 기대 | 확인 항목 |
|----------|------|----------|
| Health Check | 200 | 서버 기동 |
| POST 정상 | 201 | 리소스 생성 |
| GET 정상 | 200 | 목록 반환 |
| GET 잘못된 입력 | 400 | 에러 처리 |
| GET 다른 사용자 | 200 + 빈 결과 | 데이터 격리 |
| Redis 캐시 생성 | 키 존재 | 캐시 동작 |
| POST 후 캐시 evict | 키 삭제 | evict 동작 |

---

## 에러 처리 패턴

### 외부 입력 방어적 파싱

```kotlin
// BAD — 500 에러
private fun decodeCursor(cursor: String): NotificationCursor {
    val raw = String(Base64.getUrlDecoder().decode(cursor))
    val parts = raw.split(",", limit = 2)
    return NotificationCursor(
        createdAt = LocalDateTime.parse(parts[0]),
        id = parts[1].toLong(),
    )
}

// GOOD — 400 에러
private fun decodeCursor(cursor: String): NotificationCursor {
    try {
        val raw = String(Base64.getUrlDecoder().decode(cursor))
        val parts = raw.split(",", limit = 2)
        return NotificationCursor(
            createdAt = LocalDateTime.parse(parts[0]),
            id = parts[1].toLong(),
        )
    } catch (e: Exception) {
        throw IllegalArgumentException("잘못된 커서 형식입니다")
    }
}
```

### 독립 작업 독립 에러 핸들링

```kotlin
// BAD — createPartitions 실패 시 purge 실행 안 됨
fun execute() {
    retentionManager.createUpcomingPartitions()
    retentionManager.purgeExpiredPartitions()
}

// GOOD — 각각 독립
fun execute() {
    try {
        retentionManager.createUpcomingPartitions()
    } catch (e: Exception) {
        log.error("파티션 생성 실패", e)
    }
    try {
        retentionManager.purgeExpiredPartitions()
    } catch (e: Exception) {
        log.error("만료 파티션 삭제 실패", e)
    }
}
```

---

## 설정값 단일 출처 패턴

```kotlin
// BAD — 두 곳에 같은 값
class NotificationRepositoryImpl {
    companion object {
        private const val RETENTION_DAYS = 7L  // 여기와
    }
}
// alarm.retention.days: 7  ← application.yml에도

// GOOD — 한 곳에서 관리
class NotificationRepositoryImpl(
    private val retentionProperties: RetentionProperties,
) {
    fun findByRequesterId(...) {
        val retentionStart = LocalDateTime.now().minusDays(retentionProperties.days)
        // ...
    }
}
```

---

## 캐시 키 완전성 패턴

```kotlin
// BAD — size가 키에 없음
@Cacheable(value = ["notification:list"], key = "#requesterId")
fun getNotifications(requesterId: String, cursor: String?, size: Int)

// GOOD — 결과에 영향 주는 파라미터 포함
@Cacheable(value = ["notification:list"], key = "#requesterId + ':' + #size", condition = "#cursor == null")
fun getNotifications(requesterId: String, cursor: String?, size: Int)
```
