# 로그 해석: NOT_ENOUGH_REPLICAS

## 발생 로그

```
[Producer clientId=producer-1] Got error produce response with correlation id 5 on topic-partition lab2-acks-0, retrying (2147483646 attempts left). Error: NOT_ENOUGH_REPLICAS
```

---

## 핵심 필드 분석

| 필드 | 값 | 의미 |
|------|----|------|
| `correlationId` | 5 | 5번째 PRODUCE 요청에서 에러 발생 |
| `topic-partition` | lab2-acks-0 | lab2-acks 토픽의 파티션 0 |
| `retrying` | 2147483646 attempts left | `retries=MAX_INT` → 사실상 무한 재시도 |
| `Error` | NOT_ENOUGH_REPLICAS | errorCode=19, ISR < min.insync.replicas |

---

## 원인: ISR < min.insync.replicas

**NOT_ENOUGH_REPLICAS** (errorCode=19)는 브로커가 PRODUCE 요청을 거부하며 돌려보내는 에러다.

발생 조건:
- `acks=all (-1)` 설정 상태에서
- 현재 파티션의 **ISR(In-Sync Replicas) 수 < `min.insync.replicas`** 일 때

lab2-3 실험 컨텍스트에서 보면, 실험 3-2 시나리오와 정확히 일치한다:
- `event-participation` 토픽의 `min.insync.replicas=2`
- 브로커 2대(kafka-2, kafka-3)를 stop → ISR=1 (리더 1대만 남음)
- ISR(1) < min.insync.replicas(2) → 브로커가 쓰기 거부 → NOT_ENOUGH_REPLICAS

---

## 재시도 횟수 `2147483646`의 의미

`2147483646 = Integer.MAX_VALUE - 1`

이는 `retries=Integer.MAX_VALUE` (2147483647)로 설정된 상태에서 **1회 시도 후 남은 횟수**다.

Spring Boot 3.x의 기본 Producer 설정:
- `enable.idempotence=true` → 자동으로 `retries=MAX_INT` 설정
- 즉, **사실상 무한 재시도** 설정

하지만 실제로는 무한정 재시도하지 않는다. **`delivery.timeout.ms=120000ms` (기본 120초)** 가 만료되면 `TimeoutException`으로 최종 실패한다.

```
TimeoutException: Expiring 1 record(s) for lab2-acks-0:
120001 ms has passed since batch creation
```

---

## 현재 상황 요약

1. Producer가 `acks=all` (또는 `acksall` 프로파일)로 PRODUCE 요청 전송
2. 브로커가 ISR 부족으로 거부 → NOT_ENOUGH_REPLICAS 반환
3. Producer가 `retries=MAX_INT` 설정에 따라 재시도 시작
4. `delivery.timeout.ms=120s` 만료까지 계속 재시도
5. 120초 후 → TimeoutException으로 최종 실패

---

## 확인할 것

현재 ISR 상태 확인:

```bash
docker exec kafka-1 /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server kafka-1:19092 \
  --describe --topic lab2-acks
```

`Isr:` 항목에 브로커가 몇 개 남아 있는지 확인한다. `min.insync.replicas` 설정값보다 적으면 이 에러가 계속 발생한다.

복구하려면 stop된 브로커를 다시 start해서 ISR을 min.insync.replicas 이상으로 맞춰야 한다.
