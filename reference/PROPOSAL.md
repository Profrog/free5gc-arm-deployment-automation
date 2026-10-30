# 연구 계획서

## Title

"NWDAF-Inspired Reinforcement Learning for Cost-Aware CNI Backend Switching in Cloud-Native 5G UPF on ARM"

(NWDAF 분석 기반 폐루프 제어 패턴을 차용한, Cloud-Native 5G UPF의 비용 인지형 CNI 백엔드 전환 — 강화학습 접근)

---

## 연구 질문

> **SR-IOV·DPDK 등 하드웨어 가속 데이터패스를 쓸 수 없는 자원 제약 가상화 엣지 노드**에서, 강화학습(RL) 에이전트가 트래픽 패턴을 관측하여 **Pod 재생성 비용(downtime)을 감수해도 누적 이득이 더 큰 경량 CNI 전환 시점**을 — 고정 CNI 및 Rule-based 정책보다 — 효율적으로 찾을 수 있는가?

핵심은 "어떤 모델이 더 좋은가"가 아니라 **"모델이 비용 대비 이득이 되는 전환 시점을 찾는가"**이다. 따라서 비교 대상은 다른 ML 모델이 아니라, 현업의 일반적 관행인 **고정 CNI와 Rule-based(threshold) 정책**이다.

### 대표 도메인 & 환경 전제 (scope 한정)

**대표 적용 도메인 — 스마트팩토리 온프레미스 Private 5G의 머신비전.**
본 연구는 추상적 "제약 엣지"가 아니라, 현실에 널리 존재하는 구체 도메인 하나를
대표 시나리오로 삼는다: **공장 현장의 온프레미스 private 5G**. 이 도메인은 본 연구의
scope 조건을 자연스럽게 충족한다.
- **자원제약·단일 노드**: 공장 private 5G core는 비용 효율을 위해 서버룸/스마트랙 내
  소수(2~3대, 종종 단일)의 범용 COTS 서버에 통합 배치된다. 데이터센터급이 아니며
  SR-IOV/DPDK·증설이 비용·운영상 비현실적이다(5G-ACIA; EnterpriseViewpoint; ASTRI).
- **elephant flow 존재**: 머신비전 카메라가 생성하는 4K/8K 영상의 **지속적 대용량
  업링크**는 전형적 elephant flow다(5G-ACIA; Nokia).
- **트래픽 교차(핵심)**: 한 공장 단말/UPF가 제어 트래픽(소패킷·URLLC)과 머신비전
  영상(대패킷·eMBB)을 **동시에 처리하며, 공정 상황에 따라 그 성격이 교차**한다
  (Seliem et al., MSWiM 2025). → 고정 CNI는 한쪽에 항상 불리하므로, 트래픽 특성에
  맞춘 전환 이득이 발생한다. 본 연구의 트래픽 시나리오(T1~T5)는 이 공정 변화의 추상화다.

**환경 전제(본 testbed 실측).** 위 도메인의 제약은 본 testbed의 실제 조건으로 재현된다:
- NIC가 `virtio_net`(가상화 NIC) → **SR-IOV VF 미지원**(물리 NIC 부재)
- 4 vCPU 소규모 노드 → **DPDK의 코어 전용 점유(busy-poll)가 비현실적**
- 즉 선택 가능한 데이터패스가 **소프트웨어 CNI(ipvlan/macvlan 등)로 한정**됨

→ 즉 "하드웨어 가속 없이, 경량 CNI 선택만으로 트래픽 변화에 적응"하는 것이 본 연구의
문제이며, 스마트팩토리 머신비전은 이 문제가 **실재하고 중요한** 대표 도메인이다.
(도메인 근거 상세: `REFERENCES.md` [C5].)

---

## Abstract

Cloud-native 5G Core에서 User Plane Function(UPF)의 data plane 성능은 Container Network Interface(CNI) 드라이버에 영향을 받는다. 데이터센터급 환경에서는 SR-IOV·DPDK 등 하드웨어 가속 데이터패스로 이를 해결하지만, **스마트팩토리 온프레미스 private 5G처럼 비용 효율을 위해 소수의 범용 COTS 서버(virtio NIC)에 코어를 통합 배치하는 환경에서는 SR-IOV/DPDK·증설이 비용·운영상 배제되어, 선택지가 소프트웨어 CNI(ipvlan/macvlan)로 한정된다.** 이러한 환경의 UPF는 설비 제어(소패킷)와 머신비전 영상 업링크(대용량 벌크)를 동시에 처리하며 트래픽 성격이 공정에 따라 교차하는데, 고정 CNI는 한쪽에 항상 불리하다. 더욱이 현업에서 CNI는 배포 시점에 고정되고, 런타임 동적 제어가 있더라도 대부분 고정 임계값 기반 Rule에 의존한다. 본 연구는 이러한 **자원 제약 가상화 엣지 환경(ARM64, 4 vCPU, virtio NIC)**의 free5GC UPF에서 ipvlan과 macvlan이 트래픽 특성에 따라 상이한 성능을 보임을 공정 조건에서 실증하고(소패킷: ipvlan 유리, 대패킷: macvlan 유리), 3GPP TS 23.288 NWDAF의 "관측→분석→폐루프 제어" 패턴을 차용한 **강화학습 에이전트**가 Pod 재생성 기반 CNI 전환의 최적 시점을 자동 판단하는 closed-loop 시스템을 설계·구현·검증한다. 전환 비용(downtime 중 패킷 손실)은 전체 세션의 누적 throughput에 자연 포함되며, RL의 보상(reward)을 **total bytes received**로 정의하여 비용-이득이 목적함수에 직접 반영되도록 한다. 실환경에서의 RL 학습은 단일 노드에서 비현실적이므로, 사전 측정한 KPI 기반 **경량 시뮬레이터에서 정책을 학습**하고 실환경에서는 평가만 수행한다. 5가지 트래픽 패턴·120초 실험에서 RL 전환이 고정 CNI 및 Rule-based 대비 Net Gain, False Positive 억제, Reaction Time에서 우위를 보이는지 검증한다.

---

## Contribution

1. **제어 대상의 확장**: 표준 NWDAF가 세션/UPF 레벨의 전환을 데이터 기반으로 판단해온 "관측→분석→폐루프 제어" 패턴을, 기존에 다뤄지지 않던 **데이터플레인 CNI 백엔드 전환**이라는 새로운 제어 대상으로 확장한다. (표준에 CNI 전환이 명시된 것이 아니라, NWDAF 아키텍처 패턴을 차용·확장한 커스텀 AnLF이다.) 가장 가까운 선행연구는 UPF **앱 구현(SPGW-U/VPP)**을 LSTM 예측으로 전환하나[C6-1 Globecom'25], 본 연구는 제어 대상을 **UPF 아래 CNI 데이터패스(ipvlan/macvlan, L2/L3 커널)**로 옮긴다는 점에서 구별된다. 런타임 CNI 변경 **메커니즘**은 존재하나[C6-4 Multus/CNI-Genie], **전환 시점을 판단하는 정책(policy)은 공백**이며 본 연구가 이를 채운다.

2. **비용 인지형 순차적 의사결정의 RL 정식화**: CNI 전환은 "지금 downtime을 치르면 이후 누적 이득이 더 큰가"를 판단하는 순차적 의사결정 문제다. 이를 reward = total bytes received로 정식화하면, 전환 비용·판단 오류·타이밍이 **단일 목적함수에 자연 반영**되어, 별도 라벨링 없이 비용-이득 최적 정책을 학습할 수 있다. 분류 정확도(accuracy)가 아닌 **결정의 실효적 이득**으로 평가하는 프레임워크를 제안한다.

3. **자원 제약 엣지에 특화된 학습·배포 전략**: SR-IOV/DPDK를 쓸 수 없고 스케일아웃도 제한된 가상화 엣지(virtio NIC, 4 vCPU)에서, 경량 CNI 전환이 사실상 유일한 적응 수단임을 실증한다. 아울러 실환경 RL 학습의 비용(시간) 문제를 선행연구(RL-HPA 시뮬/전이학습)와 동일하게 **시뮬레이터 학습 + 실환경 평가**로 해결, GPU·다중 노드 없이 ARM64 단일 노드에서 전 과정을 수행한다.

---

## 문제 정의 & 동기 (실제 사례 기반)

### 환경 제약 (본 testbed 실측 — 경쟁 해법이 배제되는 근거)
본 연구의 타당성은 "왜 스케일아웃이나 고성능 데이터패스가 아니라 CNI 전환인가"에
달려 있다. 본 testbed의 실제 조건이 경쟁 해법들을 환경적으로 배제한다:

| 경쟁 해법 | 본 환경에서 가용성 | 근거 |
|-----------|------------------|------|
| **SR-IOV 고정** | ❌ 불가 | NIC가 `virtio_net` 가상 NIC, `sriov_totalvfs` 부재(VF 미지원) |
| **DPDK 고정** | ❌ 비현실적 | 4 vCPU 중 코어 전용 점유(busy-poll) 부담 과대, virtio-PMD 이점 미미, hugepage 미설정 |
| **스케일아웃(증설)** | ❌ 제한 | 단일 노드·고정 자원, Pod 추가 여력 없음 (엣지 제약) |
| **QoS/슬라이스 분리** | △ 보완적 | 세션 경로 분리는 가능하나, 각 UPF 내부 데이터패스 성능 문제는 그대로 남음 |
| **경량 CNI 동적 전환(본 연구)** | ✅ 유일하게 가능 | 소프트웨어 CNI(ipvlan/macvlan)만이 선택지 |

→ 즉 **"하드웨어 가속도 증설도 불가능한 범용 가상화 엣지"**에서는, 있는 자원으로
데이터패스를 트래픽에 맞춰 바꾸는 것이 **현실적으로 유일한 적응 수단**이다. 이 환경
한정이 reject 사유("그냥 SR-IOV/스케일아웃 쓰면 되잖아")를 원천 차단한다.
이 제약은 인위적이지 않다: 스마트팩토리 온프레미스 private 5G는 비용 효율을 위해
소수 COTS 서버에 코어를 통합 배치하는 것이 산업 표준이며(5G-ACIA; ASTRI;
EnterpriseViewpoint), 거기서 SR-IOV/DPDK·증설은 가용 여부가 아니라 **비용·운영상**
배제된다.

### 현업의 일반론과 그 한계
- **CNI는 사실상 고정**이다. Multus 등으로 배포 시 하나를 정하면 운영 내내 바꾸지 않는다. 런타임 전환이 Pod/NAD 재생성(downtime)을 요구하기 때문이다.
- **동적 제어는 대부분 Rule-based**다. Kubernetes HPA의 기본은 "CPU N% 초과 시 스케일" 같은 고정 임계값이며, 5G 자동화도 정책 규칙 기반이 지배적이다.

### 본 연구가 도움이 되는 지점 (대표 도메인: 스마트팩토리 머신비전)
구체 시나리오로 **공장 현장의 머신비전 영상 검사**를 상정한다. 한 산업용 UE/UPF가
다음을 동시에 처리한다(Seliem et al., MSWiM 2025의 "edge-hosted machine vision +
real-time control loops + bulk data transfer"):
1. **트래픽 특성의 교차**: 설비 제어·상태 보고(소패킷)와 머신비전 영상 업링크(대용량
   벌크)가 공정 상황에 따라 번갈아 지배한다. 고정 CNI는 한쪽에 항상 불리하다. →
   특성 변화 구간에서 전환 이득 발생.
2. **대용량·장기 벌크(eMBB, 영상 업링크)**: 4K/8K 검사 영상은 **플로우가 길고
   큼(elephant flow)**(5G-ACIA; Nokia). 전환 downtime을 치러도 이후 누적 throughput
   이득이 비용을 상회한다. 손실률(%) 차이는 작아 보여도 **장기 세션의 누적
   goodput(절대량)** 차이로 환산하면 유의미하다. → 본 기법의 주요 적용 대상.
3. **반대로, 적용하지 않아야 할 사례**: 공장의 **실시간 제어 루프(URLLC)**처럼 순간
   단절이 치명적이거나, 짧게 끝나는 mice flow. 전환 비용을 회수할 시간이 없어 HOLD가
   정답. → 본 연구 scope에서 제외하며, 이를 모델이 스스로 억제(HOLD)하는지 T3/T5로 검증.

### 미래 불확실성 (RL이 정당한 이유)
트래픽이 변하는 그 순간에는 "이 변화가 지속될지(SWITCH 정답) 잠깐 튀는 것인지(HOLD 정답)"가 보이지 않는다. 단순 Rule(임계값 초과 시 즉시 전환)은 T3(spike)·T5(oscillation)에서 속아 불필요한 전환(false positive)으로 downtime을 낭비한다. **미래 불확실성 하에서 과거 패턴으로 지속 가능성을 추정해야 하므로**, 단순 규칙이 아닌 학습 기반(RL) 의사결정이 정당화된다.

→ 요약: **"하드웨어 가속·증설이 불가능한 제약 엣지"에서, 트래픽 특성 변화(+그 지속성의 불확실성)에 맞춰 경량 CNI 전환 시점을 데이터 기반으로 판단한다**가 본 연구의 공백(gap)이자 기여다.

---

## NWDAF 표준과의 연관성 (포지셔닝)

- **표준 NWDAF (3GPP TS 23.288)**: AnLF(Analytics)/MTLF(Model Training)로 구성, network/NF load·UE mobility·QoS sustainability 등 analytics를 제공하고, 이를 세션 관리·UPF 선택/재배치(TS 23.502 절차) 등 **세션/UPF 레벨 최적화**에 활용한다. 표준상 NWDAF는 analytics를 **produce**하고, consumer NF(SMF/PCF/OAM 등)가 이를 받아 **집행(enforce)**한다.
- **본 연구의 위치 (독립적 기여 + 표준화 제언)**: 본 연구의 1차 기여는 "자원제약 엣지에서 트래픽 특성 기반 CNI 전환이 효과적"임을 **독립적으로 실증**하는 것이며, 특정 표준 NF에 의존하지 않는다. 다만 이를 3GPP 생태계로 통합할 경우를 고려하면, 5G Core에서 데이터 기반 AI 분석을 수행하는 표준 NF가 NWDAF가 유일하므로, 전환 **판단** 지능을 NWDAF의 **커스텀 AnLF**로 편입하는 것이 자연스럽다. 상세는 Discussion의 Standardization Pathway 참조.
- **판단/집행 분리 (표준 구조 준수)**: 본 시스템의 closed-loop은 표준의 producer/consumer 분리에 대응하여 **판단부(AnLF 역할: RL이 SWITCH/HOLD 결정)**와 **집행부(consumer 역할: CNI 전환 실행)**로 논리적으로 분리된다. 따라서 "NWDAF가 직접 전환을 집행한다"는 표준 오용이 아니다.
- **명확한 선 긋기 (제언 톤)**: 표준이 CNI 전환을 규정하지는 않으며, 본 연구는 **표준 NWDAF의 완전 준수 구현을 주장하지 않는다.** 본 시스템은 NWDAF의 폐루프(closed-loop) 패턴을 차용한 **커스텀 제어기**이며, "표준에 통합한다면 NWDAF 구조가 적합하다"는 것은 주장(claim)이 아니라 **제언(suggestion)**이다. 최근 연구 흐름(NWDAF-enabled closed-loop automation)과 궤를 같이한다.

---

## Preliminary Results

공정 조건(호스트 NIC enp1s0에 직접 분기, dual-bridge/veth 미경유)에서 측정:

| 조건 | macvlan | ipvlan | 유리 |
|------|---------|--------|------|
| 소패킷 64B (high pps) | loss 2.64% | loss 2.42% | ipvlan |
| 대패킷 1400B (500Mbps) | loss 0.16% | loss 0.33% | macvlan |

→ 트래픽 특성에 따라 최적 CNI가 상이함을 실증 → 동적 전환의 당위성 확보

---

## 현재 진행 상태

- ARM64 K8s 클러스터 + free5GC 전체 NF 배포 완료 (동작 중)
- NWDAF 엔진(관측→분석→전환 실행) closed-loop 파이프라인 구현 완료
- 트래픽 생성기 및 모니터링 시스템 구축 완료
- Baseline 측정 데이터 확보 (ipvlan/macvlan 공정 비교, pps별 throughput/loss)
- 전환 downtime 측정 데이터 확보 (switch 실험)
- **남은 작업**: ① 측정 데이터 기반 경량 시뮬레이터 구현 → ② 시뮬에서 RL 정책 학습 → ③ 실환경에서 Rule-based vs RL 평가 → ④ 분석/writing

---

## 시스템 설계

### 아키텍처
- free5GC + NWDAF(커스텀 AnLF) on ARM64 K8s (단일 노드, 4 vCPU, GPU 없음)
- 전환 메커니즘: Pod 재생성(kubectl scale / NAD 교체)
- 폐루프: OAM/KPI 수집 → RL 추론(정책) → 전환 판단(SWITCH/HOLD) → 실행
- 격리: CPU pinning

### 비용-이득 전환 조건 (break-even)
전환을 수행할 가치가 있으려면, 잔여 구간 동안의 처리량 이득이 전환 비용을 넘어야 한다:

```
ΔThroughput × T_remaining  >  C_switch (= downtime 중 손실 bytes)
```

- 좌변: 전환 후 유리한 CNI로 얻는 추가 throughput × 남은 시간
- 우변: Pod 재생성 downtime 동안 받지 못한 bytes (측정값)
- RL은 이 부등식을 명시적으로 계산하지 않고, **reward = 세션 total bytes received**를 최대화함으로써 동일한 판단을 데이터로부터 학습한다.

### RL 정식화
- **State**: 최근 윈도우의 KPI 시계열 (pps, byte rate, 패킷 크기 분포, loss, 현재 CNI)
- **Action**: {HOLD, SWITCH}
- **Reward**: 구간 total bytes received (전환 시 downtime 손실 자동 반영)
- **Algorithm**: 경량 가치기반(DQN류) — 작은 신경망, CPU 추론으로 충분

### 학습 전략 (단일 노드 제약 해결)
- 실환경 1 에피소드 = Pod 재생성 + 120초 트래픽 ≈ 2분+ → 수천 에피소드 학습은 비현실적(수십 시간~수주).
- **해결**: 사전 측정한 (CNI, pps)→(throughput, loss)와 downtime 측정치로 **경량 시뮬레이터(룩업/수식)** 구성 → 시뮬에서 수천 에피소드를 CPU로 고속 학습 → 학습된 정책을 실환경에서 **평가만** 수행.
- 선행연구 근거: RL-HPA의 큐잉 모델 시뮬 학습 및 전이학습 기법(READING_LIST.md C-1).

---

## 논문 구조

```
1. Introduction
   - 동기 도메인: 스마트팩토리 온프레미스 private 5G(소수 COTS 서버, 제어+머신비전 영상 교차)
   - 문제: CNI 고정·Rule-based가 일반론 + 전환 비용(downtime) 존재
   - 공백: 트래픽 특성 기반 CNI 런타임 전환 시점 판단은 드묾
   - 연구 질문 / Contribution

2. Background & Related Work
   - 5GC UPF data plane (TS 23.501)
   - NWDAF 아키텍처와 세션/UPF 전환 (TS 23.288/23.502) → 본 연구의 CNI 전환으로의 확장
   - CNI 성능 비교 (ipvlan vs macvlan), 컨테이너 데이터플레인 성능 [C1,C2]: 정적 비교는 포화 → 전제로 흡수
   - RL 기반 비용-이득 전환(마이그레이션/스케일링) [C3 FIRE, C4, RL-HPA]: 방법론 선례 → CNI 전환으로 대상 이동
   - ★ 가장 가까운 선행연구와의 차별화 [C6]:
     · [C6-1] Globecom'25 UPF Switching(SPGW-U/VPP, LSTM 예측, energy) ↔ 본 연구(CNI L2/L3, RL, downtime)
     · [C6-2] eUPF path selection(DQN/POMDP) ↔ 본 연구(경로가 아니라 데이터패스 전환)
     · [C6-4] Multus/CNI-Genie: 전환 "메커니즘"은 있으나 "시점 판단(policy)"은 공백
   - 스마트팩토리 5G 멀티플로우 [C5]: 트래픽 교차·elephant flow의 도메인 근거
   - elephant/mice flow (scope 근거)

3. System Design
   - 아키텍처: free5GC + NWDAF(커스텀 AnLF) on ARM64 K8s
   - 전환 메커니즘, 비용-이득 break-even
   - RL 정식화 (state/action/reward), 시뮬레이터 학습 전략

4. Experiment Design
   - 공정 조건(호스트 NIC enp1s0에 직접 분기, dual-bridge/veth 미경유), 트래픽 5종 ×120초
   - 전략 4종: A(ipvlan) / B(macvlan) / C(Rule-based) / D(RL)
   - 평가: total bytes received, 5회 반복, 95% CI

5. Evaluation
   - Baseline: ipvlan vs macvlan 공정 비교
   - Sim-to-Real Gap: 시뮬 예측 vs 실측, 시뮬 RL 성능 vs 실환경 RL 성능 (순환논리 방어)
   - D vs A,B: RL 전환이 고정보다 나은가?
   - D vs C: RL이 Rule-based보다 나은가? (핵심 구도)
   - False Positive: T3/T5에서 전환 억제
   - Reaction Time: T1/T2에서 정답 시점 대비 지연

6. Discussion
   - 적용 scope: 자원 제약 가상화 엣지(SR-IOV/DPDK 불가, 스케일아웃 제한) + 장기·대량(eMBB/벌크) 트래픽. 대표 도메인은 스마트팩토리 온프레미스 private 5G의 머신비전 영상 업링크(제어+영상 교차). URLLC(실시간 제어 루프)·mice flow·데이터센터급 환경은 제외.
   - 왜 CNI 전환인가: 경쟁 해법(SR-IOV/DPDK/스케일아웃)이 환경적으로 배제됨을 실측 근거로 제시.
   - ★ Standardization Pathway (제언): 본 기법은 특정 표준 NF에 독립적으로 효과를 실증한다. 다만 3GPP 생태계로 통합한다면, AI 분석을 수행하는 표준 NF가 NWDAF가 유일하므로 전환 판단을 커스텀 AnLF로 편입하고, producer/consumer 분리에 따라 집행을 consumer 측에 두는 구조가 자연스럽다. analytics 대상을 세션/UPF에서 CNI 데이터플레인으로 확장하는 제언이며, 구체적 인터페이스(Nnwdaf 확장) 설계는 향후 과제. (주장 아닌 제언 톤)
   - Limitation: 데이터센터급(SR-IOV 가용) 환경에서는 고성능 고정이 우위일 수 있어 본 기법의 이득이 제한적. 고성능 데이터패스와의 직접 비교는 본 testbed(virtio NIC)에서 불가하여 수행하지 않음(향후 베어메탈 검증 과제). 본 연구는 표준 NWDAF의 완전 준수 구현을 주장하지 않으며, closed-loop 패턴 차용에 한정된다.
   - ARM64 커널 경로 특성, 시뮬-실환경 gap(sim-to-real)

7. Conclusion & Future Work
```

---

## 실험 설계

### 트래픽 패턴 (5종 × 120초)

| # | 패턴 | 트래픽 특성 | 올바른 판단 |
|---|------|-----------|-----------|
| T1 | rapid_ramp | 소→대 급상승 (10s) | SWITCH (즉시) |
| T2 | slow_ramp | 소→대 점진 (120s) | SWITCH (중반) |
| T3 | spike_return | 소→대→소 (일시적) | **HOLD** |
| T4 | step_plateau | 계단식 상승 | SWITCH (정체 후) |
| T5 | oscillation | threshold 근처 진동 | **HOLD** |

### 전략 (4종) — Rule-based vs RL 구도

| 전략 | 설명 | 역할 |
|------|------|------|
| A | ipvlan **고정** (전환 없음) | Baseline (소패킷 최적, 현업 관행) |
| B | macvlan **고정** (전환 없음) | Baseline (대패킷 최적, 현업 관행) |
| C | Rule-based 전환 (고정 임계값 if-문, 예: 평균 패킷크기 > θ 이면 SWITCH) | **비교군** (전환하되 단순 규칙, 현업 동적 제어의 일반론) |
| D | RL 전환 (학습된 정책) | **본 연구의 핵심 제안** |

> **고정(A/B) vs Rule-based(C) 구분**: A/B는 전환 행위 자체가 없는 baseline이다.
> C는 전환을 **하되** 현재값 기반 고정 임계값으로 즉시 반응한다(미래 미고려).
> 따라서 D>A,B는 "전환이 고정보다 낫다"를, **D>C는 "전환하더라도 단순 규칙이
> 아니라 학습이어야 한다"**를 증명한다. 후자가 본 연구의 핵심 승부처이며,
> C는 T3(spike)·T5(oscillation)에서 미래를 못 봐 false positive 전환을 유발한다.

### 평가 기준

```
점수 = 120초간 서버가 받은 total bytes (= RL reward)

성공 기준:
  D > A, D > B   (RL 전환이 고정 CNI보다 나음)
  D > C          (RL이 Rule-based보다 나음)  ← 핵심 구도

추가 메트릭:
  - False Positive Rate: T3, T5에서 불필요 전환 횟수
  - Reaction Time: T1, T2에서 정답 시점 대비 지연(초)
```

---

## 실험 파이프라인 (학습·검증 흐름)

RL만 "시뮬 학습 → 실환경 적용"을 거치며, 평가(비교)는 **모든 전략을 실환경에서
동일 조건**으로 수행한다.

```
[1] 시뮬 환경 구축
    · baseline/switch 측정 데이터로 (CNI, pps, 패킷크기)→(throughput, loss)
      + 전환 downtime 매핑. Gym 인터페이스 권장.
        ↓
[2] 시뮬에서 RL 학습 → 정책(가중치) 산출
    · reward = 구간 total bytes received. CPU만으로 수천 에피소드.
        ↓
[3] 학습된 정책을 실환경(free5GC UPF)에 배포 (가중치 고정, 추론만)
        ↓
[3.5] ★ Sim-to-Real Gap 검증 (순환논리 방어의 핵심) ★
    (a) 시뮬 예측 KPI vs 실측 KPI 오차 (동일 입력)
    (b) 시뮬에서의 RL 성능 vs 실환경에서 동일 정책의 성능
    → "시뮬이 현실을 반영 + 정책이 처음 보는 실환경에 일반화됨" 증명
       (gap이 있어도 전략 간 순위가 보존되면 결론은 유효)
        ↓
[4] 실환경에서 A / B / C(Rule) / D(RL) 전부 동일 트래픽·반복으로 비교
    · 학습이 필요 없는 A/B/C는 시뮬 없이 바로 실환경 측정
    · total bytes 및 FP/Reaction Time 비교
```

### Sim-to-Real Gap 검증 (상세)
- **목적**: "시뮬에서 배운 RL이 실제에서도 유효한가"를 데이터로 증명 → 리뷰어의
  순환논리(circular) 공격 방어. RL은 시뮬에서만 학습하고 실환경은 처음 접하므로,
  실환경에서도 통하면 "동어반복"이 아닌 "일반화"임이 증명된다.
- **메트릭 (a) 시뮬 정확도**: 트래픽별 시뮬 예측 throughput/loss vs 실측의 오차(%).
- **메트릭 (b) 정책 성능 gap**: 시뮬 total bytes vs 실환경 total bytes의 차이(%).
- **합격선**: gap이 작을수록 좋으나, 절대값이 다소 어긋나도 **A<B<C<D 등 전략
  순위(ordering)가 실환경에서도 유지**되면 연구 주장은 성립한다.

---

## 참고 자료

읽을거리 목록: `reference/READING_LIST.md` (NWDAF 표준, RL 네트워크 제어,
**시뮬레이터 학습·sim-to-real(섹션 C-3)**, CNI 성능, elephant flow,
마이그레이션 비용 — dCollection + OpenAlex 수집).
