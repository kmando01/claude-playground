# alarm 프로젝트 성능 테스트 설정

## 환경 시작 / 초기화

```bash
# 전체 환경 시작 (인프라 + alarm-api + alarm-consumer)
./perf-test/start-all.sh

# DB TRUNCATE + Redis FLUSH
./perf-test/reset-test-data.sh

# 클린 상태 검증
docker exec alarm-mysql mysql -uroot -proot alarm_db \
  -e "SELECT COUNT(*) FROM notification; SELECT COUNT(*) FROM outbox;"
```

## TPS 목표 (ADR-001 기준)

| 환경 | write TPS | read TPS | 근거 |
|------|-----------|----------|------|
| 로컬 Docker Compose | **150** | **300** | 평균 부하(347 TPS) 단일 머신 조정 (÷4) |
| 운영 평균 | 600 | 1200 | ADR-001: 일 30M건, 평균 347 TPS, write:read=1:2 |
| 운영 피크 | 5000 | 10000 | ADR-001: 피크 5,000 TPS (쓰기) |

## Grafana 대시보드 UID

```bash
# Spring Boot 3.x Statistics
spring_boot_21

# JVM (Micrometer)
cffn6cgpr41kwe
```

## Grafana 패널 캡처 스크립트 (복붙용)

```bash
DIR="docs/perf-reports/{date}-{label}"
BASE_SB="http://admin:admin@localhost:3000/render/d-solo/spring_boot_21/spring-boot-3-x-statistics"
BASE_JVM="http://admin:admin@localhost:3000/render/d-solo/cffn6cgpr41kwe/jvm-micrometer"
COMMON="&from=now-6m&to=now&width=1200&height=400&kiosk&theme=light"
APP_VARS="orgId=1&var-application=alarm-api&var-instance=host.docker.internal%3A8080&var-hikaricp=HikariPool-1"

for panel_info in "36:hikaricp-connections" "2:response-time" "4:request-count" "74:gc-count" "68:threads"; do
  id="${panel_info%%:*}"; name="${panel_info##*:}"
  printf "Capturing %-30s..." "$name"
  curl -sf "${BASE_SB}?${APP_VARS}&panelId=${id}${COMMON}" -o "${DIR}/${name}.png" \
    && echo "OK ($(du -k "${DIR}/${name}.png" | cut -f1)KB)" || echo "FAILED"
done

curl -sf "${BASE_JVM}?${APP_VARS}&panelId=32${COMMON}" -o "${DIR}/jvm-threads.png" \
  && echo "jvm-threads OK" || echo "jvm-threads FAILED"
```

## 패널 ID 표

| 패널 | 대시보드 | panelId |
|------|----------|---------|
| HikariCP Connections | spring_boot_21 | 36 |
| HTTP Response Time | spring_boot_21 | 2 |
| HTTP Request Count | spring_boot_21 | 4 |
| GC Count | spring_boot_21 | 74 |
| Threads | spring_boot_21 | 68 |
| JVM Threads | cffn6cgpr41kwe | 32 |

> **주의**: `tomcat_threads_busy_threads` 메트릭 미수집 확인됨 (Action Item B1).
> Threads 패널(68)은 Spring executor 기준이며 Tomcat 스레드 아님.

## Prometheus 지표 수집 스크립트 (alarm-api 전용)

```bash
python3 -c "
import urllib.parse, subprocess, json
APP = 'alarm-api'
queries = [
  ('hikaricp_pending_max',  f'max_over_time(hikaricp_connections_pending{{application=\"{APP}\"}}[6m])'),
  ('hikaricp_active_max',   f'max_over_time(hikaricp_connections_active{{application=\"{APP}\"}}[6m])'),
  ('hikaricp_active_avg',   f'avg_over_time(hikaricp_connections_active{{application=\"{APP}\"}}[6m])'),
  ('heap_used_max_MB',      f'max_over_time(jvm_memory_used_bytes{{application=\"{APP}\",area=\"heap\"}}[6m])/1024/1024'),
  ('executor_active_max',   f'max_over_time(executor_active_threads{{application=\"{APP}\"}}[6m])'),
  ('http_active_req_max',   f'max_over_time(http_server_requests_active_seconds_count{{application=\"{APP}\"}}[6m])'),
  ('http_5xx_total',        f'sum(increase(http_server_requests_seconds_count{{application=\"{APP}\",status=~\"5..\"}}[6m]))'),
  ('gc_pause_max_ms',       f'max_over_time(jvm_gc_pause_seconds_max{{application=\"{APP}\"}}[6m])*1000'),
]
for name, q in queries:
    r = subprocess.run(['curl','-s',f'http://localhost:9090/api/v1/query?query={urllib.parse.quote(q)}'], capture_output=True, text=True)
    data = json.loads(r.stdout)
    vals = [(x['metric'].get('name','?'), x['value'][1]) for x in data['data']['result']] or [('N/A','N/A')]
    print(f'{name:30s}: {vals}')
"
```

## Step 1.5 캡처 스크립트 (복붙용 — load 완료 즉시 실행)

```python
# python3로 실행 — DIR 변수 먼저 설정
import subprocess, os

dir = 'docs/perf-reports/{date}-{label}'  # ← 변경
uid = 'spring_boot_21'; slug = 'spring-boot-3-x-statistics'
TM = 'from=now-6m&to=now&width=1200&height=400&kiosk&theme=light'
BASE = f'http://admin:admin@localhost:3000/render/d-solo/{uid}/{slug}'
API = 'orgId=1&var-application=alarm-api&var-instance=host.docker.internal%3A8080&var-hikaricp=HikariPool-1'
CON = 'orgId=1&var-application=alarm-consumer&var-instance=host.docker.internal%3A8082&var-hikaricp=HikariPool-1'
panels = [
    (API,'36','api-hikaricp-connections.png'),
    (API,'2', 'api-response-time.png'),
    (API,'68','api-threads.png'),
    (CON,'36','consumer-hikaricp-connections.png'),
    (CON,'68','consumer-threads.png'),
]
for vars, pid, name in panels:
    r = subprocess.run(['curl','-sf',f'{BASE}?{vars}&panelId={pid}&{TM}','-o',f'{dir}/{name}'], capture_output=True)
    size = os.path.getsize(f'{dir}/{name}') if os.path.exists(f'{dir}/{name}') else 0
    print(f'{name}: {"OK" if r.returncode==0 and size>1000 else "FAIL (size="+str(size)+")"}')

# 캡처 수 확인
count = len([f for f in os.listdir(dir) if f.endswith('.png')])
print(f'PNG 캡처 수: {count} {"✅" if count >= 5 else "⛔ 재실행 필요"}')
```

```bash
# Prometheus CB 지표 포함 저장
python3 -c "
import urllib.parse, subprocess, json
dir='docs/perf-reports/{date}-{label}'
def q(name, query):
    r=subprocess.run(['curl','-s',f'http://localhost:9090/api/v1/query?query={urllib.parse.quote(query)}'],capture_output=True,text=True)
    vals=[(x['metric'].get('name','?'),x['value'][1]) for x in json.loads(r.stdout)['data']['result']] or [('N/A','N/A')]
    return f'{name}: {vals}'
lines=[
    q('api_hikaricp_pending_max',  'max_over_time(hikaricp_connections_pending{application=\"alarm-api\"}[6m])'),
    q('api_hikaricp_active_max',   'max_over_time(hikaricp_connections_active{application=\"alarm-api\"}[6m])'),
    q('con_hikaricp_pending_max',  'max_over_time(hikaricp_connections_pending{application=\"alarm-consumer\"}[6m])'),
    q('cb_failure_rate',           'resilience4j_circuitbreaker_failure_rate{application=\"alarm-consumer\"}'),
    q('cb_state_open',             'resilience4j_circuitbreaker_state{application=\"alarm-consumer\",state=\"open\"}'),
    q('api_5xx_total',             'sum(increase(http_server_requests_seconds_count{application=\"alarm-api\",status=~\"5..\"}[6m]))'),
]
open(f'{dir}/prometheus-metrics.txt','w').write('\n'.join(lines))
print('prometheus-metrics.txt 저장 완료')
"
```

## 앱 재시작 시 강화 웜업 절차

```bash
# 1단계: 표준 smoke (50 TPS × 3min)
docker compose --profile test run --rm k6 run /scripts/smoke.js

# 2단계: 중간 부하 웜업 (100 TPS × 2min) — 재시작 시에만
# load.js에서 stages를 임시 수정하거나, 별도 스크립트 사용
# 목표: JIT 컴파일 완료 + HikariCP 커넥션 안정화
```

## k6 summary export 경로 주의

```bash
# k6 컨테이너 볼륨 매핑:
#   호스트: ./perf-test/scripts  →  컨테이너: /scripts
# results/ 디렉토리는 perf-test/scripts/results/ 아래에 있어야 함

mkdir -p perf-test/scripts/results/{round-label}

docker compose --profile test run --rm k6 run \
  --out experimental-prometheus-rw \
  --summary-export=/scripts/results/{round-label}/k6-summary.json \
  /scripts/load.js
```
