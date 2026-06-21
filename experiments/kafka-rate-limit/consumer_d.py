"""
시나리오 D (Proactive): 순차 처리 + Token Bucket 80/s + pause/resume 안전망.
H4 검증 — 429 발생 자체를 0에 수렴.
"""
import time, requests
from kafka import KafkaConsumer
from kafka.consumer.subscription_state import ConsumerRebalanceListener

API = "http://localhost:8080/call"
SCENARIO = "D"
GROUP_ID = "exp-d"
BATCH_SIZE = 50
TOTAL = 10000
TIMEOUT = 300

class TokenBucket:
    def __init__(self, rate, capacity):
        self.rate = rate
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last = time.time()

    def acquire(self):
        while True:
            now = time.time()
            self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
            self.last = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            time.sleep((1.0 - self.tokens) / self.rate)

limiter = TokenBucket(rate=80, capacity=20)
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
start = time.time()
paused_until = 0

print(f"[{SCENARIO}] Start. Token Bucket 80/s + pause/resume 안전망", flush=True)

try:
    while processed < TOTAL and (time.time() - start) < TIMEOUT:
        now = time.time()

        paused = consumer.paused()
        if paused and now >= paused_until:
            consumer.resume(*paused)
            paused_until = 0
            print(f"[{SCENARIO}] RESUME (unexpected 429 recovery)", flush=True)

        records = consumer.poll(timeout_ms=200, max_records=BATCH_SIZE)

        if consumer.paused():
            continue

        paused_this_batch = False
        for tp, msgs in records.items():
            if paused_this_batch:
                break
            for msg in msgs:
                message_id = msg.value.decode()
                limiter.acquire()

                try:
                    r = requests.post(API, json={"message_id": message_id}, timeout=5)
                except Exception as e:
                    print(f"[{SCENARIO}] API error: {e}", flush=True)
                    continue

                if r.status_code == 200:
                    processed += 1
                    consumer.commit()

                    if processed % 1000 == 0 or processed >= TOTAL:
                        elapsed = time.time() - start
                        print(f"[{SCENARIO}] processed={processed} total_429={total_429s} "
                              f"elapsed={elapsed:.0f}s", flush=True)

                elif r.status_code == 429:
                    total_429s += 1
                    retry_after = float(r.headers.get("Retry-After", "1.0"))
                    consumer.pause(*consumer.assignment())
                    paused_until = time.time() + retry_after
                    paused_this_batch = True
                    print(f"[{SCENARIO}] PAUSE (unexpected 429 #{total_429s})", flush=True)
                    break

finally:
    elapsed = time.time() - start
    rate = total_429s / (total_429s + processed) * 100 if (total_429s + processed) > 0 else 0
    print(f"[{SCENARIO}] DONE processed={processed} total_429={total_429s} "
          f"rate_429={rate:.1f}% rebalances={rebalance_count[0]} "
          f"elapsed={elapsed:.0f}s", flush=True)
    consumer.close()
