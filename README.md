# free5gc-k8s-arm

Deploy free5GC 5G core network on ARM64 Kubernetes.  
Single script `arm_init/setup.sh` runs the full pipeline from source build to UE packet core connectivity.

## Structure

```
free5gc-k8s-arm/
├── arm_init/
│   ├── pre-setup.sh        # Cluster setup (one-time)
│   └── setup.sh            # Full pipeline entrypoint
├── arm_docker/             # Docker image sources
│   ├── core_images/        #   NF (nrf,amf,ausf,pcf,udr,udm,nssf,smf,upf,curl)
│   └── ran_images/         #   UERANSIM
├── arm_k8s/                # Kubernetes manifests
│   ├── mongodb/
│   ├── networks5g/         #   Multus ipvlan NAD (N2,N3,N4)
│   ├── free5gc/            #   Core NF deployments
│   ├── free5gc-webui/
│   ├── ueransim/           #   gNB + UE
│   └── subscriber/         #   MongoDB subscriber registration
├── arm_script/             # Test & utility scripts
│   └── test-connectivity.sh
└── free5gc_build/          # free5gc source (git-ignored)
```

## Prerequisites

- ARM64 Kubernetes cluster (kubeadm, k3s, etc.)
- Multus CNI with ipvlan support
- Docker + containerd
- Go toolchain (for NF binary compilation)
- free5gc source at `/home/ubuntu/free5gc_build/free5gc`

## Usage

### 1. Cluster setup (one-time)

```bash
./arm_init/pre-setup.sh
```

Installs: containerd, Docker, kubeadm, kubectl, Flannel, Multus, Go.  
Configures: ip_forward, rp_filter=0, br_netfilter, swap off.

### 2. Full pipeline

```bash
./arm_init/setup.sh
```

### Specify version

```bash
./arm_init/setup.sh v3.4.3
```

### Custom network config

```bash
NET_IFACE=eth0 \
N2_SUBNET=192.168.2.0/24 \
N3_SUBNET=192.168.3.0/24 \
N4_SUBNET=192.168.4.0/24 \
./arm_init/setup.sh
```

## Pipeline Phases

| Phase | Description |
|-------|-------------|
| 1. Docker | Build NF binaries → Docker images → containerd import |
| 2. K8s | Load gtp5g → configure NAD/IPs → deploy MongoDB → Core → WebUI → gNB → UE |
| 3. Subscriber | Register UE subscriber data in MongoDB |

## Network Architecture

```
Calico (default CNI) → Pod-to-pod SBI communication
Multus + ipvlan      → 5G plane interfaces
  ├── N2 (10.10.2.0/24): AMF ↔ gNB (NGAP signaling)
  ├── N3 (10.10.3.0/24): UPF ↔ gNB (GTP-U user data)
  └── N4 (10.10.4.0/24): SMF ↔ UPF (PFCP control)
```

## Verify

```bash
./arm_script/test-connectivity.sh
```

Tests: pod status → gNB NGAP → UE registration → PDU session → end-to-end ping.

## Individual Scripts

```bash
./arm_k8s/setup.sh all                        # K8s deploy only
./arm_k8s/subscriber/add-subscribers.sh list   # List subscribers
./arm_k8s/subscriber/add-subscribers.sh add    # Add subscribers
```

## License

[MIT License](LICENSE)
