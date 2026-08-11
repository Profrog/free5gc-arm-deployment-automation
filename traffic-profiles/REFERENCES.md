# References — UPF Data Plane Benchmarking

본 문서는 연구 제안서, 선행연구 레퍼런스(A), 본 연구의 설계 결정(B)으로 구성됩니다.

트래픽 프로파일 설계 시 참고한 논문 및 벤치마크 자료.

> **⚠️ 설계 변경 사항 (2026-08-09)**
> 초기 설계에서는 DRANET(DRA ResourceClaim)을 통한 인터페이스 전환을 계획하였으나,
> DRANET은 ipvlan/macvlan 서브인터페이스 **생성**을 지원하지 않음이 확인되었다.
> 최종 구현은 **커널 수준 IP 이동 방식**(dual-interface + `ip addr del/add`)으로,
> Pod/프로세스 재시작 없이 ~140ms 무중단 전환을 달성한다.
> 본 문서에서 DRANET 관련 기술은 선행연구 참조로만 유효하며, 
> 실제 전환 메커니즘은 "무중단 인터페이스 전환 메커니즘" 섹션 참조.

---

## 연구 제안서 — 논문 구조 및 실험 프로세스 요약

### Title

"NWDAF-Driven Dynamic CNI Backend Selection for Cloud-Native 5G Core on ARM: Intelligent Network Plane Management via Zero-Downtime IP Migration"

### Abstract (Draft)

Cloud-native 5G Core에서 User Plane Function(UPF)의 data plane 성능은 Container Network Interface(CNI) 드라이버 구현에 영향을 받는다. 선행연구에서 ipvlan과 macvlan은 패킷 분배 로직의 차이로 인해 workload 특성에 따라 상이한 성능을 보임이 확인되었으나, 5GC UPF 환경에서 이를 런타임에 동적으로 전환하고 그 판단의 정확성을 검증한 연구는 부재한다. 본 연구는 3GPP TS 23.288 NWDAF의 AnLF를 ML 분류 모델(Random Forest)로 구현하여 UPF KPI를 실시간 분석하고, 커널 수준 IP 이동 방식으로 CNI backend(ipvlan↔macvlan)를 Pod 재시작 없이 무중단 전환하는 closed-loop 시스템을 ARM64 환경에서 설계, 구현, 검증한다. 실험은 3가지 트래픽 시나리오와 3가지 CNI 전략의 조합(9개 실험)으로 구성되며, 전환 시간(~140ms), 전환 판단 정확성, 그리고 고정 CNI 대비 동적 전환의 실효성을 평가한다.

### 논문 구조

```
1. Introduction
   - 문제 정의: 정적 CNI 할당의 한계
   - 연구 질문: "NWDAF가 CNI 전환을 올바르게 판단하는가?"
   - Contribution 요약

2. Background & Related Work
   - 5GC UPF data plane (TS 23.501)
   - NWDAF 아키텍처 (TS 23.288, AnLF/MTLF 분리)
   - CNI 성능 비교 선행연구 (Qi 2021 IEEE TNSM)
   - ipvlan vs macvlan 커널 메커니즘 (Bandewar 2015)
   - DRANET/DRA — 선행연구 참조 (미채택 근거 포함)

3. System Design
   - 전체 아키텍처: free5GC + NWDAF on ARM64 K8s (단일 노드, 4 vCPU)
   - 전환 메커니즘: dual-bridge + ip -batch (커널 수준 IP 이동)
   - NWDAF AnLF: OAM 수집 → ML 추론 → 전환 실행
   - ML 모델: Random Forest (model-agnostic 표준 준수)
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
│ 2. Multus CNI + dual-bridge 구성 (n3br + n3br-ipv)     │
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

> NWDAF ML 모델이 UPF의 KPI를 기반으로 CNI backend 전환을 올바르게 판단하는지를, 커널 수준 IP 이동 기반 closed-loop 시스템으로 구현하고, ARM64 containerised 환경에서 격리된 실험으로 검증한다.

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
| 8 | ipvlan/macvlan만 | ARM64 가용성, 단일 변수 통제 | [13] |
| 9 | DRANET 안 쓰는데? | DRANET은 ipvlan↔macvlan 미지원 확인, IP 이동이 더 적합 | [7] |

---

# A. 선행연구 레퍼런스

---

## [A1] Kernel-Level Per-Slice UPF Latency Measurement in Containerised 5G Core Networks

- **저자**: Akhil Dev Mishra, Mayank Pandey
- **출처**: arXiv:2605.28185, May 2026
- **URL**: https://arxiv.org/abs/2605.28185

### 주요 결과
- UPF forwarding delay는 부하에 비례하여 증가 (Light ~300μs → Heavy ~800μs)
- PFCP session modification latency: <200μs (data-plane load 무관)
- TC-BPF instrumentation으로 per-packet delay 정밀 측정 (28M pairs)

### 본 연구와의 관계
- **부하 단계별 측정 패턴**: Light/Medium/Heavy → 본 프로젝트 `upf-stress.yaml` Phase 3 (stepped load 6단계)
- **임계점 탐색**: 부하를 올려가며 "어디서부터 CNI 전환이 필요한가"의 기준점 도출
- **측정 방식 차이**: 이 논문은 TC-BPF(커널 hook)으로 per-packet delay 측정, 본 프로젝트는 `/proc/net/dev` + iperf3로 throughput/loss 측정

---

## [A2] Simple Measurement of UPF Performance

- **저자**: s5uishida
- **출처**: GitHub Repository, Dec 2023
- **URL**: https://github.com/s5uishida/simple_measurement_of_upf_performance

### 주요 결과 (free5GC UPF v1.2.0, x86 VM 환경)
| Metric | Value |
|--------|-------|
| TCP throughput | 233 Mbps |
| UDP throughput (offered 500M) | 382 Mbps (receiver) |
| UDP packet loss | 23% |
| RTT (ping) | 0.786ms |

### UPF 비교
| UPF | UDP (recv) | Loss | 비고 |
|-----|-----------|------|------|
| UPG-VPP v1.11.0 | 455 Mbps | 0.96% | DPDK 기반, 고성능 |
| eUPF v0.6.0 | 409 Mbps | 3.6% | eBPF 기반 |
| free5GC go-upf | 382 Mbps | 23% | 커널 TUN 기반 |
| Open5GS UPF | 319 Mbps | 30% | 커널 TUN 기반 |

### 본 연구와의 관계
- **성능 기준선**: free5GC go-upf의 x86 성능(200~400Mbps)을 기준으로 ARM64 실험 설계
- **ARM64 성능 차이 활용**: ARM64에서는 추가 성능 저하 예상(40~60% 수준) → CNI 변경에 따른 KPI 차이가 x86보다 크게 관측됨 → 실험 민감도 향상에 유리
- **iperf3 -u -b 500M 조건 재현**: 본 프로젝트 `upf-stress.yaml` Phase 2에서 동일 조건으로 ARM64 차이 비교
- **loss 임계점**: UDP 고부하 시 loss 급증 → NWDAF가 전환을 판단해야 하는 시점의 근거

---

## [A3] 5G UPF Performance on Intel Xeon (Reference — Commercial Scale)

- **출처**: Intel Network Builders, 2024
- **URL**: https://builders.intel.com/docs/networkbuilders/5g-flexcore-2-0-user-plane-function...
- **결과**: 948 Gbps (94.8% line rate), 0% packet loss
- **비고**: DPDK 기반 상용 UPF. open-source UPF와 2~3 order of magnitude 차이.

### 본 연구와의 관계
- **커널 경로가 병목임을 증명**: 동일 UPF 기능이라도 DPDK(커널 우회)로 948Gbps, 커널 기반으로 200~400Mbps → 성능 차이의 원인은 커널 네트워크 경로
- **본 연구의 전제 정당화**: 커널 경로가 병목이므로, 커널 레벨에서 경로를 바꾸는 것(macvlan↔ipvlan 전환)이 KPI에 실질적 영향을 줌
- **프로파일 차이**: 이 논문은 line rate 도달 여부만 확인 (pass/fail), 본 프로젝트는 부하 단계별 KPI 변화 추이를 관측 (성능 곡선)

---

## [A4] 3GPP TS 23.288 — Network Data Analytics Services (NWDAF)

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

## [A5] 3GPP TS 23.501 — System Architecture for the 5G System (5GS)

- **출처**: 3GPP, Release 17
- **URL**: https://www.3gpp.org/DynaReport/23501.htm

### 본 연구 관련 내용
- Table 5.7.4-1: 5QI 특성 정의 (5QI=9: Non-GBR, best effort, delay budget 300ms)
- UPF의 역할: PDU Session anchor, GTP-U tunneling, packet forwarding
- N3(gNB↔UPF), N4(SMF↔UPF PFCP), N6(UPF↔DN) 인터페이스 정의
- **UPF의 네트워크 인터페이스 구현 방식은 규정하지 않음** (벤더/오퍼레이터 자유)

---

## [A6] 3GPP TS 29.244 — Interface between the Control Plane and the User Plane (PFCP)

- **출처**: 3GPP, Release 17
- **URL**: https://www.3gpp.org/DynaReport/29244.htm

### 본 연구와의 관계
- **무중단 전환의 세션 유지 논증 근거**: CNI 전환 시 IP가 불변이므로 PFCP 세션(SMF↔UPF)이 끊기지 않음을 이 표준으로 정당화
- PFCP 세션은 IP 주소 기반으로 유지됨 → IP 이동 방식은 세션에 투명

---

## [A7] DRANET: A Composable Architecture for High-Performance Networking in Kubernetes

- **저자**: Antonio Ojea et al. (kubernetes-sigs)
- **출처**: arXiv:2506.23628, Jun 2025
- **URL**: https://arxiv.org/abs/2506.23628
- **GitHub**: https://github.com/kubernetes-sigs/dranet

### 핵심 내용
- Kubernetes DRA (Dynamic Resource Allocation, v1.34 GA) 위에서 네트워크 디바이스를 관리
- DeviceClass로 네트워크 인터페이스 추상화 (ipvlan, macvlan, SR-IOV, RDMA)
- ResourceClaim 변경으로 **런타임에** 네트워크 백엔드 전환 가능
- 기존 적용 대상: AI/ML workload의 RDMA 디바이스

### 본 연구와의 관계
- DRANET의 개념(DRA 기반 네트워크 관리)을 참고하되, 실제 전환은 커널 수준 IP 이동 방식으로 구현
- NWDAF의 결정을 `ip addr del/add`로 실행하여 무중단 전환 달성

### 본 연구에서 쓸 수 없는 한계 (미채택 근거)
- **ipvlan/macvlan 서브인터페이스 생성 미지원**: DRANET은 SR-IOV, RDMA 등 하드웨어 디바이스 관리가 주 대상이며, 같은 master 위에 ipvlan↔macvlan을 동적 전환하는 기능 없음
- **IP 변경 가능성**: ResourceClaim 변경 시 인터페이스가 재생성되어 IP가 바뀔 수 있음 → GTP-U/PFCP 세션 끊김 위험
- **전환 시간**: ResourceClaim 변경 → DRANET reconcile → 인터페이스 재구성에 수 초 소요 (본 연구 ~140ms 대비 느림)

---

## [A8] NWDAF 관련 유사 연구 비교

| 연구 | NWDAF 구현 | ML 모델 | 대상 NF | 실행(Action) | closed-loop | 본 연구와의 차이 |
|------|-----------|---------|---------|-------------|-------------|-----------------|
| [Ardestani 2025](https://arxiv.org/abs/2505.06789) (Waterloo) | ✅ 3GPP 준수 | Graph-based RF | UPF | PDU session release | ✅ | 보안(bot detection), CNI 전환 아님 |
| [LLM-NWDAF 2026](https://arxiv.org/abs/2606.11877) (Waterloo) | ✅ | LLM | 전체 NF | 분석만 (실행 없음) | ❌ | 분석 강화 목적, 인프라 실행 없음 |
| [Bayleyegn 2024](https://ieeexplore.ieee.org/document/10582517) (NetSoft) | ✅ | Random Forest | UPF | 트래픽 분류 | ❌ | 분류만, 전환 실행 없음 |
| [Kan 2024](https://arxiv.org/abs/2410.03576) | ✅ | LLM | 전체 | 정책 제안 | ❌ | 제안만, 자동 실행 없음 |
| **본 연구** | **✅ AnLF** | **Random Forest** | **UPF** | **CNI 전환 (ip -batch)** | **✅** | **인프라 레이어까지 실행 + 무중단** |

### 핵심 차별점
- 기존 연구: NWDAF의 **분석/판단**까지만 구현 (실행은 수동 또는 NF 레벨)
- 본 연구: NWDAF의 판단을 **인프라 레이어(커널 CNI 전환)까지 자동 실행**하고, 그 판단의 정확성을 검증

### NWDAF 최소 구현의 정당성 (3GPP TS 23.288 §6.2A, Rel-17)

AnLF와 MTLF는 독립 배치 가능한 논리 기능으로 분리되어 있으며, 부분 구현이 명시적으로 허용됨.

| 기능 | 구현 여부 | 정당화 |
|------|----------|--------|
| AnLF — 데이터 수집 | ✅ | OAM 경유 (kubectl top + /proc/net/dev) |
| AnLF — 분석/추론 | ✅ | ML 분류 모델 (Network Performance Analytics ID) |
| AnLF — 결과 출력 → 전환 실행 | ✅ | nwdaf-switch.sh (ip -batch) |
| MTLF — 모델 학습 | ✅ | offline 학습 (AnLF와 분리 배치 허용) |
| Nnwdaf 서비스 인터페이스 | ❌ | 단일 시스템 내부 연동으로 단순화 |
| 인프라 실행 (CNI 전환) | ✅ | 3GPP scope 밖, 표준 위반 아님, operator-specific |

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

## [A9] CNI 타입별 성능 차이 근거 — 전환 판단의 유효성 뒷받침

> **핵심 질문**: "CNI를 바꾸면 KPI가 실제로 변하는가?" + "전후 비교로 판단을 평가하는 게 유효한가?"

### A. CNI 차이가 측정 가능하다

| 논문 | 출처 | 결과 | 본 연구에서의 의의 |
|------|------|------|-------------------|
| [macvlan/ipvlan 성능 분석](https://www.shs-conferences.org/articles/shsconf/abs/2023/15/shsconf_eimm2023_01072/shsconf_eimm2023_01072.html) | SHS 2023 | ipvlan이 일반 환경에서 더 나은 성능 | 전환이 측정 가능한 차이를 만듦 |
| [K8s CNI Latency Evaluation](https://www.mdpi.com/2079-9292/13/19/3972) | MDPI Electronics 2024 | workload별 최적 CNI가 다름 | 동적 전환의 당위성 |
| [Edge 환경 CNI 성능](https://arxiv.org/abs/2401.07674) | IEEE INFOCOM Workshop 2024 | 자원 제약 환경에서 CNI 차이가 더 큼 | ARM64 환경에서 차이 관측이 용이 |
| [Bare-Metal vs K8s 5GC](https://www.researchgate.net/publication/384801122) | ResearchGate 2024 | K8s 위 5GC가 bare-metal 대비 throughput 7%↓ | CNI가 5GC 성능의 실질적 병목 |
| [CNI Plugin 벤치마크](https://par.nsf.gov/servlets/purl/10299326) | NSF/IEEE 2021 | CNI별 throughput/latency 체계적 비교 | iperf3 + 반복 측정 방법론 참조 |

### B. "전후 KPI 비교"가 유효한 평가 방법이다

| 표준/프레임워크 | 출처 | 핵심 | 본 연구에서의 의의 |
|----------------|------|------|-------------------|
| 3GPP TS 23.288 NWDAF Feedback Loop | 3GPP | 판단→실행→KPI 관측→정확성 평가 | 본 연구의 검증 방식 = 표준 패턴 |
| [ETSI ZSM 002](https://www.etsi.org/deliver/etsi_gs/ZSM/001_099/002/) | ETSI 2022 | Intent→Decision→Execution→Observation | 표준 자동화 평가 절차에 부합 |
| ITU-T Y.1731 | ITU 2020 | 변경 전후 PM 비교로 효과 판단 | 통신 업계 표준 운용 절차 |
| [ETSI NFV-TST 009](https://www.etsi.org/deliver/etsi_gs/NFV-TST/001_099/009/) | ETSI 2018 | 인프라 변경의 영향을 KPI로 정량화 | CNI 변경 효과 측정의 표준 근거 |
| O-RAN AI/ML Workflow | O-RAN WG2 2023 | action 전후 KPI로 모델 평가 | 통신 AI에서의 업계 표준 방법 |

### C. 커널 메커니즘: 왜 macvlan/ipvlan이 KPI에 차이를 만드는가

| 논문 | 출처 | 핵심 내용 | 본 연구에서의 의의 |
|------|------|----------|-------------------|
| [IPVLAN — The Beginning](http://people.netfilter.org/pablo/netdev0.1/papers/IPVLAN-The-beginning.pdf) | netdev 0.1, Bandewar/Google 2015 | ipvlan: 커널 L3 라우팅 / macvlan: NIC 레벨 MAC 분리 | 고부하 시 macvlan 유리, 저부하 시 ipvlan 유리의 기술적 원인 |
| [Data Plane Optimization](https://www.researchgate.net/publication/221198708) | ACM SIGCOMM Workshop 2011 | macvlan NAPI vs softnet queue throughput 차이 | 커널 경로 차이 → 측정 가능한 성능 차이 |
| [Linux Networking CPU Impact](https://netdevconf.org/0x17/docs/netdev-0x17-paper34-talk-slides/) | NetDev 0x17, 2023 | 인터페이스 타입별 패킷당 CPU cycle 정량화 | CNI 타입 → CPU 사용량 인과관계 근거 |

### 핵심 요약

기존 연구는 모두 **정적 비교**에 그쳤으며, 런타임에 동적으로 전환하고 그 판단의 정확성을 자동 검증하는 시스템을 구현한 연구는 없다.

---

## [A10] 트래픽 프로파일 ↔ CNI 적합성 매핑 근거

> NWDAF가 "ipvlan / macvlan 중 어느 것이 정답인가"를 판단할 때의 ground truth 정의.

### ipvlan vs macvlan 적합 조건

| 조건 | ipvlan 유리 | macvlan 유리 |
|------|------------|-------------|
| 패킷 크기 | 소패킷 (64~256B) | 대패킷 (1400B+) |
| 트래픽 패턴 | 고 PPS, burst | 고 throughput, sustained |
| CPU 특성 | per-packet overhead 낮음 | NIC offload(TSO/GRO) 활용 |
| UE 수 | 다수 (MAC table 이슈 없음) | 소수 |

근거: [IPVLAN — The Beginning (Bandewar/Google 2015)](http://people.netfilter.org/pablo/netdev0.1/papers/IPVLAN-The-beginning.pdf), [IETF draft-samizadeh-bmwg-cni-benchmarking-02 (2026)](https://datatracker.ietf.org/doc/draft-samizadeh-bmwg-cni-benchmarking/)

### 3GPP 트래픽 모델 → 프로파일 → CNI 매핑

| 3GPP 서비스 | 트래픽 특성 | 대응 프로파일 | 적합 CNI |
|------------|-----------|-------------|---------|
| mMTC ([TS 22.261](https://www.3gpp.org/DynaReport/22261.htm) §7.2) | 소패킷(128B), burst, 다수 UE | `iot-burst.yaml` | ipvlan |
| VoNR ([TS 26.114](https://www.3gpp.org/DynaReport/26114.htm)) | 초소형(80B), 20ms 주기 | `vonr.yaml` | ipvlan |
| eMBB ([TR 38.913](https://www.3gpp.org/DynaReport/38913.htm)) | 대패킷(1400B), 500Mbps | `streaming-dl.yaml` | macvlan |

### 실험 시나리오 (T3: 소→대 전환)

```
소패킷 구간 (ipvlan 적합) → 트래픽 변화 → 대패킷 구간 (macvlan 적합)
                                    ↑
                          NWDAF가 여기서 전환을 판단해야 함
```

### 벤치마킹 방법론 준수 (IETF BMWG)

| IETF 요구사항 | 본 연구 대응 |
|--------------|-------------|
| packet sizes: 64B, 512B, 1500B | 64B (Phase 1), 128B (iot-burst), 1400B (streaming-dl) |
| minimum 5 repetitions | ✅ 5회 반복 |
| CPU/memory per CNI process | monitor-collector.sh에서 수집 |

---

## [A11] ARM vs x86 아키텍처 차이와 네트워크 성능 영향

> ARM 환경에서 커널 경로 차이에 따른 KPI 변화가 x86보다 크게 관측됨 → 실험 민감도 향상에 유리

### 본 연구와의 관계
- ARM에서 per-packet 처리 비용이 상대적으로 큼 → 커널 경로(macvlan vs ipvlan) 차이가 throughput에 더 크게 반영
- 즉, ARM이 CNI 전환 효과를 관측하기에 **더 적합한 실험 플랫폼**

### 참고 문헌

| 논문 | 출처 | 핵심 결과 |
|------|------|----------|
| [ARM vs Intel Networking](https://netdevconf.org/0x17/docs/netdev-0x17-paper9-talk-slides/) | NetdevConf 0x17, 2023 | ARM이 per-packet latency에서 열세, 경로 차이 영향 증폭 |
| [ARM vs x86 Performance](https://arxiv.org/abs/2604.18896) | arXiv 2026 | x86이 branch-heavy에서 빠름, ARM은 에너지 효율 5.8×↑ |
| [x86/ARM Architecture Survey](https://www.researchgate.net/publication/362105591) | ResearchGate 2022 | 파이프라인, SIMD, 메모리 모델 차이 서베이 |
| [ARM vs x86 Trends](https://www.researchgate.net/publication/353115679) | ResearchGate 2021 | ARM 기술 발전으로 성능 격차 축소 중 |
| [Gem5 ARM/x86 Simulation](https://www.researchgate.net/publication/325978796) | ResearchGate 2018 | In-Order/Out-of-Order IPC 차이 정량 분석 |

---

# B. 본 연구의 설계 결정

---

## [B1] ipvlan/macvlan 동일 위상 — 네트워크 인터페이스 드라이버 관계

참조: [IPVLAN — The Beginning (Bandewar 2015)](http://people.netfilter.org/pablo/netdev0.1/papers/IPVLAN-The-beginning.pdf), [Linux Kernel: macvlan](https://www.kernel.org/doc/html/latest/networking/macvlan.html)

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

### 기존 방식 vs 본 연구 (IP 이동 방식)

| | 기존 (Pod 재생성) | 본 연구 (IP 이동) |
|---|---|---|
| 전환 방식 | Pod 삭제 → 새 CNI로 재생성 | `ip addr del/add`로 IP 이동 |
| 전환 시간 | 수 초 (Pod lifecycle) | **~140ms** (커널 명령) |
| Pod 재생성 | 필요 | **불필요** |
| UPF 프로세스 재시작 | 필요 | **불필요** |
| GTP-U/PFCP 세션 | 끊김 | **유지** |
| 인프라 | Multus만 | Multus + dual-bridge (n3br + n3br-ipv) |

### 논문에서의 서술

> "ipvlan과 macvlan은 동일 위상(물리 NIC 상위의 가상 sub-interface)에 위치하며, 패킷 분배 로직만 상이한 커널 드라이버이다. 본 연구는 UPF Pod에 macvlan과 ipvlan 인터페이스를 동시에 attach하고, 커널 수준에서 IP 주소를 인터페이스 간 이동하여 무중단 전환을 실현한다. UPF 프로세스는 동일 IP에 bind된 socket을 유지하므로 GTP-U 및 PFCP 세션이 유지되며, 전환 시간은 ~140ms로 기존 Pod 재생성 방식(수 초) 대비 대폭 단축된다."

---

## [B2] 실험 설계 — 트래픽 시나리오 × CNI 전략 매트릭스

참조: [IETF draft-samizadeh-bmwg-cni-benchmarking-02](https://datatracker.ietf.org/doc/draft-samizadeh-bmwg-cni-benchmarking/), [3GPP TS 22.261](https://www.3gpp.org/DynaReport/22261.htm), [3GPP TR 38.913](https://www.3gpp.org/DynaReport/38913.htm)

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
| C | NWDAF ML 기반 동적 전환 | NWDAF가 KPI 관측 → ML 모델 판단 → IP 이동 전환 실행 |

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

## [B3] NWDAF 데이터 수집 경로: OAM 방식 선택의 정당성

참조: [3GPP TS 23.288](https://www.3gpp.org/DynaReport/23288.htm), [3GPP TS 29.564](https://www.3gpp.org/DynaReport/29564.htm), [Ardestani 2025 (Waterloo)](https://arxiv.org/abs/2505.06789), [free5GC NWDAF Blog](https://free5gc.org/blog/)

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

## [B4] ML 설계 — 모델 선택 / Feature / 학습 전략

참조: [3GPP TS 23.288](https://www.3gpp.org/DynaReport/23288.htm), [Bayleyegn 2024 (NetSoft)](https://ieeexplore.ieee.org/document/10582517), [Ardestani 2025](https://arxiv.org/abs/2505.06789), [Breiman 2001 — Random Forests](https://link.springer.com/article/10.1023/A:1010933404324), [scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html)

### 모델 선택: Random Forest

3GPP TS 23.288은 model-agnostic (알고리즘 미지정, 구현자 재량).

| 기준 | Random Forest | Deep Learning (LSTM 등) |
|------|--------------|------------------------|
| ARM64 추론 속도 | <1ms | 수십~수백ms |
| 학습 데이터 양 | 수백 샘플로 충분 | 수천~수만 필요 |
| 해석 가능성 | feature importance 제공 | black box |
| 5초 주기 판단 | ✅ 여유 | ⚠️ 빠듯 |
| 학계 선례 | Bayleyegn 2024, Ardestani 2025 | 자원 제약 환경 부적합 |

### Feature 설계 (5개 기본 + 2개 추세)

| Feature | 3GPP 근거 | 역할 |
|---------|-----------|------|
| `throughput_mbps` | Network Performance | 워크로드 구분 (importance: 0.65) |
| `total_pps` | UPF volume measurement | 패킷 빈도 |
| `packet_loss_pct` | Network Performance | CNI 한계 도달 감지 |
| `cpu_milli` | NF Load | 시스템 부하 |
| `mem_mi` | NF Load | 시스템 부하 |
| `throughput_slope` | (파생) | ★ 상승 추세 — predictive 판단 핵심 |
| `loss_delta` | (파생) | ★ loss 변화 방향 |

비고: `throughput_mbps / total_pps`로 평균 패킷 크기가 암묵적으로 인코딩됨.

### 학습 전략: Predictive (추세 기반)

```
Rule-based (reactive): loss > 5% → 전환 (이미 손실 발생 후)
ML (predictive):       slope +20이면 30초 후 loss 예상 → 지금 전환 (손실 전)
```

**학습 패턴 5종** (실험 패턴과 의도적으로 상이 → 일반화 검증):

| # | 패턴 | 학습 의도 |
|---|------|----------|
| 1 | 급상승 (30s에 10→300) | 빠른 전환 결정 |
| 2 | 완상승 (300s에 10→300) | 여유 있는 판단 |
| 3 | spike 후 복귀 | **전환 안 함** (false positive 방지) |
| 4 | 계단식 | 정체 후 재상승 감지 |
| 5 | 진동 (80↔120 반복) | **전환 안 함** (flapping 방지) |

### 학습 결과

```
CV Accuracy: 90.1% ± 3.8% (5-fold)
F1 (ipvlan): 0.96 | F1 (macvlan): 0.92

Top Feature Importance:
  throughput_mbps   0.30
  cpu_milli         0.21
  throughput_slope  0.14  ← ★ 추세 활용 확인
  packet_loss_pct   0.14
  loss_delta        0.11  ← ★ 변화 방향
```

핵심 발견: `throughput_slope`와 `loss_delta`가 유의미 → 모델이 "추세"를 판단에 활용함 확인 → Rule-based와의 차별점.

---

## [B5] 실험 격리 — CPU Pinning 및 검증

참조: [Kubernetes CPU Manager](https://kubernetes.io/docs/tasks/administer-cluster/cpu-management-policies/), [IETF draft-samizadeh-bmwg-cni-benchmarking-02 §7.3](https://datatracker.ietf.org/doc/draft-samizadeh-bmwg-cni-benchmarking/)

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

---

## [B6] 실험 측정 범위 (Measurement Scope Limitation)

### 현재 테스트베드 구성

```
UE (iperf3 client)                    UPF (iperf3 server)
    │                                      │
    │  uesimtun0 (GTP-U tunnel)            │  N3: 10.10.3.1
    ▼                                      ▼
  gNB ─────── N3 ─────────────────────→ UPF ──╳── (DN Server 없음)
                                              │
                                              ▼ 외부 연결 없음
                                         iperf3가 여기서 수신
```

### 측정 가능 범위

| 방향 | 경로 | 측정 가능 | 비고 |
|------|------|-----------|------|
| **Uplink** | UE → gNB → UPF (iperf3 server) | ✅ | GTP-U encap/decap 포함 |
| **Downlink (loopback)** | UPF (iperf3 -R) → gNB → UE | ⚠️ 제한적 | UPF 내부 loopback, 진짜 DN 경유 아님 |
| **End-to-End DL** | DN Server → UPF → gNB → UE | ❌ 미측정 | DN 측 외부 서버 미구성 |

### 논문 기술 시 주의사항

본 실험 환경에서 트래픽 제네레이터(iperf3 client)는 UE 측에서 UPF의 N3 인터페이스(10.10.3.1)를 직접 타겟으로 하며, UPF 자체가 iperf3 서버로 동작한다. 따라서:

1. **측정 대상**: UE에서 UPF까지의 **uplink 데이터플레인 성능** (GTP-U encapsulation/decapsulation forwarding throughput, latency, packet loss)
2. **측정 범위 외**: DN(Data Network) 측 외부 서버를 경유하는 end-to-end 양방향 성능은 본 실험의 측정 범위에 포함되지 않음
3. **Bidirectional phase**: iperf3 `-R` (reverse) 옵션을 사용한 DL 측정은 UPF 내부 loopback 기반이며, 실제 외부 DN 서버로부터의 downlink 트래픽 경로를 반영하지 않음

### 논문 서술 예시

> "본 실험은 UE에서 UPF까지의 uplink 데이터플레인 포워딩 성능을 측정한다. 트래픽 제네레이터는 GTP-U 터널을 통해 UPF의 N3 인터페이스에 직접 iperf3 트래픽을 전송하며, UPF가 종단점(iperf3 server)으로 동작한다. DN(Data Network) 측 외부 서버를 경유하는 end-to-end downlink 성능은 본 실험의 측정 범위에 포함하지 않는다. Bidirectional 테스트의 downlink 방향은 UPF loopback 기반으로, 실제 DN 서버 경유 경로와는 차이가 있음을 밝힌다."

### End-to-End 측정을 위한 향후 확장

완전한 양방향 e2e 측정을 위해서는 다음 구성이 필요:

```
UE (client) → gNB → UPF → N6 → DN Server (iperf3 server)
                              ←        (reverse direction)
```

- UPF의 N6(DN) 인터페이스에 별도 트래픽 서버 Pod 배치
- 또는 외부 VPC/물리 서버에 iperf3 서버 구성
- 이를 통해 UPF의 UL/DL 포워딩 비대칭성, NAT 오버헤드, DN 경로 latency 포함 측정 가능

---

## [B7] 무중단 인터페이스 전환 메커니즘 (Zero-Downtime CNI Backend Switching)

### 핵심 원리

UPF Pod에 macvlan과 ipvlan 인터페이스를 **동시에 미리 attach**하고, IP 주소를 인터페이스 간 이동하여 전환한다. UPF 프로세스 재시작 없이 커널 레벨에서 패킷 경로만 변경된다.

```
UPF 프로세스: bind("10.10.3.1")  ← 불변

커널:
  n3  (macvlan on n3br)     ← IP 있으면 여기로 패킷 전달
  n3i (ipvlan on n3br-ipv)  ← IP 있으면 여기로 패킷 전달

전환 = IP 라벨을 한 인터페이스에서 다른 인터페이스로 이동
```

### 전환 명령 (atomic batch — 마이크로초 단위 gap)

```bash
# macvlan → ipvlan (netlink batch: del/add를 커널에 한번에 전송)
kubectl exec $UPF_POD -- sh -c '
  ip -batch - <<EOF
addr del 10.10.3.1/24 dev n3
addr add 10.10.3.1/24 dev n3i
EOF
'
```

### 전환 중 패킷 유실 리스크 및 조치

#### 리스크

`ip addr del`과 `ip addr add` 사이에 해당 IP를 가진 인터페이스가 없는 순간이 존재한다.
이 구간에 도착하는 패킷은 커널이 목적지를 찾지 못해 drop한다.
GTP-U는 UDP 기반이므로 재전송 메커니즘이 없어, drop된 패킷은 영구 유실된다.

#### 조치: netlink batch

개별 명령 실행 시 gap이 수 밀리초 발생하나, `ip -batch`를 사용하면
두 명령이 하나의 netlink 메시지로 커널에 전달되어 연속 처리된다.
이로써 gap을 수 마이크로초 수준으로 축소한다.

```
개별 실행: shell → del → [수ms gap] → add     (수십~수백 패킷 drop 가능)
batch 실행: shell → [del+add] → 커널 연속 처리  (0~1 패킷 drop 수준)
```

#### 논문에서의 해석: 성능 비용(performance cost)으로 정량화

전환 중 발생하는 패킷 drop은 "무중단"의 한계가 아니라 **전환 비용(switching cost)**으로 정량화한다:

- **drop_count**: 전환 전후 `/proc/net/dev`의 rx_dropped 차이로 측정
- **drop_duration**: batch 실행 시간 (마이크로초 단위)
- **throughput_loss**: drop_count × packet_size / switch_duration

이를 전환 이득(Δthroughput × remaining_time)과 비교하여 cost-benefit 분석에 포함한다.

> "전환 중 netlink batch 처리 gap(수 μs)에 의한 패킷 유실은 전환 비용으로 정량화하며, 
> 본 실험에서 측정된 평균 drop은 N개 패킷(Y μs)으로 전체 세션 throughput 대비 
> Z% 미만의 성능 손해에 해당한다. 이는 전환 이득(Δthroughput × T_remaining) 대비 
> 무시 가능한 수준이다."

### 인프라 구성

Linux 커널은 같은 master 인터페이스에 macvlan과 ipvlan을 동시에 생성할 수 없으므로, 별도 bridge를 veth pair로 연결하여 같은 L2 도메인을 유지한다.

```
n3br (OVS bridge)              n3br-ipv (Linux bridge)
  │                               │
  ├── macvlan: gNB n3             └── ipvlan: UPF n3i
  ├── macvlan: UPF n3
  │                    
  └── veth-n3mac ─────────── veth-n3ipv
       (같은 L2 도메인으로 연결)
```

### 검증 결과

| 항목 | 결과 |
|------|------|
| macvlan → ipvlan 전환 | ✅ 성공 |
| ipvlan → macvlan 전환 | ✅ 성공 |
| UPF 프로세스 재시작 | 불필요 |
| Pod 재생성 | 불필요 |
| GTP-U 세션 유지 | ✅ (IP 불변) |
| PFCP 세션 유지 | ✅ (IP 불변) |
| UE connectivity | ✅ 전환 전후 모두 유지 |
| 전환 시간 | ~밀리초 (ip addr del + add) |

### 선행 기술 참조

- **Multus Dynamic Networks Controller** (k8snetworkplumbingwg)
  - URL: https://github.com/k8snetworkplumbingwg/multus-dynamic-networks-controller
  - Pod 재시작 없이 네트워크 인터페이스 hotplug/unplug
  - KubeVirt NIC hotplug에서 실 사용
  - 본 연구에서는 IP 이동 방식이 더 빠르고 단순하여 직접 exec 방식 채택

- **FOSDEM 2022: Interface Hotplug for Kubernetes**
  - Kubernetes 런타임 중 네트워크 인터페이스 hotplug 방법론

- **KubeVirt NIC Hotplug Design Proposal**
  - URL: https://github.com/kubevirt/community/blob/main/design-proposals/nic-hotplug/nic-hotplug.md
  - VM 환경에서의 런타임 NIC 추가/제거 설계

### 논문 서술 예시

> "본 시스템은 UPF Pod에 macvlan과 ipvlan 인터페이스를 동시에 attach하고, NWDAF의 판단에 따라 커널 수준에서 IP 주소를 인터페이스 간 이동하여 무중단 전환을 실현한다. UPF 프로세스는 동일 IP에 bind된 socket을 유지하므로, GTP-U 및 PFCP 세션이 끊기지 않으며 전환 시간은 밀리초 단위이다. 이는 기존 Pod 재생성 방식(수 초) 대비 3자릿수 이상의 전환 시간 단축을 달성한다."

### 전환 비용 (Switching Cost)

`ip -batch`로 전환 시에도 수 마이크로초의 gap이 존재하며, 이 구간에 패킷 drop 가능.

| 메트릭 | 측정 방법 | 의미 |
|--------|----------|------|
| switching_duration | 전환 명령 → throughput 복귀까지 시간 | 전환에 걸리는 시간 |
| packets_lost | 전환 구간의 /proc/net/dev rx_dropped 차이 | 직접적 손실 |
| throughput_dip | 전환 중 최저 throughput | 서비스 영향도 |

**Cost-benefit 판단 기준:**
```
전환 이득 = Δthroughput × T_remaining
전환 비용 = packet_rate × switching_duration
→ Gain > Cost 일 때만 전환
```

---

## [B8] 표준 준수 범위와 확장 경계 (Standard Compliance Boundary)

### 문제: "NWDAF가 CNI를 전환하는 게 3GPP 표준인가?"

본 연구에서 가장 명확히 해야 할 부분은 **3GPP 표준 준수 범위**와 **본 연구의 확장 범위**의 경계이다.

### 3GPP NWDAF (TS 23.288)가 정의하는 것

| 항목 | 표준 정의 |
|------|-----------|
| Analytics ID | Network Performance, NF Load, QoS Sustainability, UE Mobility 등 |
| 데이터 수집 경로 | NF Event Exposure, OAM, DCCF (OR 관계) |
| ML 구조 | AnLF (추론), MTLF (학습) 분리 |
| Analytics 소비자 | SMF, PCF, AMF, NEF |
| 실행 동작 | PFCP session modification, QoS 정책 변경, 슬라이스 재선택 |

### 3GPP NWDAF가 정의하지 않는 것 (unspecified)

- 인프라 레이어 (CNI, 커널 네트워크 인터페이스) 제어
- Kubernetes/컨테이너 오케스트레이션 연동
- 물리/가상 NIC 수준의 경로 전환
- Operator-specific analytics ID의 내용 (추가는 허용하나 내용 미규정)

### 본 연구의 아키텍처: 2-Layer 분리

```
┌─────────────────────────────────────────────────────────┐
│  Analytics Layer (3GPP TS 23.288 준수)                    │
│                                                         │
│  ┌───────────────┐      ┌────────────────────┐         │
│  │ Data Collection│      │  AnLF (ML 판단)     │         │
│  │ - OAM 경로     │─────→│  - RF Classifier   │         │
│  │ - Network Perf │      │  - 입력: 5 KPI     │         │
│  │   KPI 수집     │      │  - 출력: CNI 추천   │         │
│  └───────────────┘      └────────┬───────────┘         │
│                                  │ Analytics Output      │
└──────────────────────────────────┼──────────────────────┘
                                   │
═══════════════════════════════════════════════════════════════
          확장 경계 (Extension Boundary)
═══════════════════════════════════════════════════════════════
                                   │
┌──────────────────────────────────┼──────────────────────┐
│  Actuation Layer (본 연구 제안 — Operator-defined)        │
│                                  ▼                      │
│  ┌──────────────────────────────────────────────┐      │
│  │  Infrastructure Actuator                      │      │
│  │  - NWDAF analytics output 수신                │      │
│  │  - CNI backend 전환 판단 → 실행               │      │
│  │  - ip -batch (커널 레벨 IP 이동)              │      │
│  │  - 전환 비용/이득 cost-benefit 평가           │      │
│  └──────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────┘
```

### 표준 적합성 논증

| 예상 비판 | 방어 논리 | 근거 |
|-----------|-----------|------|
| "NWDAF가 CNI를 전환하라는 건 표준에 없다" | 맞다. 전환은 NWDAF가 아닌 Actuation Layer가 수행한다. NWDAF는 판단만 한다. | TS 23.288 §6.1: Analytics consumer가 analytics를 어떻게 활용할지는 consumer의 재량 |
| "CNI 선택이라는 Analytics ID는 없다" | Operator-defined analytics로 정당화. 표준은 추가를 금지하지 않음. | TS 23.288 §6.2.1: "The list of Analytics IDs is not exhaustive" (vendor extension 허용) |
| "이건 진짜 NWDAF인가?" | 상위 계층(데이터 수집, ML 판단)은 표준 구조 준수. 하위 계층은 명시적으로 확장으로 분리. | ETSI ZSM 002 §5.3: cross-domain closed-loop에서 actuation은 domain-specific |
| "기존 NWDAF 연구와 뭐가 다른가?" | 기존 연구는 모두 control plane 내 실행(PFCP, 정책). 본 연구는 인프라 레이어까지 closed-loop 확장. | [F] Waterloo 2025: NWDAF→SMF→UPF (control plane only) |

### 유사 설계 패턴 (Cross-layer Automation 선례)

| 시스템 | 판단 (Analytics) | 실행 (Actuation) | 경계 |
|--------|-----------------|-------------------|------|
| 3GPP NWDAF + SMF | NWDAF AnLF | SMF (PFCP) | 표준 내 |
| O-RAN Near-RT RIC | xApp (ML) | E2 Node (RAN 제어) | O-RAN 표준 내 |
| ETSI ZSM | Cross-domain analytics | Domain-specific actuator | ZSM 002 정의 |
| **본 연구** | **NWDAF AnLF (표준 구조)** | **Infra Actuator (커널 CNI 전환)** | **표준 + 확장** |

### 핵심 참고 문헌

#### [H] ETSI GS ZSM 002 — Zero-touch Network and Service Management; Reference Architecture
- **출처**: ETSI ISG ZSM, v1.1.1, 2019
- **URL**: https://www.etsi.org/deliver/etsi_gs/ZSM/001_099/002/
- **핵심 내용**:
  - Closed-loop automation: Data Collection → Analytics → Decision → Execution
  - Cross-domain management: 한 도메인의 analytics가 다른 도메인의 actuation을 trigger
  - Management Domain 간 경계에서 intent 기반 인터페이스 사용
- **본 연구와의 관계**: NWDAF(5G domain) analytics → Infrastructure domain actuation은 ZSM의 cross-domain automation 패턴에 부합

#### [I] O-RAN.WG2.AIML-v01.03 — AI/ML Workflow Description and Requirements
- **출처**: O-RAN Alliance WG2, 2023
- **URL**: https://www.o-ran.org/specifications
- **핵심 내용**:
  - Near-RT RIC xApp: ML 모델 추론 → E2 인터페이스로 RAN 제어
  - ML model lifecycle: training → deployment → inference → monitoring
  - Action은 RIC이 아닌 E2 Node가 수행 (판단과 실행 분리)
- **본 연구와의 관계**: "판단은 analytics NF, 실행은 domain actuator" 패턴의 선례

#### [J] 3GPP TS 23.288 §6.2.1 — Analytics ID 확장성
- **출처**: 3GPP Release 19, 2024
- **핵심 내용**:
  - 표준 Analytics ID 목록은 normative하나 exhaustive하지 않음
  - Operator/vendor가 추가 analytics를 정의할 수 있음 (TS 29.520 Nnwdaf API 확장)
  - 단, 표준 inter-op을 위해서는 3GPP에 등록 필요 (본 연구는 단일 operator 범위)
- **본 연구에서의 활용**: "CNI Optimization"을 operator-defined analytics로 위치시킴

### 논문 서술 예시

> "본 연구의 시스템 아키텍처는 두 계층으로 명시적으로 분리된다.
> **Analytics Layer**는 3GPP TS 23.288의 NWDAF AnLF 구조를 따르며, OAM 경로로 수집된
> Network Performance KPI(throughput, packet loss, PPS)와 NF Load(CPU, memory)를
> 입력으로 Random Forest 분류 모델이 최적 CNI backend를 판단한다.
> 이 계층의 데이터 수집, ML 추론 구조, analytics output 형식은 표준 아키텍처의 범위 내에 있다.
>
> **Actuation Layer**는 본 연구가 제안하는 확장으로, AnLF의 analytics output을 수신하여
> 커널 수준의 네트워크 인터페이스 전환을 실행한다. 이는 3GPP가 규정하지 않는(unspecified)
> 영역이며, ETSI ZSM의 cross-domain closed-loop automation [H]과 O-RAN Near-RT RIC의
> xApp→E2 Node 패턴 [I]에서 공통적으로 나타나는 '판단-실행 분리(decision-actuation separation)'
> 설계 원칙에 기반한다.
>
> 두 계층의 명시적 분리는 다음을 의미한다:
> (1) Analytics Layer는 표준 NWDAF 구현에 그대로 적용 가능하며,
> (2) Actuation Layer는 operator의 인프라 환경에 따라 독립적으로 교체/확장 가능하고,
> (3) 본 연구의 contribution은 '이 cross-layer closed-loop이 실제로 UPF 성능 향상에
> 유효한가'를 실험적으로 검증하는 것이다."

### OCI 환경 특이사항 (실험 노트)

본 실험 환경(OCI VM.Standard.A1.Flex)에서 확인된 제약:
- **macvlan**: OCI VCN이 등록되지 않은 MAC 주소 패킷을 드롭 → Pod 간 외부 통신 불가
- **ipvlan**: gtp5g 커널 모듈이 ipvlan 인터페이스 위에서 GTP netlink 디바이스 생성 불가
- **해결**: OVS/Linux bridge를 중간에 두어 macvlan과 ipvlan 모두 bridge 위에 생성
  → bridge의 MAC은 OCI에 등록된 VNIC MAC과 동일하게 설정하여 VCN 통과
  → gtp5g는 macvlan(bridge 위) 인터페이스에 바인딩, IP 이동으로 ipvlan 경유 전환

---

## [B9] NWDAF 표준 전환 대상 vs 본 연구 전환 대상 (Switching Target Comparison)

### 핵심 질문

> "3GPP NWDAF가 원래 전환(switching)하려는 대상은 무엇이고, 본 연구는 무엇을 전환하는가?"

### 3GPP NWDAF의 표준 전환 대상 (Control Plane Level)

NWDAF analytics를 소비하는 NF(SMF, PCF, AMF)가 실행하는 전환:

| 전환 대상 | 실행 주체 | 메커니즘 | 계층 |
|-----------|-----------|----------|------|
| **UPF 재선택** | SMF | PFCP Session Establishment/Release | Control Plane |
| **슬라이스 재선택** | AMF + NSSF | UE Configuration Update | Control Plane |
| **QoS Flow 변경** | SMF + PCF | PCC Rule Update → PFCP QER | Control Plane |
| **PDU Session 경로 변경** | SMF | PFCP Session Modification (UP Path Switch) | Control Plane |
| **UE handover** | AMF | N2 Handover → GTP-U tunnel 재설정 | Control Plane |
| **트래픽 steering** | PCF | PCC Rule (traffic influence) | Control Plane |

**공통점**: 모두 **논리적 경로**의 전환이다. 물리 인프라는 변하지 않는다.

### 본 연구의 전환 대상 (Infrastructure Level)

| 전환 대상 | 실행 주체 | 메커니즘 | 계층 |
|-----------|-----------|----------|------|
| **CNI backend (macvlan ↔ ipvlan)** | Infrastructure Actuator | `ip -batch` (커널 IP 이동) | **Data Plane / Infrastructure** |

### 차이의 본질

```
3GPP 표준 NWDAF:
  "어떤 UPF를 쓸까?" / "어떤 슬라이스로 보낼까?" / "QoS를 얼마로 할까?"
  → GTP 터널 endpoint, 정책 파라미터가 바뀜
  → 패킷이 다른 논리적 경로로 흐름
  → 물리 NIC, 커널 인터페이스는 그대로

본 연구:
  "같은 UPF에서, 같은 IP로, 패킷을 커널의 어떤 경로로 처리할까?"
  → macvlan 경로: NIC → MAC 분기 → container (하드웨어 레벨 분리)
  → ipvlan 경로: NIC → 커널 내부 IP 라우팅 → container (소프트웨어 레벨 분리)
  → 논리적 세션(GTP-U, PFCP)은 불변
  → 커널 패킷 처리 경로만 변경
```

### 계층 비교 (OSI 관점)

```
┌─────────────────────────────────────────────────┐
│ Layer 7   Application (UPF process, GTP-U)      │  ← 양쪽 모두 불변
├─────────────────────────────────────────────────┤
│ Layer 4   Transport (UDP:2152 GTP-U)            │  ← 양쪽 모두 불변
├─────────────────────────────────────────────────┤
│ Layer 3   Network (IP: 10.10.3.1)              │  ← 양쪽 모두 불변
├─────────────────────────────────────────────────┤
│ Layer 2.5 Virtual NIC Driver                    │  ← ★ 본 연구가 전환하는 지점
│           (macvlan: MAC-based / ipvlan: IP-based)│
├─────────────────────────────────────────────────┤
│ Layer 2   Data Link (Physical NIC)              │  ← 양쪽 모두 불변
├─────────────────────────────────────────────────┤
│ Layer 1   Physical                              │  ← 양쪽 모두 불변
└─────────────────────────────────────────────────┘

3GPP NWDAF 전환: Layer 3~4 (터널 endpoint IP, QoS marking)
본 연구 전환:     Layer 2.5 (가상 NIC 드라이버의 패킷 분배 로직)
```

### 왜 이 차이가 중요한가 (연구 동기)

| | 3GPP 표준 전환 | 본 연구 전환 |
|---|---|---|
| **전환 비용** | 높음 (PFCP 세션 재수립, 수백ms~수초) | 낮음 (~μs, IP 이동만) |
| **세션 연속성** | 끊김 가능 (UPF 변경 시) | 유지 (IP, socket 불변) |
| **전환 빈도** | 드묾 (분~시간 단위) | 잦음 가능 (초~분 단위) |
| **전환 granularity** | 세션/UE 단위 | UPF 전체 (모든 세션 일괄) |
| **성능 영향 요인** | 다른 UPF의 스펙, 위치, 부하 | 같은 UPF 내 커널 경로 효율 |

**3GPP의 gap**: 표준은 "어떤 UPF를 쓸지"는 최적화하지만, "그 UPF 내부에서 패킷을 어떻게 처리할지"는 최적화하지 않는다. 본 연구는 이 **intra-UPF 최적화** gap을 채운다.

### 상호 보완 관계 (경쟁이 아닌 보완)

```
Inter-UPF 최적화 (3GPP 표준):
  NWDAF → "UPF-A보다 UPF-B가 낫다" → SMF가 세션 이동

Intra-UPF 최적화 (본 연구):
  NWDAF → "현재 트래픽에 macvlan이 낫다" → Actuator가 커널 경로 전환

두 최적화는 직교(orthogonal):
  - Inter-UPF: 어떤 노드에서 처리할지 (macro decision)
  - Intra-UPF: 그 노드 안에서 어떻게 처리할지 (micro decision)
  - 동시 적용 가능, 충돌 없음
```

### 논문에서의 서술 예시

> "3GPP NWDAF의 기존 analytics 활용은 inter-UPF 최적화에 집중한다: SMF가 NWDAF의
> Network Performance analytics를 소비하여 최적의 UPF를 선택하거나(TS 23.501 §6.3.3),
> PDU Session의 UP 경로를 변경한다(TS 23.502 §4.3.5). 이는 control plane 수준의
> 논리적 경로 전환으로, GTP-U 터널 endpoint과 PFCP 세션의 재수립을 수반한다.
>
> 본 연구는 이와 직교하는 **intra-UPF 최적화**를 제안한다. 동일 UPF 내에서
> 커널의 패킷 처리 경로(macvlan vs ipvlan)를 트래픽 특성에 따라 동적으로 전환하며,
> 이는 GTP-U/PFCP 세션을 유지한 채 data plane 수준에서 수행된다.
> 전환 대상이 Layer 2.5(가상 NIC 드라이버)로 한정되므로, 상위 계층의 세션 상태에
> 영향을 주지 않으며, 전환 비용은 기존 inter-UPF 전환(수백ms~수초) 대비
> 3자릿수 이상 낮다(~μs).
>
> 이 두 최적화 차원은 상호 보완적이다: 3GPP 표준의 inter-UPF 최적화가
> '어떤 노드에서 처리할지'를 결정한다면, 본 연구의 intra-UPF 최적화는
> '그 노드 안에서 어떻게 처리할지'를 결정한다. 양자는 동시에 적용 가능하며
> 충돌하지 않는다."

### 참고 문헌 (추가)

#### [K] 3GPP TS 23.501 §6.3.3 — UPF Selection and Reselection
- **출처**: 3GPP Release 18, 2024
- **내용**: SMF의 UPF 선택 기준 (위치, 부하, 능력, DNN/슬라이스 지원)
- **본 연구와의 관계**: 표준의 inter-UPF 선택과 본 연구의 intra-UPF 최적화가 다른 계층임을 명시

#### [L] 3GPP TS 23.502 §4.3.5 — UP Path Management
- **출처**: 3GPP Release 18, 2024
- **내용**: PDU Session의 User Plane 경로 변경 절차 (UP Path Switch, N9 forwarding)
- **본 연구와의 관계**: 표준 UP 경로 전환은 터널/세션 수준, 본 연구는 커널 드라이버 수준

#### [M] 3GPP TS 29.520 — Nnwdaf Services
- **출처**: 3GPP Release 18, 2024
- **내용**: NWDAF가 제공하는 analytics 서비스 API 정의
- Analytics subscription/notification 절차
- Analytics output의 소비자(SMF, PCF, AMF)별 활용 방식 정의
- **본 연구와의 관계**: 표준 소비자는 control plane NF, 본 연구는 infrastructure actuator를 소비자로 확장

---

## [B10] Inter-UPF 선택에서 Intra-UPF 최적화로의 확장 근거 (Bridging References)

### 핵심 논리

> "어떤 UPF를 쓸지" 문제가 "그 UPF 안에서 패킷을 어떻게 처리할지" 문제로
> 자연스럽게 확장될 수 있음을 보이는 선행연구 chain.

### 논리 체인 (Gap 도출)

```
Step 1: UPF 선택이 성능에 영향을 준다 (Inter-UPF)
  → [N] Dynamic UPF Selection, [O] Joint UPF Placement
  → "어떤 UPF를 쓰느냐에 따라 latency, throughput이 달라진다"

Step 2: 같은 UPF라도 내부 구현에 따라 성능이 크게 다르다 (Implementation)
  → [P] Evaluation of UPF Implementations (INFOCOM 2024)
  → [Q] s5uishida benchmark
  → "go-upf vs VPP-UPF vs eUPF: 같은 기능인데 5배 성능 차이"

Step 3: UPF 내부 패킷 처리 경로를 런타임에 바꿀 수 있다 (Intra-UPF path switching)
  → [R] Run-Time Adaptive BPF/XDP for 5G UPF
  → [S] HiP4-UPF (USENIX ATC'24)
  → [T] Fastlane (IIT Bombay 2024)
  → "같은 UPF 내에서도 처리 경로를 동적으로 전환 가능"

Step 4: 그런데 이 전환을 트래픽 특성에 따라 자동으로 판단하는 시스템은 없다
  → ★ 본 연구의 Gap
  → "Step 1~3은 각각 존재하지만, NWDAF analytics로 Step 3을 자동화한 연구는 없다"
```

### 참고 문헌

#### [N] Dynamic Energy-Efficient User Plane Function Selection in 5G Networks
- **저자**: Bellin et al.
- **출처**: IFIP Networking 2025
- **URL**: https://networking.ifip.org/2025/images/Net25_papers/1571142002.pdf
- **핵심 내용**:
  - UPF 선택을 동적으로 수행하여 에너지 효율 최적화
  - 선택 기준: real-time power consumption + latency/bandwidth requirements
  - **시사점**: "어떤 UPF를 쓸지"를 동적으로 결정하는 연구는 활발하다.
    그러나 "선택된 UPF 내부에서 어떻게 처리할지"는 고정으로 가정.
- **본 연구와의 관계**: inter-UPF 최적화의 선행연구. 본 연구는 이를 intra-UPF로 확장.

#### [O] Dynamic Selection of User Plane Function in 5G Environments
- **저자**: [ONDM 2021]
- **출처**: IFIP/IEEE ONDM 2021
- **URL**: https://dl.ifip.org/db/conf/ondm/ondm2021/1570718826.pdf
- **핵심 내용**:
  - Evolutionary Game Theory 기반 UPF 선택 모델
  - 서비스 지연 최소화를 위한 동적 UPF 할당
  - **시사점**: UPF "선택"은 최적화 대상으로 인정되지만,
    선택된 UPF의 내부 처리 메커니즘은 다루지 않음.

#### [P] Evaluation of User Plane Function Implementations in Real-World 5G Networks
- **저자**: Sokratis Christakis, Theodoros Tsourdinis, Nikos Makris, Thanasis Korakis, Serge Fdida
- **출처**: IEEE INFOCOM 2024 Workshops
- **URL**: https://www.researchgate.net/publication/383111414
- **핵심 내용**:
  - 실제 5G 환경에서 다양한 UPF 구현(kernel-based, DPDK, XDP) 성능 비교
  - 같은 UPF 기능이라도 내부 구현 방식에 따라 throughput/latency가 크게 상이
  - **시사점**: UPF 내부 패킷 처리 경로가 성능의 결정적 요인임을 실증.
    "어떤 UPF를 쓸지"뿐 아니라 "어떤 처리 경로를 쓸지"가 중요함의 근거.
- **본 연구와의 관계**: 처리 경로(macvlan vs ipvlan)에 따른 성능 차이가 최적화 가치가 있음의 직접 근거.

#### [Q] Simple Measurement of UPF Performance (s5uishida)
- **이미 [2]에서 인용** — go-upf(233Mbps) vs UPG-VPP(1.14Gbps) vs eUPF(359Mbps)
- **시사점**: 같은 PFCP를 처리하는 UPF라도 데이터플레인 구현에 따라 5배 차이.
  이는 내부 처리 경로 최적화의 가치를 직접 보여줌.

#### [R] Run-Time Adaptive In-Kernel BPF/XDP Solution for 5G UPF
- **저자**: Navarro do Amaral, T.A.; Rosa, R.V.; Moura, D.F.C.; Esteve Rothenberg, C.
- **출처**: MDPI Electronics 2022, 11(7), 1022
- **URL**: https://www.mdpi.com/2079-9292/11/7/1022
- **핵심 내용**:
  - UPF 내부에서 BPF 프로그램을 **런타임에** 교체하여 패킷 처리 로직 변경
  - JIT 컴파일 오버헤드를 95% 감소시키는 설계로 빠른 적응(adaptation) 달성
  - 10-11 Mpps 성능 유지하면서 런타임 경로 변경 가능
  - **시사점**: UPF 내부 패킷 처리 경로의 **런타임 전환**이 기술적으로 가능함을 실증.
    단, 이 논문은 "언제 전환할지"의 판단 로직(analytics)은 다루지 않음.
- **본 연구와의 관계**: [R]은 "전환 가능성"을 보여주고, 본 연구는 "전환 판단 자동화"를 추가.
  [R]의 actuation 기술 + 본 연구의 NWDAF analytics = 완전한 closed-loop.

#### [S] HiP4-UPF: Towards High-Performance Comprehensive 5G User Plane Function on P4 Programmable Switches
- **저자**: Wen et al.
- **출처**: USENIX Annual Technical Conference (ATC'24), July 2024
- **URL**: https://www.usenix.org/biblio-14562
- **핵심 내용**:
  - P4 프로그래머블 스위치에서 UPF 전체 기능 구현
  - 기존 open-source UPF 대비 9-619% throughput 향상
  - 패킷 처리 경로를 하드웨어 수준에서 최적화
  - **시사점**: UPF 성능은 "어떤 하드웨어/소프트웨어 경로로 패킷을 처리하느냐"에
    결정적으로 의존함을 Top-tier 학회에서 입증.
    단, 이 논문도 "정적 배포" — 런타임 적응 전환은 다루지 않음.
- **본 연구와의 관계**: 처리 경로 차이의 성능 영향이 수백% 수준임을 보여주는 상한 참조.

#### [T] Fastlane: Porting Network Applications to Fast Packet I/O Frameworks
- **저자**: IIT Bombay (Mythili Vutukuru 그룹)
- **출처**: 2024
- **URL**: https://www.cse.iitb.ac.in/~mythili/research/papers/2024-fastlane.pdf
- **핵심 내용**:
  - 네트워크 애플리케이션의 "fast path"와 "slow path"를 분리
  - Fast path: DPDK/XDP 등 고속 I/O 경로
  - Slow path: 전통적 커널 네트워크 스택
  - 두 경로 간 **런타임 전환** 프레임워크 제공
  - **시사점**: "같은 애플리케이션이 두 가지 패킷 처리 경로를 가지고,
    상황에 따라 전환한다"는 개념의 일반화된 선행연구.
- **본 연구와의 관계**: Fastlane의 "fast/slow path 전환" 개념을
  5G UPF의 "macvlan/ipvlan 전환"으로 특수화. Fastlane은 범용 프레임워크,
  본 연구는 5G-specific 적용 + NWDAF 기반 판단 자동화.

### Gap Statement (논문에서의 활용)

> "선행연구는 (1) 동적 UPF 선택(inter-UPF)[N][O], (2) UPF 구현 방식에 따른 성능 차이[P][Q][S],
> (3) UPF 내부 패킷 처리 경로의 런타임 전환 가능성[R][T]을 각각 입증하였다.
> 그러나 이 세 가지를 연결하여 — 트래픽 특성을 실시간 관측하고, 최적 처리 경로를
> 자동으로 판단하며, 무중단으로 전환하는 — end-to-end closed-loop 시스템을
> 구현한 연구는 존재하지 않는다.
>
> 특히, inter-UPF 선택[N][O]이 '어떤 노드를 쓸지'를 최적화한다면,
> 본 연구는 그 다음 단계인 '선택된 노드 내부에서 어떤 커널 경로로 처리할지'를
> 최적화하는 **intra-UPF 최적화**를 제안한다. 이는 inter-UPF 선택과 직교하며,
> 기존 시스템에 추가적으로 적용하여 성능을 더 향상시킬 수 있다."

### 시각적 정리: 선행연구 → 본 연구의 위치

```
┌─────────────────────────────────────────────────────────────────┐
│                     선행연구 landscape                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [N][O] Inter-UPF Selection        [P][Q][S] UPF Impl. Comparison│
│  "어떤 UPF?"                       "어떤 구현이 빠른가?"         │
│       │                                  │                      │
│       │                                  │                      │
│       ▼                                  ▼                      │
│  ┌─────────────────────────────────────────────┐               │
│  │ [R][T] Runtime Path Switching 가능           │               │
│  │ "패킷 처리 경로를 런타임에 바꿀 수 있다"      │               │
│  └────────────────────┬────────────────────────┘               │
│                       │                                         │
│                       │ ← 판단 자동화 부재 (Gap)                 │
│                       ▼                                         │
├─────────────────────────────────────────────────────────────────┤
│  ★ 본 연구                                                      │
│  NWDAF Analytics + Intra-UPF Path Switching                     │
│  "언제, 어떤 경로로 전환할지를 자동 판단 + 무중단 실행"           │
└─────────────────────────────────────────────────────────────────┘
```

---

## [B11] 네트워크 인터페이스 계층 구조 — enp0s6과 커널의 관계

### 계층 구조

```
[유저스페이스]  UPF 프로세스 (go-upf) — bind("10.10.3.1")
───────────────────────────────────────────────────────
[커널]         socket
                 ↓
              ipvlan/macvlan (가상 인터페이스 드라이버)
                 ↓
              bridge (n3br / n3br-ipv)
                 ↓
              enp0s6 (NIC 디바이스 오브젝트 — 커널이 하드웨어를 추상화)
───────────────────────────────────────────────────────
[하드웨어]    물리 NIC 칩 (PCIe bus 0, slot 6)
```

### enp0s6의 정체

- **커널과 물리 NIC 하드웨어 간의 인터페이스** (추상화 계층)
- 커널의 NIC 드라이버가 하드웨어 초기화 시 등록하는 네트워크 디바이스 오브젝트
- 이름 규칙: `en`(ethernet) + `p0`(PCI bus 0) + `s6`(slot 6) — Predictable Network Interface Names (systemd)
- ipvlan/macvlan은 이 디바이스를 `master`로 참조하여 커널 내부에 가상 인터페이스를 생성

### 본 프로젝트에서의 역할

```json
// NetworkAttachmentDefinition
{ "master": "enp0s6" }
```

"enp0s6의 커널 드라이버 위에 ipvlan/macvlan 서브인터페이스를 생성하겠다"는 선언.

### `ip addr del/add`의 동작 레벨

- 파일 수정이 아님 — 커널 메모리의 네트워크 자료구조를 직접 변경
- 경로: `ip 명령 → netlink 소켓 → 커널 네트워크 서브시스템 → 라우팅/인터페이스 상태 변경`
- 재부팅 시 사라짐 (비영속), 적용 즉각적 (마이크로초 단위)

### `ip addr` vs `iptables` 차이

| | `ip addr` | `iptables` |
|--|-----------|-----------|
| 역할 | 인터페이스에 IP 주소 할당 | 패킷 필터링/NAT |
| 레이어 | L2/L3 경계 (어디서 수신할지) | L3/L4 (허용/차단/변환) |
| 동작 시점 | 패킷 도착 전 — 수신 인터페이스 결정 | 패킷 도착 후 — 처리 규칙 적용 |

본 프로젝트의 전환은 `ip addr`로 수행하며, iptables는 관여하지 않음.

### 참고 문서

- [Linux Kernel Networking — Network Device Naming](https://www.freedesktop.org/wiki/Software/systemd/PredictableNetworkInterfaceNames/) — systemd의 예측 가능한 인터페이스 이름 규칙
- [Linux Kernel Documentation: netdevices](https://www.kernel.org/doc/html/latest/networking/netdevices.html) — 커널 네트워크 디바이스 구조
- [iproute2 / netlink](https://man7.org/linux/man-pages/man7/netlink.7.html) — ip 명령이 커널과 통신하는 메커니즘
- [IPVLAN — The Beginning (netdev 0.1, Bandewar/Google, 2015)](http://people.netfilter.org/pablo/netdev0.1/papers/IPVLAN-The-beginning.pdf) — ipvlan이 master 인터페이스를 참조하는 구조 설명
