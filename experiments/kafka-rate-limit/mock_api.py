"""
Mock 외부 API — 100 req/s 슬라이딩 윈도우 rate limit.
v2: per-message 이력 추가 (H5 직접 검증용)
"""
import time
from collections import deque, defaultdict, Counter
from fastapi import FastAPI, Request, Response
import uvicorn

app = FastAPI()

RATE_LIMIT = 100
WINDOW = 1.0

request_times = deque()
call_log = []  # (ts, status, message_id)
# H5 직접 추적: message_id -> [status, status, ...]
message_history = defaultdict(list)

@app.post("/call")
async def call(request: Request):
    body = await request.json()
    message_id = body.get("message_id", "unknown")
    now = time.time()

    while request_times and request_times[0] < now - WINDOW:
        request_times.popleft()

    if len(request_times) >= RATE_LIMIT:
        retry_after = WINDOW - (now - request_times[0])
        call_log.append((now, 429, message_id))
        message_history[message_id].append(429)
        return Response(
            status_code=429,
            content='{"error":"rate_limited"}',
            headers={"Retry-After": f"{max(retry_after, 0.1):.3f}"},
            media_type="application/json",
        )

    request_times.append(now)
    call_log.append((now, 200, message_id))
    message_history[message_id].append(200)
    return {"ok": True, "message_id": message_id}

@app.get("/stats")
def stats():
    total = len(call_log)
    success = sum(1 for _, s, _ in call_log if s == 200)
    rate_limited = sum(1 for _, s, _ in call_log if s == 429)
    msg_counts = Counter(mid for _, s, mid in call_log if s == 200)
    duplicates = {mid: c for mid, c in msg_counts.items() if c > 1}
    return {
        "total": total,
        "success": success,
        "rate_limited": rate_limited,
        "rate_limited_ratio": round(rate_limited / total, 4) if total else 0,
        "duplicate_count": len(duplicates),
        "duplicate_examples": dict(list(duplicates.items())[:5]),
    }

@app.get("/retry_stats")
def retry_stats():
    """H5 직접 검증: 429를 받은 후 200으로 성공한 메시지를 추적."""
    retried_success = []
    for mid, statuses in message_history.items():
        if 429 in statuses and 200 in statuses:
            first_success = next((i + 1 for i, s in enumerate(statuses) if s == 200), None)
            retried_success.append({
                "message_id": mid,
                "total_attempts": len(statuses),
                "failed_before_success": first_success - 1 if first_success else 0,
            })
    attempts_list = [r["total_attempts"] for r in retried_success]
    return {
        "messages_retried_then_succeeded": len(retried_success),
        "max_attempts_per_message": max(attempts_list) if attempts_list else 0,
        "avg_attempts_per_message": round(sum(attempts_list) / len(attempts_list), 1) if attempts_list else 0,
        "examples": sorted(retried_success, key=lambda x: -x["total_attempts"])[:5],
    }

@app.post("/reset")
def reset():
    request_times.clear()
    call_log.clear()
    message_history.clear()
    return {"ok": True}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")
