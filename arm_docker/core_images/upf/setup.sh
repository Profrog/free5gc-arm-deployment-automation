#!/bin/bash
# ARM64 UPF 이미지 빌드 및 배포
# 실행: ./setup.sh [build|import|deploy|all]
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IMAGE="arm-upf:latest"
NAMESPACE="free5gc"

log() { echo "[$(date '+%H:%M:%S')] $1"; }
ok()  { echo "[OK] $1"; }
die() { echo "[ERROR] $1"; exit 1; }

build() {
    log "=== Building ARM64 UPF image ==="
    [ -f "$SCRIPT_DIR/upf" ] || die "upf binary not found. Build from free5gc_build/free5gc/ first:
  cd ~/free5gc_build/free5gc && GOARCH=arm64 make upf
  cp bin/upf $SCRIPT_DIR/upf"

    docker build --platform linux/arm64 -t "$IMAGE" "$SCRIPT_DIR"
    ok "Built $IMAGE"
}

import_image() {
    log "=== Importing to containerd ==="
    docker save "$IMAGE" | sudo ctr -n k8s.io images import -
    ok "Imported $IMAGE"
}

deploy() {
    log "=== Patching UPF deployments to use $IMAGE ==="
    for dep in free5gc-upf free5gc-upf2; do
        kubectl set image deployment/"$dep" upf="$IMAGE" -n "$NAMESPACE" 2>/dev/null || true
        kubectl patch deployment "$dep" -n "$NAMESPACE" \
            -p '{"spec":{"template":{"spec":{"containers":[{"name":"upf","imagePullPolicy":"Never"}]}}}}' \
            2>/dev/null || true
    done
    ok "UPF deployments patched"
    kubectl get pods -n "$NAMESPACE" -l nf=upf
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
        echo "  build   - ARM64 Docker 이미지 빌드 (upf 바이너리 필요)"
        echo "  import  - containerd로 이미지 import"
        echo "  deploy  - UPF deployment 이미지 교체"
        echo "  all     - 전체 실행 (기본값)"
        ;;
esac
