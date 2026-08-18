#!/bin/bash
# quick-test.sh — 프로파일 기반 baseline 테스트 (모니터링 자동 포함)
#
# Usage:
#   ./quick-test.sh <cni> <profile_path>
#   ./quick-test.sh macvlan scenarios/1-rapid-rise/rapid-01.yaml
#   ./quick-test.sh ipvlan scenarios/6-steady/steady-08.yaml
#
# Legacy (프로파일 없이 고정 500M):
#   ./quick-test.sh macvlan 60

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CNI="${1:-macvlan}"
PROFILE="${2:-}"
NAMESPACE="free5gc"
TARGET_IP="10.10.3.1"
TARGET_PORT="5201"

# 프로파일 모드 vs 레거시 모드 판별
if [[ -f "$PROFILE" ]] || [[ -f "${SCRIPT_DIR}/${PROFILE}" ]]; then
    # 프로파일 모드
    [[ -f "$PROFILE" ]] || PROFILE="${SCRIPT_DIR}/${PROFILE}"
    PROFILE_NAME=$(python3 -c "import yaml; print(yaml.safe_load(open('$PROFILE'))['name'])")
    RUN_ID="${CNI}_${PROFILE_NAME}_$(date +%Y%m%d_%H%M%S)"
    MODE="profile"
else
    # 레거시 모드 (고정 bandwidth + duration)
    DURATION="${2:-60}"
    RUN_ID="${CNI}_$(date +%Y%m%d_%H%M%S)"
    MODE="legacy"
fi

MONITOR_DIR="${SCRIPT_DIR}/monitor-data/${RUN_ID}"

echo "═══════════════════════════════════════"
echo "  Quick Baseline Test"
echo "  CNI: $CNI"
if [[ "$MODE" == "profile" ]]; then
    echo "  Profile: $PROFILE"
    echo "  Name: $PROFILE_NAME"
else
    echo "  Mode: legacy (500M, ${DURATION}s)"
fi
echo "  Run ID: $RUN_ID"
echo "═══════════════════════════════════════"

# 1. CNI 전환
echo "[$(date '+%H:%M:%S')] Setting CNI: $CNI"
"${SCRIPT_DIR}/../arm_k8s/nwdaf/nwdaf-switch.sh" "$CNI"
echo "[$(date '+%H:%M:%S')] Waiting 30s for stabilization..."
sleep 30

# 2. 총 duration 계산
if [[ "$MODE" == "profile" ]]; then
    TOTAL_DURATION=$(python3 -c "
import yaml
p = yaml.safe_load(open('$PROFILE'))
print(sum(ph['duration'] for ph in p['phases']))
")
else
    TOTAL_DURATION="$DURATION"
fi

# 3. 모니터링 시작
echo "[$(date '+%H:%M:%S')] Starting monitor (total: ${TOTAL_DURATION}s)..."
"${SCRIPT_DIR}/monitor/monitor-collector.sh" \
    --interval 5 \
    --duration $((TOTAL_DURATION + 10)) \
    --run-id "$RUN_ID" \
    --output-dir "$MONITOR_DIR" \
    --background

# 3.1 metadata에 트래픽 정보 기록
sleep 1
python3 -c "
import json, yaml
m = '${MONITOR_DIR}/metadata.json'
with open(m) as f: data = json.load(f)
data['cni'] = '${CNI}'
if '${MODE}' == 'profile':
    p = yaml.safe_load(open('${PROFILE}'))
    data['traffic'] = {
        'profile_name': p['name'],
        'pattern': p['pattern'],
        'description': p['description'],
        'packet_size': str(p['packet_size']) + 'B',
        'total_duration_sec': ${TOTAL_DURATION},
        'phases': len(p['phases']),
        'profile': p['pattern']
    }
else:
    data['traffic'] = {
        'protocol': 'UDP',
        'bandwidth': '500Mbps',
        'packet_size': '1400B',
        'duration_sec': ${TOTAL_DURATION},
        'profile': 'large (T1)'
    }
with open(m, 'w') as f: json.dump(data, f, indent=2)
" 2>/dev/null || true

# 4. 트래픽 실행
if [[ "$MODE" == "profile" ]]; then
    echo "[$(date '+%H:%M:%S')] Running profile phases..."
    python3 -c "
import yaml, subprocess, sys, json, os

p = yaml.safe_load(open('${PROFILE}'))
pkt_size = p['packet_size']
monitor_dir = '${MONITOR_DIR}'
loss_file = os.path.join(monitor_dir, 'iperf3_loss.jsonl')

with open(loss_file, 'w') as lf:
    for i, phase in enumerate(p['phases']):
        bw = phase['bandwidth']
        dur = phase['duration']
        print(f'  Phase {i+1}/{len(p[\"phases\"])}: {bw} for {dur}s (pkt={pkt_size}B)', flush=True)
        cmd = [
            'kubectl', 'exec', '-n', '${NAMESPACE}', 'iperf3-n3', '--',
            'iperf3', '-c', '${TARGET_IP}', '-p', '${TARGET_PORT}',
            '-u', '-b', bw, '-l', str(pkt_size), '-t', str(dur),
            '-i', '5', '--json'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        try:
            data = json.loads(result.stdout)
            # interval별 데이터 추출
            for interval in data.get('intervals', []):
                s = interval['sum']
                ts_offset = s.get('start', 0)
                record = {
                    'phase': i+1,
                    'bandwidth_offered': bw,
                    'start': s.get('start', 0),
                    'end': s.get('end', 0),
                    'bytes': s.get('bytes', 0),
                    'bps': s.get('bits_per_second', 0),
                    'packets': s.get('packets', 0),
                    'lost_packets': s.get('lost_packets', 0),
                    'lost_percent': s.get('lost_percent', 0),
                }
                lf.write(json.dumps(record) + '\n')
                lf.flush()
            # 최종 결과 출력
            end = data.get('end', {}).get('sum', {})
            lost = end.get('lost_packets', 0)
            total = end.get('packets', 0)
            pct = end.get('lost_percent', 0)
            bps = end.get('bits_per_second', 0) / 1e6
            print(f'    → {bps:.1f} Mbps, loss: {lost}/{total} ({pct:.2f}%)', flush=True)
        except (json.JSONDecodeError, KeyError) as e:
            print(f'    → parse error: {e}', flush=True)
            # fallback: raw 결과 저장
            pass

print(f'  Loss log: {loss_file}', flush=True)
" 2>&1 | tee "${MONITOR_DIR}/iperf3-result.txt"
else
    echo "[$(date '+%H:%M:%S')] Running iperf3 (UDP ${TOTAL_DURATION}s, 500M, 1400B)..."
    kubectl exec -n "$NAMESPACE" iperf3-n3 -- \
        iperf3 -c "$TARGET_IP" -p "$TARGET_PORT" -u -b 500M -l 1400 -t "$TOTAL_DURATION" \
        -i 5 --json 2>&1 | python3 -c "
import sys, json, os
monitor_dir = '${MONITOR_DIR}'
loss_file = os.path.join(monitor_dir, 'iperf3_loss.jsonl')
raw = sys.stdin.read()
try:
    data = json.loads(raw)
    with open(loss_file, 'w') as lf:
        for interval in data.get('intervals', []):
            s = interval['sum']
            record = {
                'phase': 1,
                'bandwidth_offered': '500M',
                'start': s.get('start', 0),
                'end': s.get('end', 0),
                'bytes': s.get('bytes', 0),
                'bps': s.get('bits_per_second', 0),
                'packets': s.get('packets', 0),
                'lost_packets': s.get('lost_packets', 0),
                'lost_percent': s.get('lost_percent', 0),
            }
            lf.write(json.dumps(record) + '\n')
    end = data.get('end', {}).get('sum', {})
    bps = end.get('bits_per_second', 0) / 1e6
    lost = end.get('lost_packets', 0)
    total = end.get('packets', 0)
    pct = end.get('lost_percent', 0)
    print(f'  → {bps:.1f} Mbps, loss: {lost}/{total} ({pct:.2f}%)')
    print(f'  Loss log: {loss_file}')
except Exception as e:
    print(f'  Parse error: {e}')
    with open(os.path.join(monitor_dir, 'iperf3-raw.json'), 'w') as f:
        f.write(raw)
"
fi

# 5. 모니터링 종료
echo "[$(date '+%H:%M:%S')] Stopping monitor..."
"${SCRIPT_DIR}/monitor/monitor-collector.sh" --stop 2>/dev/null || true

# 6. 결과 요약
echo ""
echo "═══════════════════════════════════════"
echo "  Results: ${MONITOR_DIR}/"
echo "═══════════════════════════════════════"
ls -la "$MONITOR_DIR/" 2>/dev/null
