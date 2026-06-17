# Lab 2-4 commands.sh 사전 검증 결과

## 실험 개요

Lab 2-4는 **배치와 처리량 튜닝** 실험입니다. 5개 프로파일(A~E)을 비교하고, 실험 F에서 `buffer.memory` 포화로 인한 `TimeoutException`을 유도합니다.

---

## 사전 검증 체크리스트

### 인프라 체크 (실험 전 실행 권장)

```bash
# 브로커 상태
docker ps | grep kafka

# 토픽 상태
docker exec kafka-1 /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server kafka-1:19092 \
  --describe --topic event-participation

# 앱 상태
curl -s http://localhost:8080/actuator/health | jq .
```

---

## commands.sh 검증 결과

### 발견된 문제점

#### 1. Spring Profile YAML 파일 미존재 (Critical)

commands.sh에서 사용하는 프로파일:
- `batch-A`, `batch-B`, `batch-C`, `batch-D`, `batch-E`

현재 `src/main/resources/`에 존재하는 profile YAML:
- `application-small-buffer.yml` (실험 F용) - **존재**
- `application-inflight1.yml`, `application-inflight5.yml` 등
- `application-acks0.yml`, `application-acks1.yml`, `application-acksall.yml`

**`application-batch-A.yml` ~ `application-batch-E.yml` 파일이 전혀 없습니다.**

이 상태에서 `SPRING_PROFILES_ACTIVE=batch-A ./gradlew bootRun`을 실행하면 Spring Boot가 해당 프로파일 파일을 찾지 못해 **기본 설정(application.yml)만 로드**됩니다. 프로파일이 없어도 오류 없이 실행되므로 의도한 설정이 적용되지 않은 채로 실험이 진행될 수 있습니다.

#### 2. 앱 포트 불일치 (Warning)

`application.yml`의 서버 포트는 `8082`인데, commands.sh의 curl은 `8080`을 사용합니다.

```yaml
# application.yml
server:
  port: 8082
```

```bash
# commands.sh - 잘못된 포트
curl -s -X POST http://localhost:8080/api/labs/produce-bulk
```

실제 앱 기동 포트를 확인하고, curl 호출 URL을 맞춰야 합니다.

#### 3. eventType 필드 불일치

프로파일 A~D의 request body에는 `eventType` 필드가 없고, 프로파일 E에만 포함되어 있습니다.

```bash
# 프로파일 A (eventType 없음)
-d '{"count": 100000, "mode": "async", "eventId": "EVT-BATCH-A"}'

# 프로파일 E (eventType 있음)
-d '{"count": 100000, "mode": "async", "eventId": "EVT-BATCH-E", "eventType": "EVENT"}'
```

`eventType`이 필수 필드라면 A~D에도 추가해야 합니다. 실험 F에도 `"eventType": "EVENT"`가 포함되어 있으므로, 일관성을 위해 A~D에도 추가하는 것을 권장합니다.

#### 4. 실험 F: small-buffer 프로파일은 존재 (정상)

`application-small-buffer.yml` 파일이 존재하며 내용 확인:

```yaml
spring:
  kafka:
    producer:
      properties:
        buffer.memory: 1048576  # 1MB
        linger.ms: 100
        max.block.ms: 3000
```

commands.sh의 주석(`# buffer.memory=1MB, linger.ms=100, max.block.ms=3000`)과 일치합니다.

---

## 수정 필요 사항 요약

| 우선순위 | 항목 | 조치 |
|---------|------|------|
| Critical | `application-batch-A~E.yml` 파일 없음 | 각 프로파일 YAML 생성 필요 |
| Warning | curl 포트 8080 vs 앱 포트 8082 | 실제 기동 포트 확인 후 통일 |
| Minor | 프로파일 A~D에 `eventType` 누락 | `"eventType": "EVENT"` 추가 권장 |

---

## 생성 필요한 Profile YAML

실험을 진행하려면 다음 5개 파일을 생성해야 합니다.

### `application-batch-A.yml` (기본값과 동일하지만 명시적 선언)

```yaml
spring:
  kafka:
    producer:
      properties:
        batch.size: 16384      # 16KB
        linger.ms: 0
        compression.type: none
        buffer.memory: 33554432  # 32MB
```

### `application-batch-B.yml`

```yaml
spring:
  kafka:
    producer:
      properties:
        batch.size: 65536      # 64KB
        linger.ms: 5
        compression.type: none
        buffer.memory: 33554432  # 32MB
```

### `application-batch-C.yml`

```yaml
spring:
  kafka:
    producer:
      properties:
        batch.size: 65536      # 64KB
        linger.ms: 20
        compression.type: snappy
        buffer.memory: 33554432  # 32MB
```

### `application-batch-D.yml`

```yaml
spring:
  kafka:
    producer:
      properties:
        batch.size: 131072     # 128KB
        linger.ms: 50
        compression.type: snappy
        buffer.memory: 67108864  # 64MB
```

### `application-batch-E.yml`

```yaml
spring:
  kafka:
    producer:
      properties:
        batch.size: 65536      # 64KB
        linger.ms: 5
        compression.type: lz4
        buffer.memory: 33554432  # 32MB
```

---

## 실험 순서 및 예상 결과

### 프로파일 A~E (처리량 비교)

각 프로파일마다:
1. 앱 재시작: `SPRING_PROFILES_ACTIVE=batch-X ./gradlew bootRun`
2. 앱 기동 로그에서 설정값 확인 (batch.size, linger.ms, compression.type 로그 출력 확인)
3. curl 실행 (10만건 async)
4. API 응답의 소요시간(ms), TPS 기록

**예상 순서 (처리량 높은 순):**
- D (128KB + 50ms + snappy) > C (64KB + 20ms + snappy) > E (64KB + 5ms + lz4) > B (64KB + 5ms + none) > A (16KB + 0ms + none)
- batch.size와 linger.ms를 높일수록 배치가 커져 네트워크 왕복 횟수가 줄어들어 TPS 향상
- 단, linger.ms가 높을수록 개별 메시지의 지연시간(latency)은 증가

### 실험 F (TimeoutException 유도)

1. `SPRING_PROFILES_ACTIVE=small-buffer ./gradlew bootRun` 으로 앱 재시작
2. `docker stop kafka-1` 실행 → 브로커 1대 다운
3. **약 5~10초 대기** (ISR 변화 타이밍 고려)
4. curl 실행 (1만건 async)
5. max.block.ms=3000ms 이후 TimeoutException 발생 확인

**예상 로그 패턴:**
```
org.apache.kafka.common.errors.TimeoutException: Failed to allocate memory within the configured max blocking time
```

**주의:** 브로커 복구(`docker start kafka-1`)를 반드시 실행 후 다음 실험으로 넘어갈 것.

---

## 진행 권장 순서

1. Profile YAML 5개 파일 생성 (위 내용 참조)
2. 포트 확인: `curl -s http://localhost:8082/actuator/health | jq .`
3. 프로파일 A부터 순서대로 실험
4. 각 실험 후 결과를 REPORT.md에 기록
5. 실험 F는 마지막에 (브로커 down 상태에서 다른 실험 방해 방지)
