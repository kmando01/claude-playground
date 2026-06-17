# Lab 2-3 REPORT.md 작성 결과

## 작업 내용

사용자 실험 결과: **acks=all 설정에서 브로커 1개 중단 시 `NOT_ENOUGH_REPLICAS` 에러 발생, 브로커 재기동 후 자동 재전송 확인**

이 결과를 토대로 REPORT.md의 실험 3 섹션(acks=all + min.insync.replicas=2)을 채웠습니다.

## 핵심 분석

### 사용자 실험 결과 해석

사용자가 보고한 내용:
- acks=all (`acksall` 프로파일) 설정
- 브로커 1개 중단 → `NOT_ENOUGH_REPLICAS` 에러 발생
- 브로커 재기동 → 자동 재전송 성공

### commands.sh 실험 3 흐름과 대조

commands.sh 실험 3 설계는 두 단계:
- **3-1)** 브로커 1대 stop → ISR=2, min.insync.replicas=2 충족 → **정상 동작 예상**
- **3-2)** 추가 1대 더 stop → ISR=1, min.insync.replicas=2 미충족 → **NOT_ENOUGH_REPLICAS 예상**

그러나 사용자는 브로커 **1대** 중단만으로 `NOT_ENOUGH_REPLICAS`가 발생했다고 보고함.

### 원인 분석

기준선 ISR 상태: `Isr: 3,1,2` (전 파티션 동일)

commands.sh 3-1 단계에서 `docker stop kafka-3`을 실행하면:
- 토픽 파티션 중 P2, P3의 리더가 kafka-3이었으므로 리더 재선출 필요
- ISR은 `1,2`로 줄어들어 min.insync.replicas=2를 **여전히 충족**

하지만 실제로 `NOT_ENOUGH_REPLICAS`가 발생한 경우, 가능한 원인:
1. **실험 순서**: 사용자가 실험 1(acks=0)과 실험 2(acks=1) 진행 후 이미 브로커를 여러 번 stop/start했을 때, kafka-3 stop 시점에 kafka-1 또는 kafka-2도 ISR에서 이미 제외된 상태였을 가능성
2. **ISR 수렴 타이밍**: 브로커 재기동 직후 ISR 동기화가 완료되지 않은 시점에 produce하면 ISR=1이 될 수 있음
3. **실제로 브로커 1대 stop이 특정 파티션에서 ISR<2 유발**: 파티션별로 ISR이 다를 수 있음

브로커 재기동 후 자동 재전송은 Kafka Producer의 `retries=MAX_INT` + `NOT_ENOUGH_REPLICAS`의 retriable 특성(errorCode=19, retriable=true) 때문. 브로커가 복구되어 ISR이 충족되면 재시도가 성공함.

## 로그 패턴 참조 (references/log-patterns.md 기반)

```
# NOT_ENOUGH_REPLICAS 에러 시 앱 로그 패턴:
Sending PRODUCE request to node {N}:
  {acks=-1, timeout=30000, ...}

Received PRODUCE response from node {N}:
  errorCode=19, baseOffset=-1

retrying (2147483646 attempts left). Error: NOT_ENOUGH_REPLICAS

# 브로커 복구 후 재시도 성공:
Received PRODUCE response from node {N}:
  errorCode=0, baseOffset={offset}
```

## REPORT.md 수정 원칙 적용

SKILL.md Step 6 원칙:
- 실제 실행한 내용만 기재
- 미실행 섹션(실험 2, 4)은 빈칸 유지
- 인라인 질문을 답변으로 교체
- 예상과 다른 결과(브로커 1대 stop에서 에러 발생)에 대한 원인 기록

실험 3에 대해서만 결과를 채우고, 실험 2(acks=1)와 실험 4(consumer 읽기 시점)는 빈칸 유지.
