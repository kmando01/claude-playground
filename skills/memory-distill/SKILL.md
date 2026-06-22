---
name: memory-distill
description: >
  memory/failures.jsonl, memory/decisions.jsonl를 읽고 아직 스킬/룰에 반영되지 않은
  교훈을 찾아 해당 스킬에 직접 반영한다. 에피소드 기억을 영구 지식으로 승격한다.
  Use when user says "memory 반영", "distill", "교훈 반영", "/memory-distill",
  or periodically after accumulating several failures/decisions.
---

# Memory → Skill 증류

에피소드 기억(실패/결정)을 영구 지식(스킬/룰)으로 승격한다.

```
memory/failures.jsonl     (에피소드)
memory/decisions.jsonl    (에피소드)
        ↓ 증류
skills/*                  (영구 지식)
rules/*                   (영구 규칙)
```

## Step 1: Memory 읽기

두 파일을 읽고 각 항목을 파싱한다.

```bash
cat .claude/memory/failures.jsonl
cat .claude/memory/decisions.jsonl
```

각 항목에서 추출:
- `prevention` / `lesson` / `rule` 필드 — 스킬에 반영할 내용
- `ref` 필드 — 관련 스킬/컴포넌트
- `promoted` 필드 — 이미 반영됐으면 `true` (건너뜀)

## Step 2: 미반영 항목 식별

`promoted: true`가 없는 항목만 처리한다.

각 항목에 대해:
1. **어느 스킬/룰에 반영할지** 판단
   - `component`, `category`, `ref` 필드 기준으로 매핑
   - 예: `resilience4j` → `spring-rest-client` 스킬
   - 예: `Debezium CDC` → `transactional-outbox` 스킬
   - 해당 스킬이 없으면 → 새 스킬 생성 또는 `rules/` 반영 판단
2. **현재 스킬에 이미 반영됐는지** 확인
   - 해당 스킬 파일을 읽고, prevention 내용이 MUST/NEVER 규칙이나 주의사항으로 존재하는지 확인
   - 이미 있으면 `promoted: true`로 마크만 하고 넘어감

## Step 3: 스킬/룰에 반영

미반영 항목별로 실제 파일을 수정한다.

**반영 원칙**:
- `prevention` → 해당 스킬의 관련 섹션에 **MUST/NEVER 규칙** 또는 **⚠️ 주의** 블록으로 추가
- 코드 예시가 있으면 포함
- `ref`(공식 문서 링크)가 있으면 함께 추가
- 기존 내용을 지우지 않고 **추가**만 한다

**반영 위치 판단**:
| 내용 유형 | 반영 위치 |
|----------|----------|
| 특정 기술 설정 실수 | 해당 기술 reference 스킬 |
| 아키텍처 결정 원칙 | `rules/` 또는 design 스킬 |
| 인프라 운영 주의사항 | `docker-reference` 또는 해당 인프라 스킬 |
| 테스트 전략 교훈 | `testing-reference` 스킬 |
| 성능 관련 교훈 | `perf-test-reference` 또는 `resilience-patterns` |

## Step 4: promoted 마크

반영이 완료된 항목의 jsonl 파일에서 해당 라인에 `"promoted": true` 추가.

```bash
# 원본 라인 예시:
{"date":"2026-03-11","category":"resilience4j",...}

# 마크 후:
{"date":"2026-03-11","category":"resilience4j",...,"promoted":true}
```

jsonl은 append-only이므로 **해당 라인을 직접 수정**한다 (sed 또는 파일 재작성).

## Step 5: 요약 보고

처리 결과를 보고한다.

```
## Memory Distill 결과

### 반영 완료 (N건)
- [날짜] [category] → [스킬명] [섹션명]에 추가
- ...

### 이미 반영됨 (N건)
- [날짜] [category] — 스킬에 동일 내용 존재, promoted 마크만

### 스킬 없음 — 수동 확인 필요 (N건)
- [날짜] [category] — 적합한 스킬 없음. 새 스킬 생성 또는 rule 추가 검토 필요
```

## decisions.jsonl 작성 기준

`failures.jsonl`은 실패 후 사후 기록이지만, `decisions.jsonl`은 **결정 시점에** 기록한다.

**언제 써야 하는가** (이 중 하나라도 해당하면):
- `/design` 또는 ADR 작성 후 — 핵심 설계 결정
- 기술 스택 선택 시 — 왜 A를 골랐고 B는 왜 버렸는가
- 트레이드오프가 있는 구현 방식 선택 시
- 성능 설정값 결정 시 (CB threshold, pool size 등) — 숫자의 근거

**형식**:
```json
{"date":"YYYY-MM-DD","category":"설계|성능|기술스택","decision":"무엇을 결정했는가","rationale":"왜 이 결정인가","alternatives":"어떤 대안을 기각했는가","ref":"관련 ADR 또는 문서"}
```

**주의**: decisions.jsonl 항목은 promoted 마크 불필요 — 결정 자체가 영구 기록.

## 실행 주기

- **브랜치 완료 후** (`/compound` 실행 시점과 동일)
- **failures.jsonl에 3건 이상 쌓였을 때**
- **새 프로젝트에 toolkit을 적용하기 전** (toolkit 정리 시점)
