---
name: testing-reference
description: 테스트 전략 레퍼런스. 목적 기반 분류(도메인 정책/유스케이스/동시성 계약/직렬화), 테스트 대역 선택 기준(Fake>Mock), FIRST 원칙, IntegrationTestSupport·TRUNCATE 패턴, Context Caching, 안티패턴 포함. 테스트 작성·설계·리뷰 시 참조.
---

# 테스트 전략 레퍼런스

> Spring 도구 코드(MockK, Testcontainers, @WebMvcTest)는 `spring-testing` 스킬 참조.

---

## 1. 왜 테스트를 작성하는가

테스트의 목적이 흔들리면 작성 비용을 정당화하기 어렵다. 네 가지 가치로 먼저 정한다.

| 가치 | 설명 |
|------|------|
| **회귀 안전망** | 리팩토링·어댑터 교체 시 기존 동작이 깨지지 않음을 보장 |
| **설계 피드백** | 테스트가 작성하기 어렵다 = 결합도가 높거나 책임이 섞인 신호 |
| **살아있는 문서** | 도메인 정책을 코드로 박제. 신규 합류자가 의도를 파악하는 통로 |
| **배포 자신감** | "지금 배포해도 되나?"에 수 분 안에 답할 수 있는 상태 |

---

## 2. FIRST 원칙

모든 테스트가 만족해야 하는 기본 조건.

- **Fast** — 빠르게 동작해서 자주 돌릴 수 있다
- **Independent** — 다른 테스트의 실행 순서·결과에 의존하지 않는다
- **Repeatable** — 어느 환경에서든 반복 가능하다
- **Self-Validating** — 테스트 스스로 성공/실패를 결정한다 (콘솔 눈으로 보지 않는다)
- **Timely** — 프로덕션 코드 작성 직전에 작성한다

---

## 3. 밀폐성 vs 충실성

이 둘은 상충한다.

- **충실성(Fidelity)** — 실제 운영 환경에 얼마나 가까운가
- **밀폐성(Hermetic)** — 외부 환경에 영향받지 않고 결정적으로 동작하는가

실제 외부 API를 호출하면 충실성은 높지만 비결정적이고 느리다. 모킹하면 밀폐성은 높지만 실제와 어긋날 수 있다. **시스템 단위로 균형점을 정해야 한다.** 동시성 계약처럼 충실성이 중요한 곳은 Testcontainers까지 띄우고, 빠른 피드백이 중요한 도메인 정책은 밀폐성을 높인다.

---

## 4. 목적 기반 분류

"단위/통합"이 아니라 **무엇을 검증하는가**로 먼저 분류한다. 목적이 안 정해진 테스트는 깨졌을 때 무엇을 봐야 하는지 모호하다.

### (a) 도메인 정책 테스트

- **목적**: 도메인 객체 안의 비즈니스 규칙이 올바른가
- **범위**: 순수 Kotlin 객체 — Spring 컨텍스트 없음
- **도구**: JUnit5 + AssertJ + `@ParameterizedTest`
- **개수**: 도메인 규칙 수만큼 (가장 많이 작성됨)
- **실행 시간**: 수십ms

```kotlin
@ParameterizedTest
@ValueSource(ints = [50_000, 50_001, 100_000])
fun `주문 금액이 50,000원 이상이면 무료 배송이 적용된다`(amount: Int) {
    val order = OrderFixture.aDefaultOrder().withAmount(amount).build()
    assertThat(order.shippingFee()).isEqualTo(Money.ZERO)
}
```

### (b) 유스케이스 테스트 (Application Service)

- **목적**: 서비스가 포트를 올바르게 조립하고 예외를 전파하는가
- **범위**: Service — 협력자(Repository, Port)는 Mock 또는 Fake
- **기준**: 협력자(Mock)가 3개 이상이면 책임 분리 검토

### (c) 동시성 계약 테스트

- **목적**: 어댑터 구현체가 동시성 계약(ADR-0001)을 만족하는가
- **도구**: Testcontainers + CountDownLatch
- **방식**: 추상 계약 클래스에 여러 구현체가 상속

### (d) 직렬화 테스트

- **목적**: API 응답·캐시·이벤트 페이로드의 호환성 유지
- **방식**: JSON 라운드트립 + 필드명 계약

```kotlin
@Test
fun `JSON 필드명 계약`() {
    val jsonMap = objectMapper.readValue<Map<String, Any>>(
        objectMapper.writeValueAsString(NotificationMessage(...)))
    assertThat(jsonMap).containsOnlyKeys("id", "requesterId", "channel", ...)
}
```

### (e) 인수/통합 테스트

- **목적**: 핵심 사용자 여정이 DB까지 포함해 의도대로 동작하는가
- **범위**: Controller → Service → Port → Testcontainers DB
- **개수**: 도메인당 5~10개 시나리오 위주
- **ROI**: 가장 높음 — 여러 계층을 동시에 덮는다

### (f) Presentation 슬라이스 테스트

- **목적**: 직렬화, 입력 검증, 상태 코드, REST Docs
- **도구**: `@WebMvcTest` + Service는 `@MockBean`
- **주의**: 비즈니스 로직은 여기서 검증하지 않는다

---

## 5. 테스트 코드 작성 규칙

### 구조: Given-When-Then

```kotlin
@Test
fun `잔여 수량이 0이면 쿠폰 발급 전략이 SoldOut을 반환한다`() {
    // given
    val event = CouponFixtures.openEvent(totalQuantity = 0)

    // when
    val result = strategy.issue(event, userId = 1L)

    // then
    assertThat(result).isEqualTo(IssuanceResult.SoldOut)
}
```

### 핵심 규칙

1. **`@DisplayName`은 도메인 용어로** — "정상 케이스", "성공한다", "test_calculate"는 금지
   - ✗ `fun test_freeShipping()`
   - ✓ `fun 주문 금액이 50000원 이상이면 무료 배송이 적용된다()`
2. **테스트 안에 분기문·반복문 금지** — 케이스 확장은 `@ParameterizedTest`로
3. **하나의 테스트 = 하나의 주제** — `@DisplayName`을 한 문장으로 쓸 수 있어야 한다
4. **시간 의존 제거** — `LocalDateTime.now()` 직접 호출 대신 고정 시간 또는 `Clock` 주입
5. **private 메서드를 직접 테스트하지 않는다** — public으로 뺄 신호일 수 있다

### 네이밍

```
ClassName: {대상클래스}Test.kt
Method: `{조건}이면/이/가 {결과}를/을/다`  (한국어 권장)
         `should {result} when {condition}`  (영어 가능)
```

---

## 6. 테스트 더블 선택 기준

```
Fake > Stub > Mock
```

| 상황 | 선택 | 이유 |
|------|------|------|
| 외부 서비스 (발송 API, 외부 연동) | **Fake** | 동작하는 구현체로 실제 시나리오 재현 |
| 내부 인프라 (DB, Redis, Kafka) | **Testcontainers** | 인프라 호환성 검증 |
| 외부 HTTP 호출 | **WireMock** | 결정적 응답 제어 |
| Service 협력자 격리 | **MockK** | 최후의 수단 |

**Mock이 3개를 넘으면**: 책임이 섞여있을 가능성. 리팩토링 검토.

### Fake 패턴

```kotlin
class FakeNotificationSender : NotificationSender {
    private val callCount = AtomicInteger(0)
    @Volatile var failUntilAttempt: Int = Int.MAX_VALUE

    override fun send(notification: Notification): SendResult {
        val attempt = callCount.incrementAndGet()
        return if (attempt >= failUntilAttempt) SendResult(success = true)
        else SendResult(success = false, failReason = "Simulated failure")
    }

    fun reset() { callCount.set(0); failUntilAttempt = Int.MAX_VALUE }
}
```

---

## 7. 통합 테스트 인프라

### H2 사용 금지

H2와 운영 MySQL의 SQL 문법 차이는 Native Query, JSON 컬럼, Flyway migration에서 거짓 통과를 만든다. **Testcontainers로 실제 MySQL을 쓴다.**

### IntegrationTestSupport

Spring Context 재생성은 빌드 시간의 주 원인이다. 모든 통합 테스트가 단일 상위 클래스를 상속하도록 한다. `@MockBean`이 필요한 테스트와 불필요한 테스트는 클래스를 나눠야 컨텍스트 분리를 방지할 수 있다.

```kotlin
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
@Testcontainers
abstract class IntegrationTestSupport {

    companion object {
        @Container @JvmStatic
        val mysql = MySQLContainer<Nothing>("mysql:8.0").apply { withReuse(true) }

        @Container @JvmStatic
        val redis: GenericContainer<*> = GenericContainer<Nothing>("redis:7-alpine")
            .withExposedPorts(6379)

        @DynamicPropertySource @JvmStatic
        fun props(registry: DynamicPropertyRegistry) {
            registry.add("spring.datasource.url", mysql::getJdbcUrl)
            registry.add("spring.datasource.username", mysql::getUsername)
            registry.add("spring.datasource.password", mysql::getPassword)
            registry.add("spring.data.redis.host", redis::getHost)
            registry.add("spring.data.redis.port") { redis.getMappedPort(6379) }
        }
    }

    @Autowired protected lateinit var mockMvc: MockMvc
    @Autowired protected lateinit var dataInitializer: DataInitializer

    @AfterEach
    fun cleanup() = dataInitializer.execute()
}
```

### DB 정리: TRUNCATE 전략

`@Transactional` 롤백은 비동기·이벤트 코드에서 거짓 통과를 만든다. 인수 테스트에는 TRUNCATE를 쓴다.

| 전략 | 사용 시점 |
|------|----------|
| `@Transactional` 롤백 | 단위/슬라이스 테스트 |
| **TRUNCATE** | 인수 테스트 (Kafka Consumer, 비동기 포함) |

```kotlin
@Component
@Profile("test")
class DataInitializer(private val em: EntityManager) {
    private val tableNames: List<String> by lazy {
        em.createNativeQuery("SHOW TABLES").resultList.map { it.toString() }
    }

    fun execute() {
        em.createNativeQuery("SET FOREIGN_KEY_CHECKS = 0").executeUpdate()
        tableNames.forEach { em.createNativeQuery("TRUNCATE TABLE `$it`").executeUpdate() }
        em.createNativeQuery("SET FOREIGN_KEY_CHECKS = 1").executeUpdate()
    }
}
```

---

## 8. Fixture 전략

테스트마다 도메인 객체를 다르게 직접 생성하면 변경 비용이 폭증한다. Object Mother 패턴으로 공유한다.

```kotlin
// coupon-core/testFixtures — 모든 모듈이 재사용
object CouponFixtures {
    fun openEvent(id: Long = 1L, totalQuantity: Int = 100) = Event(...)
    fun scheduledEvent(id: Long = 1L) = openEvent(id).copy(status = SCHEDULED, ...)
    fun soldOutEvent(id: Long = 1L) = openEvent(id).copy(status = SOLD_OUT, ...)
}
```

- **기본값을 의미있게** — `openEvent()`만으로 바로 쓸 수 있어야 한다
- **케이스별 헬퍼** — `almostSoldOutEvent()`, `expiredEvent()` 등 시나리오를 이름으로 표현
- **testFixtures 모듈** — Gradle `java-test-fixtures` 플러그인으로 모듈 간 공유

---

## 9. 안티패턴

| 안티패턴 | 왜 나쁜가 | 대신 |
|---------|----------|------|
| H2로 통합 테스트 | 운영 DB와 SQL 호환성 차이 → 거짓 양성 | Testcontainers |
| `@Transactional` 롤백을 인수 테스트에 | 비동기/이벤트 코드의 거짓 통과 | TRUNCATE |
| Mock 남발 (4개+) | 프로덕션 구조 박제 → 리팩토링 저항 | Fake 객체, 책임 분리 |
| 테스트 안에 if/for | 테스트의 테스트가 필요해짐 | `@ParameterizedTest` |
| `@DisplayName`에 "성공한다", "정상 케이스" | 실패 시 무엇이 깨졌는지 알 수 없음 | 도메인 용어로 명시 |
| 테스트 간 데이터 공유 | 실행 순서 의존 → 디버깅 지옥 | `@AfterEach` TRUNCATE |
| 외부 API 실 호출 | 비결정적, 비용 발생 | WireMock, Fake |
| 테스트가 5분 넘는데 방치 | 곧 아무도 안 돌리는 죽은 자산 | Context Caching, 병렬 실행 |

---

## 10. 체크리스트

```
새 기능 구현 시:
□ 도메인 규칙 추가 → 도메인 정책 테스트 (허용 케이스 + 불가 케이스)
□ Service 로직 추가 → 유스케이스 테스트 (정상 흐름 + 예외 흐름)
□ 모듈 간 전달 DTO 변경 → 직렬화 테스트 (라운드트립 + 필드명)
□ 새 어댑터 추가 → 동시성 계약 테스트 상속

테스트 코드 리뷰 시:
□ @DisplayName이 도메인 용어로 작성됐는가?
□ 다른 테스트의 실행 순서에 의존하지 않는가?
□ Mock이 3개를 넘지 않는가?
□ 시간/랜덤 의존이 Clock/IdGenerator로 주입됐는가?
□ 통합 테스트라면 IntegrationTestSupport를 상속하는가?
□ 단위 테스트 실행 시간이 500ms 이하인가?
```

