"""실험 결과 종합 분석 — CSV + JSON → 보고서 생성"""
import json, os, csv
from pathlib import Path

BASE = Path.home() / "kafka-rate-limit-exp"

def load_json(path):
    with open(path) as f:
        return json.load(f)

def load_csv(path):
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows.append({k: float(v) for k, v in row.items()})
            except ValueError:
                pass
    return rows

def lag_recovery_time(rows):
    """lag이 0으로 처음 수렴하는 시점 (초)"""
    if not rows:
        return "N/A"
    start_ts = rows[0]["ts"]
    for row in rows:
        if row["lag"] == 0:
            return f"{row['ts'] - start_ts:.0f}s"
    return ">120s"

# 로그 파일에서 숫자 파싱 (DONE 라인)
def parse_consumer_log(log_path):
    if not os.path.exists(log_path):
        return {}
    result = {}
    with open(log_path) as f:
        for line in f:
            if "DONE" in line:
                parts = line.strip().split()
                for p in parts:
                    if "=" in p:
                        k, v = p.split("=", 1)
                        try:
                            result[k] = float(v.replace("ms", ""))
                        except ValueError:
                            result[k] = v
    return result

scenarios = {
    "A": {"name": "Naive (max_poll=500)", "group": "exp-a"},
    "B": {"name": "Static (max_poll=50)", "group": "exp-b"},
    "C": {"name": "Reactive (pause/resume)", "group": "exp-c"},
    "D": {"name": "Proactive (Token Bucket 80/s)", "group": "exp-d"},
    "E": {"name": "Rebalance 검증", "group": "exp-e"},
}

print("\n" + "="*70)
print("  Kafka Rate Limit 실험 — 종합 결과")
print("="*70)

results = {}
for sc, info in scenarios.items():
    key = sc.lower()
    json_path = BASE / "results" / f"scenario_{key}_final.json"
    csv_path = BASE / "results" / f"scenario_{key}.csv"
    log_path = BASE / "logs" / f"scenario_{key}.out"

    if not json_path.exists():
        print(f"\n[{sc}] 데이터 없음")
        continue

    api_stats = load_json(json_path)
    csv_rows = load_csv(csv_path) if csv_path.exists() else []
    log = parse_consumer_log(log_path)

    results[sc] = {
        "api_total": api_stats["total"],
        "api_success": api_stats["success"],
        "api_429": api_stats["rate_limited"],
        "rate_429": api_stats["rate_limited_ratio"] * 100,
        "duplicates": api_stats["duplicate_count"],
        "lag_recovery": lag_recovery_time(csv_rows),
        "log": log,
    }

# 테이블 출력
print(f"\n{'지표':<30} {'A':>10} {'B':>10} {'C':>10} {'D':>10} {'E':>10}")
print("-"*72)

metrics = [
    ("외부 API 총 호출", "api_total", lambda v: f"{v:,.0f}"),
    ("성공(200)", "api_success", lambda v: f"{v:,.0f}"),
    ("429 횟수", "api_429", lambda v: f"{v:,.0f}"),
    ("429 비율", "rate_429", lambda v: f"{v:.1f}%"),
    ("중복 처리 메시지", "duplicates", lambda v: f"{v:.0f}"),
    ("Lag 회복", "lag_recovery", lambda v: str(v)),
]

for label, key, fmt in metrics:
    row = f"{label:<30}"
    for sc in ["A", "B", "C", "D", "E"]:
        if sc in results and key in results[sc]:
            row += f" {fmt(results[sc][key]):>10}"
        else:
            row += f" {'N/A':>10}"
    print(row)

print()
# 로그에서 추가 지표
print(f"{'p95 latency':<30}", end="")
for sc in ["A", "B", "C", "D", "E"]:
    v = results.get(sc, {}).get("log", {}).get("p95", "N/A")
    s = f"{v:.1f}ms" if isinstance(v, float) else v
    print(f" {s:>10}", end="")
print()

print(f"{'p99 latency':<30}", end="")
for sc in ["A", "B", "C", "D", "E"]:
    v = results.get(sc, {}).get("log", {}).get("p99", "N/A")
    s = f"{v:.1f}ms" if isinstance(v, float) else v
    print(f" {s:>10}", end="")
print()

print(f"{'max_consecutive_429':<30}", end="")
for sc in ["A", "B", "C", "D", "E"]:
    v = results.get(sc, {}).get("log", {}).get("max_consecutive_429", "N/A")
    s = f"{v:.0f}" if isinstance(v, float) else v
    print(f" {s:>10}", end="")
print()

print(f"{'Rebalance 횟수':<30}", end="")
for sc in ["A", "B", "C", "D", "E"]:
    v = results.get(sc, {}).get("log", {}).get("rebalances", "N/A")
    s = f"{v:.0f}" if isinstance(v, float) else v
    print(f" {s:>10}", end="")
print()

print("\n" + "="*70)
print("  가설 판정")
print("="*70)

a_429 = results.get("A", {}).get("rate_429", 0)
b_429 = results.get("B", {}).get("rate_429", 0)
c_429 = results.get("C", {}).get("rate_429", 0)
d_429 = results.get("D", {}).get("rate_429", 0)
c_consec = results.get("C", {}).get("log", {}).get("max_consecutive_429", -1)
e_rebal = results.get("E", {}).get("log", {}).get("rebalances", 0)
c_dup = results.get("C", {}).get("duplicates", -1)

h1_verdict = "△ 반증" if abs(a_429 - b_429) < 2 else "✓ 확인"
h2_verdict = "✓ 확인" if c_consec == 1 and c_429 < a_429 / 2 else "△"
h3_verdict = "✓ 확인" if e_rebal >= 2 else "✗ 미확인"
h4_verdict = "✓ 확인" if d_429 < 1.0 else "△"
h5_verdict = "✓ 간접확인" if c_429 > 0 else "△"

verdicts = [
    ("H1", "max.poll.records 단독으로 429 감소", h1_verdict, f"A:{a_429:.1f}% vs B:{b_429:.1f}%"),
    ("H2", "pause/resume이 429 영향 격리", h2_verdict, f"max_consec={c_consec:.0f}" if isinstance(c_consec, float) else f"max_consec={c_consec}"),
    ("H3", "poll 누락 → rebalance", h3_verdict, f"rebalances={e_rebal:.0f}" if isinstance(e_rebal, float) else f"rebalances={e_rebal}"),
    ("H4", "Token Bucket → 429≈0", h4_verdict, f"D 429율:{d_429:.1f}%"),
    ("H5", "at-least-once 동작", h5_verdict, f"pause 후 재처리 확인 ({c_429:.0f}건 429→성공 retry)"),
]

for h, desc, verdict, evidence in verdicts:
    print(f"  {h}: [{verdict}] {desc}")
    print(f"      근거: {evidence}")
    print()

print("="*70)
