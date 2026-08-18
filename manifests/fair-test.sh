#!/bin/bash
# fair-test.sh — 공정 조건 ipvlan vs macvlan 성능 비교
# 소패킷(64B) 고빈도 UDP 트래픽으로 테스트

set -e

NAMESPACE="free5gc"
DURATION=30  # 각 테스트 30초
RESULTS_DIR="/home/ubuntu/free5gc-k8s-arm/traffic-profiles/monitor/data"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "=== 공정 조건 CNI 비교 실험 ==="
echo "조건: 소패킷(64B), UDP, high pps"
echo "NIC: enp1s0 (물리 NIC 직접 분기)"
echo ""

# ─── Phase 1: macvlan 테스트 ───
echo "[Phase 1] macvlan 테스트"
kubectl apply -f /home/ubuntu/free5gc-k8s-arm/manifests/fair-test-nad.yaml

cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: fair-macvlan-server
  namespace: $NAMESPACE
  annotations:
    k8s.v1.cni.cncf.io/networks: fair-macvlan
spec:
  containers:
  - name: iperf3
    image: networkstatic/iperf3:latest
    command: ["iperf3", "-s"]
    resources:
      requests:
        cpu: "500m"
        memory: "128Mi"
      limits:
        cpu: "500m"
        memory: "128Mi"
---
apiVersion: v1
kind: Pod
metadata:
  name: fair-macvlan-client
  namespace: $NAMESPACE
  annotations:
    k8s.v1.cni.cncf.io/networks: fair-macvlan
spec:
  containers:
  - name: iperf3
    image: networkstatic/iperf3:latest
    command: ["sleep", "infinity"]
    resources:
      requests:
        cpu: "500m"
        memory: "128Mi"
      limits:
        cpu: "500m"
        memory: "128Mi"
EOF

echo "  Pod 시작 대기..."
kubectl wait --for=condition=Ready pod/fair-macvlan-server -n $NAMESPACE --timeout=60s
kubectl wait --for=condition=Ready pod/fair-macvlan-client -n $NAMESPACE --timeout=60s

# macvlan 서버 IP 가져오기 (annotation에서)
MACVLAN_SERVER_IP=$(kubectl get pod fair-macvlan-server -n $NAMESPACE -o jsonpath='{.metadata.annotations.k8s\.v1\.cni\.cncf\.io/network-status}' | python3 -c "import sys,json; nets=json.load(sys.stdin); print([n['ips'][0] for n in nets if n['name']=='free5gc/fair-macvlan'][0])")
echo "  macvlan server IP: $MACVLAN_SERVER_IP"

echo "  소패킷 UDP 테스트 실행 (64B, ${DURATION}s)..."
kubectl exec -n $NAMESPACE fair-macvlan-client -- \
  iperf3 -c $MACVLAN_SERVER_IP -u -l 64 -b 0 -t $DURATION --json \
  > "${RESULTS_DIR}/fair-macvlan-udp64_${TIMESTAMP}.json" 2>/dev/null

echo "  macvlan 결과 저장 완료"

# 정리
kubectl delete pod fair-macvlan-server fair-macvlan-client -n $NAMESPACE --grace-period=0 --force 2>/dev/null
sleep 5

# ─── Phase 2: ipvlan 테스트 ───
echo ""
echo "[Phase 2] ipvlan 테스트"

cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: fair-ipvlan-server
  namespace: $NAMESPACE
  annotations:
    k8s.v1.cni.cncf.io/networks: fair-ipvlan
spec:
  containers:
  - name: iperf3
    image: networkstatic/iperf3:latest
    command: ["iperf3", "-s"]
    resources:
      requests:
        cpu: "500m"
        memory: "128Mi"
      limits:
        cpu: "500m"
        memory: "128Mi"
---
apiVersion: v1
kind: Pod
metadata:
  name: fair-ipvlan-client
  namespace: $NAMESPACE
  annotations:
    k8s.v1.cni.cncf.io/networks: fair-ipvlan
spec:
  containers:
  - name: iperf3
    image: networkstatic/iperf3:latest
    command: ["sleep", "infinity"]
    resources:
      requests:
        cpu: "500m"
        memory: "128Mi"
      limits:
        cpu: "500m"
        memory: "128Mi"
EOF

echo "  Pod 시작 대기..."
kubectl wait --for=condition=Ready pod/fair-ipvlan-server -n $NAMESPACE --timeout=60s
kubectl wait --for=condition=Ready pod/fair-ipvlan-client -n $NAMESPACE --timeout=60s

# ipvlan 서버 IP 가져오기 (annotation에서)
IPVLAN_SERVER_IP=$(kubectl get pod fair-ipvlan-server -n $NAMESPACE -o jsonpath='{.metadata.annotations.k8s\.v1\.cni\.cncf\.io/network-status}' | python3 -c "import sys,json; nets=json.load(sys.stdin); print([n['ips'][0] for n in nets if n['name']=='free5gc/fair-ipvlan'][0])")
echo "  ipvlan server IP: $IPVLAN_SERVER_IP"

echo "  소패킷 UDP 테스트 실행 (64B, ${DURATION}s)..."
kubectl exec -n $NAMESPACE fair-ipvlan-client -- \
  iperf3 -c $IPVLAN_SERVER_IP -u -l 64 -b 0 -t $DURATION --json \
  > "${RESULTS_DIR}/fair-ipvlan-udp64_${TIMESTAMP}.json" 2>/dev/null

echo "  ipvlan 결과 저장 완료"

# 정리
kubectl delete pod fair-ipvlan-server fair-ipvlan-client -n $NAMESPACE --grace-period=0 --force 2>/dev/null

# ─── 결과 요약 ───
echo ""
echo "=== 결과 요약 ==="
echo "macvlan:"
python3 -c "
import json
with open('${RESULTS_DIR}/fair-macvlan-udp64_${TIMESTAMP}.json') as f:
    d = json.load(f)
    s = d['end']['sum']
    print(f\"  Throughput: {s['bits_per_second']/1e6:.1f} Mbps\")
    print(f\"  Packets: {s['packets']}\")
    print(f\"  Lost: {s.get('lost_packets', 0)} ({s.get('lost_percent', 0):.2f}%)\")
" 2>/dev/null || echo "  (파싱 실패 — JSON 직접 확인 필요)"

echo "ipvlan:"
python3 -c "
import json
with open('${RESULTS_DIR}/fair-ipvlan-udp64_${TIMESTAMP}.json') as f:
    d = json.load(f)
    s = d['end']['sum']
    print(f\"  Throughput: {s['bits_per_second']/1e6:.1f} Mbps\")
    print(f\"  Packets: {s['packets']}\")
    print(f\"  Lost: {s.get('lost_packets', 0)} ({s.get('lost_percent', 0):.2f}%)\")
" 2>/dev/null || echo "  (파싱 실패 — JSON 직접 확인 필요)"

echo ""
echo "결과 파일:"
echo "  ${RESULTS_DIR}/fair-macvlan-udp64_${TIMESTAMP}.json"
echo "  ${RESULTS_DIR}/fair-ipvlan-udp64_${TIMESTAMP}.json"
