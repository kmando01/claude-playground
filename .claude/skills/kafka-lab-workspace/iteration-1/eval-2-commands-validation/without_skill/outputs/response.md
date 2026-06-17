# Lab 2-4 commands.sh 분석

## 파일 경로
`/Users/mando/IdeaProjects/kafka-labs/labs/lab2/lab2-4/commands.sh`

---

## 전체 구조 요약

Lab 2-4는 **배치와 처리량 튜닝** 실험으로, 두 가지 파트로 나뉩니다:

1. **프로파일 A~E**: batch.size / linger.ms / compression 조합별 100,000건 처리량 비교
2. **실험 F**: buffer.memory 꽉 참 → TimeoutException 유발 시나리오

---

## 주의사항: 핵심 문제점 발견

### batch-A ~ batch-E 프로파일 YML이 존재하지 않음

`src/main/resources/` 디렉토리를 확인한 결과, 현재 존재하는 프로파일 파일들:
- `application-inflight1.yml`
- `application-inflight5.yml`
- `application-inflight5-noidemp.yml`
- `application-small-buffer.yml`
- `application-small-request.yml`
- `application-acks0.yml`, `application-acks1.yml`, `application-acksall.yml`

**`application-batch-A.yml` ~ `application-batch-E.yml` 파일이 없습니다.**

commands.sh 주석에서 `SPRING_PROFILES_ACTIVE=batch-A ./gradlew bootRun` 같은 실행 방법을 안내하고 있지만, 해당 프로파일 파일이 없으면 앱이 기본 설정(`application.yml`)으로만 동작합니다. 즉, **모든 프로파일이 동일한 기본 설정(16KB batch, linger.ms=0, compression=none)으로 실행**되어 의미 있는 비교 실험이 불가능합니다.

---

## 프로파일별 설정 (REPORT.md 기준)

| 프로파일 | batch.size | linger.ms | compression | buffer.memory |
|---------|-----------|-----------|-------------|--------------|
| A (기본) | 16KB | 0 | none | 32MB |
| B | 64KB | 5 | none | 32MB |
| C | 64KB | 20 | snappy | 32MB |
| D | 128KB | 50 | snappy | 64MB |
| E | 64KB | 5 | lz4 | 32MB |

---

## 명령어 분석

### 파트 1: 프로파일별 처리량 테스트

각 프로파일 전환 순서:
1. 앱을 해당 프로파일로 재시작 (주석 처리된 bootRun 명령어)
2. curl로 100,000건 async produce 호출

```bash
# 예: 프로파일 A
# SPRING_PROFILES_ACTIVE=batch-A ./gradlew bootRun
curl -s -X POST http://localhost:8080/api/labs/produce-bulk \
  -H 'Content-Type: application/json' \
  -d '{"count": 100000, "mode": "async", "eventId": "EVT-BATCH-A"}' | jq .
```

**주의**: `application.yml`의 서버 포트가 **8082**인데 curl은 **8080**을 사용합니다. 포트가 맞지 않아 연결 실패할 수 있습니다.

### 파트 2: 실험 F (small-buffer 프로파일)

`application-small-buffer.yml`은 실제로 존재하며 내용은 아래와 같습니다:
```yaml
spring:
  kafka:
    producer:
      properties:
        buffer.memory: 1048576  # 1MB
        linger.ms: 100
        max.block.ms: 3000      # 3초 후 TimeoutException
```

실험 순서:
1. `SPRING_PROFILES_ACTIVE=small-buffer` 로 앱 재시작
2. `docker stop kafka-1` → 브로커 1대 다운
3. 10,000건 async produce → buffer.memory 초과 → TimeoutException 관찰
4. `docker start kafka-1` → 브로커 복구

---

## 실험 시작 전 필요한 조치

### 1. batch 프로파일 YML 파일 생성 필요

각 프로파일 파일을 `src/main/resources/`에 생성해야 합니다:

**`application-batch-A.yml`** (기본값이지만 명시적으로 작성):
```yaml
spring:
  kafka:
    producer:
      batch-size: 16384       # 16KB
      properties:
        linger.ms: 0
        compression.type: none
        buffer.memory: 33554432  # 32MB
```

**`application-batch-B.yml`**:
```yaml
spring:
  kafka:
    producer:
      batch-size: 65536       # 64KB
      properties:
        linger.ms: 5
        compression.type: none
        buffer.memory: 33554432
```

**`application-batch-C.yml`**:
```yaml
spring:
  kafka:
    producer:
      batch-size: 65536
      properties:
        linger.ms: 20
        compression.type: snappy
        buffer.memory: 33554432
```

**`application-batch-D.yml`**:
```yaml
spring:
  kafka:
    producer:
      batch-size: 131072      # 128KB
      properties:
        linger.ms: 50
        compression.type: snappy
        buffer.memory: 67108864  # 64MB
```

**`application-batch-E.yml`**:
```yaml
spring:
  kafka:
    producer:
      batch-size: 65536
      properties:
        linger.ms: 5
        compression.type: lz4
        buffer.memory: 33554432
```

### 2. 포트 확인

`application.yml`의 서버 포트를 확인하세요. 현재 설정은 `8082`이지만 commands.sh는 `8080`을 사용합니다. 둘 중 하나를 맞춰야 합니다.

---

## 실험 진행 순서 (권장)

1. batch-A ~ batch-E 프로파일 YML 파일 생성
2. 포트 통일 (commands.sh의 8080 → 8082 또는 application.yml의 8082 → 8080)
3. Kafka 클러스터 실행: `./docker/up.sh`
4. 각 프로파일별로:
   - `SPRING_PROFILES_ACTIVE=batch-A JAVA_HOME=... ./gradlew bootRun`으로 앱 시작
   - curl 명령어 실행하여 결과 기록
   - REPORT.md에 소요시간, TPS 기록
5. 실험 F (small-buffer):
   - `SPRING_PROFILES_ACTIVE=small-buffer`로 앱 재시작
   - `docker stop kafka-1`
   - curl 10,000건 실행 및 TimeoutException 관찰
   - `docker start kafka-1`로 복구

---

## 요약

| 항목 | 상태 |
|------|------|
| batch-A~E 프로파일 YML | 없음 - 생성 필요 |
| small-buffer 프로파일 YML | 존재함 |
| commands.sh 포트 (8080) | application.yml 포트(8082)와 불일치 |
| 실험 F 시나리오 | 정상 (docker stop/start 포함) |
