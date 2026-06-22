---
name: redis-operations
description: Redis 운영 패턴 레퍼런스 (캐시 외). RedisTemplate 직접 사용, SET NX 중복 체크, 분산 락(Redisson), Rate Limiting, 키 네이밍 컨벤션, TTL 전략, 모니터링 포함. 비캐시 Redis 사용 시 참조.
---

# Redis Operations (Non-Cache)

## 모듈 배치
- **infra**: RedisConfig, RedisTemplate 빈, Redis 기반 구현체
- **domain**: Port 인터페이스 정의 (Redis 의존 없음)

## 의존성 (libs.versions.toml)
```toml
[libraries]
spring-data-redis = { module = "org.springframework.boot:spring-boot-starter-data-redis" }
redisson = { module = "org.redisson:redisson-spring-boot-starter", version = "3.27.0" }
```

## RedisConfig
```kotlin
@Configuration
@EnableConfigurationProperties(RedisProperties::class)
class RedisConfig(
    private val redisProperties: RedisProperties,
) {
    @Bean
    fun redisConnectionFactory(): RedisConnectionFactory {
        return LettuceConnectionFactory(redisProperties.host, redisProperties.port)
    }

    @Bean
    fun redisTemplate(connectionFactory: RedisConnectionFactory): RedisTemplate<String, String> {
        return RedisTemplate<String, String>().apply {
            this.connectionFactory = connectionFactory
            keySerializer = StringRedisSerializer()
            valueSerializer = StringRedisSerializer()
            hashKeySerializer = StringRedisSerializer()
            hashValueSerializer = StringRedisSerializer()
        }
    }
}
```

## 키 네이밍 컨벤션

### 규칙
```
{서비스}:{도메인}:{용도}:{식별자}
```

### 예시
| 용도 | 키 패턴 | TTL |
|------|---------|-----|
| 중복 체크 | `alarm:notification:dedup:{id}` | 24h |
| 분산 락 | `alarm:notification:lock:{id}` | 30s |
| Rate Limit | `alarm:ratelimit:{userId}:{window}` | 윈도우 크기 |
| 임시 데이터 | `alarm:temp:{requestId}` | 5m |

### @ConfigurationProperties
```kotlin
@ConfigurationProperties(prefix = "redis.key")
data class RedisKeyProperties(
    val prefix: String = "alarm",
    val dedup: DedupProperties = DedupProperties(),
    val lock: LockProperties = LockProperties(),
    val rateLimit: RateLimitProperties = RateLimitProperties(),
) {
    data class DedupProperties(
        val ttlSeconds: Long = 86400,  // 24시간
    )
    data class LockProperties(
        val waitTimeSeconds: Long = 5,
        val leaseTimeSeconds: Long = 30,
    )
    data class RateLimitProperties(
        val windowSeconds: Long = 60,
        val maxRequests: Long = 100,
    )
}
```

## 중복 체크 (SET NX + TTL)

### Domain Port
```kotlin
interface DuplicateChecker {
    /**
     * 중복 여부를 확인하고, 중복이 아니면 마킹한다.
     * @return true: 새 요청 (처리 진행), false: 중복 요청 (스킵)
     */
    fun checkAndMark(key: String): Boolean
}
```

### Infra 구현
```kotlin
@Component
class RedisDuplicateChecker(
    private val redisTemplate: RedisTemplate<String, String>,
    private val keyProperties: RedisKeyProperties,
) : DuplicateChecker {

    override fun checkAndMark(key: String): Boolean {
        val redisKey = "${keyProperties.prefix}:dedup:$key"
        val result = redisTemplate.opsForValue().setIfAbsent(
            redisKey,
            "1",
            Duration.ofSeconds(keyProperties.dedup.ttlSeconds),
        )
        return result == true  // null-safe: 연결 실패 시 false
    }
}
```

### 사용 예시
```kotlin
// Consumer에서 멱등성 보장
fun processNotification(message: NotificationMessage) {
    if (!duplicateChecker.checkAndMark("notification:${message.id}")) {
        logger.info("중복 메시지 스킵: ${message.id}")
        return
    }
    // 처리 로직
}

// API에서 멱등성 키
fun sendNotification(request: SendRequest, idempotencyKey: String) {
    if (!duplicateChecker.checkAndMark("api:$idempotencyKey")) {
        return getCachedResponse(idempotencyKey)
    }
    // 처리 로직
}
```

## 분산 락 (Redisson)

### Domain Port
```kotlin
interface DistributedLock {
    /**
     * 분산 락을 획득하고 action을 실행한다.
     * @throws LockAcquisitionException 락 획득 실패 시
     */
    fun <T> withLock(key: String, action: () -> T): T
}
```

### Infra 구현
```kotlin
@Component
class RedissonDistributedLock(
    private val redissonClient: RedissonClient,
    private val keyProperties: RedisKeyProperties,
) : DistributedLock {
    private val logger = LoggerFactory.getLogger(javaClass)

    override fun <T> withLock(key: String, action: () -> T): T {
        val lockKey = "${keyProperties.prefix}:lock:$key"
        val lock = redissonClient.getLock(lockKey)

        val acquired = lock.tryLock(
            keyProperties.lock.waitTimeSeconds,
            keyProperties.lock.leaseTimeSeconds,
            TimeUnit.SECONDS,
        )

        if (!acquired) {
            throw LockAcquisitionException("락 획득 실패: $lockKey")
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

### 사용 예시
```kotlin
// 동시 발송 방지
fun sendNotification(notificationId: Long) {
    distributedLock.withLock("notification:send:$notificationId") {
        val notification = notificationRepository.findById(notificationId)
            ?: throw DomainException.NotFound("Notification", notificationId)

        notification.markAsSending()
        notificationRepository.save(notification)

        externalSender.send(notification)
    }
}
```

## Rate Limiting (Sliding Window)

### Domain Port
```kotlin
interface RateLimiter {
    /**
     * 요청 허용 여부를 확인한다.
     * @return true: 허용, false: 제한 초과
     */
    fun isAllowed(key: String): Boolean
}
```

### Infra 구현 (Sorted Set)
```kotlin
@Component
class RedisRateLimiter(
    private val redisTemplate: RedisTemplate<String, String>,
    private val keyProperties: RedisKeyProperties,
) : RateLimiter {

    override fun isAllowed(key: String): Boolean {
        val redisKey = "${keyProperties.prefix}:ratelimit:$key"
        val now = System.currentTimeMillis()
        val windowStart = now - (keyProperties.rateLimit.windowSeconds * 1000)

        val ops = redisTemplate.opsForZSet()

        // 윈도우 밖 제거
        ops.removeRangeByScore(redisKey, 0.0, windowStart.toDouble())

        // 현재 카운트 확인
        val count = ops.zCard(redisKey) ?: 0

        if (count >= keyProperties.rateLimit.maxRequests) {
            return false
        }

        // 현재 요청 추가
        ops.add(redisKey, "$now:${UUID.randomUUID()}", now.toDouble())
        redisTemplate.expire(redisKey, Duration.ofSeconds(keyProperties.rateLimit.windowSeconds))

        return true
    }
}
```

## 테스트 (Testcontainers)

```kotlin
@SpringBootTest
@Testcontainers
class RedisDuplicateCheckerTest {

    companion object {
        @Container
        val redis = GenericContainer(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379)

        @JvmStatic
        @DynamicPropertySource
        fun redisProperties(registry: DynamicPropertyRegistry) {
            registry.add("spring.data.redis.host") { redis.host }
            registry.add("spring.data.redis.port") { redis.firstMappedPort }
        }
    }

    @Autowired
    private lateinit var duplicateChecker: DuplicateChecker

    @Test
    fun `첫 요청은 true를 반환한다`() {
        assertThat(duplicateChecker.checkAndMark("test:1")).isTrue()
    }

    @Test
    fun `중복 요청은 false를 반환한다`() {
        duplicateChecker.checkAndMark("test:2")
        assertThat(duplicateChecker.checkAndMark("test:2")).isFalse()
    }

    @Test
    fun `TTL 만료 후 다시 true를 반환한다`() {
        // TTL을 1초로 설정한 테스트용 체커 필요
        duplicateChecker.checkAndMark("test:3")
        Thread.sleep(1100)
        assertThat(duplicateChecker.checkAndMark("test:3")).isTrue()
    }
}
```

## TTL 전략

| 용도 | TTL | 근거 |
|------|-----|------|
| API 멱등성 키 | 24h | 클라이언트 재시도 윈도우 |
| Consumer 중복 체크 | 7d | 데이터 보관 주기와 동일 |
| 분산 락 | 30s | 작업 최대 소요 시간 |
| Rate Limit 윈도우 | 윈도우 크기 | Sliding window |
| 임시 데이터 | 5m | 요청 처리 타임아웃 |

## 안티패턴

| 안티패턴 | 문제 | 해결 |
|----------|------|------|
| TTL 없이 SET | 메모리 무한 증가 | 항상 TTL 설정 |
| 큰 값 저장 (>1KB) | Redis 메모리 압박 | 최소 정보만 저장, 큰 데이터는 DB |
| KEYS 명령 사용 | O(N) 블로킹 | SCAN 사용 |
| 락 해제 안 함 | 데드락 | finally 블록 + leaseTime |
| 단일 Redis 의존 | SPOF | Sentinel 또는 Cluster |
| 비밀번호 없음 | 보안 취약 | requirepass 설정 |
