#!/bin/bash
# traffic-gen.sh — APN + Scenario 기반 트래픽 제네레이터
# 
# 사용법:
#   ./traffic-gen.sh --apn <apn.yaml> --scenario <scenario.yaml> [--dry-run]
#   ./traffic-gen.sh <merged-profile.yaml> [--dry-run]   # 레거시 호환
#
# APN 파일: 네트워크 정의 (DNN, Slice, UPF IP, UE Pool)
# Scenario 파일: 트래픽 패턴 (패킷크기, rate, duration, phases)
#
# 두 파일을 yq로 merge하여 실행합니다.
# 의존성: yq, iperf3, jq

set -euo pipefail

# ═══════════════════════════════════════════════════════
# 설정
# ═══════════════════════════════════════════════════════
APN_FILE=""
SCENARIO_FILE=""
PROFILE=""           # merged 결과 (또는 레거시 단일 파일)
DRY_RUN=""
TUN_IFACE="${TUN_IFACE:-uesimtun0}"
IPERF_SERVER="${IPERF_SERVER:-10.10.3.1}"
RESULT_DIR="${RESULT_DIR:-/results}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 파라미터 파싱
while [[ $# -gt 0 ]]; do
    case "$1" in
        --apn)      APN_FILE="$2"; shift 2 ;;
        --scenario) SCENARIO_FILE="$2"; shift 2 ;;
        --dry-run)  DRY_RUN="--dry-run"; shift ;;
        -*)         echo "Unknown option: $1" >&2; exit 1 ;;
        *)
            # 레거시: 단일 파일 모드
            if [[ -z "$PROFILE" ]]; then
                PROFILE="$1"
            elif [[ -z "$DRY_RUN" && "$1" == "--dry-run" ]]; then
                DRY_RUN="--dry-run"
            fi
            shift ;;
    esac
done

# APN + Scenario → merged profile 생성
if [[ -n "$APN_FILE" && -n "$SCENARIO_FILE" ]]; then
    [[ ! -f "$APN_FILE" ]] && { echo "ERROR: APN file not found: $APN_FILE" >&2; exit 1; }
    [[ ! -f "$SCENARIO_FILE" ]] && { echo "ERROR: Scenario file not found: $SCENARIO_FILE" >&2; exit 1; }

    # yq merge: APN을 base로, scenario를 overlay
    PROFILE="/tmp/merged_profile_${TIMESTAMP}.yaml"
    yq eval-all 'select(fileIndex == 0) * select(fileIndex == 1)' \
        "$APN_FILE" "$SCENARIO_FILE" > "$PROFILE"

    # APN의 dnn을 apn 필드로 복사 (호환성)
    local_apn=$(yq eval '.dnn' "$APN_FILE")
    yq eval -i ".apn = \"$local_apn\"" "$PROFILE"

    echo "[$(date '+%H:%M:%S')] Merged: $APN_FILE + $SCENARIO_FILE → $PROFILE"
elif [[ -z "$PROFILE" ]]; then
    echo "Usage: $0 --apn <apn.yaml> --scenario <scenario.yaml> [--dry-run]"
    echo "       $0 <profile.yaml> [--dry-run]"
    exit 1
fi

# ═══════════════════════════════════════════════════════
# 유틸리티
# ═══════════════════════════════════════════════════════
log()  { echo "[$(date '+%H:%M:%S')] $1"; }
die()  { echo "ERROR: $1" >&2; exit 1; }

check_deps() {
    local deps=(yq iperf3 jq)
    for d in "${deps[@]}"; do
        command -v "$d" &>/dev/null || die "$d not found. Install it first."
    done
}

# YAML 필드 읽기 헬퍼
yq_read() {
    yq eval "$1" "$PROFILE" 2>/dev/null
}

# 단위 변환: "50Mbps" → iperf3 형식 "50M"
parse_rate() {
    local rate="$1"
    # pps 형식은 별도 처리
    if [[ "$rate" == *pps ]]; then
        echo "$rate"
        return
    fi
    # bps 형식 → iperf3 compatible
    echo "$rate" | sed -E 's/([0-9]+)(Gbps|gbps)/\1G/; s/([0-9]+)(Mbps|mbps)/\1M/; s/([0-9]+)(Kbps|kbps)/\1K/'
}

# duration "120s" "5m" "1h" → seconds
parse_duration() {
    local dur="$1"
    if [[ "$dur" == *h ]]; then
        echo $(( ${dur%h} * 3600 ))
    elif [[ "$dur" == *m ]]; then
        echo $(( ${dur%m} * 60 ))
    else
        echo "${dur%s}"
    fi
}

# ═══════════════════════════════════════════════════════
# 프로파일 파싱
# ═══════════════════════════════════════════════════════
parse_profile() {
    log "Loading profile: $PROFILE"

    APN=$(yq_read '.apn')
    PROFILE_NAME=$(yq_read '.metadata.name')
    PROTOCOL=$(yq_read '.traffic_pattern.protocol')
    DIRECTION=$(yq_read '.traffic_pattern.direction')
    PACKET_SIZE=$(yq_read '.traffic_pattern.packet_size')
    RATE=$(yq_read '.traffic_pattern.rate')
    DURATION=$(yq_read '.traffic_pattern.duration')
    BURST_ENABLED=$(yq_read '.traffic_pattern.burst.enabled')
    BURST_PACKETS=$(yq_read '.traffic_pattern.burst.packets')
    BURST_INTERVAL=$(yq_read '.traffic_pattern.burst.interval')
    UE_COUNT=$(yq_read '.ue.count')
    JITTER=$(yq_read '.traffic_pattern.jitter')
    OUTPUT=$(yq_read '.measurement.output')
    METRIC_INTERVAL=$(yq_read '.measurement.interval')

    DURATION_SEC=$(parse_duration "$DURATION")
    RATE_PARSED=$(parse_rate "$RATE")

    log "  APN:       $APN"
    log "  Profile:   $PROFILE_NAME"
    log "  Protocol:  $PROTOCOL"
    log "  Direction: $DIRECTION"
    log "  Rate:      $RATE → $RATE_PARSED"
    log "  Duration:  $DURATION ($DURATION_SEC sec)"
    log "  UE Count:  $UE_COUNT"
    log "  Burst:     $BURST_ENABLED (${BURST_PACKETS}pkts / ${BURST_INTERVAL})"
}

# ═══════════════════════════════════════════════════════
# 트래픽 생성 — iperf3 기반 (TCP/UDP 고속)
# ═══════════════════════════════════════════════════════
gen_iperf3() {
    local proto_flag=""
    [[ "$PROTOCOL" == "udp" ]] && proto_flag="-u"

    local direction_flag=""
    [[ "$DIRECTION" == "downlink" ]] && direction_flag="-R"  # reverse (서버→클라이언트)

    local output_file="${RESULT_DIR}/${APN}_iperf3_${TIMESTAMP}.json"
    mkdir -p "$RESULT_DIR"

    log "Starting iperf3: $PROTOCOL $DIRECTION @ $RATE_PARSED for ${DURATION_SEC}s"

    local cmd="iperf3 -c $IPERF_SERVER \
        --bind-dev $TUN_IFACE \
        $proto_flag \
        $direction_flag \
        -b $RATE_PARSED \
        -l $PACKET_SIZE \
        -t $DURATION_SEC \
        -P $UE_COUNT \
        -i ${METRIC_INTERVAL%s} \
        -J"

    if [[ "$DRY_RUN" == "--dry-run" ]]; then
        log "[DRY-RUN] $cmd > $output_file"
    else
        eval "$cmd" > "$output_file" 2>&1 || true
        log "Results saved: $output_file"
    fi
}

# ═══════════════════════════════════════════════════════
# 트래픽 생성 — UDP burst 패턴 (IoT 시나리오)
# ═══════════════════════════════════════════════════════
gen_burst_udp() {
    local output_file="${RESULT_DIR}/${APN}_burst_${TIMESTAMP}.json"
    mkdir -p "$RESULT_DIR"

    local burst_interval_sec
    burst_interval_sec=$(parse_duration "$BURST_INTERVAL")
    local iterations=$(( DURATION_SEC / burst_interval_sec ))

    log "Starting UDP burst: ${BURST_PACKETS} pkts every ${BURST_INTERVAL} × ${iterations} iterations"

    if [[ "$DRY_RUN" == "--dry-run" ]]; then
        log "[DRY-RUN] Will send $BURST_PACKETS UDP packets of ${PACKET_SIZE}B every ${burst_interval_sec}s for ${iterations} rounds"
        return
    fi

    local results=()
    for ((i=1; i<=iterations; i++)); do
        local ts_start=$(date +%s%N)

        # nping으로 UDP burst 전송
        if command -v nping &>/dev/null; then
            nping --udp -p 5001 \
                --source-ip "$(ip -4 addr show "$TUN_IFACE" | grep -oP 'inet \K[0-9.]+')" \
                --data-length "$PACKET_SIZE" \
                -c "$BURST_PACKETS" \
                --delay 0 \
                "$IPERF_SERVER" 2>/dev/null
        else
            # fallback: dd + socat
            for ((p=0; p<BURST_PACKETS; p++)); do
                dd if=/dev/urandom bs="$PACKET_SIZE" count=1 2>/dev/null | \
                    socat - "UDP4:${IPERF_SERVER}:5001,bind=${TUN_IFACE}" 2>/dev/null || true
            done
        fi

        local ts_end=$(date +%s%N)
        local elapsed_ms=$(( (ts_end - ts_start) / 1000000 ))
        results+=("{\"round\":$i,\"elapsed_ms\":$elapsed_ms,\"packets\":$BURST_PACKETS}")

        log "  Burst $i/$iterations done (${elapsed_ms}ms)"

        # 다음 burst까지 대기
        if ((i < iterations)); then
            sleep "$burst_interval_sec"
        fi
    done

    # JSON 결과 저장
    printf '{"profile":"%s","apn":"%s","bursts":[%s]}\n' \
        "$PROFILE_NAME" "$APN" "$(IFS=,; echo "${results[*]}")" > "$output_file"
    log "Results saved: $output_file"
}

# ═══════════════════════════════════════════════════════
# 트래픽 생성 — 고정 PPS (VoNR 시나리오)
# ═══════════════════════════════════════════════════════
gen_fixed_pps() {
    local output_file="${RESULT_DIR}/${APN}_pps_${TIMESTAMP}.json"
    mkdir -p "$RESULT_DIR"

    local pps="${RATE_PARSED%pps}"
    local interval_us=$(( 1000000 / pps ))  # 패킷 간 간격 (μs)

    log "Starting fixed-PPS: ${pps} pps × ${PACKET_SIZE}B for ${DURATION_SEC}s (${DIRECTION})"

    if [[ "$DRY_RUN" == "--dry-run" ]]; then
        log "[DRY-RUN] iperf3 UDP @ ${pps}pps = $((pps * PACKET_SIZE * 8))bps"
        return
    fi

    # iperf3로 정확한 bitrate 계산 (pps × packet_size × 8)
    local target_bps=$(( pps * PACKET_SIZE * 8 ))
    local target_rate
    if ((target_bps >= 1000000)); then
        target_rate="$((target_bps / 1000000))M"
    elif ((target_bps >= 1000)); then
        target_rate="$((target_bps / 1000))K"
    else
        target_rate="${target_bps}"
    fi

    local direction_flag=""
    [[ "$DIRECTION" == "downlink" ]] && direction_flag="-R"
    [[ "$DIRECTION" == "bidirectional" ]] && direction_flag="--bidir"

    iperf3 -c "$IPERF_SERVER" \
        --bind-dev "$TUN_IFACE" \
        -u \
        $direction_flag \
        -b "$target_rate" \
        -l "$PACKET_SIZE" \
        -t "$DURATION_SEC" \
        -P "$UE_COUNT" \
        -i "${METRIC_INTERVAL%s}" \
        -J > "$output_file" 2>&1 || true

    log "Results saved: $output_file"
}

# ═══════════════════════════════════════════════════════
# 결과 요약 출력
# ═══════════════════════════════════════════════════════
print_summary() {
    local output_file="${RESULT_DIR}/${APN}_*_${TIMESTAMP}.json"
    local latest
    latest=$(ls -t ${RESULT_DIR}/${APN}_*_${TIMESTAMP}.json 2>/dev/null | head -1)

    if [[ -z "$latest" || "$DRY_RUN" == "--dry-run" ]]; then
        return
    fi

    echo ""
    echo "═══════════════════════════════════════════"
    echo "  Profile:   $PROFILE_NAME ($APN)"
    echo "  Duration:  ${DURATION_SEC}s"
    echo "  File:      $latest"
    echo "═══════════════════════════════════════════"

    # iperf3 JSON에서 요약 추출
    if jq -e '.end.sum_sent' "$latest" &>/dev/null; then
        echo ""
        echo "  Throughput (sent):     $(jq -r '.end.sum_sent.bits_per_second / 1000000 | floor' "$latest") Mbps"
        echo "  Throughput (received): $(jq -r '.end.sum_received.bits_per_second / 1000000 | floor' "$latest") Mbps"
        if jq -e '.end.sum.jitter_ms' "$latest" &>/dev/null; then
            echo "  Jitter:                $(jq -r '.end.sum.jitter_ms' "$latest") ms"
            echo "  Packet Loss:           $(jq -r '.end.sum.lost_percent' "$latest")%"
        fi
    fi
    echo ""
}

# ═══════════════════════════════════════════════════════
# 멀티페이즈 실행 (upf-stress 등 phases 배열 지원)
# ═══════════════════════════════════════════════════════
run_phases() {
    local phase_count
    phase_count=$(yq_read '.phases | length')

    log "Multi-phase profile detected: $phase_count phases"
    echo ""

    for ((idx=0; idx<phase_count; idx++)); do
        local phase_name phase_desc phase_proto phase_dir phase_pktsize phase_rate phase_dur
        phase_name=$(yq_read ".phases[$idx].name")
        phase_desc=$(yq_read ".phases[$idx].description")
        phase_proto=$(yq_read ".phases[$idx].traffic_pattern.protocol")
        phase_dir=$(yq_read ".phases[$idx].traffic_pattern.direction")
        phase_pktsize=$(yq_read ".phases[$idx].traffic_pattern.packet_size")
        phase_rate=$(yq_read ".phases[$idx].traffic_pattern.rate")
        phase_dur=$(yq_read ".phases[$idx].traffic_pattern.duration")

        echo ""
        log "━━━ Phase $((idx+1))/$phase_count: $phase_name ━━━"
        log "  $phase_desc"
        echo ""

        # rate_steps가 있으면 stepped load 실행
        local has_steps
        has_steps=$(yq_read ".phases[$idx].traffic_pattern.rate_steps | length" 2>/dev/null)

        if [[ "$has_steps" != "null" && "$has_steps" -gt 0 ]]; then
            run_stepped_load "$idx" "$has_steps" "$phase_proto" "$phase_dir" "$phase_pktsize"
        else
            # 단일 rate 실행
            local rate_parsed dur_sec direction_flag proto_flag
            rate_parsed=$(parse_rate "$phase_rate")
            dur_sec=$(parse_duration "$phase_dur")

            proto_flag=""
            [[ "$phase_proto" == "udp" ]] && proto_flag="-u"

            direction_flag=""
            [[ "$phase_dir" == "downlink" ]] && direction_flag="-R"
            [[ "$phase_dir" == "bidirectional" ]] && direction_flag="--bidir"

            local output_file="${RESULT_DIR}/${APN}_${phase_name}_${TIMESTAMP}.json"

            local cmd="iperf3 -c $IPERF_SERVER \
                --bind-dev $TUN_IFACE \
                $proto_flag \
                $direction_flag \
                -b $rate_parsed \
                -l $phase_pktsize \
                -t $dur_sec \
                -i 1 \
                -J"

            if [[ "$DRY_RUN" == "--dry-run" ]]; then
                log "[DRY-RUN] $cmd > $output_file"
            else
                log "Running: $phase_proto $phase_dir @ $rate_parsed, ${phase_pktsize}B, ${dur_sec}s"
                eval "$cmd" > "$output_file" 2>&1 || true
                log "Results: $output_file"

                # 간단 요약 출력
                if jq -e '.end' "$output_file" &>/dev/null; then
                    local sent recv loss
                    sent=$(jq -r '.end.sum_sent.bits_per_second // .end.sum.bits_per_second // 0 | . / 1000000 | floor' "$output_file" 2>/dev/null)
                    recv=$(jq -r '.end.sum_received.bits_per_second // 0 | . / 1000000 | floor' "$output_file" 2>/dev/null)
                    loss=$(jq -r '.end.sum.lost_percent // "N/A"' "$output_file" 2>/dev/null)
                    log "  → Sent: ${sent}Mbps | Received: ${recv}Mbps | Loss: ${loss}%"
                fi
            fi
        fi

        # 페이즈 간 5초 쿨다운
        if ((idx < phase_count - 1)) && [[ "$DRY_RUN" != "--dry-run" ]]; then
            log "Cooldown 5s..."
            sleep 5
        fi
    done
}

# ═══════════════════════════════════════════════════════
# Stepped load: rate_steps 배열을 순차적으로 실행
# ═══════════════════════════════════════════════════════
run_stepped_load() {
    local phase_idx="$1" step_count="$2" proto="$3" dir="$4" pktsize="$5"
    local step_dur
    step_dur=$(yq_read ".phases[$phase_idx].traffic_pattern.step_duration")
    local step_dur_sec
    step_dur_sec=$(parse_duration "$step_dur")

    local proto_flag="" direction_flag=""
    [[ "$proto" == "udp" ]] && proto_flag="-u"
    [[ "$dir" == "downlink" ]] && direction_flag="-R"
    [[ "$dir" == "bidirectional" ]] && direction_flag="--bidir"

    local phase_name
    phase_name=$(yq_read ".phases[$phase_idx].name")

    for ((s=0; s<step_count; s++)); do
        local step_rate
        step_rate=$(yq_read ".phases[$phase_idx].traffic_pattern.rate_steps[$s]")
        local rate_parsed
        rate_parsed=$(parse_rate "$step_rate")

        local output_file="${RESULT_DIR}/${APN}_${phase_name}_step${s}_${TIMESTAMP}.json"

        log "  Step $((s+1))/$step_count: $step_rate for ${step_dur_sec}s"

        local cmd="iperf3 -c $IPERF_SERVER \
            --bind-dev $TUN_IFACE \
            $proto_flag \
            $direction_flag \
            -b $rate_parsed \
            -l $pktsize \
            -t $step_dur_sec \
            -i 1 \
            -J"

        if [[ "$DRY_RUN" == "--dry-run" ]]; then
            log "  [DRY-RUN] $cmd"
        else
            eval "$cmd" > "$output_file" 2>&1 || true

            # 요약
            if jq -e '.end' "$output_file" &>/dev/null; then
                local recv loss
                recv=$(jq -r '.end.sum_received.bits_per_second // .end.sum.bits_per_second // 0 | . / 1000000 | floor' "$output_file" 2>/dev/null)
                loss=$(jq -r '.end.sum.lost_percent // "N/A"' "$output_file" 2>/dev/null)
                log "    → Received: ${recv}Mbps | Loss: ${loss}%"
            fi
        fi
    done
}

# ═══════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════
main() {
    [[ -z "$PROFILE" ]] && die "Usage: $0 <profile.yaml> [--dry-run]"
    [[ ! -f "$PROFILE" ]] && die "Profile not found: $PROFILE"

    check_deps
    parse_profile

    echo ""
    log "════════════ Traffic Generation Start ════════════"
    echo ""

    # 실행 전 TUN 인터페이스 확인
    if [[ "$DRY_RUN" != "--dry-run" ]]; then
        if ! ip link show "$TUN_IFACE" &>/dev/null; then
            die "Interface $TUN_IFACE not found. Is UE registered?"
        fi
    fi

    # phases 배열이 있으면 멀티페이즈 실행
    local has_phases
    has_phases=$(yq_read '.phases | length' 2>/dev/null)

    if [[ "$has_phases" != "null" && "$has_phases" -gt 0 ]]; then
        run_phases
    elif [[ "$BURST_ENABLED" == "true" ]]; then
        gen_burst_udp
    elif [[ "$RATE" == *pps ]]; then
        gen_fixed_pps
    else
        gen_iperf3
    fi

    print_summary
    log "════════════ Traffic Generation Done ════════════"
}

main "$@"
