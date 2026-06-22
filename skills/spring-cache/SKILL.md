---
name: spring-cache
description: Spring Cache + Redis caching patterns for Kotlin. Use when implementing caching strategies, cache invalidation, TTL management, or Redis integration in multi-module projects.
---

# Spring Cache + Redis 패턴

## 모듈 배치

```
domain  → CachePort 인터페이스 정의 (선택)
infra   → Redis 설정, @Cacheable 구현, CachePort 구현
app-api → 캐시 적용 대상 결정 (Application Service)
```

## Redis 설정

### @ConfigurationProperties
```kotlin
// infra 모듈
@ConfigurationProperties(prefix = "cache")
data class CacheProperties(
    val defaultTtl: Duration = Duration.ofMinutes(30),
    val configs: Map<String, CacheConfig> = emptyMap()
) {
    data class CacheConfig(
        val ttl: Duration,
        val maxSize: Long = 1000
    )
}
```

### application.yml
```yaml
cache:
  default-ttl: 30m
  configs:
    products:
      ttl: 1h
    orders:
      ttl: 5m
    user-profile:
      ttl: 24h
```

### RedisCacheManager 설정
```kotlin
@Configuration
@EnableCaching
class RedisCacheConfig(
    private val properties: CacheProperties
) {
    @Bean
    fun cacheManager(connectionFactory: RedisConnectionFactory): RedisCacheManager {
        val defaultConfig = RedisCacheConfiguration.defaultCacheConfig()
            .entryTtl(properties.defaultTtl)
            .serializeKeysWith(
                RedisSerializationContext.SerializationPair.fromSerializer(StringRedisSerializer())
            )
            .serializeValuesWith(
                RedisSerializationContext.SerializationPair.fromSerializer(
                    GenericJackson2JsonRedisSerializer(objectMapper())
                )
            )
            .disableCachingNullValues()

        val cacheConfigs = properties.configs.mapValues { (_, config) ->
            defaultConfig.entryTtl(config.ttl)
        }

        return RedisCacheManager.builder(connectionFactory)
            .cacheDefaults(defaultConfig)
            .withInitialCacheConfigurations(cacheConfigs)
            .build()
    }

    private fun objectMapper() = ObjectMapper().apply {
        registerModule(JavaTimeModule())
        registerModule(KotlinModule.Builder().build())
        activateDefaultTyping(
            polymorphicTypeValidator(),
            ObjectMapper.DefaultTyping.NON_FINAL
        )
    }
}
```

## @Cacheable 패턴

### 기본 조회 캐시
```kotlin
// infra 모듈 또는 app-api Application Service
@Cacheable(
    cacheNames = ["products"],
    key = "#id"
)
fun getProduct(id: Long): Product {
    return productRepository.findById(id)
        ?: throw DomainException.NotFound("Product", id)
}
```

### 목록 캐시 (페이지네이션 주의)
```kotlin
@Cacheable(
    cacheNames = ["product-list"],
    key = "#categoryId + ':' + #pageable.pageNumber + ':' + #pageable.pageSize"
)
fun getProducts(categoryId: Long, pageable: Pageable): Page<Product> {
    return productRepository.findByCategoryId(categoryId, pageable)
}
```

### 조건부 캐시
```kotlin
// 결과가 null이 아닐 때만 캐시
@Cacheable(
    cacheNames = ["orders"],
    key = "#id",
    unless = "#result == null"
)
fun findOrder(id: Long): Order? {
    return orderRepository.findById(id)
}
```

## 캐시 무효화

### 단건 무효화
```kotlin
@CacheEvict(cacheNames = ["products"], key = "#id")
fun updateProduct(id: Long, command: UpdateProductCommand): Product {
    val product = productRepository.findById(id)
        ?: throw DomainException.NotFound("Product", id)
    val updated = product.update(command)
    return productRepository.save(updated)
}
```

### 갱신과 동시에 캐시 업데이트
```kotlin
@CachePut(cacheNames = ["products"], key = "#id")
fun updateProduct(id: Long, command: UpdateProductCommand): Product {
    // @CachePut: 메서드 항상 실행 + 결과를 캐시에 저장
    val product = productRepository.findById(id) ?: throw ...
    return productRepository.save(product.update(command))
}
```

### 전체 무효화
```kotlin
@CacheEvict(cacheNames = ["product-list"], allEntries = true)
fun createProduct(command: CreateProductCommand): Product {
    // 목록 캐시 전체 무효화 (새 상품이 추가되었으므로)
    return productRepository.save(Product.create(command))
}
```

### 여러 캐시 동시 무효화
```kotlin
@Caching(evict = [
    CacheEvict(cacheNames = ["products"], key = "#id"),
    CacheEvict(cacheNames = ["product-list"], allEntries = true)
])
fun deleteProduct(id: Long) {
    productRepository.delete(id)
}
```

## Cache-Aside 패턴 (수동 제어)

@Cacheable로 부족한 경우 직접 제어:

```kotlin
// infra 모듈
@Repository
class RedisCacheRepository(
    private val redisTemplate: RedisTemplate<String, String>,
    private val objectMapper: ObjectMapper,
    private val properties: CacheProperties
) {
    fun <T> getOrPut(
        key: String,
        ttl: Duration = properties.defaultTtl,
        type: Class<T>,
        loader: () -> T
    ): T {
        // 1. 캐시에서 조회
        val cached = redisTemplate.opsForValue().get(key)
        if (cached != null) {
            return objectMapper.readValue(cached, type)
        }

        // 2. 없으면 원본 조회
        val value = loader()

        // 3. 캐시에 저장
        redisTemplate.opsForValue().set(
            key,
            objectMapper.writeValueAsString(value),
            ttl
        )
        return value
    }

    fun evict(key: String) {
        redisTemplate.delete(key)
    }

    fun evictByPattern(pattern: String) {
        val keys = redisTemplate.keys(pattern)
        if (keys.isNotEmpty()) {
            redisTemplate.delete(keys)
        }
    }
}
```

## 캐시 키 설계

```kotlin
// 키 네이밍 컨벤션
object CacheKeys {
    fun product(id: Long) = "product:$id"
    fun productList(categoryId: Long, page: Int) = "product-list:$categoryId:$page"
    fun userProfile(userId: Long) = "user:$userId:profile"
    fun orderCount(userId: Long) = "user:$userId:order-count"
}
```

## 캐시 전략 선택

| 전략 | 설명 | 사용 케이스 |
|------|------|------------|
| **Cache-Aside** | 앱이 직접 캐시 관리 | 대부분의 경우 (기본 선택) |
| **Write-Through** | 쓰기 시 캐시+DB 동시 갱신 | 쓰기 후 즉시 읽기가 많은 경우 |
| **Write-Behind** | 쓰기 시 캐시만 갱신, DB는 비동기 | 쓰기 빈번 + 일시적 불일치 허용 |

## 캐시 안티패턴

```kotlin
// BAD: 자주 변경되는 데이터 캐시
@Cacheable("orders")
fun getOrder(id: Long): Order { ... }  // 주문 상태가 자주 변함

// BAD: 캐시 키에 가변 객체 사용
@Cacheable(key = "#user")  // User 객체 전체가 키 → hashCode 문제
fun getData(user: User) { ... }

// GOOD: 불변 ID를 키로
@Cacheable(key = "#userId")
fun getData(userId: Long) { ... }

// BAD: TTL 없는 캐시 → 메모리 누수
// GOOD: 반드시 TTL 설정 (application.yml에서 관리)

// BAD: 트랜잭션 롤백 시 캐시 불일치
@Transactional
@CachePut(cacheNames = ["products"], key = "#id")
fun update(id: Long): Product {
    val saved = repository.save(...)  // 이후 예외 발생하면?
    externalApi.notify(...)           // 여기서 실패 → 트랜잭션 롤백
    return saved                      // 캐시에는 이미 저장됨!
}

// GOOD: 트랜잭션 커밋 후 캐시 갱신
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
fun onProductUpdated(event: ProductUpdatedEvent) {
    cacheRepository.evict(CacheKeys.product(event.productId))
}
```
