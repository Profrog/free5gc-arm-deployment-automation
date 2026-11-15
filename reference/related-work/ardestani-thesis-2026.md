# From User-Plane Telemetry to Closed-Loop Control: NWDAF-Enabled Automation in 5G Networks

**저자**: Fatemeh Shafiei Ardestani (Master of Mathematics, University of Waterloo, 2026)
**지도교수**: Raouf Boutaba
**관련 논문**:
- F. S. Ardestani, N. Saha, N. Limam, R. Boutaba, "Towards NWDAF-enabled Analytics and Closed-Loop Automation in 5G Networks," IEEE/IFIP NOMS 2026. (arXiv:2505.06789)
- F. S. Ardestani, N. Limam, R. Boutaba, "Towards Zero-Touch Network Orchestration: A NWDAF-Centered Standards-Compliant Closed-Loop Approach," ITU Journal (under review).
**코드**: https://github.com/fatemeshafiee/closed-loop-nwdaf

> 본 파일은 thesis 전문(사용자 제공)을 related-work 레퍼런스로 보관한 것.
> 우리 연구(PROPOSAL-ebpf-telemetry.md)와의 관계 분석은 문서 하단 "우리 연구와의 관계" 참조.

---

## 핵심 요약 (우리 관점)

- **코어**: Open5GS (C 기반 UPF 확장). free5GC 아님.
- **데이터 수집**: 3GPP 표준 **UPF Event Exposure Service(EES)**를 C로 구현(최초). per-flow/
  per-session 단위 volume/throughput/QoS(delay, loss) 노출. lock-free SPSC ring buffer로
  hot path 영향 최소화. 오버헤드: 1 subscriber, 1000Mbps에서 one-way delay +0.11ms, CPU +6.5% 미만.
- **분석**: 모듈형 NWDAF (OAI NWDAF 코드베이스 기반). AnLF 엔진 + **ML Model Provision
  Service(MLMPS, MLflow 통합)**로 모델 수명주기 관리.
- **집행(closed-loop)**: 2개 use case
  - (i) **SMF 기반**: bot 탐지(graph feature + Random Forest) → 이상 UE의 **PDU session release**
  - (ii) **PCF 기반**: 혼잡(delay/loss) 분석 → **AMBR/MBR rate 조정**(token-bucket, heuristic),
    GBR flow 보호 (PDU session release보다 덜 파괴적)
- **평가**: end-to-end 응답시간(수집→탐지→집행), 수집주기 vs 탐지지연 trade-off, GBR 보호 효과.

---

## Table 2.1 — NWDAF 구현 비교 (thesis)

| Ref | Core | UPF EES | ML Lifecycle | Closed-Loop | Focus |
|-----|------|:---:|:---:|:---:|-------|
| [16] Chouman | Open5GS | ✗ | ✗ | ✗ | Control-plane packet statistics |
| [24] Manias | Open5GS | ✗ | ✗ | ✗ | NF interaction clustering |
| [14] Bayleyegn | **free5GC** | ✗ | ✗ | ✗ | Performance prediction |
| [9] Abbas | OAI EPC | ✗ | ✗ | ✗ | Slice scaling, DDoS mitigation |
| [29] Peters | Open5GS | ✗ | ✗ | ✗ | Abnormal UE throughput/sessions |
| [25] Mekrache | OAI 5GC | ✓* (SMF relay) | ✗ | ✗ | Flow-level anomaly detection |
| [20] Daniel | **free5GC** | ✗ | ✗ | ✗ | AMF/SMF event exposure; mobility prediction |
| [27] Nadar | OAI 5GC | ✗ | ✓ | ✗ | Ontology-based ML model provisioning |
| **Ours (Ardestani)** | Open5GS | **✓** | **✓** | **✓** | Closed-loop network orchestration |

✓* = partial (SMF relay로 UPF 데이터 간접 수집).

---

## Future Work (thesis Chapter 7) — 우리 틈의 근거

thesis가 명시적으로 "안 했다 / 향후 과제"로 남긴 것:

1. **UPF EES delay가 UPF-내부 delay에 한정** — RAN-side 포함 end-to-end delay는 future work.
2. **Chapter 5의 rate 조정이 heuristic** — "학습 기반(learning-based) 접근으로 교체하면
   non-stationary 트래픽을 더 잘 다룰 수 있다"를 future work로 명시. ← **우리 ML attribution과 연결점**
3. **PCF와 SMF 집행을 각각 독립적으로 연구** — 여러 NF가 **동시에** NWDAF analytics를
   소비·집행할 때의 **충돌/조율(orchestration) 로직은 미해결**, future work. ← **멀티 NF race 관련**
4. 프레임워크를 추가 use case/집행 전략으로 확장 가능(개방형).

---

## 우리 연구(PROPOSAL-ebpf-telemetry)와의 관계 — 틈 분석

### 그들이 이미 한 것 (중복 주의)
- NWDAF closed-loop end-to-end (수집→분석→집행) 구현 ✓
- UPF EES 표준 데이터 수집 + 오버헤드 실측 ✓
- ML 수명주기(MLMPS) ✓
- SMF(session release) / PCF(rate 조정) 집행 ✓
- congestion을 delay/loss로 판정 + confidence 기반 heuristic 집행 ✓

### 그들이 안 한 것 (우리 틈)
| 축 | Ardestani thesis | 우리 틈 |
|----|-----------------|--------|
| 코어 | **Open5GS** | **free5GC** (free5GC closed-loop은 Table 2.1에서 빈칸) |
| 메트릭 성격 | UPF EES 표준값(volume/throughput/delay/loss) = **집계/플로우 단위** | **경로별 drop 원인 분해**(ring/backlog/qdisc/socket/CNI) — EES에 없는 차원 |
| 계측 기술 | UPF 소스에 C 계측 삽입 | **eBPF 커널 경로 계측** |
| drop 귀속 | egress 전송실패 카운트(방향별), per-user 귀속 안 함 | **drop 발생 경로/원인 귀속** |
| 환경 | 데이터센터급(자원 넉넉, UPF를 일부러 제약해 실험) | **가속 불가 자원제약 엣지(virtio, 4vCPU) 자체가 제약** |
| 집행 판단 | **heuristic** (confidence×congestion 매핑) | **학습 기반**(그들 future work #2가 정확히 지목) |
| 멀티 NF | 독립 연구(조율 미해결, future work #3) | (선택적) race 조율 |

### 핵심 결론
- **우리 틈 = "free5GC + eBPF 경로별 drop 원인 분해 메트릭 + 학습 기반 판단 + 자원제약 엣지"**
- 특히 thesis Future Work #2("heuristic을 learning-based로")와 #3("멀티 NF 조율")가
  우리가 비집고 들어갈 **공식적으로 열린 문**이다.
- **주의**: 그들의 UPF EES는 "표준 이벤트 노출"이고 **drop 경로 분해가 아님.** 우리 novelty는
  "세분화" 일반이 아니라 **"drop 원인 경로 귀속"**이라는 EES에 없는 차원에 둬야 함.
  (단순 "세분화 > 집계"는 Kestrel(2510.27664)이 이미 보였으므로 그쪽과도 선 그어야 함.)
- **경쟁 리스크**: Boutaba 랩(Waterloo)이 Open5GS 기반으로 이 공간을 빠르게 선점 중.
  코드도 공개(github.com/fatemeshafiee/closed-loop-nwdaf). 우리는 free5GC + eBPF + 엣지로 차별화.
