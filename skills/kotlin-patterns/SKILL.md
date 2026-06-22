---
name: kotlin-patterns
description: Apply idiomatic Kotlin patterns when writing Kotlin code. Covers null safety, scope functions, data classes, sealed classes, coroutines, and collection operations. Use for ALL Kotlin code.
---

# Kotlin Patterns & Idioms

## Null Safety

### Safe Call & Elvis
```kotlin
// Good
val name = user?.name ?: "Unknown"
val length = text?.length ?: 0

// Bad
val name = if (user != null) user.name else "Unknown"
```

### let / takeIf / takeUnless
```kotlin
// null이 아닐 때만 실행
user?.let { sendWelcomeEmail(it) }

// 조건 필터링
findUser(id)
    ?.takeIf { it.isActive }
    ?.let { grantAccess(it) }
```

### require / check
```kotlin
fun processPayment(amount: Long, userId: Long) {
    require(amount > 0) { "금액은 양수여야 합니다: $amount" }
    require(userId > 0) { "유효하지 않은 사용자 ID: $userId" }

    val user = userRepository.findById(userId)
    checkNotNull(user) { "사용자를 찾을 수 없습니다: $userId" }
    check(user.isActive) { "비활성 사용자: $userId" }
}
```

## Scope Functions

| 함수 | 참조 | 반환값 | 용도 |
|------|------|--------|------|
| let | it | Lambda 결과 | null 체크, 변환 |
| run | this | Lambda 결과 | 객체 설정 + 결과 |
| with | this | Lambda 결과 | 객체에 대한 다수 호출 |
| apply | this | 객체 자체 | 객체 초기화 |
| also | it | 객체 자체 | 부수 효과 (로깅 등) |

```kotlin
// apply: 객체 초기화
val config = ServerConfig().apply {
    port = 8080
    host = "localhost"
    maxConnections = 100
}

// also: 부수 효과
fun createUser(request: CreateUserRequest): User =
    userRepository.save(request.toDomain())
        .also { logger.info("사용자 생성: ${it.id}") }

// let: null 체크 + 변환
val displayName = user?.let { "${it.firstName} ${it.lastName}" }

// run: 계산 결과
val result = service.run {
    validate(input)
    process(input)
}
```

## Data Class

```kotlin
// 불변 데이터 전달
data class CreateOrderCommand(
    val userId: Long,
    val items: List<OrderItemCommand>,
    val couponCode: String? = null
)

// 수정은 copy() 사용
val updated = order.copy(status = OrderStatus.CONFIRMED)
```

## Sealed Class / Interface

```kotlin
// 도메인 예외
sealed class DomainException(
    val errorCode: String,
    override val message: String
) : RuntimeException(message) {
    class NotFound(entity: String, id: Any) :
        DomainException("NOT_FOUND", "$entity not found: $id")
    class AlreadyExists(entity: String, key: String) :
        DomainException("ALREADY_EXISTS", "$entity already exists: $key")
    class InvalidState(reason: String) :
        DomainException("INVALID_STATE", reason)
}

// 결과 타입
sealed interface Result<out T> {
    data class Success<T>(val data: T) : Result<T>
    data class Failure(val error: DomainException) : Result<Nothing>
}

// exhaustive when
fun handleResult(result: Result<Order>) = when (result) {
    is Result.Success -> processOrder(result.data)
    is Result.Failure -> handleError(result.error)
}
```

## Extension Functions

```kotlin
// 유틸리티를 확장 함수로
fun String.toSlug(): String =
    lowercase()
        .replace(Regex("[^a-z0-9\\s-]"), "")
        .replace(Regex("\\s+"), "-")

fun <T> T?.orThrow(lazyMessage: () -> String): T =
    this ?: throw IllegalArgumentException(lazyMessage())

// 컬렉션 확장
fun <T> List<T>.second(): T = this[1]
```

## Collection Operations

```kotlin
// 변환
val names = users.map { it.name }

// 필터링
val activeUsers = users.filter { it.isActive }

// 그룹핑
val byDepartment = users.groupBy { it.department }

// 집계
val totalSalary = users.sumOf { it.salary }

// 체이닝
val result = orders
    .filter { it.status == OrderStatus.COMPLETED }
    .flatMap { it.items }
    .groupBy { it.productId }
    .mapValues { (_, items) -> items.sumOf { it.quantity } }

// 대량 데이터는 Sequence 사용
val result = users.asSequence()
    .filter { it.isActive }
    .map { it.toDto() }
    .take(100)
    .toList()
```

## Coroutines (필요 시)

```kotlin
// 구조적 동시성
suspend fun processOrders(orderIds: List<Long>): List<OrderResult> =
    coroutineScope {
        orderIds.map { id ->
            async { orderService.process(id) }
        }.awaitAll()
    }

// Flow
fun observeOrders(): Flow<Order> = flow {
    while (true) {
        emit(orderRepository.findPending())
        delay(1000)
    }
}
```

## Anti-Patterns

```kotlin
// BAD: !! 사용
val name = user!!.name

// GOOD: 안전한 처리
val name = user?.name ?: throw UserNotFoundException(userId)

// BAD: 가변 컬렉션 노출
fun getUsers(): MutableList<User> = users

// GOOD: 불변 컬렉션 반환
fun getUsers(): List<User> = users.toList()

// BAD: 과도한 scope 함수 중첩
user?.let { u ->
    u.address?.let { a ->
        a.city?.let { c -> process(c) }
    }
}

// GOOD: 평탄하게
val city = user?.address?.city ?: return
process(city)
```
