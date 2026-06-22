# 다이어그램 작성 규칙

## 전체 시스템 아키텍처 (graph TD)

### Edge 라벨 원칙
- 동일 노드로 2개 이상의 화살표가 나갈 때 **반드시 라벨로 의도를 구분**한다.
- 단방향/양방향 모두 라벨 명시.

```mermaid
A -->|INSERT| DB
A -->|이벤트 발행| MQ
Cache -->|조회 캐싱| A
Cache -->|캐시 무효화| A
DB -->|binlog CDC| Connector
```

---

## 쓰기 시퀀스

### 비동기 메시지 발행 — 변환 스텝 명시
메시지 브로커로 이벤트를 발행할 때 중간 변환(e.g. EventRouter, Transformer)이 있으면 명시한다.

```
Connector->>Connector: EventRouter Transform
    aggregateId → 메시지 key
    payload(JSON) → 메시지 value
    eventType → 헤더 + 토픽 라우팅
```

### HTTP Retry vs 메시지 ErrorHandler — 레이어 명확히 분리

**잘못된 표현 (혼동 유발)**
```
External-->>Consumer: 503 (Retry 소진)
```

**올바른 표현**
```
External-->>Consumer: 503 (HTTP Retry N회 소진)
Note over Consumer: HTTP 레벨 retry 소진 후
    메시지 ErrorHandler로 전파
```

### Circuit Breaker OPEN 구간 — Note 필수
```
Note over MQ,Consumer: CB OPEN 구간: Consumer pause 상태
    → 메시지 MQ에 적체, resume 후 일괄 소비
```

### 재시도 분기 — 압축 + 상세 섹션 참조
쓰기 메인 시퀀스에서는 재시도 분기를 압축하고, 상세는 별도 섹션으로 위임한다.
```
Note over MQ,Consumer: retry 상세 흐름은 섹션 2-1 참조
```

---

## 재시도/DLQ 상세 시퀀스

### 섹션 상단 — 재시도 레이어 순서 반드시 명시
```
Note over MQ,Consumer: 재시도 레이어 순서
    ① HTTP Retry(max=N, WaitDms×배수) 소진 → 예외 throw
    ② 메시지 ErrorHandler가 catch
       → BackOff(Xms, Y회) 재시도
    ③ Y회 소진 → DeadLetterRecoverer → dead 토픽
    ※ 역직렬화 오류(e.g. JsonProcessingException)는 ②를 건너뛰고 즉시 dead 라우팅
```

설정값(N, WaitD, X, Y)은 코드에서 읽어 실제 값으로 채운다.

### DLQ 처리 현황 — 필수 명시
```
Note over MQ: dead 토픽
    현재: 수동 확인
    향후: admin replay API 예정 (구현 시 교체)
```
실제 구현 상태에 맞게 수정한다.

---

## 읽기 시퀀스

### 캐시 정책 — 조건·키 패턴 명시
```
@Cacheable 조회
key = "{도메인}:{requester}:{size}"
condition: cursor == null (첫 페이지만)
```

### 캐시 무효화 — 일괄 패턴 명시
```
API->>Cache: evict({requester})
    {도메인}:{requester}:[size1, size2, size3] 일괄 무효화
```
CACHED_SIZES 등 실제 값은 코드에서 읽는다.

---

## 배치/스케줄러 시퀀스

### 실패 처리 — 현재 상태와 개선 계획 함께 명시
```
Manager-->>-Scheduler: 완료 (실패 시 log.error만 기록)
Note over Scheduler: MVP 단계 — 운영 안정화 후 알림 연동 예정
```
이미 알림/메트릭 연동이 구현된 경우 해당 내용으로 교체한다.

### 단계 독립성 — Note로 명시
```
Note over Scheduler: 각 단계 독립 try-catch
    단계 A 실패해도 단계 B는 계속 실행
```

---

## Mermaid 문법 주의사항

| 항목 | 규칙 |
|------|------|
| `-->>` 화살표 텍스트 | `<br/>` 사용 금지 → Note로 분리 |
| `Note over A,B:` | 멀티라인은 `<br/>`로 줄바꿈 |
| `loop` / `alt` / `else` | 중첩 2단계까지만. 더 깊으면 별도 섹션으로 분리 |
| `autonumber` | 모든 sequenceDiagram 상단에 추가 |
| participant alias | `as` 뒤에 `<br/>`로 포트번호/역할 추가 가능 |
