# 근본 원인 분석 가이드

## 원칙

**숫자를 올리기 전에 "왜 부족한가"를 먼저 답한다.**
pool을 올리면 DB가 죽고, threads를 올리면 경쟁이 심해진다.
모든 설정값은 실측 데이터 + 목표 TPS에서 역산한다.

## 핵심 공식

### 1. Tomcat threads ↔ HikariCP pool 관계 (Little's Law)

```
pool    = target_TPS × T_db / 1000
threads = target_TPS × T_req / 1000
ratio   = threads / pool = T_req / T_db
```

| 변수 | 의미 | 실측 방법 |
|------|------|-----------|
| `T_db` | 커넥션 점유 시간 (ms) | `hikaricp_connections_usage_seconds` |
| `T_req` | 전체 요청 처리 시간 (ms) | `http_server_requests_seconds` |
| `target_TPS` | 목표 TPS | ADR / 설계 문서 |

### 예시: 목표 5,000 TPS

| T_db | T_req | 적정 pool | 적정 threads | 비율 |
|------|-------|-----------|-------------|------|
| 5ms | 10ms | 25 | 50 | 2:1 |
| 10ms | 15ms | 50 | 75 | 1.5:1 |
| 10ms | 30ms | 50 | 150 | 3:1 |
| 20ms | 50ms | 100 | 250 | 2.5:1 |

### 2. HikariCP 공식 (DB 관점 상한)

```
max_connections = (CPU_cores × 2) + effective_spindle_count
```

- 로컬 Docker MySQL (4 core): max ~10 이상 의미 없을 수 있음
- 프로덕션 RDS (8 core, SSD): ~17
- 이 값은 **DB가 효율적으로 처리할 수 있는 상한**. 이보다 올리면 DB 내부 경쟁 증가.

### 3. Death Spiral 판별

```
[정상] threads=75, pool=50 → 75개 중 50개만 순간 DB 접근 → 25개 짧은 대기 → OK
[위험] threads=200, pool=30 → 200개 중 170개 대기 → 대기시간 누적 → 처리시간 증가 → 더 많은 대기 → 붕괴
```

**Death Spiral 조건**: `threads / pool > T_req / T_db × 2` 이면 위험

## 실측 데이터 수집 방법

### Load 테스트(정상 부하)에서 수집

```bash
# 커넥션 점유 시간 (T_db)
curl -s "http://localhost:9090/api/v1/query?query=hikaricp_connections_usage_seconds_sum/hikaricp_connections_usage_seconds_count" \
  | python3 -c "import json,sys; [print(f'{float(r[\"value\"][1])*1000:.1f}ms') for r in json.load(sys.stdin)['data']['result']]"

# 커넥션 획득 대기 시간
curl -s "http://localhost:9090/api/v1/query?query=hikaricp_connections_acquire_seconds_sum/hikaricp_connections_acquire_seconds_count" \
  | python3 -c "import json,sys; [print(f'{float(r[\"value\"][1])*1000:.1f}ms') for r in json.load(sys.stdin)['data']['result']]"

# 전체 요청 처리 시간 (T_req)
curl -s "http://localhost:9090/api/v1/query?query=http_server_requests_seconds_sum/http_server_requests_seconds_count" \
  | python3 -c "import json,sys; [print(f'{r[\"metric\"].get(\"uri\",\"?\")}: {float(r[\"value\"][1])*1000:.1f}ms') for r in json.load(sys.stdin)['data']['result']]"
```

### Stress 테스트에서 수집하면 안 되는 이유

Stress에서는 이미 대기 시간이 누적되어 T_db, T_req가 왜곡됨.
반드시 **정상 부하(Load)** 상태에서 측정한 값으로 계산한다.

## 근본 질문 체크리스트

설정값 변경 전에 반드시 답해야 하는 질문들:

- [ ] `T_db`(커넥션 점유 시간)을 실측했는가?
- [ ] `T_req`(전체 처리 시간)을 실측했는가?
- [ ] 목표 TPS가 명확한가? (ADR 근거)
- [ ] 공식에 대입하여 적정 pool/threads를 계산했는가?
- [ ] 현재 값이 계산값보다 큰가/작은가? → 어느 쪽이 근본 원인?
- [ ] DB 관점 상한(CPU cores × 2)을 초과하지 않는가?
- [ ] Death Spiral 조건에 해당하지 않는가?

## 안티패턴 사례

### 사례 1: pool만 올리기 (OSIV ON + pool 10 → 50)
- **결과**: Pending 28 → 149 악화
- **원인**: OSIV ON으로 커넥션 점유 시간이 전체 요청 시간과 동일 → pool 올려도 점유 시간은 불변

### 사례 2: 임의로 pool=30 설정 (OSIV OFF 후)
- **결과**: Load에서는 OK, Stress에서 Pending=169 붕괴
- **원인**: 30이라는 숫자에 근거 없음. Tomcat 200 대비 6.7:1 비대칭이 Death Spiral 유발
