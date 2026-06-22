---
name: patterns-reference
description: 공통 패턴 상세 레퍼런스. ApiResponse/ErrorResponse/PageResponse 코드, Idempotency Key 전체 구현(Port+Redis+AOP), DomainException sealed class 포함. API 개발, 패턴 적용 시 참조.
---

# 공통 패턴 레퍼런스

## API 응답 형식

```kotlin
data class ApiResponse<T>(
    val success: Boolean,
    val data: T? = null,
    val error: ErrorResponse? = null
)

data class ErrorResponse(
    val code: String,
    val message: String,
    val details: List<FieldError>? = null
)

data class PageResponse<T>(
    val content: List<T>,
    val page: Int,
    val size: Int,
    val totalElements: Long,
    val totalPages: Int
)
```

## Idempotency Key Pattern

상태 변경 API(POST/PUT/PATCH/DELETE)에 적용.

### 흐름
```
Client → [Idempotency-Key: uuid] → Server
  1. 키로 기존 결과 조회
  2. 있으면 → 저장된 응답 반환 (재처리 없음)
  3. 없으면 → 처리 → 결과 저장 → 응답
```

### domain 모듈 (Port)
```kotlin
interface IdempotencyStore {
    fun get(key: String): IdempotencyRecord?
    fun save(key: String, record: IdempotencyRecord)
}

data class IdempotencyRecord(
    val key: String,
    val statusCode: Int,
    val responseBody: String,
    val createdAt: LocalDateTime = LocalDateTime.now()
)
```

### infra 모듈 (Redis 구현)
```kotlin
@ConfigurationProperties(prefix = "idempotency")
data class IdempotencyProperties(
    val ttl: Duration = Duration.ofHours(24),
    val keyPrefix: String = "idempotency"
)

@Repository
class RedisIdempotencyStore(
    private val redisTemplate: StringRedisTemplate,
    private val properties: IdempotencyProperties
) : IdempotencyStore {

    override fun get(key: String): IdempotencyRecord? {
        val value = redisTemplate.opsForValue().get("${properties.keyPrefix}:$key")
        return value?.let { objectMapper.readValue(it) }
    }

    override fun save(key: String, record: IdempotencyRecord) {
        redisTemplate.opsForValue().set(
            "${properties.keyPrefix}:$key",
            objectMapper.writeValueAsString(record),
            properties.ttl
        )
    }
}
```

### application.yml
```yaml
idempotency:
  ttl: 24h
  key-prefix: idempotency
```

### app-api 모듈 (AOP)
```kotlin
@Aspect
@Component
class IdempotencyAspect(
    private val idempotencyStore: IdempotencyStore
) {
    @Around("@annotation(Idempotent)")
    fun checkIdempotency(joinPoint: ProceedingJoinPoint): Any? {
        val request = (RequestContextHolder.getRequestAttributes() as ServletRequestAttributes).request
        val key = request.getHeader("Idempotency-Key")
            ?: throw DomainException.InvalidState("Idempotency-Key 헤더 필수")

        idempotencyStore.get(key)?.let { return it.toResponse() }

        val result = joinPoint.proceed()
        idempotencyStore.save(key, IdempotencyRecord.from(result))
        return result
    }
}

@Target(AnnotationTarget.FUNCTION)
@Retention(AnnotationRetention.RUNTIME)
annotation class Idempotent
```

### 사용
```kotlin
@PostMapping
@Idempotent  // 이것만 붙이면 멱등성 보장
fun createOrder(@RequestBody request: CreateOrderRequest): ApiResponse<OrderResponse> {
    // ...
}
```

## Domain Exception Pattern

```kotlin
sealed class DomainException(
    val errorCode: String,
    override val message: String
) : RuntimeException(message) {
    class NotFound(entity: String, id: Any) :
        DomainException("NOT_FOUND", "$entity not found: $id")
    class AlreadyExists(entity: String, field: String, value: Any) :
        DomainException("ALREADY_EXISTS", "$entity already exists: $field=$value")
    class InvalidState(reason: String) :
        DomainException("INVALID_STATE", reason)
    class AccessDenied(reason: String) :
        DomainException("ACCESS_DENIED", reason)
}
```
