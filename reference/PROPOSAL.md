# 연구 계획서

## Title

"NWDAF-Driven Dynamic CNI Backend Selection for Cloud-Native 5G UPF on ARM: Cost-Aware Switching via Random Forest"

---

## 연구 질문

> NWDAF(Random Forest)가 트래픽 패턴을 분석하여, Pod 재생성 비용(downtime)을 감수해도 이득인 CNI 전환 시점을 올바르게 판단하는가?

---

## Abstract

Cloud-native 5G Core에서 User Plane Function(UPF)의 data plane 성능은 Container Network Interface(CNI) 드라이버에 영향을 받는다. 본 연구는 ARM64 Kubernetes 환경의 free5GC UPF에서 ipvlan과 macvlan이 트래픽 특성에 따라 상이한 성능을 보임을 공정 조건에서 실증하고(소패킷: ipvlan 유리, 대패킷: macvlan 유리), 3GPP TS 23.288 NWDAF AnLF를 Random Forest로 구현하여 Pod 재생성 기반 CNI 전환의 최적 시점을 자동 판단하는 closed-loop 시스템을 설계, 구현, 검증한다. 전환 비용(downtime 중 패킷 손실)은 전체 세션의 누적 throughput에 자연 포함되며, 전략별 전체 세션의 total bytes received를 직접 비교하여 판단의 유효성을 평가한다. 실험은 5가지 트래픽 패턴에서 120초간 수행되며, RF 전환이 고정 CNI 및 Rule-based 전환 대비 Net Gain, False Positive 억제, Reaction Time에서 우위를 보이는지 검증한다.

---

## Contribution

1. NWDAF(Random Forest)가 UPF의 KPI를 기반으로, Pod 재생성 비용(downtime)을 포함한 전체 세션 throughput이 고정 CNI 및 Rule-based 대비 개선되는 전환 시점을 올바르게 판단하는지를, 공정 조건(물리 NIC 직접 분기) ARM64 환경에서 실증한다.

2. ML 기반 네트워크 의사결정 시스템의 평가 기준으로, 분류 정확도(accuracy)가 아닌 결정의 실효적 이득(total bytes received)을 직접 측정하는 평가 프레임워크를 제안한다. 이를 통해 전환 비용, 판단 오류, 타이밍 등 모든 요소가 단일 메트릭에 자연 반영되며, 다양한 모델 간 공정 비교가 가능해진다.

---

## Preliminary Results

공정 조건(물리 NIC 직접 분기)에서 측정:

| 조건 | macvlan | ipvlan | 유리 |
|------|---------|--------|------|
| 소패킷 64B (high pps) | loss 2.64% | loss 2.42% | ipvlan |
| 대패킷 1400B (500Mbps) | loss 0.16% | loss 0.33% | macvlan |

→ 트래픽 특성에 따라 최적 CNI가 상이함을 실증
→ 동적 전환의 당위성 확보

---

## 현재 진행 상태

- ARM64 K8s 클러스터 + free5GC 전체 NF 배포 완료 (동작 중)
- NWDAF 엔진 구현 완료 (Random Forest 학습/추론 파이프라인)
- 트래픽 생성기 및 모니터링 시스템 구축 완료
- Baseline 측정 데이터 확보 (ipvlan/macvlan 공정 비교)
- 남은 작업: 전환 실험(C, D) 수행 → 비교 분석 → 논문 writing

---

## 논문 구조

```
1. Introduction
   - 문제: 정적 CNI 할당의 한계 + 전환 비용(downtime)이 존재
   - 연구 질문: RF가 전환 비용 포함해도 이득인 시점을 판단하는가?
   - Contribution

2. Background & Related Work
   - 5GC UPF data plane (TS 23.501)
   - NWDAF 아키텍처 (TS 23.288, AnLF/MTLF)
   - CNI 성능 비교 선행연구 (ipvlan vs macvlan)
   - Pod lifecycle 기반 CNI 전환 비용

3. System Design
   - 아키텍처: free5GC + NWDAF on ARM64 K8s (단일 노드, 4 vCPU)
   - 전환 메커니즘: Pod 재생성 (kubectl scale)
   - NWDAF: OAM 수집 → RF 추론 → 전환 판단 → 실행
   - ML: Random Forest (시계열 feature, 5초 주기)
   - 격리: CPU pinning

4. Experiment Design
   - 공정 조건: 물리 NIC 직접 분기 (편향 제거)
   - 트래픽 5종, 전부 120초
   - 전략 4종: A(ipvlan) / B(macvlan) / C(Rule-based) / D(RF)
   - 평가: total bytes received (120s)
   - 5회 반복, 95% CI

5. Evaluation
   - Baseline: ipvlan vs macvlan 공정 비교
   - D vs A, B: RF 전환이 고정보다 나은가?
   - D vs C: RF가 Rule-based보다 나은가?
   - False Positive: spike/oscillation에서 전환 억제
   - Reaction Time: 전환 필요 시점 대비 지연

6. Discussion
   - ARM64 커널 경로 특성
   - RF 한계, 후속 연구(다중 모델 비교)
   - Limitation

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

### 전략 (4종)

| 전략 | 설명 | 역할 |
|------|------|------|
| A | ipvlan 고정 120초 | Baseline (소패킷 최적) |
| B | macvlan 고정 120초 | Baseline (대패킷 최적) |
| C | Rule-based 전환 | ML이 왜 필요한지 증명용 baseline |
| D | RF 전환 | 본 연구의 핵심 |

### 평가 기준

```
점수 = 120초간 서버가 받은 total bytes

성공 기준:
  D > A (RF가 ipvlan 고정보다 나음)
  D > C (RF가 Rule-based보다 나음)
  
추가 메트릭:
  - False Positive Rate: T3, T5에서 불필요 전환 횟수
  - Reaction Time: T1, T2에서 정답 시점 대비 지연(초)
```




