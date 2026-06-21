"""
시나리오 E (Rebalance 검증): 429 받았을 때 poll() 없이 sleep().
max_poll_interval_ms=15초 설정 → 20초 sleep → rebalance 발생 확인.
H3 검증.
"""
import time, requests
from kafka import KafkaConsumer
from kafka.consumer.subscription_state import ConsumerRebalanceListener

API = "http://localhost:8080/call"
SCENARIO = "E"
GROUP_ID = "exp-e"
MAX_POLL_RECORDS = 50
DURATION = 90

POLL_INTERVAL_MS = 15000  # 15초

rebalance_count = [0]

class RebalanceListener(ConsumerRebalanceListener):
    def on_partitions_assigned(self, partitions):
        rebalance_count[0] += 1
        print(f"[{SCENARIO}] REBALANCE #{rebalance_count[0]} assigned={[str(p) for p in partitions]}", flush=True)
    def on_partitions_revoked(self, partitions):
        print(f"[{SCENARIO}] REVOKE partitions={[str(p) for p in partitions]}", flush=True)

consumer = KafkaConsumer(
    bootstrap_servers="localhost:9092",
    group_id=GROUP_ID,
    auto_offset_reset="earliest",
    enable_auto_commit=False,
    max_poll_records=MAX_POLL_RECORDS,
    max_poll_interval_ms=POLL_INTERVAL_MS,
    session_timeout_ms=10000,
    heartbeat_interval_ms=3000,
)
consumer.subscribe(["external-api-calls"], listener=RebalanceListener())

processed = 0
rate_limited = 0
start = time.time()

print(f"[{SCENARIO}] Start. max_poll_interval_ms={POLL_INTERVAL_MS}ms "
      f"→ 429 시 {POLL_INTERVAL_MS//1000 + 5}초 sleep으로 rebalance 유발", flush=True)

try:
    while time.time() - start < DURATION:
        records = consumer.poll(timeout_ms=1000, max_records=MAX_POLL_RECORDS)
        triggered_sleep = False
        for tp, msgs in records.items():
            for msg in msgs:
                message_id = msg.value.decode()
                try:
                    r = requests.post(API, json={"message_id": message_id}, timeout=5)
                except Exception as e:
                    print(f"[{SCENARIO}] API error: {e}", flush=True)
                    continue

                if r.status_code == 200:
                    processed += 1
                    consumer.commit()
                elif r.status_code == 429:
                    rate_limited += 1
                    sleep_time = POLL_INTERVAL_MS / 1000 + 5  # 20초 — interval 초과
                    print(f"[{SCENARIO}] 429 받음. poll() 없이 {sleep_time:.0f}s sleep → rebalance 예상", flush=True)
                    time.sleep(sleep_time)
                    print(f"[{SCENARIO}] sleep 종료. rebalances_so_far={rebalance_count[0]}", flush=True)
                    triggered_sleep = True
                    break

                if processed % 200 == 0 and processed > 0:
                    print(f"[{SCENARIO}] processed={processed} rebalances={rebalance_count[0]}", flush=True)

            if triggered_sleep:
                break

        if rebalance_count[0] >= 2:
            print(f"[{SCENARIO}] rebalance {rebalance_count[0]}회 확인 → 실험 종료", flush=True)
            break

finally:
    print(f"[{SCENARIO}] DONE processed={processed} rate_limited={rate_limited} "
          f"rebalances={rebalance_count[0]}", flush=True)
    consumer.close()
