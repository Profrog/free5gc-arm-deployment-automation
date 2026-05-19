#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
K8S_DIR="$(dirname "$SCRIPT_DIR")"
NAMESPACE="free5gc"

NFS="nrf amf ausf pcf udr udm nssf smf smf2"

log() { echo "[$(date '+%H:%M:%S')] $1"; }
die() { echo "[ERROR] $1"; exit 1; }

# ────────────────────────────────────────────
# 1. Docker 이미지 빌드
# ────────────────────────────────────────────
build_images() {
    log "=== Building Docker images ==="
    for nf in nrf amf ausf pcf udr udm nssf smf; do
        local dir="$SCRIPT_DIR/$nf"
        [ -d "$dir" ] || die "Directory not found: $dir"
        log "Building arm-curl:$nf ..."
        docker build -t arm-curl:$nf "$dir" 2>&1 | tail -1
    done

    # arm-curl:latest (init container용 - curl만 있는 경량 이미지)
    log "Building arm-curl:latest (init container) ..."
    docker build -t arm-curl:latest - << 'EOF'
FROM arm64v8/alpine:3.18
RUN apk add --no-cache curl
EOF

    # arm-curl:v2 는 udm과 동일
    docker tag arm-curl:udm arm-curl:v2
    log "Tagged arm-curl:v2 from arm-curl:udm"
}

# ────────────────────────────────────────────
# 2. containerd import
# ────────────────────────────────────────────
import_images() {
    log "=== Importing images to containerd ==="
    for tag in nrf amf ausf pcf udr udm nssf smf v2 latest; do
        log "Importing arm-curl:$tag ..."
        docker save arm-curl:$tag | sudo ctr -n k8s.io images import - 2>&1 | tail -1
    done
}

# ────────────────────────────────────────────
# 3. Kubernetes 배포
# ────────────────────────────────────────────
deploy() {
    log "=== Deploying to Kubernetes (namespace: $NAMESPACE) ==="

    # 기존 NF deployment 삭제
    log "Deleting existing deployments ..."
    kubectl delete deployment \
        free5gc-nrf free5gc-amf free5gc-ausf free5gc-pcf \
        free5gc-udr free5gc-udm free5gc-nssf \
        free5gc-smf free5gc-smf2 free5gc-upf free5gc-upf2 \
        -n $NAMESPACE 2>/dev/null || true

    sleep 5

    # configmap 적용
    log "Applying configmaps ..."
    for nf in nrf amf ausf pcf udr udm nssf; do
        kubectl apply -f "$SCRIPT_DIR/$nf/${nf}-configmap.yaml" -n $NAMESPACE
    done
    kubectl apply -f "$SCRIPT_DIR/smf/smf-configmap.yaml" -n $NAMESPACE

    # deployment 적용
    log "Applying deployments ..."
    kubectl apply -k "$K8S_DIR/free5gc/common/" -n $NAMESPACE
    kubectl apply -k "$K8S_DIR/free5gc/slices/" -n $NAMESPACE

    log "Waiting for pods to start (30s) ..."
    sleep 30
    kubectl get pods -n $NAMESPACE | grep -v "ContainerStatus\|Evicted"
}

# ────────────────────────────────────────────
# 4. 상태 확인
# ────────────────────────────────────────────
status() {
    log "=== Pod status ==="
    kubectl get pods -n $NAMESPACE | grep -v "ContainerStatus\|Evicted"
}

# ────────────────────────────────────────────
# Main
# ────────────────────────────────────────────
case "${1:-all}" in
    build)   build_images ;;
    import)  import_images ;;
    deploy)  deploy ;;
    status)  status ;;
    all)
        build_images
        import_images
        deploy
        ;;
    *)
        echo "Usage: $0 [build|import|deploy|status|all]"
        echo "  build   - Docker 이미지 빌드"
        echo "  import  - containerd로 이미지 import"
        echo "  deploy  - Kubernetes 배포"
        echo "  status  - pod 상태 확인"
        echo "  all     - 전체 실행 (기본값)"
        ;;
esac
