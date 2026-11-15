# Kestrel: Rethinking Telemetry Design for Fine-Grained Anomaly Detection in 5G User Planes

**저자**: Niloy Saha, Noura Limam, Yang Xiao, Raouf Boutaba (University of Waterloo)
**출처**: arXiv:2510.27664v1 [cs.NI], 2025-10-31
**링크**: abs https://arxiv.org/abs/2510.27664 · pdf https://arxiv.org/pdf/2510.27664

> Waterloo(Boutaba 랩) 작업. Ardestani thesis(NWDAF closed-loop)와 같은 그룹.
> 우리 연구(PROPOSAL-ebpf-telemetry)의 가장 가까운 선행이자 최대 경쟁.

---

## 핵심 요약

- **문제**: 5G UPF에서 QoS 이상 탐지는 fine-grained per-flow 가시성이 필요하나, 기존 텔레메트리는
  trade-off에 갇힘 — (a) coarse per-class counter(3GPP-PM)는 가볍지만 transient/per-flow 이상을
  가림, (b) per-packet postcard는 완전하지만 line rate에 비례해 비용 폭발(10Gbps/200B에서 >3Gbps, >30%).
- **제안 (Kestrel)**: sketch 기반 텔레메트리. **Count-Min Sketch를 histogram-augmented bucket +
  per-QID 파티셔닝으로 확장** → per-TEID **분포**(latency tail, inter-arrival time, policer color)를
  compact하게 보존. export는 트래픽의 ~0.15%.
- **형식적 보장**: sketch collision 고려한 detectability 조건 + sizing rule(w=512, d=3이면 50ms microburst도 탐지).
- **구현/평가**: **Intel Tofino ASIC(하드웨어 P4)** 스위치, 10Gbps, 8 queue. XGBoost 탐지기(anomaly별 4개).
  - 집계(3GPP-PM) 대비 AUPRC 2배, ∆-SMP(postcard sampling) 대비 10배 적은 대역폭 + 13% 높은 AUPRC.
  - 4가지 이상: congestion, contention, microburst, policy abuse (+mixed).

## 핵심 수치

- contention에서 3GPP-PM 0.22 / ∆-SMP 0.37 / **Kestrel 0.75** (집계가 가장 크게 실패하는 지점).
- mixed에서 3GPP-PM 0.43 / ∆-SMP 0.71 / **Kestrel 0.80** AUPRC.
- time-to-first-detection: 3GPP-PM 5.0s / ∆-SMP 0.70s / **Kestrel 0.80s** (F1 0.81로 최고).
- Tofino 자원: SRAM/TCAM <20%, hash 25%, ALU 35%.

## Future Work (명시)

> "While this work focused on **hardware-accelerated UPFs**, the same principles of
> anomaly-driven telemetry could extend to **software data planes (e.g., eBPF or VPP)**,
> enabling lightweight, anomaly-aware monitoring for heterogeneous 5G deployments."

→ **soft data plane(eBPF/VPP) 확장을 명시적 future work로 남김.** 우리 틈의 공식 근거.

---

## 우리 연구(PROPOSAL-ebpf-telemetry)와의 관계 — 틈 분석

### 그들이 한 것 (중복 주의)
- "집계는 transient/per-flow를 가린다 → 세분화가 필요"라는 **문제제기와 동기** (우리와 동일)
- 세분화 신호(분포) → ML(XGBoost) 탐지, **집계 대비 우수 실증** (우리의 "세분화>집계"를 이미 함)
- time-to-detection 축도 이미 평가 (우리가 생각한 "빠른 감지"도 이미 다룸)

### 그들이 안 한 것 (우리 틈)
| 축 | Kestrel | 우리 틈 |
|----|---------|--------|
| 플랫폼 | **하드웨어 P4(Tofino ASIC)** | **소프트웨어 data plane(eBPF/virtio)** ← Kestrel future work가 지목 |
| 세분화 신호 | **latency/IAT 분포, policer color** (큐/시간 분포) | **drop 원인 경로 분해**(kfree_skb 97 reason: ring/backlog/qdisc/socket) |
| drop 취급 | drop을 anomaly "증상"으로 탐지 | **drop을 "원인별로 귀속"** (왜/어디서 드롭됐나) |
| 목적 | 이상 **탐지**(detection) | 탐지 → **세션관리 액션**(closed-loop, Ardestani 결합) |
| 환경 | 데이터센터급 라인레이트(10Gbps) | **자원제약 엣지**(4vCPU, virtio, 가속 불가) |
| 판단 | anomaly별 XGBoost 분류 | **원인 귀속 → 원인별 차별화된 액션 + 학습** |

### 핵심 결론 (경계선)
- **"세분화 > 집계"는 쓰면 안 됨** — Kestrel이 이미 함. 우리 novelty 아님.
- **"time-to-detection이 빠르다"도 쓰기 어려움** — Kestrel이 이미 평가.
- **우리 유일 차별점 = (1) drop 원인 경로 귀속(latency/IAT 분포가 아닌 drop reason 축),
  (2) 소프트웨어 eBPF(Kestrel은 HW P4), (3) 탐지가 아닌 세션관리 액션(Ardestani 결합),
  (4) 자원제약 엣지.**
- **주의**: Kestrel의 anomaly(congestion/contention/microburst/policy abuse)는 latency/IAT로
  드러남. drop reason은 그와 **다른 신호 축**이므로 "보완적"이라 주장 가능. 단, drop reason이
  latency/IAT가 못 잡는 걸 잡는다는 걸 보여야 함.

### 경쟁 리스크
- 같은 그룹(Waterloo)이 Kestrel(telemetry) + Ardestani(closed-loop)를 양쪽에서 선점.
- 둘을 합치면(세분화 telemetry → closed-loop) 우리 방향과 매우 가까워짐. **그들이 eBPF soft
  dataplane + drop reason + closed-loop까지 확장하면 우리 틈이 사라질 수 있음.** 속도가 리스크.
