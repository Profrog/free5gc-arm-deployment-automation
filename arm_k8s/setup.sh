#!/bin/bash
# ARM k8s 배포 스크립트
# 프로세스: 1) 로컬 이미지 확인 → 2) config/deploy yaml 수정 → 3) 배포
# 사용: ./setup.sh [check|config|deploy|all|status]
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NAMESPACE="free5gc"

# 로컬 빌드 이미지 목록 (arm_docker 디렉토리명과 일치)
REQUIRED_IMAGES="arm-curl:nrf arm-curl:amf arm-curl:ausf arm-curl:pcf arm-curl:udr arm-curl:udm arm-curl:nssf arm-curl:smf arm-curl:curl arm-curl:upf arm-curl:ueransim"

# 네트워크 대역 설정
NET_IFACE="${NET_IFACE:-enp0s6}"
N2_SUBNET="${N2_SUBNET:-10.10.2.0/24}"
N3_SUBNET="${N3_SUBNET:-10.10.3.0/24}"
N4_SUBNET="${N4_SUBNET:-10.10.4.0/24}"

log() { echo "[$(date '+%H:%M:%S')] $1"; }
ok()  { echo "[OK] $1"; }
die() { echo "[ERROR] $1"; exit 1; }

# ════════════════════════════════════════════
# 1. 로컬 이미지 확인
# ════════════════════════════════════════════
check_images() {
    log "=== Checking local images in containerd ==="
    local missing=""
    for img in $REQUIRED_IMAGES; do
        if ! sudo ctr -n k8s.io images ls -q | grep -q "$img"; then
            missing="$missing $img"
        fi
    done

    if [ -n "$missing" ]; then
        die "Missing images:$missing\n  Run arm_init/setup.sh first."
    fi
    ok "All required images present"
}

# ════════════════════════════════════════════
# 2. config/deploy yaml 수정 (인터페이스, IP 대역)
# ════════════════════════════════════════════
update_config() {
    log "=== Updating configs (iface: $NET_IFACE) ==="

    # NAD의 master 인터페이스 수정
    sed -i "s/\"master\": \"[^\"]*\"/\"master\": \"$NET_IFACE\"/" \
        "$SCRIPT_DIR/networks5g/network-attachments-ipvlan.yaml"

    # NAD 서브넷 수정
    local nad_file="$SCRIPT_DIR/networks5g/network-attachments-ipvlan.yaml"
    update_nad_subnet "$nad_file" "n2network" "$N2_SUBNET"
    update_nad_subnet "$nad_file" "n3network" "$N3_SUBNET"
    update_nad_subnet "$nad_file" "n4network" "$N4_SUBNET"

    # deployment/configmap IP를 NAD 대역에 맞춤
    sync_ips

    # imagePullPolicy: Never 보장
    find "$SCRIPT_DIR" -name "*-deployment.yaml" -exec \
        sed -i '/image: arm-curl:/{ n; s/imagePullPolicy: .*/imagePullPolicy: Never/; t; a\        imagePullPolicy: Never
}' {} \;

    ok "Configs updated"
}

# NAD 서브넷 업데이트 헬퍼
update_nad_subnet() {
    local file="$1" name="$2" subnet="$3"
    local prefix=$(echo "$subnet" | cut -d'/' -f1 | sed 's/\.[0-9]*$//')
    local mask=$(echo "$subnet" | cut -d'/' -f2)

    # 해당 NAD 블록의 subnet/range/gateway 수정
    # awk로 해당 name 블록을 찾아 수정
    python3 - "$file" "$name" "$prefix" "$mask" << 'PYEOF'
import sys, re, json

file, name, prefix, mask = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
with open(file) as f:
    content = f.read()

docs = content.split('---')
for i, doc in enumerate(docs):
    if f'name: {name}' in doc:
        # config JSON 수정
        m = re.search(r"config: '(\{.*?\})'", doc, re.DOTALL)
        if m:
            cfg = json.loads(m.group(1))
            cfg['ipam']['subnet'] = f"{prefix}.0/{mask}"
            cfg['ipam']['rangeStart'] = f"{prefix}.10"
            cfg['ipam']['rangeEnd'] = f"{prefix}.200"
            cfg['ipam']['gateway'] = f"{prefix}.1"
            new_cfg = json.dumps(cfg, indent=4)
            doc = doc[:m.start(1)] + new_cfg + doc[m.end(1):]
            docs[i] = doc

with open(file, 'w') as f:
    f.write('---'.join(docs))
PYEOF
}

# deployment annotation과 configmap의 IP를 NAD 대역에 맞춤
sync_ips() {
    local n2_prefix=$(echo "$N2_SUBNET" | cut -d'/' -f1 | sed 's/\.[0-9]*$//')
    local n3_prefix=$(echo "$N3_SUBNET" | cut -d'/' -f1 | sed 's/\.[0-9]*$//')
    local n4_prefix=$(echo "$N4_SUBNET" | cut -d'/' -f1 | sed 's/\.[0-9]*$//')

    # 현재 기본값: 10.10.2, 10.10.3, 10.10.4
    local old_n2="10.10.2" old_n3="10.10.3" old_n4="10.10.4"

    if [ "$n2_prefix" != "$old_n2" ] || [ "$n3_prefix" != "$old_n3" ] || [ "$n4_prefix" != "$old_n4" ]; then
        log "  Syncing IPs: N2=$n2_prefix, N3=$n3_prefix, N4=$n4_prefix"
        find "$SCRIPT_DIR" -name "*.yaml" -exec sed -i \
            -e "s|$old_n2\.|${n2_prefix}.|g" \
            -e "s|$old_n3\.|${n3_prefix}.|g" \
            -e "s|$old_n4\.|${n4_prefix}.|g" {} \;
        ok "IPs synced to new subnets"
    else
        ok "IP subnets already match (N2=$n2_prefix, N3=$n3_prefix, N4=$n4_prefix)"
    fi
}

# ════════════════════════════════════════════
# 3. 배포
# ════════════════════════════════════════════
deploy() {
    log "=== Deploying to namespace: $NAMESPACE ==="
    kubectl create namespace "$NAMESPACE" 2>/dev/null || true

    # 1) MongoDB
    log "  [1/6] MongoDB"
    kubectl apply -k "$SCRIPT_DIR/mongodb" -n "$NAMESPACE"
    kubectl wait --for=condition=ready pod -l app=mongodb -n "$NAMESPACE" --timeout=60s

    # 2) Network Attachments (ipvlan)
    log "  [2/6] NetworkAttachmentDefinitions"
    kubectl apply -k "$SCRIPT_DIR/networks5g" -n "$NAMESPACE"

    # 3) Free5GC Core
    log "  [3/6] Free5GC Core"
    kubectl apply -k "$SCRIPT_DIR/free5gc" -n "$NAMESPACE"

    # 4) WebUI
    log "  [4/6] Free5GC WebUI"
    kubectl apply -k "$SCRIPT_DIR/free5gc-webui" -n "$NAMESPACE"

    # 5) UERANSIM gNB
    log "  [5/7] UERANSIM gNB"
    kubectl apply -k "$SCRIPT_DIR/ueransim/ueransim-gnb" -n "$NAMESPACE"
    sleep 10

    # 6) UERANSIM UEs
    log "  [6/7] UERANSIM UEs"
    kubectl apply -k "$SCRIPT_DIR/ueransim/ueransim-ue" -n "$NAMESPACE"

    # 7) NWDAF (replicas=0, test job에서 on/off)
    log "  [7/7] NWDAF (deployed OFF — scale to 1 to enable)"
    kubectl apply -k "$SCRIPT_DIR/nwdaf" -n "$NAMESPACE"

    ok "Deployment complete (NWDAF: off — use 'kubectl scale deploy/nwdaf -n free5gc --replicas=1' to enable)"
}

# ════════════════════════════════════════════
# 4. 상태 확인
# ════════════════════════════════════════════
status() {
    kubectl get pods -n "$NAMESPACE" -o wide | grep -v "Evicted"
}

# ════════════════════════════════════════════
# Main
# ════════════════════════════════════════════
case "${1:-all}" in
    check)  check_images ;;
    config) update_config ;;
    deploy) deploy ;;
    all)
        check_images
        update_config
        deploy
        ;;
    status) status ;;
    *)
        echo "Usage: $0 [check|config|deploy|all|status]"
        echo "  check  - 로컬 이미지 존재 확인"
        echo "  config - yaml 설정 수정 (인터페이스, imagePullPolicy)"
        echo "  deploy - k8s 배포"
        echo "  all    - 전체 (기본값)"
        echo "  status - pod 상태 확인"
        echo ""
        echo "환경변수:"
        echo "  NET_IFACE  - ipvlan master 인터페이스 (default: enp0s6)"
        echo "  N2_SUBNET  - N2 대역 (default: 10.10.2.0/24)"
        echo "  N3_SUBNET  - N3 대역 (default: 10.10.3.0/24)"
        echo "  N4_SUBNET  - N4 대역 (default: 10.10.4.0/24)"
        ;;
esac
