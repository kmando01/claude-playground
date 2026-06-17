# 실험 전 사전 검증 체크리스트

## 인프라 체크

```bash
# 브로커 상태
docker ps | grep kafka

# 토픽 상태 (리더/ISR 기준선)
docker exec kafka-1 /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server kafka-1:19092 \
  --describe --topic event-participation

# 앱 상태
curl -s http://localhost:8080/actuator/health | jq .
```

## commands.sh 검토 항목

| 체크 | 항목 |
|------|------|
| [ ] | Spring Profile 명시 여부 (`SPRING_PROFILES_ACTIVE=xxx`) |
| [ ] | Profile 파일 존재 여부 (`application-xxx.yml`) |
| [ ] | request body에 `eventType` 필드 포함 여부 |
| [ ] | 브로커 stop 후 복구 명령 존재 여부 |
| [ ] | 실험 의도와 시나리오 일치 여부 |

## 자주 발생하는 실수

### eventType 누락
```json
// 잘못됨
{"count": 100, "mode": "sync", "eventId": "EVT-001"}

// 올바름
{"count": 100, "mode": "sync", "eventId": "EVT-001", "eventType": "EVENT"}
```

### acks 실험 시나리오 주의
- `acks=0`: 브로커 응답을 아예 안 기다림 → 브로커 down과 무관하게 성공 응답
  - 단, min.insync.replicas는 브로커 설정이라 acks=0이어도 ISR 부족 시 저장 자체가 안 됨
- `acks=1`: 리더만 확인 → 리더 down 후 재선출 전에 보내야 유실 발생
- `acks=all`: min.insync.replicas 브로커 수 이상 ISR 유지 필요

### ISR 변화 타이밍
브로커 stop 후 즉시 describe하면 ISR이 아직 업데이트 안 됐을 수 있음.
약 5-10초 대기 후 확인 권장.
