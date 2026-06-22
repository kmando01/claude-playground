---
name: context-engineering
description: Context Engineering 원칙에 따라 rules, skills, memory를 생성/검증한다. 새 rule/skill 생성, 기존 rule 리팩토링, episodic memory 기록 시 사용.
---

# Context Engineering Workflow

rules, skills, memory를 생성하거나 수정할 때 이 워크플로우를 따른다.

## 1. Rule 생성/검증 체크리스트

새 rule을 만들거나 기존 rule을 수정할 때:

```
□ 30줄 이내인가?
□ 원칙(MUST/NEVER/SHOULD)만 포함하는가?
□ 코드 템플릿, 예시 코드가 없는가? (있으면 → Skill로 분리)
□ 기존 rule에 통합 가능하지 않은가?
□ 특정 파일 타입 전용이면 globs frontmatter를 추가했는가?
□ CLAUDE.md 라우팅 테이블에 등록했는가?
```

### globs 예시
```yaml
---
globs: ["*.gradle.kts", "settings.gradle.kts"]
---
```
이 rule은 .gradle.kts 파일 작업 시에만 로드된다.

### Rule 작성 패턴
```markdown
# {주제}

## 핵심 원칙
- **MUST**: ~하라
- **NEVER**: ~하지 마라
- **SHOULD**: ~하는 것이 좋다

## 상세 가이드
상세 템플릿/예시는 `{skill-name}` 스킬을 참조하라.
```

## 2. Skill 생성 체크리스트

새 skill을 만들 때:

```
□ YAML frontmatter에 name + description이 있는가?
□ description이 검색 가능할 만큼 구체적인가?
□ 자기 완결적인가? (이 skill만으로 작업 완료 가능)
□ 코드 예시, 템플릿이 충분한가?
□ CLAUDE.md 라우팅 테이블에 등록했는가?
□ 이미 유사한 skill이 존재하지 않는가?
```

### Skill 디렉토리 구조
```
.claude/skills/{skill-name}/
└── SKILL.md
```

### Skill 작성 패턴
```markdown
---
name: {skill-name}
description: {검색 가능한 구체적 설명}
---

# {제목}

## 개요
{이 skill이 언제, 왜 필요한지}

## 템플릿/패턴
{코드 예시, 설정 템플릿, 상세 가이드}

## 체크리스트
{완료 전 확인사항}
```

## 3. Rule → Skill 분리 가이드

기존 rule이 30줄을 초과하면:

### Step 1: 원칙 추출
rule에서 MUST/NEVER/SHOULD 문장만 추출한다.
```
원본: "새로운 인프라 추가 시 Docker + docker-compose를 기본으로 사용한다."
     + docker-compose.yml 전체 템플릿 (50줄)
     + healthcheck 설정 예시 (20줄)

분리 후:
  Rule: "MUST: 새 인프라는 Docker + docker-compose 사용. 직접 설치 금지."
  Skill: docker-compose 템플릿, healthcheck 예시, 이미지 목록 전부
```

### Step 2: Reference Skill 생성
추출한 레퍼런스를 skill로 만든다. 이름은 `{rule-name}-reference`.

### Step 3: Rule에 참조 추가
```markdown
## 상세 가이드
코드 템플릿, 설정 예시는 `{skill-name}` 스킬을 참조하라.
```

### Step 4: 검증
- rule이 30줄 이내인지 확인
- skill에 모든 레퍼런스가 보존됐는지 확인
- 정보 손실이 없는지 확인

## 4. Episodic Memory 기록 가이드

### decisions.jsonl — 결정 기록
주요 기술 결정, 설계 선택 시 기록한다.

```jsonl
{"schema":"v1","fields":["date","topic","decision","alternatives","reasoning","outcome"]}
{"date":"2025-01-15","topic":"메시지 큐 선택","decision":"Kafka","alternatives":["RabbitMQ","Redis Streams"],"reasoning":"피크 5000 TPS, 순서 보장 필요, 재처리 요구사항","outcome":"채택 - ADR-001"}
```

기록 시점:
- 기술 스택 선택
- 아키텍처 패턴 결정
- 트레이드오프가 있는 선택
- ADR 작성 시

### failures.jsonl — 실패 기록
실패, 버그, 재작업 발생 시 기록한다.

```jsonl
{"schema":"v1","fields":["date","what","root_cause","prevention","severity"]}
{"date":"2025-01-20","what":"CLAUDE.md에 모든 규칙 집중으로 응답 품질 저하","root_cause":"context window에서 2400줄이 attention 경쟁","prevention":"rules는 원칙만, 레퍼런스는 skill로 분리","severity":"high"}
```

기록 시점:
- 빌드/테스트 실패 후 원인 파악 완료
- 설계 재작업 발생
- 성능 이슈 해결 후
- 동일 실수 반복 시

### 기록 규칙
- **append-only**: 기존 줄 수정/삭제 금지 (JSONL 특성)
- **첫 줄은 스키마**: 에이전트가 구조를 즉시 파악
- **간결하게**: 한 줄에 한 기록, 필수 필드만

## 5. 헬스체크 — 기존 Setup 검증

기존 rule/skill 전체를 점검할 때:

```
□ rules/ 전체 줄 수 < 500줄?
□ 30줄 초과 rule이 없는가?
□ rule에 코드 템플릿이 포함되어 있지 않은가?
□ 모든 rule/skill이 CLAUDE.md 라우팅 테이블에 등록되어 있는가?
□ MEMORY.md가 200줄 이내인가?
□ decisions.jsonl, failures.jsonl에 최근 기록이 있는가?
□ 사용하지 않는 rule/skill이 있는가?
```

실행:
```bash
# rules 전체 줄 수 확인
wc -l .claude/rules/*.md | tail -1

# 30줄 초과 rule 찾기
for f in .claude/rules/*.md; do
  lines=$(wc -l < "$f")
  [ "$lines" -gt 30 ] && echo "WARN: $f ($lines lines)"
done

# MEMORY.md 줄 수 확인
wc -l memory/MEMORY.md
```