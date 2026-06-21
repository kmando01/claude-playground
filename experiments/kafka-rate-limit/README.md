# Kafka Rate Limit 실험

> 실험 보고서: [kafka-rate-limit-empirical.md](./kafka-rate-limit-empirical.md)

Kafka 컨슈머의 외부 API rate limit 대응 패턴 5개를 실측으로 검증한다.

## 검증 가설

| # | 가설 | 결과 |
|---|---|---|
| H1 | burst 크기 감소 → 429 비율 감소 | ✓ burst=200: 88.9% → burst=30: 58.8% |
| H2 | pause/resume → 429 영향 격리 | ✓ max_retries_per_msg=1 |
| H3 | poll 누락 → rebalance 발생 | ✓ 20s sleep → REVOKE 즉시 |
| H4 | Token Bucket → 429≈0 | ✓ 10,000건 중 429=0 |
| H5 | at-least-once (seek 필수) | ✓ 158건 직접 추적 |

## 시나리오

| 파일 | 설명 |
|---|---|
| `consumer_a.py` | Naive — concurrent burst=200, 재시도 루프 |
| `consumer_b.py` | Static — concurrent burst=30, 재시도 루프 |
| `consumer_c.py` | Reactive — sequential + pause/resume + seek() |
| `consumer_d.py` | Proactive — Token Bucket 80/s + pause/resume |
| `consumer_e.py` | Rebalance 검증 — poll 없이 sleep |
| `mock_api.py` | FastAPI mock (100 req/s 슬라이딩 윈도우) |
| `monitor.py` | 1초 간격 lag + stats CSV 수집 |
| `analyze.py` | 결과 분석 및 표 출력 |

## 핵심 발견

1. **seek() 없는 pause/resume은 at-least-once를 보장하지 않는다**  
   kafka-python에서 `poll()`은 position을 advance시킴. pause/resume만으로는 429 받은 메시지가 현재 세션에서 스킵됨.

2. **순차 처리에서 max.poll.records는 429에 영향 없음**  
   burst 효과는 동시 처리(ThreadPoolExecutor)로 재현해야 측정 가능.

## 재현 방법

```bash
# 1. Kafka 3.x (KRaft) + Java 필요
bash setup_kafka.sh

# 2. 의존성
pip install kafka-python fastapi uvicorn requests

# 3. Mock API 시작
python3 mock_api.py &

# 4. 시나리오 실행
bash run_scenario.sh A exp-a
bash run_scenario.sh B exp-b
bash run_scenario.sh C exp-c
bash run_scenario.sh D exp-d
bash run_scenario.sh E exp-e

# 5. 분석
python3 analyze.py
```

## 결과 요약

| 시나리오 | 429 비율 | max_retries | 처리 시간 |
|---|---|---|---|
| A (burst=200) | 88.9% | 25회 | 172s |
| B (burst=30) | 58.8% | 12회 | 106s |
| C (pause/resume) | 1.6% | 1회 | 110s |
| D (Token Bucket) | 0.0% | 0회 | 128s |
| E (rebalance) | — | — | rebalance 2회 |
