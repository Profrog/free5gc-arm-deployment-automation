#!/bin/bash
# nwdaf-switch.sh — 무중단 CNI 백엔드 전환 (IP 이동 방식)
#
# UPF Pod에 macvlan(n3/n4)과 ipvlan(n3i/n4i)이 동시에 attach되어 있으며,
# IP 주소를 인터페이스 간 이동하여 Pod/프로세스 재시작 없이 전환한다.
#
# 사용법:
#   ./nwdaf-switch.sh macvlan     # ipvlan → macvlan 전환
#   ./nwdaf-switch.sh ipvlan      # macvlan → ipvlan 전환
#   ./nwdaf-switch.sh status      # 현재 상태 확인
#
# 환경변수:
#   NAMESPACE    — K8s namespace (default: free5gc)
#   N3_IP        — N3 인터페이스 IP (default: 10.10.3.1/24)
#   N4_IP        — N4 인터페이스 IP (default: 10.10.4.1/24)

set -euo pipefail

NAMESPACE="${NAMESPACE:-free5gc}"
N3_IP="${N3_IP:-10.10.3.1/24}"
N4_IP="${N4_IP:-10.10.4.1/24}"

# 인터페이스 매핑
MACVLAN_N3="n3"
MACVLAN_N4="n4"
IPVLAN_N3="n3i"
IPVLAN_N4="n4i"

log() { echo "[$(date '+%H:%M:%S.%3N')] [NWDAF-SWITCH] $1"; }

# ═══════════════════════════════════════════════════════
# UPF Pod 찾기
# ═══════════════════════════════════════════════════════
get_upf_pod() {
    kubectl -n "$NAMESPACE" get pods -l nf=upf,name=upf \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
}

# ═══════════════════════════════════════════════════════
# 현재 상태 확인 — IP가 어느 인터페이스에 있는지
# ═══════════════════════════════════════════════════════
get_current_backend() {
    local pod
    pod=$(get_upf_pod)
    if [[ -z "$pod" ]]; then
        echo "unknown"
        return
    fi

    local n3_has_ip
    n3_has_ip=$(kubectl -n "$NAMESPACE" exec "$pod" -- \
        ip addr show dev "$MACVLAN_N3" 2>/dev/null | grep -c "${N3_IP%%/*}" || true)

    if [[ "$n3_has_ip" -gt 0 ]]; then
        echo "macvlan"
    else
        echo "ipvlan"
    fi
}

show_status() {
    local current pod
    current=$(get_current_backend)
    pod=$(get_upf_pod)
    echo ""
    echo "═══════════════════════════════════════"
    echo "  UPF Network Backend Status"
    echo "═══════════════════════════════════════"
    echo "  Pod:      $pod"
    echo "  Current:  $current"
    echo "  N3 IP:    $N3_IP"
    echo "  N4 IP:    $N4_IP"
    echo ""
    echo "  Interfaces:"
    echo "    macvlan: $MACVLAN_N3 / $MACVLAN_N4 (on n3br/n4br)"
    echo "    ipvlan:  $IPVLAN_N3 / $IPVLAN_N4 (on n3br-ipv/n4br-ipv)"
    echo "═══════════════════════════════════════"
    echo ""
}

# ═══════════════════════════════════════════════════════
# 전환 실행 — IP 이동 (밀리초 단위, 무중단)
# ═══════════════════════════════════════════════════════
switch_backend() {
    local target="$1"
    local pod current

    pod=$(get_upf_pod)
    if [[ -z "$pod" ]]; then
        log "ERROR: UPF pod not found"
        exit 1
    fi

    current=$(get_current_backend)
    if [[ "$current" == "$target" ]]; then
        log "Already on $target, no switch needed"
        return 0
    fi

    log "Switching: $current → $target"
    log "Pod: $pod"

    local start_time end_time elapsed
    start_time=$(date +%s%N)

    if [[ "$target" == "ipvlan" ]]; then
        # macvlan → ipvlan: IP를 n3/n4에서 n3i/n4i로 이동 (atomic batch)
        kubectl -n "$NAMESPACE" exec "$pod" -- sh -c "
            ip -batch - <<EOF
addr del $N3_IP dev $MACVLAN_N3
addr add $N3_IP dev $IPVLAN_N3
addr del $N4_IP dev $MACVLAN_N4
addr add $N4_IP dev $IPVLAN_N4
EOF
        " 2>/dev/null

    elif [[ "$target" == "macvlan" ]]; then
        # ipvlan → macvlan: IP를 n3i/n4i에서 n3/n4로 이동 (atomic batch)
        kubectl -n "$NAMESPACE" exec "$pod" -- sh -c "
            ip -batch - <<EOF
addr del $N3_IP dev $IPVLAN_N3
addr add $N3_IP dev $MACVLAN_N3
addr del $N4_IP dev $IPVLAN_N4
addr add $N4_IP dev $MACVLAN_N4
EOF
        " 2>/dev/null

    else
        log "ERROR: Unknown target '$target'. Use 'macvlan' or 'ipvlan'."
        exit 1
    fi

    end_time=$(date +%s%N)
    elapsed=$(( (end_time - start_time) / 1000000 ))

    log "Switch complete: $current → $target (${elapsed}ms)"

    # 검증
    local verify
    verify=$(get_current_backend)
    if [[ "$verify" == "$target" ]]; then
        log "Verified: now on $target ✓"
    else
        log "WARNING: verification failed, expected=$target actual=$verify"
        exit 1
    fi

    return 0
}

# ═══════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════
case "${1:-status}" in
    macvlan|ipvlan)
        switch_backend "$1"
        ;;
    status)
        show_status
        ;;
    *)
        echo "Usage: $0 {macvlan|ipvlan|status}"
        echo ""
        echo "  macvlan  — Switch to macvlan (high throughput, large packets)"
        echo "  ipvlan   — Switch to ipvlan (low overhead, high PPS)"
        echo "  status   — Show current backend"
        exit 1
        ;;
esac
