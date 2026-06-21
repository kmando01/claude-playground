"""
1초 간격으로 컨슈머 lag + mock API 통계를 CSV로 출력.
usage: python3 monitor.py <group_id>
"""
import sys, time, subprocess, requests, json

GROUP = sys.argv[1] if len(sys.argv) > 1 else "exp-a"
KAFKA_BIN = "/tmp/kafka_2.13-3.9.0/bin"

print("ts,lag,api_total,api_success,api_429,api_429_ratio,duplicates", flush=True)

while True:
    ts = int(time.time())

    # Kafka consumer lag
    try:
        result = subprocess.run(
            [f"{KAFKA_BIN}/kafka-consumer-groups.sh",
             "--bootstrap-server", "localhost:9092",
             "--describe", "--group", GROUP],
            capture_output=True, text=True, timeout=5
        )
        lines = [l for l in result.stdout.splitlines() if l.strip() and "GROUP" not in l and "---" not in l]
        lag = sum(int(l.split()[5]) for l in lines if l.split()[5].isdigit())
    except Exception:
        lag = -1

    # mock API 통계
    try:
        r = requests.get("http://localhost:8080/stats", timeout=2)
        d = r.json()
        api_total = d["total"]
        api_success = d["success"]
        api_429 = d["rate_limited"]
        api_429_ratio = d["rate_limited_ratio"]
        duplicates = d["duplicate_count"]
    except Exception:
        api_total = api_success = api_429 = duplicates = -1
        api_429_ratio = -1

    print(f"{ts},{lag},{api_total},{api_success},{api_429},{api_429_ratio:.4f},{duplicates}", flush=True)
    time.sleep(1)
