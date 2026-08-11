#!/bin/bash
# monitor-collector.sh — Pod별 리소스 & 패킷로스 주기적 수집기
#
# monitoring-eyes 패턴 차용:
#   - Cron 기반 주기적 수집
#   - File-based 시계열 저장 (test_run/pod별 JSON)
#   - KPI: CPU(millicores), Memory(Mi), PacketLoss(%)
#
# 사용법:
#   ./monitor-collector.sh [--interval 5] [--duration 120] [--output-dir ./results]
#   ./monitor-collector.sh --background   # 백그라운드 실행
#
# 의존성: kubectl, jq

set -uo pipefail

# ═══════════════════════════════════════════════════════
# 설정
# ═══════════════════════════════════════════════════════
NAMESPACE="${NAMESPACE:-free5gc}"
INTERVAL="${INTERVAL:-5}"                    # 수집 주기 (초)
DURATION="${DURATION:-0}"                    # 0 = 무한 (외부 종료까지)
OUTPUT_DIR="${OUTPUT_DIR:-}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d_%H%M%S)}"
BACKGROUND=false
PID_FILE="/tmp/monitor-collector.pid"

# 모니터링 대상 Pod label
TARGET_PODS=(
    "nf=upf"
    "nf=smf"
    "nf=amf"
    "nf=nrf"
    "nf=ausf"
    "nf=udm"
    "nf=udr"
    "nf=pcf"
    "nf=nssf"
    "component=gnb"
    "component=ue"
    "component=iperf3-server"
    "component=traffic-generator"
)

# ═══════════════════════════════════════════════════════
# 유틸리티
# ═══════════════════════════════════════════════════════
log()  { echo "[$(date '+%H:%M:%S')] $1"; }
die()  { echo "ERROR: $1" >&2; exit 1; }

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --interval)   INTERVAL="$2"; shift 2 ;;
            --duration)   DURATION="$2"; shift 2 ;;
            --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
            --run-id)     RUN_ID="$2"; shift 2 ;;
            --background) BACKGROUND=true; shift ;;
            --stop)       stop_collector; exit 0 ;;
            -h|--help)    usage; exit 0 ;;
            *)            die "Unknown option: $1" ;;
        esac
    done

    # 출력 디렉토리 기본값
    if [[ -z "$OUTPUT_DIR" ]]; then
        SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
        OUTPUT_DIR="${SCRIPT_DIR}/monitor-data/${RUN_ID}"
    fi
}

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --interval N     수집 주기 (초, default: 5)"
    echo "  --duration N     총 수집 시간 (초, 0=무한, default: 0)"
    echo "  --output-dir DIR 출력 디렉토리"
    echo "  --run-id ID      실행 식별자 (default: timestamp)"
    echo "  --background     백그라운드 실행"
    echo "  --stop           실행 중인 collector 중지"
}

stop_collector() {
    if [[ -f "$PID_FILE" ]]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
            log "Collector stopped (PID: $pid)"
        fi
        rm -f "$PID_FILE"
    else
        log "No running collector found"
    fi
}

# ═══════════════════════════════════════════════════════
# 데이터 수집 함수
# ═══════════════════════════════════════════════════════

# Per-CPU 사용량 수집 (/proc/stat 기반)
# 실험 격리 검증용: core별 사용량을 기록하여 UPF 코어와 시스템 코어 분리 확인
collect_per_cpu() {
    local timestamp="$1"
    local cpu_dir="${OUTPUT_DIR}/system"
    mkdir -p "$cpu_dir"

    # /proc/stat에서 per-CPU 시계열 읽기
    # 형식: cpuN user nice system idle iowait irq softirq steal
    local cpu_data
    cpu_data=$(grep "^cpu[0-9]" /proc/stat)

    # JSONL로 기록
    local json_line="{\"ts\":\"$timestamp\""
    while IFS= read -r line; do
        local cpu_id user nice system idle
        cpu_id=$(echo "$line" | awk '{print $1}')
        user=$(echo "$line" | awk '{print $2}')
        nice=$(echo "$line" | awk '{print $3}')
        system=$(echo "$line" | awk '{print $4}')
        idle=$(echo "$line" | awk '{print $5}')
        local total=$((user + nice + system + idle))
        local busy=$((user + nice + system))
        json_line="${json_line},\"${cpu_id}_busy\":${busy},\"${cpu_id}_total\":${total}"
    done <<< "$cpu_data"
    json_line="${json_line}}"

    echo "$json_line" >> "${cpu_dir}/per_cpu.jsonl"
}

# kubectl top pods → CPU(m), Memory(Mi) 추출
collect_resource_usage() {
    local timestamp="$1"

    # kubectl top pods - 전체 namespace
    local top_output
    top_output=$(kubectl top pods -n "$NAMESPACE" --no-headers 2>/dev/null) || return 1

    echo "$top_output" | while IFS= read -r line; do
        local pod_name cpu_raw mem_raw
        pod_name=$(echo "$line" | awk '{print $1}')
        cpu_raw=$(echo "$line" | awk '{print $2}')   # e.g., "23m" or "1234m"
        mem_raw=$(echo "$line" | awk '{print $3}')   # e.g., "45Mi" or "1234Mi"

        # CPU: "23m" → 23, "2" → 2000
        local cpu_milli
        if [[ "$cpu_raw" == *m ]]; then
            cpu_milli="${cpu_raw%m}"
        else
            cpu_milli=$(( ${cpu_raw} * 1000 ))
        fi

        # Memory: "45Mi" → 45, "1Gi" → 1024
        local mem_mi
        if [[ "$mem_raw" == *Gi ]]; then
            mem_mi=$(( ${mem_raw%Gi} * 1024 ))
        elif [[ "$mem_raw" == *Mi ]]; then
            mem_mi="${mem_raw%Mi}"
        elif [[ "$mem_raw" == *Ki ]]; then
            mem_mi=$(( ${mem_raw%Ki} / 1024 ))
        else
            mem_mi="$mem_raw"
        fi

        # Pod 디렉토리에 저장
        local pod_dir="${OUTPUT_DIR}/pods/${pod_name}"
        mkdir -p "$pod_dir"

        # 시계열 JSONL append
        printf '{"ts":"%s","cpu_milli":%s,"mem_mi":%s}\n' \
            "$timestamp" "$cpu_milli" "$mem_mi" >> "${pod_dir}/resources.jsonl"
    done
}

# UPF Pod의 패킷 로스 계산
# monitoring-eyes의 ratio 방식 차용: (dropped / total_recv) * 100
collect_packet_loss() {
    local timestamp="$1"

    # UPF Pod 찾기
    local upf_pods
    upf_pods=$(kubectl get pods -n "$NAMESPACE" -l nf=upf -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)

    for upf_pod in $upf_pods; do
        local pod_dir="${OUTPUT_DIR}/pods/${upf_pod}"
        mkdir -p "$pod_dir"

        # N3(gtpu) 인터페이스 통계 수집
        local iface_stats
        iface_stats=$(kubectl exec -n "$NAMESPACE" "$upf_pod" -c upf -- \
            cat /proc/net/dev 2>/dev/null) || continue

        # n3 또는 n3i 인터페이스 찾기 (실제 데이터플레인 트래픽 경로)
        # 현재 활성 CNI에 따라 n3(macvlan) 또는 n3i(ipvlan)에 패킷이 흐름
        local gtp_line
        gtp_line=$(echo "$iface_stats" | grep -E "^\s*(n3|n3i):" | head -1)
        # n3이 트래픽 있으면 n3, 없으면 n3i
        local n3_rx=$(echo "$iface_stats" | grep -E "^\s*n3:" | awk '{print $3}')
        local n3i_rx=$(echo "$iface_stats" | grep -E "^\s*n3i:" | awk '{print $3}')
        if [[ "${n3_rx:-0}" -gt "${n3i_rx:-0}" ]]; then
            gtp_line=$(echo "$iface_stats" | grep -E "^\s*n3:" | head -1)
        else
            gtp_line=$(echo "$iface_stats" | grep -E "^\s*n3i:" | head -1)
        fi

        if [[ -n "$gtp_line" ]]; then
            # /proc/net/dev format:
            # iface: rx_bytes rx_packets rx_errs rx_drop ... tx_bytes tx_packets tx_errs tx_drop ...
            local rx_packets rx_drop tx_packets tx_drop
            rx_packets=$(echo "$gtp_line" | awk '{print $3}')
            rx_drop=$(echo "$gtp_line" | awk '{print $5}')
            tx_packets=$(echo "$gtp_line" | awk '{print $11}')
            tx_drop=$(echo "$gtp_line" | awk '{print $13}')

            # Loss rate 계산
            local total_packets=$((rx_packets + tx_packets))
            local total_drop=$((rx_drop + tx_drop))
            local loss_pct="0.0"
            if [[ "$total_packets" -gt 0 ]]; then
                loss_pct=$(awk "BEGIN {printf \"%.4f\", ($total_drop / $total_packets) * 100}")
            fi

            printf '{"ts":"%s","rx_packets":%s,"rx_drop":%s,"tx_packets":%s,"tx_drop":%s,"loss_pct":%s}\n' \
                "$timestamp" "$rx_packets" "$rx_drop" "$tx_packets" "$tx_drop" "$loss_pct" \
                >> "${pod_dir}/packet_loss.jsonl"
        fi

        # eth0 통계도 수집 (N6 방향)
        local eth_line
        eth_line=$(echo "$iface_stats" | grep "eth0" | head -1)
        if [[ -n "$eth_line" ]]; then
            local eth_rx_pkt eth_rx_drop eth_tx_pkt eth_tx_drop
            eth_rx_pkt=$(echo "$eth_line" | awk '{print $3}')
            eth_rx_drop=$(echo "$eth_line" | awk '{print $5}')
            eth_tx_pkt=$(echo "$eth_line" | awk '{print $11}')
            eth_tx_drop=$(echo "$eth_line" | awk '{print $13}')

            printf '{"ts":"%s","iface":"eth0","rx_packets":%s,"rx_drop":%s,"tx_packets":%s,"tx_drop":%s}\n' \
                "$timestamp" "$eth_rx_pkt" "$eth_rx_drop" "$eth_tx_pkt" "$eth_tx_drop" \
                >> "${pod_dir}/iface_stats.jsonl"
        fi
    done
}

# iperf3 Job Pod에서 실시간 throughput 뽑기 (가능한 경우)
collect_traffic_gen_stats() {
    local timestamp="$1"

    local gen_pod
    gen_pod=$(kubectl get pods -n "$NAMESPACE" -l component=traffic-generator \
        --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [[ -n "$gen_pod" ]]; then
        local pod_dir="${OUTPUT_DIR}/pods/${gen_pod}"
        mkdir -p "$pod_dir"

        # Pod 상태 기록
        local phase
        phase=$(kubectl get pod -n "$NAMESPACE" "$gen_pod" -o jsonpath='{.status.phase}' 2>/dev/null)
        printf '{"ts":"%s","phase":"%s"}\n' "$timestamp" "$phase" \
            >> "${pod_dir}/status.jsonl"
    fi
}

# ═══════════════════════════════════════════════════════
# 메타데이터 저장
# ═══════════════════════════════════════════════════════
save_metadata() {
    mkdir -p "$OUTPUT_DIR"

    cat > "${OUTPUT_DIR}/metadata.json" <<EOF
{
    "run_id": "${RUN_ID}",
    "namespace": "${NAMESPACE}",
    "interval_sec": ${INTERVAL},
    "duration_sec": ${DURATION},
    "start_time": "$(date -Iseconds)",
    "node": "$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo 'unknown')",
    "k8s_version": "$(kubectl version --short 2>/dev/null | grep Server | awk '{print $3}' || echo 'unknown')",
    "pods_monitored": $(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l),
    "collector_version": "1.0"
}
EOF
    log "Metadata saved: ${OUTPUT_DIR}/metadata.json"
}

# ═══════════════════════════════════════════════════════
# 메인 수집 루프
# ═══════════════════════════════════════════════════════
collection_loop() {
    local start_time=$(date +%s)
    local sample_count=0

    log "Starting collection loop (interval: ${INTERVAL}s, duration: ${DURATION}s)"
    log "Output: ${OUTPUT_DIR}"

    while true; do
        local now=$(date +%s)
        local timestamp=$(date -Iseconds)

        # Duration 체크 (0이면 무한)
        if [[ "$DURATION" -gt 0 ]]; then
            local elapsed=$((now - start_time))
            if [[ "$elapsed" -ge "$DURATION" ]]; then
                log "Duration reached (${DURATION}s). Stopping."
                break
            fi
        fi

        # 수집 실행
        collect_resource_usage "$timestamp"
        collect_packet_loss "$timestamp"
        collect_traffic_gen_stats "$timestamp"
        collect_per_cpu "$timestamp"

        sample_count=$((sample_count + 1))

        # 10회마다 상태 출력
        if ((sample_count % 10 == 0)); then
            log "Collected $sample_count samples (elapsed: $((now - start_time))s)"
        fi

        sleep "$INTERVAL"
    done

    local end_time=$(date -Iseconds)
    log "Collection finished. Total samples: $sample_count"

    # 종료 시간 메타데이터 업데이트
    local tmp
    tmp=$(mktemp)
    jq --arg end "$end_time" --argjson samples "$sample_count" \
        '.end_time = $end | .total_samples = $samples' \
        "${OUTPUT_DIR}/metadata.json" > "$tmp" && mv "$tmp" "${OUTPUT_DIR}/metadata.json"
}

# ═══════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════
main() {
    parse_args "$@"

    # 사전 체크
    command -v kubectl &>/dev/null || die "kubectl not found"
    command -v jq &>/dev/null || die "jq not found"
    kubectl get ns "$NAMESPACE" &>/dev/null || die "Namespace '$NAMESPACE' not found"

    # 출력 디렉토리 생성
    mkdir -p "${OUTPUT_DIR}/pods"

    # 메타데이터 저장
    save_metadata

    if [[ "$BACKGROUND" == true ]]; then
        log "Starting in background..."
        collection_loop &
        local bg_pid=$!
        echo "$bg_pid" > "$PID_FILE"
        log "Background PID: $bg_pid (stop with: $0 --stop)"
    else
        # foreground 실행 — Ctrl+C로 종료
        trap 'log "Interrupted. Finalizing..."; break' INT TERM
        collection_loop
    fi
}

main "$@"
