#!/bin/bash
# nwdaf-switch.sh — NWDAF AI 결정을 DRANET ResourceClaim으로 실행
#
# NWDAF가 "macvlan로 바꿔라" 또는 "ipvlan로 바꿔라" 결정을 내리면
# 이 스크립트가 ResourceClaim의 deviceClassName을 변경하여 전환 실행.
#
# 사용법:
#   ./nwdaf-switch.sh macvlan     # ipvlan → macvlan 전환
#   ./nwdaf-switch.sh ipvlan      # macvlan → ipvlan 전환
#   ./nwdaf-switch.sh status      # 현재 상태 확인
#
# 실제 NWDAF 연동 시에는 이 스크립트를 NWDAF의 decision output hook으로 호출.

set -euo pipefail

NAMESPACE="${NAMESPACE:-free5gc}"
CLAIM_NAME="${CLAIM_NAME:-upf-network}"
MONITOR_LOG="${MONITOR_LOG:-}"  # 모니터링 이벤트 마커 파일

log() { echo "[$(date '+%H:%M:%S')] [NWDAF-SWITCH] $1"; }

# ═══════════════════════════════════════════════════════
# 현재 상태 확인
# ═══════════════════════════════════════════════════════
get_current_backend() {
    kubectl get resourceclaim "$CLAIM_NAME" -n "$NAMESPACE" \
        -o jsonpath='{.spec.devices.requests[0].deviceClassName}' 2>/dev/null
}

show_status() {
    local current
    current=$(get_current_backend)
    echo ""
    echo "═══════════════════════════════════════"
    echo "  UPF Network Backend Status"
    echo "═══════════════════════════════════════"
    echo "  Claim:    $CLAIM_NAME"
    echo "  Current:  $current"
    echo "  Options:  net-ipvlan (low overhead)"
    echo "            net-macvlan (high performance)"
    echo "═══════════════════════════════════════"
    echo ""
}

# ═══════════════════════════════════════════════════════
# 전환 실행
# ═══════════════════════════════════════════════════════
switch_backend() {
    local target="$1"
    local device_class="net-${target}"
    local current
    current=$(get_current_backend)

    if [[ "$current" == "$device_class" ]]; then
        log "Already using $device_class. No change needed."
        return 0
    fi

    log "Switching: $current → $device_class"
    local switch_time
    switch_time=$(date -Iseconds)

    # ResourceClaim 패치
    kubectl patch resourceclaim "$CLAIM_NAME" -n "$NAMESPACE" --type='json' \
        -p="[
            {\"op\": \"replace\", \"path\": \"/spec/devices/requests/0/deviceClassName\", \"value\": \"$device_class\"},
            {\"op\": \"replace\", \"path\": \"/spec/devices/requests/1/deviceClassName\", \"value\": \"$device_class\"}
        ]"

    log "ResourceClaim patched. Waiting for DRANET to reconcile..."

    # DRANET이 실제 전환을 수행할 때까지 대기
    sleep 5

    # 전환 확인
    local new_backend
    new_backend=$(get_current_backend)
    if [[ "$new_backend" == "$device_class" ]]; then
        log "✓ Switch complete: $current → $new_backend"
    else
        log "✗ Switch may have failed. Current: $new_backend"
    fi

    # 모니터링 이벤트 마커 기록
    if [[ -n "$MONITOR_LOG" ]]; then
        printf '{"ts":"%s","event":"cni_switch","from":"%s","to":"%s"}\n' \
            "$switch_time" "$current" "$device_class" >> "$MONITOR_LOG"
        log "Event marker written to: $MONITOR_LOG"
    fi

    # 기본 monitor-data 에도 기록 (최신 run)
    local latest_run
    latest_run=$(ls -td /home/ubuntu/free5gc-k8s-arm/traffic-profiles/monitor-data/run_* 2>/dev/null | head -1)
    if [[ -n "$latest_run" ]]; then
        printf '{"ts":"%s","event":"cni_switch","from":"%s","to":"%s"}\n' \
            "$switch_time" "$current" "$device_class" >> "${latest_run}/events.jsonl"
    fi
}

# ═══════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════
main() {
    case "${1:-}" in
        macvlan|ipvlan)
            switch_backend "$1"
            ;;
        status)
            show_status
            ;;
        on)
            log "Enabling NWDAF Pod (scale replicas=1)"
            kubectl scale deployment/nwdaf -n "$NAMESPACE" --replicas=1
            kubectl wait --for=condition=ready pod -l nf=nwdaf -n "$NAMESPACE" --timeout=60s 2>/dev/null && \
                log "✓ NWDAF is ON" || log "⚠ NWDAF pod not ready yet"
            ;;
        off)
            log "Disabling NWDAF Pod (scale replicas=0)"
            kubectl scale deployment/nwdaf -n "$NAMESPACE" --replicas=0
            log "✓ NWDAF is OFF"
            ;;
        *)
            echo "Usage: $0 <macvlan|ipvlan|status|on|off>"
            echo ""
            echo "CNI Control:"
            echo "  $0 macvlan    # Switch to high-performance macvlan"
            echo "  $0 ipvlan     # Switch to low-overhead ipvlan"
            echo "  $0 status     # Show current backend"
            echo ""
            echo "NWDAF Control:"
            echo "  $0 on         # Enable NWDAF (scale replicas=1)"
            echo "  $0 off        # Disable NWDAF (scale replicas=0)"
            exit 1
            ;;
    esac
}

main "$@"
