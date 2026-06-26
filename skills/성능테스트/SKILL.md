---
name: 성능테스트
description: "K8s 환경에서 Locust 기반 성능 테스트를 자동으로 수행하는 오케스트레이터. 스크립트 생성 → ConfigMap/Helm 배포 → 단계별 부하 테스트 → JVM 심층 분석(GC/heap/thread dump) → 병목/누수 탐지 → Datadog 지표 캡처 → 문서 작성까지 전 과정을 자동화. 쿠폰 템플릿 성능 테스트 경험(2607-COUPON/ASTROARENA) 기반으로 제작. 트리거: '/성능테스트', '성능테스트 해줘', '부하 테스트', 'locust 돌려줘', '병목 찾아줘'"
---

# K8s 성능 테스트 오케스트레이터

> Locust K8s Helm 배포 + 단계별 부하 + JVM 심층 분석 + 병목/누수 탐지 + 문서화

---

## 가드레일

**반드시 아래 환경에서만 실행. 아래 외 값이면 즉시 거부.**

| 항목          | 허용 값                                                              |
| ------------- | -------------------------------------------------------------------- |
| 클러스터      | `arn:aws:eks:ap-northeast-2:220852994885:cluster/eks-boc-2212-stage` |
| 네임스페이스  | `ec-dev`, `ec-qa`                                                    |
| host URL 차단 | `staging`, `stage`, `live`, `prod`                                   |

---

## 입력 파싱

`/성능테스트 {eventKey} {gameKey} {host}` 형식 또는 대화에서 추출.

| 파라미터  | 예시                                       | 설명                        |
| --------- | ------------------------------------------ | --------------------------- |
| eventKey  | `2607-COUPON`                              | 이벤트 키                   |
| gameKey   | `ASTROARENA`                               | 게임 키 (auth handler 결정) |
| host      | `http://ec-web24.ec-dev.svc.cluster.local` | 내부 서비스 URL             |
| namespace | `ec-dev` (기본)                            | K8s 네임스페이스            |
| workers   | `30` (기본)                                | Locust worker pod 수        |

---

## Step 0: 사전 확인

```bash
# 1. kubectl context 확인
kubectl config current-context

# 2. kec-external-mock 배포 상태
kubectl get pods -n ec-dev -l back=kec-external-mock

# 3. 테스트 대상 pod 상태
kubectl get pods -n ec-dev -l back={service-name}

# 4. WireMock health
curl -s http://localhost:8080/__admin/health
```

**체크리스트:**

- [ ] kec-external-mock 2/2 Running (WireMock + Toxiproxy 또는 WireMock only)
- [ ] 대상 서비스 pod Running
- [ ] Spring Profile: `dev,perf` (GPP mock 사용 시)
- [ ] WireMock 올바른 매핑 등록 확인

---

## Step 1: 게임별 인증 구조 파악

게임 키로 어떤 auth handler를 사용하는지 확인:

- `aod` → AodAuthHandler (KOS 인증)
- `h5` → H5AuthHandler (Tencent tcOpenId)
- 그 외 → KidAuthHandler (KID 인증, `gamelinks` 구조)

쿠폰 템플릿 기준 AUTH_MODE:

- `uid`: body에 `userId` 포함, `kraftonAccount` 헤더 불필요
- `kid`: `kraftonAccount` 헤더에 `gameAccounts[].gameName` = KOS namespace 값

---

## Step 2: Locust 스크립트 생성

`kec-perftest-platform/performance/{eventKey}_locust.py` 생성.

**핵심 규칙:**

- `SequentialTaskSet` 사용 (순서 보장)
- `on_start`에서 `GET /init` 호출 → 서버 목록 수집
- 메인 task: `POST /{path}` (쿠폰 리딤 등)
- `catch_response=True` + 성공/실패 판정 코드 명시
- `wait_time = between(0.5, 2)`
- AUTH_MODE 환경변수로 `uid`/`kid`/`random` 선택

**쿠폰 템플릿 헤더 구조 (KID 모드):**

```python
base["kraftonAccount"] = json.dumps({
    "globalAccountId": global_id,
    "globalNickname": nickname,
    "gameAccounts": [{
        "accountId": account_id,
        "nickname": nickname,
        "gameName": "uropa",     # KOS namespace (게임별 다름)
        "platform": "NA",
        "gppUserId": gpp_user_id,
    }],
})
```

**주의:**

- GPP mock 사용 시 쿠폰 코드 사전 시드 불필요 (mock이 어떤 코드든 200 반환)
- `gameAccounts[].gameName`은 DB의 `game.getKosNamespace()` 값과 일치해야 함

---

## Step 3: ConfigMap + Helm 배포

```bash
# ConfigMap 생성
kubectl create configmap {eventKey}-locust-script \
  --from-file={eventKey}_locust.py \
  -n ec-dev

# Helm 배포
helm install {eventKey}-locust deliveryhero/locust \
  --set loadtest.name={eventKey}-locust \
  --set loadtest.locust_locustfile_configmap={eventKey}-locust-script \
  --set loadtest.locust_locustfile={eventKey}_locust.py \
  --set loadtest.locust_host={host} \
  --set worker.replicas=30 \
  --set image.repository=220852994885.dkr.ecr.ap-northeast-2.amazonaws.com/locust \
  --set image.tag=2.43.3 \
  --set master.resources.requests.memory=4Gi \
  --set master.resources.limits.memory=5Gi \
  --set worker.resources.requests.memory=512Mi \
  --set worker.resources.limits.memory=1Gi \
  -n ec-dev

# 릴리즈 이름은 숫자로 시작하면 안 됨 (DNS-1035 규칙)
# 예: 2607-coupon-locust → coupon-2607-locust

# 포트포워딩
kubectl port-forward svc/coupon-2607-locust 8089:8089 -n ec-dev &
```

---

## Step 4: 단계별 부하 테스트

Locust REST API로 자동 제어:

```bash
# 시작
curl -X POST http://localhost:8089/swarm \
  -d "user_count=100&spawn_rate=10&host={host}"

# 통계 확인
curl -s http://localhost:8089/stats/requests | python3 -c "..."

# 정지 / 리셋
curl -X GET http://localhost:8089/stop
curl -X GET http://localhost:8089/stats/reset
```

| 단계 | users | spawn_rate | 목적           |
| ---- | ----- | ---------- | -------------- |
| 1    | 100   | 10/s       | 기본 동작 확인 |
| 2    | 300   | 30/s       | 안정성 확인    |
| 3    | 500   | 50/s       | 중간 부하      |
| 4    | 1,000 | 100/s      | 고부하         |
| 5    | 2,000 | 200/s      | 피크           |

**각 단계에서 수집:**

- RPS, p50, p95, p99, fail rate
- 에러 타입 분석

---

## Step 5: JVM 지표 수집 (Actuator 포트포워딩)

```bash
kubectl port-forward pod/{pod-name} 9090:8080 -n ec-dev &
```

**수집 지표:**

```bash
# GC
curl http://localhost:9090/_/metrics/jvm.gc.pause
curl http://localhost:9090/_/metrics/jvm.gc.overhead
curl http://localhost:9090/_/metrics/jvm.gc.memory.allocated
curl http://localhost:9090/_/metrics/jvm.gc.live.data.size
curl http://localhost:9090/_/metrics/jvm.gc.memory.promoted

# 메모리
curl http://localhost:9090/_/metrics/jvm.memory.used
curl http://localhost:9090/_/metrics/jvm.buffer.memory.used
curl http://localhost:9090/_/metrics/jvm.classes.loaded

# 스레드
curl http://localhost:9090/_/metrics/jvm.threads.live
curl http://localhost:9090/_/metrics/jvm.threads.started
curl http://localhost:9090/_/metrics/http.server.requests.active
```

---

## Step 6: JVM 심층 분석 — jcmd

```bash
# Heap histogram (top 20 — 할당 주범 파악)
kubectl exec -n ec-dev {pod} -c {container} -- jcmd 1 GC.class_histogram 2>/dev/null | head -25

# GC 상세 (GCLocker, Humongous 등 cause 확인)
kubectl exec -n ec-dev {pod} -- jcmd 1 GC.heap_info

# Thread dump (BLOCKED/WAITING 분석)
kubectl exec -n ec-dev {pod} -- jcmd 1 Thread.print | python3 -c "..."

# Code cache 포화 여부
kubectl exec -n ec-dev {pod} -- jcmd 1 Compiler.codecache

# File Descriptor 누수
kubectl exec -n ec-dev {pod} -- sh -c "ls /proc/1/fd | wc -l"
```

**주의:** `jcmd GC.class_histogram`은 Heap Inspection GC를 유발하므로 측정값 왜곡 주의 (210ms STW 발생 가능)

---

## Step 7: 누수 탐지 — T0 → T+5min 비교

아래 지표를 T0에 기록하고 5분 후 재측정:

| 지표                                           | 누수 판정 기준                |
| ---------------------------------------------- | ----------------------------- |
| OldGen live (`jvm.gc.live.data.size`)          | 선형 증가 → 메모리 누수       |
| 스레드 수 (`jvm.threads.live`)                 | 지속 증가 → 스레드 누수       |
| Direct buffer (`jvm.buffer.memory.used`)       | 지속 증가 → Netty buffer 누수 |
| Metaspace                                      | 지속 증가 → classloader 누수  |
| MongoDB cursor (`CursorResourceManager$State`) | 계속 증가 → cursor 누수       |
| FD 수 (`/proc/1/fd`)                           | 계속 증가 → socket 누수       |

**GC cause 태그 확인:**

- `G1 Humongous Allocation` → 512KB+ 단일 객체 존재 (Event BSON 주의)
- `GCLocker Initiated GC` → JNI 기반 (MongoDB/Netty)
- `Heap Inspection Initiated GC` → jcmd histogram 명령 유발

---

## Step 8: 병목 분석 패턴

**Socket I/O 지배적일 때 (프로파일러):**

- MongoDB 쿼리 full scan → 인덱스 확인
- Event/Game 캐시 미적용 → 요청당 반복 조회
- `parsePathConfig` 이중 JSON 파싱 → 요청 내 중복 제거

**GC pressure 높을 때:**

- `[B` (byte array) 대용량 → BSON read buffer (Event 도큐먼트 크기 확인)
- `[C` (char array) 누적 → JSON string 변환 (ObjectMapper.readValue 남용)
- Humongous allocation → MongoDB projection으로 도큐먼트 크기 축소

**OkHttp SocketTimeout (고부하):**

- `maxRequestsPerHost=5` (기본값) → GPP 동시 호출 많을 때 큐 대기 → 타임아웃
- fix: `Dispatcher().apply { maxRequests=512; maxRequestsPerHost=512 }`

**MongoDB transaction overhead:**

- `MongoTransactionManager` 기본 WriteConcern = MAJORITY → commit당 ~20ms
- 2 write TX per request → ~40ms 추가 latency

**LockService @Transactional 주의:**

- Redis 작업에 MongoDB TX 적용 → 불필요한 MongoDB session 생성
- fix: `@Transactional` 제거 또는 `propagation = NEVER`

---

## Step 9: Datadog 대시보드 분석

브라우저로 접속:

```
https://krafton-webservice.datadoghq.com/dashboard/ksz-5tj-98z/ec-web24-service-dashboard
```

**확인할 위젯:**

- Throughput / Error Rate / P95 Latency
- Heap Memory / GC Pause by Cause / Thread Count
- GC Allocation Rate / Old Gen / Eden Size
- Socket I/O (Profiler)

**Continuous Profiler:**

```
https://krafton-webservice.datadoghq.com/profiling/explorer?query=env:ec-dev+service:ec-web24
```

- Wall Time vs CPU Time 비율 → I/O 대기 vs CPU 부하 구분
- Socket I/O Read Time → MongoDB 병목 지표

---

## Step 10: 정리 + 보고서

**Helm 삭제:**

```bash
helm uninstall coupon-2607-locust -n ec-dev
kubectl delete configmap {eventKey}-locust-script -n ec-dev
```

**문서 작성 위치:** `.ai/plan/{eventKey}-perf-stage-results.md`

**포함 내용:**

- 단계별 RPS/p50/p95/p99/fail 표
- JVM 지표 비교표 (Stage별)
- 누수 분석 결과 (T0 → T+5min)
- 이상 지점 목록 (근거 지표 + 코드 위치 + fix 방향)
- 병목 지점 (원인 + 예상 개선 효과)
- 미해결 이슈

---

## 알려진 함정

| 함정                                              | 설명                                                                             | 대처                                                                            |
| ------------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| WireMock 런타임 매핑 소실                         | pod 재시작 시 `__admin/mappings` 사라짐                                          | 새 이미지에 bake-in 필수 (`develop_e5ad9e2` 이후 해결)                          |
| WireMock 경로 `/internal` vs `/platform/internal` | GPP SDK 실제 경로는 `/platform/internal/namespaces/.../coupon/code`              | WireMock 매핑에 `/platform/` prefix 반드시 포함                                 |
| Toxiproxy 불안정                                  | 500+ users 부하에서 Toxiproxy 크래시 (Exit 137)                                  | 용량 테스트 시 `toxiproxy.enabled=false`                                        |
| kec-external-mock liveness probe                  | 고부하 시 `/__admin/health` 응답 지연 → probe 실패 → pod 재시작                  | `probe.timeoutSeconds=30, periodSeconds=60, failureThreshold=5`                 |
| kec-external-mock Jetty thread                    | 500+ users 동시 요청 → Jetty thread pool 소진 → health check 실패                | `develop_e5ad9e2` (--container-threads 200) + replicaCount=3                    |
| Locust 릴리즈 이름 숫자 시작                      | `2607-coupon-locust` → DNS-1035 오류                                             | `coupon-2607-locust`처럼 알파벳 시작                                            |
| jcmd histogram → GC 유발                          | `GC.class_histogram` 실행 시 Heap Inspection GC 발생 → GC MAX 왜곡 (~170ms)      | 측정 전후 GC MAX 변화 별도 기록, 실제 앱 동작 아님                              |
| JAVA_TOOL_OPTIONS vs SPRING_PROFILES_ACTIVE       | JVM property가 env var보다 우선순위 높음 → perf profile 미활성화                 | `JAVA_TOOL_OPTIONS`에 `-Dspring.profiles.active=dev,perf` 직접 명시             |
| AuthMode KID — gameAccounts.gameName              | KOS namespace 값과 일치해야 함 (예: "uropa")                                     | DB `game.getKosNamespace()` 확인 필수, `accounts` 아닌 `gameAccounts` 필드 사용 |
| OkHttp maxRequestsPerHost=5                       | 1000+ users 동시 GPP 호출 시 SocketTimeoutException                              | `okhttp3` dependency + Dispatcher(512, 512) 설정 (Stage 4+ 필요)                |
| DataPipeline auth 토큰 캐시 비활성                | `@EnableCaching`이 `@Profile("aod")`에만 있음 → dev/perf에서 매 요청 토큰 재발급 | dev 프로필에도 `@EnableCaching` 활성화 또는 기본 캐시 매니저 사용               |
| LockService @Transactional                        | Redis 작업에 MongoDB TX 적용 → 불필요한 session 생성 320/s                       | `@Transactional` 제거 권장                                                      |
| Survivor Space 100% 포화                          | 고부하 시 Survivor 포화 → Old Gen 조기 승격 → Old Gen 90%                        | `parsePathConfig` 이중 파싱 제거(할당 감소) + `-XX:G1NewSizePercent=20`         |

---

## 다음 세션 시작 체크리스트

```bash
# 1. kubectl context 확인
kubectl config current-context
# → arn:aws:eks:ap-northeast-2:220852994885:cluster/eks-boc-2212-stage

# 2. ec-web24 상태 (perf profile 적용 여부)
kubectl get pod -n ec-dev -l back=ec-web24
kubectl exec -n ec-dev {pod} -c ec-web24 -- env | grep "SPRING_PROFILES\|BASE_URL"
# → SPRING_PROFILES_ACTIVE=dev,perf
# → BASE_URL=http://kec-external-mock.ec-dev.svc.cluster.local

# 3. kec-external-mock (3 replicas, Toxiproxy off)
kubectl get pods -n ec-dev -l back=kec-external-mock
# → 3개 모두 1/1 Running (Toxiproxy 없으므로 1/1)

# 4. WireMock 매핑 확인
kubectl port-forward pod/{mock-pod} 8080:8080 -n ec-dev &
curl http://localhost:8080/__admin/mappings | python3 -c "..."
# → /platform/internal/namespaces/.../coupon/code 존재 확인

# 5. Locust 기존 배포 확인 (재사용 또는 재배포)
helm list -n ec-dev | grep locust
kubectl get pods -n ec-dev | grep locust-master

# 6. 포트포워딩
kubectl port-forward pod/{locust-master} 8089:8089 -n ec-dev &
kubectl port-forward pod/{ec-web24} 9090:8080 -n ec-dev &  # actuator

# 7. WireMock 재시작 후 매핑 재등록 (pod 재시작 있었다면)
curl -X POST http://localhost:8080/__admin/mappings -H "Content-Type: application/json" -d '{...}'
```

---

## 성능 기준 (2607-COUPON/ASTROARENA 1 pod 기준)

| Stage | users | 기대 RPS | p50    | p95       | 판정           |
| ----- | ----- | -------- | ------ | --------- | -------------- |
| 1     | 100   | ~70      | ~130ms | ~190ms    | PASS           |
| 2     | 300   | ~180     | ~180ms | ~460ms    | PASS           |
| 3     | 500   | ~220     | ~980ms | ~1,900ms  | ⚠️ 1 pod 한계  |
| 4     | 1000  | ~350     | -      | ~10,000ms | ❌ OkHttp 병목 |
