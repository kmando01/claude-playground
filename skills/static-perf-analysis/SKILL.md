---
name: static-perf-analysis
description: 코드베이스 정적 성능 분석. 설정 파일과 소스 코드를 분석하여 숨겨진 프레임워크 동작(Hidden Behavior)과 설정값 병목(Bottleneck)을 찾는다. 성능 테스트 전 사전 점검 또는 테스트 결과 해석 시 사용. Use when user says "정적 분석", "성능 분석", "병목 분석", "hidden behavior", "/static-perf", or before running performance tests.
---

# 정적 성능 분석 (Static Performance Analysis)

## 목적

성능 테스트 실행 없이, 코드와 설정만으로 잠재적 성능 문제를 사전에 식별한다.
실측 메트릭이 있으면 함께 대조하여 근거를 강화한다.

## 분석 프로세스

```
1. 수집 → 2. Hidden Behavior 분석 → 3. Bottleneck 분석 → 4. 리포트
```

### Step 1: 수집 (병렬 탐색)

아래 파일들을 Explore 에이전트로 병렬 수집한다:

| 카테고리 | 대상 |
|----------|------|
| 설정 | `application*.yml`, `docker-compose*.yml`, `build.gradle.kts` |
| JPA | `@Entity` 클래스 (`@GeneratedValue` 전략, 연관관계, 인덱스) |
| 커넥션 | HikariCP, Redis(Lettuce/Jedis), HTTP Client Factory 설정 |
| 스레드 | Tomcat threads, `@Async`, Kafka listener concurrency |
| 외부 호출 | RestClient/WebClient 팩토리, timeout, Circuit Breaker, Retry |
| Kafka | Producer/Consumer 설정, 토픽 파티션 수, AckMode |
| 부하 목표 | ADR 또는 설계 문서의 TPS/레이턴시 목표 |

### Step 2: Hidden Behavior 분석

**정의**: "이 설정이 내부적으로 이렇게 동작하는 줄 몰랐다"에 해당하는 경우.
단순 리소스 부족이 아닌, 프레임워크/라이브러리의 숨겨진 내부 동작이 원인.

**점검 항목 (체크리스트)**:

#### JPA/Hibernate
- [ ] `GenerationType.IDENTITY` → Hibernate 배치 INSERT 비활성화 (INSERT마다 즉시 flush + SELECT LAST_INSERT_ID)
- [ ] `GenerationType.AUTO` → DB 방언에 따라 시퀀스 조회용 별도 커넥션 점유 가능
- [ ] `spring.jpa.open-in-view` 기본값 `true` → Controller까지 영속성 컨텍스트 유지, DB 커넥션 장기 점유
- [ ] `@Transactional` 안에서 외부 API/Redis 호출 → 응답 대기 동안 DB 커넥션 점유
- [ ] Lazy Loading + `toString()`/직렬화 → N+1 쿼리 암묵적 발생

#### Redis
- [ ] Lettuce 기본 단일 커넥션 공유 → 동기 API 사용 시 head-of-line blocking
- [ ] `RedisTemplate` 동기 호출을 `@Transactional` 안에서 사용 → DB 커넥션 + Redis 대기 동시 점유

#### Kafka
- [ ] `max.poll.records` x 레코드당 처리 시간 > `max.poll.interval.ms` → 리밸런싱 트리거
- [ ] `enable-auto-commit=false` + BATCH AckMode → 처리 중 실패 시 전체 배치 재처리
- [ ] 토픽 `auto.create` + 기본 `num.partitions=1` → concurrency 올려도 1 스레드만 활성
- [ ] Consumer 내 동기 외부 호출 → 처리 시간 누적으로 poll timeout 위험

#### HTTP Client
- [ ] `SimpleClientHttpRequestFactory` → 매 요청 새 TCP 소켓 (커넥션 풀 없음, Keep-Alive 미사용)
- [ ] 커넥션 풀 없이 대량 호출 → ephemeral port 고갈, TIME_WAIT 소켓 누적

#### 동시성
- [ ] Redis check-then-act (hasKey → set) → TOCTOU 레이스 컨디션 (SET NX로 원자화 필요)
- [ ] `@Transactional` + Unique 제약 → 동시 요청 시 DeadlockLoserDataAccessException 가능

#### Circuit Breaker
- [ ] `slidingWindowSize` 너무 작음 (< 50) → 소수 실패에 과민 반응, 불필요한 OPEN
- [ ] CB OPEN 시 연쇄 영향 (예: Kafka Consumer pause) → 장애 증폭

### Step 3: Bottleneck 분석

**정의**: 설정값이 부하 조건과 수치적으로 맞지 않아 성능 저하를 일으키는 경우.

**점검 항목**:

| 영역 | 점검 | 공식/기준 |
|------|------|-----------|
| DB 커넥션 풀 | HikariCP `maximumPoolSize` vs 동시 스레드 수 | 풀 < 스레드의 1/4이면 병목 |
| 스레드 풀 | Tomcat `threads.max` vs 목표 TPS | TPS / (1000ms / avg_latency_ms) |
| Kafka 파티션 | 토픽 파티션 수 vs Consumer concurrency | 파티션 < concurrency면 유휴 스레드 |
| Kafka Consumer | concurrency 기본값 1 vs 목표 처리량 | 단일 스레드 max = 1000/처리ms msg/s |
| Redis 풀 | Lettuce pool 미설정 vs 동시 Redis 호출 수 | pool 없으면 직렬화됨 |
| HTTP 타임아웃 | connect + read timeout vs SLA | timeout > SLA면 의미 없음 |
| 배치 크기 | `max.poll.records` vs 레코드 처리 시간 | records x time_per_record < poll.interval |
| JVM | Heap 사이즈 vs 동시 객체 수 | 미설정이면 기본 256MB |

### Step 4: 리포트 출력

각 발견 사항마다 아래 형식으로 출력한다:

```
### 발견 N: [제목]

- **유형**: [숨겨진 동작] 또는 [병목]
- **현상**: 예상되는 성능 이상 (또는 실측 메트릭이 있으면 관찰된 현상)
- **원인**: 어떤 설정/동작이 문제인가
- **근거**: 공식 문서, 소스 코드, 또는 수치 계산
- **개선안**: 구체적인 설정 변경 또는 코드 수정 (코드 블록 포함)
- **예상 효과**: 변경 후 기대되는 개선
```

마지막에 요약 테이블 출력:

```
| # | 유형 | 핵심 원인 | 영향도 | 수정 난이도 |
```

영향도 = Critical / High / Medium / Low
수정 난이도 = Low (설정 변경) / Medium (코드 수정) / High (아키텍처 변경)

## 실측 메트릭이 있는 경우

Grafana/Prometheus 지표가 제공되면 정적 분석 결과와 대조한다:
- `hikaricp_connections_active` → 발견의 커넥션 풀 병목 확인
- `kafka_consumer_fetch_manager_records_lag` → Consumer 처리 지연 확인
- `jvm_gc_pause_seconds` → GC 영향 확인
- `http_server_requests_seconds` → 레이턴시 분포 확인
- `resilience4j_circuitbreaker_state` → CB OPEN 빈도 확인

## 주의사항

- 정적 분석은 **추론**이다. "~할 수 있다", "~위험이 있다"로 표현한다.
- 실측 데이터 없이 "~이 발생했다"로 단정하지 않는다.
- 각 발견에 반드시 공식 문서 또는 프레임워크 소스 레벨 근거를 포함한다.
- 우선순위는 영향도 대비 수정 난이도 기준으로 정렬한다.
