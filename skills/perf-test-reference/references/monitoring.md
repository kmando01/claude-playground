# 모니터링 체크리스트

성능 테스트에서 **k6 외부 지표만으로는 원인 분석이 불가능**하다.
아래 내부 지표를 반드시 수집한다.

## 필수 수집 지표

### Application Layer

| 지표 | 소스 | 왜 필요한가 |
|------|------|------------|
| HikariCP Active / Pending / Total | Micrometer → Prometheus | 커넥션 풀 포화 여부 판단 |
| Tomcat threads (busy / max) | Micrometer → Prometheus | 스레드 풀 포화 여부 판단 |
| JVM Heap 사용량 / GC 횟수 / GC pause | Micrometer → Prometheus | GC가 latency spike 원인인지 판별 |
| HTTP 엔드포인트별 latency (p50/p95/p99) | Micrometer → Prometheus | 어떤 API가 느린지 특정 |

### Kafka Layer

| 지표 | 소스 | 왜 필요한가 |
|------|------|------------|
| Consumer lag (per partition) | Kafka metrics / Burrow | 처리 속도 < 유입 속도 판단 |
| Consumer 처리량 (msg/s) | Micrometer → Prometheus | concurrency 효과 측정 |
| Partition 분배 균등성 | Consumer group describe | 특정 파티션 편향 감지 |

### Infra Layer

| 지표 | 소스 | 왜 필요한가 |
|------|------|------------|
| CPU / Memory (컨테이너별) | cAdvisor / docker stats | 리소스 한계 도달 여부 |
| MySQL slow query | slow_query_log | 쿼리 레벨 병목 |
| MySQL connections (active / max) | SHOW STATUS | DB 커넥션 한계 |
| Redis ops/s, memory, latency | INFO, redis-cli --latency | Redis 단일 스레드 포화 |
| TIME_WAIT 소켓 수 | `ss -s` or `netstat` | ephemeral port 고갈 징후 |

## Grafana 대시보드 구성 권장

```
[Row 1] k6 Overview    : TPS, latency p50/p95/p99, error rate
[Row 2] HikariCP       : Active, Pending, Total, Connection Wait Time
[Row 3] Tomcat          : Busy Threads, Max Threads, Request Queue
[Row 4] Kafka Consumer  : Lag (per partition), msg/s, rebalance events
[Row 5] JVM             : Heap Used, GC Pause, Thread Count
[Row 6] Infra           : CPU%, Memory%, Disk I/O (per container)
[Row 7] Redis           : ops/s, connected clients, memory, latency
[Row 8] MySQL           : connections, slow queries, InnoDB buffer pool hit ratio
```

## 에러 분석 참조

| HTTP Status | 의미 | 조치 |
|-------------|------|------|
| 429 | Rate limiting | 서버 throttle 확인 |
| 500 | 서버 에러 | 로그 확인, 예외 유형 분류 |
| 502/503 | 프록시/서버 다운 | 리소스 한계, OOM 여부 |
| 504 | Gateway timeout | upstream 응답 지연 |
| 0 (connection refused) | 서버 수용 불가 | Tomcat 큐 포화, backlog 확인 |
