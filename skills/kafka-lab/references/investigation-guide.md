# 예상 밖 동작 분석 가이드

## 검색 우선순위

1. Kafka 공식 문서: `https://kafka.apache.org/documentation/`
2. Producer/Consumer 설정: `https://kafka.apache.org/42/configuration/`
3. Apache JIRA: `https://issues.apache.org/jira/browse/KAFKA-{번호}`
4. Kafka KIP: `https://cwiki.apache.org/confluence/display/KAFKA/`

## 분석 절차

```
1. 로그에서 핵심 단서 추출
   → errorCode, retrying 횟수, elapsed, ISR 상태

2. 가설 수립 (가장 가능성 높은 순서)
   → 설정값 기반 / 타이밍 기반 / 버전 기반

3. 공식 문서에서 근거 확인
   → WebFetch로 해당 설정 페이지 직접 조회

4. 소스 코드 레벨 확인 (필요시)
   → GitHub Kafka 소스 (Sender.java, RecordAccumulator.java 등)

5. 결론 도출
   → "공식 문서 기준" vs "실제 동작" 명확히 구분
```

## 자주 나오는 예상 밖 동작

| 현상 | 원인 | 근거 |
|------|------|------|
| delivery.timeout.ms 지나도 재시도 계속 | count=N × delivery.timeout.ms, runCatching이 삼킴 | KIP-91 |
| 브로커 1대 down인데 에러 없음 | ISR=2, min.insync.replicas=2 충족 | Kafka broker configs |
| acks=0인데 NOT_ENOUGH_REPLICAS | acks는 Producer 설정, min.insync.replicas는 Broker 설정 | 별개 레이어 |
| 토픽 없는데 메시지 전송 성공 | auto.create.topics.enable=true (기본값) | Kafka broker configs |

## 틀린 분석 수정 원칙

사용자가 분석을 교정하면:
1. 즉시 인정하고 올바른 근거 찾기
2. 메모리에 잘못된 내용 업데이트
3. REPORT.md에 올바른 내용으로 재작성
