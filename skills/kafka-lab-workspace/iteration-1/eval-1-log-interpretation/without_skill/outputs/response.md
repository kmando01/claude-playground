# Kafka 로그 분석: NOT_ENOUGH_REPLICAS 에러

## 로그 원문

```
[Producer clientId=producer-1] Got error produce response with correlation id 5 on topic-partition lab2-acks-0, retrying (2147483646 attempts left). Error: NOT_ENOUGH_REPLICAS
```

## 이 로그가 의미하는 것

### 에러 원인

`NOT_ENOUGH_REPLICAS`는 Kafka 브로커가 Producer로부터 메시지를 받았지만, **토픽의 `min.insync.replicas` 설정을 충족할 만큼 충분한 ISR(In-Sync Replicas)이 없을 때** 발생하는 에러입니다.

쉽게 말하면:

- 토픽이 "최소 N개의 브로커가 동기화 상태여야 쓰기를 허용한다"고 설정되어 있는데
- 현재 실제로 동기화 상태인 브로커 수가 그 최솟값보다 적은 상황

### 각 필드 설명

| 필드 | 값 | 의미 |
|------|-----|------|
| `clientId=producer-1` | producer-1 | 이 메시지를 보낸 Producer 식별자 |
| `correlation id 5` | 5 | Producer가 요청을 보낼 때 붙인 고유 식별 번호 (요청-응답 매칭용) |
| `topic-partition lab2-acks-0` | lab2-acks 토픽의 0번 파티션 | 에러가 발생한 토픽과 파티션 |
| `retrying (2147483646 attempts left)` | 약 21억 번 남음 | 재시도 횟수 (Integer.MAX_VALUE - 1). `retries=Integer.MAX_VALUE`가 기본값임을 의미 |
| `Error: NOT_ENOUGH_REPLICAS` | - | 실제 에러 코드 |

### `retrying (2147483646 attempts left)` 의 의미

`2147483646`은 `Integer.MAX_VALUE(2147483647) - 1`입니다.

Spring Boot 3.x의 Producer 기본 설정은 `retries=Integer.MAX_VALUE`이며, 이미 1번 재시도가 이루어졌기 때문에 남은 횟수가 `2147483646`으로 표시되는 것입니다. 즉, Producer가 **사실상 무한 재시도** 설정으로 동작하고 있다는 뜻입니다.

## lab2-3 컨텍스트에서의 해석

lab2-3은 `acks` 설정 실험을 하는 랩입니다. 이 에러가 발생한 상황은 다음과 같이 추정됩니다:

### 전형적인 발생 시나리오

```
토픽 설정:
  - replication.factor = 3 (브로커 3개에 복제)
  - min.insync.replicas = 2 (최소 2개 ISR 필요)

Producer 설정:
  - acks = all (또는 acks = -1)
    → 모든 ISR이 확인해야 성공으로 처리

문제 상황:
  - 브로커 1대가 다운되거나 리더와 동기화가 끊김
  - ISR이 1개만 남음 (리더만 살아있음)
  - min.insync.replicas = 2를 충족하지 못함
  → NOT_ENOUGH_REPLICAS 에러 발생
```

### acks 설정과의 관계

| acks 설정 | NOT_ENOUGH_REPLICAS 발생 여부 |
|-----------|-------------------------------|
| `acks=0` | 발생 안 함 (응답 자체를 안 기다림) |
| `acks=1` | 발생 안 함 (리더만 확인) |
| `acks=-1` (all) | **발생함** (ISR 전체 확인 필요) |

`acks=all`일 때만 이 에러가 의미 있습니다. 리더 브로커는 요청을 받았지만, ISR 조건을 충족하지 못하므로 클라이언트에게 에러를 반환한 것입니다.

## 정리

이 로그의 핵심 메시지는:

1. **Producer가 메시지를 보냈지만 브로커가 거부했다** - 브로커가 다운되거나 네트워크 문제 등으로 ISR 수가 `min.insync.replicas` 미만으로 떨어졌기 때문
2. **Producer는 자동으로 재시도 중이다** - 거의 무한에 가까운 횟수로 재시도 설정이 되어 있어, 브로커가 복구되면 자동으로 메시지 전송이 성공될 것
3. **데이터 유실은 없다** - 메시지가 유실된 게 아니라 Producer 쪽 버퍼에 남아 있으며, 조건이 충족되면 전송됨

lab2-3에서 의도적으로 브로커를 종료하거나 ISR 조건을 맞추지 않은 상태에서 `acks=all`로 메시지를 보냈다면, 이 로그는 **정상적인 실험 결과**입니다.
