# Towards NWDAF-enabled Analytics and Closed-Loop Automation in 5G Networks

**저자**: Fatemeh Shafiei Ardestani, Niloy Saha, Noura Limam, Raouf Boutaba (University of Waterloo)
**출처**: arXiv:2505.06789v1 [cs.NI], 2025-05-11 (IEEE/IFIP NOMS 2026)
**링크**: abs https://arxiv.org/abs/2505.06789 · pdf https://arxiv.org/pdf/2505.06789
**코드**: https://github.com/fatemeshafiee/closed-loop-nwdaf

> Ardestani thesis Chapter 4의 바탕 논문. (thesis가 PCF use case까지 확장한 상위 버전)
> Kestrel과 같은 Waterloo 그룹.

---

## 핵심 요약

- **문제**: 기존 NWDAF 구현은 ML로 analytics 생성에만 집중, (1) 표준 데이터 수집(UPF EES),
  (2) closed-loop 집행 통합, (3) end-to-end 평가가 미흡.
- **제안**: 3GPP 준수 closed-loop 프레임워크 (Open5GS + OAI 5GC)
  - **UPF Event Exposure Service(EES)를 C로 최초 구현** — per-flow/session volume·throughput·QoS 표준 수집
  - **ML Model Provision Service (MLflow 통합)** — 모델 수명주기
  - **SMF 확장** — NWDAF 이상행동 analytics 구독 → 이상 UE PDU session release
- **use case**: bot 탐지 (CTU-13 데이터, graph feature + Random Forest) → SMF가 PDU session 종료.
- **평가**: UPF EES 오버헤드 미미(1 subscriber, 100Mbps에서 지연 변화 거의 없음, CPU 소폭),
  수집주기↓ → 탐지지연↓ (단 ML 추론이 bottleneck), NWDAF 모듈 중 MLMPS가 CPU 50%+.

## Table 1 (NWDAF 구현 비교)

| Work | Core | Event Exposure | ML Analytics | Closed-Loop | Focus |
|------|------|:---:|:---:|:---:|-------|
| [9] | Open5GS | ✗ | ✗ | ✗ | Control-plane packet stats |
| [14] | Open5GS | ✗ | ✓ | ✗ | NF interaction clustering |
| [8] | **free5GC** | ✓ | ✓ | ✗ | Performance prediction |
| [6] | OAI EPC | ✗ | ✓ | ✓ | Slice scaling, DDoS |
| [16] | Open5GS | ✓ | ✓ | ✗ | Abnormal UE throughput |
| [15] | OAI 5GC | ✓*(SMF relay) | ✓ | ✗ | Flow anomaly detection |
| **This Work** | Open5GS & OAI 5GC | ✓ | ✓ | **✓** | Closed-loop security (UE anomaly) |

## Future Work (명시)

> "extending the pipeline to support **online training** and enabling **adaptive ML models
> that evolve with network conditions**."

---

## 우리 연구(PROPOSAL-ebpf-telemetry)와의 관계 — 틈 분석

### 그들이 한 것 (중복 주의)
- NWDAF closed-loop end-to-end (수집→분석→집행), 3GPP 준수 ✓
- UPF EES 표준 수집 + 오버헤드 실측 ✓
- SMF 집행(PDU session release) ✓ / MLflow 모델 수명주기 ✓
- Open5GS & OAI (free5GC 아님)

### 그들이 안 한 것 (우리 틈)
| 축 | 이 논문 (Ardestani NOMS) | 우리 틈 |
|----|------------------------|--------|
| 코어 | Open5GS & OAI | **free5GC** (Table 1에서 free5GC는 [8]뿐, closed-loop ✗) |
| 수집 신호 | UPF EES **표준값**(volume/throughput/QoS delay) | **eBPF 경로별 drop 원인**(kfree_skb reason) |
| 집행 대상 | **SMF session release**(보안, 이상 UE 차단) | **세션관리/자원 조정**(성능, drop 원인별 대응) |
| use case | 보안(bot 탐지) | **성능/QoS**(트래픽 교차 시 drop 원인 귀속) |
| 환경 | 데이터센터급(일반) | 자원제약 엣지(virtio, 4vCPU) |
| 모델 | 고정 RF (online training은 future work) | 학습 기반 판단 (그들 FW가 연 문) |

### 핵심 결론
- 이 논문의 use case는 **보안(bot → session release)**이라, 우리의 **성능/QoS(drop 원인 → 세션관리)**와
  **목적이 다름.** closed-loop 틀은 같지만 "무엇을 탐지해 무엇을 하는가"가 다름.
- 그들의 수집은 **표준 EES 집계값**이지 **drop 원인(reason)이 아님** → 우리 신호 축과 다름.
- Future Work("online/adaptive ML")가 우리 학습 기반 판단과 연결점.
- **단 PCF use case(thesis Chapter 5)는 "congestion→rate 조정"이라 우리 성능 방향과 더 가까움.**
  → thesis Chapter 5가 NOMS 논문보다 우리에게 더 직접적 경쟁. (ardestani-thesis-2026.md 참조)
