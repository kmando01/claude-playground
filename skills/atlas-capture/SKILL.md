---
name: atlas-capture
description: >
  MongoDB Atlas 메트릭 차트를 Playwright로 element-level 크롭 캡쳐하고,
  Confluence 페이지에 증거 기반으로 문서화하는 스킬.

  **반드시 이 스킬을 사용해야 하는 상황:**
  - "Atlas 캡쳐해줘", "MongoDB 메트릭 문서화", "차트 캡쳐해서 Confluence에 써줘"
  - MongoDB 성능 이슈 / 장애 분석 결과를 Confluence에 남겨야 할 때
  - "이거 캡쳐 기반으로 설명해줘" + Atlas URL이 있을 때
  - 특정 Atlas 차트(Query Executor, Opcounters, Replication Lag 등)를 증거로 첨부해야 할 때

  핵심 원칙: **캡쳐 먼저, 캡쳐 기반으로 이야기한다.**
  주장만 하고 캡쳐가 없으면 증거가 없는 것이다.
---

## 핵심 원칙

캡쳐 없이 분석하지 않는다. 모든 주장은 캡쳐된 차트로 뒷받침해야 한다.
"Secondary QE가 oplog replication이다" → Opcounters-Repl 차트로 직접 증명.

---

## Step 0: 입력 확인

사용자로부터 확인할 것:
- **Atlas URL**: 캡쳐할 메트릭 페이지 URL
- **캡쳐할 차트 목록**: 차트 이름 (예: "Query Executor", "Opcounters - Repl")
- **Confluence 페이지 ID**: URL에서 추출 (예: `.../pages/1130049891/...` → `1130049891`)
- **작성할 내용**: 어떤 분석을 문서화할 것인지

---

## Step 1: Atlas 페이지 접속

```js
// Playwright로 Atlas 접속
browser_navigate(url)
```

Atlas는 SPA이므로 스크롤 컨테이너가 `<main>` 태그 안에 있다.
`window.scrollBy`는 동작하지 않으므로 반드시 `main.scrollTop`으로 스크롤.

```js
// 올바른 스크롤 방법
() => {
  const main = document.querySelector('main');
  main.scrollTop = 800;
  return main.scrollTop;
}
```

---

## Step 2: 차트 찾기 및 활성화

### 2-1. 차트 위치 찾기

```js
// 차트 H4 헤딩을 기준으로 절대 위치 계산
() => {
  const headers = document.querySelectorAll('h4');
  for (const h of headers) {
    if (h.textContent.trim() === '차트이름') {
      const main = document.querySelector('main');
      const rect = h.getBoundingClientRect();
      const absTop = main.scrollTop + rect.top;
      main.scrollTop = absTop - 100;
      return { found: true, absTop };
    }
  }
  return { found: false };
}
```

### 2-2. 비활성 차트 활성화

차트 목록 페이지(맨 아래)에서 "+" 버튼으로 표시된 차트는 현재 비활성.
활성화하려면 버튼 클릭 후 다시 차트 위치를 찾아 스크롤.

```js
// 비활성 차트 활성화
browser_click('button:has-text("+차트이름")')
```

활성화 확인: 버튼이 `"-차트이름"`으로 바뀌면 성공.

---

## Step 3: Element-level 크롭 캡쳐

전체 페이지 스크린샷 대신 반드시 **차트 컨테이너만** 크롭해서 찍는다.
다른 차트(Disk IOPS 등)가 섞이면 무슨 차트인지 모르게 된다.

```js
// 차트 컨테이너만 element screenshot
browser_take_screenshot(
  target: 'div.charts-row-outer-container:has-text("차트이름 Chart")',
  filename: 'chart-name.png'
)
```

**캡쳐 후 반드시 Read로 확인** — 원하는 차트만 찍혔는지 검증.

캡쳐 확인 기준:
- ✅ 차트 타이틀이 이미지 상단에 보임
- ✅ 다른 차트 섹션이 섞이지 않음  
- ✅ 3개 노드(shard-00-00, 01, 02)가 모두 보임

---

## Step 4: Confluence 첨부파일 업로드

캡쳐한 파일을 모두 Confluence 페이지에 업로드.

```
confluence_upload_attachment(
  content_id: "페이지ID",
  file_path: "/절대경로/chart-name.png",
  comment: "차트 설명"
)
```

여러 장이면 병렬로 업로드한다.

---

## Step 5: 캡쳐 기반 분석 작성 및 페이지 업데이트

**작성 원칙:**
- 주장 → 캡쳐 → 해석 순서로 작성
- "이렇다" 라고 주장만 하면 안 되고, 무엇을 보면 그걸 알 수 있는지 차트로 보여줘야 함
- 캡쳐에 없는 것은 주장하지 않는다

**증거 체인 구조 (권장):**

```markdown
## [주장]

![chart-name.png](chart-name.png)

[차트에서 읽히는 수치/패턴 설명]

**이것이 [주장]의 근거인 이유:**
- [차트의 어떤 부분이 무엇을 의미하는지]
- [반대 케이스라면 어떻게 보였을지 — 대조]
```

**대조를 활용한 증명 (강력):**
"앱 트래픽이 secondary로 가고 있다면 Primary처럼 불규칙한 스파이크가 생겨야 한다.
그런데 Secondary는 평탄 → 앱 트래픽이 없음을 증명"

```
confluence_update_page(
  page_id: "페이지ID",
  title: "페이지 제목",
  content: "마크다운 내용",
  content_format: "markdown",
  version_comment: "분석 추가"
)
```

---

## 자주 쓰는 Atlas 차트 이름 & 의미

| 차트 이름 | 측정 내용 | 주목할 점 |
|-----------|----------|-----------|
| `Opcounters` | 초당 read/write/command 수 | Primary vs Secondary 트래픽 비교 |
| `Opcounters - Repl` | oplog로 적용된 replication 연산 수 | Secondary에만 있어야 정상. Primary=0이면 oplog 증거 |
| `Query Executor` | 초당 index scan / document scan 수 | Secondary flat = oplog apply, spiky = 앱 쿼리 |
| `Replication Lag` | Secondary가 Primary를 얼마나 뒤따르는지 | 0이면 실시간 복제 중 |
| `Connections` | 노드별 커넥션 수 | Primary 집중이면 secondary 라우팅 없음 |
| `Page Faults` | 디스크 I/O 발생 횟수 | 캐시 미스 = working set > RAM |

---

## 주의사항

- **SPA 스크롤**: `window.scrollBy` 안 됨 → `main.scrollTop` 사용
- **차트 로딩 대기**: 활성화 후 차트가 렌더링될 때까지 잠깐 기다릴 수 있음
- **element screenshot 실패 시**: `has-text` 셀렉터가 여러 요소에 매칭되면 더 구체적인 텍스트로 좁혀야 함 (예: `"Query Executor Chart Permalink"`)
- **버전 관리**: confluence_update_page는 현재 버전에서 +1 자동 처리됨
