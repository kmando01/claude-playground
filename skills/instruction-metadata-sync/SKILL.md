---
name: instruction-metadata-sync
description: >
  ec-web24에서 Kotlin Instruction 파일을 추가하거나 수정한 후 backoffice-center-app/constants/instructionMetadata.ts를
  동기화할 때 사용. scripts/scan_instruction.py로 requestInputs(ctx.requestOptions 패턴)와
  possibleErrors(throw BaseException 패턴)를 자동 추출해 TypeScript 스니펫을 생성한다.

  **PROACTIVE — 사용자가 요청하지 않아도 반드시 자동 실행:**
  Claude가 ec-web24/src/.../instruction/impl/ 하위 Kotlin 파일을 Edit/Write로 수정하거나
  EcCode.kt에 새 에러 코드를 추가한 직후, 커밋 전에 이 스킬을 선제적으로 실행해야 한다.
  사용자가 "메타데이터 업데이트해줘"라고 말할 때까지 기다리지 말 것.

  명시적 트리거: "instruction 추가", "instruction 수정", "새 노드 만들었어", "instructionMetadata 업데이트",
  "BE instruction 구현", "메타데이터 동기화", "Kotlin instruction 바꿨어".
---

# Instruction Metadata Sync

ec-web24 Kotlin Instruction 구현과 backoffice-center-app의 `instructionMetadata.ts`가
항상 일치하도록 동기화한다.

## 배경

`InstructionMetadata` 타입에서 `possibleErrors`와 `requestInputs`는 **required 필드**다.
누락 시 `vue-tsc --noEmit` 빌드 에러가 발생한다.
하지만 TypeScript는 "Kotlin 구현이 바뀌었는데 메타데이터를 안 고친 경우"는 잡지 못한다.
그 갭을 이 스킬이 채운다.

## 트리거 조건

### 자동 트리거 (사용자 요청 없이 Claude가 선제 실행)

Claude가 아래 파일을 Edit/Write한 직후 **커밋 전에** 반드시 이 스킬을 실행한다:

- `ec-web24/src/.../instruction/impl/**/*.kt` — 신규 생성 또는 수정
- `ec-common/.../exception/EcCode.kt` — 새 에러 코드 추가

### 명시적 트리거 (사용자가 요청할 때)

- `ec-web24/src/.../instruction/impl/**/*.kt` 파일을 새로 만들었다
- 기존 Kotlin instruction 파일에서 `ctx.requestOptions[...]` 패턴을 추가/변경/삭제했다
- `throw BaseException(EcCode.X, ...)` 패턴을 추가/변경/삭제했다
- `instructionMetadata.ts`에 새 노드를 등록하려 한다

## 워크플로우

### Step 1 — 변경된 Kotlin 파일 확인

```bash
# 수정된 instruction 파일 목록
git diff --name-only HEAD | grep "instruction/impl"
# 또는 사용자가 파일 경로를 직접 알려준 경우 그것을 사용
```

### Step 2 — 스캔 스크립트 실행

스킬 디렉터리의 `scripts/scan_instruction.py`를 사용한다.

```bash
python3 ~/.claude/skills/instruction-metadata-sync/scripts/scan_instruction.py \
  <kotlin_file_path>
```

스크립트가 자동으로:

1. EcCode.kt 파일을 상위 디렉터리에서 탐색
2. `ctx.requestOptions["key"]` 패턴 추출 (required/optional 판단 포함)
3. `throw BaseException(EcCode.X, ...)` 패턴 추출 + errorCode/description 조회
4. `instructionMetadata.ts`에 붙여넣을 TypeScript 스니펫 출력

### Step 3 — instructionMetadata.ts 업데이트

스캔 결과를 바탕으로 `backoffice-center-app/constants/instructionMetadata.ts`를 수정한다.

**새 노드 추가 시** — 두 필드 모두 필수:

```typescript
newInstruction: {
  name: 'NewInstruction',
  requireSlots: [...],
  provideSlots: [...],
  params: [...],
  possibleErrors: [  // ← 스캔 결과 붙여넣기, 없으면 []
    { code: 'ERROR_CODE', errorCode: 1234, description: '설명' },
  ],
  requestInputs: [  // ← 스캔 결과 붙여넣기, 없으면 []
    reqInput('bodyFields', 'key', 'string', true, '설명'),
  ],
},
```

**기존 노드 수정 시** — 해당 필드만 diff 적용:

- requestOptions 키 추가/삭제 → requestInputs 배열 업데이트
- EcCode throw 추가/삭제 → possibleErrors 배열 업데이트

### Step 4 — TODO 항목 처리

스크립트 출력에 `/* TODO */`가 있으면 수동으로 채운다:

- `description`: 한국어로 에러 상황 설명
- required 판단이 불확실한 필드: Kotlin 코드를 직접 확인

### Step 5 — 타입 체크 통과 확인

```bash
cd backoffice-center-app
npx vue-tsc --noEmit 2>&1 | grep -v "Cannot find type\|Entry point\|The file is in"
# 출력 없으면 통과
```

### Step 6 — 동일 PR 커밋

Kotlin 파일 변경과 `instructionMetadata.ts` 변경은 **같은 커밋 또는 같은 PR**에 포함시킨다.
나뉘면 빌드가 깨지거나 메타데이터가 실제 구현과 달라진다.

## 스캔 결과 해석

| 출력 항목               | 의미                           | 대응                      |
| ----------------------- | ------------------------------ | ------------------------- |
| `key: string (필수)`    | `?: throw` 또는 `!!` 패턴 감지 | `required: true`          |
| `key: string (선택)`    | null-safe 처리 감지            | `required: false`         |
| `errorCode: /* TODO */` | EcCode.kt에서 코드 못 찾음     | 수동으로 EcCode enum 확인 |
| `/* TODO: 설명 */`      | 설명 자동 생성 불가            | 한국어로 직접 작성        |

## 주의사항

- `possibleErrors: []`는 "이 노드는 에러가 없다"는 **의도적인 선언**이다.
  감사가 안 된 노드라면 주석으로 표시해도 된다.
- 헬퍼 메서드를 통해 requestOptions를 읽는 경우 스캔이 누락될 수 있다.
  이 경우 Kotlin 파일을 직접 읽어 확인한다.
- `authInfo`에서 오는 필드(게임별 인증 토큰 등)는 requestInputs에 넣지 않는다.
  FE가 직접 보내는 필드만 등록한다.
