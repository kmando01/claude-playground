---
name: perf-hypothesis-verify
description: >
  "X가 Y에 영향을 준다"는 성능·운영 가설을 지표로 증명하는 실험 사이클 오케스트레이터.
  가설 정의 → 도구 적합성 검토 → 통제 실험 설계 → Ladder 실행 → Collateral Damage 검증 →
  운영 리스크 실험 → 증거 기반 보고서 작성까지 전 단계를 자율적으로 수행한다.
  반증(false → "증명 안 됨")도 결론으로 명시한다.

  Use when:
  - "X가 성능에 영향을 주는지 실험해줘", "지표로 증명해줘", "가설 검증해줘"
  - "핫 문서/핫 키/핫 파티션이 문제인지 확인해줘"
  - "어떤 설계가 더 성능이 좋은지 실험으로 비교해줘"
  - "성능 주장을 데이터로 증명하고 싶어"
  - "말로만 하지 말고 실험으로 증명해줘"
  - "운영 리스크가 있다는 걸 테스트로 보여줘"
  - 단순 벤치마크가 아니라 "왜 느려지는지" 원인을 지표로 규명해야 할 때
  - 실험 결과를 보고서로 남겨야 할 때
---

# perf-hypothesis-verify — 성능·운영 가설 검증 사이클

> **철학**: 직관이 아니라 지표로 증명한다. 말로 설명할 수 있는 건 실험으로도 증명할 수 있다.
> 반증도 결론이다 — "차이가 없다"는 것도 데이터로 보여야 한다.
> 결과는 "차이가 있다/없다"가 아니라 "어떤 지표가 얼마나 움직였는가"로 말한다.

---

## Step 0: 가설 명세화

사용자의 주장을 검증 가능한 명제로 변환한다.

```
원문: "핫 문서가 MongoDB 성능에 영향을 준다"
명제: "같은 총 ops를 (단일 doc 집중 / 분산)으로 처리했을 때
       throughput·latency·서버 메트릭이 다르게 움직인다"
```

```
원문: "Lua가 성능을 저하시킨다"
명제A: "Lua 실행 중 다른 커맨드의 latency가 올라간다"  → 테스트 가능
명제B: "정상 Lua가 INCR보다 throughput이 낮다"         → 테스트 가능
```

가설이 여러 하위 명제로 나뉠 수 있으면 **하나씩 분리해서** 각각 검증한다.

명제 작성 체크리스트:
- **변수 고립**: 다른 조건은 모두 같고 하나만 다른가?
- **측정 대상**: 어떤 지표가 움직이면 증명인가?
- **영향 범위**: 직접 영향(hot 리소스 자체)과 간접 영향(무관한 다른 작업) 모두 검증할 것인가?
- **운영 리스크**: 성능이 아닌 장애·복구·관찰가능성 관련 가설도 있는가?

---

## Step 1: 도구 적합성 검토 (GATE)

> **이 단계를 건너뛰면 실험 결과가 거짓 음성(false negative)이 된다.**
> Python으로 500 스레드를 만들어도 GIL 때문에 진짜 동시 부하가 발생하지 않는다.

### 동시성 모델 체크

| 언어/도구 | 동시성 모델 | 리소스 경합 실험 적합성 | 비고 |
|-----------|------------|----------------------|------|
| Python threading | GIL → 사실상 순차 | ❌ 부적합 | write ticket 고갈 미재현 |
| Python asyncio | 단일 스레드 이벤트 루프 | ❌ 부적합 | 동시 커넥션 제한 |
| Go goroutine | OS 스레드 병렬 | ✅ 적합 | 진정한 동시 부하 |
| Java virtual thread | M:N 모델 | ✅ 적합 | |
| Node.js | 단일 스레드 이벤트 루프 | ⚠️ 제한적 | I/O bound에서만 |
| k6 | Go 기반 | ✅ 적합 | HTTP/gRPC에 최적 |

검증하려는 효과가 **리소스 경합**(lock, ticket, connection pool 포화)이라면 진정한 동시 실행 도구 필수.
현재 도구가 부적합하면 **즉시 전환**하고 이유를 기록한다.

### 가설 유형별 실험 도구 선택

| 가설 유형 | 적합한 실험 도구 | 핵심 측정 지표 |
|-----------|-----------------|----------------|
| 리소스 경합 (lock/ticket/queue) | Go, Java, k6 | peak_queue, writeConflicts, ticket_out |
| 처리량/지연 비교 | Go, Java, k6, redis-benchmark | p99, max, TPS |
| 장애·복구 리스크 | redis-cli + bash | 에러 메시지, 복구 가능 여부 |
| 운영 가시성 | redis-cli, docker logs | 로그 라인 수, 통계 구분 가능 여부 |
| 데이터 정합성 | Go, Java | 실제 저장값 vs 기대값 |

---

## Step 2: 통제 실험 설계

### 핵심 원칙: 변수는 하나만

```
Baseline (Control) : 총 N ops, 구현 A (예: INCR)
Variant (Treatment): 총 N ops, 구현 B (예: Lua GET+INCR)

같아야 하는 것: workers 수, ops 수, 데이터 크기, 하드웨어, 시간대
다른 것: 오직 검증 대상 하나만
```

### 실험 유형 분류

**유형 1: 처리량·지연 비교** (Ladder 필요)
→ Step 4 Ladder 실행

**유형 2: Collateral Damage** (혼합 시나리오)
→ Step 5 Mixed 실험

**유형 3: 운영 리스크** (시나리오 기반, Ladder 불필요)
→ Step 5.5 운영 리스크 실험

### 측정 지표

**애플리케이션 레벨** (항상 측정):
- throughput (ops/s), latency p50/p95/p99/max

**서버 내부 지표** (DB별 선택):
- MongoDB: `metrics.operation.writeConflicts`, `queues.execution.write.out/available/queueLength`
- Redis: `INFO commandstats`, `SLOWLOG`, `FUNCTION STATS`
- PostgreSQL: `pg_stat_activity`, `pg_locks`
- Kafka: consumer lag, partition leader throttle

**스냅샷 패턴**: before/after delta. 실험 중 peak는 20~50ms 간격 별도 goroutine 폴링.

---

## Step 3: 실험 스크립트 작성

```
{project}/
├── bench_control.go    # Baseline
├── bench_variant.go    # Variant
├── bench_mixed.go      # Collateral damage
├── bench_ops_risk.go   # 운영 리스크 시나리오
└── results/
    ├── *.json
    └── REPORT.md
```

공통 구조:
```
1. setup()           → 초기화 (drop/create)
2. snapshot_before() → 서버 메트릭 캡처
3. monitor()         → peak 추적 goroutine
4. run_workers()     → 실제 부하
5. snapshot_after()  → delta 계산
6. percentiles()     → p50/p95/p99/max
7. save_json()
8. verify_integrity() → completed_ops == 실제_레코드_수
```

---

## Step 4: Ladder 실행 (처리량·지연 비교형)

> 임계점을 찾기 위해 단계적으로 올린다. 한 번에 500으로 올리면 임계점을 놓친다.

### 표준 단계

| 단계 | workers | 예상 관찰 |
|------|---------|-----------|
| 1 | 10 | 차이 거의 없음 (warm-up, 기저선 확인) |
| 2 | 50 | 첫 번째 신호 포착 |
| 3 | 100 | 차이 명확화 |
| 4 | 200 | 리소스 포화 구간 |
| 5 | 500 | 최대 스트레스 |

Control → Variant 순으로 실행, 즉시 JSON 저장.

**조기 종료**: workers=50에서 이미 p99 2x + 핵심 메트릭 50x → 200, 500만 추가 실행.
**반증 조기 종료**: 전 단계 차이가 p99 10% 미만이면 도구 적합성 재검토 후 명제 반증으로 결론.

---

## Step 5: Collateral Damage 실험

> "hot 리소스를 건드리지 않는 정상 작업까지 영향을 받는가?"
> 이 실험이 "시스템 전체 영향" 명제를 증명하는 결정적 증거다.

```
workers/2 → Variant (hot resource 접근)
workers/2 → Control (무관한 리소스 접근)

cold worker 성능이 순수 Control 대비 저하되면 → collateral damage 확인
```

---

## Step 5.5: 운영 리스크 실험 (장애·복구·가시성)

성능 숫자로 증명 안 되는 운영 리스크도 **실험으로 직접 재현**한다.

### 패턴 A: 장애 복구 불가 재현

```bash
# 예: Redis Lua UNKILLABLE
redis-cli EVAL "write_then_hang_script" 1 key 99999999999 &
sleep 6  # lua-time-limit 초과 후
redis-cli SCRIPT KILL
# 기대: UNKILLABLE 메시지 → 복구 불가 직접 확인
```

결과 기록: 에러 메시지 전문 + 복구 가능 여부 + 유일한 복구 수단

### 패턴 B: Partial Write 재현

```
script: write A → write B → 에러 유발 → write C
측정: A, B, C 각각의 상태
기대 (트랜잭션이라면): 모두 (nil)
실제: A=set, B=set, C=(nil) → 롤백 없음 증명
```

### 패턴 C: 관찰가능성 격차 측정

```bash
# 예: EVAL vs Functions 통계 구분
for i in 1..100; do redis-cli EVAL script_A; redis-cli EVAL script_B; done
redis-cli INFO commandstats | grep cmdstat_eval
# 기대: 두 스크립트가 합산됨 → 구분 불가 증명
```

### 패턴 D: 로그 오염 측정

```bash
# N회 호출 → 로그 라인 수 카운트
redis-cli EVAL "redis.log(redis.LOG_WARNING, 'DEBUG:...')" 0
docker logs container | grep "DEBUG:" | wc -l
# 호출 수 == 로그 라인 수 → 1:1 오염 증명
```

### 패턴 E: 블로킹 효과 측정

```
클라이언트 A: 블로킹 작업 시작 (Lua, DEBUG SLEEP, 디버거 등)
클라이언트 B: 즉시 GET 발행 → 완료까지 대기 시간 측정
비교: baseline GET vs 블로킹 중 GET
```

---

## Step 6: 보고서 작성

`results/REPORT.md` 필수 섹션:

```markdown
# {가설} 검증 결과

## 실험 환경
(DB 버전, OS, CPU, 메모리, 클라이언트 도구 선택 이유)

## 결과 테이블 (Ladder)
| workers | Control p99 | Variant p99 | 배율 | 핵심_메트릭 배율 |

## Collateral Damage 실험
| cold worker 측정 | 혼합 시나리오 | 순수 Control | 변화 |

## 운영 리스크 실험 결과
| 실험 | 결과 | 증거 |

## 핵심 시그니처 검증
- [ ] Throughput 격차 (Variant < Control)
- [ ] Latency p99 폭증 (≥2x)
- [ ] 핵심 메트릭 격차 (≥10x)
- [ ] 리소스 포화 (queue/ticket/lock 고갈)
- [ ] Cold worker 피해
- [ ] 운영 리스크 직접 재현 (해당 시)

## 반증된 명제 (있다면)
(증명 시도했으나 데이터로 반증된 것들 — 이것도 결론이다)

## 결론: 증거 강도 평가
| 증거 | 강도★ | 핵심 수치 |

## 실무 시사점
```

### 증거 강도 기준

| ★ | 기준 |
|----|------|
| ★★★★★ | 인과관계 직접 증명. 해당 메트릭이 100% 해당 원인에서만 발생 |
| ★★★★☆ | 강한 상관. 주 원인으로 충분 |
| ★★★☆☆ | 유의미하나 노이즈·도구 제한 영향 있음 |
| ★★☆☆☆ | 방향은 맞으나 배율이 실용적으로 작음 |
| ★☆☆☆☆ | 관찰됐으나 통계적 유의성 불충분 |

---

## 자주 발생하는 함정

### 1. 도구 GIL/동시성 제한 → false negative
증상: writeConflicts 격차는 크지만 throughput/latency 차이 없음
진단: `peak_tickets_out` 이 항상 0
대응: Go, Java, k6로 교체

### 2. 총 작업량이 달라 비교 불가
대응: `num_workers × ops_per_worker` 를 Control/Variant 동일하게

### 3. 정합성 검증 누락
대응: `completed_ops == 실제_레코드_수` 항상 검증

### 4. Ladder 생략 → 임계점 미파악
대응: 10 → 50 → 100 → 200 → 500 단계 준수

### 5. Collateral damage 생략
대응: Step 5 혼합 시나리오는 선택이 아닌 필수

### 6. 반증을 실패로 처리
증상: "성능 차이가 안 나서 실험 실패"라고 결론
대응: 반증도 결론이다. "정상 Lua는 INCR 대비 collateral damage 없음 — 데이터로 확인"처럼 명시

### 7. 운영 리스크를 말로만 설명
증상: "이 방식은 디버깅이 어렵습니다"라고 서술만 함
대응: 블로킹 측정, partial write 재현, 로그 오염 카운트 등 **직접 실험으로 증명**

### 8. 평균/p50만 보고 tail latency 놓침
증상: "평균은 괜찮아 보임"
진단: p99/max가 평균의 수백 배
대응: 항상 p99, max를 함께 보고 "평균은 정상이지만 max가 2000ms"를 명시
