# Kafka 로그 패턴 해석 가이드

## PRODUCE 요청/응답 핵심 필드

```
Sending PRODUCE request to node {N}:
  {acks=-1, timeout=30000, partitionSizes=[topic-{P}={bytes}]}
  correlationId={id}

Received PRODUCE response from node {N}:
  errorCode={code}, baseOffset={offset}
```

| 필드 | 의미 |
|------|------|
| `node {N}` | 현재 파티션 리더 브로커 |
| `acks=-1` | acks=all |
| `timeout=30000` | request.timeout.ms (30초) |
| `partitionSizes` | 배치 크기 (bytes) |
| `correlationId` | 요청 식별자 (순서 보장 확인용) |
| `errorCode=0` | 성공 |
| `errorCode=19` | NOT_ENOUGH_REPLICAS |
| `baseOffset=-1` | 저장 실패 (에러 응답) |

## 주요 에러 코드

| errorCode | 이름 | 재시도 | 원인 |
|-----------|------|--------|------|
| 0 | SUCCESS | - | 성공 |
| 19 | NOT_ENOUGH_REPLICAS | O | ISR < min.insync.replicas |
| 10 | MESSAGE_TOO_LARGE | X | max.request.size 초과 (클라이언트) |
| 3 | UNKNOWN_TOPIC | O | 토픽 없음 (auto.create=true면 생성) |

## 초기화 로그 패턴

```
Instantiated an idempotent producer  → enable.idempotence=true
ProducerId set to {N} with epoch 0   → 브로커에서 PID 발급
Cluster ID: Some({id})               → 메타데이터 조회 성공
Node -2 disconnected                 → 정상 (가상 노드, 초기화 과정)
```

## 재시도 패턴

```
retrying (2147483646 attempts left). Error: NOT_ENOUGH_REPLICAS
```
- `retries=MAX_INT` → 사실상 무한 재시도
- `delivery.timeout.ms=120s` 후 TimeoutException
- idempotent producer: delivery.timeout.ms 만료 후 TimeoutException 발생 (무력화 아님)

## TimeoutException 패턴

```
TimeoutException: Expiring 1 record(s) for {topic}-{partition}:
120001 ms has passed since batch creation
```
- `delivery.timeout.ms` 정상 동작
- `120001ms` = delivery.timeout.ms(120000) + 1ms 오차

## 메타데이터 갱신 패턴 (리더 재선출 후)

```
Sending metadata request to node localhost:9093 (id: 2)
Received METADATA response: brokers=[...], isr=[2,3], offlineReplicas=[1]
Updating last seen epoch for partition {topic}-{N} from {old} to epoch {new}
Updated cluster metadata updateVersion {N}
```
- 브로커 down 후 클라이언트가 새 리더를 감지하는 과정
- `leaderEpoch` 증가 → 새 리더 선출됨

## ISR 상태 해석

```
Partition: 0  Leader: 2  Replicas: 2,3,1  Isr: 2,3
```

| 항목 | 의미 |
|------|------|
| `Leader` | 현재 읽기/쓰기 담당 브로커 |
| `Replicas` | 복제본 위치 (첫 번째 = preferred leader) |
| `Isr` | 현재 리더와 동기화된 브로커 목록 |
| `offlineReplicas` | 오프라인 브로커 |

`Isr < min.insync.replicas` → acks=all produce 불가
