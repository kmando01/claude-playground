---
name: spring-rest-client
description: Spring RestClient/WebClient patterns for Kotlin with resilience (Circuit Breaker, Retry, Timeout, Fallback). Use when implementing external API integrations in client-external module.
---

# Spring REST Client + Resilience 패턴

## 모듈 배치

```
client-external → RestClient 설정, 외부 API 호출, Circuit Breaker
domain          → 외부 서비스 Port 인터페이스 정의
common          → 공통 예외 (ExternalApiException)
app-api         → client-external 주입받아 사용
```

## RestClient 설정 (Spring Boot 3.2+)

### @ConfigurationProperties
```kotlin
// client-external 모듈
@ConfigurationProperties(prefix = "external-api.payment")
data class PaymentClientProperties(
    val baseUrl: String,
    val connectTimeout: Duration = Duration.ofSeconds(3),
    val readTimeout: Duration = Duration.ofSeconds(5),
    val apiKey: String = ""
)
```

### application.yml
```yaml
external-api:
  payment:
    base-url: https://api.payment.example.com
    connect-timeout: 3s
    read-timeout: 5s
    api-key: ${PAYMENT_API_KEY:}
  notification:
    base-url: https://api.notification.example.com
    connect-timeout: 2s
    read-timeout: 3s
```

### RestClient Bean 설정
```kotlin
@Configuration
class PaymentClientConfig(
    private val properties: PaymentClientProperties
) {
    @Bean
    fun paymentRestClient(): RestClient {
        val factory = SimpleClientHttpRequestFactory().apply {
            setConnectTimeout(properties.connectTimeout)
            setReadTimeout(properties.readTimeout)
        }

        return RestClient.builder()
            .baseUrl(properties.baseUrl)
            .requestFactory(factory)
            .defaultHeader(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
            .defaultHeader("X-API-Key", properties.apiKey)
            .build()
    }
}
```

## 외부 API 클라이언트 구현

### Port 정의 (domain 모듈)
```kotlin
interface PaymentGateway {
    fun requestPayment(orderId: Long, amount: Money): PaymentResult
    fun cancelPayment(paymentId: String): PaymentResult
}

data class PaymentResult(
    val paymentId: String,
    val status: PaymentStatus,
    val approvedAt: LocalDateTime?
)

enum class PaymentStatus { APPROVED, FAILED, CANCELLED }
```

### Client 구현 (client-external 모듈)
```kotlin
@Component
class PaymentClient(
    private val paymentRestClient: RestClient
) : PaymentGateway {

    override fun requestPayment(orderId: Long, amount: Money): PaymentResult {
        val request = PaymentRequest(orderId = orderId, amount = amount.value)

        val response = paymentRestClient.post()
            .uri("/v1/payments")
            .body(request)
            .retrieve()
            .onStatus(HttpStatusCode::is4xxClientError) { _, response ->
                throw ExternalApiException.BadRequest(
                    service = "payment",
                    message = "결제 요청 실패: ${response.statusCode}"
                )
            }
            .onStatus(HttpStatusCode::is5xxServerError) { _, response ->
                throw ExternalApiException.ServerError(
                    service = "payment",
                    message = "결제 서버 오류: ${response.statusCode}"
                )
            }
            .body(PaymentResponse::class.java)
            ?: throw ExternalApiException.ServerError("payment", "응답 없음")

        return response.toDomain()
    }
}
```

### 예외 정의 (common 모듈)
```kotlin
sealed class ExternalApiException(
    val service: String,
    override val message: String
) : RuntimeException(message) {
    class BadRequest(service: String, message: String) :
        ExternalApiException(service, message)
    class ServerError(service: String, message: String) :
        ExternalApiException(service, message)
    class Timeout(service: String) :
        ExternalApiException(service, "$service API 타임아웃")
    class CircuitOpen(service: String) :
        ExternalApiException(service, "$service 서비스 일시 중단")
}
```

## Resilience4j 패턴

### 의존성 (build.gradle.kts)
```kotlin
// client-external 모듈
dependencies {
    implementation("io.github.resilience4j:resilience4j-spring-boot3")
    implementation("io.github.resilience4j:resilience4j-kotlin")
    implementation("io.github.resilience4j:resilience4j-micrometer") // CB 상태 Prometheus 노출 (필수)
}
```

> **MUST**: `resilience4j-micrometer`는 CB 있는 서비스에 처음부터 포함한다.
> 없으면 CB가 OPEN/CLOSED인지 Prometheus에서 볼 수 없어 장애 시 추측으로만 진단하게 된다.
> `resilience4j_circuitbreaker_state`, `resilience4j_circuitbreaker_failure_rate` 메트릭이 노출된다.

### application.yml
```yaml
resilience4j:
  circuitbreaker:
    instances:
      payment:
        sliding-window-size: 10
        failure-rate-threshold: 50
        wait-duration-in-open-state: 30s
        permitted-number-of-calls-in-half-open-state: 3
        slow-call-duration-threshold: 3s
        slow-call-rate-threshold: 80
      notification:
        sliding-window-size: 5
        failure-rate-threshold: 60
        wait-duration-in-open-state: 60s

  retry:
    instances:
      payment:
        max-attempts: 3
        wait-duration: 500ms
        retry-exceptions:
          - java.io.IOException
          - org.springframework.web.client.ResourceAccessException
        ignore-exceptions:
          - com.example.common.exception.ExternalApiException$BadRequest
      notification:
        max-attempts: 2
        wait-duration: 300ms

  timelimiter:
    instances:
      payment:
        timeout-duration: 5s
      notification:
        timeout-duration: 3s
```

### Circuit Breaker + Retry 적용
```kotlin
@Component
class PaymentClient(
    private val paymentRestClient: RestClient
) : PaymentGateway {

    @CircuitBreaker(name = "payment", fallbackMethod = "paymentFallback")
    @Retry(name = "payment")
    override fun requestPayment(orderId: Long, amount: Money): PaymentResult {
        val response = paymentRestClient.post()
            .uri("/v1/payments")
            .body(PaymentRequest(orderId, amount.value))
            .retrieve()
            .body(PaymentResponse::class.java)
            ?: throw ExternalApiException.ServerError("payment", "응답 없음")

        return response.toDomain()
    }

    // Fallback: Circuit Breaker OPEN 또는 모든 재시도 실패 시
    private fun paymentFallback(
        orderId: Long,
        amount: Money,
        ex: Exception
    ): PaymentResult {
        logger.warn(ex) { "결제 API 호출 실패, fallback 실행: orderId=$orderId" }

        return when (ex) {
            is CallNotPermittedException ->
                throw ExternalApiException.CircuitOpen("payment")
            else ->
                throw ExternalApiException.ServerError("payment", "결제 처리 실패: ${ex.message}")
        }
    }
}
```

## 어노테이션 적용 순서

> 공식 문서: https://resilience4j.readme.io/docs/getting-started-3#aspect-order

Resilience4j 어노테이션 적용 순서 (바깥 → 안쪽):

```
Retry → CircuitBreaker → RateLimiter → Bulkhead → TimeLimiter
```

실행 순서 (안쪽 → 바깥쪽):
```
실제 호출 → TimeLimiter(타임아웃) → CircuitBreaker(기록) → Retry(재시도)
```

```kotlin
@Retry(name = "payment")                    // 3. 실패 시 재시도
@CircuitBreaker(name = "payment")           // 2. 실패율 기록
@TimeLimiter(name = "payment")              // 1. 타임아웃 체크
fun requestPayment(...): PaymentResult { ... }
```

## 프로그래매틱 데코레이터 순서 (MUST)

> 공식 문서: https://resilience4j.readme.io/docs/getting-started-3#decorating-and-executing-a-functional-interface

**MUST**: `Retry.decorateCheckedSupplier` 가 바깥, `CircuitBreaker.decorateCheckedSupplier` 가 안쪽

```kotlin
// GOOD: Retry(CB(f)) — 공식 권장 순서
val response = Retry.decorateCheckedSupplier(mockSendApiRetry) {
    CircuitBreaker.decorateCheckedSupplier(mockSendApiCircuitBreaker) {
        callApi(request)
    }.get()
}.get()

// BAD: CB(Retry(f)) — NEVER 사용
// - CB가 실패를 늦게 감지 (모든 재시도 소진 후에야 failure 1건 기록)
// - CB OPEN 시에도 내부 Retry가 callApi를 계속 호출 → retry storm 방지 효과 없음
val response = CircuitBreaker.decorateCheckedSupplier(cb) {
    Retry.decorateCheckedSupplier(retry) {
        callApi(request)
    }.get()
}.get()
```

**이유**: Retry가 바깥이어야 CB가 각 시도의 실패를 즉시 기록하고, CB OPEN 시 `CallNotPermittedException`이 Retry로 전파되어 재시도가 즉시 중단됨.

## 요청/응답 DTO (client-external 내부)

```kotlin
// 외부 API 전용 DTO (client-external 모듈 내부에만 존재)
// domain과 공유하지 않음!

data class PaymentRequest(
    val orderId: Long,
    val amount: BigDecimal
)

data class PaymentResponse(
    val id: String,
    val status: String,
    @JsonFormat(pattern = "yyyy-MM-dd'T'HH:mm:ss")
    val approvedAt: LocalDateTime?
) {
    fun toDomain() = PaymentResult(
        paymentId = id,
        status = PaymentStatus.valueOf(status),
        approvedAt = approvedAt
    )
}
```

## 로깅 인터셉터

```kotlin
@Component
class RestClientLoggingInterceptor : ClientHttpRequestInterceptor {
    private val logger = KotlinLogging.logger {}

    override fun intercept(
        request: HttpRequest,
        body: ByteArray,
        execution: ClientHttpRequestExecution
    ): ClientHttpResponse {
        logger.debug { "[→] ${request.method} ${request.uri}" }
        val start = System.currentTimeMillis()

        val response = execution.execute(request, body)

        val elapsed = System.currentTimeMillis() - start
        logger.debug { "[←] ${response.statusCode} ${request.uri} (${elapsed}ms)" }

        return response
    }
}

// RestClient 빌더에 추가
RestClient.builder()
    .requestInterceptor(loggingInterceptor)
    .build()
```

## 클라이언트 안티패턴

```kotlin
// BAD: client-external에서 domain 모듈 직접 의존
class PaymentClient(
    private val orderRepository: OrderRepository  // client-external → domain 직접 참조!
)

// GOOD: 필요한 값만 파라미터로 받기
fun requestPayment(orderId: Long, amount: Money): PaymentResult

// BAD: 외부 API 응답 DTO를 domain까지 전파
fun requestPayment(...): PaymentResponse  // 외부 DTO 그대로 반환

// GOOD: domain 객체로 변환 후 반환
fun requestPayment(...): PaymentResult  // domain DTO 반환

// BAD: Retry 없이 외부 API 호출
fun callApi() {
    restClient.get().uri("/api").retrieve().body(...)
}

// GOOD: Resilience4j로 보호
@CircuitBreaker(name = "service")
@Retry(name = "service")
fun callApi() { ... }

// BAD: 모든 예외에 대해 재시도
// 4xx (클라이언트 오류)는 재시도해도 결과가 같음
resilience4j.retry.instances.payment:
  retry-exceptions:
    - java.lang.Exception  # 너무 넓음!

// GOOD: 일시적 오류만 재시도
resilience4j.retry.instances.payment:
  retry-exceptions:
    - java.io.IOException
    - org.springframework.web.client.ResourceAccessException
  ignore-exceptions:
    - com.example.common.exception.ExternalApiException$BadRequest
```

## 테스트 (WireMock)

```kotlin
@SpringBootTest
@AutoConfigureWireMock(port = 0)
class PaymentClientTest {

    @Autowired
    private lateinit var paymentClient: PaymentClient

    @Test
    fun `결제 요청 성공`() {
        stubFor(
            post(urlEqualTo("/v1/payments"))
                .willReturn(
                    aResponse()
                        .withStatus(200)
                        .withHeader("Content-Type", "application/json")
                        .withBody("""
                            {
                                "id": "pay_123",
                                "status": "APPROVED",
                                "approvedAt": "2024-01-15T10:30:00"
                            }
                        """)
                )
        )

        val result = paymentClient.requestPayment(1L, Money(10000))

        assertThat(result.paymentId).isEqualTo("pay_123")
        assertThat(result.status).isEqualTo(PaymentStatus.APPROVED)
    }

    @Test
    fun `서버 오류 시 재시도 후 실패`() {
        stubFor(
            post(urlEqualTo("/v1/payments"))
                .willReturn(aResponse().withStatus(500))
        )

        assertThatThrownBy {
            paymentClient.requestPayment(1L, Money(10000))
        }.isInstanceOf(ExternalApiException.ServerError::class.java)

        // 3회 재시도 확인
        verify(3, postRequestedFor(urlEqualTo("/v1/payments")))
    }

    @Test
    fun `타임아웃 시 CircuitBreaker 동작 확인`() {
        stubFor(
            post(urlEqualTo("/v1/payments"))
                .willReturn(
                    aResponse()
                        .withStatus(200)
                        .withFixedDelay(6000)  // 타임아웃 초과
                )
        )

        assertThatThrownBy {
            paymentClient.requestPayment(1L, Money(10000))
        }.isInstanceOf(ExternalApiException::class.java)
    }
}
```
