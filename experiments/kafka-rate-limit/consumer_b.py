"""
시나리오 B (Static, 동시 burst=30):
  poll(30) → 30개 동시 HTTP 호출
  → 429 시 50ms+jitter sleep 후 재시도
A와 비교해 burst 크기만 다름 (H1 검증).
"""
import time, requests, random
from kafka import KafkaConsumer
from concurrent.futures import ThreadPoolExecutor, as_completed

API = "http://localhost:8080/call"
SCENARIO = "B"
GROUP_ID = "exp-b"
BATCH_SIZE = 30
MAX_WORKERS = 30
TOTAL = 10000
TIMEOUT = 300

def call_with_retry(message_id):
    retries = 0
    while True:
        try:
            r = requests.post(API, json={"message_id": message_id}, timeout=5)
            if r.status_code == 200:
                return retries
            elif r.status_code == 429:
                retries += 1
                time.sleep(0.05 + random.uniform(0, 0.05))
        except Exception:
            time.sleep(0.1)

consumer = KafkaConsumer(
    "external-api-calls",
    bootstrap_servers="localhost:9092",
    group_id=GROUP_ID,
    auto_offset_reset="earliest",
    enable_auto_commit=False,
    max_poll_records=BATCH_SIZE,
)

processed = 0
total_429s = 0
max_retries_per_msg = 0
start = time.time()

print(f"[{SCENARIO}] Start. concurrent_batch={BATCH_SIZE}", flush=True)

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    try:
        while processed < TOTAL and (time.time() - start) < TIMEOUT:
            batch = consumer.poll(timeout_ms=2000, max_records=BATCH_SIZE)
            msgs = [m for msgs in batch.values() for m in msgs]
            if not msgs:
                continue

            futures = {executor.submit(call_with_retry, m.value.decode()): m for m in msgs}
            for future in as_completed(futures):
                retries = future.result()
                total_429s += retries
                if retries > max_retries_per_msg:
                    max_retries_per_msg = retries

            processed += len(msgs)
            consumer.commit()

            if processed % 1000 == 0 or processed >= TOTAL:
                elapsed = time.time() - start
                rate = total_429s / (total_429s + processed) * 100 if (total_429s + processed) > 0 else 0
                print(f"[{SCENARIO}] processed={processed} total_429={total_429s} "
                      f"rate_429={rate:.1f}% max_retries={max_retries_per_msg} "
                      f"elapsed={elapsed:.0f}s", flush=True)
    finally:
        elapsed = time.time() - start
        rate = total_429s / (total_429s + processed) * 100 if (total_429s + processed) > 0 else 0
        print(f"[{SCENARIO}] DONE processed={processed} total_429={total_429s} "
              f"rate_429={rate:.1f}% max_retries_per_msg={max_retries_per_msg} "
              f"elapsed={elapsed:.0f}s", flush=True)
        consumer.close()
