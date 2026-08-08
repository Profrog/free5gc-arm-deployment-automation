#!/bin/bash
# run.sh — APN 프로파일 트래픽 테스트 런처
#
# 사용법:
#   ./run.sh profiles/internet.yaml          # 단일 프로파일 실행
#   ./run.sh --all                           # profiles/ 아래 전체 순차 실행
#   ./run.sh profiles/vonr.yaml --dry-run    # 드라이런 (배포 미실행)
#   ./run.sh --status                        # 현재 Job 상태 확인
#   ./run.sh --collect                       # 결과 수집
#   ./run.sh --clean                         # Job/ConfigMap 정리

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NAMESPACE="${NAMESPACE:-free5gc}"
RESULT_LOCAL_DIR="${SCRIPT_DIR}/results"
JOB_NAME="traffic-gen"
TIMEOUT="${TIMEOUT:-600}"  # Job 완료 대기 시간 (초)
MONITOR_INTERVAL="${MONITOR_INTERVAL:-5}"  # 모니터링 수집 주기 (초)
MONITOR_PID=""

# ═══════════════════════════════════════════════════════
log()  { echo "[$(date '+%H:%M:%S')] $1"; }
die()  { echo "ERROR: $1" >&2; exit 1; }

# ═══════════════════════════════════════════════════════
# 모니터링 시작/종료 (트래픽과 동시 실행)
# ═══════════════════════════════════════════════════════
start_monitor() {
    local run_id="$1"
    local monitor_dir="${SCRIPT_DIR}/monitor-data/${run_id}"

    if [[ -f "${SCRIPT_DIR}/monitor/monitor-collector.sh" ]]; then
        log "Starting monitor-collector (interval: ${MONITOR_INTERVAL}s)..."
        "${SCRIPT_DIR}/monitor/monitor-collector.sh" \
            --interval "$MONITOR_INTERVAL" \
            --run-id "$run_id" \
            --output-dir "$monitor_dir" \
            --background
        MONITOR_PID=$(cat /tmp/monitor-collector.pid 2>/dev/null || echo "")
        log "Monitor PID: $MONITOR_PID"
    else
        log "monitor-collector.sh not found, skipping monitoring"
    fi
}

stop_monitor() {
    if [[ -n "$MONITOR_PID" ]] && kill -0 "$MONITOR_PID" 2>/dev/null; then
        log "Stopping monitor-collector (PID: $MONITOR_PID)..."
        kill "$MONITOR_PID" 2>/dev/null || true
        wait "$MONITOR_PID" 2>/dev/null || true
    elif [[ -f /tmp/monitor-collector.pid ]]; then
        "${SCRIPT_DIR}/monitor/monitor-collector.sh" --stop 2>/dev/null || true
    fi
}

run_visualize() {
    local run_id="$1"
    local monitor_dir="${SCRIPT_DIR}/monitor-data/${run_id}"

    if [[ -d "$monitor_dir" ]] && command -v python3 &>/dev/null; then
        log "Generating visualizations..."
        python3 "${SCRIPT_DIR}/monitor/monitor-visualize.py" "$monitor_dir" 2>/dev/null || {
            log "Visualization failed (matplotlib missing?). Skipping."
        }

        log "Running anomaly detection..."
        python3 "${SCRIPT_DIR}/monitor/monitor-detect.py" "$monitor_dir" 2>/dev/null || {
            local exit_code=$?
            if [[ $exit_code -eq 2 ]]; then
                log "⚠ CRITICAL anomalies detected!"
            elif [[ $exit_code -eq 1 ]]; then
                log "⚠ Degradation detected"
            fi
        }
    fi
}

# ═══════════════════════════════════════════════════════
# 사전 확인
# ═══════════════════════════════════════════════════════
preflight() {
    command -v kubectl &>/dev/null || die "kubectl not found"
    kubectl get ns "$NAMESPACE" &>/dev/null || die "Namespace '$NAMESPACE' not found"
}

# ═══════════════════════════════════════════════════════
# ConfigMap 생성/갱신
# ═══════════════════════════════════════════════════════
create_configmaps() {
    local profile_file="$1"
    log "Creating ConfigMap from: $profile_file"

    # 프로파일 ConfigMap
    kubectl create configmap traffic-profile \
        --from-file=profile.yaml="$profile_file" \
        -n "$NAMESPACE" \
        --dry-run=client -o yaml | kubectl apply -f -

    # 제네레이터 스크립트 ConfigMap
    kubectl create configmap traffic-gen-script \
        --from-file=traffic-gen.sh="${SCRIPT_DIR}/generator/traffic-gen.sh" \
        -n "$NAMESPACE" \
        --dry-run=client -o yaml | kubectl apply -f -
}

# ═══════════════════════════════════════════════════════
# 이전 Job 정리
# ═══════════════════════════════════════════════════════
cleanup_job() {
    if kubectl get job "$JOB_NAME" -n "$NAMESPACE" &>/dev/null; then
        log "Deleting previous Job: $JOB_NAME"
        kubectl delete job "$JOB_NAME" -n "$NAMESPACE" --wait=false 2>/dev/null || true
        sleep 3
    fi
}

# ═══════════════════════════════════════════════════════
# iperf3 서버 배포 확인
# ═══════════════════════════════════════════════════════
ensure_iperf_server() {
    if ! kubectl get deployment iperf3-server -n "$NAMESPACE" &>/dev/null; then
        log "Deploying iperf3 server..."
        kubectl apply -f "${SCRIPT_DIR}/k8s/traffic-job.yaml" -n "$NAMESPACE" \
            -l component=iperf3-server 2>/dev/null || \
        kubectl apply -f "${SCRIPT_DIR}/k8s/traffic-job.yaml" -n "$NAMESPACE"
        log "Waiting for iperf3 server to be ready..."
        kubectl rollout status deployment/iperf3-server -n "$NAMESPACE" --timeout=120s
    else
        log "iperf3 server already running"
    fi
}

# ═══════════════════════════════════════════════════════
# Job 배포 및 대기
# ═══════════════════════════════════════════════════════
run_job() {
    local profile_file="$1"
    local run_id="run_$(date +%Y%m%d_%H%M%S)"

    create_configmaps "$profile_file"
    cleanup_job
    ensure_iperf_server

    # 모니터링 시작 (트래픽과 동시 실행)
    start_monitor "$run_id"

    log "Launching traffic generator Job..."
    kubectl apply -f "${SCRIPT_DIR}/k8s/traffic-job.yaml" -n "$NAMESPACE"

    log "Waiting for Job completion (timeout: ${TIMEOUT}s)..."
    local job_result=0
    if kubectl wait --for=condition=complete job/"$JOB_NAME" \
        -n "$NAMESPACE" --timeout="${TIMEOUT}s" 2>/dev/null; then
        log "✓ Job completed successfully"
    else
        log "✗ Job did not complete in time"
        kubectl logs job/"$JOB_NAME" -n "$NAMESPACE" --tail=20 2>/dev/null || true
        job_result=1
    fi

    # 모니터링 종료 & 시각화/분석
    stop_monitor
    run_visualize "$run_id"

    log "Monitor data: ${SCRIPT_DIR}/monitor-data/${run_id}/"
    return $job_result
}

# ═══════════════════════════════════════════════════════
# 결과 수집 (Pod에서 로컬로 복사)
# ═══════════════════════════════════════════════════════
collect_results() {
    mkdir -p "$RESULT_LOCAL_DIR"

    local pod
    pod=$(kubectl get pods -n "$NAMESPACE" -l component=traffic-generator \
        --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)

    if [[ -z "$pod" ]]; then
        log "No traffic-gen pod found"
        return 1
    fi

    log "Collecting results from pod: $pod"
    kubectl cp "$NAMESPACE/$pod:/results/" "$RESULT_LOCAL_DIR/" 2>/dev/null || {
        # Pod이 이미 종료된 경우 logs로 대체
        log "Pod terminated. Dumping logs instead..."
        kubectl logs -n "$NAMESPACE" "$pod" > "${RESULT_LOCAL_DIR}/job_log_$(date +%Y%m%d_%H%M%S).txt" 2>/dev/null
    }

    log "Results saved to: $RESULT_LOCAL_DIR/"
    ls -la "$RESULT_LOCAL_DIR/" 2>/dev/null
}

# ═══════════════════════════════════════════════════════
# 상태 확인
# ═══════════════════════════════════════════════════════
show_status() {
    echo ""
    echo "═══ Traffic Generator Status ═══"
    echo ""
    echo "Jobs:"
    kubectl get jobs -n "$NAMESPACE" -l app=free5gc-test 2>/dev/null || echo "  (none)"
    echo ""
    echo "Pods:"
    kubectl get pods -n "$NAMESPACE" -l app=free5gc-test 2>/dev/null || echo "  (none)"
    echo ""
    echo "iperf3 Server:"
    kubectl get pods -n "$NAMESPACE" -l component=iperf3-server 2>/dev/null || echo "  (not deployed)"
    echo ""
}

# ═══════════════════════════════════════════════════════
# 정리
# ═══════════════════════════════════════════════════════
clean_all() {
    log "Cleaning up traffic generator resources..."
    kubectl delete job "$JOB_NAME" -n "$NAMESPACE" --ignore-not-found
    kubectl delete deployment iperf3-server -n "$NAMESPACE" --ignore-not-found
    kubectl delete service iperf3-server -n "$NAMESPACE" --ignore-not-found
    kubectl delete configmap traffic-profile traffic-gen-script -n "$NAMESPACE" --ignore-not-found
    log "Cleanup done"
}

# ═══════════════════════════════════════════════════════
# 전체 프로파일 순차 실행
# ═══════════════════════════════════════════════════════
run_all() {
    local profiles=("${SCRIPT_DIR}"/profiles/*.yaml)
    local total=${#profiles[@]}
    local passed=0
    local failed=0

    # schema.yaml 제외
    profiles=( $(printf '%s\n' "${profiles[@]}" | grep -v schema.yaml) )
    total=${#profiles[@]}

    log "Running all ${total} profiles..."
    echo ""

    for profile in "${profiles[@]}"; do
        local name
        name=$(basename "$profile" .yaml)
        log "━━━ [$((passed+failed+1))/$total] $name ━━━"

        if run_job "$profile"; then
            collect_results
            passed=$((passed+1))
        else
            failed=$((failed+1))
        fi
        echo ""
    done

    echo "═══════════════════════════════════"
    echo "  Results: $passed passed, $failed failed (of $total)"
    echo "  Output:  $RESULT_LOCAL_DIR/"
    echo "═══════════════════════════════════"
}

# ═══════════════════════════════════════════════════════
# 실험 시나리오 실행 (--experiment)
# ═══════════════════════════════════════════════════════
run_experiment() {
    local exp_file="$1"
    [[ ! -f "$exp_file" ]] && die "Experiment file not found: $exp_file"

    command -v yq &>/dev/null || die "yq required for --experiment mode"

    local exp_name rep_count nwdaf_enabled initial_cni
    exp_name=$(yq eval '.metadata.name' "$exp_file")
    rep_count=$(yq eval '.measurement.repetitions // 1' "$exp_file")
    nwdaf_enabled=$(yq eval '.nwdaf.enabled' "$exp_file")
    initial_cni=$(yq eval '.cni.initial' "$exp_file")

    echo "═══════════════════════════════════════"
    echo "  Experiment: $exp_name"
    echo "  NWDAF: $nwdaf_enabled"
    echo "  Initial CNI: $initial_cni"
    echo "  Repetitions: $rep_count"
    echo "═══════════════════════════════════════"
    echo ""

    local nwdaf_switch="${SCRIPT_DIR}/../arm_k8s/dranet/nwdaf-switch.sh"

    for rep in $(seq 1 "$rep_count"); do
        log "━━━ Repetition $rep/$rep_count ━━━"

        local run_id="exp_$(yq eval '.metadata.matrix_id' "$exp_file")_rep${rep}_$(date +%Y%m%d_%H%M%S)"

        # 1. NWDAF on/off
        if [[ "$nwdaf_enabled" == "true" ]]; then
            log "Enabling NWDAF..."
            "$nwdaf_switch" on 2>/dev/null || kubectl scale deploy/nwdaf -n "$NAMESPACE" --replicas=1
            if [[ "$(yq eval '.nwdaf.wait_ready // false' "$exp_file")" == "true" ]]; then
                kubectl wait --for=condition=ready pod -l nf=nwdaf -n "$NAMESPACE" --timeout=60s 2>/dev/null || true
            fi
        else
            log "NWDAF OFF"
            "$nwdaf_switch" off 2>/dev/null || kubectl scale deploy/nwdaf -n "$NAMESPACE" --replicas=0 2>/dev/null || true
        fi

        # 2. Initial CNI 설정
        log "Setting initial CNI: $initial_cni"
        "$nwdaf_switch" "$initial_cni" 2>/dev/null || true
        sleep 3

        # 3. 모니터링 시작
        start_monitor "$run_id"

        # 4. 실험 파일 자체를 traffic profile로 사용 (phases + traffic_pattern 인라인)
        #    traffic-gen.sh가 phases 배열을 순차 실행
        local total_duration=0
        local phase_count
        phase_count=$(yq eval '.phases | length' "$exp_file")

        for i in $(seq 0 $((phase_count - 1))); do
            local dur
            dur=$(yq eval ".phases[$i].traffic_pattern.duration // \"60s\"" "$exp_file" | sed 's/s//')
            total_duration=$((total_duration + dur))
        done

        log "Deploying traffic Job ($phase_count phases, total ${total_duration}s)"

        # 실험 파일 자체를 ConfigMap으로 올림
        create_configmaps "$exp_file"
        cleanup_job
        kubectl apply -f "${SCRIPT_DIR}/k8s/traffic-job.yaml" -n "$NAMESPACE"

        # 전체 duration 대기 (+ 30초 여유)
        local wait_total=$((total_duration + 30))
        log "Waiting up to ${wait_total}s for Job completion..."
        if kubectl wait --for=condition=complete job/"$JOB_NAME" \
            -n "$NAMESPACE" --timeout="${wait_total}s" 2>/dev/null; then
            log "✓ Job completed"
        else
            log "⚠ Job timeout — collecting partial results"
        fi

        # 5. 모니터링 종료 & 분석
        stop_monitor
        run_visualize "$run_id"

        # 6. NWDAF 로그 수집 (on인 경우)
        if [[ "$nwdaf_enabled" == "true" ]]; then
            local nwdaf_pod
            nwdaf_pod=$(kubectl get pods -n "$NAMESPACE" -l nf=nwdaf -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
            if [[ -n "$nwdaf_pod" ]]; then
                kubectl logs "$nwdaf_pod" -n "$NAMESPACE" --tail=100 \
                    > "${SCRIPT_DIR}/monitor-data/${run_id}/nwdaf-log.txt" 2>/dev/null || true
            fi
        fi

        # 7. 결과 기록
        local result_dir="${SCRIPT_DIR}/monitor-data/${run_id}"
        cp "$exp_file" "$result_dir/experiment.yaml" 2>/dev/null || true
        log "Results: $result_dir/"
        echo ""
    done

    # 종료 — NWDAF off
    "$nwdaf_switch" off 2>/dev/null || kubectl scale deploy/nwdaf -n "$NAMESPACE" --replicas=0 2>/dev/null || true

    echo "═══════════════════════════════════════"
    echo "  ✓ Experiment complete: $exp_name"
    echo "  Repetitions: $rep_count"
    echo "  Results: ${SCRIPT_DIR}/monitor-data/"
    echo "═══════════════════════════════════════"
}

# ═══════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════
main() {
    preflight

    case "${1:-}" in
        --experiment)
            [[ -z "${2:-}" ]] && die "Usage: $0 --experiment <experiment.yaml>"
            run_experiment "$2"
            ;;
        --all)
            run_all
            ;;
        --status)
            show_status
            ;;
        --collect)
            collect_results
            ;;
        --clean)
            clean_all
            ;;
        --help|-h)
            echo "Usage:"
            echo "  $0 --apn <apn.yaml> --scenario <scenario.yaml> [--dry-run]"
            echo "  $0 <profile.yaml> [--dry-run]    (legacy single-file)"
            echo "  $0 --all"
            echo "  $0 --status | --collect | --clean"
            ;;
        --apn)
            # 신규 구조: --apn + --scenario
            local apn_file="" scenario_file="" dry_run_flag=""
            shift  # consume --apn
            apn_file="$1"; shift
            [[ "${1:-}" == "--scenario" ]] && { shift; scenario_file="$1"; shift; }
            [[ "${1:-}" == "--dry-run" ]] && { dry_run_flag="--dry-run"; shift; }

            [[ -z "$apn_file" ]] && die "Missing --apn file"
            [[ -z "$scenario_file" ]] && die "Missing --scenario file"
            [[ ! -f "$apn_file" ]] && die "APN file not found: $apn_file"
            [[ ! -f "$scenario_file" ]] && die "Scenario file not found: $scenario_file"

            # APN + Scenario → merged profile 생성
            local merged="/tmp/merged_profile_$(date +%s).yaml"
            yq eval-all 'select(fileIndex == 0) * select(fileIndex == 1)' \
                "$apn_file" "$scenario_file" > "$merged"
            local apn_name
            apn_name=$(yq eval '.dnn' "$apn_file")
            yq eval -i ".apn = \"$apn_name\"" "$merged"

            log "APN: $apn_file ($apn_name)"
            log "Scenario: $scenario_file"

            if [[ "$dry_run_flag" == "--dry-run" ]]; then
                log "[DRY-RUN] Merged profile:"
                cat "$merged"
                create_configmaps "$merged"
                log "[DRY-RUN] ConfigMaps created. Job NOT deployed."
            else
                run_job "$merged" && collect_results
            fi
            rm -f "$merged"
            ;;
        *.yaml|*.yml)
            # 레거시: 단일 프로파일 파일
            local profile="$1"
            [[ ! -f "$profile" ]] && die "Profile not found: $profile"

            if [[ "${2:-}" == "--dry-run" ]]; then
                log "[DRY-RUN] Would deploy with profile: $profile"
                create_configmaps "$profile"
                log "[DRY-RUN] ConfigMaps created. Job NOT deployed."
            else
                run_job "$profile" && collect_results
            fi
            ;;
        *)
            die "Usage: $0 --apn <apn.yaml> --scenario <scenario.yaml> | <profile.yaml> | --all | --status | --collect | --clean"
            ;;
    esac
}

main "$@"
