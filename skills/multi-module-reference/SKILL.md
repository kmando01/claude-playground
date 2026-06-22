---
name: multi-module-reference
description: 멀티모듈 아키텍처 상세 레퍼런스. 모듈별 책임 상세, 패키지 구조, Domain↔Infra 매핑 패턴, build.gradle.kts 예시 포함. 새 도메인/모듈 추가, 코드 리뷰 시 참조.
---

# 멀티모듈 아키텍처 레퍼런스

## 모듈별 상세 책임

### xxx-app-api (API 서버)
- REST Controller, Request/Response DTO
- API 문서 (SpringDoc/OpenAPI)
- 인증/인가 필터 (Spring Security)
- 요청 유효성 검증 (@Valid, Bean Validation)
- 다른 app 모듈과 코드 공유 금지

### xxx-app-admin (어드민)
- 관리자용 API Controller, 어드민 전용 DTO
- 어드민 인증/인가
- app-api와 독립적으로 배포 가능

### xxx-app-batch (배치/컨슈머)
- Spring Batch Job 정의, Kafka Consumer 정의
- 스케줄러 설정, 장시간 실행 작업 처리

### xxx-domain (핵심 비즈니스)
- **순수 Kotlin** - Spring/JPA 의존성 절대 금지
- Entity, Value Object, Domain Service, Port Interface, Domain Event, Domain Exception

```kotlin
dependencies {
    implementation(project(":xxx-common"))
    // Spring, JPA 의존성 절대 금지!
}
```

### xxx-infra (인프라)
- JPA Entity, Repository 구현체 (domain Port 구현)
- Redis 연동, Kafka Producer, 외부 인프라 설정

```kotlin
dependencies {
    implementation(project(":xxx-domain"))
    implementation(project(":xxx-common"))
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
}
```

### xxx-client-external (외부 API 연동)
- 외부 API Client (RestClient, WebClient, Feign)
- 외부 API DTO, Circuit Breaker, Retry 설정

```kotlin
dependencies {
    implementation(project(":xxx-domain"))
    implementation(project(":xxx-common"))
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```

### xxx-common (공통)
- 유틸리티, 상수, 공통 예외, 확장 함수
- **의존성 없음** (다른 모듈 참조 금지)

## 패키지 구조

### domain 모듈
```
xxx-domain/src/main/kotlin/com/xxx/domain/
├── {도메인명}/
│   ├── model/          # Entity, Value Object
│   ├── service/        # Domain Service
│   ├── port/           # Port Interface (in/out)
│   ├── event/          # Domain Event
│   └── exception/      # Domain Exception
```

### infra 모듈
```
xxx-infra/src/main/kotlin/com/xxx/infra/
├── {도메인명}/
│   ├── entity/         # JPA Entity (@Entity)
│   ├── repository/     # JPA Repository (Port 구현)
│   └── mapper/         # Domain ↔ JPA Entity 변환
├── redis/              # Redis 관련
├── kafka/              # Kafka Producer
└── config/             # 인프라 설정
```

### app-api 모듈
```
xxx-app-api/src/main/kotlin/com/xxx/api/
├── {도메인명}/
│   ├── controller/     # REST Controller
│   ├── dto/            # Request/Response DTO
│   └── mapper/         # DTO ↔ Domain 변환
├── auth/               # 인증/인가
├── config/             # API 설정
└── filter/             # 필터, 인터셉터
```

## Domain ↔ Infra 매핑 패턴

```kotlin
// domain 모듈: 순수 모델
data class Order(
    val id: Long,
    val userId: Long,
    val items: List<OrderItem>,
    val status: OrderStatus,
    val createdAt: LocalDateTime
)

// domain 모듈: Port Interface
interface OrderRepository {
    fun findById(id: Long): Order?
    fun save(order: Order): Order
    fun findByUserId(userId: Long): List<Order>
}

// infra 모듈: JPA Entity
@Entity
@Table(name = "orders")
class OrderJpaEntity(
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long = 0,
    val userId: Long,
    @Enumerated(EnumType.STRING)
    var status: OrderStatus,
    val createdAt: LocalDateTime = LocalDateTime.now()
) {
    fun toDomain(): Order = Order(
        id = id,
        userId = userId,
        items = emptyList(),
        status = status,
        createdAt = createdAt
    )

    companion object {
        fun from(order: Order): OrderJpaEntity = OrderJpaEntity(
            id = order.id,
            userId = order.userId,
            status = order.status,
            createdAt = order.createdAt
        )
    }
}

// infra 모듈: Port 구현
@Repository
class OrderRepositoryImpl(
    private val jpaRepository: OrderJpaRepository
) : OrderRepository {
    override fun findById(id: Long): Order? =
        jpaRepository.findByIdOrNull(id)?.toDomain()

    override fun save(order: Order): Order =
        jpaRepository.save(OrderJpaEntity.from(order)).toDomain()

    override fun findByUserId(userId: Long): List<Order> =
        jpaRepository.findByUserId(userId).map { it.toDomain() }
}
```

## 인프라 추가 절차

```
1. docker-compose.yml에 서비스 정의 (healthcheck 포함)
2. application-local.yml에 연결 설정
3. infra 모듈에 Config 클래스 추가
4. infra 모듈에 Testcontainers 기반 통합 테스트 추가
5. .env.example에 환경 변수 추가
```

직접 설치(brew install 등) 금지 — 모든 외부 인프라는 docker-compose로 관리.
