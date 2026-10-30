# First Glance — Reading List for the AI Review Paper

> **Purpose**: 리뷰 논문(영문, ~3,000 words, "내 관심 영역에서 AI가 어떻게
> 활용되는가")을 쓰기 위해 **큰 그림 → 디테일** 순서로 읽을 논문 목록.
> 읽는 순서 = 리뷰의 논리 흐름.
>
> **Source of truth**: 서지정보·상세는 `REFERENCES.md`의 [C1]–[C6] 및
> `READING_LIST.md` 참조. 인용 키는 `references.bib`.
> 아웃라인: `REVIEW_PAPER_outline.md`.
>
> **How to read**: 레벨 0~1을 먼저 통독(리뷰의 ~70%가 잡힘). 레벨 2는 집필 중
> 필요 부분만 발췌. 레벨 3은 선택.
>
> 체크박스로 진행 추적: [ ] 미독 / [x] 완독 / [~] 발췌만

---

## LEVEL 0 — 큰 그림 (도메인 전체 지도, 흐름만)

목표: "UPF 데이터플레인이 뭔지 + 왜 중요한지 + 왜 AI가 들어오는지" 맥락 잡기.

- [ ] **0-1. 3GPP TS 23.501** — 5G System Architecture (UPF/user plane 위치)
  - 범위: UPF가 무엇이고 데이터플레인 어디에 있는지만. (clause: UPF/PDU session)
  - 리뷰 섹션: §1 Introduction, §2.1 Background
  - 참조: REFERENCES.md [A5]
  - 🔗 https://www.3gpp.org/ftp/Specs/archive/23_series/23.501/

- [ ] **0-2. Mishra & Pandey — Kernel-Level Per-Slice UPF Latency Measurement**
  - arXiv:2605.28185 (2026). 왜 UPF 데이터플레인 성능이 실제로 중요한지 (실측).
  - 포인트: forwarding delay가 부하에 민감(eMBB 99p 574→1243µs).
  - 리뷰 섹션: §1
  - 참조: REFERENCES.md [A1]
  - 🔗 https://arxiv.org/abs/2605.28185

- [ ] **0-3. DRL for Cloud-Native Wireless Network (slicing/MEC)**
  - arXiv:2305.06249 (Wang et al.). "AI가 네트워크 자원제어에 쓰인다"의 큰 그림.
  - 범위: intro + 문제설정만. 두 use case(slicing, MEC) 개념.
  - 리뷰 섹션: §2.3, §3 도입
  - 참조: (bib 미등록 — 필요 시 추가)
  - 🔗 https://arxiv.org/abs/2305.06249

- [ ] **0-4. 3GPP NWDAF 입문 — 이승현, "오픈소스 기반 5G NWDAF 설계 및 구현"** ★5G-AI 핵심
  - 고려대 석사, 2023 (지도 백상헌). NWDAF 표준+구현을 한국어로 정리, 입문 최적.
  - 왜 ★: 리뷰 주제가 "5G에서 AI"인데 NWDAF는 5G Core의 **유일한 표준 AI 분석 NF**.
    이거 없이는 리뷰가 성립 안 됨. 큰 그림에서 "5G의 AI 표준 엔진" 역할 파악.
  - 리뷰 섹션: §2.3, §4 (표준 AI 폐루프)
  - 참조: READING_LIST.md B
  - 🔗 https://dcollection.korea.ac.kr/srch/srchDetail/000000270210

- [ ] **0-5. 3GPP TS 23.288** — NWDAF 본체 표준 (AnLF/MTLF, analytics 종류)
  - 범위: clause 5(아키텍처), clause 6(analytics 종류)만 훑기. producer/consumer 구조.
  - 리뷰 섹션: §4 (표준 AI 폐루프), 본 연구 포지셔닝 근거
  - 참조: REFERENCES.md [A4], READING_LIST.md A
  - 🔗 https://www.3gpp.org/ftp/Specs/archive/23_series/23.288/

---

## LEVEL 1 — 리뷰의 두 축 (뼈대, 제대로 읽기)

### 축 A — 학습 기반 네트워크/K8s 제어 (성숙한 "방법 패턴") → §3

- [ ] **A-1. FIRE — Failure-Adaptive RL for Edge Migrations** ★정석
  - Siew et al., IEEE TSC (accepted); arXiv:2209.14399.
  - 왜 ★: **sim(digital twin) 학습 + migration cost를 reward에 + greedy/vanilla RL
    baseline 비교** — 이 분야 방법 패턴의 교과서.
  - 리뷰 섹션: §3.3
  - 키: `siew2022fire` / 참조: [C3]
  - 🔗 https://arxiv.org/abs/2209.14399

- [ ] **A-2. RL-HPA / Cost-Efficient RL Autoscaling** (고려대 계열)
  - READING_LIST C-1 (김성석 전이학습; 장용현 cost-efficient RL; 큐잉모델 시뮬).
  - 포인트: 실환경 RL 학습 비용 → 시뮬 학습 전략. 비용 인지형 제어.
  - 리뷰 섹션: §3.1
  - 참조: READING_LIST.md C-1
  - 🔗 전이학습: https://dcollection.korea.ac.kr/srch/srchDetail/000000267388
  - 🔗 cost-efficient RL: https://dcollection.korea.ac.kr/srch/srchDetail/000000257731
  - 🔗 큐잉모델 시뮬: https://dcollection.korea.ac.kr/srch/srchDetail/000000265207

- [ ] **A-3. PDS-based Flow Allocation in UPFs**
  - Bhat et al., ICC 2026 submitted; arXiv:2601.03108.
  - 포인트: UPF 간 flow 배정을 MDP+RL, 시뮬 학습, Q-learning 대비 우위.
  - 리뷰 섹션: §3.2
  - 키: `bhat2026flowalloc` / 참조: [C6-3]
  - 🔗 https://arxiv.org/abs/2601.03108

- [ ] **A-4. Layer-Aware Container Migration (RL)**
  - Liu et al., arXiv:2406.13404 (2024).
  - 포인트: migration cost vs latency break-even을 policy-gradient RL로.
  - 리뷰 섹션: §3.3
  - 키: `liu2024migration` / 참조: [C4]
  - 🔗 https://arxiv.org/abs/2406.13404

### 축 B — 런타임 데이터패스/NF 적응 (떠오르는 "대상") → §4

- [ ] **B-1. Dynamic AI-Based UPF Switching** ★가장 가까운 경쟁
  - Christakis, Makris, Fdida, Korakis — IEEE Globecom 2025.
  - 왜 ★: UPF 앱 구현(SPGW-U↔VPP)을 LSTM 예측으로 전환. 본 연구/리뷰 핵심 비교군.
  - 읽을 때: 전환 대상(L7 앱), 방법(LSTM 예측), 비용(energy) 정확히 메모.
  - 리뷰 섹션: §4.1
  - 키: `christakis2025upfswitching` / 참조: [C6-1]
  - 🔗 https://sunrise6g.eu/wp-content/uploads/2026/01/UPF_Switching_Final-Globecom-2025.pdf

- [ ] **B-2. Intelligent eUPF — Time-Sensitive Path Selection**
  - Moreira et al., ICCSA 2026; arXiv:2605.01475.
  - 포인트: DQN+POMDP로 MEC↔cloud 경로 선택, eBPF passive delay 측정.
  - 리뷰 섹션: §4.2
  - 키: `moreira2026eupf` / 참조: [C6-2]
  - 🔗 https://arxiv.org/abs/2605.01475

- [ ] **B-3. NWDAF-enabled Analytics and Closed-Loop Automation** ★표준 AI 폐루프
  - arXiv:2505.06789 (NOMS 2026).
  - 왜 ★: NWDAF 분석 → **SMF가 consume하여 집행**하는 폐루프 = 본 연구의 판단/집행
    분리 설계의 직접 선례이자, "5G 표준이 AI 분석을 어떻게 집행으로 연결하나"의 핵심 사례.
  - 읽을 때: producer(NWDAF)/consumer(SMF) 분리 구조에 주목.
  - 리뷰 섹션: §4.3 (표준 AI 폐루프)
  - 참조: READING_LIST.md B
  - 🔗 https://arxiv.org/abs/2505.06789  (DOI: https://doi.org/10.1109/noms69089.2026.11668240)

- [~] **B-4. Multus Dynamic Networks Controller / CNI-Genie** (참고 — 정독 아님)
  - GitHub 도구. 런타임 CNI 변경 **메커니즘**은 되나 "언제(정책)"는 없음. README만.
  - 리뷰 섹션: §4.3 (mechanism vs policy 구분 — 1~2문장 인용용)
  - 키: `multus_dynamic_networks`, `cnigenie` / 참조: [C6-4]
  - 🔗 https://github.com/k8snetworkplumbingwg/multus-dynamic-networks-controller
  - 🔗 https://github.com/cni-genie/CNI-Genie/

---

## LEVEL 2 — 디테일 보강 (전제·배경, 발췌 읽기)

- [ ] **2-1. Dakic et al. — K8s CNI Performance/Latency Evaluation**
  - Electronics 2024, 13(19):3972. "CNI는 패킷크기/워크로드별 최적이 다름" 근거.
  - 리뷰 섹션: §2.2
  - 키: `dakic2024cni` / 참조: [C1]
  - 🔗 https://www.mdpi.com/2079-9292/13/19/3972

- [ ] **2-2. Kang et al. — CNI Plugins for Edge (ARM+AMD)**
  - IEEE IC2E 2021. 엣지 CNI 오버헤드 평가.
  - 리뷰 섹션: §2.2
  - 키: `kang2021cni` / 참조: [C2]
  - 🔗 https://www.dre.vanderbilt.edu/~gokhale/WWW/papers/IC2E21_CNI_Eval.pdf

- [ ] **2-3. UPF Dataplane I/O Modes Comparison (AF_PACKET/AF_XDP/CNDP/DPDK)**
  - arXiv:2608.14589. 소프트웨어 포워딩 경로별 성능 — §2.1 배경 보강.
  - 리뷰 섹션: §2.1
  - 참조: (bib 미등록 — 필요 시 추가)
  - 🔗 https://arxiv.org/abs/2608.14589

- [ ] **2-4. ipvlan / macvlan 커널 문서**
  - 드라이버 동작 원리(IP 기반 vs MAC 기반 분배).
  - 리뷰 섹션: §2.2
  - 참조: REFERENCES.md [B1]
  - 🔗 https://www.kernel.org/doc/html/latest/networking/macvlan.html
  - 🔗 http://people.netfilter.org/pablo/netdev0.1/papers/IPVLAN-The-beginning.pdf

- [~] **2-5. RL 기초 도구 (§2.3 정의용 — 발췌)**
  - MDP/RL/DQN 용어 정의 + 커스텀 환경·알고리즘 구현체 레퍼런스.
  - 리뷰 섹션: §2.3 ("AI control"의 방법 정의)
  - 🔗 Gymnasium: https://gymnasium.farama.org/introduction/create_custom_env/
  - 🔗 Stable-Baselines3: https://stable-baselines3.readthedocs.io/

- [ ] **2-6. Sim-to-Real / Digital Twin for Network RL (§5 challenges)**
  - 시뮬 학습 → 실환경 배포의 gap. 본 연구/리뷰의 핵심 open challenge.
  - 리뷰 섹션: §5 (open challenges), 본 연구 sim-to-real 방어 근거
  - 참조: READING_LIST.md C-3
  - 🔗 Digital Twin DRL: https://doi.org/10.1109/tcomm.2024.3395698
  - 🔗 Mobile network sim-to-real: https://doi.org/10.48550/arxiv.1802.06416
  - 🔗 Real–Sim–Real transfer(방법론): https://doi.org/10.3390/app10051555

---

## LEVEL 3 — (선택) 도메인 색칠 / 동기

- [ ] **3-1. 5G-ACIA White Paper — Machine Vision with 5G** (2022)
  - 머신비전 = 고대역폭 지속 트래픽. 트래픽 교차 동기.
  - 키: `5gacia2022machinevision` / 참조: [C5-1]
  - 🔗 https://5g-acia.org/ (download/24343)

- [ ] **3-2. Seliem et al. — Multi-Flow 5G UE: Smart Factory** (MSWiM 2025)
  - 제어+머신비전+벌크 동시 처리. 멀티플로우 사례.
  - 키: `seliem2025smartfactory` / 참조: [C5-2]
  - 🔗 https://arxiv.org/abs/2508.21783

---

## 읽기 → 집필 매핑 (요약)

```
LEVEL 0 (0-1~0-5)      → §1 Introduction, §2 Background 도입, §4 NWDAF 큰그림
LEVEL 1 축A (A-1~A-4)  → §3 AI Theme 1 (학습 기반 제어)
LEVEL 1 축B (B-1~B-4)  → §4 AI Theme 2 (런타임 적응 + 표준 AI 폐루프/NWDAF)
  └ 축A ∩ 축B 가 비어있음 → §5 Discussion: GAP (리뷰 핵심 통찰)
LEVEL 2 (2-1~2-6)      → §2 Background(2-1~2-5) + §5 challenges(2-6)
LEVEL 3 (3-1~3-2)      → §1/§5 동기·색칠 (선택)
```

## TODO (리스트 보강 — 선택)

- [ ] bib 미등록 2건 추가 여부 결정: DRL Cloud-Native Wireless(2305.06249),
      UPF I/O-mode(2608.14589). §2 집필 시 필요하면 references.bib에 등록.
- [ ] NWDAF 입문(이승현)·TS 23.288·sim-to-real 자료의 bib 키 등록 여부 결정
      (현재 READING_LIST에 URL만 있고 bib 키 미부여).
