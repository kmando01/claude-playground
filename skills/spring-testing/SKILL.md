---
name: spring-testing
description: Spring Boot + Kotlin testing patterns for multi-module projects. Use when writing tests, setting up test infrastructure, or debugging test failures. Covers MockK, Testcontainers, @WebMvcTest, REST Docs, test fixtures.
---

# Spring Boot 테스트 패턴

## Step 0: 프로젝트 컨텍스트 로드

`.claude/project-context.md`의 `## [testing]` 섹션이 있으면 읽는다.
- Testcontainers 구성 (어떤 컨테이너, 어떤 이미지)
- 테스트 데이터 팩토리 위치 및 패턴
- 프로젝트 특화 테스트 규칙
- 없으면 범용 패턴으로 진행.

---

## 모듈별 테스트 전략

```
domain     → 단위 테스트 (MockK, 프레임워크 의존 없음)
infra      → 통합 테스트 (Testcontainers, @DataJpaTest)
app-api    → 슬라이스 테스트 (@WebMvcTest) + REST Docs
client-ext → WireMock (외부 API 모킹)
```

## 테스트 픽스처 패턴

### Object Mother (도메인 테스트 데이터 팩토리)
```kotlin
// domain 모듈: test/.../fixture/OrderFixture.kt
object OrderFixture {
    fun pending(
        id: Long = 0,
        userId: Long = 1L,
        totalPrice: Money = Money(10000)
    ) = Order(
        id = id,
        userId = userId,
        items = listOf(OrderItemFixture.default()),
        status = OrderStatus.PENDING,
        totalPrice = totalPrice
    )

    fun confirmed(id: Long = 1L) = pending(id = id).confirm()
}

object OrderItemFixture {
    fun default(
        productId: Long = 1L,
        price: Money = Money(5000),
        quantity: Int = 2
    ) = OrderItem(
        productId = productId,
        productName = "테스트 상품",
        price = price,
        quantity = quantity
    )
}
```

### 사용
```kotlin
// 기본값으로 간결하게
val order = OrderFixture.pending()

// 필요한 값만 오버라이드
val order = OrderFixture.pending(userId = 99L, totalPrice = Money(50000))
```

## MockK 패턴

### 기본 Mock
```kotlin
class OrderServiceTest {
    private val orderRepository = mockk<OrderRepository>()
    private val sut = OrderService(orderRepository)

    @Test
    fun `주문 생성 시 PENDING 상태여야 한다`() {
        // Arrange
        every { orderRepository.save(any()) } answers { firstArg() }

        // Act
        val result = sut.execute(command)

        // Assert
        assertThat(result.status).isEqualTo(OrderStatus.PENDING)
        verify(exactly = 1) { orderRepository.save(any()) }
    }
}
```

### Slot으로 인자 캡처
```kotlin
@Test
fun `저장되는 주문의 총 가격이 정확해야 한다`() {
    val slot = slot<Order>()
    every { orderRepository.save(capture(slot)) } answers { firstArg() }

    sut.execute(command)

    assertThat(slot.captured.totalPrice).isEqualTo(Money(20000))
}
```

### relaxed Mock (반환값 자동 생성)
```kotlin
// 모든 메서드가 기본값 반환 (0, "", false, emptyList 등)
private val repository = mockk<OrderRepository>(relaxed = true)

// 특정 메서드만 relaxed
private val repository = mockk<OrderRepository> {
    every { findById(any()) } returns null  // 명시
}
```

### verify 패턴
```kotlin
// 호출 횟수
verify(exactly = 1) { repository.save(any()) }
verify(atLeast = 1) { repository.findById(any()) }

// 호출 안 됨
verify(exactly = 0) { repository.delete(any()) }

// 호출 순서
verifyOrder {
    repository.findById(1L)
    repository.save(any())
}
```

## Testcontainers 패턴

### 추상 통합 테스트 클래스
```kotlin
// infra 모듈: test/.../support/IntegrationTestSupport.kt
@SpringBootTest
@Testcontainers
abstract class IntegrationTestSupport {
    companion object {
        @Container
        @JvmStatic
        val mysql = MySQLContainer("mysql:8.0").apply {
            withDatabaseName("test_db")
            withUsername("test")
            withPassword("test")
            withCommand("--character-set-server=utf8mb4", "--collation-server=utf8mb4_unicode_ci")
        }

        @JvmStatic
        @DynamicPropertySource
        fun properties(registry: DynamicPropertyRegistry) {
            registry.add("spring.datasource.url") { mysql.jdbcUrl }
            registry.add("spring.datasource.username") { mysql.username }
            registry.add("spring.datasource.password") { mysql.password }
        }
    }

    @Autowired
    protected lateinit var entityManager: EntityManager

    @AfterEach
    fun cleanup() {
        entityManager.clear()
    }
}
```

### Redis Testcontainer
```kotlin
companion object {
    @Container
    @JvmStatic
    val redis = GenericContainer("redis:7-alpine")
        .withExposedPorts(6379)

    @JvmStatic
    @DynamicPropertySource
    fun redisProperties(registry: DynamicPropertyRegistry) {
        registry.add("spring.data.redis.host") { redis.host }
        registry.add("spring.data.redis.port") { redis.firstMappedPort }
    }
}
```

### @DataJpaTest (JPA 슬라이스)
```kotlin
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(OrderRepositoryImpl::class)  // 커스텀 Repository 구현체
@Testcontainers
class OrderRepositoryImplTest {
    companion object {
        @Container
        @JvmStatic
        val mysql = MySQLContainer("mysql:8.0")

        @JvmStatic
        @DynamicPropertySource
        fun properties(registry: DynamicPropertyRegistry) {
            registry.add("spring.datasource.url") { mysql.jdbcUrl }
            registry.add("spring.datasource.username") { mysql.username }
            registry.add("spring.datasource.password") { mysql.password }
        }
    }

    @Autowired
    private lateinit var sut: OrderRepositoryImpl

    @Test
    fun `주문을 저장하고 조회할 수 있다`() {
        val order = OrderFixture.pending()
        val saved = sut.save(order)

        val found = sut.findById(saved.id)

        assertThat(found).isNotNull
        assertThat(found!!.userId).isEqualTo(order.userId)
        assertThat(found.status).isEqualTo(OrderStatus.PENDING)
    }
}
```

## @WebMvcTest 패턴

### Controller 슬라이스 테스트
```kotlin
@WebMvcTest(OrderController::class)
class OrderControllerTest {
    @Autowired
    private lateinit var mockMvc: MockMvc

    @Autowired
    private lateinit var objectMapper: ObjectMapper

    @MockkBean
    private lateinit var createOrderUseCase: CreateOrderUseCase

    @Test
    fun `주문 생성 성공`() {
        val order = OrderFixture.pending(id = 1L)
        every { createOrderUseCase.execute(any()) } returns order

        mockMvc.perform(
            post("/api/v1/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(
                    CreateOrderRequest(items = listOf(
                        OrderItemRequest(productId = 1, quantity = 2)
                    ))
                ))
        )
            .andExpect(status().isOk)
            .andExpect(jsonPath("$.success").value(true))
            .andExpect(jsonPath("$.data.id").value(1))
            .andExpect(jsonPath("$.data.status").value("PENDING"))
    }

    @Test
    fun `입력 검증 실패 시 400 반환`() {
        mockMvc.perform(
            post("/api/v1/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""{"items": []}""")
        )
            .andExpect(status().isBadRequest)
            .andExpect(jsonPath("$.success").value(false))
            .andExpect(jsonPath("$.error.code").value("VALIDATION_ERROR"))
    }

    @Test
    fun `존재하지 않는 주문 조회 시 404 반환`() {
        every { getOrderUseCase.execute(999L) } throws
            DomainException.NotFound("Order", 999L)

        mockMvc.perform(get("/api/v1/orders/999"))
            .andExpect(status().isNotFound)
            .andExpect(jsonPath("$.error.code").value("NOT_FOUND"))
    }
}
```

## REST Docs 테스트 패턴

```kotlin
@WebMvcTest(OrderController::class)
@AutoConfigureRestDocs
class OrderControllerDocsTest {
    @Autowired
    private lateinit var mockMvc: MockMvc

    @MockkBean
    private lateinit var createOrderUseCase: CreateOrderUseCase

    @Test
    fun `주문 생성 API 문서`() {
        every { createOrderUseCase.execute(any()) } returns OrderFixture.pending(id = 1L)

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
                            fieldWithPath("data.totalPrice").description("총 금액"),
                            fieldWithPath("error").description("에러 정보").optional()
                        )
                    )
                )
            )
    }
}
```

## 테스트 안티패턴

```kotlin
// BAD: 테스트 간 상태 공유
companion object {
    var savedOrderId: Long = 0  // 테스트 순서 의존!
}

// GOOD: 각 테스트가 독립적
@Test
fun `테스트`() {
    val saved = repository.save(OrderFixture.pending())
    // saved.id 사용
}

// BAD: 불필요한 검증
verify { repository.findById(any()) }  // 내부 구현 검증
verify { logger.info(any()) }           // 로깅 검증

// GOOD: 행위/결과 검증
assertThat(result.status).isEqualTo(OrderStatus.CONFIRMED)

// BAD: 매직 넘버
assertThat(result.totalPrice).isEqualTo(Money(20000))

// GOOD: 계산 과정이 보이는 검증
val expectedPrice = Money(5000) * 2 + Money(3000) * 1
assertThat(result.totalPrice).isEqualTo(expectedPrice)
```
