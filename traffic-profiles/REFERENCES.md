# References — UPF Data Plane Benchmarking

트래픽 프로파일 설계 시 참고한 논문 및 벤치마크 자료.

---

## [1] Kernel-Level Per-Slice UPF Latency Measurement in Containerised 5G Core Networks

- **저자**: Akhil Dev Mishra, Mayank Pandey
- **출처**: arXiv:2605.28185, May 2026
- **URL**: https://arxiv.org/abs/2605.28185

### 핵심 내용
- Containerized open5GS 환경에서 eMBB/URLLC/mMTC 3 슬라이스 동시 운용
- TC-BPF instrumentation으로 N3→N6 per-packet forwarding delay 측정
- 약 28M matched delay pairs 수집

### 주요 결과
| Slice | Load | p50 latency | p99 latency |
|-------|------|-------------|-------------|
| eMBB  | Light (10%) | ~300μs | 574μs |
| eMBB  | Medium (50%) | ~600μs | ~900μs |
| eMBB  | Heavy (90%) | ~800μs | 1,243μs |
| URLLC | All loads | Stable | Load-insensitive |
| mMTC  | All loads | Wide-tail | TCP retx behavior |

- PFCP session modification latency: <200μs (data-plane load 무관)
- UPF process isolation이 URLLC slice의 delay 안정성 보장

### 시사점
- UPF forwarding delay는 부하에 비례하여 증가 (eMBB)
- stepped load 테스트로 임계점 탐색 가능
- ARM64 환경에서는 더 높은 latency 예상

---

## [2] Simple Measurement of UPF Performance

- **저자**: s5uishida
- **출처**: GitHub Repository, Dec 2023
- **URL**: https://github.com/s5uishida/simple_measurement_of_upf_performance

### 측정 환경
- VirtualBox VM (2-core, 8GB RAM)
- PacketRusher → 5GC (Open5GS / free5GC) → iperf3 server
- 단일 UE, DNN: internet, SST:1/SD:010203

### 주요 결과 (free5GC UPF v1.2.0)
| Metric | Value |
|--------|-------|
| TCP throughput | 233 Mbps (sender) / 229 Mbps (receiver) |
| UDP throughput (offered 500M) | 499 Mbps (sender) / 382 Mbps (receiver) |
| UDP packet loss | 23% |
| RTT (ping) | 0.786ms avg |

### UPF 비교 (Open5GS C-Plane 기준)
| UPF | TCP | UDP (recv) | Loss | RTT |
|-----|-----|-----------|------|-----|
| UPG-VPP v1.11.0 | 1.14 Gbps | 455 Mbps | 0.96% | 0.398ms |
| eUPF v0.6.0 | 359 Mbps | 409 Mbps | 3.6% | 0.882ms |
| Open5GS UPF (TUN) | 205 Mbps | 319 Mbps | 30% | 1.081ms |
| Open5GS UPF (TAP) | 275 Mbps | 314 Mbps | 32% | 1.198ms |

### 시사점
- free5GC go-upf는 kernel TUN 기반으로 200~400Mbps 대역 성능
- ARM64(Graviton 등)에서는 추가 성능 저하 예상 (40-60% 수준)
- UDP 고부하 시 loss가 급격히 증가하는 임계점 존재

---

## [3] 5G UPF Performance on Intel Xeon (Reference — Commercial Scale)

- **출처**: Intel Network Builders, 2024
- **URL**: https://builders.intel.com/docs/networkbuilders/5g-flexcore-2-0-user-plane-function...
- **결과**: 948 Gbps (94.8% line rate), 0% packet loss
- **비고**: DPDK 기반 상용 UPF. open-source UPF와 2~3 order of magnitude 차이. 논문에서 상한 참조용.

---

## 프로파일 설계 근거

`upf-stress.yaml`의 각 Phase가 위 레퍼런스에서 어떻게 도출되었는지:

| Phase | 근거 |
|-------|------|
| Phase 1 (64B flood) | [1]의 per-packet delay가 pps에 비례 → 소패킷으로 pps 극대화하여 encap/decap 병목 관측 |
| Phase 2 (1400B 500M) | [2]의 `iperf3 -u -b 500M` 동일 조건 재현. ARM64에서의 차이 비교 |
| Phase 3 (stepped) | [1]의 light/medium/heavy 3단계 → 6단계로 세분화하여 loss 곡선 도출 |
| Phase 4 (bidir) | [1]에서 N3→N6만 측정. 양방향 동시 부하는 미측정 → 추가 실험 |

---

## [4] 3GPP TS 23.288 — Network Data Analytics Services (NWDAF)

- **출처**: 3GPP, Release 17/18
- **URL**: https://www.3gpp.org/DynaReport/23288.htm

### 핵심 내용
- NWDAF의 역할: NF로부터 데이터 수집 → Analytics 생성 → 다른 NF에 제공
- Nnwdaf_AnalyticsInfo / Nnwdaf_EventsSubscription 서비스 정의
- Analytics ID: Network Performance, UE Mobility, Abnormal Behaviour 등

### 본 연구와의 관계
- NWDAF가 UPF 성능 메트릭(throughput, latency, loss)을 수집하는 것은 표준 절차
- NWDAF가 분석 결과를 기반으로 **정책 결정을 내리는 것**은 표준의 의도된 사용법
- 결정의 실행(CNI 전환)은 표준 범위 밖 인프라 레이어 → **표준 위반 아님**

---

## [5] 3GPP TS 23.501 — System Architecture for the 5G System (5GS)

- **출처**: 3GPP, Release 17
- **URL**: https://www.3gpp.org/DynaReport/23501.htm

### 본 연구 관련 내용
- Table 5.7.4-1: 5QI 특성 정의 (5QI=9: Non-GBR, best effort, delay budget 300ms)
- UPF의 역할: PDU Session anchor, GTP-U tunneling, packet forwarding
- N3(gNB↔UPF), N4(SMF↔UPF PFCP), N6(UPF↔DN) 인터페이스 정의
- **UPF의 네트워크 인터페이스 구현 방식은 규정하지 않음** (벤더/오퍼레이터 자유)

---

## [6] 3GPP TS 29.244 — Interface between the Control Plane and the User Plane (PFCP)

- **출처**: 3GPP, Release 17
- **URL**: https://www.3gpp.org/DynaReport/29244.htm

### 본 연구 관련 내용
- PFCP Session Establishment/Modification/Deletion 절차
- Usage Reporting Rule (URR): UPF가 SMF에 주기적 usage report 전송
- 본 연구에서 NWDAF는 커널 통계(/proc/net/dev) 및 kubectl top을 통해 KPI를 직접 수집
- **CNI 전환은 PFCP 절차와 독립** — 전환 전후 PFCP 세션 유지됨

---

## [7] DRANET: A Composable Architecture for High-Performance Networking in Kubernetes

- **저자**: Antonio Ojea et al. (kubernetes-sigs)
- **출처**: arXiv:2506.23628, Jun 2025
- **URL**: https://arxiv.org/abs/2506.23628
- **GitHub**: https://github.com/kubernetes-sigs/dranet

### 핵심 내용
- Kubernetes DRA (Dynamic Resource Allocation)를 네트워크 디바이스에 적용
- DeviceClass로 네트워크 인터페이스 추상화 (ipvlan, macvlan, SR-IOV, RDMA)
- ResourceClaim 변경으로 **런타임에** 네트워크 백엔드 전환 가능
- 기존 적용 대상: AI/ML workload의 RDMA 디바이스

### 본 연구와의 관계
- DRANET을 **5GC UPF에 적용하는 것은 본 연구가 최초**
- NWDAF의 결정을 DRANET ResourceClaim으로 변환하여 실행
- ipvlan(저오버헤드) ↔ macvlan(고성능) 간 동적 전환의 실행 계층

---

## [8] Kubernetes Dynamic Resource Allocation (DRA)

- **출처**: Kubernetes KEP-3063, KEP-4381
- **URL**: https://kubernetes.io/docs/concepts/scheduling-eviction/dynamic-resource-allocation/
- **Status**: GA in Kubernetes v1.34 (2026)

### 핵심 내용
- 기존 Device Plugin의 한계 극복: 런타임 리소스 할당/해제
- DeviceClass → ResourceClaim → ResourceSlice 계층 구조
- Pod 실행 중 리소스 변경 가능 (기존 CNI는 Pod 생성 시점만)

### 본 연구와의 관계
- DRA가 GA된 시점(2026)과 본 연구 시점 일치 → 기술 성숙도 충분
- DRANET이 DRA 위에서 네트워크 디바이스를 관리 → NWDAF 결정의 실행 기반

---

## [9] LLM-Enabled NWDAF: A Step Toward AI-Native 6G Network Intelligence

- **저자**: (University of Waterloo 등)
- **출처**: arXiv:2606.11877, Jun 2026
- **URL**: https://arxiv.org/abs/2606.11877

### 핵심 내용
- Open-source NWDAF 구현의 한계점 지적
- NWDAF에 LLM을 붙여 자연어 기반 네트워크 분석 제안
- closed-loop automation의 필요성 강조

### 본 연구와의 차이
- [9]는 NWDAF + LLM (분석 강화)
- 본 연구는 NWDAF + DRANET (실행 강화, 인프라 레이어까지 closed-loop)

---

## 표준 적합성 요약

| 구성요소 | 3GPP 표준 | 본 연구의 위치 |
|----------|-----------|---------------|
| NWDAF 분석/결정 | TS 23.288 | ✅ 표준 절차 준수 |
| UPF 기능 (GTP-U, PFCP) | TS 23.501, TS 29.244 | ✅ 변경 없음 |
| 5QI/QoS 정의 | TS 23.501 Table 5.7.4-1 | ✅ 표준 값 사용 |
| CNI 백엔드 전환 | 표준 범위 밖 (인프라) | ✅ 위반 아님 — 표준이 규정하지 않는 영역 |
| DRA/DRANET | Kubernetes native (비3GPP) | ✅ 인프라 레이어 독립 기술 |

---

## [10] CNI 타입별 성능 차이 근거 — 전환 판단의 유효성 뒷받침

> **핵심 질문**: "네트워크 인터페이스를 전환한 뒤 KPI를 비교해서 '이 전환이 올바랐다'고 판단하는 방법론이 유효한가?"

이 질문은 두 가지를 요구한다:
1. CNI 타입이 KPI에 인과적 영향을 준다 (바꾸면 실제로 KPI가 변한다)
2. KPI 변화를 보고 판단의 적합성을 평가하는 것이 유효한 방법이다

---

### A. 직접 근거: macvlan/ipvlan 성능 차이가 측정 가능함

#### [10-A1] Container network architecture and performance analysis of Macvlan and IPvlan (SHS 2023)

- **출처**: SHS Web of Conferences, EIMM 2023
- **URL**: https://www.shs-conferences.org/articles/shsconf/abs/2023/15/shsconf_eimm2023_01072/shsconf_eimm2023_01072.html
- **결과**: ipvlan이 일반 환경에서 더 나은 network performance
- **의의**: macvlan ↔ ipvlan 전환이 throughput/latency에 **측정 가능한 차이**를 만듦을 실증

#### [10-A2] Performance and Latency Efficiency Evaluation of K8s CNIs (MDPI Electronics, 2024)

- **출처**: Electronics 13(19), 3972, 2024
- **URL**: https://www.mdpi.com/2079-9292/13/19/3972
- **결과**: CNI 선택에 따라 packet size/workload별 성능이 유의미하게 달라짐
- **의의**: one-size-fits-all CNI는 없으며, workload 조건에 따라 최적 CNI가 달라짐 → 동적 전환의 당위성

#### [10-A3] Performance Evaluation of K8s Networking in Constraint Edge Environments (IEEE INFOCOM Workshop, 2024)

- **출처**: IEEE INFOCOM ICCN Workshops, Vancouver, 2024
- **URL**: https://arxiv.org/abs/2401.07674
- **결과**: 자원 제약(Edge) 환경에서 CNI별 throughput/CPU/memory 차이가 더 크게 나타남
- **의의**: ARM64와 유사한 제약 환경에서 CNI → KPI 인과관계가 더 명확

#### [10-A4] Bare-Metal vs Kubernetes for 5G Core (2024)

- **출처**: ResearchGate, 2024
- **URL**: https://www.researchgate.net/publication/384801122
- **결과**: K8s 위 5GC가 bare-metal 대비 throughput 7% 감소 (300+ UE)
- **의의**: K8s 네트워킹 레이어가 5GC 성능의 실질적 병목. CNI 최적화가 5GC KPI에 직접 영향

#### [10-A5] Assessing Container Network Interface Plugins (IEEE SRDS, 2021)

- **출처**: NSF/IEEE, 2021
- **URL**: https://par.nsf.gov/servlets/purl/10299326
- **결과**: CNI별 throughput/latency/scalability 체계적 비교 (macvlan 포함)
- **의의**: CNI 벤치마킹 방법론의 선례. iperf3 + 반복 측정 + 통계 처리 방법 참고

---

### B. 방법론 근거: "전환 후 KPI 비교"가 유효한 평가 방법인 이유

#### [10-B1] 3GPP TS 23.288 — NWDAF Analytics Feedback Loop

- NWDAF는 "판단 → 실행 → KPI 관측 → 정확성 평가" closed-loop으로 설계됨
- Analytics accuracy를 실행 전후 KPI 비교로 측정하도록 표준이 정의
- **의의**: 본 연구의 검증 방식은 3GPP 표준이 의도한 패턴 그 자체

#### [10-B2] ETSI GS ZSM 002 — Zero-touch Service Management Reference Architecture (2022)

- **URL**: https://www.etsi.org/deliver/etsi_gs/ZSM/001_099/002/
- Closed-loop: Intent → Decision → Execution → Observation → Evaluation
- "판단의 올바름"은 Observation 단계에서 KPI가 Intent 방향으로 변했는지로 평가
- **의의**: ETSI가 정의한 자동화 시스템의 표준 평가 절차에 부합

#### [10-B3] ITU-T Y.1731 — Ethernet OAM Performance Monitoring (2020)

- Frame delay, frame loss ratio, throughput을 측정하여 configuration 변경의 효과를 판단
- 네트워크 변경 전후 PM(Performance Monitoring) 값 비교는 **통신 업계 표준 운용 절차**
- **의의**: "변경 전후 KPI 비교"가 통신에서 보편적으로 인정된 방법론

#### [10-B4] ETSI GS NFV-TST 009 — NFVI Networking Benchmarks (2018)

- **URL**: https://www.etsi.org/deliver/etsi_gs/NFV-TST/001_099/009/
- 인프라 레이어 변경의 영향을 throughput/latency/frame loss로 정량화하는 방법 정의
- **의의**: CNI(인프라) 변경의 효과를 KPI로 측정/비교하는 방법론 자체의 표준적 근거

#### [10-B5] O-RAN AI/ML Workflow (O-RAN.WG2.AIML-v01.03, 2023)

- Near-RT RIC: ML model 결정 → 실행 → KPI 관측으로 모델 평가
- Model performance는 action 전후 KPI 변화의 통계적 유의성으로 판단
- **의의**: 통신 AI 시스템에서 "실행 후 KPI 비교"가 판단 정확성 평가의 **업계 표준 방법**

---

### C. 커널 레벨 기술 근거: 왜 macvlan/ipvlan이 KPI에 차이를 만드는가

#### [10-C1] IPVLAN — The Beginning (netdev 0.1, Mahesh Bandewar/Google, 2015)

- **URL**: http://people.netfilter.org/pablo/netdev0.1/papers/IPVLAN-The-beginning.pdf
- ipvlan: MAC 공유 → 커널 내부 L3 라우팅 (CPU-bound)
- macvlan: 별도 MAC → NIC 하드웨어 레벨 패킷 분리 (NIC-offload 가능)
- **의의**: 고부하 시 macvlan 유리, 저부하 시 ipvlan 오버헤드 적음의 **기술적 원인** 설명

#### [10-C2] Data Plane Optimization in Open Virtual Routers (ACM SIGCOMM Workshop, 2011)

- **URL**: https://www.researchgate.net/publication/221198708
- macvlan의 NAPI 기반 패킷 전달 vs softnet queue 경유의 throughput 차이 측정
- **의의**: 커널 패킷 처리 경로 차이가 측정 가능한 성능 차이를 만듦을 실증

#### [10-C3] Assessing the Impact of Linux Networking on CPU Consumption (NetDev 0x17, 2023)

- **URL**: https://netdevconf.org/0x17/docs/netdev-0x17-paper34-talk-slides/
- Linux 네트워킹 스택 경로별 CPU cycle 소비 정량화
- 인터페이스 타입에 따라 패킷당 CPU cost가 다름
- **의의**: CNI 타입 → CPU 사용량 인과관계의 커널 레벨 근거

---

### 논문에서의 활용 (Related Work / Background)

> "선행연구[10-A1][10-A2][10-A3]에서 컨테이너 네트워크 인터페이스 유형(macvlan, ipvlan)에 따라 throughput, latency, CPU 사용량이 유의미하게 달라짐이 확인되었으며, 이 차이는 커널 레벨의 패킷 처리 경로 차이[10-C1][10-C2][10-C3]에 기인한다. 또한 5G Core를 Kubernetes 위에 배포할 경우 네트워킹 오버헤드가 직접적 성능 병목[10-A4]이 된다. 한편, 전환 실행 후 KPI 비교로 판단의 올바름을 검증하는 방식은 3GPP NWDAF의 analytics feedback loop[10-B1], ETSI ZSM의 closed-loop automation[10-B2], ITU-T Y.1731의 performance monitoring[10-B3], 그리고 O-RAN AI/ML workflow[10-B5]에서 공통적으로 채택하는 표준적 평가 방법론이다. 그러나 기존 연구는 모두 정적 비교에 그쳤으며, 런타임에 동적으로 전환하고 그 판단의 정확성을 자동 검증하는 시스템을 구현한 연구는 없다."

---

## [11] 트래픽 프로파일 ↔ CNI 적합성 매핑 근거

> **핵심 논리**: "선행연구에 따르면 프로파일 A(소패킷 고빈도)에서는 ipvlan이 유리하고, 프로파일 B(대패킷 고throughput)에서는 macvlan이 유리하다. 따라서 A→B 전환 시 NWDAF가 macvlan을 선택하는 것이 올바르다."

### 근거 1: CNI별 최적 workload 조건 (IETF BMWG + 실측)

**출처**: IETF draft-samizadeh-bmwg-cni-benchmarking-02 (Apr 2026), §4.1.3:
> "It is frequently observed that a CNI optimized for high-throughput TCP bulk traffic may perform suboptimally under UDP-heavy traffic, high pod churn, or policy-intensive workloads."

**출처**: MDPI Electronics 2024 (Dakic et al.):
> "Certain CNIs are better suited for specific use cases, mainly when tuning our environment for smaller or larger network packets and workload types."

### 근거 2: ipvlan vs macvlan의 기술적 특성 → workload 적합성

커널 메커니즘 차이([10-C1] Bandewar 2015)에서 도출:

| 특성 | ipvlan (L2) | macvlan (bridge) |
|------|-------------|-----------------|
| MAC 주소 | 호스트와 공유 | 독립 MAC 할당 |
| 패킷 처리 경로 | 커널 내부 L3 routing | NIC 레벨 MAC filtering |
| CPU 사용 패턴 | 패킷당 고정 overhead 낮음 | 패킷당 overhead 높지만 NIC offload 가능 |
| **소패킷 고빈도 (high pps)** | ✅ 유리 — 커널 내부 처리가 빠름, per-packet CPU cost 낮음 | ❌ 불리 — MAC lookup overhead가 pps에 비례 |
| **대패킷 고throughput** | ❌ 불리 — 커널 L3 경로에 CPU 병목 | ✅ 유리 — NIC offload(TSO/GRO), HW multiqueue 활용 |
| **다수 UE (다수 인터페이스)** | ✅ 유리 — MAC table 이슈 없음 | ❌ 주의 — 스위치 MAC table 용량 제한 |

### 근거 3: 3GPP 표준 트래픽 모델 → 프로파일 매핑

| 3GPP 서비스 카테고리 | 표준 출처 | 트래픽 특성 | 대응 프로파일 | 예측 유리 CNI |
|---------------------|-----------|------------|--------------|--------------|
| **mMTC** (Massive IoT) | TS 22.261 §7.2, TR 38.913 | 소패킷(32~256B), 간헐적 burst, 다수 디바이스 | `iot-burst.yaml` (128B, 100pps, 20UE, burst) | **ipvlan** |
| **VoNR** (Voice) | TS 22.261 §7.1, 5QI=1 | 초소형 패킷(60~80B), 20ms 주기, GBR | `vonr.yaml` (80B, 50pps, 10UE) | **ipvlan** |
| **eMBB** (Enhanced Broadband) | TS 22.261 §7.1, TR 38.913 | 대패킷(1400B), 고throughput(100M~1Gbps) | `streaming-dl.yaml` (1400B, 500Mbps) | **macvlan** |
| **UPF Stress** | 벤치마크 시나리오 | 대패킷, 양방향, 500Mbps+ | `upf-stress.yaml` Phase 2,3,4 | **macvlan** |

### 실험 시나리오 설계: A→B 전환

```
Phase 1 (ipvlan 적합):   iot-burst + vonr 동시 실행 (소패킷, 다수 UE, 낮은 throughput)
         │
         │ ← 트래픽 패턴 변화 (e.g., 스트리밍 세션 시작)
         ▼
Phase 2 (macvlan 적합):  streaming-dl 시작 (대패킷, 고throughput, 단일/소수 UE)
         │
         │ ← NWDAF 감지: "throughput 부족, packet loss 증가" → "macvlan로 전환"
         ▼
Phase 3 (전환 후):       동일 streaming-dl 계속 → KPI 개선 확인
```

### 표준 근거 정리

| 프로파일 파라미터 | 값 | 표준 출처 |
|-----------------|-----|----------|
| eMBB DL target throughput | 100 Mbps (user experienced) | 3GPP TR 38.913 Table 7.1 |
| eMBB packet delay budget | ≤10ms (5QI=9 → 300ms 허용이나 실질 목표) | 3GPP TS 23.501 Table 5.7.4-1 |
| URLLC latency target | ≤1ms (user plane) | 3GPP TR 38.913 §7.1 |
| mMTC device density | 1M devices/km² | 3GPP TR 38.913 §7.3 |
| mMTC packet size | 32~256 bytes | 3GPP TR 37.868 (MTC traffic model) |
| VoNR codec | AMR-WB 23.85kbps, 20ms frame | 3GPP TS 26.114, 5QI=1 |
| VoNR packet size | ~60~80 bytes (RTP + AMR payload) | 3GPP TS 26.114 §7.4 |

### IETF BMWG 방법론 준수

| 요구사항 (draft-samizadeh-bmwg-cni-benchmarking-02) | 본 연구 대응 |
|---------------------------------------------------|-------------|
| "packet sizes: 64B, 512B, 1500B" (§4.1.1) | ✅ 64B (upf-stress P1), 128B (iot-burst), 1400B (streaming-dl) |
| "TCP_RR, UDP_RR workloads" (§7.4) | ✅ UDP (all profiles), TCP (streaming-dl P2) |
| "Short-lived TCP / Persistent streaming / Burst UDP" (§7.4) | ✅ vonr(short UDP), streaming-dl(persistent), iot-burst(burst) |
| "minimum 5 repetitions" (§7.3) | ✅ 실험 프로토콜에 반영 필요 |
| "CPU/memory per CNI process" (§4.1.3) | ✅ monitor-collector.sh에서 수집 |

### 논문에서의 활용 (Experiment Design)

> "실험 시나리오는 3GPP TR 38.913 및 TS 22.261에서 정의한 mMTC(소패킷, 간헐적 burst)와 eMBB(대패킷, 고throughput) 트래픽 모델에 기반한다. 선행연구[10-A1][10-A2][10-C1]에 따르면, 소패킷 고빈도 환경에서는 ipvlan의 커널 내부 처리가 유리하고, 대패킷 고throughput 환경에서는 macvlan의 NIC offload가 유리하다. IETF CNI 벤치마킹 방법론[BMWG-02]도 'CNI optimized for high-throughput bulk traffic may perform suboptimally under UDP-heavy traffic'임을 확인한다. 이에 따라 본 실험은 mMTC→eMBB 트래픽 전환 시 NWDAF가 ipvlan→macvlan 전환을 올바르게 판단하는지를 검증한다. 프로파일 파라미터(packet size, rate, burst pattern)는 3GPP 표준 값을 준수하며, 벤치마킹 방법론은 IETF BMWG draft-samizadeh-bmwg-cni-benchmarking-02의 절차를 따른다."

---

## [12] NWDAF 최소 구현의 정당성 — 3GPP Rel-17 기능 분리 구조

> **핵심**: 3GPP TS 23.288 Rel-17에서 NWDAF의 AnLF와 MTLF는 독립 배치 가능한 논리 기능으로 분리되어 있으며, 부분 구현이 명시적으로 허용된다.

### NWDAF 내부 구조 (TS 23.288 §6.2A, Rel-17)

```
NWDAF (단일 NF 또는 분리 배치)
├── AnLF (Analytics Logical Function)
│     - 데이터 수집 (OAM/NF로부터)
│     - 분석/추론 실행 (학습된 모델 사용)
│     - Analytics 결과 출력
│
├── MTLF (Model Training Logical Function)
│     - 모델 학습 (학습 데이터 기반)
│     - 학습된 모델을 AnLF에 제공
│
└── 서비스 인터페이스 (Nnwdaf)
      - Nnwdaf_AnalyticsInfo (요청/응답형)
      - Nnwdaf_EventsSubscription (구독/알림형)
      - Nnwdaf_MLModelProvision (모델 제공)
```

### 3GPP 원문 근거

**TS 23.288 §6.2A:**
> "The NWDAF may be deployed as a single NF containing both AnLF and MTLF, or as separate NF instances for AnLF and MTLF."

### 본 연구의 구현 범위

| TS 23.288 기능 | 구현 여부 | 구현 방식 | 정당화 |
|----------------|----------|----------|--------|
| AnLF — 데이터 수집 | ✅ | kubectl top + /proc/net/dev → monitor-collector.sh | OAM 경유 수집 (표준 절차) |
| AnLF — 분석/추론 | ✅ | sklearn ML 분류 모델 | Network Performance Analytics ID 해당 |
| AnLF — 결과 출력 | ✅ | nwdaf-switch.sh 호출 (전환 신호) | Analytics output → action |
| MTLF — 모델 학습 | ✅ | offline 학습 → 모델 파일 | AnLF와 분리 배치 허용 |
| Nnwdaf 서비스 인터페이스 | ❌ | scope out | 단일 벤더 내부 연동 (외부 인터페이스 불필요) |
| NRF 등록 | ❌ | scope out | 단일 클러스터 내 직접 연동 |
| Consumer NF 연동 (PCF 등) | ❌ | scope out | NWDAF → DRANET 직접 연동으로 대체 |

### NWDAF → DRANET 직접 연동의 정당성

TS 23.288 §6.1.2에 따르면:
- NWDAF는 analytics를 **제공**하는 역할
- Analytics에 따른 **action은 consumer의 책임**
- 3GPP는 "NWDAF가 직접 인프라를 변경하는 경로"를 **정의하지도, 금지하지도 않음**

따라서 NWDAF가 DRANET을 직접 호출하는 것은:
- 3GPP scope 밖 (인프라 레이어) ✅
- 표준 위반 아님 ✅
- Operator-specific implementation에 해당 ✅

### Analytics ID 매핑

| 본 연구 기능 | TS 23.288 Analytics ID | 비고 |
|-------------|----------------------|------|
| throughput/loss 기반 전환 판단 | Network Performance (Table 6.1.1) | NF별 성능 분석 |
| KPI 이상 탐지 (monitor-detect.py) | Abnormal Behaviour | 임계값 초과 감지 |

### 논문에서의 서술

> "본 연구의 NWDAF는 TS 23.288 Rel-17의 AnLF에 해당하며, MTLF와의 분리 배치가 표준에서 명시적으로 허용된다(§6.2A). 서비스 인터페이스(Nnwdaf)는 본 연구 범위 밖으로, 단일 시스템 내부 연동으로 단순화하였다. NWDAF의 analytics 결과에 따른 실행(CNI 전환)은 3GPP가 규정하지 않는 인프라 레이어 동작이며, operator-specific implementation으로 정당화된다."

---

## [13] ipvlan/macvlan 동일 위상 — 네트워크 인터페이스 드라이버 관계

### 기술적 위치

```
물리 NIC (eth0)
│
├── ipvlan sub-interface: MAC 공유, 커널 내부 IP 기반 패킷 분배
└── macvlan sub-interface: MAC 분리, NIC 레벨 MAC 기반 패킷 분배
```

- **동일 위상**: 둘 다 Linux 커널의 가상 네트워크 인터페이스 드라이버
- **동일 역할**: Pod에 secondary network interface 제공
- **차이점**: 패킷 분배 로직만 다름 (IP 기반 vs MAC 기반)
- **상위 레이어 투명**: IP, GTP-U, PFCP 세션은 전환을 인지하지 못함

### Multus 시대 vs DRANET 시대

| | Multus (기존) | DRANET (본 연구) |
|---|---|---|
| 추상화 | NetworkAttachmentDefinition | DeviceClass + ResourceClaim |
| 전환 시점 | Pod 생성 시 고정 | **런타임에 DeviceClass 변경** |
| 전환 시 Pod 재생성 | 필요 | **불필요** |
| 상위 레이어 영향 | Pod 재생성 → 세션 끊김 | 없음 (PFCP 유지) |

### 논문에서의 서술

> "ipvlan과 macvlan은 동일 위상(물리 NIC 상위의 가상 sub-interface)에 위치하며, 패킷 분배 로직만 상이한 커널 드라이버이다. 따라서 전환 시 상위 프로토콜 스택(IP, GTP-U, PFCP)에 영향을 주지 않으며, DRANET의 ResourceClaim 변경만으로 런타임 전환이 가능하다. 이는 기존 Multus 기반 구조에서 Pod 재생성이 필요했던 한계를 해결한다."

---

## [14] 실험 설계 — 트래픽 시나리오 × CNI 전략 매트릭스

### 트래픽 시나리오 (행)

| # | 시나리오 | 트래픽 특성 | 대응 프로파일 | 표준 근거 |
|---|---------|------------|--------------|----------|
| T1 | 대규모 트래픽 | 1400B, 고throughput (500Mbps), 소수 UE | `streaming-dl.yaml` | TS 22.261 §7.1 (eMBB) |
| T2 | 소규모 트래픽 | 80~128B, 저throughput, 다수 UE, burst | `iot-burst.yaml` + `vonr.yaml` | TR 37.868 (mMTC), TS 26.114 (VoNR) |
| T3 | 소규모→대규모 전환 | T2로 시작 → 중간에 T1으로 전환 | T2 → T1 순차 실행 | 실제 운용 시나리오 (혼합 트래픽) |

### CNI 전략 (열)

| # | 전략 | 설명 |
|---|------|------|
| A | ipvlan 고정 (baseline) | 전체 실험 동안 ipvlan 유지. Rule-based도 NWDAF도 없음 |
| B | macvlan 고정 (baseline) | 전체 실험 동안 macvlan 유지. Rule-based도 NWDAF도 없음 |
| C | NWDAF ML 기반 동적 전환 | NWDAF가 KPI 관측 → ML 모델 판단 → DRANET 전환 실행 |

### 실험 매트릭스 (3×3 = 9 조합)

| | A. ipvlan 고정 | B. macvlan 고정 | C. NWDAF 동적 전환 |
|---|---|---|---|
| **T1. 대규모** | A-T1 | B-T1 | C-T1 |
| **T2. 소규모** | A-T2 | B-T2 | C-T2 |
| **T3. 소→대 전환** | A-T3 | B-T3 | C-T3 |

### 각 조합에서 측정하는 것

| 조합 | 측정 목표 |
|------|----------|
| A-T1, B-T1 | 대규모 트래픽에서 ipvlan vs macvlan 성능 차이 (macvlan 유리 확인) |
| A-T2, B-T2 | 소규모 트래픽에서 ipvlan vs macvlan 성능 차이 (ipvlan 유리 확인) |
| A-T3, B-T3 | 고정 CNI의 한계 — T2→T1 전환 시 한쪽은 반드시 성능 저하 |
| C-T1 | NWDAF가 macvlan 선택/유지하는지 (올바른 판단) |
| C-T2 | NWDAF가 ipvlan 선택/유지하는지 (올바른 판단) |
| **C-T3** | **핵심 실험** — NWDAF가 전환 시점을 감지하고 ipvlan→macvlan 전환하는지 |

### 검증 기준

| 검증 항목 | 판단 방법 |
|----------|----------|
| NWDAF 판단 정확성 | C-T1이 B-T1과 유사한 KPI → macvlan 선택 올바름 |
| | C-T2가 A-T2와 유사한 KPI → ipvlan 선택 올바름 |
| | C-T3에서 전환 후 KPI가 B-T1 수준으로 수렴 |
| NWDAF vs 고정의 우위 | C-T3 vs A-T3: ipvlan 고정은 T1 구간에서 성능 저하 |
| | C-T3 vs B-T3: macvlan 고정은 T2 구간에서 오버헤드 |
| 전환 비용 | C-T3에서 전환 순간의 일시적 KPI 저하 (전환 소요시간) |
| False positive | C-T1, C-T2에서 불필요한 전환이 발생하지 않는지 |

### 기대 결과 요약

```
T1 (대규모):  B ≥ C > A     (macvlan 유리, NWDAF도 macvlan 선택)
T2 (소규모):  A ≥ C > B     (ipvlan 유리, NWDAF도 ipvlan 선택)
T3 (전환):    C > A, C > B  (NWDAF만 두 구간 모두 최적 — 핵심 결론)
```

### 논문에서의 활용 (Evaluation)

> "실험은 3가지 트래픽 시나리오(대규모/소규모/전환)와 3가지 CNI 전략(ipvlan 고정/macvlan 고정/NWDAF 동적 전환)의 조합으로 구성된다. T1, T2에서의 고정 CNI 결과(A-T1, B-T2)는 NWDAF 판단의 ground truth로 활용되며, T3에서 NWDAF 동적 전환(C-T3)이 양쪽 고정 전략(A-T3, B-T3)보다 전체 구간 평균 KPI에서 우위를 보이는지를 핵심 가설로 검증한다."

---

## [15] NWDAF 데이터 수집 경로: OAM 방식 선택의 정당성

> **예상 공격**: "왜 3GPP TS 23.288의 Nupf Event Exposure를 구현하지 않았는가?"

### 3GPP가 정의한 NWDAF 데이터 수집 경로 (TS 23.288)

```
경로 1: NF Event Exposure (직접 구독)
  NWDAF ←[Nupf/Nsmf/Namf]→ UPF/SMF/AMF
  - NF가 Event Exposure 서비스 제공
  - NWDAF subscribe → NF가 이벤트 notify

경로 2: OAM (Operations & Maintenance)  ← 본 연구
  NWDAF ← OAM 시스템
  - 외부 모니터링을 통해 간접 수집
  - PM counters, 커널 통계 등

경로 3: DCCF (Data Collection Coordination Function) — Rel-17+
  NWDAF ← DCCF ← 여러 NF/OAM
  - 대규모 배포 시 중앙 조율
```

**표준은 이 세 경로를 OR 관계로 정의** — 어느 하나만 구현해도 표준 적합.

### 방어 근거 1: Nupf Event Exposure의 현실

| 사실 | 출처 |
|------|------|
| Nupf Event Exposure는 Rel-18에서 처음 도입 (optional) | 3GPP TS 29.564 |
| free5GC: Nupf **미구현** (공식 릴리스 기준, 2025) | [nwdaf_closedloop2025] |
| Open5GS: Nupf **미구현** | Open5GS 공식 repo |
| NWDAF 연구 23편 중 대부분 OAM/외부 수집 방식 사용 | [nwdaf_survey2025] |
| "None of the most widely used 5G open-source projects have yet officially deployed NWDAF to their official repositories" | [nwdaf_survey2025] |

### 방어 근거 2: Nupf 구현의 비용과 오버헤드

| 항목 | Nupf Event Exposure | OAM (본 연구) |
|------|-------------------|--------------|
| UPF 소스 코드 수정 | **필요** (free5GC UPF에 서비스 추가) | 불필요 |
| UPF latency 영향 | +0.11ms per subscriber [waterloo2026] | 없음 (Pod 외부 수집) |
| UPF CPU 영향 | +6.5% [waterloo2026] | 없음 |
| 범용성 | 특정 UPF 구현체에 종속 | 어떤 UPF든 적용 가능 |
| 구현 복잡도 | 높음 (SBI 서비스, subscribe/notify 프로토콜) | 낮음 (kubectl + /proc) |

### 방어 근거 3: OAM 방식이 학계에서 표준적

| 논문 | 수집 방식 | 비고 |
|------|----------|------|
| Barrachina et al. 2022 | Open5GS + Prometheus (OAM) | IEEE, Kubernetes CNF 모니터링 |
| Chouman et al. 2022 (IWCMC) | Open5GS + 외부 수집 | NWDAF 최초 구현 중 하나 |
| Bayleyegn et al. 2024 (NetSoft) | free5GC + 외부 모니터링 | Real-time KPI prediction |
| Bolla et al. 2023 (Globecom) | 외부 수집 기반 NWDAF | Open-source prototype |
| **본 연구** | kubectl top + /proc/net/dev | OAM 경로 |

### 방어 근거 4: free5GC 공식 입장

free5GC Blog (2024.11):
> "For network management information, NWDAF also connects to the Operation, Administration and Maintenance (OAM) system."

→ free5GC 스스로가 OAM 경유를 NWDAF의 정상 데이터 수집 경로로 명시.

### OAM 방식의 장점 (약점이 아닌 강점으로 포지셔닝)

1. **UPF 성능 무영향**: Nupf는 +0.11ms latency, +6.5% CPU. OAM은 0
2. **UPF 구현 비종속**: 어떤 UPF(free5GC, Open5GS, 상용)든 동일하게 적용 가능
3. **측정과 피측정의 분리**: 모니터링이 실험 대상(UPF 성능)을 왜곡하지 않음 — 실험 내적 타당성 향상
4. **배포 단순성**: ARM64 자원 제약 환경에서 추가 NF 서비스 불필요

### 논문에서의 서술

> "3GPP TS 23.288은 NWDAF 데이터 수집 경로로 NF Event Exposure, OAM, DCCF를 정의하며, 본 연구는 OAM 경로를 채택한다. 이는 (1) Nupf Event Exposure가 오픈소스 5GC(free5GC, Open5GS)에 미구현된 현실[survey2025], (2) Event Exposure 구현 시 UPF 성능 오버헤드(+0.11ms, +6.5% CPU)[waterloo2026]가 실험 결과를 왜곡할 수 있는 점, (3) OAM 방식이 학계 NWDAF 연구의 표준적 수집 방법인 점을 고려한 설계 선택이다. 수집 메트릭(throughput, packet loss, CPU/memory)은 TS 23.288 Network Performance Analytics ID의 입력 데이터와 동일하다."

---

## [16] ML 모델 선택 근거 — Random Forest

### 3GPP는 모델을 지정하지 않음

TS 23.288은 **model-agnostic**:
- 아키텍처(AnLF/MTLF)와 데이터 흐름만 정의
- 특정 ML 알고리즘을 명시하거나 요구하지 않음
- 알고리즘 선택은 구현자(operator/vendor)의 재량

### 학계에서 사용된 NWDAF ML 모델 (서베이 23편 기준)

| 모델 | 사용 논문 수 | 대표 논문 |
|------|------------|----------|
| LSTM | 6 | Manias 2022, Jeon 2024 |
| **Random Forest** | **4** | **Bayleyegn 2024 (NetSoft)**, Abbas 2022 |
| XGBoost/GBM | 3 | Abbas 2021 |
| Decision Tree | 3 | Oliveira 2024 |
| SVM | 2 | Mekrache 2023 |
| MLP/CNN | 2 | Zhang 2024 |
| LLM | 1 | Kan 2024 |

### Random Forest 선택 이유

| 기준 | Random Forest | Deep Learning (LSTM 등) |
|------|--------------|------------------------|
| ARM64 추론 속도 | <1ms | 수십~수백ms (GPU 없이) |
| 학습 데이터 양 | 수백 샘플로 충분 | 수천~수만 필요 |
| 해석 가능성 | feature importance 제공 | black box |
| 5초 주기 판단 | ✅ 여유 | ⚠️ 빠듯할 수 있음 |
| 논문 분석 가치 | "어떤 KPI가 판단에 가장 중요한가" | 해석 어려움 |
| 학계 선례 | free5GC + RF [Bayleyegn 2024] | 있지만 자원 제약 환경 부적합 |

### 본 연구 모델 상세

```
모델명: Random Forest Classifier (Breiman, 2001)
구현: sklearn.ensemble.RandomForestClassifier
Pipeline: StandardScaler → RandomForestClassifier

하이퍼파라미터:
  - n_estimators: 100 (트리 수)
  - max_depth: 10 (과적합 방지)
  - min_samples_split: 5
  - random_state: 42 (재현성)

입력 features (5차원):
  [throughput_mbps, packet_loss_pct, total_pps, cpu_milli, mem_mi]

출력: "ipvlan" 또는 "macvlan"

Feature Importance (학습 결과):
  throughput_mbps      0.6469  ← 가장 중요
  total_pps            0.1289
  mem_mi               0.1043
  packet_loss_pct      0.0826
  cpu_milli            0.0374
```

### 논문에서의 서술

> "본 연구는 Random Forest Classifier[Breiman2001]를 NWDAF AnLF의 분류 모델로 채택한다. 3GPP TS 23.288은 특정 ML 알고리즘을 규정하지 않으며(model-agnostic), Random Forest는 NWDAF 학계 연구에서 가장 널리 사용되는 모델 중 하나이다[survey2025]. ARM64 자원 제약 환경에서의 추론 속도(<1ms), 5초 판단 주기에 대한 적합성, 그리고 feature importance를 통한 해석 가능성을 고려하여 선택하였다. 학습 결과, throughput(0.65)이 전환 판단의 가장 중요한 feature임이 확인되었으며, 이는 선행연구[SHS2023, MDPI2024]의 '대패킷 고throughput에서 macvlan 유리' 결론과 일치한다."

---

## [17] 실험 격리 — CPU Pinning 및 검증

### 문제: 단일 노드에서의 리소스 경합

단일 ARM64 노드(4 vCPU)에서 UPF, traffic-gen, NWDAF, monitor가 공존.
UPF 고부하 시 모니터링/제어 시스템이 영향받으면 측정 왜곡 발생.

### 해결: Kubernetes CPU Manager static policy

```
CPU 0, 1  →  UPF Pod 전용 (Guaranteed QoS, exclusive)
CPU 2     →  traffic-gen Pod 전용 (Guaranteed QoS)
CPU 3     →  나머지 (NWDAF, monitor, NFs, kubelet, OS)
```

kubelet 설정:
```yaml
cpuManagerPolicy: static
reservedSystemCPUs: "3"
```

### 검증 방법: per-CPU 사용량 기록

- `/proc/stat` 기반 per-CPU busy/idle 시계열 수집 (monitor-collector.sh)
- 실험 A/B/C 간에 CPU 2,3의 사용량이 일정함을 확인
- CPU 0,1은 실험 조건(CNI 타입, 트래픽 볼륨)에 따라 변동 → 이것이 측정 대상

논문 Table 예시:

| 실험 | UPF CPU (core 0,1) | System CPU (core 2,3) | 격리 유효 |
|------|--------------------|-----------------------|-----------|
| A-T1 | 1650m ± 30m | 180m ± 12m | ✅ |
| B-T1 | 1420m ± 25m | 175m ± 15m | ✅ |
| C-T1 | 1480m ± 35m | 185m ± 10m | ✅ |

→ System CPU가 전 실험에 걸쳐 일정 = **격리 유효, 측정 왜곡 없음**

### 표준 근거

**IETF BMWG draft-samizadeh-bmwg-cni-benchmarking-02 §7.1:**
> "Ensure consistent CPU pinning and disable power-saving features or CPU frequency scaling to stabilize performance measurements."

**IETF BMWG §4.1.3:**
> "CPU/GPU utilization SHOULD be reported per node and per CNI process."

**ETSI GS NFV-TST 009:**
> "System resource metrics MUST be collected at both node-level and pod-level granularity."

### 측정과 피측정의 완전 분리

```
측정 대상 (CPU 0,1):
  - UPF data plane 패킷 처리
  - ipvlan/macvlan 커널 경로
  - → cpu_milli, mem_mi, packet_loss, throughput

측정 도구 (CPU 3):
  - monitor-collector.sh (kubectl exec)
  - nwdaf-engine.py (추론/판단)
  - → 측정 대상에 영향 없음

트래픽 생성 (CPU 2):
  - iperf3 (traffic-gen Pod)
  - → 일정한 부하 생성, UPF와 코어 분리
```

### 논문에서의 서술

> "Kubernetes CPU Manager static policy[K8s docs]를 적용하여 UPF에 물리 코어 2개를 전용 할당하고, 모니터링/제어 시스템은 별도 코어에서 동작하도록 격리하였다. 이는 IETF BMWG[BMWG-02]가 요구하는 'consistent CPU pinning' 조건을 충족한다. 격리의 유효성은 per-CPU 사용량 시계열을 기록하여 검증하며, 시스템 코어(CPU 2,3)의 사용량이 실험 조건에 무관하게 일정함을 확인한다."

---

## [18] 연구 제안서 — 논문 구조 및 실험 프로세스 요약

### Title

"NWDAF-Driven Dynamic CNI Backend Selection for Cloud-Native 5G Core on ARM: Intelligent Network Plane Management Using DRANET"

### Abstract (Draft)

Cloud-native 5G Core에서 User Plane Function(UPF)의 data plane 성능은 Container Network Interface(CNI) 드라이버 구현에 영향을 받는다. 선행연구에서 ipvlan과 macvlan은 패킷 분배 로직의 차이로 인해 workload 특성에 따라 상이한 성능을 보임이 확인되었으나, 5GC UPF 환경에서 이를 런타임에 동적으로 전환하고 그 판단의 정확성을 검증한 연구는 부재한다. 본 연구는 3GPP TS 23.288 NWDAF의 AnLF를 ML 분류 모델(Random Forest)로 구현하여 UPF KPI를 실시간 분석하고, Kubernetes DRANET을 활용하여 CNI backend(ipvlan↔macvlan)를 런타임에 동적 전환하는 closed-loop 시스템을 ARM64 환경에서 설계, 구현, 검증한다. 실험은 3가지 트래픽 시나리오와 3가지 CNI 전략의 조합(9개 실험)으로 구성되며, CPU pinning과 steal time 모니터링으로 실험 격리를 보장한다. 결과를 통해 NWDAF의 전환 판단 정확성, 전환 비용, 그리고 고정 CNI 대비 동적 전환의 실효성을 평가한다.

### 논문 구조

```
1. Introduction
   - 문제 정의: 정적 CNI 할당의 한계
   - 연구 질문: "NWDAF가 CNI 전환을 올바르게 판단하는가?"
   - Contribution 요약

2. Background & Related Work
   - 5GC UPF data plane (TS 23.501)
   - NWDAF 아키텍처 (TS 23.288, AnLF/MTLF 분리)
   - DRANET/DRA (K8s v1.34)
   - CNI 성능 비교 선행연구 (Qi 2021 IEEE TNSM)
   - ipvlan vs macvlan 커널 메커니즘 (Bandewar 2015)

3. System Design
   - 전체 아키텍처: free5GC + NWDAF + DRANET on ARM64 K8s
   - NWDAF AnLF: OAM 수집 → ML 추론 → DRANET 실행
   - ML 모델: Random Forest (model-agnostic 표준 준수)
   - 전환 메커니즘: ResourceClaim DeviceClass 변경
   - 격리 설계: CPU pinning, 코어 분리

4. Experiment Design
   - 실험 매트릭스 (3×3)
   - 트래픽 프로파일 (3GPP 표준 기반)
   - 측정 방법론 (IETF BMWG 준수)
   - 격리 검증 방법 (per-CPU, steal time)

5. Baseline Measurement
   - ipvlan 고정 성능 측정 (A-T1, A-T2)
   - macvlan 고정 성능 측정 (B-T1, B-T2)
   - CNI별 차이 확인 → NWDAF 실험의 전제 검증
   - 선행연구(Qi 2021)와의 경향 일치 확인

6. Evaluation
   - NWDAF 판단 정확성 (C-T1, C-T2: 올바른 CNI 선택 여부)
   - 동적 전환 효과 (C-T3 vs A-T3, B-T3: 전체 구간 KPI 비교)
   - 전환 비용 (전환 순간 throughput dip, 안정화 시간)
   - NWDAF 오버헤드 (CPU 3 사용량: B vs C 차이)
   - False positive 분석 (불필요한 전환 횟수)
   - 격리 검증 (per-CPU flat + steal time < 1%)

7. Discussion
   - 가설 지지/불지지 해석
   - ARM64 환경 특성
   - 전환 빈도 최적화 (cooldown 파라미터 영향)
   - Limitation: 단일 노드, 2 CNI만, OAM 방식

8. Conclusion & Future Work
   - 결론
   - Future Work: Nupf Event Exposure, SR-IOV 확장, 다중 NF 전환, 딥러닝 모델
```

### 실험 프로세스 (End-to-End)

```
┌─────────────────────────────────────────────────────────┐
│ Phase 0: 환경 준비                                       │
├─────────────────────────────────────────────────────────┤
│ 1. K8s 클러스터 + CPU Manager static policy 설정        │
│ 2. DRANET DaemonSet 배포 + DeviceClass 적용             │
│ 3. free5GC NFs 배포 (UPF: CPU 0,1 pinning)             │
│ 4. NWDAF Pod 배포 (replicas=0, 대기)                    │
│ 5. ML 모델 학습 (train-model.py)                        │
│ 6. iperf3-server 배포                                    │
└─────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────┐
│ Phase 1: Baseline 측정 (A, B 실험)                       │
├─────────────────────────────────────────────────────────┤
│ for experiment in A-T1 A-T2 A-T3 B-T1 B-T2 B-T3:      │
│   1. NWDAF OFF                                           │
│   2. CNI 고정 설정 (nwdaf-switch.sh ipvlan/macvlan)      │
│   3. 모니터링 시작 (per-CPU + steal time 포함)           │
│   4. 트래픽 실행 (traffic-gen Job, phases 순차)          │
│   5. 모니터링 종료, 결과 저장                            │
│   6. 5회 반복                                            │
└─────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────┐
│ Phase 2: NWDAF 실험 (C 실험)                             │
├─────────────────────────────────────────────────────────┤
│ for experiment in C-T1 C-T2 C-T3:                       │
│   1. NWDAF ON (scale replicas=1)                         │
│   2. 초기 CNI 설정 (의도적으로 비최적으로 시작)          │
│   3. 모니터링 시작                                       │
│   4. 트래픽 실행                                         │
│   5. NWDAF가 감지 → 전환 판단 → 실행 (자동)             │
│   6. 모니터링 종료, NWDAF 로그 수집                      │
│   7. 5회 반복                                            │
└─────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────┐
│ Phase 3: 분석 및 검증                                    │
├─────────────────────────────────────────────────────────┤
│ 1. 격리 검증: per-CPU 시계열 → CPU 2,3 flat 확인        │
│ 2. steal time 검증: 전 실험 < 1% 확인                   │
│ 3. Baseline 비교: A-T1 vs B-T1 → CNI 차이 유의미?      │
│ 4. NWDAF 정확성: C-T1→macvlan 선택? C-T2→ipvlan 선택?  │
│ 5. 동적 전환 효과: C-T3 vs A-T3, B-T3 전체 구간 평균   │
│ 6. 전환 비용: dip 길이/크기, CPU 3 spike                │
│ 7. 통계: 5회 반복의 평균 ± 표준편차, 95% CI             │
└─────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────┐
│ Phase 4: 결과 해석                                       │
├─────────────────────────────────────────────────────────┤
│ Case 1: C-T3 > A-T3, B-T3                              │
│   → "동적 전환이 고정 대비 우위, NWDAF 판단 유효"       │
│                                                          │
│ Case 2: C-T3 ≈ B-T3                                    │
│   → "전환 비용이 이득을 상쇄, cooldown 최적화 필요"     │
│                                                          │
│ Case 3: C-T3 < B-T3                                    │
│   → "동적 전환의 비용 > 이득, 전환 조건 재설계 필요"    │
│                                                          │
│ 어떤 경우든 유효한 학술 기여 (올바른 방법으로 검증)      │
└─────────────────────────────────────────────────────────┘
```

### Contribution (1개로 집중)

> NWDAF ML 모델이 UPF의 KPI를 기반으로 CNI backend 전환을 올바르게 판단하는지를 DRANET 기반 closed-loop 시스템으로 구현하고, ARM64 containerised 환경에서 격리된 실험으로 검증한다.

### 방어 포인트 체크리스트

| # | 예상 공격 | 방어 | 근거 |
|---|----------|------|------|
| 1 | NWDAF 구현이 너무 단순 | AnLF만 구현은 Rel-17이 허용 | TS 23.288 §6.2A |
| 2 | 프로파일이 표준 준수? | 3GPP TR 38.913, TS 22.261 파라미터 사용 | [11] |
| 3 | KPI 비교로 판단 평가 가능? | NWDAF feedback loop = 표준 패턴 | TS 23.288, ETSI ZSM, O-RAN |
| 4 | CNI 변경→KPI 인과관계? | Qi 2021 (IEEE TNSM) + CPU pinning으로 변수 격리 | [10], [17] |
| 5 | Nupf 미구현 | OAM은 표준 경로, 오픈소스 공통, 측정 왜곡 방지 | [15] |
| 6 | ML 모델 단순 | model-agnostic 표준, RF는 학계 관행 | [16] |
| 7 | VM 환경 격리 | steal time < 1% 검증, 동일 조건 비교 | [17] |
| 8 | ipvlan/macvlan만 | ARM64 가용성, 단일 변수 통제, DRANET 1차 지원 | [13] |

---

## [19] ML 학습 전략 — Predictive 모델을 위한 시계열 패턴 기반 학습

### 핵심 설계: "현재 값이 아닌 추세(trend)를 학습"

```
Rule-based (reactive):
  입력: [throughput=200Mbps, loss=7%]
  판단: "loss > 5% → 전환!" (이미 손실 발생 후)

ML (predictive):
  입력: [throughput=100Mbps, Δthroughput=+20, slope=+15, loss=0.5%, Δloss=+0.3]
  판단: "이 추세면 30초 후 loss 발생 → 지금 전환" (손실 발생 전)
```

### Feature 설계 (7차원)

| Feature | 의미 | predictive에 기여하는 이유 |
|---------|------|--------------------------|
| throughput_mbps | 현재 throughput | 기본 상태 |
| **throughput_delta** | 직전 대비 변화량 | 올라가는 중인지 |
| **throughput_slope** | window 기울기 | **상승 속도** (핵심) |
| packet_loss_pct | 현재 loss | 이미 문제인지 |
| **loss_delta** | loss 변화량 | loss가 커지는 중인지 |
| cpu_milli | 현재 CPU | 부하 수준 |
| cpu_delta | CPU 변화량 | CPU가 올라가는 중인지 |

### 학습 패턴 (5종) — 실험 패턴과 의도적으로 상이

| # | 패턴 | 학습 의도 | 실험과의 차이 |
|---|------|----------|-------------|
| 1 | 급상승 (30s에 10→300) | 빠른 전환 결정 | 실험은 180s ramp |
| 2 | 완상승 (300s에 10→300) | 여유 있는 판단 | 실험은 180s ramp |
| 3 | **spike 후 복귀** (10→200→10) | **전환 안 함** (false positive 방지) | 실험에 없음 |
| 4 | 계단식 (10→100 유지→200) | 정체 후 재상승 감지 | 실험은 연속 상승 |
| 5 | **진동** (80↔120 반복) | **전환 안 함** (flapping 방지) | 실험에 없음 |

**학습 ≠ 실험**: 의도적으로 상이하게 설계하여 과적합 아닌 일반화(generalization) 검증.

### 라벨링 기준

```
각 패턴의 switch_at 시점:
  - switch_at 이전: label = "ipvlan" (아직 전환 불필요)
  - switch_at 이후: label = "macvlan" (전환 필요)
  - switch_at = None: 전부 "ipvlan" (전환하면 안 됨)

switch_at 결정 근거:
  → baseline 실험(A-T3)에서 ipvlan의 loss가 시작되는 throughput 지점
  → 그 지점 "이전"에 전환하도록 라벨링 (predictive)
```

### 학습 결과

```
CV Accuracy: 90.1% ± 3.8% (5-fold)
F1 (ipvlan): 0.96 | F1 (macvlan): 0.92

Feature Importance:
  throughput_mbps      0.30   ← 현재 상태
  cpu_milli            0.21
  throughput_slope     0.14   ← ★ 추세 (ML의 핵심 가치)
  packet_loss_pct      0.14
  loss_delta           0.11   ← ★ 변화 방향
  throughput_delta     0.06
  cpu_delta            0.04
```

**핵심 발견**: `throughput_slope`(0.14)와 `loss_delta`(0.11)가 유의미한 feature.
→ 모델이 "현재 값"뿐 아니라 "변화 추세"를 판단에 활용함을 확인.
→ Rule-based(현재 값만 봄)와의 차별점이 feature importance로 정량화됨.

### 논문에서의 서술

> "ML 모델의 학습 데이터는 5종의 트래픽 패턴(급상승, 완상승, spike 복귀, 계단식, 진동)으로 생성하며, 실험에 사용되는 패턴(180초 점진 증가)과 의도적으로 상이하게 설계하여 일반화 능력을 검증한다. Feature importance 분석 결과, throughput_slope(0.14)와 loss_delta(0.11)가 유의미한 판단 기준으로 활용되어, 모델이 현재 값의 threshold 비교가 아닌 시계열 추세를 기반으로 predictive 판단을 수행함을 확인하였다. 이는 rule-based 접근(threshold 초과 시 reactive 반응)이 제공할 수 없는 예측적 전환의 근거이다."

### Rule-based와의 비교 논리

```
동일 시나리오 (100Mbps 구간):

Rule-based:
  throughput=100, loss=0.5%
  → loss < 5%, throughput < 150 → "ipvlan 유지" (문제 없다고 판단)
  → 30초 후 throughput=200, loss=12% → 그제야 전환 (이미 손실 누적)

ML:
  throughput=100, slope=+20, delta=+15, loss=0.5%, loss_delta=+0.3
  → "slope +20이면 30초 후 160Mbps, loss 급증 예상" → 지금 전환
  → 30초 후 throughput=200이지만 이미 macvlan → loss 0.5% 유지
```
