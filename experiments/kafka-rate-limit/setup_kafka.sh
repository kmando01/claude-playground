#!/bin/bash
# Kafka KRaft 모드 로컬 셋업
set -e

KAFKA_HOME=/tmp/kafka_2.13-3.9.0
LOG_DIR=/tmp/kafka-logs
DATA_DIR=/tmp/kafka-data

echo "=== Kafka 기존 프로세스 종료 ==="
pkill -f "kafka.Kafka" 2>/dev/null || true
sleep 2

echo "=== 데이터 디렉토리 초기화 ==="
rm -rf $LOG_DIR $DATA_DIR
mkdir -p $LOG_DIR $DATA_DIR

echo "=== KRaft 설정 파일 생성 ==="
cat > /tmp/kafka-server.properties << 'EOF'
# KRaft mode
process.roles=broker,controller
node.id=1
controller.quorum.voters=1@localhost:9093
listeners=PLAINTEXT://localhost:9092,CONTROLLER://localhost:9093
advertised.listeners=PLAINTEXT://localhost:9092
controller.listener.names=CONTROLLER
inter.broker.listener.name=PLAINTEXT
listener.security.protocol.map=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT

log.dirs=/tmp/kafka-data
num.partitions=4
offsets.topic.replication.factor=1
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
log.retention.hours=1
log.segment.bytes=1073741824
EOF

echo "=== KRaft 클러스터 ID 생성 및 포맷 ==="
CLUSTER_ID=$($KAFKA_HOME/bin/kafka-storage.sh random-uuid)
echo "Cluster ID: $CLUSTER_ID"
$KAFKA_HOME/bin/kafka-storage.sh format -t $CLUSTER_ID -c /tmp/kafka-server.properties

echo "=== Kafka 브로커 시작 ==="
KAFKA_LOG4J_OPTS="-Dlog4j.configuration=file:$KAFKA_HOME/config/log4j.properties" \
$KAFKA_HOME/bin/kafka-server-start.sh /tmp/kafka-server.properties > /tmp/kafka-broker.log 2>&1 &

echo "Kafka 시작 대기 (15초)..."
sleep 15

echo "=== 브로커 상태 확인 ==="
$KAFKA_HOME/bin/kafka-broker-api-versions.sh --bootstrap-server localhost:9092 2>&1 | head -3 && echo "Kafka OK"
