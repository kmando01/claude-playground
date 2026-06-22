---
name: transactional-outbox
description: Transactional Outbox + CDC(Debezium) 패턴 레퍼런스. Outbox 테이블 설계, JPA Entity, Debezium Connector 설정, Polling Publisher 대안, 멱등 Consumer, 장애 복구 시나리오 포함. 이벤트 발행 신뢰성 보장 시 참조.
---

# Transactional Outbox + CDC Pattern

## 왜 필요한가
```
문제: DB 저장 + Kafka 전송을 원자적으로 실행 불가
  - DB 저장 성공 + Kafka 실패 → 데이터 불일치
  - Kafka 먼저 전송 + DB 실패 → 유령 메시지

해결: Outbox 패턴
  1. 비즈니스 데이터 + Outbox 레코드를 같은 트랜잭션에 저장
  2. CDC(Debezium)가 Outbox 테이블 변경을 감지하여 Kafka로 전달
  → 원자성 보장 (같은 DB 트랜잭션)
```

## 데이터 흐름
```
API Request
  → @Transactional { notification 저장 + outbox 저장 }
  → Debezium이 outbox INSERT 감지
  → Kafka work 토픽으로 전달
  → Consumer가 처리
```

## Outbox 테이블 설계

### DDL
```sql
CREATE TABLE outbox_event (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    aggregate_type  VARCHAR(100) NOT NULL,     -- 'Notification'
    aggregate_id    BIGINT NOT NULL,           -- notification.id
    event_type      VARCHAR(100) NOT NULL,     -- 'NOTIFICATION_CREATED'
    payload         JSON NOT NULL,             -- 이벤트 데이터
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_outbox_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 설계 포인트
- `aggregate_type` + `aggregate_id` → Kafka 메시지 키로 사용 (순서 보장)
- `payload`는 JSON → Consumer가 역직렬화
- `created_at` 인덱스 → Polling Publisher 폴백 시 사용
- Debezium이 읽은 후 삭제하지 않음 (로그 보관 + 디버깅)

## JPA Entity (infra)

```kotlin
@Entity
@Table(name = "outbox_event")
class OutboxEventEntity(
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long = 0L,

    @Column(nullable = false, length = 100)
    val aggregateType: String,

    @Column(nullable = false)
    val aggregateId: Long,

    @Column(nullable = false, length = 100)
    val eventType: String,

    @Column(nullable = false, columnDefinition = "JSON")
    val payload: String,

    @Column(nullable = false)
    val createdAt: LocalDateTime = LocalDateTime.now(),
)
```

### Repository
```kotlin
interface OutboxEventJpaRepository : JpaRepository<OutboxEventEntity, Long> {
    fun findByCreatedAtBeforeOrderByCreatedAtAsc(
        before: LocalDateTime,
        pageable: Pageable,
    ): List<OutboxEventEntity>
}
```

## Domain Service에서 Outbox 저장

```kotlin
// domain Port
interface OutboxEventPort {
    fun save(event: OutboxEvent)
}

// domain 모델
data class OutboxEvent(
    val aggregateType: String,
    val aggregateId: Long,
    val eventType: String,
    val payload: String,
)

// domain Service
@Service
@Transactional
class NotificationService(
    private val notificationRepository: NotificationRepository,
    private val outboxEventPort: OutboxEventPort,
    private val objectMapper: ObjectMapper,
) {
    fun send(command: SendNotificationCommand): Notification {
        // 1. 비즈니스 로직
        val notification = Notification.create(command)
        val saved = notificationRepository.save(notification)

        // 2. 같은 트랜잭션에서 Outbox 저장
        outboxEventPort.save(
            OutboxEvent(
                aggregateType = "Notification",
                aggregateId = saved.id,
                eventType = "NOTIFICATION_CREATED",
                payload = objectMapper.writeValueAsString(saved.toMessage()),
            )
        )

        return saved
    }
}
```

## Debezium Connector 설정

### docker-compose.yml
```yaml
debezium:
  image: debezium/connect:2.5
  container_name: debezium
  ports:
    - "8083:8083"
  environment:
    GROUP_ID: 1
    BOOTSTRAP_SERVERS: kafka:29092
    CONFIG_STORAGE_TOPIC: debezium_configs
    OFFSET_STORAGE_TOPIC: debezium_offsets
    STATUS_STORAGE_TOPIC: debezium_statuses
  depends_on:
    kafka:
      condition: service_healthy
    mysql:
      condition: service_healthy
```

### Connector 등록 (JSON)

> **⚠️ MUST**: `include.schema.changes: false` + `snapshot.mode: no_data` 반드시 설정.
> 미설정 시 Debezium이 DDL 이벤트(TRUNCATE 등)를 `topic.prefix` 토픽에 발행 시도.
> 해당 토픽 미생성 + `auto.create.topics.enable=false` 조합이면 `UNKNOWN_TOPIC_OR_PARTITION` 무한 재시도 → 이후 DML(INSERT) 이벤트 블로킹.
> 커넥터가 RUNNING이어도 메시지가 발행되지 않는 증상 발생.
> 디버그: TRUNCATE 실행 후 `kafka-consumer-groups.sh` 로 LOG-END-OFFSET 확인 (0이면 블로킹 중).

```json
{
  "name": "outbox-connector",
  "config": {
    "connector.class": "io.debezium.connector.mysql.MySqlConnector",
    "tasks.max": "1",
    "database.hostname": "mysql",
    "database.port": "3306",
    "database.user": "debezium",
    "database.password": "${DEBEZIUM_PASSWORD}",
    "database.server.id": "1",
    "database.server.name": "alarm",
    "database.include.list": "alarm_db",
    "table.include.list": "alarm_db.outbox_event",
    "topic.prefix": "alarm",
    "include.schema.changes": "false",
    "snapshot.mode": "no_data",

    "transforms": "outbox",
    "transforms.outbox.type": "io.debezium.transforms.outbox.EventRouter",
    "transforms.outbox.table.field.event.id": "id",
    "transforms.outbox.table.field.event.key": "aggregate_id",
    "transforms.outbox.table.field.event.type": "event_type",
    "transforms.outbox.table.field.event.payload": "payload",
    "transforms.outbox.route.by.field": "aggregate_type",
    "transforms.outbox.route.topic.replacement": "notification.work",

    "schema.history.internal.kafka.bootstrap.servers": "kafka:29092",
    "schema.history.internal.kafka.topic": "schema-changes.alarm"
  }
}
```

### Connector 등록 명령어
```bash
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d @connector-config.json
```

### EventRouter 동작
```
outbox_event INSERT 감지
  → aggregate_type = "Notification"
  → route.topic.replacement = "notification.work"
  → key = aggregate_id (순서 보장)
  → value = payload (JSON)
```

## Polling Publisher (Debezium 대안/폴백)

CDC 없이 구현하는 가벼운 대안:

```kotlin
@Component
class OutboxPollingPublisher(
    private val outboxRepository: OutboxEventJpaRepository,
    private val kafkaTemplate: KafkaTemplate<String, String>,
    private val topicProperties: KafkaTopicProperties,
) {
    private val logger = LoggerFactory.getLogger(javaClass)

    @Scheduled(fixedDelayString = "\${outbox.polling.interval-ms:1000}")
    @Transactional
    fun publishPendingEvents() {
        val events = outboxRepository.findByCreatedAtBeforeOrderByCreatedAtAsc(
            LocalDateTime.now().minusSeconds(1),
            PageRequest.of(0, 100),
        )

        events.forEach { event ->
            try {
                kafkaTemplate.send(
                    topicProperties.work,
                    event.aggregateId.toString(),
                    event.payload,
                ).get(5, TimeUnit.SECONDS)  // 동기 전송 (순서 보장)

                outboxRepository.delete(event)  // 전송 성공 후 삭제
            } catch (e: Exception) {
                logger.error("Outbox 발행 실패: eventId=${event.id}", e)
                // 다음 폴링에서 재시도 (at-least-once)
            }
        }
    }
}
```

### CDC vs Polling Publisher 트레이드오프
| 항목 | CDC (Debezium) | Polling Publisher |
|------|---------------|-------------------|
| 지연 | 밀리초 | 폴링 간격 (1~5초) |
| 인프라 | Debezium + Kafka Connect | 없음 (스케줄러) |
| 순서 보장 | binlog 순서 | 쿼리 순서 (createdAt) |
| DB 부하 | binlog 읽기 (낮음) | 폴링 쿼리 (중간) |
| 운영 복잡도 | 높음 | 낮음 |
| 적합 규모 | 대규모 (>1,000 TPS) | 중소규모 (<1,000 TPS) |

## 멱등 Consumer

Outbox는 at-least-once 보장 → Consumer 멱등성 필수:

```kotlin
@Component
class IdempotentNotificationProcessor(
    private val duplicateChecker: DuplicateChecker,  // Redis SET NX
    private val notificationProcessor: NotificationProcessor,
) {
    fun process(message: NotificationMessage) {
        val idempotencyKey = "consume:notification:${message.id}"

        if (!duplicateChecker.checkAndMark(idempotencyKey)) {
            logger.info("중복 메시지 스킵: ${message.id}")
            return
        }

        notificationProcessor.process(message)
    }
}
```

## 장애 복구 시나리오

| 장애 | 영향 | 복구 |
|------|------|------|
| DB 장애 | Outbox 저장 실패 = 비즈니스 저장도 실패 | 트랜잭션 롤백, 클라이언트 재시도 |
| Debezium 장애 | 이벤트 전달 지연 | Debezium 재시작, offset부터 재개 |
| Kafka 장애 | 이벤트 전달 불가 | Kafka 복구 후 Debezium 자동 재개 |
| Consumer 장애 | 메시지 미처리 | Consumer 재시작, 마지막 commit offset부터 재개 |
| 전체 장애 | 모든 것 중단 | Outbox 테이블에 데이터 남아있음 → 순서대로 재처리 |

## 안티패턴

| 안티패턴 | 문제 | 해결 |
|----------|------|------|
| Outbox 없이 직접 Kafka 전송 | DB-Kafka 불일치 | Outbox 패턴 사용 |
| Outbox에 큰 payload 저장 | DB 부하 | 최소 정보만 저장, 상세는 Consumer가 조회 |
| Outbox 삭제 안 함 (CDC) | 테이블 무한 증가 | 배치 job으로 오래된 레코드 삭제 |
| Consumer 멱등성 미구현 | 중복 처리 | Redis SET NX로 중복 체크 |
| Debezium 모니터링 안 함 | 장애 감지 불가 | Connector 상태 헬스체크 |
