---
name: spring-hexagonal-patterns
description: Apply Spring Boot hexagonal architecture patterns aligned with multi-module project structure. Covers domain modeling, ports & adapters, API design, exception handling, validation, and testing. Use when working on Spring Boot multi-module projects.
---

# Spring Boot + 멀티모듈 아키텍처 패턴

## 모듈 ↔ 헥사고날 매핑

```
멀티모듈                    헥사고날 아키텍처
─────────────────────────────────────────
xxx-domain          →    Domain Layer (Entity, Value Object, Port)
xxx-infra           →    Outbound Adapter (JPA, Redis, Kafka)
xxx-client-external →    Outbound Adapter (외부 API)
xxx-app-api         →    Inbound Adapter (REST Controller)
xxx-app-admin       →    Inbound Adapter (Admin Controller)
xxx-app-batch       →    Inbound Adapter (Batch Job, Consumer)
xxx-common          →    Shared Kernel (공통 유틸, 상수)
```

## Domain Layer (xxx-domain)

### Entity (도메인 모델)
```kotlin
// 순수 Kotlin - 프레임워크 의존성 없음
data class Order(
    val id: Long = 0,
    val userId: Long,
    val items: List<OrderItem>,
    val status: OrderStatus,
    val totalPrice: Money,
    val createdAt: LocalDateTime = LocalDateTime.now()
) {
    fun confirm(): Order {
        check(status == OrderStatus.PENDING) {
            "PENDING 상태만 확인 가능: $status"
        }
        return copy(status = OrderStatus.CONFIRMED)
    }

    fun cancel(): Order {
        check(status in listOf(OrderStatus.PENDING, OrderStatus.CONFIRMED)) {
            "취소 불가 상태: $status"
        }
        return copy(status = OrderStatus.CANCELLED)
    }
}

enum class OrderStatus { PENDING, CONFIRMED, SHIPPED, DELIVERED, CANCELLED }
```

### Value Object
```kotlin
@JvmInline
value class Money(val amount: Long) {
    init { require(amount >= 0) { "금액은 0 이상: $amount" } }

    operator fun plus(other: Money) = Money(amount + other.amount)
    operator fun times(quantity: Int) = Money(amount * quantity)

    companion object {
        val ZERO = Money(0)
    }
}

@JvmInline
value class Email(val value: String) {
    init {
        require(value.matches(Regex("^[\\w.-]+@[\\w.-]+\\.\\w+$"))) {
            "유효하지 않은 이메일: $value"
        }
    }
}
```

### Port (인터페이스)
```kotlin
// Inbound Port (Use Case)
interface CreateOrderUseCase {
    fun execute(command: CreateOrderCommand): Order
}

data class CreateOrderCommand(
    val userId: Long,
    val items: List<OrderItemCommand>
)

// Outbound Port (Repository)
interface OrderRepository {
    fun findById(id: Long): Order?
    fun save(order: Order): Order
    fun findByUserId(userId: Long, pageable: PageRequest): Page<Order>
}

// Outbound Port (External)
interface PaymentClient {
    fun requestPayment(orderId: Long, amount: Money): PaymentResult
}
```

### Domain Service
```kotlin
class OrderService(
    private val orderRepository: OrderRepository,
    private val productRepository: ProductRepository
) : CreateOrderUseCase {

    override fun execute(command: CreateOrderCommand): Order {
        val items = command.items.map { item ->
            val product = productRepository.findById(item.productId)
                ?: throw DomainException.NotFound("Product", item.productId)
            OrderItem(
                productId = product.id,
                productName = product.name,
                price = product.price,
                quantity = item.quantity
            )
        }

        val totalPrice = items.fold(Money.ZERO) { acc, item ->
            acc + (item.price * item.quantity)
        }

        return orderRepository.save(
            Order(
                userId = command.userId,
                items = items,
                status = OrderStatus.PENDING,
                totalPrice = totalPrice
            )
        )
    }
}
```

### Domain Exception
```kotlin
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
    class AccessDenied(reason: String) :
        DomainException("ACCESS_DENIED", reason)
}
```

## Outbound Adapter (xxx-infra)

### JPA Entity
```kotlin
@Entity
@Table(name = "orders")
class OrderJpaEntity(
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long = 0,

    @Column(nullable = false)
    val userId: Long,

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    var status: OrderStatus,

    @Column(nullable = false)
    val totalPrice: Long,

    @Column(nullable = false)
    val createdAt: LocalDateTime = LocalDateTime.now()
) {
    fun toDomain(items: List<OrderItem>): Order = Order(
        id = id,
        userId = userId,
        items = items,
        status = status,
        totalPrice = Money(totalPrice),
        createdAt = createdAt
    )

    companion object {
        fun from(order: Order) = OrderJpaEntity(
            id = order.id,
            userId = order.userId,
            status = order.status,
            totalPrice = order.totalPrice.amount,
            createdAt = order.createdAt
        )
    }
}
```

### Repository 구현
```kotlin
@Repository
class OrderRepositoryImpl(
    private val jpaRepository: OrderJpaRepository,
    private val itemJpaRepository: OrderItemJpaRepository
) : OrderRepository {

    override fun findById(id: Long): Order? {
        val entity = jpaRepository.findByIdOrNull(id) ?: return null
        val items = itemJpaRepository.findByOrderId(id).map { it.toDomain() }
        return entity.toDomain(items)
    }

    @Transactional
    override fun save(order: Order): Order {
        val saved = jpaRepository.save(OrderJpaEntity.from(order))
        val savedItems = order.items.map { item ->
            itemJpaRepository.save(OrderItemJpaEntity.from(saved.id, item))
        }
        return saved.toDomain(savedItems.map { it.toDomain() })
    }

    override fun findByUserId(userId: Long, pageable: PageRequest): Page<Order> =
        jpaRepository.findByUserId(userId, pageable).map { entity ->
            val items = itemJpaRepository.findByOrderId(entity.id).map { it.toDomain() }
            entity.toDomain(items)
        }
}
```

## Inbound Adapter (xxx-app-api)

### REST Controller
```kotlin
@RestController
@RequestMapping("/api/v1/orders")
class OrderController(
    private val createOrderUseCase: CreateOrderUseCase,
    private val getOrderUseCase: GetOrderUseCase
) {
    @PostMapping
    fun createOrder(
        @Valid @RequestBody request: CreateOrderRequest,
        @AuthenticationPrincipal user: AuthUser
    ): ApiResponse<OrderResponse> {
        val command = request.toCommand(user.id)
        val order = createOrderUseCase.execute(command)
        return ApiResponse.success(OrderResponse.from(order))
    }

    @GetMapping("/{orderId}")
    fun getOrder(
        @PathVariable orderId: Long,
        @AuthenticationPrincipal user: AuthUser
    ): ApiResponse<OrderResponse> {
        val order = getOrderUseCase.execute(orderId, user.id)
        return ApiResponse.success(OrderResponse.from(order))
    }
}
```

### API Response
```kotlin
data class ApiResponse<T>(
    val success: Boolean,
    val data: T? = null,
    val error: ErrorResponse? = null
) {
    companion object {
        fun <T> success(data: T) = ApiResponse(success = true, data = data)
        fun error(code: String, message: String) =
            ApiResponse<Nothing>(success = false, error = ErrorResponse(code, message))
    }
}
```

### Global Exception Handler
```kotlin
@RestControllerAdvice
class GlobalExceptionHandler {
    private val logger = LoggerFactory.getLogger(javaClass)

    @ExceptionHandler(DomainException.NotFound::class)
    fun handleNotFound(e: DomainException.NotFound): ResponseEntity<ApiResponse<Nothing>> {
        logger.warn("Not found: ${e.message}")
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(ApiResponse.error(e.errorCode, e.message))
    }

    @ExceptionHandler(DomainException.AlreadyExists::class)
    fun handleAlreadyExists(e: DomainException.AlreadyExists): ResponseEntity<ApiResponse<Nothing>> {
        logger.warn("Already exists: ${e.message}")
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(ApiResponse.error(e.errorCode, e.message))
    }

    @ExceptionHandler(MethodArgumentNotValidException::class)
    fun handleValidation(e: MethodArgumentNotValidException): ResponseEntity<ApiResponse<Nothing>> {
        val errors = e.bindingResult.fieldErrors.map {
            FieldError(it.field, it.defaultMessage ?: "Invalid")
        }
        return ResponseEntity.badRequest()
            .body(ApiResponse.error("VALIDATION_ERROR", "입력값 검증 실패", errors))
    }
}
```

### Input Validation
```kotlin
data class CreateOrderRequest(
    @field:NotNull(message = "상품 목록은 필수입니다")
    @field:Size(min = 1, message = "최소 1개 상품이 필요합니다")
    val items: List<OrderItemRequest>
) {
    fun toCommand(userId: Long) = CreateOrderCommand(
        userId = userId,
        items = items.map { it.toCommand() }
    )
}

data class OrderItemRequest(
    @field:Positive(message = "상품 ID는 양수여야 합니다")
    val productId: Long,

    @field:Min(value = 1, message = "수량은 1 이상이어야 합니다")
    @field:Max(value = 100, message = "수량은 100 이하여야 합니다")
    val quantity: Int
)
```

## Transaction Management

```kotlin
// app 모듈의 Application Service에서 트랜잭션 관리
@Service
@Transactional(readOnly = true)
class OrderApplicationService(
    private val createOrderUseCase: CreateOrderUseCase,
    private val orderRepository: OrderRepository
) {
    @Transactional
    fun createOrder(command: CreateOrderCommand): Order =
        createOrderUseCase.execute(command)

    fun getOrder(id: Long): Order =
        orderRepository.findById(id)
            ?: throw DomainException.NotFound("Order", id)
}
```

## Testing Patterns

### Unit Test (domain)
```kotlin
class OrderServiceTest {
    private val orderRepository = mockk<OrderRepository>()
    private val productRepository = mockk<ProductRepository>()
    private val sut = OrderService(orderRepository, productRepository)

    @Test
    fun `주문 생성 시 PENDING 상태여야 한다`() {
        // Arrange
        val product = Product(id = 1, name = "상품A", price = Money(10000))
        every { productRepository.findById(1) } returns product
        every { orderRepository.save(any()) } answers { firstArg() }

        // Act
        val result = sut.execute(CreateOrderCommand(
            userId = 1L,
            items = listOf(OrderItemCommand(productId = 1, quantity = 2))
        ))

        // Assert
        assertThat(result.status).isEqualTo(OrderStatus.PENDING)
        assertThat(result.totalPrice).isEqualTo(Money(20000))
    }
}
```

### Integration Test (infra)
```kotlin
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class OrderRepositoryImplTest {
    @Container
    companion object {
        val postgres = PostgreSQLContainer("postgres:15")
            .apply { start() }

        @JvmStatic
        @DynamicPropertySource
        fun properties(registry: DynamicPropertyRegistry) {
            registry.add("spring.datasource.url") { postgres.jdbcUrl }
            registry.add("spring.datasource.username") { postgres.username }
            registry.add("spring.datasource.password") { postgres.password }
        }
    }

    @Autowired
    private lateinit var repository: OrderRepositoryImpl

    @Test
    fun `주문을 저장하고 조회할 수 있다`() {
        val order = Order(
            userId = 1L,
            items = listOf(/* ... */),
            status = OrderStatus.PENDING,
            totalPrice = Money(10000)
        )

        val saved = repository.save(order)
        val found = repository.findById(saved.id)

        assertThat(found).isNotNull
        assertThat(found!!.userId).isEqualTo(1L)
    }
}
```

### Slice Test (app-api)
```kotlin
@WebMvcTest(OrderController::class)
class OrderControllerTest {
    @Autowired
    private lateinit var mockMvc: MockMvc

    @MockkBean
    private lateinit var createOrderUseCase: CreateOrderUseCase

    @Test
    fun `주문 생성 API 성공`() {
        every { createOrderUseCase.execute(any()) } returns testOrder()

        mockMvc.perform(
            post("/api/v1/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""{"items": [{"productId": 1, "quantity": 2}]}""")
        )
            .andExpect(status().isOk)
            .andExpect(jsonPath("$.success").value(true))
    }
}
```

### API 문서 테스트 (REST Docs → OpenAPI 3)
```kotlin
// 테스트가 곧 문서. Controller에 @Tag, @Operation 등 문서 어노테이션 불필요.
@WebMvcTest(OrderController::class)
@AutoConfigureRestDocs
class OrderControllerDocsTest {
    @Autowired
    private lateinit var mockMvc: MockMvc

    @MockkBean
    private lateinit var createOrderUseCase: CreateOrderUseCase

    @Test
    fun `주문 생성 API 문서`() {
        every { createOrderUseCase.execute(any()) } returns testOrder()

        mockMvc.perform(
            post("/api/v1/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""{"items": [{"productId": 1, "quantity": 2}]}""")
        )
            .andExpect(status().isOk)
            .andDo(
                MockMvcRestDocumentationWrapper.document(
                    identifier = "order-create",
                    resourceDetails = ResourceSnippetParametersBuilder()
                        .tag("주문")
                        .summary("주문 생성")
                        .description("새로운 주문을 생성합니다"),
                    snippets = arrayOf(
                        requestFields(
                            fieldWithPath("items[].productId").description("상품 ID"),
                            fieldWithPath("items[].quantity").description("수량")
                        ),
                        responseFields(
                            fieldWithPath("success").description("성공 여부"),
                            fieldWithPath("data.id").description("주문 ID"),
                            fieldWithPath("data.status").description("주문 상태"),
                            fieldWithPath("error").description("에러 정보").optional()
                        )
                    )
                )
            )
    }
}

// OpenAPI 3 스펙 생성: ./gradlew :xxx-app-api:openapi3
// 생성된 openapi3.json으로 Swagger UI 제공
```
