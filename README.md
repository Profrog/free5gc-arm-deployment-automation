# free5gc-k8s-arm

ARM64 환경에서 free5GC 5G 코어 네트워크를 소스 레벨부터 수정하고, 빌드 → Docker 이미지 → K8s 배포까지 한 번에 돌려서 바로 동작을 확인할 수 있는 개발/테스트 환경입니다.

추가로, **NWDAF ML 모델 기반 동적 CNI 전환(DRANET)** 연구 환경을 포함합니다.

**핵심 워크플로우:**
```
소스 수정 → 빌드 → Docker → K8s 배포 → NWDAF/DRANET 실험 → 결과 분석
```

## Research: NWDAF + DRANET Dynamic CNI Switching

NWDAF(Network Data Analytics Function)가 UPF의 KPI를 ML로 분석하여, DRANET을 통해 CNI backend(ipvlan↔macvlan)를 런타임에 동적 전환하는 closed-loop 시스템.

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  NWDAF AnLF │────>│  ML 분류    │────>│   DRANET    │
│ (KPI 수집)  │     │(ipvlan/mac) │     │(전환 실행)  │
└─────────────┘     └─────────────┘     └─────────────┘
       │                                        │
   kubectl top                          ResourceClaim
   /proc/net/dev                        DeviceClass 변경
```

## Structure

```
free5gc-k8s-arm/
├── arm_init/                # 인프라 + 빌드 파이프라인
│   ├── infra-setup.sh       #   K8s, Docker, CNI, Go 설치
│   ├── clone-source.sh      #   NF 소스 clone
│   ├── build.sh             #   NF 바이너리 빌드
│   ├── docker-build.sh      #   Docker 이미지 빌드 (NWDAF 포함)
│   └── deploy.sh            #   K8s 배포
├── free5gc_source/          # NF별 소스 코드
├── free5gc_build/           # 빌드된 바이너리
├── arm_docker/              # Docker image sources
├── arm_k8s/                 # Kubernetes manifests
│   ├── mongodb/
│   ├── networks5g/          #   Multus NAD (레거시, DRANET으로 교체 예정)
│   ├── free5gc/             #   Core NF deployments
│   ├── free5gc-webui/
│   ├── ueransim/            #   gNB + UE
│   ├── subscriber/
│   ├── dranet/              #   ★ DRANET (DeviceClass, ResourceClaim, 전환 스크립트)
│   └── nwdaf/               #   ★ NWDAF NF (ML 엔진, 모델, Dockerfile, K8s manifests)
├── traffic-profiles/        # ★ 트래픽 생성 + 실험 프레임워크
│   ├── profiles/            #   트래픽 프로파일 (APN, 시나리오)
│   ├── experiments/         #   실험 매트릭스 정의 (9개 YAML)
│   ├── generator/           #   트래픽 생성기 스크립트
│   ├── monitor/             #   모니터링 (per-CPU, packet loss, anomaly detection)
│   ├── k8s/                 #   트래픽 Job manifests
│   ├── references.bib       #   논문 참고문헌
│   ├── REFERENCES.md        #   연구 근거 정리 (방어 포인트별)
│   └── run.sh               #   실험 실행 런처
├── CI_channel/              # Gerrit + Jenkins CI
└── arm_service/             # 연결성 테스트 스크립트
```

## Quick Start

### 1. 인프라 + 5GC 배포

```bash
./arm_init/infra-setup.sh          # K8s, Docker, Go (one-time)
./arm_init/clone-source.sh         # NF 소스 clone
./arm_init/build.sh                # NF 바이너리 빌드
./arm_init/docker-build.sh         # Docker 이미지 (NWDAF 포함)
./arm_k8s/setup.sh all             # K8s 배포 (7단계, NWDAF는 OFF 상태)
```

### 2. NWDAF 모델 학습

```bash
cd arm_k8s/nwdaf/src
python3 train-model.py             # 합성 데이터 기반 RandomForest 학습
```

### 3. 실험 실행

```bash
cd traffic-profiles

# 단일 실험
./run.sh --experiment experiments/experiment-c-t3.yaml

# 전체 매트릭스 (9개)
for f in experiments/experiment-*.yaml; do
    ./run.sh --experiment "$f"
done
```

### 4. NWDAF 수동 제어

```bash
./arm_k8s/dranet/nwdaf-switch.sh on       # NWDAF 활성화
./arm_k8s/dranet/nwdaf-switch.sh off      # NWDAF 비활성화
./arm_k8s/dranet/nwdaf-switch.sh ipvlan   # CNI 수동 전환
./arm_k8s/dranet/nwdaf-switch.sh macvlan  # CNI 수동 전환
./arm_k8s/dranet/nwdaf-switch.sh status   # 현재 상태 확인
```

## Experiment Matrix

```
            A. ipvlan 고정    B. macvlan 고정    C. NWDAF 동적 전환
T1 대규모        ✓                 ✓                  ✓
T2 소규모        ✓                 ✓                  ✓
T3 소→대         ✓                 ✓                  ✓ (핵심)
```

- A, B: baseline (ground truth)
- C-T3: **핵심 실험** — NWDAF가 트래픽 패턴 변화를 감지하고 전환 판단

## NWDAF Architecture (3GPP TS 23.288 Rel-17)

| 기능 | 구현 | 파일 |
|------|------|------|
| AnLF (추론) | ✅ | `arm_k8s/nwdaf/src/nwdaf-engine.py` |
| MTLF (학습) | ✅ | `arm_k8s/nwdaf/src/train-model.py` |
| ML Model | RandomForest | `arm_k8s/nwdaf/src/model/nwdaf-classifier.pkl` |
| 전환 실행 | DRANET | `arm_k8s/dranet/nwdaf-switch.sh` |
| 데이터 수집 | OAM 경로 | kubectl top + /proc/net/dev |

## Network Architecture

```
Calico (default CNI)  → Pod-to-pod SBI communication
DRANET (ipvlan/macvlan) → 5G data plane interfaces
  ├── N3 (10.10.3.0/24): UPF ↔ gNB (GTP-U user data)
  └── N4 (10.10.4.0/24): SMF ↔ UPF (PFCP control)
```

## CPU Isolation (Experiment)

```
CPU 0, 1  →  UPF 전용 (Guaranteed QoS, CPU Manager static)
CPU 2     →  traffic-gen 전용
CPU 3     →  나머지 (NFs, NWDAF, monitor, kubelet)
```

## Prerequisites

- ARM64 Kubernetes cluster (kubeadm, **v1.32+** for DRA/DRANET)
- DRANET DaemonSet
- containerd with NRI enabled
- Docker + Go toolchain
- Python 3.11+ (numpy, scikit-learn, joblib)

## References

연구 근거 및 논문 참고문헌: [`traffic-profiles/REFERENCES.md`](traffic-profiles/REFERENCES.md)

## License

[MIT License](LICENSE)
