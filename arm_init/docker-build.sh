#!/bin/bash
# 빌드된 NF 바이너리를 Docker 이미지로 패키징 + containerd import
# 사전 조건: build.sh 실행 완료 (free5gc_build/{nf}/{nf} 바이너리 존재)
#
# 사용: ./docker-build.sh [NF_NAME...]
#   예: ./docker-build.sh              (전체 이미지 빌드)
#       ./docker-build.sh amf smf      (특정 NF만 빌드)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$PROJECT_DIR/arm_docker"
CORE_DIR="$DOCKER_DIR/core_images"
RAN_DIR="$DOCKER_DIR/ran_images"
BUILD_DIR="$PROJECT_DIR/free5gc_build"

ALL_NFS="nrf amf ausf pcf udr udm nssf smf upf ueransim"

log() { echo "[$(date '+%H:%M:%S')] $1"; }
ok()  { echo "[OK] $1"; }
die() { echo "[ERROR] $1"; exit 1; }

# 사전 조건
command -v docker &>/dev/null || die "docker not found. Run arm_init/infra-setup.sh first."

# ────────────────────────────────────────────
# 빌드 대상 결정
# ────────────────────────────────────────────
if [ $# -gt 0 ]; then
    BUILD_NFS="$*"
else
    BUILD_NFS="$ALL_NFS"
fi

# 바이너리 존재 확인
for nf in $BUILD_NFS; do
    if [ "$nf" = "ueransim" ]; then
        [ -f "$BUILD_DIR/ueransim/nr-gnb" ] || die "Binary not found: $BUILD_DIR/ueransim/nr-gnb\n  Run arm_init/build.sh first."
    else
        [ -f "$BUILD_DIR/$nf/$nf" ] || die "Binary not found: $BUILD_DIR/$nf/$nf\n  Run arm_init/build.sh first."
    fi
done

# ────────────────────────────────────────────
# Core NF 이미지 빌드 (Go 바이너리 → alpine)
# ────────────────────────────────────────────
build_core_image() {
    local nf="$1"
    mkdir -p "$CORE_DIR/$nf"
    cp "$BUILD_DIR/$nf/$nf" "$CORE_DIR/$nf/$nf"
    chmod +x "$CORE_DIR/$nf/$nf"
    cat > "$CORE_DIR/$nf/Dockerfile" << EOF
FROM arm64v8/alpine:3.18
RUN apk add --no-cache curl
WORKDIR /app
COPY ./$nf ./$nf
CMD ["./$nf"]
EOF
    log "  Building image arm-curl:$nf ..."
    docker build -t "arm-curl:$nf" "$CORE_DIR/$nf" 2>&1 | tail -1
}

# ────────────────────────────────────────────
# UPF 이미지 빌드
# ────────────────────────────────────────────
build_upf_image() {
    mkdir -p "$CORE_DIR/upf"
    cp "$BUILD_DIR/upf/upf" "$CORE_DIR/upf/upf"
    chmod +x "$CORE_DIR/upf/upf"
    log "  Building image arm-curl:upf ..."
    docker build --platform linux/arm64 -t arm-curl:upf "$CORE_DIR/upf" 2>&1 | tail -1
}

# ────────────────────────────────────────────
# UERANSIM 이미지 빌드
# ────────────────────────────────────────────
build_ueransim_image() {
    mkdir -p "$RAN_DIR/ueransim"
    cp "$BUILD_DIR/ueransim/nr-gnb" "$RAN_DIR/ueransim/nr-gnb"
    cp "$BUILD_DIR/ueransim/nr-ue" "$RAN_DIR/ueransim/nr-ue"
    chmod +x "$RAN_DIR/ueransim/nr-gnb" "$RAN_DIR/ueransim/nr-ue"

    # Dockerfile 생성 (빌드 없이 바이너리 복사만)
    cat > "$RAN_DIR/ueransim/Dockerfile" << 'EOF'
FROM arm64v8/ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    libsctp-dev lksctp-tools iproute2 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /ueransim
COPY ./nr-gnb .
COPY ./nr-ue .
VOLUME ["/ueransim/config"]
EOF
    log "  Building image arm-curl:ueransim ..."
    docker build --platform linux/arm64 -t arm-curl:ueransim "$RAN_DIR/ueransim" 2>&1 | tail -1
}

# ────────────────────────────────────────────
# curl init container 이미지 빌드
# ────────────────────────────────────────────
build_curl_image() {
    mkdir -p "$CORE_DIR/curl"
    cat > "$CORE_DIR/curl/Dockerfile" << 'EOF'
FROM arm64v8/alpine:3.18
RUN apk add --no-cache curl
EOF
    log "  Building image arm-curl:curl (init container) ..."
    docker build -t arm-curl:curl "$CORE_DIR/curl" 2>&1 | tail -1
}

# ────────────────────────────────────────────
# 외부 이미지 pull + containerd import
# ────────────────────────────────────────────
EXTERNAL_IMAGES=(
    "mongo:4.4"
    "fluent/fluent-bit:1.9"
    "ghcr.io/niloysh/free5gc:v3.2.0"
    "ghcr.io/niloysh/upf-exporter:v3.0.1"
)

pull_external_images() {
    log "=== Pulling external images ==="
    for img in "${EXTERNAL_IMAGES[@]}"; do
        if sudo ctr -n k8s.io images ls -q | grep -q "$img"; then
            log "  $img: already in containerd, skip."
        else
            log "  Pulling $img ..."
            docker pull --platform linux/arm64 "$img" 2>&1 | tail -1
            docker save "$img" | sudo ctr -n k8s.io images import - 2>&1 | tail -1
            ok "  $img imported"
        fi
    done
}

# ────────────────────────────────────────────
# containerd import
# ────────────────────────────────────────────
import_image() {
    local tag="$1"
    docker save "arm-curl:$tag" | sudo ctr -n k8s.io images import - 2>&1 | tail -1
}

# ────────────────────────────────────────────
# Main
# ────────────────────────────────────────────
log "=== Docker image build + containerd import ==="
log "  Targets: $BUILD_NFS"
echo ""

CORE_NFS="nrf amf ausf pcf udr udm nssf smf"
IMPORT_TAGS=""

for nf in $BUILD_NFS; do
    case "$nf" in
        upf)
            build_upf_image
            IMPORT_TAGS="$IMPORT_TAGS upf"
            ;;
        ueransim)
            build_ueransim_image
            IMPORT_TAGS="$IMPORT_TAGS ueransim"
            ;;
        *)
            build_core_image "$nf"
            IMPORT_TAGS="$IMPORT_TAGS $nf"
            ;;
    esac
done

# curl init container (항상 빌드)
build_curl_image
IMPORT_TAGS="$IMPORT_TAGS curl"

echo ""
log "Importing images to containerd ..."
for tag in $IMPORT_TAGS; do
    log "  Importing arm-curl:$tag ..."
    import_image "$tag"
done

# 외부 이미지 pull + import
echo ""
pull_external_images

echo ""
ok "All images ready in containerd"
echo ""
log "Custom images:"
for tag in $IMPORT_TAGS; do
    echo "  arm-curl:$tag"
done
log "External images:"
for img in "${EXTERNAL_IMAGES[@]}"; do
    echo "  $img"
done
