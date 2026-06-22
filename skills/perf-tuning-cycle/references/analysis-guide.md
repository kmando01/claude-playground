# 성능 분석 가이드 (Analysis Reference)

성능 테스트 결과를 분석할 때 두 가지 관점으로 본다.

## 관점 1: 숨겨진 설정 동작 (Hidden Behavior)

**"이 설정이 내부적으로 이렇게 동작하는 줄 몰랐다"에 해당하는 경우.**
단순 리소스 부족이 아니라, 프레임워크/라이브러리의 숨겨진 내부 동작이 원인.

### 분석 방법
1. 성능 테스트에서 **이상 현상**(갑작스러운 TPS 드롭, 레이턴시 스파이크, 간헐적 타임아웃)을 먼저 식별
2. 해당 현상이 프레임워크의 숨겨진 내부 동작 때문인지 추론
3. 공식 문서나 소스 코드 레벨의 근거를 함께 제시

### 체크리스트

#### JPA/Hibernate
- [ ] `GenerationType.IDENTITY` → Hibernate 배치 INSERT 비활성화. persist()마다 즉시 flush + SELECT LAST_INSERT_ID
  - **증상**: 쓰기 TPS가 기대보다 낮음. 건당 INSERT가 느림
  - **근거**: Hibernate 공식 — "IDENTITY generation disables JDBC batching for INSERT statements"
- [ ] `open-in-view=true` (Spring Boot 기본) → Controller 응답 완료까지 DB 커넥션 점유
  - **증상**: HikariCP pending 증가, 부하 시 갑작스런 응답 지연
  - **근거**: Spring Boot 문서 — "spring.jpa.open-in-view is enabled by default" + OSIV 경고 로그
- [ ] `@Transactional` 안에서 외부 API/Redis 호출 → 응답 대기 동안 DB 커넥션 점유
  - **증상**: 외부 API 지연이 DB 커넥션 고갈로 전파. 무관한 API까지 느려짐
  - **근거**: Spring @Transactional은 메서드 시작~종료까지 커넥션 유지
- [ ] Lazy Loading + `toString()`/직렬화 → N+1 쿼리 암묵적 발생
  - **증상**: 단건은 빠른데 목록 API가 비정상적으로 느림
- [ ] `AUTO` GenerationType → DB 방언에 따라 시퀀스 조회용 별도 커넥션 추가 점유
  - **증상**: persist() 한 번에 커넥션 2개 점유, 풀 작으면 데드락

#### Redis
- [ ] Lettuce 기본 단일 커넥션 공유 → 동기 API 사용 시 head-of-line blocking
  - **증상**: Redis 자체 응답은 빠른데 애플리케이션 전체 p95 높음
  - **근거**: Lettuce 문서 — 기본 모드는 단일 커넥션 멀티플렉싱, 동기 호출 시 순차 처리
- [ ] `RedisTemplate` 동기 호출을 `@Transactional` 안에서 → DB 커넥션 + Redis 대기 동시 점유
  - **증상**: Redis 지연이 DB 커넥션 고갈로 증폭

#### Kafka
- [ ] `max.poll.records × 레코드당 처리시간 > max.poll.interval.ms` → 리밸런싱 트리거
  - **증상**: Consumer 주기적으로 멈춤, lag 급증 후 회복 반복 (톱니 패턴)
  - **근거**: KIP-62 — poll interval 초과 시 Consumer를 dead로 간주
- [ ] `enable-auto-commit=false` + BATCH AckMode → 처리 중 실패 시 전체 배치 재처리
  - **증상**: 일부 메시지 실패 시 중복 처리 급증
- [ ] `auto.create + num.partitions=1` → concurrency 올려도 1 스레드만 활성
  - **증상**: concurrency=6 설정했는데 처리량 변화 없음. 로그에 1개 스레드만 출력
- [ ] Consumer 내 동기 외부 호출 → 처리 시간 누적으로 poll timeout 위험
  - **증상**: 외부 API 지연 시 Kafka 리밸런싱 발생

#### HTTP Client
- [ ] `SimpleClientHttpRequestFactory` → 매 요청 새 TCP 소켓 (커넥션 풀 없음, Keep-Alive 미사용)
  - **증상**: 외부 호출 많을 때 TIME_WAIT 소켓 누적, ephemeral port 고갈
  - **근거**: Spring 문서 — SimpleClientHttpRequestFactory는 "simple, no connection pooling"
- [ ] 커넥션 풀 없이 대량 호출 → ephemeral port 고갈

#### 동시성
- [ ] Redis check-then-act (`hasKey` → `set`) → TOCTOU 레이스 컨디션
  - **증상**: 동시 요청 시 중복 처리 발생
  - **개선**: SET NX로 원자화
- [ ] `@Transactional` + Unique 제약 → 동시 요청 시 DeadlockLoserDataAccessException
  - **증상**: 간헐적 500 에러, 부하 비례 증가

#### Circuit Breaker
- [ ] `slidingWindowSize` 너무 작음 (< 50) → 소수 실패에 과민 반응, 불필요한 OPEN
  - **증상**: 간헐적 CB OPEN, 정상 요청도 차단
- [ ] CB OPEN 시 연쇄 영향 (예: Kafka Consumer pause) → 장애 증폭
  - **증상**: 외부 API 일시 장애 → 전체 Consumer 중단

#### Tomcat
- [ ] 기본 스레드 200개 vs HikariCP 기본 10개 → 190개 스레드가 커넥션 대기
  - **증상**: 부하 증가 시 갑자기 응답시간 폭증 (선형이 아닌 cliff 형태 저하)
  - **근거**: 스레드가 풀보다 훨씬 많으면 대기 큐에서 병목

---

## 관점 2: 실제 병목 지점 (Bottleneck)

**설정값 자체가 현재 부하 조건과 수치적으로 맞지 않아서 성능 저하를 일으키는 경우.**

### 분석 방법
1. 부하 조건(동시 사용자 수, 목표 TPS)과 현재 설정값의 **수치적 불일치**를 찾음
2. Prometheus 메트릭으로 근거를 뒷받침

### 점검 테이블

| 영역 | 점검 | 판단 공식/기준 | Prometheus 지표 |
|------|------|---------------|-----------------|
| DB 커넥션 풀 | HikariCP `maximumPoolSize` vs 동시 스레드 | pending > 0 또는 active ≈ max | `hikaricp_connections_pending`, `hikaricp_connections_active` |
| 스레드 풀 | Tomcat `threads.max` vs 목표 TPS | 필요 스레드 ≈ TPS × avg_latency_s | `tomcat_threads_busy_threads`, `tomcat_threads_current_threads` |
| Kafka 파티션 | 파티션 수 vs Consumer concurrency | 파티션 < concurrency면 유휴 스레드 | 토픽 describe로 확인 |
| Kafka Consumer | concurrency vs 목표 처리량 | 단일 스레드 max ≈ 1000/처리ms msg/s | `kafka_consumer_fetch_manager_records_lag_max` |
| Redis 풀 | Lettuce pool 미설정 vs 동시 Redis 호출 | pool 없으면 직렬화됨 | `lettuce_command_completion_seconds` |
| HTTP timeout | connect + read timeout vs SLA | timeout > SLA면 의미 없음 | 외부 호출 duration 메트릭 |
| 배치 크기 | `max.poll.records × time_per_record` | > `max.poll.interval.ms`면 리밸런싱 | Consumer 로그에서 리밸런싱 여부 |
| JVM Heap | 미설정 → 기본 256MB | GC pause 빈도로 확인 | `jvm_gc_pause_seconds_count`, `jvm_memory_used_bytes` |

---

## 교차 분석 매트릭스 (외부 + 내부 → 원인 특정)

k6(외부)에서 현상을 잡고, Prometheus(내부)로 원인을 특정한다:

| k6 현상 | + 내부 지표 | → 원인 유형 | 확인 방법 |
|---------|------------|------------|-----------|
| p95 높음 | HikariCP pending 높음 | [숨겨진 동작] OSIV / [병목] pool size | OSIV 설정 확인, pool vs 스레드 비율 |
| p95 높음 | GC pause 높음 | [병목] 힙 부족 | heap 사용률, GC 로그 |
| p95 높음 | 내부 지표 정상 | [숨겨진 동작] 외부 호출 blocking | client-external 응답시간, HTTP client 종류 |
| 에러율 높음 | HikariCP active = max | [병목] 커넥션 풀 고갈 | pool size 대비 동시 요청 수 |
| TPS 정체 | Kafka lag 증가 | [병목] Consumer < 유입 / [숨겨진 동작] 파티션=1 | 파티션 수, concurrency, 처리시간 |
| TPS 정체 | 내부 지표 정상 | k6 VU 부족 또는 인프라 한계 | VU 수 확인, 인프라 CPU/메모리 |
| 간헐적 타임아웃 | 주기적 패턴 | [숨겨진 동작] 리밸런싱 / CB OPEN 연쇄 | Consumer 로그, CB 상태 메트릭 |
| 부하 증가 시 급격한 저하 (cliff) | Tomcat 스레드 포화 | [숨겨진 동작] 스레드 vs 커넥션 비대칭 | 스레드 busy ≈ max 시점과 응답시간 급증 시점 대조 |

---

## 발견 사항 출력 형식

각 발견 사항마다:

```markdown
### 발견 N: [제목]

- **유형**: [숨겨진 동작] 또는 [병목]
- **현상**: 성능 테스트에서 관찰된 이상 (수치 포함)
- **원인**: 어떤 설정/동작이 문제인가
- **근거**: 공식 문서, 소스 코드, 또는 수치 계산
- **개선안**: 구체적인 설정 변경 또는 코드 수정 (코드 블록 포함)
- **예상 효과**: 변경 후 기대되는 개선
```

마지막에 요약 테이블:

| # | 유형 | 핵심 원인 | 영향도 | 수정 난이도 |
|---|------|----------|--------|-----------|

- **영향도**: Critical / High / Medium / Low
- **수정 난이도**: Low (설정 변경) / Medium (코드 수정) / High (아키텍처 변경)
- **우선순위**: 영향도 대비 수정 난이도 기준으로 정렬 (High 영향 + Low 난이도 먼저)

---

## Action Items 관리

### 형식

분석 후 미확인 항목과 개선 과제를 Action Items로 보고서에 기록한다. 다음 사이클에서 이전 Action Items를 반드시 참조한다.

```markdown
### 미확인 Hidden Behavior

| ID | 항목 | 잠재 영향 | 확인 방법 | 상태 |
|----|------|----------|----------|------|
| A1 | IDENTITY 배치 INSERT 비활성화 | 쓰기 TPS 상한 | Hibernate SQL 로그, Stress 테스트 | TODO |
| A2 | Lettuce 단일 커넥션 blocking | Redis 호출 직렬화 | lettuce 메트릭, Consumer 병렬화 후 | TODO |

### 성능 병목 개선

| ID | 항목 | 목적 | 방법 | 상태 |
|----|------|------|------|------|
| B1 | Stress 테스트 5K TPS | 한계점 측정 | k6 stress.js | TODO |
| B2 | Consumer 비동기 전환 | 11 msg/s 한계 해소 | CompletableFuture 설계 | TODO |
```

### 상태 관리 규칙

- **TODO**: 미확인/미착수
- **IN_PROGRESS**: 현재 사이클에서 진행 중
- **DONE**: 확인 완료 또는 해소됨. 근거 기록 (예: "OSIV OFF로 Pending 0 — comparison 보고서 참조")
- **N/A**: 해당 없음으로 판명 (예: "코드 검토 결과 @Transactional 안 외부 호출 없음")
- **DEFERRED**: 현재 우선순위 아님. 사유 기록

### 사이클 간 연결

매 사이클 Step 3 시작 시:
1. 이전 보고서의 Action Items 중 TODO 항목 확인
2. 이번 테스트 결과로 확인 가능한 항목이 있으면 상태 업데이트
3. 새로 발견된 항목은 새 ID로 추가

---

## 주의사항

- **실측 없이 단정 금지**: 내부 지표가 없는 상태에서 "~이 발생했다"로 단정하지 않는다. "~할 수 있다", "~위험이 있다"로 표현
- **교차 검증 필수**: k6 결과만으로 원인을 추측하지 않는다. 반드시 내부 지표와 교차
- **이전 보고서 참조**: `docs/perf-reports/` 내 이전 결과와 비교하여 추이 파악
- **static-perf-analysis 스킬 참조**: 실측 전 사전 점검은 `static-perf-analysis` 스킬의 체크리스트 활용
- **DB/Redis 초기화**: A/B 비교 시 테스트 간 반드시 `TRUNCATE + FLUSHDB`. 데이터 누적은 비교를 왜곡한다
- **Grafana 캡처**: 전체 대시보드 URL 대신 `d-solo` + `panelId`로 개별 패널 캡처. 접힌 패널은 N/A 렌더링
