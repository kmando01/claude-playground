---
name: timeout-tuning
description: >
  외부 API timeout (connect/read) 값을 실측 p99 기반으로 역산하고,
  CB threshold와의 정합성을 검증하는 방법론.
  timeout 설정, CB 재설계, sendmock 분포 측정 시 참조.
---

# Timeout 튜닝 — 실측 p99 기반 방법론

## 핵심 원칙

**임의의 숫자(3s, 5s, 30s)를 쓰지 않는다. 실측 p99 × 안전 배수로 역산한다.**

```
connect_timeout = connect p99 × 10
read_timeout    = read(정상) p99 × 20
```

배수 근거:
- connect: TCP 연결은 안정적 → ×10으로 충분
- read: 응답 분산 ↑, bimodal 분포 가능 → ×20으로 여유 확보

---

## Step 1: connect time 측정

```bash
python3 -c "
import subprocess
from concurrent.futures import ThreadPoolExecutor

def measure(i):
    r = subprocess.run([
        'curl', '-sf', '-w', '%{time_connect}',
        '-X', 'POST', 'http://TARGET_HOST/endpoint',
        '-H', 'Content-Type: application/json',
        '-d', 'REQUEST_BODY',
        '-o', '/dev/null'
    ], capture_output=True, text=True)
    return float(r.stdout.strip() or '0') * 1000

with ThreadPoolExecutor(max_workers=30) as ex:
    results = sorted(list(ex.map(measure, range(500))))

new_conns = [c for c in results if c > 0.01]  # keep-alive 재사용 제외
def p(arr, pct): return arr[min(int(len(arr)*pct/100), len(arr)-1)]
print(f'connect p99={p(new_conns,99):.2f}ms  max={new_conns[-1]:.2f}ms')
print(f'→ connect_timeout 권장: {p(new_conns,99)*10:.0f}ms')
"
```

---

## Step 2: read time 측정 (응답 분포 확인)

```bash
python3 -c "
import subprocess, json
from concurrent.futures import ThreadPoolExecutor

def send(i):
    r = subprocess.run([
        'curl', '-sf',
        '-X', 'POST', 'http://TARGET_HOST/endpoint',
        '-H', 'Content-Type: application/json',
        '-d', 'VALID_REQUEST_BODY',   # ← 올바른 body 필수 (400이면 분포 왜곡)
    ], capture_output=True, text=True)
    try:
        body = json.loads(r.stdout)
        return body.get('latencyMs', 0), body.get('result', '')
    except:
        return 0, 'PARSE_ERROR'

with ThreadPoolExecutor(max_workers=30) as ex:
    results = list(ex.map(send, range(500)))

latencies = sorted([r[0] for r in results])
def p(arr, pct): return arr[min(int(len(arr)*pct/100), len(arr)-1)]

# bimodal 분리 (임시 기준 500ms)
normal  = [l for l in latencies if l < 500]
delayed = [l for l in latencies if l >= 500]

print(f'정상({len(normal)}건): p95={p(normal,95)}ms  p99={p(normal,99)}ms  max={normal[-1]}ms')
if delayed:
    print(f'지연({len(delayed)}건): min={min(delayed)}ms  max={max(delayed)}ms')
    print(f'→ 갭 확인: read_timeout 후보 << {min(delayed)}ms 이어야 정상↔지연 명확히 분리')
print(f'→ read_timeout 권장: {p(normal,99)*20:.0f}ms')
"
```

---

## Step 3: bimodal 갭 검증

```
설정 기준:
  read_timeout = max(정상_p99 × 20, 정상_max × 5)

bimodal이면 추가 검증:
  read_timeout < 지연_min  → ✅ 정상과 지연 명확히 분리
  read_timeout > 지연_min  → ⚠️ 일부 지연 응답이 통과됨 (의도인지 확인)
```

### 실측 예시 (sendmock, 2026-03-11)

```
connect p99=2.78ms  → connect_timeout = 30ms  (×10)
read 정상 p99=10.5ms → read_timeout  = 200ms  (×20)

bimodal 갭: 정상 max=15ms << 200ms << 820ms=지연 min  ✅
```

---

## Step 4: CB threshold와 정합성 검증 (필수)

timeout 설정 후 반드시 확인해야 한다.

### timeout의 성격 판단

| 구분 | 상황 | CB 처리 |
|------|------|---------|
| **전략적 포기** | bimodal 분포에서 이상 구간을 포기. 서버는 정상이지만 느림 | `ignoreExceptions`에 `SocketTimeoutException` 추가 |
| **장애 신호** | 정상 서버가 갑자기 응답을 멈춤. 트래픽 급증, 장애 징후 | `recordExceptions`에 포함. threshold 재산정 필요 |

### CB threshold 재산정 공식

```
CB_threshold = (CB가 카운트하는 실패율 steady-state) + 여유(20%p)

예시 A — timeout을 ignoreExceptions 처리:
  steady-state = 자연 실패 10%
  threshold = 10% + 20% = 30%

예시 B — timeout을 recordExceptions 처리:
  steady-state = 자연 실패 10% + timeout 25% = 35%
  threshold = 35% + 20% = 55%  ← 거의 50%로 복귀
  (주의: 35% < threshold이어야 정상 운영 시 CB 미오픈)
```

### CB oscillation 체크

timeout을 recordExceptions에 포함했다면:
```
steady-state 실패율 > threshold → CB 영구 OPEN → consumer 항상 PAUSE
```

**증상 확인**:
```bash
grep -E "CB OPEN|pause|resume|HALF_OPEN" perf-test/logs/alarm-consumer.log | grep -v "does not permit" | tail -20
# OPEN → HALF_OPEN → OPEN 반복이면 oscillation
```

---

## 이 프로젝트 현황 (2026-03-11 기준)

### 현재 적용된 값
```yaml
# alarm-consumer/src/main/resources/application.yml
mock-send-api:
  connect-timeout: 30ms   # 실측 p99=2.78ms × 10배
  read-timeout: 200ms     # 실측 p99=10.5ms × 20배
  circuit-breaker:
    failure-rate-threshold: 30  # ← CB oscillation 발생 중!
```

### 내일 해결해야 할 것 (E1-3)

**파일**: `alarm-client-external/src/main/kotlin/com/alarm/client/config/ResilienceConfig.kt`

**변경**:
```kotlin
// ignoreExceptions에 SocketTimeoutException 추가
.ignoreExceptions(
    NonRetryableException::class.java,
    java.net.SocketTimeoutException::class.java,  // ← 추가
)

// permitted-calls-in-half-open 3 → 5 (probe 안정성)
// application.yml: permitted-calls-in-half-open-state: 5
```

**이유**: sendmock의 25% 지연은 "의도된 시뮬레이션" → 전략적 포기 분류
→ timeout은 CB가 아닌 Kafka retry 토픽 3단계 DLQ로 처리
→ CB는 sendmock 완전 장애(500, 네트워크 단절)에만 반응

**예상 효과**:
```
CB baseline = 10% (자연 실패만)
threshold = 30% → 여유 20%p 유지
T_req = 0.25 × 0.2s + 0.75 × 0.02s = 0.065s
consumer throughput = 30 / 0.065 = 461 TPS  ← 300 TPS 유입 초과
```

---

## 관련 파일
- `docs/perf-reports/2026-03-11-action-E1-2/REPORT.md` — CB oscillation 발견 경위
- `docs/solutions/timeout-measurement-methodology.md` — 이 내용의 docs 버전
