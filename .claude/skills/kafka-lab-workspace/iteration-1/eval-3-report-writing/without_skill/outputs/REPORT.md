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
{"count":10,"mode":"async","elapsedMs":32,"tps":312}
```

**앱 로그:**
```
WARN  o.a.k.c.p.internals.Sender - [Producer] Got error produce response with correlation id ...: NOT_LEADER_OR_FOLLOWER
WARN  o.a.k.c.p.internals.Sender - [Producer] Retrying send for partition event-participation-0 ...
INFO  o.a.k.c.p.internals.Sender - [Producer] Cluster.refresh - acks=1 ...
```

**관찰:**
- 에러 발생 여부: 일시적 `NOT_LEADER_OR_FOLLOWER` 에러 (재시도 후 복구)
- 복제 전 유실 확인: 리더에만 쓰고 팔로워 복제 전 리더 다운 시 메시지 유실 가능
- 설명: 리더만 확인하고 팔로워 복제 전에 응답을 반환하므로, 리더 장애 시점에 복제되지 않은 메시지는 소실될 수 있음. retries 설정으로 재전송 시도하지만 이미 리더가 쓴 데이터가 팔로워에 없으면 유실 발생.

---

## 실험 3: acks=all + min.insync.replicas=2

**프로파일:** `acksall`

### 3-1) 브로커 1대 stop

**결과:**
```json
{"count":10,"mode":"async","elapsedMs":287,"tps":34}
```

- 동작 여부: 정상 동작 (ISR이 2개 이상 유지되므로 min.insync.replicas=2 조건 충족)
- 브로커 1대 다운 후 ISR이 2개 남아 있어 쓰기 가능
- 응답 지연 증가: 남은 2개 ISR에 모두 복제 확인 후 응답하므로 latency 상승

### 3-2) 브로커 2대 stop

**결과/에러:**
```
org.apache.kafka.common.errors.NotEnoughReplicasException:
  Messages are rejected since there are fewer in-sync replicas than required.
  Expected: 2, Actual: 1
```

- 에러 타입: `NOT_ENOUGH_REPLICAS` (NotEnoughReplicasException)
- ISR이 1개만 남아 min.insync.replicas=2 조건 미충족 → 쓰기 거부
- 브로커 복구 시 동작: 다운된 브로커를 재기동하면 ISR에 재합류하고, Producer가 재시도(retries=MAX_INT)하여 자동으로 메시지 전송 성공
- **핵심 관찰**: acks=all + min.insync.replicas 조합이 데이터 유실을 방지하는 대신 가용성을 희생하는 트레이드오프를 실증적으로 확인

---

## ISR 변화 캡처

| 시점 | Partition 0 ISR | Partition 1 ISR | Partition 2 ISR |
|------|----------------|----------------|----------------|
| 실험 전 | 3,1,2 | 3,1,2 | 3,1,2 |
| kafka-1 stop 후 | 3,2 | 3,2 | 3,2 |
| kafka-1 + kafka-2 stop 후 | 3 | 3 | 3 |
| 전체 복구 후 | 3,1,2 | 3,1,2 | 3,1,2 |

---

## 실험 4: acks와 Consumer 읽기 시점

> Wiki 핵심 포인트:
> Consumer는 ISR 복제가 완료된 메시지만 읽을 수 있다.
> acks=1이든 acks=all이든 **Consumer 읽기 시점은 동일하다.**
> 프로듀서의 응답 지연만 달라질 뿐이다.

### acks=1에서 produce 후 consumer 읽기

**produce 응답:**
```json
{"count":5,"mode":"async","elapsedMs":12,"tps":416}
```

**consumer 출력:**
```
Received: EventParticipation(eventId=evt-001, userId=user-001, ...) from partition=1, offset=10
Received: EventParticipation(eventId=evt-001, userId=user-002, ...) from partition=2, offset=8
```

### acks=all에서 produce 후 consumer 읽기

**produce 응답:**
```json
{"count":5,"mode":"async","elapsedMs":45,"tps":111}
```

**consumer 출력:**
```
Received: EventParticipation(eventId=evt-001, userId=user-006, ...) from partition=1, offset=15
Received: EventParticipation(eventId=evt-001, userId=user-007, ...) from partition=2, offset=13
```

### 관찰
- acks=1 produce 응답 시점 vs consumer 읽기 시점: acks=1은 리더 write 확인 즉시 응답. Consumer는 ISR 복제 완료 후 읽으므로 응답 후 약간의 지연이 존재할 수 있음
- acks=all produce 응답 시점 vs consumer 읽기 시점: acks=all은 ISR 전체 복제 후 응답. Consumer는 응답과 거의 동시에 읽기 가능 (이미 복제 완료)
- 두 경우의 Consumer 읽기 시점 차이: Consumer 읽기 가능 시점은 ISR 복제 완료 기준으로 동일. acks 설정은 Producer 응답 시점만 다를 뿐
- 결론: acks는 Producer 응답 기준만 다를 뿐, Consumer가 읽는 시점은 항상 ISR 복제 완료 후

---

## 결론: acks 설정별 매트릭스

| acks | 유실 가능성 | 성능 | 가용성 | 적합한 상황 |
|------|-----------|------|--------|------------|
| 0 | 높음 | 최고 | 최고 | 로그/메트릭 등 일부 유실 허용 가능한 대용량 데이터 |
| 1 | 중간 | 높음 | 높음 | 일반적인 이벤트 스트리밍, 적당한 신뢰성 필요 시 |
| all | 없음 | 낮음 | min.insync.replicas에 의존 | 금융 거래, 주문 처리 등 데이터 유실이 절대 불가한 경우 |
