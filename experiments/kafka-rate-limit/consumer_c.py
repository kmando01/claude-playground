"""
시나리오 C (Reactive): 순차 처리 + 429 시 pause/resume + Retry-After 존중.
- pause 중에도 poll() 호출 유지 (max.poll.interval.ms 초과 방지)
- 429'd 메시지는 commit 안 함 → resume 후 동일 메시지 재처리 (at-least-once)
H2, H5 검증.
"""
import time, requests
from kafka import KafkaConsumer
from kafka.consumer.subscription_state import ConsumerRebalanceListener

API = "http://localhost:8080/call"
SCENARIO = "C"
GROUP_ID = "exp-c"
BATCH_SIZE = 50
TOTAL = 10000
TIMEOUT = 300

rebalance_count = [0]

class RebalanceListener(ConsumerRebalanceListener):
    def on_partitions_assigned(self, partitions):
        rebalance_count[0] += 1
        print(f"[{SCENARIO}] REBALANCE #{rebalance_count[0]}", flush=True)
    def on_partitions_revoked(self, partitions):
        pass

consumer = KafkaConsumer(
    bootstrap_servers="localhost:9092",
    group_id=GROUP_ID,
    auto_offset_reset="earliest",
    enable_auto_commit=False,
    max_poll_records=BATCH_SIZE,
)
consumer.subscribe(["external-api-calls"], listener=RebalanceListener())

processed = 0
total_429s = 0
max_retries_per_msg = 0  # 같은 메시지가 pause→resume 후 다시 429 받은 횟수
consecutive_429_per_msg = {}  # message_id -> 현재 연속 429 수
start = time.time()
paused_until = 0

print(f"[{SCENARIO}] Start. sequential + pause/resume, Retry-After 존중", flush=True)

try:
    while processed < TOTAL and (time.time() - start) < TIMEOUT:
        now = time.time()

        paused = consumer.paused()
        if paused and now >= paused_until:
            consumer.resume(*paused)
            paused_until = 0
            print(f"[{SCENARIO}] RESUME", flush=True)

        records = consumer.poll(timeout_ms=200, max_records=BATCH_SIZE)

        if consumer.paused():
            continue

        paused_this_batch = False
        for tp, msgs in records.items():
            if paused_this_batch:
                break
            for msg in msgs:
                message_id = msg.value.decode()
                try:
                    r = requests.post(API, json={"message_id": message_id}, timeout=5)
                except Exception as e:
                    print(f"[{SCENARIO}] API error: {e}", flush=True)
                    continue

                if r.status_code == 200:
                    processed += 1
                    retries = consecutive_429_per_msg.pop(message_id, 0)
                    if retries > max_retries_per_msg:
                        max_retries_per_msg = retries
                    consumer.commit()

                    if processed % 1000 == 0 or processed >= TOTAL:
                        elapsed = time.time() - start
                        rate = total_429s / (total_429s + processed) * 100
                        print(f"[{SCENARIO}] processed={processed} total_429={total_429s} "
                              f"rate_429={rate:.1f}% max_retries={max_retries_per_msg} "
                              f"rebalances={rebalance_count[0]} elapsed={elapsed:.0f}s", flush=True)

                elif r.status_code == 429:
                    total_429s += 1
                    consecutive_429_per_msg[message_id] = consecutive_429_per_msg.get(message_id, 0) + 1
                    retry_after = float(r.headers.get("Retry-After", "1.0"))
                    # at-least-once 핵심: seek으로 position을 429 메시지 앞으로 되돌림
                    # pause/resume만으로는 position이 reset되지 않아 메시지가 스킵됨
                    consumer.seek(tp, msg.offset)
                    consumer.pause(*consumer.assignment())
                    paused_until = time.time() + retry_after
                    paused_this_batch = True
                    break  # 배치 내 나머지 처리 중단

finally:
    elapsed = time.time() - start
    rate = total_429s / (total_429s + processed) * 100 if (total_429s + processed) > 0 else 0
    print(f"[{SCENARIO}] DONE processed={processed} total_429={total_429s} "
          f"rate_429={rate:.1f}% max_retries_per_msg={max_retries_per_msg} "
          f"rebalances={rebalance_count[0]} elapsed={elapsed:.0f}s", flush=True)
    consumer.close()
