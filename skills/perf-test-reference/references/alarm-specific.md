# alarm 프로젝트 특화 가이드

이전 테스트 리뷰에서 발견된 이 프로젝트 고유의 주의점.

## 1. OSIV 효과 분리 실험

이전에 증명하지 못한 "OSIV가 근본 원인"을 검증하기 위해 아래 3개 라운드를 실행한다.

| 라운드 | OSIV | HikariCP pool | 비교 목적 |
|--------|------|---------------|----------|
| A | ON | 10 (baseline) | 기준선 |
| B | OFF | 10 | OSIV 단독 효과 |
| C | ON | 30 | pool 증가 단독 효과 |

- B가 A 대비 크게 개선 → OSIV가 주 원인
- C가 A 대비 크게 개선 → pool 크기가 주 원인
- B와 C 모두 개선 → 둘 다 기여, 기여도 비율 기록

## 2. Kafka 파티션/concurrency 변경 기록

파티션 수를 변경할 때는 반드시 기록한다 (이전 테스트에서 파티션 1→6 시점이 불명확했음).

```markdown
## Kafka 토픽 설정 변경 이력

| 시점 | 토픽 | 파티션 | concurrency | 비고 |
|------|------|--------|-------------|------|
| baseline | notification | 1 | 1 | 초기 상태 |
| Round X | notification | 6 | 1 | 파티션만 확장 |
| Round Y | notification | 6 | 6 | concurrency 적용 |
```

## 3. Debezium/CDC 포함 여부

이 프로젝트는 Debezium CDC를 사용하므로 아래를 명시한다.

- [ ] Debezium connector 활성화 상태에서 테스트했는가?
- [ ] CDC가 MySQL binlog 읽기로 인한 추가 I/O가 있는가?
- [ ] CDC가 Kafka에 발행하는 메시지량이 테스트 부하에 포함되는가?
- [ ] CDC OFF 상태에서 baseline을 잡고, ON 상태에서 비교하는 것을 권장

## 4. poll 안전 공식 지속 모니터링

readTimeout 변경 시 항상 아래를 재계산한다.

```
안전 공식: max.poll.records × worst_case_per_record < max.poll.interval.ms

현재: max.poll.records = {N}, readTimeout = {X}s, max.poll.interval.ms = {Y}ms
계산: {N} × {X}s = {결과}s vs {Y/1000}s → 충족/위반 (여유율: {%})

※ 경계값(=)은 "충족"이 아닌 "여유 0%"로 기록한다
※ 여유율 최소 30% 이상 권장
```

## 5. Consumer end-to-end latency 측정

이전 테스트에서 빠졌던 항목. Consumer 처리량(msg/s)만이 아닌 **지연 시간**도 측정한다.

```
측정 방법:
1. Producer 발행 시각을 메시지 헤더에 포함
2. Consumer 처리 완료 시각과의 차이를 Micrometer 히스토그램으로 수집
3. Grafana에서 p50/p95/p99 시각화

지표명 예시: kafka.consumer.e2e.latency
```

## 6. 이전 테스트 수치 불일치 해소

baseline p95가 18ms인데 OSIV OFF 전 p95가 209ms였던 불일치를 방지하기 위해:

- [ ] **모든 라운드에서 동일 k6 스크립트 사용** (파일 경로 + git 커밋 해시 기록)
- [ ] k6 스크립트를 변경했다면 **이전 라운드와 직접 비교하지 않음**
- [ ] 스크립트 변경이 필요한 경우, 새 baseline을 설정하고 이후 라운드와 비교

## 7. 환경 구성

### reset-test-data.sh

```bash
#!/bin/bash
docker exec alarm-mysql mysql -uroot -p$MYSQL_ROOT_PASSWORD -e "
  TRUNCATE TABLE alarm_db.notification;
  TRUNCATE TABLE alarm_db.outbox;
"
docker exec alarm-redis redis-cli FLUSHALL
echo "✅ DB TRUNCATE + Redis FLUSH 완료"
```

### 컨테이너 리소스 제한 (재현성을 위해 권장)

```yaml
alarm-api:
  mem_limit: 1g
  cpus: "2.0"
mysql:
  mem_limit: 2g
  cpus: "2.0"
```

### 목표 산출 (ADR-001 기준)

```
- 일 30M건 → 평균 347 TPS
- 피크 5,000 TPS (쓰기), 10,000 TPS (조회)
- write:read = 1:2 (쓰기 피크 기준)
- SLO: p95 ≤ 200ms, p99 ≤ 500ms, 에러율 ≤ 0.1%
```
