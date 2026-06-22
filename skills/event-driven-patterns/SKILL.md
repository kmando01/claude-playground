---
name: event-driven-patterns
description: 이벤트 드리븐 아키텍처 패턴 레퍼런스. 최종 일관성, 보상 트랜잭션, 이벤트 순서 보장, Dead Letter 처리 정책, 이벤트 스키마 진화, 모니터링 포함. 비동기/이벤트 기반 시스템 설계 시 참조.
---

# Event-Driven Architecture Patterns

## 이 프로젝트의 이벤트 흐름
```
[API] → DB (notification + outbox)
  → [Debezium CDC] → Kafka work 토픽
  → [Consumer] → 외부 API 발송
  → 실패 시: retry 토픽 → dead 토픽
```

## 이벤트 설계

### 이벤트 정의 (domain)
```kotlin
// 이벤트는 domain 모듈에 정의 (순수 Kotlin)
sealed interface NotificationEvent {
    val notificationId: Long
    val occurredAt: LocalDateTime

    data class Created(
        override val notificationId: Long,
        val channel: String,
        val recipient: String,
        val content: String,
        override val occurredAt: LocalDateTime = LocalDateTime.now(),
    ) : NotificationEvent

    data class Sent(
        override val notificationId: Long,
        val sentAt: LocalDateTime,
        override val occurredAt: LocalDateTime = LocalDateTime.now(),
    ) : NotificationEvent

    data class Failed(
        override val notificationId: Long,
        val reason: String,
        val attempt: Int,
        override val occurredAt: LocalDateTime = LocalDateTime.now(),
    ) : NotificationEvent
}
```

### 이벤트 메시지 (Kafka payload)
```kotlin
data class NotificationMessage(
    val id: Long,
    val channel: String,
    val recipient: String,
    val content: String,
    val metadata: Map<String, String> = emptyMap(),
    val version: Int = 1,  // 스키마 버전
)
```

## 최종 일관성 (Eventual Consistency)

### 원칙
```
1. 동기 요청은 "접수" 상태만 반환
2. 실제 처리는 비동기로 진행
3. 클라이언트는 상태 조회 API로 결과 확인
```

### 상태 머신
```
PENDING → SENDING → SENT (성공)
                  → FAILED (실패)
                  → RETRY (재시도 중)
                  → DEAD (최종 실패)
```

### 구현 패턴
```kotlin
// API: 즉시 응답 (동기)
@PostMapping("/api/v1/notifications")
fun send(@RequestBody request: SendNotificationRequest): ResponseEntity<ApiResponse<NotificationResponse>> {
    val notification = notificationService.send(request.toCommand())
    // PENDING 상태로 즉시 응답 (202 Accepted)
    return ResponseEntity.status(HttpStatus.ACCEPTED)
        .body(ApiResponse.success(NotificationResponse.from(notification)))
}

// 상태 조회 API
@GetMapping("/api/v1/notifications/{id}")
fun getStatus(@PathVariable id: Long): ResponseEntity<ApiResponse<NotificationResponse>> {
    val notification = notificationService.findById(id)
    return ResponseEntity.ok(ApiResponse.success(NotificationResponse.from(notification)))
}
```

### 일관성 보장 체크리스트
- [ ] 비즈니스 데이터 + Outbox 같은 트랜잭션
- [ ] Consumer 멱등성 (Redis SET NX)
- [ ] 상태 전이 검증 (잘못된 전이 방지)
- [ ] 타임아웃 처리 (SENDING 상태 장기 체류 감지)

## 이벤트 순서 보장

### 전략별 비교
| 전략 | 순서 보장 범위 | 처리량 | 구현 복잡도 |
|------|--------------|--------|------------|
| 단일 파티션 | 전체 | 낮음 | 단순 |
| 키 기반 파티셔닝 | 같은 키 내 | 높음 | 단순 |
| 시퀀스 번호 | 전체 (Consumer 측) | 높음 | 복잡 |

### 키 기반 파티셔닝 (권장)
```kotlin
// 같은 notificationId → 같은 파티션 → 순서 보장
kafkaTemplate.send(topic, notificationId.toString(), payload)

// 순서가 중요한 경우: userId를 키로
kafkaTemplate.send(topic, userId.toString(), payload)
```

### 순서 보장이 깨지는 경우
| 상황 | 원인 | 대응 |
|------|------|------|
| Consumer 리밸런스 | 파티션 재할당 | offset commit 후 리밸런스 |
| retry 토픽 전송 | 원본 순서 이탈 | retry도 같은 키 사용 |
| 파티션 수 변경 | 키 해시 변경 | 파티션 수 변경 시 주의 |
| Consumer 병렬 처리 | 파티션 내 병렬화 | 파티션 내 순차 처리 유지 |

## Dead Letter 처리 정책

### DLQ 처리 흐름
```
dead 토픽 메시지
  → DLQ 모니터링 Consumer
  → 분류: 재처리 가능 / 불가능
  → 재처리 가능: 원인 해결 후 work 토픽으로 재전송
  → 불가능: 로깅 + 알림 + 수동 처리
```

### DLQ Consumer
```kotlin
@Component
class DeadLetterConsumer(
    private val notificationRepository: NotificationRepository,
) {
    private val logger = LoggerFactory.getLogger(javaClass)
    private val deadLetterCounter = Metrics.counter("kafka.dead.letter.count")

    @KafkaListener(
        topics = ["#{@kafkaTopicProperties.dead}"],
        groupId = "\${spring.kafka.consumer.group-id}-dlq",
    )
    fun consume(
        record: ConsumerRecord<String, NotificationMessage>,
        ack: Acknowledgment,
    ) {
        val errorClass = record.headers().lastHeader("error-class")
            ?.let { String(it.value()) } ?: "Unknown"
        val errorMessage = record.headers().lastHeader("error-message")
            ?.let { String(it.value()) } ?: "Unknown"

        logger.error(
            "DLQ 메시지 수신: key={}, errorClass={}, errorMessage={}",
            record.key(), errorClass, errorMessage,
        )

        // 메트릭 기록
        deadLetterCounter.increment()

        // 상태 업데이트
        notificationRepository.findById(record.value().id)?.let { notification ->
            notification.markAsDead(errorMessage)
            notificationRepository.save(notification)
        }

        ack.acknowledge()
    }
}
```

### DLQ 재처리 도구
```kotlin
// 관리자 API로 DLQ 메시지 재처리
@PostMapping("/admin/api/v1/notifications/{id}/retry")
fun retryDeadLetter(@PathVariable id: Long): ResponseEntity<ApiResponse<Unit>> {
    notificationService.retryFromDead(id)
    return ResponseEntity.accepted().body(ApiResponse.success(Unit))
}
```

## 보상 트랜잭션 (Compensating Transaction)

### 언제 필요한가
```
알림 발송 성공 → 과금 처리 실패
  → 알림 발송 취소 (보상 트랜잭션)
```

### 패턴
```kotlin
// Saga Orchestrator (단순 버전)
@Service
class NotificationSaga(
    private val notificationService: NotificationService,
    private val billingService: BillingService,
) {
    fun execute(command: SendNotificationCommand) {
        val notification = notificationService.send(command)
        try {
            billingService.charge(notification)
        } catch (e: Exception) {
            // 보상: 알림 상태를 CANCELLED로 변경
            notificationService.compensate(notification.id, "과금 실패: ${e.message}")
            throw e
        }
    }
}
```

### 보상 설계 원칙
1. **멱등성**: 보상 트랜잭션도 멱등해야 함
2. **로깅**: 보상 사유와 원본 트랜잭션 ID 기록
3. **타임아웃**: 보상 실패 시 수동 개입 경로 확보
4. **순서**: 역순으로 보상 실행

## 이벤트 스키마 진화

### 버전 관리
```kotlin
data class NotificationMessage(
    val id: Long,
    val channel: String,
    val recipient: String,
    val content: String,
    val version: Int = 1,  // 스키마 버전
    // v2에서 추가
    val priority: String? = null,  // 하위 호환: nullable + 기본값
)
```

### 호환성 규칙
| 변경 | 호환성 | 허용 |
|------|--------|------|
| 필드 추가 (nullable) | 하위 호환 | O |
| 필드 추가 (required) | 비호환 | X (새 토픽 필요) |
| 필드 삭제 | 상위 호환 | 주의 (Consumer 확인) |
| 필드 타입 변경 | 비호환 | X (새 토픽 필요) |
| 필드 이름 변경 | 비호환 | X |

### Consumer 버전 처리
```kotlin
fun process(message: NotificationMessage) {
    when {
        message.version >= 2 -> processV2(message)
        else -> processV1(message)
    }
}
```

## 모니터링

### 핵심 메트릭
| 메트릭 | 의미 | 알림 임계값 |
|--------|------|------------|
| `kafka.consumer.lag` | 미처리 메시지 수 | > 10,000 |
| `kafka.dead.letter.count` | DLQ 메시지 수 | > 0 (즉시) |
| `notification.processing.time` | 처리 소요 시간 | p99 > 5s |
| `notification.send.success.rate` | 발송 성공률 | < 99% |
| `outbox.pending.count` | 미발행 Outbox 수 | > 1,000 |

### Consumer Lag 모니터링
```kotlin
@Component
class KafkaLagHealthIndicator(
    private val kafkaAdmin: AdminClient,
    private val topicProperties: KafkaTopicProperties,
) : HealthIndicator {

    override fun health(): Health {
        // Consumer group lag 확인
        val lag = calculateLag()
        return if (lag < 10_000) {
            Health.up().withDetail("lag", lag).build()
        } else {
            Health.down().withDetail("lag", lag).build()
        }
    }
}
```

## 안티패턴

| 안티패턴 | 문제 | 해결 |
|----------|------|------|
| 동기식 이벤트 처리 | 장애 전파 | 비동기 + 상태 머신 |
| 이벤트에 전체 데이터 | 메시지 크기 증가 | ID + 최소 정보, Consumer가 조회 |
| Consumer에서 DB 직접 수정 | 도메인 우회 | Domain Service 호출 |
| 순서 의존 로직 + 병렬 Consumer | 데이터 정합성 깨짐 | 키 기반 파티셔닝 |
| DLQ 무시 | 실패 메시지 방치 | DLQ 모니터링 + 알림 필수 |
| 이벤트 스키마 무관리 | 역직렬화 실패 | 버전 필드 + 하위 호환성 유지 |
