#!/bin/bash
# ARM K8s 클러스터 사전 설정
# setup.sh 실행 전에 한 번만 실행
# 사용: ./pre-setup.sh
set -e

log() { echo "[$(date '+%H:%M:%S')] $1"; }
ok()  { echo "[OK] $1"; }

# ════════════════════════════════════════════
# 1. 시스템 패키지
# ════════════════════════════════════════════
install_packages() {
    log "=== System packages ==="
    sudo apt-get update
    sudo apt-get install -y curl git vim iproute2 iputils-ping jq
    ok "Packages installed"
}

# ════════════════════════════════════════════
# 2. Containerd + Docker
# ════════════════════════════════════════════
install_containerd() {
    log "=== Containerd ==="
    if command -v containerd &>/dev/null; then
        ok "Already installed"; return
    fi

    sudo apt-get install -y ca-certificates curl gnupg
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --yes --dearmor -o /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin

    sudo mkdir -p /etc/containerd
    containerd config default | sudo tee /etc/containerd/config.toml > /dev/null
    sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
    sudo systemctl enable --now containerd
    ok "Containerd installed"
}

# ════════════════════════════════════════════
# 3. K8s 네트워킹 사전 설정
# ════════════════════════════════════════════
setup_networking() {
    log "=== K8s networking prerequisites ==="
    cat <<EOF | sudo tee /etc/modules-load.d/k8s.conf > /dev/null
overlay
br_netfilter
EOF
    sudo modprobe overlay
    sudo modprobe br_netfilter

    cat <<EOF | sudo tee /etc/sysctl.d/k8s.conf > /dev/null
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1
net.ipv4.conf.all.rp_filter = 0
net.ipv4.conf.default.rp_filter = 0
EOF
    sudo sysctl --system > /dev/null

    sudo swapoff -a
    sudo sed -i '/swap/ s/^/#/' /etc/fstab
    ok "Networking configured"
}

# ════════════════════════════════════════════
# 4. Kubernetes (kubeadm, kubelet, kubectl)
# ════════════════════════════════════════════
install_k8s() {
    log "=== Kubernetes ==="
    if command -v kubectl &>/dev/null; then
        ok "Already installed"; return
    fi

    sudo apt-get install -y apt-transport-https ca-certificates curl gpg
    curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.28/deb/Release.key | sudo gpg --yes --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
    echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.28/deb/ /' | sudo tee /etc/apt/sources.list.d/kubernetes.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y kubelet kubeadm kubectl
    sudo apt-mark hold kubelet kubeadm kubectl
    ok "Kubernetes installed"
}

# ════════════════════════════════════════════
# 5. 클러스터 생성 (single-node)
# ════════════════════════════════════════════
create_cluster() {
    log "=== K8s cluster ==="
    if [ -f /etc/kubernetes/admin.conf ]; then
        ok "Cluster already exists"; return
    fi

    sudo kubeadm init --pod-network-cidr=10.244.0.0/16
    mkdir -p "$HOME/.kube"
    sudo cp /etc/kubernetes/admin.conf "$HOME/.kube/config"
    sudo chown "$(id -u):$(id -g)" "$HOME/.kube/config"
    kubectl taint nodes --all node-role.kubernetes.io/control-plane:NoSchedule- 2>/dev/null || true
    ok "Cluster created"
}

# ════════════════════════════════════════════
# 6. CNI: Flannel + Multus
# ════════════════════════════════════════════
install_cni() {
    log "=== Flannel ==="
    if ! kubectl get pods -n kube-flannel -l app=flannel 2>/dev/null | grep -q '1/1'; then
        kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml
        kubectl wait pods -n kube-flannel -l app=flannel --for=condition=Ready --timeout=120s
    fi
    ok "Flannel ready"

    log "=== Multus ==="
    if ! kubectl get pods -n kube-system -l app=multus 2>/dev/null | grep -q '1/1'; then
        kubectl apply -f https://raw.githubusercontent.com/k8snetworkplumbingwg/multus-cni/master/deployments/multus-daemonset.yml
        kubectl wait pods -n kube-system -l app=multus --for=condition=Ready --timeout=120s
    fi
    ok "Multus ready"
}

# ════════════════════════════════════════════
# 7. Go (NF 빌드용)
# ════════════════════════════════════════════
install_go() {
    log "=== Go ==="
    if command -v go &>/dev/null; then
        ok "Already installed ($(go version))"; return
    fi

    local GO_VER="1.21.6"
    wget -q "https://go.dev/dl/go${GO_VER}.linux-arm64.tar.gz" -O /tmp/go.tar.gz
    sudo rm -rf /usr/local/go
    sudo tar -C /usr/local -xzf /tmp/go.tar.gz
    echo 'export PATH=$PATH:/usr/local/go/bin' | sudo tee /etc/profile.d/go.sh > /dev/null
    export PATH=$PATH:/usr/local/go/bin
    rm /tmp/go.tar.gz
    ok "Go $GO_VER installed"
}

# ════════════════════════════════════════════
# Main
# ════════════════════════════════════════════
log "ARM K8s cluster pre-setup"
install_packages
install_containerd
setup_networking
install_k8s
create_cluster
install_cni
install_go

echo ""
ok "Pre-setup complete. Run ./setup.sh to deploy free5gc."
