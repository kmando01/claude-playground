---
name: spring-jpa-performance
description: Optimize JPA/Hibernate performance. Covers N+1 prevention, projections, pagination, bulk operations, caching, and index optimization. Use when working with JPA repositories or diagnosing performance issues.
---

# JPA 성능 최적화 패턴

## 성능 체크리스트

코드 리뷰 시 확인:
- [ ] N+1 쿼리 없음
- [ ] 필요한 컬럼만 조회 (Projection)
- [ ] 적절한 페이지네이션
- [ ] Bulk 연산 시 직접 쿼리 사용
- [ ] 인덱스 설계 완료
- [ ] 쿼리 로그 확인

## N+1 문제 해결

### Fetch Join
```kotlin
interface OrderJpaRepository : JpaRepository<OrderJpaEntity, Long> {
    @Query("SELECT o FROM OrderJpaEntity o JOIN FETCH o.items WHERE o.userId = :userId")
    fun findByUserIdWithItems(@Param("userId") userId: Long): List<OrderJpaEntity>
}
```

### EntityGraph
```kotlin
interface OrderJpaRepository : JpaRepository<OrderJpaEntity, Long> {
    @EntityGraph(attributePaths = ["items", "items.product"])
    fun findByUserId(userId: Long): List<OrderJpaEntity>
}
```

### BatchSize
```kotlin
@Entity
class OrderJpaEntity(
    @BatchSize(size = 100)
    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    val items: MutableList<OrderItemJpaEntity> = mutableListOf()
)
```

## Projection 패턴

### Interface Projection
```kotlin
interface OrderSummary {
    val id: Long
    val userId: Long
    val status: String
    val totalPrice: Long
    val createdAt: LocalDateTime
}

interface OrderJpaRepository : JpaRepository<OrderJpaEntity, Long> {
    fun findSummaryByUserId(userId: Long): List<OrderSummary>
}
```

### DTO Projection
```kotlin
data class OrderDto(
    val id: Long,
    val userName: String,
    val totalPrice: Long
)

@Query("""
    SELECT new com.xxx.infra.order.dto.OrderDto(o.id, u.name, o.totalPrice)
    FROM OrderJpaEntity o JOIN UserJpaEntity u ON o.userId = u.id
    WHERE o.status = :status
""")
fun findDtoByStatus(@Param("status") status: OrderStatus): List<OrderDto>
```

## 페이지네이션

### Offset Pagination
```kotlin
fun findByStatus(status: OrderStatus, pageable: Pageable): Page<OrderJpaEntity>
```

### Keyset Pagination (대량 데이터)
```kotlin
@Query("""
    SELECT o FROM OrderJpaEntity o
    WHERE o.createdAt < :cursor
    ORDER BY o.createdAt DESC
""")
fun findByCursor(
    @Param("cursor") cursor: LocalDateTime,
    pageable: Pageable
): Slice<OrderJpaEntity>
```

### Slice vs Page
```kotlin
// Page: 전체 카운트 쿼리 실행 (목록 + 총 페이지 수 표시)
fun findByStatus(status: OrderStatus, pageable: Pageable): Page<OrderJpaEntity>

// Slice: 카운트 쿼리 없음 (무한 스크롤)
fun findByStatus(status: OrderStatus, pageable: Pageable): Slice<OrderJpaEntity>
```

## Bulk 연산

### Bulk Update
```kotlin
@Modifying(clearAutomatically = true)
@Query("UPDATE OrderJpaEntity o SET o.status = :status WHERE o.id IN :ids")
fun bulkUpdateStatus(
    @Param("ids") ids: List<Long>,
    @Param("status") status: OrderStatus
): Int
```

### Bulk Delete
```kotlin
@Modifying(clearAutomatically = true)
@Query("DELETE FROM OrderJpaEntity o WHERE o.status = :status AND o.createdAt < :before")
fun deleteOldByStatus(
    @Param("status") status: OrderStatus,
    @Param("before") before: LocalDateTime
): Int
```

### Bulk Insert (JDBC)
```kotlin
@Repository
class OrderBulkRepository(private val jdbcTemplate: JdbcTemplate) {
    fun bulkInsert(orders: List<OrderJpaEntity>) {
        jdbcTemplate.batchUpdate(
            "INSERT INTO orders (user_id, status, total_price, created_at) VALUES (?, ?, ?, ?)",
            orders,
            1000
        ) { ps, order ->
            ps.setLong(1, order.userId)
            ps.setString(2, order.status.name)
            ps.setLong(3, order.totalPrice)
            ps.setObject(4, order.createdAt)
        }
    }
}
```

## 2차 캐시

### 설정
```yaml
# application.yml
spring:
  jpa:
    properties:
      hibernate:
        cache:
          use_second_level_cache: true
          use_query_cache: true
          region.factory_class: org.hibernate.cache.jcache.JCacheRegionFactory
```

### Entity 캐시
```kotlin
@Entity
@Cacheable
@Cache(usage = CacheConcurrencyStrategy.READ_WRITE)
class ProductJpaEntity(
    @Id val id: Long,
    val name: String,
    val price: Long
)
```

### 캐시 전략

| 전략 | 용도 |
|------|------|
| READ_ONLY | 절대 변경되지 않는 데이터 (코드 테이블) |
| READ_WRITE | 읽기 위주, 간헐적 수정 |
| NONSTRICT_READ_WRITE | 약간의 불일치 허용 |
| TRANSACTIONAL | JTA 트랜잭션 필요 |

## 인덱스 최적화

```kotlin
@Entity
@Table(
    name = "orders",
    indexes = [
        Index(name = "idx_orders_user_id", columnList = "userId"),
        Index(name = "idx_orders_status_created", columnList = "status, createdAt"),
        Index(name = "idx_orders_user_status", columnList = "userId, status")
    ]
)
class OrderJpaEntity(...)
```

### 인덱스 설계 가이드
- WHERE 절에 자주 사용되는 컬럼
- JOIN 조건 컬럼
- ORDER BY 컬럼
- 카디널리티가 높은 컬럼 우선
- 복합 인덱스: 조건 순서대로

## 쿼리 로깅

```yaml
# application.yml (개발 환경)
spring:
  jpa:
    properties:
      hibernate:
        format_sql: true
        generate_statistics: true

logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.type.descriptor.sql.BasicBinder: TRACE
```

### 슬로우 쿼리 감지
```yaml
spring:
  jpa:
    properties:
      hibernate:
        session.events.log.LOG_QUERIES_SLOWER_THAN_MS: 500
```

## Anti-Patterns

### Open Session in View (OSIV)
```yaml
# 반드시 비활성화
spring:
  jpa:
    open-in-view: false
```

### Eager Fetching
```kotlin
// BAD: EAGER
@OneToMany(fetch = FetchType.EAGER)
val items: List<OrderItemJpaEntity>

// GOOD: LAZY + 필요 시 Fetch Join
@OneToMany(fetch = FetchType.LAZY)
val items: List<OrderItemJpaEntity>
```

### toString on Lazy
```kotlin
// BAD: Lazy 연관관계 toString에 포함
data class OrderJpaEntity(
    val items: List<OrderItemJpaEntity>  // toString 시 Lazy 로딩!
)

// GOOD: 연관관계 제외
@Entity
class OrderJpaEntity(...) {
    @OneToMany(fetch = FetchType.LAZY)
    val items: MutableList<OrderItemJpaEntity> = mutableListOf()

    // items는 toString에서 제외됨
    override fun toString() = "OrderJpaEntity(id=$id, userId=$userId)"
}
```
