# Kafka Rate Limit 패턴 — 실험으로 증명하기 (v2)

> 실험 일자: 2026-06-21
> 검증 강도: ★★★★☆ (4/5) — 5개 시나리오, 메시지 10K, 단일 컨슈머, localhost 환경
> v1 대비 변경: 동시 처리 도입(H1 재설계), seek() 추가(H5 직접 측정), 그룹 삭제 자동화

---

## 1. 결론 요약

| 가설 | 결과 | 결정적 수치 |
|---|---|---|
| H1: burst 크기 감소 → 429 감소 | **✓ 확인** | A(burst=200): 88.9% → B(burst=30): 58.8% |
| H2: pause/resume 영향 격리 | **✓ 확인** | C max_retries_per_msg=1 (cascade 없음) |
| H3: poll 누락 → rebalance | **✓ 확인** | 20s sleep → REVOKE+REBALANCE 즉시 발생 |
| H4: Token Bucket → 429≈0 | **✓ 완벽** | D: 10,000건 처리 중 429 = 0건 |
| H5: at-least-once 동작 | **✓ 직접 확인** | 158건이 429 후 동일 message_id로 재처리 성공 |

> **H5 핵심 발견**: `pause/resume`만으로는 at-least-once가 보장되지 않는다. **`consumer.seek(tp, msg.offset)`이 필수**. seek 없이는 Kafka position이 429 받은 메시지를 지나쳐버려 해당 메시지가 현재 세션에서 영구 스킵된다.

---

## 2. 실험 환경

| 항목 | 값 |
|---|---|
| Kafka 버전 | apache/kafka 3.9.0 (KRaft 모드, JVM 직접 실행) |
| Kafka 클라이언트 | kafka-python 3.0.2 |
| Python 버전 | 3.9.6 |
| OS / 하드웨어 | macOS 14 / Apple Silicon (localhost 네트워크) |
| 토픽 파티션 수 | 4 |
| 메시지 적재 수 | 10,000 |
| 외부 API rate limit | 100 req/s (슬라이딩 윈도우 1s) |
| Token Bucket rate (D) | 80/s, burst capacity=20 |
| `max.poll.interval.ms` (E만) | 15,000ms |
| mock API 응답 지연 | 0ms |

---

## 3. 결과 — 시나리오 비교

| 지표 | A (Naive) | B (Static) | C (Reactive) | D (Proactive) | E (Rebalance) |
|---|---|---|---|---|---|
| **처리 방식** | 동시 burst=200 | 동시 burst=30 | 순차 + pause/resume | 순차 + TokenBucket | 순차 (rebalance 유도) |
| 총 API 호출 | 89,775 | 24,301 | 10,158 | 10,000 | 151 |
| 성공(200) | 10,000 | 10,000 | 10,000 | 10,000 | 150 |
| **429 횟수** | **79,775** | **14,301** | **158** | **0** | 1 |
| **429 비율** | **88.9%** | **58.8%** | **1.6%** | **0.0%** | 0.7% |
| max_retries/msg | **25** | **12** | **1** | 0 | — |
| 재처리 메시지 수 (H5) | 7,283 | 6,670 | **158** | 0 | — |
| 평균 시도 횟수/재처리 | 12.0회 | 3.1회 | **2.0회** | — | — |
| 총 소요 시간 | 172s | 106s | 110s | 128s | ~45s |
| Rebalance 횟수 | 0 | 0 | 0 | 0 | **2** |

---

## 4. 가설별 상세 분석

### H1 — burst 크기 감소 → 429 감소 ✓ **확인**

비교: A (동시 200개) vs B (동시 30개), 같은 retry 로직, 같은 10,000건 처리

```
429 비율: A 88.9% → B 58.8% (30%p 감소)
총 429수: A 79,775건 → B 14,301건 (5.6배 감소)
최대 재시도/메시지: A 25회 → B 12회 (2배 차이)
처리 시간: A 172s → B 106s (B가 38% 빠름)
```

**메커니즘**: 200개를 동시에 발화하면 100개 초과분이 모두 429를 받고 rate limit window(1초)가 채워진다. 이후 50ms마다 재시도하지만 window가 가득 찬 동안은 계속 실패 → cascade. 30개는 한 번에 발화해도 rate limit window에 여유가 있어 cascade 폭이 훨씬 작다.

**v1에서 순차 처리로 테스트했을 때 H1 반증된 이유**: 순차 처리는 한 번에 1개씩 발화하므로 batch 크기에 무관하게 동일한 속도. burst 효과가 없었음. 동시 처리로 재설계하자 명확한 차이 나타남.

---

### H2 — pause/resume 영향 격리 ✓ **확인**

C 시나리오: `max_retries_per_msg = 1`

```
429 발생 패턴:
  msg-N → 429 → seek(tp, offset) → pause(Retry-After)
                                   ↓
  (poll() 루프 유지)
                                   ↓
  resume → msg-N 재전달 → 200 → commit
```

모든 429가 "1회 발생 후 다음 시도에서 성공"으로 완전 격리됨. cascade 없음.

B와 비교 (같은 30개 burst지만 mechanism 다름):
- B: 429 후 즉시 재시도 → window 아직 찬 상태 → 또 429 → max_retries=12
- C: 429 후 pause → Retry-After(~0.4s) 대기 → window 충분히 빈 상태 → 다음 시도 성공 → max_retries=1

---

### H3 — poll 누락 → rebalance ✓ **확인**

시나리오 E 로그 (max_poll_interval_ms=15,000):
```
[E] 429 받음. poll() 없이 20s sleep → rebalance 예상
[E] REVOKE partitions=[partition=3,0,1,2]
[E] REBALANCE #2 assigned=[partition=3,0,1,2]
[E] rebalance 2회 확인 → 실험 종료
```

C는 120초 내내 rebalance 0회. pause 중에도 `consumer.poll()` 루프를 유지했기 때문. poll 없는 sleep과의 대비가 명확하다.

---

### H4 — Token Bucket → 429 완전 차단 ✓ **완벽 확인**

D: 10,000건 중 429 = **0건**, 128초 완료

```
Token Bucket (80/s, capacity=20):
  acquire() → 토큰 소진 시 (1-tokens)/rate 초 sleep → 최대 80/s 보장

80/s < 100/s(API 한도) → 항상 여유 있음 → 429 수학적 불가
```

소요 시간 비교: A(172s) vs B(106s) vs C(110s) vs D(128s). D는 429 없이 가장 안정적이나, 80/s cap 때문에 B/C보다 약간 느림.

---

### H5 — at-least-once 동작 ✓ **직접 확인**

mock API `/retry_stats` 결과:
```json
{
  "messages_retried_then_succeeded": 158,
  "max_attempts_per_message": 2,
  "avg_attempts_per_message": 2.0,
  "examples": [
    {"message_id": "msg-429", "total_attempts": 2, "failed_before_success": 1},
    {"message_id": "msg-411", "total_attempts": 2, "failed_before_success": 1}
  ]
}
```

158개 메시지가 429 → 200 경로를 거쳐 재처리됨. 모두 1회 실패 후 1회 성공(avg=2.0).

**중요한 발견 — seek() 없이는 at-least-once가 동작하지 않는다**:

v1 실험(seek 없음): retry_stats=0, max_retries=0 — 429 받은 메시지가 재처리되지 않음
v2 실험(seek 추가): retry_stats=158, max_retries=1 — 정상 재처리

kafka-python에서 `pause()`는 파티션에서 새로운 fetch를 막지만, 이미 `poll()`로 가져온 메시지의 **position은 이미 advance된 상태**다. seek 없이 resume하면 Kafka는 position 이후(= 429 받은 메시지 다음)부터 전달하므로 해당 메시지는 현재 세션에서 영구 스킵된다.

```python
# at-least-once 보장을 위한 올바른 구현
elif r.status_code == 429:
    consumer.seek(tp, msg.offset)   # ← 이게 없으면 at-least-once 깨짐
    consumer.pause(*consumer.assignment())
    paused_until = time.time() + retry_after
```

---

## 5. 흥미로운 발견들

### 발견 1: H1은 "처리 방식"에 따라 결론이 달라진다

순차 처리(1개씩): max.poll.records 변경 → 429 비율 변화 없음 (H1 반증)
동시 처리(N개 동시): burst 크기 축소 → 429 비율 유의미하게 감소 (H1 확인)

실무 적용: ThreadPool이나 CompletableFuture로 병렬 처리하는 Java Spring Kafka 환경에서 max.poll.records는 효과가 있다. Python 순차 처리나 단순 루프 환경에서는 무의미하다.

### 발견 2: 모든 전략은 "같은 10,000건"을 완료하는 데 걸리는 시간이 다르다

| 전략 | 시간 | 비효율 원인 |
|---|---|---|
| A | 172s | 대부분의 시간이 429 재시도 |
| B | 106s | A보다 burst 작아서 재시도 적음 |
| C | 110s | 429마다 0.4s 대기 × 158회 = 63s 유휴 |
| D | 128s | 80/s cap × 128s = 10,240 ≈ 10,000 |

D가 429 없이 가장 안정적이나, rate 80% cap 때문에 B보다 느리다. C는 pause 대기가 크지만 429가 적어서 전반적으로 효율적이다.

### 발견 3: A/B의 재처리 건수가 높은 이유

A: 7,283건 재처리, avg 12.0회/메시지
B: 6,670건 재처리, avg 3.1회/메시지

429 후 재시도하는 모든 행위가 mock API의 `message_history`에 기록된다. A는 한 메시지가 최대 25번 API를 호출하므로 재처리 건수가 많다. 이것이 cascade의 실제 비용: 같은 메시지를 수십 번 중복 호출한다.

---

## 6. 실무 시사점

### 모니터링 알람 기준

| 지표 | 임계값 | 의미 |
|---|---|---|
| 429 비율 | >5% | burst 제어 필요 |
| 429 비율 | >30% | cascade 발생 중 — pause/resume 미적용 의심 |
| max_retries/메시지 | >5 | Token Bucket 없이 재시도만 쓰는 패턴 |
| rebalance 횟수 | >2/시간 | pause 중 poll() 누락 의심 |

### 설정 권장

```python
# 최소한으로 갖춰야 할 구현 (C 수준)
elif r.status_code == 429:
    consumer.seek(tp, msg.offset)       # 필수: at-least-once 보장
    consumer.pause(*consumer.assignment())
    paused_until = time.time() + float(r.headers.get("Retry-After", "1.0"))
    break

# 권장 추가 (D 수준)
limiter = TokenBucket(rate=외부API한도 * 0.8, capacity=rate * 0.25)
limiter.acquire()  # API 호출 전

# 분산 컨슈머 시 Token Bucket rate 조정
rate = 외부API한도 / 컨슈머_인스턴스_수
```

---

## 7. 한 줄 요약

> **burst=200이 88.9% 429를 만들고, burst=30은 58.8%로 줄이고, pause/resume이 1.6%로 격리하고, Token Bucket이 0%로 소멸시킨다. 단, seek() 없는 pause/resume은 at-least-once를 보장하지 않는다.**
