# READING LIST — NWDAF 표준 & 강화학습(RL) 기반 네트워크 제어

본 연구("NWDAF 패턴을 차용한 UPF CNI 전환 시점의 RL 기반 판단")를 위한 선행
학습 자료 목록. `unified_paper_search.py`(dCollection + OpenAlex)로 수집.

> 포지셔닝 메모: 표준 NWDAF는 세션/UPF 레벨 최적화를 데이터 기반으로 판단한다.
> 본 연구는 그 "관측→분석→폐루프 제어" 패턴을 **데이터플레인 CNI 전환**이라는
> 새로운 제어 대상으로 **확장**한다. (표준에 CNI 전환이 있는 것이 아님 — 패턴 차용)

---

## A. NWDAF / 5G 코어 표준 (1순위: 반드시)

3GPP 문서는 https://www.3gpp.org/ftp/Specs/archive/ 또는 https://portal.3gpp.org 에서 무료.

- **3GPP TS 23.288** — Architecture enhancements for 5GS to support network data
  analytics services. **NWDAF 본체 문서.** AnLF/MTLF 분리, analytics 종류(load
  level, NF load, UE mobility, QoS sustainability 등). → Background 절의 근거.
  집중: clause 5(아키텍처), clause 6(각 analytics).
  https://www.3gpp.org/ftp/Specs/archive/23_series/23.288/
- **3GPP TS 23.501** — System architecture for the 5G System. UPF/user plane의
  표준적 위치. CNI 전환이 건드리는 데이터플레인의 맥락.
  https://www.3gpp.org/ftp/Specs/archive/23_series/23.501/
- **3GPP TS 23.502** — Procedures for the 5G System. 세션 수립/수정, UPF 선택·
  재배치(relocation) 절차 → "NWDAF 세션 전환"의 표준 절차 근거.
  https://www.3gpp.org/ftp/Specs/archive/23_series/23.502/

## B. NWDAF 입문/정리 (1순위: 표준 읽기 전 먼저)

- **[국내·동일학교] 이승현, "오픈소스 기반의 5G 네트워크 데이터 분석 기능 설계 및
  구현", 고려대 석사, 2023 (지도 백상헌).** NWDAF 표준+구현을 한국어로 정리.
  입문용 최적, 인용도 자연스러움.
  https://dcollection.korea.ac.kr/srch/srchDetail/000000270210
- Towards NWDAF-enabled Analytics and Closed-Loop Automation in 5G Networks, 2026.
  **NWDAF 기반 폐루프(closed-loop) 자동화** — 본 연구의 closed-loop 구조와 직결.
  https://doi.org/10.1109/noms69089.2026.11668240
- Beyond NWDAF Services for Comprehensive 5G Network Analytics and Orchestration, 2025.
  https://doi.org/10.1109/cits65975.2025.11099169
- Data Collection Using NWDAF Network Function in a 5G Core Network (real testbed), 2023.
  NWDAF 데이터 수집 실측 — 구현 레퍼런스.
  https://doi.org/10.1109/isncc58260.2023.10323894

## C. 강화학습(RL) 기반 네트워크/쿠버네티스 제어 (2순위: 방법론 핵심)

### C-1. 쿠버네티스 × RL (본 연구와 가장 가까움, 시뮬 학습 전략 포함)
- **[국내·동일학교 계열] 김성석, "강화학습 기반 수평적 파드 오토스케일링 정책의
  학습 가속화를 위한 전이학습 기법", 고려대, 2022.** RL HPA의 실환경 학습 비용
  문제 → **시뮬레이션 학습 + 전이학습**. **본 연구 시뮬레이터 전략의 직접 근거.**
  https://dcollection.korea.ac.kr/srch/srchDetail/000000267388
- **[국내·동일학교 계열] "대기행렬 모델을 활용한 강화학습 기반 파드 오토스케일링
  기법", 2022.** 큐잉 모델 시뮬로 RL 정책 학습/비교. **시뮬레이터 설계 참고.**
  https://dcollection.korea.ac.kr/srch/srchDetail/000000265207
- **[국내·동일학교 계열] 장용현, "Cost-Efficient RL-based Horizontal Pod
  Autoscaling in Kubernetes Cluster", 고려대, 2022 (지도 유헌창).** 'cost-efficient'
  명시 — 비용 인지형 RL 제어. 본 연구 비용-이득 프레이밍과 직접 연결.
  https://dcollection.korea.ac.kr/srch/srchDetail/000000257731
- RL-driven Kubernetes autoscaling for high-throughput 5G, 2025. RL×K8s×5G 삼박자.
  https://doi.org/10.30574/wjaets.2025.15.2.0663
- DRS: a deep RL enhanced Kubernetes scheduler for microservices, 2023 (cite 42).
  https://doi.org/10.1002/spe.3284
- Efficient Microservice Deployment in Kubernetes via RL, 2024 (cite 29).
  https://doi.org/10.1109/noms59830.2024.10575912

### C-2. RL × 5G/네트워크 제어 일반 (DRL 정합성 근거)
- Admission Control and Virtual Network Embedding in 5G: Deep RL, 2022 (cite 27).
  https://doi.org/10.1109/access.2022.3148703
- Uplink Power Control Framework Based on RL for 5G, 2021 (cite 29).
  https://doi.org/10.1109/tvt.2021.3074892
- RL-based Dynamic Admission Control with Resource Recycling, 2023.
  https://doi.org/10.1109/globecom54140.2023.10437226
- **[국내·동일학교]** 분산 강화학습 기반 무선랜 네트워크 최적화, 고려대, 2023.
  https://dcollection.korea.ac.kr/srch/srchDetail/000000277018

### C-3. 시뮬레이터 학습 & Sim-to-Real (★ 본 연구 학습 전략의 핵심 근거)

"시뮬에서 RL 학습 → 실환경 평가 + sim-to-real gap 검증"이 분야 표준임을 뒷받침.
단일 노드에서 RL 학습이 가능한 이유이자, 순환논리 방어(gap 보고)의 방법론 근거.

- **[국내·동일학교, 직접 선례] "대기행렬 모델을 활용한 강화학습 기반 파드
  오토스케일링", 고려대, 2022.** 쿠버네티스 RL 정책을 **큐잉 시뮬레이션에서 학습·
  비교** — 본 연구 시뮬 전략과 판박이. (섹션 C-1과 중복, 시뮬 관점에서 재참조)
  https://dcollection.korea.ac.kr/srch/srchDetail/000000265207
- Digital Twin-Enhanced DRL for Resource Management, 2024 (cite 60). **디지털 트윈
  (=실시스템 시뮬 복제본)에서 DRL 학습** — 본 연구 시뮬의 학술 용어/정석.
  https://doi.org/10.1109/tcomm.2024.3395698
- Digital Twin-Accelerated Online DRL for Admission Control, 2024 (cite 21).
  https://doi.org/10.1109/tcomm.2024.3476430
- Digital Twin Virtualization with ML for IoT and Beyond 5G, 2022 (cite 39).
  https://doi.org/10.1145/3522783.3529519
- Digital Twin-Based Network Slice Optimization Using DRL, 2026.
  https://openalex.org/W7220313540
- Sim-to-Real Optimization of Complex Real World Mobile Network, 2018. **모바일
  네트워크 sim-to-real** — 네트워크 도메인 sim-to-real 선례.
  https://doi.org/10.48550/arxiv.1802.06416
- Real–Sim–Real Transfer for Real-World Robot Control Policy, 2020 (cite 32).
  sim-to-real gap 검증 방법론(로보틱스의 정석).
  https://doi.org/10.3390/app10051555
- (도구) Learning to Fly — a Gym Environment with PyBullet for RL, 2021 (cite 203).
  **커스텀 Gym 환경 구축 예시** — 본 연구 시뮬레이터를 Gym 인터페이스로 만들 때 참고.
  https://doi.org/10.1109/iros51168.2021.9635857
- (도구) Gymnasium(구 OpenAI Gym) 공식 — 커스텀 환경 작성 가이드.
  https://gymnasium.farama.org/introduction/create_custom_env/
- (도구) Stable-Baselines3 — 검증된 RL 알고리즘(DQN 등) 구현체.
  https://stable-baselines3.readthedocs.io/

## D. 컨테이너/CNI 데이터플레인 성능 (문제정의·baseline 근거)

- **UniNet: Accelerating the Container Network Data Plane in IaaS Clouds, 2024.**
  컨테이너 네트워크 데이터플레인 가속 — CNI 데이터패스 성능의 직접 근거.
  https://doi.org/10.1109/cloud62652.2024.00023
- A Comprehensive Benchmark of Flannel CNI in SDN/Non-SDN Cloud-Native, 2025.
  CNI 성능 벤치마크 방법론 — Preliminary Results(ipvlan/macvlan 비교) 보강.
  https://doi.org/10.1109/tnsm.2025.3602607
- Kubernetes Load-balancing and related network functions using P4, 2021 (cite 9).
  https://doi.org/10.1145/3493425.3502768

## E. 트래픽 특성 / scope 근거 (elephant vs mice flow)

본 연구 scope("순간 단절 민감 트래픽이 아니라 장기·대량 트래픽에 효과적")의 근거.

- Flow-Aware Elephant Flow Detection for SDN, 2020 (cite 58).
  https://doi.org/10.1109/access.2020.2987977
- Adaptive approach for elephant flow detection, 2017 (cite 14).
  https://doi.org/10.1002/nem.1987

## F. 비용-이득 / 마이그레이션 비용 (break-even 수식 근거)

- **[국내·동일학교]** 차량 엣지 컴퓨팅에서 리버스 옥션 기반 서비스 마이그레이션/
  경로 결정 알고리즘, 고려대, 2024 (지도 백상헌). 마이그레이션 비용-이득 의사결정.
  https://dcollection.korea.ac.kr/srch/srchDetail/000000257665
- Live migration of containerized microservices between remote Kubernetes
  (OpenAlex; "service migration cost kubernetes"로 재검색). downtime 비용 근거.

---

## 읽는 순서 (추천)

1. B의 이승현(2023) 석사논문으로 NWDAF 전체 그림 잡기 (한국어)
2. A의 TS 23.288 clause 5·6 훑으며 표준 용어 확인
3. C-1의 고려대 RL-HPA 3편 → 시뮬레이터 학습 전략 흡수 (본 연구 핵심)
4. B의 NWDAF closed-loop(2026)로 폐루프 자동화 포지셔닝 확인
5. D/E/F로 문제정의·scope·비용수식 보강

_생성: unified_paper_search.py (dCollection + OpenAlex), 2026-10._
