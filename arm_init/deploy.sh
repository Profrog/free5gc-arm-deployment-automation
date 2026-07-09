#!/bin/bash
# free5gc K8s 배포 (arm_k8s/setup.sh wrapper)
# 사전 조건: docker-build.sh 실행 완료 (containerd에 이미지 존재)
#
# 사용: ./deploy.sh [check|config|deploy|all|status]
#   인자 없으면 all (이미지확인 → config수정 → 배포)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
K8S_SETUP="$PROJECT_DIR/arm_k8s/setup.sh"

# 네트워크 설정을 환경변수로 전달
export NET_IFACE="${NET_IFACE:-enp0s6}"
export N2_SUBNET="${N2_SUBNET:-10.10.2.0/24}"
export N3_SUBNET="${N3_SUBNET:-10.10.3.0/24}"
export N4_SUBNET="${N4_SUBNET:-10.10.4.0/24}"

[ -f "$K8S_SETUP" ] || { echo "[ERROR] $K8S_SETUP not found"; exit 1; }

# subscriber 등록
register_subscriber() {
    local SUB_SCRIPT="$PROJECT_DIR/arm_k8s/subscriber/add-subscribers.sh"
    if [ -f "$SUB_SCRIPT" ]; then
        echo "[$(date '+%H:%M:%S')] Registering subscribers ..."
        bash "$SUB_SCRIPT" add
        echo "[OK] Subscribers registered"
    fi
}

# 실행
bash "$K8S_SETUP" "${1:-all}"

# deploy 또는 all일 때 subscriber 등록
case "${1:-all}" in
    deploy|all) register_subscriber ;;
esac
