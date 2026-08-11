#!/bin/bash
# quick-test.sh — 모니터링 포함 빠른 baseline 테스트
# Usage: ./quick-test.sh [macvlan|ipvlan] [duration_sec]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CNI="${1:-macvlan}"
DURATION="${2:-60}"
NAMESPACE="free5gc"
RUN_ID="${CNI}_$(date +%Y%m%d_%H%M%S)"
MONITOR_DIR="${SCRIPT_DIR}/monitor-data/${RUN_ID}"

echo "═══════════════════════════════════════"
echo "  Quick Baseline Test"
echo "  CNI: $CNI"
echo "  Duration: ${DURATION}s"
echo "  Run ID: $RUN_ID"
echo "═══════════════════════════════════════"

# 1. CNI 전환
echo "[$(date '+%H:%M:%S')] Setting CNI: $CNI"
"${SCRIPT_DIR}/../arm_k8s/nwdaf/nwdaf-switch.sh" "$CNI"
echo "[$(date '+%H:%M:%S')] Waiting 10s for stabilization..."
sleep 10

# 2. 모니터링 시작
echo "[$(date '+%H:%M:%S')] Starting monitor..."
"${SCRIPT_DIR}/monitor/monitor-collector.sh" \
    --interval 5 \
    --duration $((DURATION + 10)) \
    --run-id "$RUN_ID" \
    --output-dir "$MONITOR_DIR" \
    --background

# 3. iperf3 실행
echo "[$(date '+%H:%M:%S')] Running iperf3 (UDP ${DURATION}s, 500M, 1400B)..."
kubectl exec -n "$NAMESPACE" iperf3-n3 -- \
    iperf3 -c 10.10.3.1 -p 5201 -u -b 500M -l 1400 -t "$DURATION" 2>&1 | tee "${MONITOR_DIR}/iperf3-result.txt"

# 4. 모니터링 종료
echo "[$(date '+%H:%M:%S')] Stopping monitor..."
"${SCRIPT_DIR}/monitor/monitor-collector.sh" --stop 2>/dev/null || true

# 5. 결과 요약
echo ""
echo "═══════════════════════════════════════"
echo "  Results: ${MONITOR_DIR}/"
echo "═══════════════════════════════════════"
ls -la "$MONITOR_DIR/" 2>/dev/null
