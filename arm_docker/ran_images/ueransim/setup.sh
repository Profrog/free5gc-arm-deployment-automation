#!/bin/bash
# ARM64 UERANSIM 이미지 빌드 및 배포
# 실행: ./setup.sh [build|import|deploy|all]
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IMAGE="arm-ueransim:v3.2.6"
NAMESPACE="free5gc"

log() { echo "[$(date '+%H:%M:%S')] $1"; }
ok()  { echo "[OK] $1"; }

build() {
    log "=== Building ARM64 UERANSIM image (소스 빌드, 시간 소요) ==="
    docker build --platform linux/arm64 -t "$IMAGE" "$SCRIPT_DIR"
    ok "Built $IMAGE"
}

import_image() {
    log "=== Importing to containerd ==="
    docker save "$IMAGE" | sudo ctr -n k8s.io images import -
    ok "Imported $IMAGE"
}

deploy() {
    log "=== Patching UERANSIM deployments to use $IMAGE ==="

    # gNB
    kubectl set image deployment/ueransim-gnb gnb="$IMAGE" -n "$NAMESPACE" 2>/dev/null || true
    kubectl patch deployment ueransim-gnb -n "$NAMESPACE" \
        -p '{"spec":{"template":{"spec":{"containers":[{"name":"gnb","imagePullPolicy":"Never"}]}}}}' \
        2>/dev/null || true

    # UE1, UE2
    for ue in ueransim-ue1 ueransim-ue2; do
        kubectl set image deployment/"$ue" ue="$IMAGE" -n "$NAMESPACE" 2>/dev/null || true
        kubectl patch deployment "$ue" -n "$NAMESPACE" \
            -p '{"spec":{"template":{"spec":{"containers":[{"name":"ue","imagePullPolicy":"Never"}]}}}}' \
            2>/dev/null || true
    done

    ok "UERANSIM deployments patched"
    kubectl get pods -n "$NAMESPACE" -l app=ueransim
}

case "${1:-all}" in
    build)  build ;;
    import) import_image ;;
    deploy) deploy ;;
    all)
        build
        import_image
        deploy
        ;;
    *)
        echo "Usage: $0 [build|import|deploy|all]"
        echo "  build   - ARM64 Docker 이미지 빌드 (소스 컴파일)"
        echo "  import  - containerd로 이미지 import"
        echo "  deploy  - gNB/UE deployment 이미지 교체"
        echo "  all     - 전체 실행 (기본값)"
        ;;
esac
