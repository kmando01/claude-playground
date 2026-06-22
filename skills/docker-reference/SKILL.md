---
name: docker-reference
description: Docker + docker-compose 인프라 구성 레퍼런스. docker-compose.yml 템플릿, 이미지 목록, 인프라 추가 절차, Graceful Shutdown, 운영 명령어 포함. 인프라 설정 시 참조.
---

# Docker 인프라 레퍼런스

## docker-compose 디렉토리 구조

```
project-root/
├── docker-compose.yml          # 로컬 개발용 인프라
├── docker-compose.override.yml # 개발자별 오버라이드 (선택)
├── docker/                     # Dockerfile 및 설정 파일
│   ├── mysql/
│   │   └── init.sql
│   ├── redis/
│   │   └── redis.conf
│   └── kafka/
└── .env.example
```

## docker-compose.yml 기본 템플릿

```yaml
version: '3.8'

services:
  mysql:
    image: mysql:8.0
    container_name: xxx-mysql
    ports:
      - "3306:3306"
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:-root}
      MYSQL_DATABASE: ${MYSQL_DATABASE:-xxx_db}
      MYSQL_CHARACTER_SET_SERVER: utf8mb4
      MYSQL_COLLATION_SERVER: utf8mb4_unicode_ci
    volumes:
      - mysql-data:/var/lib/mysql
      - ./docker/mysql/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: xxx-redis
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    container_name: xxx-zookeeper
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
    volumes:
      - zookeeper-data:/var/lib/zookeeper/data

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    container_name: xxx-kafka
    depends_on:
      zookeeper:
        condition: service_started
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
    volumes:
      - kafka-data:/var/lib/kafka/data

volumes:
  mysql-data:
  redis-data:
  zookeeper-data:
  kafka-data:
```

## 새 인프라 추가 예시 (Elasticsearch)

```yaml
elasticsearch:
  image: elasticsearch:8.11.0
  container_name: xxx-elasticsearch
  ports:
    - "9200:9200"
  environment:
    - discovery.type=single-node
    - xpack.security.enabled=false
    - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
  volumes:
    - elasticsearch-data:/usr/share/elasticsearch/data
  healthcheck:
    test: ["CMD-SHELL", "curl -f http://localhost:9200/_cluster/health || exit 1"]
    interval: 10s
    timeout: 5s
    retries: 5
```

## 인프라 추가 4단계

### 1. docker-compose.yml에 서비스 추가
### 2. application.yml에 연결 설정
```yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/xxx_db
    username: root
    password: root
  data:
    redis:
      host: localhost
      port: 6379
  kafka:
    bootstrap-servers: localhost:9092
```

### 3. infra 모듈에 Config 클래스
```kotlin
@Configuration
class RedisConfig {
    @Bean
    fun redisTemplate(connectionFactory: RedisConnectionFactory): RedisTemplate<String, Any> {
        return RedisTemplate<String, Any>().apply {
            setConnectionFactory(connectionFactory)
            keySerializer = StringRedisSerializer()
            valueSerializer = GenericJackson2JsonRedisSerializer()
        }
    }
}
```

### 4. Testcontainers 통합 테스트
```kotlin
@Testcontainers
class RedisIntegrationTest {
    companion object {
        @Container
        val redis = GenericContainer("redis:7-alpine").withExposedPorts(6379)

        @JvmStatic
        @DynamicPropertySource
        fun properties(registry: DynamicPropertyRegistry) {
            registry.add("spring.data.redis.host") { redis.host }
            registry.add("spring.data.redis.port") { redis.firstMappedPort }
        }
    }
}
```

## 자주 사용하는 인프라 이미지

| 인프라 | 이미지 | 포트 |
|--------|--------|------|
| MySQL | `mysql:8.0` | 3306 |
| PostgreSQL | `postgres:15` | 5432 |
| Redis | `redis:7-alpine` | 6379 |
| Kafka | `confluentinc/cp-kafka:7.5.0` | 9092 |
| Elasticsearch | `elasticsearch:8.11.0` | 9200 |
| MongoDB | `mongo:7` | 27017 |
| RabbitMQ | `rabbitmq:3-management` | 5672, 15672 |
| MinIO (S3) | `minio/minio` | 9000, 9001 |
| LocalStack | `localstack/localstack` | 4566 |
| Zipkin | `openzipkin/zipkin` | 9411 |

## Graceful Shutdown

```yaml
# application.yml
server:
  shutdown: graceful
spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
```

```
SIGTERM → 새 요청 거부 (503) → 진행 중 요청 완료 대기 (30초) → Bean 소멸 → 프로세스 종료
```

```kotlin
@Component
class GracefulShutdownHandler(
    private val kafkaListenerEndpointRegistry: KafkaListenerEndpointRegistry
) {
    @PreDestroy
    fun onShutdown() {
        kafkaListenerEndpointRegistry.stop()
    }
}
```

```yaml
# docker-compose
services:
  app:
    stop_grace_period: 40s  # Spring 30s + 여유 10s
```

## 운영 명령어

```bash
docker-compose up -d                  # 전체 시작
docker-compose up -d mysql redis      # 특정 서비스
docker-compose logs -f mysql          # 로그
docker-compose ps                     # 상태
docker-compose down                   # 중지
docker-compose down -v                # 볼륨 포함 삭제
docker-compose restart redis          # 재시작
```

## .env.example

```env
MYSQL_ROOT_PASSWORD=root
MYSQL_DATABASE=xxx_db
REDIS_PORT=6379
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
```

## Anti-Patterns

```yaml
# BAD → GOOD
image: mysql:latest          → image: mysql:8.0
- /Users/me/data:/var/lib/   → - mysql-data:/var/lib/mysql
MYSQL_ROOT_PASSWORD: secret  → MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:-root}
depends_on: [mysql]          → depends_on: { mysql: { condition: service_healthy } }
```
