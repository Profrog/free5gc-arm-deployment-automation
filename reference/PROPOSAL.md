# 연구 계획서

## Title

"Learning-Based CNI Selection for CPU- and Drop-Aware Data-Path Adaptation in Cloud-Native 5G UPF on Resource-Constrained Edge"

(자원 제약 엣지의 Cloud-Native 5G UPF에서, CPU·drop을 함께 고려한 데이터패스 적응을 위한 학습 기반 CNI 선택 — 학습 모델을 NWDAF 패턴에 탑재해 rule-based 전환과 비교)

---

## 연구 질문

> **SR-IOV·DPDK 등 하드웨어 가속 데이터패스를 쓸 수 없는 자원 제약 가상화 엣지 노드**에서,
> AI 학습 모델이 트래픽 특성을 관측하여 **{CPU 사용량, packet drop}이 최소가 되는 최적 CNI**를
> — 고정 CNI 및 Rule-based 정책보다 — 더 잘 선택/전환할 수 있는가?

핵심은 "어떤 모델이 더 정확한가"가 아니라 **"학습된 선택이 단순 규칙 대비 {CPU, drop}를
실제로 더 낮추는가"**이다. 따라서 비교 대상은 다른 복잡한 모델이 아니라, 현업의 일반적
관행인 **고정 CNI와 Rule-based(threshold) 정책**이다.

### 문제의 동기: 제약 조건의 집합, 그리고 그것이 나타나는 현실

본 연구의 **1급 동기는 특정 산업이 아니라 "자원 제약 가상화 엣지"라는 제약 조건의
집합**이다. 아래 네 조건이 동시에 성립하는 환경에서, CNI 선택 문제가 발생한다:

1. **가속 데이터패스 부재** — SR-IOV/DPDK 등 하드웨어 가속을 쓸 수 없음.
2. **CPU 병목** — 코어 수가 적어, 패킷 처리(특히 커널 softirq) 비용이 곧바로 여유
   자원을 잠식함(메모리는 상대적으로 여유).
3. **스케일아웃 불가** — 노드 증설 여력이 없는 단일/소수 노드.
4. **트래픽 특성 교차** — 한 UPF가 소패킷(제어)과 대패킷(벌크/영상)을 번갈아 처리.

이 **제약 집합**이 성립하면 "있는 자원으로 데이터패스를 트래픽에 맞춰 바꾸는 것"이
사실상 유일한 적응 수단이 된다. 여기서 중요한 점은 — **핵심은 물리적 위치(클라우드냐
현장이냐)가 아니라 제약의 구조**라는 것이다. "가상화 엣지"는 클라우드 엣지와 온프레미스
가상화를 모두 포함하며, 둘 다 위 제약 집합을 공유할 수 있다.

**구체화 — 이 제약 집합이 비용 결정으로 강제되는 대표 현실: 스마트팩토리 온프레미스
private 5G.** 추상적 제약을 현실에 앵커링하기 위한 대표 사례이다(증명 대상이 아니라
동기부여용 예시). 공장 현장은 위 네 조건을 자연스럽게 만족한다:
- **(조건 1·2·3)** 공장 private 5G core는 비용 효율을 위해 서버룸/스마트랙 내 소수
  (2~3대, 종종 단일)의 범용 COTS 서버에 통합 배치되며, SR-IOV/DPDK·증설이 비용·운영상
  배제된다(5G-ACIA; EnterpriseViewpoint; ASTRI).
- **(조건 4)** 한 공장 단말/UPF가 설비 제어(소패킷·URLLC)와 머신비전 영상 업링크
  (대패킷·eMBB, elephant flow)를 **동시에 처리하며 공정에 따라 교차**한다(Seliem et al.,
  MSWiM 2025; 5G-ACIA; Nokia). → 고정 CNI는 한쪽에 항상 불리.

### 환경 전제: testbed가 "제약 집합"을 만족함을 실측 검증 (2026-11-05)

본 testbed가 공장 하드웨어를 물리적으로 복제하는 것은 아니다. **testbed와 공장이
공유하는 것은 위 "제약 조건의 집합"이며**, CNI 선택 문제는 바로 그 제약 구조에서
발생하므로 결과가 이전된다. 아래는 노드(`5g-vnci`)에서 직접 확인한 값으로, testbed가
제약 집합을 실제로 만족함을 보인다:

| 제약 조건 | testbed 실측값 | 공장 현실에서의 대응(강제 원인) |
|-----------|---------------|------------------------------|
| ① 가속 데이터패스 부재 | NIC `enp1s0`/`enp0s6` = `virtio_net`, `sriov_totalvfs` 부재; HugePages=0 | COTS 서버 비용·운영상 SR-IOV/DPDK 미채용 |
| ② CPU 병목 | 4 vCPU(ARM Neoverse-N1), 메모리 23Gi 여유 → **병목은 CPU** | 소수 서버 통합 배치, 코어 여유 부족 |
| ③ 스케일아웃 불가 | 노드 1대(단일 control-plane) | 현장 공간·비용 제약, 증설 비현실적 |
| ④ 트래픽 교차 | 트래픽 생성기로 소/대패킷 교차 재현(실험 설계) | 제어 + 머신비전 영상의 공정별 교차 |

> **정직한 구분.** 공유하는 것은 *제약의 구조*이지 물리적 조건이 아니다. testbed는
> Oracle Cloud ARM VM이고 공장은 현장 COTS 서버로, 물리적 위치와 SR-IOV 배제의 원인
> (VM 정책 vs 비용 결정)은 다르다. 그러나 **CNI 선택 문제를 규정하는 네 제약은 양쪽에서
> 동일하게 성립**하므로, 가상화 엣지의 대리 환경(proxy)으로 타당하다. 물리 공장 하드웨어
> 검증은 향후 과제로 남긴다(Discussion의 Limitation 참조).

특히 **메모리는 23Gi로 여유인 반면 CPU는 4코어로 고정**이라는 실측은, 목적함수에
memory가 아니라 **CPU**를 넣은 선택을 환경적으로 정당화한다(아래 "왜 {CPU, drop}인가").

---

## Abstract

Cloud-native 5G Core에서 User Plane Function(UPF)의 data plane 성능은 Container Network
Interface(CNI) 드라이버에 영향을 받는다. 데이터센터급 환경에서는 SR-IOV·DPDK 등 하드웨어
가속 데이터패스로 이를 해결하지만, **스마트팩토리 온프레미스 private 5G처럼 비용 효율을
위해 소수의 범용 COTS 서버(가상화 NIC)에 코어를 통합 배치하는 환경에서는 SR-IOV/DPDK·증설이
비용·운영상 배제되어, 선택지가 소프트웨어 CNI(ipvlan/macvlan)로 한정된다.** 이러한 환경의
UPF는 설비 제어(소패킷)와 머신비전 영상 업링크(대용량 벌크)를 동시에 처리하며 트래픽
성격이 공정에 따라 교차하는데, 고정 CNI는 한쪽에 항상 불리하다. 더욱이 현업에서 CNI는
배포 시점에 고정되고, 런타임 동적 제어가 있더라도 대부분 고정 임계값 기반 Rule에 의존한다.

본 연구는 이러한 **자원 제약 가상화 엣지 환경(ARM64 Neoverse-N1, 4 vCPU, virtio_net NIC,
단일 노드 — 본 testbed 실측)**에서 ipvlan과 macvlan이 트래픽 특성에 따라
**CPU 사용량과 packet drop에서 상이한 성능**을 보임을 공정 조건에서 실증하고, 이 실측
데이터로 **{CPU, drop}을 함께 최소화하는 최적 CNI를 선택하는 AI 모델을 학습**한다.
1차에서는 패킷 특성별 {CPU, drop} 데이터셋을 구축하고, CPU와 drop을 정규화 후 동일
가중(50:50)으로 합한 목적함수로 최적 CNI를 정의하여 학습 모델을 만든다. 2차에서는 이
학습 모델을 3GPP TS 23.288 NWDAF의 "관측→분석→폐루프 제어" 패턴을 차용한 커스텀 AnLF에
탑재하여, **고정 임계값 기반 Rule-based 전환 대비 {CPU, drop} 최소화 성능이 우수한지**
검증한다. 전 과정은 GPU·다중 노드 없이 단일 엣지 노드에서 수행한다.

---

## Contribution

1. **{CPU, drop} 공동 최적화 관점의 CNI 선택 데이터셋 및 학습 모델**: 기존 CNI 비교
   연구가 주로 throughput/latency에 초점을 둔 것과 달리, 본 연구는 **CPU 사용량(특히
   커널 softirq 경로)과 packet drop을 함께** 측정하여, 패킷 특성 → 최적 CNI 매핑을
   **직접 구축한 데이터로 학습**한다. CPU와 drop을 정규화 후 가중합(50:50)한 단일
   목적함수로 최적 CNI를 정의하며, 가중치는 파라미터화하여 민감도를 분석한다.

2. **학습 기반 판단을 NWDAF 패턴에 탑재, Rule-based 대비 검증**: 런타임 CNI 변경
   **메커니즘**은 존재하나[C6-4 Multus/CNI-Genie], **언제·무엇으로 전환할지 판단하는
   정책(policy)은 공백**이다. 본 연구는 1차에서 학습한 모델을 NWDAF 커스텀 AnLF에
   탑재하여 이 공백을 채우고, 현업 관행인 고정 임계값 Rule-based 전환과 **{CPU, drop}
   최소화 측면에서 직접 비교**한다. 가장 가까운 선행연구는 UPF 앱 구현(SPGW-U/VPP)을
   전환하나[C6-1 Globecom'25], 본 연구는 제어 대상을 **UPF 아래 CNI 데이터패스(ipvlan/
   macvlan, L2/L3 커널)**로 옮긴다는 점에서 구별된다.

3. **자원 제약 엣지에 특화된 실증**: SR-IOV/DPDK를 쓸 수 없고 스케일아웃도 제한된
   가상화 엣지에서, 경량 CNI 선택이 사실상 유일한 적응 수단임을 {CPU, drop} 실측으로
   입증한다. 전 과정을 GPU·다중 노드 없이 단일 엣지 노드에서 수행한다.

---

## 문제 정의 & 동기 (실제 사례 기반)

### 환경 제약 (본 testbed 실측 — 경쟁 해법이 배제되는 근거)
본 연구의 타당성은 "왜 스케일아웃이나 고성능 데이터패스가 아니라 CNI 선택인가"에
달려 있다. 본 testbed의 실제 조건이 경쟁 해법들을 환경적으로 배제한다:

| 경쟁 해법 | 본 환경에서 가용성 | 실측 근거 (2026-11-05) |
|-----------|------------------|------|
| **SR-IOV 고정** | ❌ 불가 | `enp1s0`/`enp0s6` 드라이버 `virtio_net`, `sriov_totalvfs` 파일 부재(VF 미지원) |
| **DPDK 고정** | ❌ 비현실적 | `HugePages_Total=0`(미설정), 4 vCPU에 코어 전용 점유 부담 과대, virtio-PMD 이점 미미 |
| **스케일아웃(증설)** | ❌ 제한 | 노드 1대(단일 control-plane), allocatable cpu=4 고정 |
| **QoS/슬라이스 분리** | △ 보완적 | 세션 경로 분리는 가능하나, 각 UPF 내부 데이터패스 성능 문제는 그대로 남음 |
| **경량 CNI 선택/전환(본 연구)** | ✅ 유일하게 가능 | 소프트웨어 CNI(ipvlan/macvlan)만이 선택지 |

→ 즉 **"하드웨어 가속도 증설도 불가능한 범용 가상화 엣지"**에서는, 있는 자원으로
데이터패스를 트래픽에 맞춰 바꾸는 것이 **현실적으로 유일한 적응 수단**이다.

### 현업의 일반론과 그 한계
- **CNI는 사실상 고정**이다. Multus 등으로 배포 시 하나를 정하면 운영 내내 바꾸지 않는다.
- **동적 제어는 대부분 Rule-based**다. Kubernetes HPA의 기본은 "CPU N% 초과 시 스케일"
  같은 고정 임계값이며, 5G 자동화도 정책 규칙 기반이 지배적이다.

### 왜 {CPU, drop} 인가
자원 제약 엣지에서 두 지표는 모두 치명적이며, **본 testbed의 실측 병목과 직접 연결된다.**
- **CPU (이 노드의 실제 병목)**: 본 노드는 메모리 23Gi로 여유가 있으나 **CPU가 4코어로
  고정**되어 있다(실측). 소프트웨어 CNI의 패킷 처리 비용 상당 부분이 **커널 softirq
  (ksoftirqd)**로 소모되는데, 4코어 노드에서 이는 UPF·기타 NF가 쓸 여유 코어를 직접
  잠식한다. 즉 **CPU 여유 = 수용 가능한 추가 워크로드**이므로, CPU는 이 환경에서 1급
  비용 지표다. (메모리가 병목이 아니기에 목적함수에서 memory가 아니라 CPU를 택했다.)
- **drop**: 소패킷·고 pps 구간에서 손실이 급증한다. UPF 데이터패스 품질에 직결.
- 두 지표는 **상충할 수 있다**(한 CNI가 drop은 낮지만 CPU는 더 쓰는 구간). 바로 이
  trade-off 구간에서 단순 임계값 규칙은 한쪽만 보고 그릇된 선택을 하기 쉬우며,
  **두 지표를 함께 학습한 모델이 유리**할 것으로 기대된다. 이 지점이 본 연구의
  핵심 승부처다.

> 요지: 환경 실측(4 vCPU 병목, 가속 데이터패스 배제)이 "왜 CPU를 목적함수에 넣는가"와
> "왜 CNI 선택이 유일한 적응 수단인가"를 **동시에** 정당화한다. 문제 정의가 testbed
> 조건에서 연역적으로 도출된다.

→ 요약: **"하드웨어 가속·증설이 불가능한 제약 엣지에서, 트래픽 특성에 따라 {CPU, drop}을
함께 최소화하는 CNI를 데이터 기반으로 선택한다"**가 본 연구의 공백(gap)이자 기여다.

---

## NWDAF 표준과의 연관성 (포지셔닝)

- **표준 NWDAF (3GPP TS 23.288)**: AnLF(Analytics)/MTLF(Model Training)로 구성, network/NF
  load·QoS sustainability 등 analytics를 제공하고, 이를 세션 관리·UPF 선택/재배치 등
  **세션/UPF 레벨 최적화**에 활용한다. 표준상 NWDAF는 analytics를 **produce**하고,
  consumer NF(SMF/PCF/OAM 등)가 이를 받아 **집행(enforce)**한다.
- **본 연구의 위치 (독립적 기여 + 표준화 제언)**: 본 연구의 1차 기여는 "자원제약
  엣지에서 트래픽 특성 기반 CNI 선택이 {CPU, drop}을 효과적으로 낮춘다"를 **독립적으로
  실증·학습**하는 것이다. 이를 3GPP 생태계로 통합할 경우, AI 분석을 수행하는 표준 NF가
  NWDAF가 유일하므로, 전환 **판단** 지능을 NWDAF의 **커스텀 AnLF**로 편입하는 것이
  자연스럽다.
- **판단/집행 분리 (표준 구조 준수)**: 본 시스템의 closed-loop은 표준의 producer/consumer
  분리에 대응하여 **판단부(AnLF 역할: 학습 모델이 최적 CNI 결정)**와 **집행부(consumer
  역할: CNI 전환 실행)**로 논리적으로 분리된다.
- **명확한 선 긋기 (제언 톤)**: 표준이 CNI 전환을 규정하지는 않으며, 본 연구는 표준
  NWDAF의 완전 준수 구현을 주장하지 않는다. NWDAF의 폐루프 패턴을 차용한 **커스텀
  제어기**이며, "표준에 통합한다면 NWDAF 구조가 적합하다"는 것은 주장이 아니라 **제언**이다.

---

## Preliminary Results

공정 조건(호스트 NIC에 직접 분기, dual-bridge/veth 미경유)에서 측정한 기존 결과
(drop/throughput, 2026-10-31):

| 조건 | macvlan drop | ipvlan drop | 유리(drop) |
|------|---------|--------|------|
| 소패킷 64B (uncapped, high pps) | ~1.18% | ~1.35% | macvlan |
| 대패킷 1400B (800Mbps) | ~0.036% | ~0.037% | 유사 |
| 대패킷 1400B (1200Mbps) | ~0.113% | ~0.111% | 유사 |

→ 트래픽 특성에 따라 drop 거동이 달라짐을 확인. **단, 기존 데이터에는 CPU 지표가 없어**,
본 연구의 목적함수({CPU, drop})를 평가하려면 **CPU 수집을 추가한 재측정이 필요**하다
(아래 진행 상태 참조). CPU를 포함하면 특히 소패킷·고 pps 구간에서 CNI 간 차이가 더
뚜렷해질 것으로 예상된다.

---

## 현재 진행 상태

- ARM64 K8s 클러스터 + Multus/CNI 측정 환경 동작 중. CNI 공정 비교용 NAD
  (fair-ipvlan/fair-macvlan, 물리 NIC `enp1s0` 직결) 구성 완료.
- **환경 전제 실측 검증 완료(2026-11-05)**: aarch64 Neoverse-N1 / 4 vCPU / virtio_net
  (SR-IOV VF 미지원) / HugePages 0 / 단일 노드 — SR-IOV·DPDK·스케일아웃이 모두
  환경적으로 배제됨을 확인. CPU가 유일 병목 자원임도 확인(메모리 23Gi 여유).
- **free5GC 코어는 현재 미배포 상태**(MongoDB만 상주). 1차(CNI 데이터셋+학습)에는
  코어/NF가 불필요하므로 문제되지 않음. 2차 검증 시 standalone UPF를 최소로 기동.
- 기존 측정(2026-10-31)은 **drop/throughput만** 보유, **CPU 미수집**.
- **남은 작업**: ① fair-test에 CPU(pod cgroup + node softirq/sys) 수집 추가 →
  ② {CPU, drop} 데이터셋 재측정/구축 → ③ 가중합(50:50, 정규화 후) 라벨링 →
  ④ AI 학습 모델 구현·검증 → ⑤ (2차) NWDAF 탑재 후 Rule-based 대비 평가.

---

## 시스템 설계

### 목적함수 (방법 중립)
CPU와 drop을 각각 [0,1]로 정규화한 뒤 동일 가중으로 합한다(낮을수록 좋음):

```
score(cni | 조건) = 0.5 · norm(CPU) + 0.5 · norm(drop)
```

- `CPU` = pod cgroup CPU + node softirq/sys (커널 패킷처리 비용 포함)
- `drop` = 측정 구간 손실(패킷수/%)
- 각 조건에서 score가 더 낮은 CNI가 그 조건의 **최적 CNI**.
- 가중치(0.5/0.5)는 파라미터화하여 민감도 분석(0.3/0.7, 0.7/0.3 등)에 사용.

### AI 학습 구현의 두 축 (방법 미정 — 데이터 특성에 따라 선택)
동일한 {CPU, drop} 측정 데이터와 위 목적함수를 공통 입력으로 하되, 구현은 두 축 중
하나로 간다:
- **축 1 (지도학습)**: 조건별 최적 CNI를 라벨로 삼아 분류기(RF/XGBoost 등)를 학습.
  실측 데이터를 직접 사용하며 별도 시뮬레이터가 필요 없다.
- **축 2 (강화학습)**: 위 score를 음수화한 값을 reward로 삼아 정책을 학습. 실환경
  에피소드 비용이 커, 측정 데이터 기반 경량 시뮬레이터에서 학습 후 실환경에서는
  평가만 수행한다(sim-to-real gap은 전략 순위 보존으로 검증).

> 두 축 모두 목적함수(가중합 50:50)를 공유하므로, 방법 결정을 데이터 수집 이후로
> 미뤄도 1차 데이터/라벨 설계는 영향받지 않는다.

### 아키텍처 (2차)
- standalone UPF(NRF 등 코어 의존 없이 기동) + NWDAF(커스텀 AnLF, 학습 모델 탑재)
- 폐루프: KPI(CPU/drop) 수집 → 학습 모델 추론(최적 CNI 판단) → 전환 실행
- 전환 메커니즘: 커널 수준 IP 이동(무중단, ~수백 ms) 또는 NAD/Pod 재구성

---

## 실험 설계

### 1차 — CNI 레벨 데이터셋 & 학습
- **측정 변수**: CNI(ipvlan/macvlan) × 패킷크기(64/256/1400B) × 부하(pps/bitrate 스윕)
- **수집 지표**: throughput, drop, **CPU(pod cgroup + node softirq/sys)** — 각 조건 반복
- **라벨링**: 정규화 후 가중합 score가 낮은 CNI를 최적으로 라벨
- **학습/검증**: 패킷 특성 피처 → 최적 CNI 예측. 홀드아웃/교차검증으로 일반화 평가

### 2차 — NWDAF 탑재, Rule-based 대비 검증
| 전략 | 설명 | 역할 |
|------|------|------|
| A | ipvlan 고정 | Baseline (현업 관행) |
| B | macvlan 고정 | Baseline (현업 관행) |
| C | Rule-based 전환 (고정 임계값 if-문) | **비교군** (단순 규칙) |
| D | 학습 모델 전환 (NWDAF 탑재) | **본 연구 제안** |

- **평가지표**: 전환 후 {CPU, drop}(및 가중합 score), 불필요한 전환(flapping) 횟수,
  반응 지연. 트래픽 변동 시나리오에서 반복 측정, 신뢰구간 제시.
- **성공 기준**: D가 A/B(고정) 및 C(Rule-based) 대비 가중합 score를 유의하게 낮춤.
  특히 CPU-drop **trade-off 구간**에서 C 대비 우위가 본 연구의 핵심 주장.

---

## 논문 구조

```
1. Introduction
   - 동기 도메인: 스마트팩토리 온프레미스 private 5G (제어+머신비전 영상 교차)
   - 문제: CNI 고정·Rule-based가 일반론 / 자원제약 엣지에서 {CPU,drop} 모두 중요
   - 공백: 트래픽 특성 기반 CNI 선택을 {CPU,drop} 공동 최적으로 학습한 사례 드묾
   - 연구 질문 / Contribution

2. Background & Related Work
   - 5GC UPF data plane (TS 23.501)
   - NWDAF 아키텍처 (TS 23.288) → 본 연구의 CNI 판단으로의 확장(제언)
   - CNI 성능 비교 (ipvlan vs macvlan), 컨테이너 데이터플레인 [C1,C2]
   - 학습 기반 네트워크/자원 제어 [C3,C4,RL-HPA] : 방법론 선례
   - ★ 가장 가까운 선행연구 차별화 [C6]:
     · [C6-1] Globecom'25 UPF Switching(SPGW-U/VPP) ↔ 본 연구(CNI L2/L3 데이터패스)
     · [C6-4] Multus/CNI-Genie: 전환 "메커니즘"은 있으나 "판단 정책"은 공백
   - 스마트팩토리 5G 멀티플로우 [C5]

3. System Design
   - 목적함수: {CPU,drop} 정규화 가중합(50:50)
   - AI 학습의 두 축(지도/강화) — 방법 중립 서술
   - (2차) NWDAF 커스텀 AnLF + 전환 메커니즘

4. Experiment Design
   - 1차: CNI×패킷특성×부하 → {throughput, drop, CPU} 측정, 라벨링
   - 2차: 전략 A/B/C/D 비교

5. Evaluation
   - 1차: 조건별 최적 CNI, CPU-drop trade-off 구간 식별, 모델 성능
   - 2차: D vs A,B (고정 대비) / D vs C (Rule-based 대비, 핵심)

6. Discussion
   - 적용 scope: 자원 제약 가상화 엣지(SR-IOV/DPDK 불가). 대표 도메인 스마트팩토리.
   - 왜 CNI 선택인가: 경쟁 해법 환경적 배제(실측 근거)
   - Standardization Pathway (제언): 판단을 커스텀 AnLF로 편입하는 구조
   - Limitation: 데이터센터급(SR-IOV 가용)에서는 이득 제한적. 베어메탈 검증은 향후 과제.
     testbed는 가상화 엣지의 제약 집합을 만족하는 **대리 환경(proxy)**이며 물리 공장
     하드웨어(현장 COTS 서버)와는 물리적 위치·SR-IOV 배제 원인이 다르다. 물리 공장
     환경에서의 직접 검증은 future work.

7. Conclusion & Future Work
   - 학습 방법(지도/강화) 확정 및 전환 타이밍 제어로의 확장
```

---

## 참고 자료

읽을거리 목록: `reference/READING_LIST.md`, 서지정보: `reference/REFERENCES.md`,
인용 키: `reference/references.bib`, 아웃라인: `reference/REVIEW_PAPER_outline.md`.
