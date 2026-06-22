# 진단 가이드 (Step 4)

Action Item 처방 전 "왜 그 처방인가"를 숫자로 증명한다.

## 1. HikariCP 커넥션 점유 시간 분석

```bash
curl -sf http://localhost:{port}/actuator/prometheus | grep "hikaricp_connections_" | grep -v "^#"
```

**계산:**
```
평균 대기 = acquire_seconds_sum / acquire_seconds_count
평균 점유 = usage_seconds_sum  / usage_seconds_count  (≈ 트랜잭션 시간)
```

**판단 기준:**
| 패턴 | 의미 | 처방 |
|------|------|------|
| usage 높음 (>100ms) | 트랜잭션 안에 느린 작업 | 외부 API/Redis 트랜잭션 범위 밖으로 이동 |
| acquire 높음 | pool 경쟁 | pool 크기 조정 (Little's Law 역산) |
| usage/acquire > 5x | 점유가 대기를 압도 | 트랜잭션 범위 좁히기 우선 |

**Little's Law 역산:**
```
pool = target_TPS × T_db(ms) / 1000
예: 300 TPS × 50ms / 1000 = 15개
```

## 2. 트랜잭션 경계 정적 분석

각 `@Transactional` 메서드에서 확인:
- [ ] 트랜잭션 안에 외부 API 호출 있는가?
- [ ] 트랜잭션 안에 Redis 호출 있는가?
- [ ] 불필요한 SELECT (중복 체크)가 INSERT 전에 있는가?
- [ ] N+1 쿼리가 발생하는가?
- [ ] OSIV 켜진 상태에서 Controller → Service 흐름인가?

## 3. Consumer 파이프라인 상태 확인

```bash
# Kafka lag + consumed 확인
docker exec alarm-kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --describe --group alarm-consumer 2>&1 \
  | awk '/alarm-notification-work/{consumed+=$4; logend+=$5; lag+=$6} END{printf "consumed=%d logend=%d lag=%d\n", consumed, logend, lag}'

# Debezium 상태
curl -s http://localhost:8083/connectors/alarm-outbox-connector/status

# MySQL binlog 크기 (100MB 이상이면 정리 고려)
docker exec alarm-mysql mysql -uroot -proot \
  -e "SHOW BINARY LOGS;" 2>/dev/null
```

## 4. DIAGNOSIS.md 템플릿

`docs/perf-reports/{date}-{label}/DIAGNOSIS.md`:

```markdown
# 진단 보고서 — {date}-{label}

## HikariCP 커넥션 점유 시간
| 앱 | acquire 평균 | usage 평균 | usage/acquire 비율 | 해석 |
|----|-------------|-----------|-------------------|------|
| alarm-api | Xms | Yms | N배 | |
| alarm-consumer | Xms | Yms | N배 | |

## 트랜잭션 경계
| 파일:라인 | 메서드 | 트랜잭션 안 작업 | 문제 여부 |
|----------|--------|----------------|---------|

## 파이프라인 상태
- Kafka work lag: N (log-end: M, consumed: K)
- Debezium: RUNNING / FAILED
- MySQL binlog: Xmb (파일명)

## 처방 근거
각 Action Item ID별로 "왜 이 처방인가" 수식/수치로 설명
```
