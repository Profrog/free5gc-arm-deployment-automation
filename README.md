# free5gc-k8s-arm

ARM64 환경에서 free5GC 5G 코어 네트워크를 소스 레벨부터 수정하고, 빌드 → Docker 이미지 → K8s 배포까지 한 번에 돌려서 바로 동작을 확인할 수 있는 개발/테스트 환경입니다.

**핵심 워크플로우:**
```
소스 수정 (free5gc_source/) → 빌드 (build.sh) → Docker (docker-build.sh) → K8s 배포 (deploy.sh) → 테스트 확인
```

NF(AMF, SMF 등) 코드를 수정한 뒤 스크립트 몇 개만 실행하면, 수정된 코드가 반영된 5G 코어가 K8s 위에서 동작하고 UERANSIM으로 UE 등록 ~ end-to-end ping까지 검증할 수 있습니다.

## Structure

```
free5gc-k8s-arm/
├── arm_init/
│   ├── infra-setup.sh      # 1. 인프라 setup (K8s, Docker, CNI 등)
│   ├── clone-source.sh     # 2. NF 소스 clone (GitHub → free5gc_source/)
│   ├── build.sh            # 3. NF 바이너리 빌드 (free5gc_source → free5gc_build)
│   ├── docker-build.sh     # 4. Docker 이미지 빌드 + containerd import
│   └── deploy.sh           # 5. K8s 배포
├── free5gc_source/         # NF별 소스 코드 (git clone)
│   ├── nrf/                #   https://github.com/free5gc/nrf
│   ├── amf/                #   https://github.com/free5gc/amf
│   ├── ausf/               #   https://github.com/free5gc/ausf
│   ├── pcf/                #   https://github.com/free5gc/pcf
│   ├── udr/                #   https://github.com/free5gc/udr
│   ├── udm/                #   https://github.com/free5gc/udm
│   ├── nssf/               #   https://github.com/free5gc/nssf
│   ├── smf/                #   https://github.com/free5gc/smf
│   └── upf/                #   https://github.com/free5gc/go-upf
├── free5gc_build/          # 빌드된 바이너리 ({nf}/{nf})
├── arm_docker/             # Docker image sources
│   ├── core_images/        #   NF Dockerfile + binary
│   └── ran_images/         #   UERANSIM
├── arm_k8s/                # Kubernetes manifests
│   ├── mongodb/
│   ├── networks5g/         #   Multus ipvlan NAD (N2,N3,N4)
│   ├── free5gc/            #   Core NF deployments
│   ├── free5gc-webui/
│   ├── ueransim/           #   gNB + UE
│   └── subscriber/         #   MongoDB subscriber registration
├── arm_service/            # Test & utility scripts
│   └── test-connectivity.sh
└── build/                  # gtp5g kernel module
```

## Prerequisites

- ARM64 Kubernetes cluster (kubeadm, k3s, etc.)
- Multus CNI with ipvlan support
- Docker + containerd
- Go toolchain (for NF binary compilation)

## Usage

### 1. 인프라 setup (one-time)

```bash
./arm_init/infra-setup.sh
```

Installs: containerd, Docker, kubeadm, kubectl, Flannel, Multus, Go.

### 2. Clone NF sources

```bash
./arm_init/clone-source.sh
```

특정 버전으로 clone:
```bash
./arm_init/clone-source.sh v3.4.3
```

### 3. Build NF binaries

```bash
./arm_init/build.sh
```

특정 NF만 빌드:
```bash
./arm_init/build.sh amf smf
```

### 4. Docker 이미지 빌드

```bash
./arm_init/docker-build.sh
```

특정 NF만 이미지 빌드:
```bash
./arm_init/docker-build.sh amf smf
```

### 5. K8s 배포

```bash
./arm_init/deploy.sh
```

Custom network config:
```bash
NET_IFACE=eth0 \
N2_SUBNET=192.168.2.0/24 \
N3_SUBNET=192.168.3.0/24 \
N4_SUBNET=192.168.4.0/24 \
./arm_init/setup.sh
```

## Workflow

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│clone-source  │──>│   build.sh   │──>│docker-build  │──>│  deploy.sh   │──>│    test-     │
│   .sh        │   │              │   │   .sh        │   │              │   │connectivity  │
│GitHub→source │   │source→binary │   │binary→Docker │   │  K8s 배포    │   │   .sh        │
└──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
```

### NF 소스 수정 시

1. `free5gc_source/{nf}/` 에서 코드 수정
2. `./arm_init/build.sh {nf}` — 해당 NF만 재빌드
3. `./arm_init/docker-build.sh {nf}` — 해당 NF 이미지만 재빌드
4. `./arm_init/deploy.sh` — K8s 재배포

## Pipeline Phases

| Phase | Script | Description |
|-------|--------|-------------|
| 1. Infra | infra-setup.sh | K8s, Docker, CNI, Go 설치 (one-time) |
| 2. Source | clone-source.sh | NF별 GitHub 레포 clone |
| 3. Build | build.sh | Go/C++ 바이너리 빌드 |
| 4. Docker | docker-build.sh | Docker 이미지 빌드 → containerd import |
| 5. Deploy | deploy.sh | K8s 배포 + subscriber 등록 |

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
./arm_service/test-connectivity.sh
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
