---
name: sequence-diagram
description: >
  코드베이스를 분석해 Mermaid 시퀀스 다이어그램을 생성·업데이트한다.
  시스템 아키텍처, 주요 흐름(쓰기/읽기/비동기/에러), 배치/스케줄러 흐름을 포함한다.
  Use when user says "시퀀스 다이어그램", "sequence diagram", "다이어그램 그려줘",
  "다이어그램 작성", "/sequence-diagram", "docs/sequence-diagram.md 업데이트",
  or after major feature branch merges that change data flow.
---

# 시퀀스 다이어그램 생성 스킬

## Step 1: 변경 범위 파악

```bash
git branch --show-current
git log main..HEAD --oneline
git diff main...HEAD --name-only
```

변경된 파일을 보고 **어떤 다이어그램이 영향받는지** 판단한다.

| 변경 위치 | 영향받는 다이어그램 |
|---------|----------------|
| Controller / UseCase / Service | 쓰기 시퀀스, 읽기 시퀀스 |
| 메시지 큐 Config / Consumer | 비동기 발행·소비 시퀀스 |
| Cache / Repository | 조회 시퀀스 |
| Batch / Scheduler | 배치 시퀀스 |
| docker-compose / infra | 전체 아키텍처 |

## Step 2: 코드 탐색

영향받는 다이어그램에 필요한 파일을 읽는다.

**항상 확인**
- 엔트리포인트(Controller / Consumer / Scheduler) — 흐름 시작점
- 핵심 설정 파일(application.yml) — 타임아웃, 재시도, CB 설정값
- 인프라 Config — 에러 핸들러, 백오프, notRetryableExceptions

**추가로 확인 (흐름별)**
- 쓰기: UseCase / Service → Repository → 이벤트 발행 경로
- 읽기: Cache 전략(조건, 키 패턴, evict) → Repository
- 비동기: 메시지 포맷, 재시도 레이어, DLQ 처리
- 배치: cron 표현식, 각 단계 try-catch 독립성, 실패 시 알림 경로

## Step 3: 다이어그램 작성

`docs/sequence-diagram.md`에 작성한다.

**섹션 구성 (프로젝트에 해당하는 섹션만 포함)**

```
## 0. 클래스 다이어그램        (classDiagram — 새 도메인/아키텍처 변경 시만)
## 1. 전체 시스템 아키텍처     (graph TD — 모듈·컴포넌트 관계)
## 2. 쓰기 흐름               (sequenceDiagram — 주요 쓰기 경로)
## 2-1. 에러/재시도 상세       (재시도 레이어 순서 명시)
## 3. 읽기 흐름               (캐시 전략 포함)
## 4. 배치/스케줄러 흐름       (주기적 작업)
```

**클래스 다이어그램 생성 기준** (§0):
- 새 도메인 추가, 모듈 구조 변경, Port/Adapter 추가 시
- 4가지 관점 포함: ① 헥사고날 레이어 ② 도메인 모델 + 상태 전이 ③ Port & Adapter ④ 비동기 처리 흐름
- 기존 `docs/class-diagram.md` 또는 Wiki `클래스-다이어그램` 페이지에 저장

작성 규칙은 `references/diagram-rules.md` 참조.

## Step 4: 자가 검증

작성 후 `references/quality-checklist.md`의 체크리스트를 순서대로 확인한다.
모든 항목 통과 후 완료 선언한다.

## 관련 스킬

| 스킬 | 용도 |
|------|------|
| `write-strategy-doc` | 설계 결정 문서화 |
| `adr-review` | 다이어그램과 실제 코드 정합성 검증 |
| `kafka-patterns` | Kafka 설정값 판단 기준 |
| `spring-cache` | Redis 캐시 패턴 참조 |
