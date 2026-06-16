# Runbook 검증 체크리스트

## A. 필수 파일 커밋 여부

```bash
# 전체 untracked 확인
git status --short

# git에 추적되는 파일 목록
git ls-files
```

| 항목 | 확인 방법 | 실패 시 영향 |
|------|-----------|-------------|
| `gradlew` / `gradlew.bat` | `git ls-files gradlew` | `./gradlew` 첫 명령 즉시 실패 |
| `gradle/wrapper/gradle-wrapper.jar` | `git ls-files gradle/` | Wrapper 실행 불가 |
| `docker-compose.yml` | `git ls-files docker-compose.yml` | 인프라 기동 불가 |
| docker-compose volume 대상 경로 | 아래 B 참조 | `docker compose up` 실패 |
| 앱 설정 파일 (`application.yml` 등) | `git ls-files src/` | 앱 기동 실패 |
| `docs/` 하위 전체 | `git ls-files docs/` | README 링크 404, 문서 소실 |

## B. docker-compose.yml volume 마운트 검증

```bash
# volume 마운트 경로 추출
grep -A1 "volumes:" docker-compose.yml | grep "\./monitoring"

# 해당 경로가 git에 있는지 확인
git ls-files monitoring/
```

모든 `./경로:` 형태의 호스트 마운트가 `git ls-files`에 존재해야 한다.

## C. README 명령어 → 파일 존재 검증

README의 실행 섹션에서 아래를 순서대로 추출하고 검증:

1. **사전 요구사항** — 도구 버전(JDK, Docker) 명시됐는가?
2. **`./` 로 시작하는 스크립트** — `git ls-files`에 존재하는가? 실행 권한(`chmod +x`)이 있는가?
3. **`docker compose`** — `docker-compose.yml` 커밋됐는가? volumes 대상 모두 존재하는가?
4. **포트 번호** — 실제 `application.yml`의 `server.port`와 일치하는가?
5. **curl 예시** — 엔드포인트가 실제 Controller에 존재하는가?
6. **문서 링크** (`[링크](경로)`) — `git ls-files 경로`로 존재 확인

## D. 환경변수 / 시크릿

```bash
# application.yml에서 ${} 패턴 추출
grep -rn "\${" src/main/resources/
```

- 기본값 없는 `${VAR}` 는 README에 설정법 안내 필수
- `.env.example` 또는 README에 필요한 환경변수 목록 있어야 함

## E. Fresh Clone 시뮬레이션 (최종 관문 — 생략 불가)

```bash
# 1) 실제 clone
rm -rf /tmp/verify-clone
git clone <repo-url> /tmp/verify-clone

# 2) 인프라 기동
# 로컬에 동일 컨테이너가 이미 실행 중이면 이름 충돌 → 기존 컨테이너 활용해도 무방
cd /tmp/verify-clone && docker compose up -d

# 3) 앱 기동 (포트 충돌 시 --server.port=XXXX 로 우회)
./gradlew :<module>:bootRun > /tmp/app.log 2>&1 &
until grep -q "Started\|ERROR\|FAILED" /tmp/app.log; do sleep 3; done
tail -5 /tmp/app.log   # "Started ... in X seconds" 확인

# 4) curl로 실제 응답 확인 (존재 확인이 아니라 응답 확인)
curl -s http://localhost:<port>/api/... | python3 -m json.tool
```

**포트 충돌 처리:**
- 로컬에 이미 앱이 실행 중이면 `--args='--server.port=8090'` 으로 우회
- 컨테이너 이름 충돌은 이미 실행 중인 인프라를 그대로 활용하면 됨

**통과 기준:** curl 응답이 README 예시와 일치하면 완료. 존재 확인(git ls-files)만으로 E를 통과 처리하지 않는다.
