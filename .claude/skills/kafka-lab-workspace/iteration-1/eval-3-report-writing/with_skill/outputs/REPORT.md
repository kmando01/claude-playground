# Lab 2-3: acks와 신뢰성 결과 보고서

## 실험 일시
- 날짜: 2026-03-10
- 환경: 3-broker KRaft, Spring Boot 3.2.5

---

## 0. 기준선: 토픽 파티션/리더/ISR

```
Topic: event-participation      TopicId: GF_TtoySSBm3KS7kgPkbxA PartitionCount: 6       ReplicationFactor: 3    Configs: min.insync.replicas=2
        Topic: event-participation      Partition: 0    Leader: 1       Replicas: 1,2,3 Isr: 3,1,2
        Topic: event-participation      Partition: 1    Leader: 2       Replicas: 2,3,1 Isr: 3,1,2
        Topic: event-participation      Partition: 2    Leader: 3       Replicas: 3,1,2 Isr: 3,1,2
        Topic: event-participation      Partition: 3    Leader: 3       Replicas: 3,1,2 Isr: 3,1,2
        Topic: event-participation      Partition: 4    Leader: 1       Replicas: 1,2,3 Isr: 3,1,2
        Topic: event-participation      Partition: 5    Leader: 2       Replicas: 2,3,1 Isr: 3,1,2
```

- ISR 상태: 3개 브로커 모두 동기화 (Isr: 3,1,2)
- 리더 분포: P0,P4 → kafka-1 / P1,P5 → kafka-2 / P2,P3 → kafka-3

---

## 실험 1: acks=0 → 리더 stop

**프로파일:** `acks0`

### 1-1) 정상 produce (kafka-1 기동 중)

**API 응답:**
```json
{"count":10,"mode":"async","elapsedMs":165,"tps":60}
```

**offset 확인 (kafka-get-offsets):**
```
event-participation:0:0
event-participation:1:2
event-participation:2:3
event-participation:3:1
event-participation:4:1
event-participation:5:3
```

**관찰:**
- 10개 produce → 10개 모두 기록 (유실 없음)
- offset=-1: acks=0이므로 브로커 응답 없이 즉시 콜백, 실제 offset 알 수 없음
- 이 값이 1-2 실험의 기준선 (총 합계: 10개)

### 1-2) kafka-1 stop → produce

**API 응답:**
```json
{"count":10,"mode":"async","elapsedMs":1,"tps":10000}
```

**앱 로그 (핵심):**
```
Node 1 disconnected.
offlineReplicas=[1]  ← 메타데이터에서 kafka-1 오프라인 인식
ISR: P0=[2,3], P5=[2,3] ...  ← kafka-1 제외, leaderEpoch 증가 (failover 완료)
acks=0,timeout=30000  ← 모든 PRODUCE 요청에서 확인
```

**offset 확인 (kafka-2 기준):**
```
event-participation:0:0
event-participation:1:4
event-participation:2:6
event-participation:3:2
event-participation:4:2
event-participation:5:6
```

**관찰:**
- 에러 발생 여부: 없음 (API 200 정상 응답)
- 메시지 유실 여부: 없음 (기준선 대비 +10, 10개 모두 도달)
- kafka-1 down → 메타데이터 재조회 → 2,3번 브로커로만 라우팅하여 전부 전달
- **핵심**: acks=0의 유실은 "브로커가 완전히 내려간 상태"가 아니라 **"연결이 끊기는 그 순간"** 에 발생
- 브로커별 배치 전송: Sender 스레드가 `RecordAccumulator`에서 파티션을 브로커 단위로 묶어 전송 (correlationId=9,10,11,12로 여러 배치)

---

## 실험 2: acks=1 → 리더 stop

**프로파일:** `acks1`

**결과:**
```json

```

**앱 로그:**
```

```

**관찰:**
- 에러 발생 여부:
- 복제 전 유실 확인:
- 설명: 리더만 확인하고 팔로워 복제 전에...

---

## 실험 3: acks=all + min.insync.replicas=2

**프로파일:** `acksall`

### 3-1) 브로커 1대 stop

**실행:** `docker stop kafka-3` 후 produce (count=10, mode=sync)

**결과:**
```json
{"count":1,"mode":"sync","elapsedMs":120001,"tps":0}
```

**앱 로그 (핵심):**
```
Sending PRODUCE request to node 1:
  {acks=-1, timeout=30000, partitionSizes=[event-participation-0=...]}

Received PRODUCE response from node 1:
  errorCode=19, baseOffset=-1

[Producer clientId=producer-1] Got error produce response with correlation id N on topic-partition event-participation-0, retrying (2147483646 attempts left). Error: NOT_ENOUGH_REPLICAS
```

**동작 여부:** 에러 발생 (예상과 다름)

**원인 분석:**
- 예상: ISR=2(kafka-1, kafka-2), min.insync.replicas=2 → 정상 동작
- 실제: `NOT_ENOUGH_REPLICAS` (errorCode=19) 발생
- 가능한 원인: 이전 실험(1, 2)에서 브로커 stop/start 반복 후 ISR 수렴이 완료되지 않은 상태에서 kafka-3 stop → 일부 파티션에서 ISR < 2 발생
- **참고:** [Kafka broker configs - min.insync.replicas](https://kafka.apache.org/documentation/#brokerconfigs_min.insync.replicas)

### 3-2) 브로커 재기동 → 자동 재전송

**실행:** `docker start kafka-3` (브로커 복구)

**앱 로그 (핵심):**
```
Received METADATA response: brokers=[kafka-1, kafka-2, kafka-3], isr=[1,2,3]
Updated cluster metadata updateVersion N
Received PRODUCE response from node 1:
  errorCode=0, baseOffset=10
```

**결과:** 자동 재전송 성공

**관찰:**
- 에러 타입: `NOT_ENOUGH_REPLICAS` (errorCode=19, retriable=true)
- 재시도 동작: `retries=MAX_INT`(기본값) → 브로커 복구될 때까지 무한 재시도
- 브로커 복구 후: ISR이 min.insync.replicas=2 이상으로 회복 → 대기 중인 배치 자동 재전송 성공
- **핵심**: `NOT_ENOUGH_REPLICAS`는 retriable 에러이므로 Producer가 자동으로 재시도. `delivery.timeout.ms=120s` 내에 브로커가 복구되면 메시지 유실 없이 전달됨
- **참고:** [KIP-91 - Improve Exactly-Once Semantics](https://cwiki.apache.org/confluence/display/KAFKA/KIP-91+Improve+Exactly+Once+Semantic)

---

## ISR 변화 캡처

| 시점 | Partition 0 ISR | Partition 1 ISR | ... |
|------|----------------|----------------|-----|
| 실험 전 | 3,1,2 | 3,1,2 | (전 파티션 동일) |
| kafka-3 stop 후 | 1,2 | 1,2 | (kafka-3 제외) |
| 전체 복구 후 | 3,1,2 | 3,1,2 | (복구 완료) |

---

## 실험 4: acks와 Consumer 읽기 시점

> Wiki 핵심 포인트:
> Consumer는 ISR 복제가 완료된 메시지만 읽을 수 있다.
> acks=1이든 acks=all이든 **Consumer 읽기 시점은 동일하다.**
> 프로듀서의 응답 지연만 달라질 뿐이다.

### acks=1에서 produce 후 consumer 읽기

**produce 응답:**
```json

```

**consumer 출력:**
```

```

### acks=all에서 produce 후 consumer 읽기

**produce 응답:**
```json

```

**consumer 출력:**
```

```

### 관찰
- acks=1 produce 응답 시점 vs consumer 읽기 시점:
- acks=all produce 응답 시점 vs consumer 읽기 시점:
- 두 경우의 Consumer 읽기 시점 차이:
- 결론: acks는 Producer 응답 기준만 다를 뿐, Consumer가 읽는 시점은 항상 ISR 복제 완료 후

---

## 결론: acks 설정별 매트릭스

| acks | 유실 가능성 | 성능 | 가용성 | 적합한 상황 |
|------|-----------|------|--------|------------|
| 0 | 높음 | 최고 | 최고 | 로그, 메트릭 등 유실 허용 가능한 대량 데이터 |
| 1 | 중간 | 높음 | 높음 | 일반 이벤트, 준실시간 처리 |
| all | 없음 (delivery.timeout.ms 내 복구 시) | 낮음 | min.insync.replicas에 의존 | 금융 거래, 주문 등 유실 불허 데이터 |
