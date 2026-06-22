---
name: jvm-profiling
description: "JVM 프로파일링 실전 가이드. 증상 → 도구 선택 → 실행 커맨드 → 결과 해석 → 수정 사이클. CPU 병목·메모리 누수·락 경합·I/O 대기 4가지 시나리오를 다룬다. kakaopay-coupon 프로젝트에서 async-profiler / JFR을 활용한 운영급 프로파일링에 특화. Use when: '느려요', '프로파일링', 'JFR', 'async-profiler', 'flame graph', 'CPU 병목', '메모리 누수', 'GC 튜닝', '락 경합', 'wall-clock', '스레드 블로킹', '/jvm-profiling'."
---

# JVM 프로파일링 실전 가이드

> "여기가 느릴 것 같다"는 추측을 "이 메서드가 CPU의 40%를 쓰고 있다"는 데이터로 바꾸기 위한 워크플로우.
> **핵심 원칙: 코드 수정 전에 측정, 측정 후에 수정, 수정 후에 재측정.**

---

## Step 0: 증상 분류 (도구 선택 전에)

사용자가 설명한 증상에서 시나리오를 먼저 특정한다:

| 증상 | 의심 시나리오 | → 섹션 |
|------|--------------|--------|
| 응답 느리고 CPU 높음 | CPU 병목 | [A] |
| 시간 지날수록 느려짐, Old Gen 증가, OOM | 메모리 누수/GC 압박 | [B] |
| CPU 낮은데 throughput 안 나옴, BLOCKED 스레드 | 락 경합 | [C] |
| CPU/락 깨끗한데 응답 느림 (I/O, 외부 호출 의심) | wall-clock 대기 | [D] |

**하나만 선택해서 시작한다. 동시에 여러 개 켜지 말 것** (프로파일러 자체가 노이즈를 유발).

---

## [A] CPU 병목

### 언제 의심하나
- CPU 사용률 > 70% 지속
- 부하 테스트에서 throughput이 hardware 한계 전에 평탄해짐

### 실행 커맨드

**JFR (추가 설치 없음, JDK 11+)**
```bash
jcmd                    # PID 확인
jcmd <pid> JFR.start name=cpu duration=60s settings=profile filename=/tmp/cpu.jfr
jmc /tmp/cpu.jfr        # GUI 분석: Method Profiling → Hot Methods 또는 Flame View
```

**async-profiler (더 정밀, safepoint bias 없음)**
```bash
# kakaopay-coupon 환경 (M-series Mac)
cd /path/to/async-profiler
./profiler.sh -d 60 -f /tmp/cpu.html <pid>

# 더 정밀 (1ms 간격)
./profiler.sh -e cpu -i 1ms -d 60 -f /tmp/cpu.html <pid>
```

### Flame Graph 읽는 법
- **가로 폭** = 전체 시간 대비 비율. 넓을수록 CPU를 많이 씀.
- **세로** = 호출 스택. 위가 호출자, 아래가 피호출자.
- **색상은 무의미** (랜덤).
- **가장 넓고 평평한 봉우리(plateau)의 최상단** = 1차 용의자.

### Self time vs Total time

| 용어 | 의미 | 해석 |
|------|------|------|
| **Self (Flat)** | 메서드 본체가 직접 쓴 시간 | 높으면 = 이 메서드가 범인 |
| **Total (Cum)** | 하위 호출 포함 전체 | 높아도 Self 낮으면 = 아래에 범인이 있음 |

### kakaopay-coupon 전형적 핫스팟

- `ObjectMapper.writeValueAsString` / `readValue` — 직렬화 반복 수행
- `EntityManager.persist` + `GenerationType.IDENTITY` — INSERT마다 SELECT LAST_INSERT_ID
- Lua 스크립트 없는 Redis check-then-act — round-trip 2배

---

## [B] 메모리 누수 / GC 압박

### 언제 의심하나
- Old Gen 사용량이 GC 후에도 우상향
- Full GC 또는 Concurrent GC cycle이 잦아짐
- 응답 시간이 시간이 지날수록 점점 늘어남 (GC pause 누적)

### 단계별 접근

**1단계: GC 로그로 패턴 확인 (제일 먼저)**
```bash
# JVM 시작 옵션에 추가
-Xlog:gc*:file=/tmp/gc.log:time,level,tags

# 실행 중 GC 정보 즉시 확인
jcmd <pid> GC.heap_info
```
→ [gceasy.io](https://gceasy.io)에 업로드하면 자동 분석. "Heap after GC" 우상향이면 누수.

**2단계: Allocation 프로파일링 (어디서 객체가 만들어지나)**
```bash
# async-profiler (10MB마다 1샘플)
./profiler.sh -e alloc -d 60 -f /tmp/alloc.html <pid>

# JFR
jcmd <pid> JFR.start name=alloc duration=120s settings=profile filename=/tmp/alloc.jfr
# JMC → Memory → Allocations
```

**3단계: Heap Dump (누수 확정 시)**
```bash
jcmd <pid> GC.heap_dump /tmp/heap.hprof

# OOM 발생 시 자동 생성 (JVM 옵션)
-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/tmp/
```
→ Eclipse MAT으로 분석:
1. **Leak Suspects Report** — 자동 분석
2. **Dominator Tree** — 메모리를 가장 많이 retain하는 객체
3. **Path to GC Roots** — 왜 GC 안 되는지 (어떤 참조가 잡고 있나)

### kakaopay-coupon 전형적 패턴
- `Map<Long, CouponCache>` 같은 static 캐시에 eviction 없음
- `@Transactional` 내에서 대량 엔티티 로딩 후 영속성 컨텍스트가 오래 유지

---

## [C] 락 경합

### 언제 의심하나
- CPU 사용률 낮은데 RPS가 안 나옴
- 스레드 덤프에 `BLOCKED` 상태 스레드 다수
- `jstack <pid>` 결과에 `waiting to lock <...>` 줄이 많음

### 실행 커맨드

**async-profiler**
```bash
# 락 경합 프로파일 — 얼마나 오래 기다렸나 (나노초 단위)
./profiler.sh -e lock -d 60 -f /tmp/lock.html <pid>
```
결과 해석: Top 프레임 = 어떤 락 객체 클래스, 아래 스택 = 누가 기다렸는지.

**JFR**
```bash
jcmd <pid> JFR.start name=lock duration=120s settings=profile filename=/tmp/lock.jfr
# JMC → Lock Instances / Contention
```
→ `Java Monitor Enter`, `Java Monitor Wait`, `Java Thread Park` 이벤트 확인.

**스레드 덤프 (즉시 확인)**
```bash
jcmd <pid> Thread.print        # 모든 스레드 스택 출력
jstack <pid> > /tmp/threads.txt   # 파일로 저장
```

### 흔한 해결 패턴

| 원인 | 해결 |
|------|------|
| `synchronized (this)` 범위 과다 | 필드별 별도 lock으로 분리 |
| `Hashtable` / `Collections.synchronizedMap` | `ConcurrentHashMap` 교체 |
| Read-heavy 공유 자원 | `ReadWriteLock` 또는 `StampedLock` |
| 락 자체 제거 가능 | 불변 객체, ThreadLocal, copy-on-write |

---

## [D] Wall-clock 대기 (I/O / 외부 호출 / Sleep)

### 언제 의심하나
- CPU 프로파일이 깨끗한데 응답이 느림
- HTTP 외부 호출, Redis, DB 응답을 기다리는 구간 의심
- `Thread.sleep`, `Future.get()` 같은 패턴이 코드에 있음

### 실행 커맨드

```bash
# wall-clock 모드: 스레드가 자고 있어도 샘플링 (-t: 스레드별 분리)
./profiler.sh -e wall -t -d 30 -f /tmp/wall.html <pid>
```

결과에서 `SocketInputStream.read`, `RedisClient.connect`, `HikariPool.getConnection` 같은 I/O 대기 프레임이 주를 이루면 코드가 아닌 **인프라 레이턴시 또는 설정** 문제.

---

## 운영 환경 안전 운용

### JFR — 항상 켜두는 패턴 (overhead < 1%)

```bash
# JVM 시작 옵션
-XX:StartFlightRecording=name=continuous,maxage=24h,maxsize=2g,settings=default,disk=true
-XX:FlightRecorderOptions=repository=/var/log/jfr
```

장애 발생 시:
```bash
jcmd <pid> JFR.dump name=continuous filename=/tmp/snapshot.jfr
```

### Incident 발생 시 5분 프로파일

```bash
jcmd <pid> JFR.start name=incident duration=5m settings=profile filename=/tmp/incident.jfr
```
재시작 불필요. 파일을 로컬로 받아 JMC로 분석.

### async-profiler 컨테이너 환경 주의

- `SYS_PTRACE`, `SYS_ADMIN` 권한 또는 `perf_event_paranoid` 조정 필요
- 권한 없는 환경 fallback: `-e ctimer`
- GraalVM Native Image에서는 동작 안 함

---

## 흔한 함정

| 함정 | 대응 |
|------|------|
| 30초 프로파일은 표본이 너무 작음 | 최소 1분, 가능하면 5분 |
| 로컬 ≠ 운영 (GC 빈도, 동시성이 다름) | staging 또는 운영에서 직접 측정 |
| allocation + native 프로파일링 동시 실행 | 한 번에 하나씩, 프로파일러 자체가 노이즈 유발 |
| 평균 응답 시간만 봄 | p99, p999도 같이 볼 것 (JFR Latency 뷰) |
| "String 연산이 느릴 것 같다" | 측정 먼저. JIT가 대부분 최적화함. 직관 말고 데이터. |

---

## Quick Cheat Sheet

```bash
# PID 확인
jcmd

# CPU (JFR)
jcmd <pid> JFR.start name=cpu duration=60s settings=profile filename=/tmp/cpu.jfr

# CPU (async-profiler)
./profiler.sh -d 60 -f /tmp/cpu.html <pid>

# 메모리 할당
./profiler.sh -e alloc -d 60 -f /tmp/alloc.html <pid>

# 락 경합
./profiler.sh -e lock -d 60 -f /tmp/lock.html <pid>

# Wall-clock (I/O 대기)
./profiler.sh -e wall -t -d 30 -f /tmp/wall.html <pid>

# Heap dump
jcmd <pid> GC.heap_dump /tmp/heap.hprof

# GC 로그
-Xlog:gc*:file=/tmp/gc.log:time,level,tags
```

---

---

## [E] 가상 스레드 (Virtual Thread) 프로파일링 ★ (신규)

> 가상 스레드 도입 후 "메모리가 이상하게 많이 쓰인다", "처리량이 예상보다 낮다",
> "스레드가 많은데 CPU가 안 오른다" 같은 증상에 특화된 진단 경로.

### 증상 → 진단 도구 매핑

| 증상 | 의심 원인 | 도구 |
|------|----------|------|
| 가상 스레드 N개인데 OS 스레드도 N개에 가까움 | Pinning (synchronized/JNI) | JFR `VirtualThreadPinned` |
| Heap이 급격히 증가, vthread 수 비례 | ThreadLocal 누수 | NMT + heap dump |
| vthread 수 늘려도 TPS가 안 오름 | 커넥션 풀/downstream 자원 포화 | HikariCP metrics |
| 특정 구간 carrier 스레드 포화 | JNI pinning | JFR + parallelism 조정 |

---

### E-1. NMT로 메모리 영역 분리 확인

가상 스레드가 OS stack이 아닌 Java Heap으로 가는지 확인:

```bash
# NMT 활성화 후 JVM 시작
java -XX:NativeMemoryTracking=detail MyApp

# 스냅샷 찍기 (pid 확인: jcmd)
jcmd <pid> VM.native_memory summary

# 핵심 해석 포인트:
# -  Thread (reserved=446568KB, committed=446568KB)
#             (threads #1528)          ← OS 스레드 수 확인
#             (stack: reserved=441712KB ← 플랫폼 스레드면 이 값이 크게 증가
#
# 가상 스레드 정상 패턴:
#   Thread #36 (캐리어 스레드만), stack 소량
#   Java Heap 상승 (Continuation 오브젝트)
```

**가상 스레드 per-thread 메모리 비용 (실측값)**:

| 항목 | 플랫폼 스레드 | 가상 스레드 |
|------|-------------|------------|
| native stack/thread | **278.7 KB** (Xss256k 기준) | **≈ 0 KB** |
| Java Heap/thread | 2.9 KB | 2.4 KB (Continuation) |
| OS 스레드 수 (10K개 생성 시) | ~10,001 | **~40** (캐리어만) |

---

### E-2. JFR로 Pinning 이벤트 캡처

`synchronized` 블록이나 JNI에서 carrier 스레드가 블로킹되는지 확인:

```bash
# JDK 21: VirtualThreadPinned 이벤트 활성화
java -XX:StartFlightRecording=filename=pin.jfr,settings=default \
     -Djdk.tracePinnedThreads=full MyApp

# JFR 파일 분석 (jfr CLI 또는 JMC)
jfr print --events jdk.VirtualThreadPinned pin.jfr | head -50

# 실시간 출력 (pinning 발생 시 스택 트레이스 콘솔에 출력)
java -Djdk.tracePinnedThreads=full MyApp
```

**JDK 25(JEP 491): `synchronized` pinning 해결됨**. JNI pinning은 JDK 버전 무관 잔존.

---

### E-3. Continuation Heap 비용 산정

스택 깊이별 Continuation 크기 (실측값):

```
depth 1   → 2,686 B/vthread
depth 100 → 4,887 B/vthread  (~40B/frame)
depth 200 → 8,806 B/vthread
depth 500 → 21,277 B/vthread

Xmx 산정: vthread_수 × (2KB + depth × 40B) + 앱 Heap
예: 10만 vthread, depth=100 → 10만 × 6KB = 600MB + 앱
```

---

### E-4. Carrier 스레드 수 튜닝

JNI pinning이 있고 parallelism을 늘려야 할 때:

```bash
# 기본값 = CPU 코어 수
-Djdk.virtualThreadScheduler.parallelism=50
-Djdk.virtualThreadScheduler.maxPoolSize=256  # 상한값 (기본 256)

# 효과: parallelism 2배 → JNI 처리량 2배 (선형)
# 주의: OS 스레드도 선형 증가 → 기존 ThreadPool과 동일한 자원 소모
# 권장: JNI 작업은 별도 platform thread pool로 오프로드
```

---

### E-5. ThreadLocal 누수 진단

```bash
# Heap dump 분석
jcmd <pid> GC.heap_dump /tmp/heap.hprof

# MAT(Memory Analyzer Tool) 또는 jmap으로
# ThreadLocalMap.Entry 수와 평균 payload 크기 확인
# → 수 × payload ≈ vthread 수 × ThreadLocal 비용

# 빠른 확인 (GC 전후 used 비교)
# ThreadLocal 1KB × 10만 vthread = 100MB 추가 예상
```

**ThreadLocal vs ScopedValue 비용 (JDK 25 실측)**:

| 방식 | 10KB payload 비용/vthread | 비고 |
|------|--------------------------|------|
| `ThreadLocal` | **10.4 KB** (payload 그대로 복사) | N개 vthread → N배 heap |
| `InheritableThreadLocal` | **≈ 0 KB** (reference 공유) | childValue() 오버라이드 시 동일한 N배 |
| `ScopedValue` | **≈ 0 KB** (shared immutable) | payload 크기 무관 ~3KB/vthread |

---

## 이 스킬과 연관된 스킬

- `static-perf-analysis` — 코드/설정 분석으로 프로파일링 전에 가설 수립
- `perf-bench` — kakaopay-coupon k6 부하 생성 (프로파일링 대상 부하 만들기)
- `hikaricp-pool-sizing` — DB 커넥션 풀 병목 공식 산정
- `stress-test-methodology` — 측정 → 분석 → 리포트 전체 사이클
