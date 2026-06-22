---
name: spring-transaction
description: Spring transaction management patterns for Kotlin. Use when implementing transactional boundaries, concurrency control (optimistic/pessimistic locking), or handling transaction propagation and isolation levels.
---

# Spring 트랜잭션 & 동시성 제어 패턴

## 트랜잭션 기본 규칙

```
app-api (Controller)  → 트랜잭션 시작하지 않음
app-api (AppService)  → @Transactional 선언 (트랜잭션 경계)
domain  (Service)     → 트랜잭션 어노테이션 없음 (순수 Kotlin)
infra   (Repository)  → 개별 트랜잭션 불필요 (상위에서 관리)
```

## Application Service 패턴

```kotlin
// app-api 모듈
@Service
@Transactional(readOnly = true)  // 기본: 읽기 전용
class OrderApplicationService(
    private val createOrderUseCase: CreateOrderUseCase,
    private val orderRepository: OrderRepository
) {
    @Transactional  // 쓰기 작업만 오버라이드
    fun createOrder(command: CreateOrderCommand): Order =
        createOrderUseCase.execute(command)

    fun getOrder(id: Long): Order =
        orderRepository.findById(id)
            ?: throw DomainException.NotFound("Order", id)

    fun getOrders(userId: Long, pageable: PageRequest): Page<Order> =
        orderRepository.findByUserId(userId, pageable)
}
```

## 전파 레벨 (Propagation)

### REQUIRED (기본값)
```kotlin
// 기존 트랜잭션 있으면 참여, 없으면 새로 생성
@Transactional(propagation = Propagation.REQUIRED)
fun createOrder(command: CreateOrderCommand): Order { ... }
```

### REQUIRES_NEW (독립 트랜잭션)
```kotlin
// 항상 새 트랜잭션 생성. 외부 트랜잭션 실패해도 이 트랜잭션은 유지됨.
// 사용 케이스: 감사 로그, 이벤트 발행 등 반드시 기록해야 하는 작업
@Transactional(propagation = Propagation.REQUIRES_NEW)
fun saveAuditLog(event: AuditEvent) {
    auditRepository.save(AuditLog.from(event))
}
```

### NOT_SUPPORTED (트랜잭션 없이)
```kotlin
// 외부 API 호출 등 트랜잭션이 불필요하거나 해로운 경우
@Transactional(propagation = Propagation.NOT_SUPPORTED)
fun callExternalApi(orderId: Long): PaymentResult {
    return paymentClient.requestPayment(orderId)
}
```

## 격리 레벨 (Isolation)

| 레벨 | Dirty Read | Non-Repeatable Read | Phantom Read | 사용 케이스 |
|------|-----------|-------------------|-------------|------------|
| READ_COMMITTED (기본) | X | O | O | 대부분의 경우 |
| REPEATABLE_READ | X | X | O | 정산, 잔액 계산 |
| SERIALIZABLE | X | X | X | 거의 사용 안 함 (성능 비용) |

```kotlin
// 정산처럼 읽은 데이터가 트랜잭션 내에서 변하면 안 되는 경우
@Transactional(isolation = Isolation.REPEATABLE_READ)
fun calculateSettlement(date: LocalDate): Settlement { ... }
```

## 낙관적 락 (Optimistic Lock)

### JPA Entity (@Version)
```kotlin
// infra 모듈
@Entity
@Table(name = "orders")
class OrderJpaEntity(
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long = 0,

    @Version  // 낙관적 락 버전 필드
    val version: Long = 0,

    @Enumerated(EnumType.STRING)
    var status: OrderStatus,

    // ...
)
```

### 충돌 시 처리
```kotlin
// infra 모듈: Repository 구현
@Repository
class OrderRepositoryImpl(
    private val jpaRepository: OrderJpaRepository
) : OrderRepository {

    @Transactional
    override fun save(order: Order): Order {
        try {
            val entity = OrderJpaEntity.from(order)
            return jpaRepository.save(entity).toDomain()
        } catch (e: OptimisticLockingFailureException) {
            throw DomainException.InvalidState(
                "다른 사용자가 동시에 수정했습니다. 다시 시도해주세요."
            )
        }
    }
}
```

### app-api에서 재시도
```kotlin
// 재시도 로직 (AOP 또는 직접 구현)
@Transactional
fun confirmOrder(orderId: Long): Order {
    repeat(3) { attempt ->
        try {
            val order = orderRepository.findById(orderId)
                ?: throw DomainException.NotFound("Order", orderId)
            val confirmed = order.confirm()
            return orderRepository.save(confirmed)
        } catch (e: DomainException.InvalidState) {
            if (attempt == 2) throw e  // 마지막 시도에서도 실패하면 throw
        }
    }
    throw DomainException.InvalidState("주문 확인에 실패했습니다")
}
```

## 비관적 락 (Pessimistic Lock)

### JPA Repository
```kotlin
// infra 모듈: JPA Repository
interface OrderJpaRepository : JpaRepository<OrderJpaEntity, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("SELECT o FROM OrderJpaEntity o WHERE o.id = :id")
    fun findByIdForUpdate(id: Long): OrderJpaEntity?
}
```

### 사용 (재고 차감 등 충돌 빈번한 경우)
```kotlin
@Transactional
fun decreaseStock(productId: Long, quantity: Int): Product {
    val product = productJpaRepository.findByIdForUpdate(productId)
        ?: throw DomainException.NotFound("Product", productId)

    val domain = product.toDomain()
    val decreased = domain.decreaseStock(quantity)  // 도메인 로직

    product.stock = decreased.stock
    return productJpaRepository.save(product).toDomain()
}
```

## 분산 락 (Redis + Redisson)

```kotlin
// infra 모듈
@Component
class RedisDistributedLock(
    private val redissonClient: RedissonClient
) {
    fun <T> withLock(
        key: String,
        waitTime: Long = 5,
        leaseTime: Long = 10,
        unit: TimeUnit = TimeUnit.SECONDS,
        action: () -> T
    ): T {
        val lock = redissonClient.getLock("lock:$key")
        val acquired = lock.tryLock(waitTime, leaseTime, unit)
        if (!acquired) {
            throw DomainException.InvalidState("잠금 획득 실패: $key")
        }
        try {
            return action()
        } finally {
            if (lock.isHeldByCurrentThread) {
                lock.unlock()
            }
        }
    }
}
```

### 사용
```kotlin
@Transactional
fun reserveSeat(seatId: Long, userId: Long): Reservation {
    return distributedLock.withLock("seat:$seatId") {
        val seat = seatRepository.findById(seatId)
            ?: throw DomainException.NotFound("Seat", seatId)
        val reserved = seat.reserve(userId)
        seatRepository.save(reserved)
    }
}
```

## 락 전략 선택 가이드

| 상황 | 전략 | 이유 |
|------|------|------|
| 읽기 많고 충돌 드문 경우 | 낙관적 락 | 락 오버헤드 없음, 충돌 시에만 비용 |
| 충돌이 빈번한 경우 (재고, 좌석) | 비관적 락 | 충돌 시 재시도 비용이 더 큼 |
| 멀티 인스턴스 환경 | 분산 락 | DB 락으로 부족, Redis 기반 |
| 단순 카운터 증감 | DB 원자적 연산 | 락 불필요, UPDATE SET stock = stock - 1 |

## 트랜잭션 안티패턴

```kotlin
// BAD: Controller에서 @Transactional
@RestController
class OrderController {
    @Transactional  // 여기서 하면 안 됨!
    @PostMapping("/orders")
    fun create() { ... }
}

// BAD: 트랜잭션 안에서 외부 API 호출
@Transactional
fun createOrder(command: CreateOrderCommand): Order {
    val order = orderRepository.save(...)
    paymentClient.requestPayment(order)  // DB 커넥션을 잡고 있는 동안 외부 호출!
    return order
}

// GOOD: 외부 호출은 트랜잭션 밖에서
fun createOrder(command: CreateOrderCommand): Order {
    val order = createOrderInternal(command)  // @Transactional
    paymentClient.requestPayment(order)       // 트랜잭션 밖
    return order
}

// BAD: 같은 클래스 내 @Transactional 호출 (프록시 우회)
@Service
class OrderService {
    fun outer() {
        inner()  // @Transactional이 적용 안 됨! (self-invocation)
    }

    @Transactional
    fun inner() { ... }
}

// GOOD: 별도 클래스로 분리
@Service
class OrderFacade(private val orderService: OrderService) {
    fun outer() {
        orderService.inner()  // 프록시를 통해 호출 → 트랜잭션 적용됨
    }
}
```
