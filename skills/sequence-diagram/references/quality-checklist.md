# 시퀀스 다이어그램 품질 체크리스트

작성 완료 후 이 목록을 순서대로 확인한다.

## 전체 아키텍처 (섹션 1)

- [ ] 동일 노드로 2개 이상 화살표가 나갈 때 모두 라벨로 구분됨
- [ ] 비동기 연결(MQ, CDC 등)에 방향과 의미 라벨 있음
- [ ] 읽기·쓰기 양방향 캐시 화살표 모두 라벨 있음

## 쓰기/비동기 시퀀스 (섹션 2)

- [ ] 메시지 발행 시 중간 변환 스텝(EventRouter 등) 명시
- [ ] HTTP Retry 소진 → 메시지 ErrorHandler 전파 레이어 분리 표현
- [ ] CB OPEN 구간 Note: "Consumer pause → 적체 → resume 후 일괄 소비"
- [ ] retry 분기는 압축하고 상세 섹션 참조 Note 있음
- [ ] 설정값(retry max, backoff, CB threshold 등)이 코드 실제 값과 일치

## 재시도/DLQ 상세 시퀀스 (섹션 2-1)

- [ ] 섹션 상단 Note에 재시도 레이어 순서 ①②③ 명시
  - ① HTTP Retry 소진 → 예외 throw
  - ② 메시지 ErrorHandler → BackOff 재시도
  - ③ 소진 → DeadLetterRecoverer → dead 토픽
- [ ] 역직렬화 오류 등 notRetryable 예외의 즉시 dead 라우팅 명시
- [ ] DLQ Note에 현재 처리 방식(수동/admin API 등) 명시

## 읽기 시퀀스 (섹션 3)

- [ ] 캐시 조건(cursor == null 등) 명시
- [ ] 캐시 키 전체 패턴 명시 (실제 값 아닌 패턴 형식)
- [ ] 캐시 무효화 시 일괄 삭제 대상 목록 명시 (코드에서 읽은 실제 값)

## 배치/스케줄러 시퀀스 (섹션 4, 해당하는 경우)

- [ ] 각 단계 실패 시 처리 명시 (log / 알림 / 향후 계획)
- [ ] 단계 독립 try-catch 여부 Note로 명시

## Mermaid 문법

- [ ] 모든 sequenceDiagram에 `autonumber` 있음
- [ ] `-->>` 화살표에 `<br/>` 없음 → 멀티라인은 Note로 분리
- [ ] 중첩 `loop`/`alt`/`else` 2단계 이하
