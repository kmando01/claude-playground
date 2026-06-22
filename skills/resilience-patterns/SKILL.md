---
name: resilience-patterns
description: Circuit Breaker / Retry / Timeout 설계 철학과 결정 기준. 구현 방법이 아닌 "왜 이 값인가"에 답한다. CB threshold 역산, ignoreExceptions 함정, timeout-CB 책임 분리, Retry 대상 선택 기준 포함. Use when configuring Circuit Breaker, deciding timeout values, or designing resilience strategy for external API integration.
---

# Resilience 설계 원칙

구현 코드는 `spring-rest-client` 스킬 참조. 이 스킬은 **"왜 이 값인가"** 에 답한다.

---

## Circuit Breaker

### 핵심 질문: "이 예외는 downstream 장애의 신호인가?"

CB `recordExceptions` / `ignoreExceptions` 결정 전에 반드시 이 질문을 먼저 해야 한다.

| 예외 유형 | 판단 | 이유 |
|-----------|------|------|
| 5xx 서버 오류 | ✅ record | 명확한 장애 신호 |
| SocketTimeoutException | ✅ record | downstream이 응답을 제때 못 줌 = 장애 신호 |
| ConnectException | ✅ record | downstream 프로세스 다운 |
| 4xx 클라이언트 오류 | ❌ ignore | 요청 형식 문제. downstream 장애 아님 |

### threshold는 steady-state 실패율에서 역산한다

임의의 숫자(50%, 30%)를 넣지 않는다. **정상 운영 중 실제 실패율을 먼저 측정**하고 역산한다.

```
# 1단계: steady-state 실패율 측정 (부하 테스트 or 운영 지표)
# 예시: 자연 실패 10% + timeout 25% = steady-state 35%

# 2단계: threshold 역산
threshold = steady-state 실패율 + 여유 (10%p)
          = 35% + 10% = 45%

# 의미
# - 정상(35%):      CB CLOSED 유지
# - 실제 장애(100%): 45% 초과 즉시 OPEN → 보호 기능 유지
```

**안티패턴**: threshold < steady-state → CB 영구 OPEN

```yaml
# BAD: steady-state 35% > threshold 30%
# → CB가 HALF_OPEN probe 즉시 실패 → 30초마다 OPEN 반복
# → Kafka consumer 대부분 PAUSE → lag 정체
failure-rate-threshold: 30

# GOOD
failure-rate-threshold: 45  # steady-state(35%) + 여유(10%p)
```

### permitted-calls-in-half-open-state 역산

```
# 정상 상태(실패율 p)에서 probe N회 중 CLOSED 복귀 실패 확률
# P(실패) = 1 - (1-p)^N

# 예시: p=35%, N=3 → P = 1 - 0.65³ = 72.6%  (너무 높음)
# 예시: p=10%, N=5 → P = 1 - 0.90⁵ = 41.0%  (허용 가능)

# 실제 장애 해소 후 안정적 복귀를 원하면 N을 충분히 크게 (5 이상 권장)
```

### `ignoreExceptions(SocketTimeoutException)` 함정

CB oscillation이 발생할 때 timeout을 ignore하고 싶은 유혹이 생기지만 **두 가지 이유로 NEVER**:

**이유 1 — 기술적 무효**: Spring RestClient는 read timeout 시 `ResourceAccessException(SocketTimeoutException)` 형태로 던진다. resilience4j `ignoreExceptions`는 **최상위 예외 타입만** 체크하므로, `SocketTimeoutException`을 등록해도 실제로 무시되지 않는다.

```kotlin
// BAD: 실제로 효과 없음
.ignoreExceptions(
    java.net.SocketTimeoutException::class.java,  // 최상위는 ResourceAccessException
)
```

**이유 2 — 보호 기능 소멸**: downstream이 완전히 다운됐을 때 모든 응답이 SocketTimeoutException인데, ignore하면 CB가 영구 CLOSED → consumer가 죽은 서버에 계속 요청.

**올바른 처방**: oscillation의 근본 원인은 `threshold < steady-state`. timeout을 ignore하는 게 아니라 **threshold를 올리는 것**.

---

## Timeout

### timeout 값은 실측 응답 분포에서 역산한다

```
# 측정: curl 또는 k6로 응답 시간 분포 측정
# 정상 응답 p99 × 배수 = timeout 설정값

| timeout 종류 | 배수 권장 | 이유 |
|-------------|----------|------|
| connect     | p99 × 10 | TCP 연결은 안정적, 편차 작음 |
| read        | p99 × 20 | 응답 분산 크고, 정상↔지연 갭 명확히 분리 |
```

**핵심**: 정상 응답과 비정상 응답 사이에 **명확한 갭**이 있을 때만 timeout 단축이 의미 있다.

```
# 좋은 케이스 (갭이 명확)
정상 응답 p99 = 10ms
지연 응답 min = 820ms  → 갭 82배. timeout=200ms으로 명확히 분리 가능

# 나쁜 케이스 (갭이 불분명)
정상 응답 p99 = 150ms
지연 응답 min = 180ms  → 갭 20%. timeout 단축 시 정상 요청도 잘림
```

### timeout과 CB의 책임 분리

```
timeout = 개별 요청 수준: "이 요청은 포기, 다음으로"  → Retry / DLQ로 처리
CB      = 서비스 수준:   "downstream 자체가 이상"  → OPEN으로 fast-fail
```

timeout이 구조적으로 높은 경우(예: 특정 API가 25% 지연) → timeout을 CB에서 ignore하는 게 아니라 **threshold를 올려 CB가 steady-state를 허용**하도록 설계.

---

## Retry

### 재시도해야 하는 예외 vs 하지 말아야 하는 예외

| 예외 유형 | 재시도 여부 | 이유 |
|-----------|------------|------|
| 503 ServiceUnavailable | ✅ | 일시적 과부하. 잠시 후 회복 가능 |
| 429 TooManyRequests | ✅ | Rate limit. backoff 후 재시도 |
| 500 InternalServerError | ❌ | 서버 로직 오류. 재시도해도 동일 결과 |
| 4xx (400, 401, 404) | ❌ | 요청 자체가 잘못됨. 재시도 무의미 |
| SocketTimeoutException | 상황에 따라 | CB + DLQ가 있으면 Retry보다 DLQ 위임 권장 |

### Retry는 CB 바깥에 위치해야 한다

```kotlin
// GOOD: Retry(CB(f)) — CB가 각 시도의 실패를 즉시 기록
Retry.decorateCheckedSupplier(retry) {
    CircuitBreaker.decorateCheckedSupplier(cb) { callApi() }.get()
}.get()

// BAD: CB(Retry(f)) — CB가 모든 재시도 소진 후에야 failure 1건 기록
// → CB가 장애를 늦게 감지 + CB OPEN 시에도 retry storm 발생
```

---

## 비동기 파이프라인(Kafka)에서의 CB

Kafka consumer가 외부 API를 호출할 때 CB oscillation은 **lag 정체**로 나타난다.

```
CB OPEN → consumer thread PAUSE → Kafka 메시지 미처리 → lag 증가
CB HALF_OPEN → probe N회 실패 → 즉시 OPEN 재전환 → 30초 주기 반복
```

**진단**: CB oscillation 의심 신호
- check 실패가 30초 주기로 간헐적 발생
- consumer lag이 감소하다가 주기적으로 정체
- log에서 `CircuitBreaker 'X' is OPEN` 반복

**처방 순서**:
1. steady-state 실패율 측정 (부하 테스트 중 Prometheus `resilience4j_circuitbreaker_failure_rate`)
2. `threshold < steady-state` 확인 → threshold 상향
3. `permitted-calls-in-half-open` 증가로 probe 안정성 확보

> **모니터링**: `resilience4j-micrometer` 의존성 추가 필수. 없으면 CB 상태를 Prometheus에서 볼 수 없음.
