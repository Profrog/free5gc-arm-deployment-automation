#!/bin/bash
# UE → RAN → Core 트래픽 연결 테스트
# 사용: ./test-connectivity.sh
set -e

NAMESPACE="free5gc"
PASS=0
FAIL=0

log() { echo "[$(date '+%H:%M:%S')] $1"; }
pass() { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

# ════════════════════════════════════════════
# 1. Pod 상태 확인
# ════════════════════════════════════════════
test_pods() {
    log "=== [1/5] Pod status ==="
    local not_running
    not_running=$(kubectl get pods -n "$NAMESPACE" --no-headers | grep -v "Running\|Completed" | wc -l)
    if [ "$not_running" -eq 0 ]; then
        pass "All pods Running"
    else
        fail "Some pods not Running:"
        kubectl get pods -n "$NAMESPACE" --no-headers | grep -v "Running\|Completed"
    fi
}

# ════════════════════════════════════════════
# 2. gNB NGAP 연결 확인 (N2: gNB → AMF)
# ════════════════════════════════════════════
test_gnb() {
    log "=== [2/5] gNB NGAP connection (N2) ==="
    local gnb_pod
    gnb_pod=$(kubectl get pod -n "$NAMESPACE" -l component=gnb -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [ -z "$gnb_pod" ]; then
        fail "gNB pod not found"; return
    fi

    local gnb_log
    gnb_log=$(kubectl logs -n "$NAMESPACE" "$gnb_pod" --tail=50 2>/dev/null)
    if echo "$gnb_log" | grep -qi "NG Setup procedure is successful\|ngap.*connected\|amf.*connected"; then
        pass "gNB connected to AMF via NGAP"
    else
        fail "gNB NGAP connection not confirmed"
    fi
}

# ════════════════════════════════════════════
# 3. UE 등록 확인
# ════════════════════════════════════════════
test_ue_registration() {
    log "=== [3/5] UE registration ==="
    local ue_pod
    ue_pod=$(kubectl get pod -n "$NAMESPACE" -l component=ue -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [ -z "$ue_pod" ]; then
        fail "UE pod not found"; return
    fi

    local ue_log
    ue_log=$(kubectl logs -n "$NAMESPACE" "$ue_pod" --tail=50 2>/dev/null)
    if echo "$ue_log" | grep -qi "Registration is successful\|registered\|PDU Session"; then
        pass "UE registered to core"
    else
        fail "UE registration not confirmed"
    fi
}

# ════════════════════════════════════════════
# 4. PDU Session / TUN 인터페이스 확인
# ════════════════════════════════════════════
test_pdu_session() {
    log "=== [4/5] PDU Session (uesimtun0) ==="
    local ue_pod
    ue_pod=$(kubectl get pod -n "$NAMESPACE" -l component=ue -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [ -z "$ue_pod" ]; then
        fail "UE pod not found"; return
    fi

    local tun
    tun=$(kubectl exec -n "$NAMESPACE" "$ue_pod" -- ip addr show uesimtun0 2>/dev/null)
    if [ -n "$tun" ]; then
        local ip
        ip=$(echo "$tun" | grep -oP 'inet \K[0-9.]+')
        pass "uesimtun0 UP (IP: $ip)"
    else
        fail "uesimtun0 not found"
    fi
}

# ════════════════════════════════════════════
# 5. End-to-end ping (UE → 인터넷 via UPF)
# ════════════════════════════════════════════
test_ping() {
    log "=== [5/5] End-to-end ping (UE → 8.8.8.8 via UPF) ==="
    local ue_pod
    ue_pod=$(kubectl get pod -n "$NAMESPACE" -l component=ue -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [ -z "$ue_pod" ]; then
        fail "UE pod not found"; return
    fi

    local result
    result=$(kubectl exec -n "$NAMESPACE" "$ue_pod" -- ping -I uesimtun0 -c 3 -W 5 8.8.8.8 2>&1)
    if echo "$result" | grep -q "bytes from"; then
        local rtt
        rtt=$(echo "$result" | grep "rtt\|round-trip" | head -1)
        pass "Ping successful ($rtt)"
    else
        # 내부 DNS로 대체 시도
        result=$(kubectl exec -n "$NAMESPACE" "$ue_pod" -- ping -I uesimtun0 -c 3 -W 5 10.10.3.1 2>&1)
        if echo "$result" | grep -q "bytes from"; then
            pass "Ping to UPF successful (외부 라우팅 미설정)"
        else
            fail "Ping failed"
            echo "    $result" | tail -3
        fi
    fi
}

# ════════════════════════════════════════════
# Main
# ════════════════════════════════════════════
echo ""
log "free5gc connectivity test: UE → gNB → UPF → Core"
echo ""

test_pods
test_gnb
test_ue_registration
test_pdu_session
test_ping

echo ""
echo "════════════════════════════════"
echo "  Results: $PASS passed, $FAIL failed"
echo "════════════════════════════════"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
