---
name: observability-reference
description: 모니터링 & 관측성 레퍼런스. Actuator 설정, Logback XML, MDC Filter, 커스텀 Metrics, Health Check, 분산 추적 설정 포함. 모니터링/로깅 구현 시 참조.
---

# 모니터링 & 관측성 레퍼런스

## 의존성

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("io.micrometer:micrometer-registry-prometheus")
    // 분산 추적 (선택)
    implementation("io.micrometer:micrometer-tracing-bridge-brave")
    implementation("io.zipkin.reporter2:zipkin-reporter-brave")
}
```

## Actuator 설정

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health, info, metrics, prometheus
  endpoint:
    health:
      show-details: when_authorized
      probes:
        enabled: true
  metrics:
    tags:
      application: ${spring.application.name}
```

## 커스텀 Health Indicator

```kotlin
@Component
class ExternalApiHealthIndicator(
    private val externalClient: ExternalApiClient
) : HealthIndicator {
    override fun health(): Health =
        try {
            externalClient.ping()
            Health.up().withDetail("externalApi", "reachable").build()
        } catch (e: Exception) {
            Health.down(e).withDetail("externalApi", "unreachable").build()
        }
}
```

## 커스텀 Metrics

```kotlin
@Component
class OrderMetrics(private val meterRegistry: MeterRegistry) {
    private val orderCounter = Counter.builder("orders.created")
        .description("생성된 주문 수")
        .register(meterRegistry)

    private val orderTimer = Timer.builder("orders.processing.time")
        .description("주문 처리 시간")
        .register(meterRegistry)

    fun recordOrderCreated() = orderCounter.increment()

    fun <T> recordProcessingTime(block: () -> T): T =
        orderTimer.recordCallable(block)!!

    fun registerPendingOrdersGauge(supplier: () -> Long) {
        Gauge.builder("orders.pending", supplier)
            .description("대기 중인 주문 수")
            .register(meterRegistry)
    }
}
```

## Logback 설정 (JSON)

```xml
<!-- logback-spring.xml -->
<configuration>
    <springProfile name="local">
        <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
            <encoder>
                <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n</pattern>
            </encoder>
        </appender>
        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>

    <springProfile name="!local">
        <appender name="JSON" class="ch.qos.logback.core.ConsoleAppender">
            <encoder class="net.logstash.logback.encoder.LogstashEncoder">
                <includeMdcKeyName>traceId</includeMdcKeyName>
                <includeMdcKeyName>userId</includeMdcKeyName>
                <includeMdcKeyName>requestId</includeMdcKeyName>
            </encoder>
        </appender>
        <root level="INFO">
            <appender-ref ref="JSON"/>
        </root>
    </springProfile>
</configuration>
```

## MDC Filter

```kotlin
@Component
class MdcFilter : OncePerRequestFilter() {
    override fun doFilterInternal(
        request: HttpServletRequest,
        response: HttpServletResponse,
        filterChain: FilterChain
    ) {
        try {
            MDC.put("requestId", UUID.randomUUID().toString().take(8))
            MDC.put("method", request.method)
            MDC.put("uri", request.requestURI)
            SecurityContextHolder.getContext().authentication?.name?.let {
                MDC.put("userId", it)
            }
            filterChain.doFilter(request, response)
        } finally {
            MDC.clear()
        }
    }
}
```

## 로그 레벨 가이드

| 레벨 | 용도 | 예시 |
|------|------|------|
| **ERROR** | 즉시 대응 필요 | DB 연결 실패, 결제 오류 |
| **WARN** | 모니터링 필요 | 재시도 발생, 느린 쿼리 |
| **INFO** | 비즈니스 이벤트 | 주문 생성, 결제 완료 |
| **DEBUG** | 개발/디버깅 | 쿼리 파라미터, 중간값 |

```kotlin
// Good
logger.info("주문 생성 완료: orderId={}, userId={}, amount={}", order.id, order.userId, order.totalPrice)
logger.warn("외부 API 재시도: attempt={}, endpoint={}", attempt, endpoint)
logger.error("결제 처리 실패: orderId={}, error={}", orderId, e.message, e)

// Bad
logger.info("done")
logger.error("something went wrong")
```

## 분산 추적

```yaml
management:
  tracing:
    sampling:
      probability: 1.0  # 개발: 100%, 프로덕션: 0.1
  zipkin:
    tracing:
      endpoint: http://localhost:9411/api/v2/spans
```

```yaml
# docker-compose.yml
zipkin:
  image: openzipkin/zipkin
  container_name: xxx-zipkin
  ports:
    - "9411:9411"
```

## 알림 기준

| 지표 | 임계값 | 심각도 |
|------|--------|--------|
| 에러율 (5xx) | > 1% | CRITICAL |
| 응답 시간 (p99) | > 3s | WARNING |
| Health Check 실패 | 연속 3회 | CRITICAL |
| 디스크 사용률 | > 80% | WARNING |
| DB 커넥션 풀 고갈 | > 90% | CRITICAL |
