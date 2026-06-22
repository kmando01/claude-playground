---
name: design-principles-reference
description: 설계 원칙 상세 레퍼런스. Rich Domain Model, Aggregate, Value Object, Port 설계의 BAD/GOOD 코드 예시, API 상태 코드 테이블, 에러 응답 형식, 데이터 모델 설계 가이드 포함. /design 실행 시 참조.
---

# 설계 원칙 레퍼런스

## Rich Domain Model — BAD vs GOOD

```
BAD (빈약한 도메인):
  Entity에 getter/setter만 있고, 비즈니스 로직은 Service에 있음
  → 절차적 코드, 도메인 지식 분산

GOOD (풍부한 도메인):
  Entity가 자신의 상태 변경 규칙을 직접 관리
  Service는 Entity 간 조율만 담당
  → 비즈니스 규칙이 도메인에 응집
```

## Value Object 예시

```kotlin
// BAD: 원시값 직접 사용
val price: Long
val email: String

// GOOD: 의미 있는 타입으로 감싸기
val price: Money
val email: Email
```
- 유효성 검증이 타입에 내장 → 잘못된 값이 시스템에 들어올 수 없음
- 비즈니스 연산이 타입에 포함 (Money + Money, Money * quantity)

## Port 설계 예시

### 도메인 관점으로 정의
```kotlin
// BAD: 인프라 용어 누출
interface OrderJpaRepository { ... }
interface OrderRedisCache { ... }

// GOOD: 도메인 관점
interface OrderRepository { ... }
interface OrderCache { ... }
```

### 인터페이스 분리 (ISP)
```kotlin
// BAD: 거대 인터페이스
interface OrderRepository {
    fun save(order: Order): Order
    fun findById(id: Long): Order?
    fun findByUserId(userId: Long): List<Order>
    fun findByStatus(status: OrderStatus): List<Order>
    fun countByDate(date: LocalDate): Long
    fun sumRevenueByMonth(month: YearMonth): Money
}

// GOOD: 역할별 분리
interface OrderRepository {
    fun save(order: Order): Order
    fun findById(id: Long): Order?
    fun findByUserId(userId: Long, pageable: PageRequest): Page<Order>
}

interface OrderStatistics {
    fun countByDate(date: LocalDate): Long
    fun sumRevenueByMonth(month: YearMonth): Money
}
```

## API 설계 예시

### 자원 중심 설계
```
BAD:  POST /api/v1/createOrder
      GET  /api/v1/getOrderById?id=1
GOOD: POST /api/v1/orders
      GET  /api/v1/orders/1
```

### 상태 코드 테이블
| 상황 | 코드 |
|------|------|
| 생성 성공 | 201 Created |
| 조회/수정/삭제 성공 | 200 OK |
| 입력 검증 실패 | 400 Bad Request |
| 인증 실패 | 401 Unauthorized |
| 권한 없음 | 403 Forbidden |
| 리소스 없음 | 404 Not Found |
| 충돌 (중복, 동시성) | 409 Conflict |
| 서버 에러 | 500 Internal Server Error |

### 에러 응답 형식
```json
{
  "success": false,
  "error": {
    "code": "ORDER_ALREADY_CANCELLED",
    "message": "이미 취소된 주문입니다",
    "details": [
      { "field": "orderId", "reason": "주문 상태: CANCELLED" }
    ]
  }
}
```

## 데이터 모델 설계

### 인덱스 설계 순서
1. API에서 필요한 쿼리를 먼저 나열
2. 각 쿼리의 WHERE, ORDER BY, JOIN 조건 확인
3. 그 조건에 맞는 인덱스 설계
4. 쓰기 성능과 트레이드오프 확인

### 정규화 vs 비정규화
- **기본은 정규화**: 데이터 정합성 우선
- **성능 병목이 증명되면** 비정규화 고려 (조회 성능 vs 갱신 복잡도)
- **읽기 모델 분리**: CQRS가 필요한 수준이면 별도 조회용 테이블/뷰 고려

### Soft Delete 주의
```kotlin
// Soft Delete를 쓸 때 항상 질문:
// 1. 모든 쿼리에 WHERE deleted = false를 빼먹지 않을 자신이 있는가?
// 2. UNIQUE 제약조건과 충돌하지 않는가?
// 3. 개인정보 보호 규정상 실제 삭제가 필요하지 않은가?
```

## 패턴 적용 시 정책 체크리스트

패턴 이름만으로는 구현이 결정되지 않는다. 적용 시 반드시 아래 세부 정책을 결정하고 ADR/설계 문서에 명시하라.

| 패턴 | 결정 필수 항목 |
|------|---------------|
| 멱등성 키 | 생성 주체(클라이언트/서버), 유일성 범위(글로벌/사용자/세션), 포맷 가이드(UUID 권장 등), TTL |
| UNIQUE 제약 | 범위(단일/복합), 위반 시 응답 코드 + 메시지, catch 위치(infra 레이어) |
| 캐시 | TTL, 무효화 전략(TTL/이벤트/수동), 키 범위(글로벌/사용자), 캐시 미스 시 동작 |
| 재시도 | 최대 횟수, 백오프 전략(고정/지수), 재시도 대상 예외, 멱등성 보장 여부 |
| 분산 락 | 락 키 범위, TTL, 획득 실패 시 동작(대기/즉시 실패), 데드락 방지 |

## 설계 안티패턴 상세

| 안티패턴 | 증상 | 해결 |
|----------|------|------|
| **God Service** | 하나의 Service가 10개 이상 메서드 | 역할별 UseCase 분리 |
| **Anemic Domain** | Entity에 로직 없음, Service에만 로직 | 도메인 로직을 Entity로 이동 |
| **Leaky Abstraction** | domain에 JPA 어노테이션, infra 용어 | Port 인터페이스로 추상화 |
| **Shared Mutable State** | 여러 모듈이 같은 테이블 직접 접근 | Aggregate 경계 정의, API로 통신 |
| **Distributed Monolith** | 모듈 분리했지만 모든 모듈이 서로 의존 | 의존성 방향 정리, 이벤트 기반 디커플링 |
| **Premature Optimization** | 규모 추정 없이 캐시/샤딩 도입 | Step 3 규모 추정 먼저 |
| **Config in Code** | 타임아웃, TTL, 풀 사이즈 하드코딩 | @ConfigurationProperties로 외부화 |
