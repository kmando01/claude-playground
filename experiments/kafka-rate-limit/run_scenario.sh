#!/bin/bash
# 단일 시나리오 실행 스크립트
# usage: bash run_scenario.sh <A|B|C|D|E> <group_id>
set -e

SCENARIO=$1
GROUP=$2
BASE_DIR="$HOME/kafka-rate-limit-exp"
KAFKA_HOME=/tmp/kafka_2.13-3.9.0
KAFKA_BIN=$KAFKA_HOME/bin

echo "========================================="
echo "시나리오 $SCENARIO 시작 (group: $GROUP)"
echo "========================================="

# mock API 통계 초기화
curl -s -X POST http://localhost:8080/reset > /dev/null
echo "Mock API 통계 초기화 완료"

# 컨슈머 그룹 offset 초기화 (없으면 무시)
$KAFKA_BIN/kafka-consumer-groups.sh \
    --bootstrap-server localhost:9092 \
    --delete --group $GROUP 2>/dev/null && echo "그룹 $GROUP offset 초기화" || echo "그룹 없음 (정상)"

sleep 1

# 백그라운드 모니터 시작
python3 $BASE_DIR/monitor.py $GROUP > $BASE_DIR/results/scenario_${SCENARIO,,}.csv 2>/dev/null &
MONITOR_PID=$!
echo "모니터 시작 (PID: $MONITOR_PID)"

# 컨슈머 실행
python3 $BASE_DIR/consumer_${SCENARIO,,}.py 2>&1 | tee $BASE_DIR/logs/scenario_${SCENARIO,,}.out

# 모니터 종료
kill $MONITOR_PID 2>/dev/null || true
sleep 1

# 최종 통계 수집
curl -s http://localhost:8080/stats > $BASE_DIR/results/scenario_${SCENARIO,,}_final.json
echo ""
echo "--- 최종 통계 (시나리오 $SCENARIO) ---"
python3 -c "
import json, sys
with open('$BASE_DIR/results/scenario_${SCENARIO,,}_final.json') as f:
    d = json.load(f)
print(f'  총 호출: {d[\"total\"]}')
print(f'  성공:   {d[\"success\"]}')
print(f'  429:    {d[\"rate_limited\"]} ({d[\"rate_limited_ratio\"]*100:.1f}%)')
print(f'  중복:   {d[\"duplicate_count\"]}')
"
echo "========================================="
echo "시나리오 $SCENARIO 완료"
echo "========================================="
