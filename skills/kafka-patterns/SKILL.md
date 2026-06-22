---
name: kafka-patterns
description: Kafka Producer/Consumer 패턴 레퍼런스. Producer 설정(ack, idempotent, 배치), Consumer 패턴(수동 commit, 에러 핸들링), 3단계 DLQ(work→retry→dead), 토픽 설계, Testcontainers 테스트 포함. Kafka 연동 구현 시 참조.
---

# Kafka Patterns

## 모듈 배치
- **infra**: KafkaConfig, Producer, Consumer 구현
- **domain**: 이벤트 정의, Port 인터페이스
- **consumer (app-batch)**: `@KafkaListener` 진입점

## 의존성 (libs.versions.toml)
```toml
[versions]
spring-kafka = "3.3.1"

[libraries]
spring-kafka = { module = "org.springframework.kafka:spring-kafka", version.ref = "spring-kafka" }
spring-kafka-test = { module = "org.springframework.kafka:spring-kafka-test", version.ref = "spring-kafka" }
```

## Producer 설정

### application.yml
```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    producer:
      acks: all                    # 모든 replica 확인
      retries: 3
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        enable.idempotence: true   # 중복 전송 방지
        max.in.flight.requests.per.connection: 5  # idempotent 모드에서 허용
        linger.ms: 5               # 배치 대기 시간
        batch.size: 16384          # 배치 크기 (16KB)
        compression.type: lz4      # 압축
```

### @ConfigurationProperties
```kotlin
@ConfigurationProperties(prefix = "kafka.topic")
data class KafkaTopicProperties(
    val work: String = "notification.work",
    val retry: String = "notification.retry",
    val dead: String = "notification.dead",
    val partitions: Int = 10,
    val replication: Short = 3,
    val retryMaxAttempts: Int = 3,
    val retryBackoffMs: Long = 5000,
)
```

### Producer 구현 (infra)
```kotlin
@Component
class NotificationKafkaProducer(
    private val kafkaTemplate: KafkaTemplate<String, Any>,
    private val topicProperties: KafkaTopicProperties,
) {
    private val logger = LoggerFactory.getLogger(javaClass)

    fun send(notificationId: Long, payload: NotificationMessage) {
        val key = notificationId.toString()  // 파티션 키 = ID (순서 보장)
        kafkaTemplate.send(topicProperties.work, key, payload)
            .whenComplete { result, ex ->
                if (ex != null) {
                    logger.error("Kafka 전송 실패: notificationId=$notificationId", ex)
                } else {
                    logger.info("Kafka 전송 성공: topic=${result.recordMetadata.topic()}, " +
                        "partition=${result.recordMetadata.partition()}, offset=${result.recordMetadata.offset()}")
                }
            }
    }
}
```

## Consumer 설정

### application.yml
```yaml
spring:
  kafka:
    consumer:
      group-id: ${KAFKA_GROUP_ID:alarm-consumer-group}
      auto-offset-reset: earliest
      enable-auto-commit: false    # 수동 commit 필수
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: "com.alarm.*"
        max.poll.records: 100      # 한 번에 가져올 레코드 수
        max.poll.interval.ms: 300000  # 5분 내 처리 못하면 리밸런스
        session.timeout.ms: 30000
    listener:
      ack-mode: manual             # 수동 ACK
      concurrency: 3               # Consumer 스레드 수
```

### Consumer 구현 (consumer 모듈)
```kotlin
@Component
class NotificationKafkaConsumer(
    private val notificationProcessor: NotificationProcessor,
    private val topicProperties: KafkaTopicProperties,
    private val kafkaTemplate: KafkaTemplate<String, Any>,
) {
    private val logger = LoggerFactory.getLogger(javaClass)

    @KafkaListener(
        topics = ["#{@kafkaTopicProperties.work}"],
        groupId = "\${spring.kafka.consumer.group-id}",
        containerFactory = "kafkaListenerContainerFactory",
    )
    fun consumeWork(
        record: ConsumerRecord<String, NotificationMessage>,
        ack: Acknowledgment,
    ) {
        try {
            notificationProcessor.process(record.value())
            ack.acknowledge()  // 성공 시에만 commit
        } catch (e: RetryableException) {
            logger.warn("재시도 가능 오류, retry 토픽으로 전송: ${record.key()}", e)
            sendToRetry(record)
            ack.acknowledge()  // 원본은 commit (retry로 넘김)
        } catch (e: Exception) {
            logger.error("처리 불가 오류, dead 토픽으로 전송: ${record.key()}", e)
            sendToDead(record, e)
            ack.acknowledge()
        }
    }

    @KafkaListener(
        topics = ["#{@kafkaTopicProperties.retry}"],
        groupId = "\${spring.kafka.consumer.group-id}-retry",
    )
    fun consumeRetry(
        record: ConsumerRecord<String, NotificationMessage>,
        ack: Acknowledgment,
    ) {
        val attempt = getRetryCount(record) + 1
        try {
            notificationProcessor.process(record.value())
            ack.acknowledge()
        } catch (e: Exception) {
            if (attempt >= topicProperties.retryMaxAttempts) {
                logger.error("최대 재시도 초과($attempt), dead로 전송: ${record.key()}", e)
                sendToDead(record, e)
            } else {
                logger.warn("재시도 $attempt/${topicProperties.retryMaxAttempts}: ${record.key()}", e)
                sendToRetry(record, attempt)
            }
            ack.acknowledge()
        }
    }

    private fun sendToRetry(record: ConsumerRecord<String, NotificationMessage>, attempt: Int = 1) {
        val headers = record.headers().toMutableList()
        kafkaTemplate.send(
            ProducerRecord(topicProperties.retry, null, record.key(), record.value(),
                RecordHeaders().apply {
                    add("retry-count", attempt.toString().toByteArray())
                    add("original-topic", topicProperties.work.toByteArray())
                })
        )
    }

    private fun sendToDead(record: ConsumerRecord<String, NotificationMessage>, error: Exception) {
        kafkaTemplate.send(
            ProducerRecord(topicProperties.dead, null, record.key(), record.value(),
                RecordHeaders().apply {
                    add("error-message", error.message?.toByteArray() ?: byteArrayOf())
                    add("error-class", error.javaClass.name.toByteArray())
                    add("original-topic", topicProperties.work.toByteArray())
                })
        )
    }

    private fun getRetryCount(record: ConsumerRecord<String, *>): Int {
        return record.headers().lastHeader("retry-count")
            ?.value()?.let { String(it).toIntOrNull() } ?: 0
    }
}
```

## 토픽 설계

### 3단계 DLQ 전략
```
work (정상 처리)
  ├── 성공 → ACK
  └── 실패 → retry (재시도 가능 에러)
          ├── 성공 → ACK
          └── 실패 (maxAttempts 초과) → dead (수동 처리)
```

### 토픽 자동 생성 (KafkaConfig)
```kotlin
@Configuration
class KafkaTopicConfig(
    private val topicProperties: KafkaTopicProperties,
) {
    @Bean
    fun workTopic(): NewTopic = TopicBuilder
        .name(topicProperties.work)
        .partitions(topicProperties.partitions)
        .replicas(topicProperties.replication.toInt())
        .config(TopicConfig.RETENTION_MS_CONFIG, "604800000") // 7일
        .build()

    @Bean
    fun retryTopic(): NewTopic = TopicBuilder
        .name(topicProperties.retry)
        .partitions(topicProperties.partitions)
        .replicas(topicProperties.replication.toInt())
        .config(TopicConfig.RETENTION_MS_CONFIG, "604800000")
        .build()

    @Bean
    fun deadTopic(): NewTopic = TopicBuilder
        .name(topicProperties.dead)
        .partitions(1)  // DLQ는 파티션 1개 (순서 무관)
        .replicas(topicProperties.replication.toInt())
        .config(TopicConfig.RETENTION_MS_CONFIG, "-1") // 무기한 보관
        .build()
}
```

### 파티셔닝 전략
| 키 | 목적 | 효과 |
|---|------|------|
| notificationId | 같은 알림 순서 보장 | 재시도 시 순서 유지 |
| userId | 같은 유저 순서 보장 | 유저별 알림 순서 유지 |
| channelType | 채널별 분산 | 채널별 처리량 격리 |

## ContainerFactory 설정
```kotlin
@Configuration
class KafkaConsumerConfig {

    @Bean
    fun kafkaListenerContainerFactory(
        consumerFactory: ConsumerFactory<String, Any>,
    ): ConcurrentKafkaListenerContainerFactory<String, Any> {
        return ConcurrentKafkaListenerContainerFactory<String, Any>().apply {
            this.consumerFactory = consumerFactory
            containerProperties.ackMode = ContainerProperties.AckMode.MANUAL
            // 에러 핸들링은 Consumer에서 직접 처리 (3단계 DLQ)
        }
    }
}
```

## 테스트

### Testcontainers + Kafka
```kotlin
@SpringBootTest
@Testcontainers
class NotificationKafkaConsumerTest {

    companion object {
        @Container
        val kafka = KafkaContainer(DockerImageName.parse("confluentinc/cp-kafka:7.6.0"))

        @JvmStatic
        @DynamicPropertySource
        fun kafkaProperties(registry: DynamicPropertyRegistry) {
            registry.add("spring.kafka.bootstrap-servers") { kafka.bootstrapServers }
        }
    }

    @Autowired
    private lateinit var kafkaTemplate: KafkaTemplate<String, Any>

    @Autowired
    private lateinit var topicProperties: KafkaTopicProperties

    @Test
    fun `work 토픽 메시지를 정상 처리한다`() {
        // given
        val message = NotificationMessage(id = 1L, channel = "SMS", recipient = "010-1234-5678")

        // when
        kafkaTemplate.send(topicProperties.work, "1", message).get()

        // then
        await().atMost(Duration.ofSeconds(10)).untilAsserted {
            // 처리 결과 검증
        }
    }

    @Test
    fun `처리 실패 시 retry 토픽으로 전송한다`() {
        // given: 실패하는 메시지
        val message = NotificationMessage(id = -1L, channel = "INVALID", recipient = "")

        // when
        kafkaTemplate.send(topicProperties.work, "-1", message).get()

        // then: retry 토픽에서 메시지 확인
        val consumer = createConsumer(topicProperties.retry)
        await().atMost(Duration.ofSeconds(10)).untilAsserted {
            val records = consumer.poll(Duration.ofMillis(500))
            assertThat(records.count()).isGreaterThan(0)
        }
    }
}
```

## 안티패턴

| 안티패턴 | 문제 | 해결 |
|----------|------|------|
| auto-commit 사용 | 처리 전 commit → 메시지 유실 | `enable-auto-commit: false` + 수동 ACK |
| 무한 재시도 | Consumer 블로킹, 메시지 적체 | maxAttempts 제한 + DLQ |
| key 없이 전송 | 순서 보장 불가 | 비즈니스 키로 파티셔닝 |
| Consumer에서 긴 작업 | poll timeout → 리밸런스 | 비동기 처리 or max.poll.records 조절 |
| trusted.packages: * | 역직렬화 보안 취약 | 특정 패키지만 허용 |
| DLQ 모니터링 안 함 | 실패 메시지 방치 | DLQ Consumer + 알림 설정 |
