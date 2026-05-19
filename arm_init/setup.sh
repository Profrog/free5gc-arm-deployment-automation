#!/bin/bash
# ARM free5gc 전체 파이프라인
# UE 1대 → 패킷코어까지 한 번에 구축
#
# 사용: ./setup.sh [VERSION]
#   예: ./setup.sh v3.4.3
#       ./setup.sh          (현재 버전으로 실행)
set -e

# ════════════════════════════════════════════
# 설정
# ════════════════════════════════════════════
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$PROJECT_DIR/arm_docker"
CORE_DIR="$DOCKER_DIR/core_images"
RAN_DIR="$DOCKER_DIR/ran_images"
K8S_DIR="$PROJECT_DIR/arm_k8s"
NFS="nrf amf ausf pcf udr udm nssf smf"
NAMESPACE="free5gc"

log() { echo "[$(date '+%H:%M:%S')] $1"; }
ok()  { echo "[OK] $1"; }
die() { echo "[ERROR] $1"; exit 1; }

# 사전 조건 확인
command -v go &>/dev/null || die "go not found. Run arm_init/pre-setup.sh first."
command -v docker &>/dev/null || die "docker not found. Run arm_init/pre-setup.sh first."
command -v kubectl &>/dev/null || die "kubectl not found. Run arm_init/pre-setup.sh first."

# free5gc 소스
FREE5GC_SRC="$PROJECT_DIR/free5gc_build/free5gc"
if [ ! -d "$FREE5GC_SRC" ]; then
    log "Cloning free5gc source ..."
    mkdir -p "$(dirname "$FREE5GC_SRC")"
    git clone --recursive https://github.com/free5gc/free5gc.git "$FREE5GC_SRC"
fi
CURRENT_VERSION=$(cd "$FREE5GC_SRC" && git describe --tags 2>/dev/null || echo "v3.4.2")
FREE5GC_VERSION="${1:-$CURRENT_VERSION}"

# 네트워크 설정 (환경변수로 오버라이드 가능)
NET_IFACE="${NET_IFACE:-enp0s6}"
N2_SUBNET="${N2_SUBNET:-10.10.2.0/24}"
N3_SUBNET="${N3_SUBNET:-10.10.3.0/24}"
N4_SUBNET="${N4_SUBNET:-10.10.4.0/24}"

# ════════════════════════════════════════════
# Phase 1: 도커 이미지 빌드 + import
# ════════════════════════════════════════════
phase_docker() {
    log "══ Phase 1: Docker images ══"

    # 소스 체크아웃
    cd "$FREE5GC_SRC"
    if [ "$FREE5GC_VERSION" != "$CURRENT_VERSION" ]; then
        log "Switching to $FREE5GC_VERSION ..."
        git checkout "$FREE5GC_VERSION"
        git submodule update --init --recursive
    fi

    # NF 바이너리 빌드
    mkdir -p "$FREE5GC_SRC/bin"
    for nf in $NFS upf; do
        log "  Building $nf ..."
        cd "$FREE5GC_SRC/NFs/$nf/cmd" && \
            CGO_ENABLED=0 go build -ldflags "-s -w" -o "$FREE5GC_SRC/bin/$nf" main.go
    done

    # Dockerfile + 바이너리 갱신
    for nf in $NFS; do
        mkdir -p "$CORE_DIR/$nf"
        cp "$FREE5GC_SRC/bin/$nf" "$CORE_DIR/$nf/$nf"
        chmod +x "$CORE_DIR/$nf/$nf"
        cat > "$CORE_DIR/$nf/Dockerfile" << EOF
FROM arm64v8/alpine:3.18
RUN apk add --no-cache curl
WORKDIR /app
COPY ./$nf ./$nf
CMD ["./$nf"]
EOF
    done
    cp "$FREE5GC_SRC/bin/upf" "$CORE_DIR/upf/upf"
    chmod +x "$CORE_DIR/upf/upf"

    # Docker 이미지 빌드
    for nf in $NFS; do
        docker build -t "arm-curl:$nf" "$CORE_DIR/$nf" 2>&1 | tail -1
    done
    docker build -t arm-curl:curl "$CORE_DIR/curl"
    docker build --platform linux/arm64 -t arm-curl:upf "$CORE_DIR/upf" 2>&1 | tail -1
    docker build --platform linux/arm64 -t arm-curl:ueransim "$RAN_DIR/ueransim" 2>&1 | tail -1

    # containerd import
    for tag in $NFS curl upf ueransim; do
        docker save "arm-curl:$tag" | sudo ctr -n k8s.io images import - 2>&1 | tail -1
    done

    ok "Phase 1 complete: all images ready"
}

# ════════════════════════════════════════════
# Phase 2: K8s config 수정 + 배포
# ════════════════════════════════════════════
phase_k8s() {
    log "══ Phase 2: K8s deploy ══"

    # gtp5g 커널 모듈 로드
    if ! lsmod | grep -q gtp5g; then
        if modinfo gtp5g &>/dev/null; then
            sudo modprobe gtp5g
        else
            cd "$PROJECT_DIR/build/gtp5g" && make && sudo make install && sudo modprobe gtp5g
        fi
        log "  gtp5g module loaded"
    fi

    # NAD master 인터페이스 수정
    sed -i "s/\"master\": \"[^\"]*\"/\"master\": \"$NET_IFACE\"/" \
        "$K8S_DIR/networks5g/network-attachments-ipvlan.yaml"

    # IP 대역 동기화
    local n2_prefix=$(echo "$N2_SUBNET" | cut -d'/' -f1 | sed 's/\.[0-9]*$//')
    local n3_prefix=$(echo "$N3_SUBNET" | cut -d'/' -f1 | sed 's/\.[0-9]*$//')
    local n4_prefix=$(echo "$N4_SUBNET" | cut -d'/' -f1 | sed 's/\.[0-9]*$//')
    if [ "$n2_prefix" != "10.10.2" ] || [ "$n3_prefix" != "10.10.3" ] || [ "$n4_prefix" != "10.10.4" ]; then
        log "  Syncing IPs: N2=$n2_prefix, N3=$n3_prefix, N4=$n4_prefix"
        find "$K8S_DIR" -name "*.yaml" -exec sed -i \
            -e "s|10\.10\.2\.|${n2_prefix}.|g" \
            -e "s|10\.10\.3\.|${n3_prefix}.|g" \
            -e "s|10\.10\.4\.|${n4_prefix}.|g" {} \;
    fi

    # 배포
    kubectl create namespace "$NAMESPACE" 2>/dev/null || true

    log "  [1/6] MongoDB"
    kubectl apply -k "$K8S_DIR/mongodb" -n "$NAMESPACE"
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=mongodb -n "$NAMESPACE" --timeout=120s

    log "  [2/6] NetworkAttachmentDefinitions"
    kubectl apply -k "$K8S_DIR/networks5g" -n "$NAMESPACE"

    log "  [3/6] Free5GC Core"
    kubectl apply -k "$K8S_DIR/free5gc" -n "$NAMESPACE"

    log "  [4/6] Free5GC WebUI"
    kubectl apply -k "$K8S_DIR/free5gc-webui" -n "$NAMESPACE"

    log "  Waiting for core pods ..."
    sleep 30

    log "  [5/6] UERANSIM gNB"
    kubectl apply -k "$K8S_DIR/ueransim/ueransim-gnb" -n "$NAMESPACE"
    sleep 10

    log "  [6/6] UERANSIM UE"
    kubectl apply -k "$K8S_DIR/ueransim/ueransim-ue" -n "$NAMESPACE"

    ok "Phase 2 complete: k8s deployed"
}

# ════════════════════════════════════════════
# Phase 3: Subscriber 등록
# ════════════════════════════════════════════
phase_subscriber() {
    log "══ Phase 3: Subscriber registration ══"
    bash "$K8S_DIR/subscriber/add-subscribers.sh" add
    ok "Phase 3 complete: subscribers registered"
}

# ════════════════════════════════════════════
# Status
# ════════════════════════════════════════════
status() {
    echo ""
    kubectl get pods -n "$NAMESPACE" -o wide | grep -v "Evicted"
}

# ════════════════════════════════════════════
# Main
# ════════════════════════════════════════════
log "free5gc ARM pipeline - version: $FREE5GC_VERSION"
log "Network: iface=$NET_IFACE N2=$N2_SUBNET N3=$N3_SUBNET N4=$N4_SUBNET"
echo ""

phase_docker
phase_k8s
phase_subscriber
status

echo ""
ok "Pipeline complete: UE → gNB → UPF → Core"
