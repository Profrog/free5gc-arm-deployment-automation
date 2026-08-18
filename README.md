# free5gc-k8s-arm

ARM64 환경에서 free5GC 5G 코어 네트워크를 소스 레벨부터 수정하고, 빌드 → Docker 이미지 → K8s 배포까지 한 번에 돌려서 바로 동작을 확인할 수 있는 개발/테스트 환경입니다.

추가로, **NWDAF(Random Forest) 기반 동적 CNI 전환 시점 판단** 연구 환경을 포함합니다.

**핵심 워크플로우:**
```
소스 수정 → 빌드 → Docker → K8s 배포 → NWDAF 실험 → 결과 분석
```

## Research: NWDAF + Zero-Downtime CNI Backend Switching

NWDAF(Network Data Analytics Function)가 UPF의 KPI를 ML로 분석하여, 커널 수준 IP 이동(`ip -batch`)으로 CNI backend(ipvlan↔macvlan)를 Pod 재시작 없이 무중단 전환하는 closed-loop 시스템.

### 전환 메커니즘

UPF Pod에 macvlan과 ipvlan 인터페이스를 **동시에 미리 attach**(Multus)하고, NWDAF의 판단에 따라 IP 주소를 인터페이스 간 이동하여 전환합니다. UPF 프로세스 재시작 없이 커널 레벨에서 패킷 경로만 변경됩니다.

```
┌─────────────┐     ┌─────────────┐     ┌──────────────────┐
│  NWDAF AnLF │────>│  ML 분류    │────>│  ip -batch 실행  │
│ (KPI 수집)  │     │(ipvlan/mac) │     │ (커널 IP 이동)   │
└─────────────┘     └─────────────┘     └──────────────────┘
       │                                        │
   kubectl top                          ip addr del/add
   /proc/net/dev                        (netlink → 커널 메모리)
```

### 왜 이 방식인가

| | Pod 재생성 | Multus Dynamic | 본 프로젝트 (IP 이동) |
|--|-----------|----------------|---------------------|
| IP 변경 | ⭕ | ⭕ | ❌ (불변) |
| GTP-U/PFCP 세션 | 끊김 | 끊김 위험 | 유지 |
| 전환 시간 | 수 초 | 수 초 | ~140ms |
| UPF 재시작 | 필요 | 가능 | 불필요 |

## Structure

```
free5gc-k8s-arm/
├── arm_init/                # 인프라 + 빌드 파이프라인
│   ├── infra-setup.sh       #   K8s, Docker, CNI, Go 설치
│   ├── clone-source.sh      #   NF 소스 clone
│   ├── build.sh             #   NF 바이너리 빌드
│   ├── docker-build.sh      #   Docker 이미지 (NWDAF 포함)
│   └── deploy.sh            #   K8s 배포
├── free5gc_source/          # NF별 소스 코드 (gtp5g 포함)
├── free5gc_build/           # 빌드된 바이너리
├── arm_docker/              # Docker image sources
├── arm_k8s/                 # Kubernetes manifests
│   ├── mongodb/
│   ├── networks5g/          #   Multus NAD (ipvlan + macvlan dual-attach)
│   ├── free5gc/             #   Core NF deployments
│   ├── free5gc-webui/
│   ├── free5gc-metrics/     #   메트릭 수집 설정
│   ├── ueransim/            #   gNB + UE
│   ├── subscriber/
│   └── nwdaf/               #   ★ NWDAF NF (ML 엔진, 모델, 전환 스크립트, K8s manifests)
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

# 전체 실험 매트릭스 (3×3 = 9개 조합)
for f in experiments/experiment-*.yaml; do
    ./run.sh --experiment "$f"
done
```

### 4. CNI 전환 제어

```bash
./arm_k8s/nwdaf/nwdaf-switch.sh on       # NWDAF 자동 전환 활성화
./arm_k8s/nwdaf/nwdaf-switch.sh off      # NWDAF 비활성화
./arm_k8s/nwdaf/nwdaf-switch.sh ipvlan   # CNI 수동 전환 (ip addr 이동)
./arm_k8s/nwdaf/nwdaf-switch.sh macvlan  # CNI 수동 전환 (ip addr 이동)
./arm_k8s/nwdaf/nwdaf-switch.sh status   # 현재 상태 확인
```

### 5. 모니터링

```bash
# 실험과 동시에 수집 (5초 간격, 백그라운드)
./traffic-profiles/monitor/monitor-collector.sh --interval 5 --background

# 중지
./traffic-profiles/monitor/monitor-collector.sh --stop
```

### 6. 빠른 Baseline 테스트 (모니터링 자동 포함)

```bash
cd traffic-profiles

# macvlan 60초 (CNI 전환 + 모니터링 + iperf3 + 결과 저장)
./quick-test.sh macvlan 60

# ipvlan 60초
./quick-test.sh ipvlan 60

# 결과: monitor-data/{cni}_{timestamp}/
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

## Network Architecture

```
                    enp0s6 (물리 NIC — 커널-하드웨어 인터페이스)
                       │
         ┌─────────────┼──────────────┐
         │             │              │
      n3br (bridge)  n3br-ipv (bridge)
         │             │
   macvlan: UPF n3   ipvlan: UPF n3i     ← 둘 다 미리 attach
         │             │
         └──── veth pair ────┘            ← 같은 L2 도메인
                       │
              IP: 10.10.3.1/24            ← 한 쪽에만 존재, 전환 시 이동

Calico (default CNI)   → Pod-to-pod SBI communication
Multus + ipvlan/macvlan → 5G data plane interfaces
  ├── N3 (10.10.3.0/24): UPF ↔ gNB (GTP-U user data)
  ├── N4 (10.10.4.0/24): SMF ↔ UPF (PFCP control)
  └── N6: UPF ↔ DN (일반 IP)
```

## NWDAF Architecture (3GPP TS 23.288 Rel-17)

| 기능 | 구현 | 파일 |
|------|------|------|
| AnLF (추론) | ✅ | `arm_k8s/nwdaf/src/nwdaf-engine.py` |
| MTLF (학습) | ✅ | `arm_k8s/nwdaf/src/train-model.py` |
| ML Model | RandomForest (5 features) | `arm_k8s/nwdaf/src/model/nwdaf-classifier.pkl` |
| 전환 실행 | `ip -batch` (커널 IP 이동) | `arm_k8s/nwdaf/nwdaf-switch.sh` |
| 데이터 수집 | OAM 경로 | kubectl top + /proc/net/dev |

### ML Features

| Feature | 역할 |
|---------|------|
| throughput_mbps | 현재 처리량 |
| total_pps | 초당 패킷 수 |
| packet_loss_pct | 패킷 손실률 — 현재 CNI 한계 감지 |
| cpu_milli | UPF CPU 사용량 |
| mem_mi | UPF 메모리 사용량 |

## Monitoring

### 목적

1. **NWDAF 입력 데이터 제공** — ML 모델이 전환 판단에 사용하는 KPI (throughput, loss, CPU)를 실시간 수집
2. **전환 판단 검증** — CNI 전환 전후 KPI 비교로 NWDAF 판단의 정확성 평가
3. **격리 유효성 + 실험 재현성** — per-CPU 시계열로 코어 간 간섭 없음 확인, 실험 조건을 metadata로 기록

### 수집 항목

| 카테고리 | 수집 대상 | 소스 | 출력 |
|----------|----------|------|------|
| 리소스 | CPU(milli), Memory(Mi) per Pod | `kubectl top pods` | `pods/{name}/resources.jsonl` |
| 패킷 통계 | rx/tx packets, drop, loss% | `/proc/net/dev` (upfgtp, eth0) | `pods/{name}/packet_loss.jsonl` |
| per-CPU | 코어별 busy/total ticks | `/proc/stat` | `system/per_cpu.jsonl` |
| 이벤트 | CNI 전환 시점, from/to | nwdaf-switch.sh | `events.jsonl` |

### 출력 구조

```
monitor-data/run_20260811_041000/
├── metadata.json              # 실험 조건 (interval, duration, k8s version)
├── system/
│   └── per_cpu.jsonl          # 코어별 사용량 시계열
├── pods/
│   ├── upf-xxx/
│   │   ├── resources.jsonl    # CPU/Memory 시계열
│   │   └── packet_loss.jsonl  # 패킷 통계 시계열
│   └── ...
└── events.jsonl               # CNI 전환 이벤트 마커
```

### 분석 도구

| 도구 | 역할 |
|------|------|
| `monitor-visualize.py` | 시계열 그래프 생성 (throughput, loss, per-CPU) |
| `monitor-detect.py` | 이상 탐지 (anomaly detection) |
| `app.py` | Streamlit 웹 대시보드 (수집 결과 시각화) |

```bash
# 대시보드 실행 (수집 완료 후)
cd traffic-profiles/monitor
streamlit run app.py --server.port 8501
# → http://<서버IP>:8501 에서 확인
```

대시보드 기능:
- Pod별 CPU/Memory 시계열 차트
- UPF Packet Loss 추이
- Anomaly Detection 결과 오버레이
- Run 간 비교 (A-T1 vs B-T1 등)

### 격리 검증

- **per-CPU 시계열**: CPU 2,3(시스템 코어)이 실험 조건에 무관하게 flat → 격리 성공
- **steal time**: 전 실험 구간에서 < 1% → 가상화 간섭 없음 확인

## Baseline Experiment Results (동작 검증)

테스트 환경에서 CNI 전환에 따른 KPI 차이가 실측으로 확인됨.

### A-T1 vs B-T1: 대규모 트래픽 (UDP 500Mbps, 1400B, 60초)

| 항목 | A-T1 (macvlan) | B-T1 (ipvlan) | 차이 |
|------|---------------|--------------|------|
| Offered | 500 Mbps | 500 Mbps | — |
| Receiver throughput | 498 Mbps | 489 Mbps | macvlan +9 Mbps |
| Packet loss | 0.28% (7,436) | 2.1% (55,021) | macvlan이 7.4× 낮음 |
| Jitter | 0.005 ms | 0.005 ms | 동일 |

**결론**: 대규모 트래픽에서 macvlan이 유리 (선행연구 예측 일치). CNI 전환의 실효성 확인.

전환 시간: macvlan → ipvlan **134ms** (ip -batch, 무중단)

로그 위치: [`traffic-profiles/baseline-results/`](traffic-profiles/baseline-results/)

## Key Design Decisions

| 결정 | 이유 |
|------|------|
| 커널 IP 이동 (DRANET 미채택) | DRANET은 ipvlan↔macvlan 서브인터페이스 전환 미지원 |
| dual-bridge 구조 | 커널이 같은 master에 macvlan+ipvlan 동시 생성 불가 → 별도 bridge + veth pair |
| OAM 수집 경로 | free5GC에 Nupf Event Exposure 미구현 + 측정 대상 성능 무영향 |
| Random Forest | ARM64 추론 <1ms, feature importance 해석 가능, 학계 선례 |
| ARM64 플랫폼 | 커널 경로 차이에 따른 KPI 변화가 x86보다 크게 관측됨 → 실험 민감도 향상 |

## Infrastructure Spec

| 항목 | 스펙 |
|------|------|
| Cloud | Oracle Cloud Infrastructure (OCI) |
| Region | ap-chuncheon-1 (춘천) |
| Instance | VM.Standard.A1.Flex |
| CPU | ARM Neoverse-N1, 4 vCPU |
| Memory | 24 GB |
| OS | Ubuntu 22.04.5 LTS |
| Kernel | 6.8.0-1058-oracle (aarch64) |
| NIC | enp0s6 (virtio-net) |

### CPU 할당

```
CPU 0, 1  →  UPF 전용 (K8s CPU Manager static policy)
CPU 2     →  traffic-gen (iperf3)
CPU 3     →  시스템 (NFs, NWDAF, monitor, kubelet)
```

단일 노드 4코어 환경에서 격리 실험 수행. IETF BMWG "consistent CPU pinning" 준수.

## Prerequisites

- ARM64 Linux (tested: Ubuntu 22.04 on OCI A1.Flex)
- Kubernetes v1.28+ (kubeadm)
- Multus CNI
- containerd
- Docker + Go toolchain (for source build)
- Python 3.11+ (numpy, scikit-learn, joblib)
- gtp5g 커널 모듈 (free5GC UPF용)

## References

연구 계획서: [`reference/PROPOSAL.md`](reference/PROPOSAL.md)

선행연구 및 설계 결정 근거: [`reference/REFERENCES.md`](reference/REFERENCES.md)

## License

[MIT License](LICENSE)
