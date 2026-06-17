---
name: root-cause-analysis
description: 문제/장애/이상 현상 발생 시 "항상 안된다"는 관찰로 끝내지 않고 왜(Why) 발생했는지 근본 원인을 체계적으로 분석한다. Docker, DB, 네트워크, 성능, 코드 등 도메인에 무관하게 적용. Use when: 뭔가 "안된다", "간헐적으로 터진다", "느려졌다", "소켓을 잃었다", "연결이 끊긴다", "타임아웃 난다", "죽는다", 또는 장애 상황 직면 시. Triggers on "왜", "원인", "분석", "이유", "안 되는 이유", "root cause", "장애".
---

# 근본 원인 분석 (Root Cause Analysis)

## 핵심 원칙

```
관찰 ≠ 분석
"Docker 소켓을 잃는다" → 관찰
"Docker VM에 전체 RAM을 할당해 macOS OOM이 발생했다" → 분석
```

**항상 분석으로 마무리한다. 관찰에서 멈추지 않는다.**

## 분석 프로세스 (5 Why)

1. **현상 정의**: 무엇이 어떻게 실패하는가? (정확하고 구체적으로)
2. **1st Why**: 이 현상이 왜 발생하는가?
3. **2nd Why**: 그 원인은 왜 발생하는가?
4. **3rd Why**: (반복) → 근본 원인 도달까지
5. **증거 수집**: 가설을 지표/로그/수치로 검증
6. **해결책 도출**: 근본 원인에 대한 해결 (증상 해결 아님)

---

## 도메인별 분석 명령

### 메모리/리소스 고갈

```bash
# Mac 메모리 압박 확인
vm_stat | awk '/free/{f=$3} /compressor/{c=$5} END{printf "Free:%.0fMB Compressed:%.0fMB\n",f*4096/1024/1024,c*4096/1024/1024}'
sysctl hw.memsize | awk '{printf "Total RAM: %.0f MB\n",$2/1024/1024}'

# 프로세스별 메모리 상위
ps aux --sort=-%mem | head -10

# Docker VM 메모리 설정 vs 실제
cat ~/Library/Group\ Containers/group.com.docker/settings-store.json | python3 -c "import sys,json;d=json.load(sys.stdin);print('Docker VM:',d.get('MemoryMiB','?'),'MB')"

# Docker 컨테이너 리소스 사용
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

### DB 연결 문제

```bash
# MySQL
mysql -e "SHOW STATUS LIKE 'Threads_connected'; SHOW VARIABLES LIKE 'max_connections';"
mysql -e "SHOW PROCESSLIST;" | head -20

# Connection timeout 순서 확인
# 1. DB wait_timeout
# 2. 로드밸런서 idle timeout  
# 3. 방화벽/NAT timeout
# → 가장 짧은 것 < maxLifetime 설정 확인
```

### 네트워크 단절

```bash
# 소켓 상태
ss -s 2>/dev/null || netstat -s | grep -E "failed|reset|error"

# TIME_WAIT 소켓 수 (과다 시 port exhaustion)
netstat -an | grep TIME_WAIT | wc -l

# Docker 소켓 확인
ls -la /var/run/docker.sock 2>/dev/null || ls -la ~/.docker/run/docker.sock 2>/dev/null
```

### 성능 저하 (JVM/Spring)

```bash
# HikariCP 병목 (Prometheus)
curl -s "http://localhost:9090/api/v1/query?query=hikaricp_connections_pending"
curl -s "http://localhost:9090/api/v1/query?query=hikaricp_connections_usage_seconds_sum/hikaricp_connections_usage_seconds_count*1000"

# GC 압박
curl -s "http://localhost:9090/api/v1/query?query=rate(jvm_gc_pause_seconds_sum[1m])*1000"

# Tomcat 스레드 포화
curl -s "http://localhost:9090/api/v1/query?query=tomcat_threads_current_threads"
```

### 애플리케이션 에러

```bash
# 최근 에러 로그 (종류별 집계)
grep "ERROR\|Exception\|FATAL" app.log | awk '{print $NF}' | sort | uniq -c | sort -rn | head -10

# 에러 발생 시점과 메트릭 상관관계
# → Grafana에서 에러 급증 시점 전후 HikariCP/GC/TPS 확인
```

---

## 분석 보고 형식

분석 완료 후 반드시 아래 구조로 정리:

```
[현상] 무엇이 어떻게 실패하는가
  예) Docker 소켓(/docker.sock)이 사라져 docker 명령이 실패

[원인 체인] Why → Why → Why
  1. Docker Desktop 프로세스가 macOS에 의해 kill됨
  2. macOS OOM killer 발동 (사용 가능한 물리 메모리 <25MB)
  3. Docker VM에 전체 RAM(18,432MB) 할당 → macOS 자신에게 여유 없음

[증거] 수치/로그/지표로 검증
  - vm_stat Free: 25MB (위험 수준)
  - vm_stat Compressed: 1,297MB (메모리 압박 신호)
  - Docker VM 설정: MemoryMiB=18432 = Mac 전체 RAM

[해결책] 근본 원인 제거
  - Docker VM 메모리: 18,432MB → 12,288MB (Mac에 6GB 여유)
  - 효과: macOS OOM 방지 → Docker 안정 운영

[검증 계획] 해결 후 어떻게 확인하는가
  - vm_stat Free > 2,000MB 유지 확인
  - 부하 테스트 중 Docker 소켓 손실 재현 안 됨 확인
```

---

## 자주 놓치는 원인들

| 증상 | 실제 원인 (증상 아닌 것) |
|---|---|
| Docker 소켓 손실 | macOS OOM (VM 메모리 과다 할당) |
| DB 연결 끊김 | 인프라 idle timeout < maxLifetime 설정 |
| 간헐적 500 에러 | HikariCP timeout (pool 부족 아닌 쿼리 지연) |
| k6 dropped iterations | VU 부족 (서버 문제 아님) |
| 앱 OOM | 힙 외 메모리 (netty direct, metaspace) |
| Tomcat 503 | acceptCount 초과 (thread pool이 아님) |

## 안티패턴

```
❌ "Docker가 불안정해요" → 관찰, 분석 아님
❌ "재시작하면 됩니다" → 증상 해소, 원인 제거 아님
❌ "그냥 메모리 늘렸어요" → usage_time 먼저 확인 안 함
❌ 캡처 없이 "~인 것 같습니다" → 추측, 증거 아님
```
