---
name: spring-aop-patterns
description: Apply Spring AOP patterns for cross-cutting concerns. Covers logging, performance monitoring, exception translation, retry, audit, rate limiting, and caching aspects. Use when implementing cross-cutting concerns in Spring Boot.
---

# Spring AOP Patterns

## AOP 적용 판단 기준

| 패턴 | AOP 적용 여부 | 이유 |
|------|-------------|------|
| 로깅 | YES | 모든 서비스에 동일 패턴 |
| 성능 모니터링 | YES | 비침투적 측정 |
| 예외 변환 | YES | 계층 간 예외 매핑 |
| 재시도 | YES | 일시적 오류 복구 |
| 감사 | YES | 변경 추적 |
| Rate Limiting | YES | 요청 제한 |
| 캐싱 | MAYBE | Spring Cache 우선 |
| 트랜잭션 | NO | @Transactional 사용 |
| 인증/인가 | NO | Spring Security 사용 |
| 비즈니스 로직 | NEVER | 도메인에 직접 구현 |

## Logging Aspect

```kotlin
@Aspect
@Component
class LoggingAspect {
    @Around("@within(org.springframework.stereotype.Service)")
    fun logServiceMethods(joinPoint: ProceedingJoinPoint): Any? {
        val logger = LoggerFactory.getLogger(joinPoint.target.javaClass)
        val methodName = joinPoint.signature.name
        val args = joinPoint.args.map { sanitize(it) }

        logger.info("→ $methodName(${args.joinToString()})")
        val startTime = System.currentTimeMillis()

        return try {
            val result = joinPoint.proceed()
            val duration = System.currentTimeMillis() - startTime
            logger.info("← $methodName [${duration}ms]")
            result
        } catch (e: Exception) {
            val duration = System.currentTimeMillis() - startTime
            logger.error("✗ $methodName [${duration}ms]: ${e.message}")
            throw e
        }
    }

    private fun sanitize(arg: Any?): String = when (arg) {
        null -> "null"
        is String -> if (arg.length > 100) "${arg.take(100)}..." else arg
        is Collection<*> -> "[size=${arg.size}]"
        else -> arg.toString().take(50)
    }
}
```

## Performance Monitoring

```kotlin
@Target(AnnotationTarget.FUNCTION)
@Retention(AnnotationRetention.RUNTIME)
annotation class Timed(val value: String = "")

@Aspect
@Component
class PerformanceAspect(private val meterRegistry: MeterRegistry) {
    @Around("@annotation(timed)")
    fun measurePerformance(joinPoint: ProceedingJoinPoint, timed: Timed): Any? {
        val metricName = timed.value.ifEmpty { joinPoint.signature.name }
        val timer = Timer.start(meterRegistry)

        return try {
            joinPoint.proceed()
        } finally {
            timer.stop(Timer.builder(metricName)
                .tag("class", joinPoint.target.javaClass.simpleName)
                .tag("method", joinPoint.signature.name)
                .register(meterRegistry))
        }
    }
}
```

## Exception Translation

```kotlin
@Aspect
@Component
@Order(1)
class ExceptionTranslationAspect {
    private val logger = LoggerFactory.getLogger(javaClass)

    @Around("@within(org.springframework.stereotype.Repository)")
    fun translateRepositoryExceptions(joinPoint: ProceedingJoinPoint): Any? =
        try {
            joinPoint.proceed()
        } catch (e: DataAccessException) {
            logger.error("DB 오류: ${e.message}", e)
            throw InfrastructureException("데이터베이스 오류", e)
        }
}
```

## Retry Aspect

```kotlin
@Target(AnnotationTarget.FUNCTION)
@Retention(AnnotationRetention.RUNTIME)
annotation class Retryable(
    val maxAttempts: Int = 3,
    val backoffMs: Long = 1000,
    val retryOn: Array<KClass<out Exception>> = [Exception::class]
)

@Aspect
@Component
class RetryAspect {
    private val logger = LoggerFactory.getLogger(javaClass)

    @Around("@annotation(retryable)")
    fun retry(joinPoint: ProceedingJoinPoint, retryable: Retryable): Any? {
        var lastException: Exception? = null

        repeat(retryable.maxAttempts) { attempt ->
            try {
                return joinPoint.proceed()
            } catch (e: Exception) {
                if (retryable.retryOn.none { it.isInstance(e) }) throw e

                lastException = e
                logger.warn("재시도 ${attempt + 1}/${retryable.maxAttempts}: ${e.message}")

                if (attempt < retryable.maxAttempts - 1) {
                    Thread.sleep(retryable.backoffMs * (attempt + 1))
                }
            }
        }

        throw lastException!!
    }
}
```

## Audit Aspect

```kotlin
@Target(AnnotationTarget.FUNCTION)
@Retention(AnnotationRetention.RUNTIME)
annotation class Audited(val action: String)

@Aspect
@Component
class AuditAspect(private val auditLogger: AuditLogger) {
    @AfterReturning(
        pointcut = "@annotation(audited)",
        returning = "result"
    )
    fun audit(joinPoint: ProceedingJoinPoint, audited: Audited, result: Any?) {
        auditLogger.log(
            action = audited.action,
            actor = SecurityContextHolder.getContext().authentication?.name ?: "system",
            target = joinPoint.args.firstOrNull()?.toString() ?: "",
            result = result?.toString()?.take(200) ?: ""
        )
    }
}
```

## Aspect 순서

```kotlin
@Order(1)  // 가장 먼저 (외부)
class LoggingAspect

@Order(2)
class PerformanceAspect

@Order(3)
class RetryAspect

@Order(4)
class ExceptionTranslationAspect

@Order(5)  // 가장 나중에 (내부, 비즈니스에 가장 가까움)
class AuditAspect
```

## Pointcut 표현식 참고

```kotlin
// 특정 패키지의 모든 메서드
@Around("execution(* com.xxx.domain..*.*(..))")

// 특정 어노테이션이 붙은 클래스
@Around("@within(org.springframework.stereotype.Service)")

// 특정 어노테이션이 붙은 메서드
@Around("@annotation(com.xxx.common.annotation.Timed)")

// 조합
@Around("@within(Service) && execution(public * *(..))")
```

## Anti-Patterns

```kotlin
// BAD: AOP에서 비즈니스 로직
@Around("...")
fun checkBusinessRule(joinPoint: ProceedingJoinPoint): Any? {
    val order = joinPoint.args[0] as Order
    if (order.totalPrice > Money(1000000)) { // 비즈니스 룰!
        throw BusinessException("한도 초과")
    }
    return joinPoint.proceed()
}

// GOOD: 비즈니스 로직은 도메인에
class OrderService {
    fun validateOrderLimit(order: Order) {
        require(order.totalPrice <= Money(1000000)) { "한도 초과" }
    }
}
```
