# k6 스크립트 템플릿

## 디렉토리 구조

```
k6-scripts/
├── config/
│   └── thresholds.js        # SLO 임계치 중앙 관리
├── scenarios/
│   ├── load-test.js          # 일반 부하 테스트
│   ├── stress-test.js        # 한계 탐색
│   └── spike-test.js         # 순간 급증
├── lib/
│   ├── endpoints.js          # API 호출 함수
│   └── data-generator.js     # 테스트 데이터 생성
└── README.md                 # 실행 방법, 파라미터 설명
```

## Load Test 템플릿

```javascript
// scenarios/load-test.js
import http from 'k6/http';
import { check } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// ─── 커스텀 메트릭 ───
const errorRate = new Rate('error_rate');
const writeLatency = new Trend('write_latency', true);
const readLatency = new Trend('read_latency', true);

// ─── 설정 ───
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';

export const options = {
  // ── 시나리오 분리: write와 read를 독립적으로 제어 ──
  scenarios: {
    write: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: 100,
      maxVUs: 500,
      stages: [
        { duration: '1m', target: 200 },   // ramp-up
        { duration: '3m', target: 200 },   // steady
        { duration: '1m', target: 0 },     // ramp-down
      ],
      exec: 'writeScenario',
    },
    read: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: 200,
      maxVUs: 1000,
      stages: [
        { duration: '1m', target: 600 },
        { duration: '3m', target: 600 },
        { duration: '1m', target: 0 },
      ],
      exec: 'readScenario',
    },
  },

  // ── SLO 기반 임계치 ──
  thresholds: {
    'write_latency': ['p(95)<200', 'p(99)<500'],
    'read_latency': ['p(95)<100', 'p(99)<300'],
    'error_rate': ['rate<0.001'],             // 0.1%
    'dropped_iterations': ['count<100'],      // VU 부족 감지
  },
};

// ─── 시나리오 함수 ───
export function writeScenario() {
  const payload = JSON.stringify({
    userId: Math.floor(Math.random() * 100000),
    type: 'PUSH',
    title: `test-${Date.now()}`,
    content: 'load test notification',
  });

  const res = http.post(`${BASE_URL}/api/v1/notifications`, payload, {
    headers: { 'Content-Type': 'application/json' },
    tags: { name: 'POST /api/v1/notifications' },
  });

  writeLatency.add(res.timings.duration);
  errorRate.add(res.status >= 400);

  check(res, {
    'write: status 2xx': (r) => r.status >= 200 && r.status < 300,
  });
  // sleep 없음 — ramping-arrival-rate가 요청 속도를 제어
}

export function readScenario() {
  const userId = Math.floor(Math.random() * 100000);

  const res = http.get(`${BASE_URL}/api/v1/notifications?userId=${userId}`, {
    tags: { name: 'GET /api/v1/notifications' },
  });

  readLatency.add(res.timings.duration);
  errorRate.add(res.status >= 400);

  check(res, {
    'read: status 2xx': (r) => r.status >= 200 && r.status < 300,
  });
}
```

### 핵심 포인트

- **`ramping-arrival-rate`**: "초당 N 요청" 정밀 제어. sleep 불필요 (executor가 rate 제어)
- **`dropped_iterations`**: VU 부족으로 요청을 못 보낸 경우 감지
- **시나리오 분리**: write/read 각각의 latency를 독립 측정
- **에러 분류 태깅**:
  ```javascript
  check(res, {
    'status is not 5xx': (r) => r.status < 500,
    'status is not 429': (r) => r.status !== 429,
    'response time < 500ms': (r) => r.timings.duration < 500,
  });
  ```

## Stress Test 템플릿 (한계 탐색)

```javascript
// scenarios/stress-test.js
// 목적: 시스템이 버틸 수 있는 최대 TPS 탐색
export const options = {
  scenarios: {
    stress: {
      executor: 'ramping-arrival-rate',
      startRate: 100,
      timeUnit: '1s',
      preAllocatedVUs: 500,
      maxVUs: 5000,
      stages: [
        { duration: '2m', target: 500 },
        { duration: '2m', target: 1000 },
        { duration: '2m', target: 2000 },
        { duration: '2m', target: 3000 },   // 어디서 깨지는지 관찰
        { duration: '2m', target: 5000 },
        { duration: '2m', target: 0 },      // 회복 관찰
      ],
      exec: 'mixedScenario',
    },
  },
  thresholds: {
    // stress test는 임계치를 넘는 지점을 찾는 게 목적
    // → threshold를 PASS/FAIL이 아닌 관찰용으로 설정
    http_req_duration: [{ threshold: 'p(95)<500', abortOnFail: false }],
  },
};
```

## docker-compose 설정

```yaml
k6:
  image: grafana/k6:0.50.0
  container_name: alarm-k6
  volumes:
    - ./perf-test:/scripts
  network_mode: host
  profiles:
    - test
```

## 실행 명령어

```bash
# Load Test
docker-compose run --rm k6 run /scripts/scenarios/load-test.js

# 환경 변수 전달
docker-compose run --rm \
  -e BASE_URL=http://host.docker.internal:8080 \
  k6 run /scripts/scenarios/load-test.js

# 결과 JSON 저장
docker-compose run --rm k6 run \
  --summary-export=/scripts/results/result.json \
  /scripts/scenarios/load-test.js

# Prometheus remote write 출력
docker-compose run --rm k6 run \
  --out experimental-prometheus-rw \
  /scripts/scenarios/load-test.js
```

## 결과 디렉토리 구조

```
results/
├── round-01-baseline/
│   ├── config.md              # 이 라운드의 설정값
│   ├── k6-summary.json
│   ├── grafana-hikaricp.png
│   ├── grafana-kafka.png
│   └── notes.md               # 발견 사항, 다음 변경 계획
├── round-02-osiv-off/
│   ├── config.md
│   ├── change.md              # 변경 내용 + 이유
│   ├── k6-summary.json
│   └── ...
└── summary.md                 # 전체 라운드 비교 요약
```
