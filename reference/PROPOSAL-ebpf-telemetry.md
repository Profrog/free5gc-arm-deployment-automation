# 연구 계획서 (탐색/검증 단계) — eBPF 세분화 텔레메트리 방향

> **상태: DRAFT.** 메인 프레이밍 = **AI 중심 (자원-인지 NWDAF 운영 컨트롤러)**.
> 기존 "observer effect 측정 / drop 원인 귀속" 내용은 **환경·근거·Plan B**로 재배치됨.
> 2026-11-15 세션 결과물. 실험은 별도 세션 진행 중.

---

## ★★ 메인 프레이밍 (AI 중심) — Resource-Aware NWDAF Runtime Orchestration

### 제목(가제)
**"Resource-Aware NWDAF Runtime Orchestration on Constrained Edge: A Learning-Based Controller"**

### 연구 질문
> 자원제약 엣지(소규모 공장 ARM 소형 노드)에서 패킷코어와 공존하는 NWDAF를, 제한된 CPU
> 예산 안에서 **AI 에이전트가 런타임에 어떻게 운영(언제 어떤 모듈을 켤지)**해야, 관측이
> UPF를 잠식(observer effect)하지 않으면서 탐지 성능을 유지하는가? 학습 정책이 고정 정책
> (always-on/off/fixed)을 trade-off(탐지 vs 잠식)에서 이기는가?

핵심: **배치(placement)가 아니라 운영(runtime control)**. "언제 어떤 모듈을 켜고 끌지"를
상태 기반으로 학습하는 **adaptive controller**가 주인공.

### 문제 정형화 (MDP / Bandit)
- **State**: UPF CPU 사용률, 트래픽 특성(pps/패킷크기), 최근 drop(reason 분포 포함),
  각 NWDAF 모듈 현재 on/off, 마지막 관측 이후 경과시간.
- **Action**: NWDAF 모듈별 on/off 조합 {SBI 수집, AnLF 추론, MTLF 학습, MLMPS} (또는 수집주기 레벨).
- **Reward**: `탐지이익(F1류) − λ·UPF잠식비용 − μ·전환비용(flapping)`.
- **학습**: 고정규칙 / 지도학습(상태→on/off) / RL(Bandit·DQN·PPO) **비교 + ablation**.

### 환경 정의 (= observer effect + 모듈 분해, 이제 "환경"으로 강등)
- **observer effect**: 포화 시 관측이 UPF 처리량을 잠식(예비 실측 −10.4%) → reward의 비용항.
- **모듈별 부담 상이**: MLMPS가 무겁다(Ardestani 관찰) 등 → action 공간을 모듈별로 구성하는 근거.
- → 둘 다 "AI 문제를 성립시키는 환경"이지 메인 기여가 아님. (메인은 학습 컨트롤러.)

### 평가 (AI 실험 설계)
| 전략 | 설명 | 역할 |
|------|------|------|
| Always-on | NWDAF 항상 켜기 | baseline (Waterloo 기본 가정) |
| Always-off | 관측 없음 | baseline (잠식 0, 가시성 0) |
| Fixed-interval | 고정 주기 | baseline (현업 관행) |
| Supervised | 상태→on/off 분류 | 학습 비교군 |
| **RL (제안)** | 순차 비용-인지 제어 | **본 연구** |

- **지표**: 탐지성능(F1) vs UPF 잠식비용 **Pareto**, flapping 횟수, 반응지연.
- **ablation**: 상태표현(모듈분해 유무), 보상(비용항 유무), feature(drop reason 유무) → **기여 분리**.
- **성공 기준**: 학습 정책이 Pareto에서 고정 정책들을 지배(탐지 유지하며 잠식↓).

### RADAR와 선긋기 (방법 축)
RADAR(2609.31292)=마이크로서비스 trace sampling, **collector 비용** 절감, **stateless Bandit**,
entropy 보상. 본 연구=**5G NWDAF 모듈 운영**, **관측 대상(UPF) 잠식(observer effect)** 비용,
**상태 기반(MDP)**, 탐지 vs 잠식 보상. → 대상·비용의 본질·상태성이 다름.
(RADAR future work가 "cluster 상태 포함 MDP 확장"을 지목 → 우리가 그 방향.)

### NWDAF closed-loop 비용 지형 + 조사 순서 (누적 비용 안전망)

observer effect를 "수집"만이 아니라 **closed-loop 전 단계의 비용**으로 본다. 단일 비용원이
작아도 **누적하면 제약 노드에서 유의**해질 수 있다 → 단계적으로 쌓아가며 확인.

| 순서 | 비용원 | 내용 | 측정 포인트 |
|:---:|------|------|------------|
| **①** | **수집(관측)** | UPF EES/eBPF hot path 훅 + SBI 수신·저장 | **최우선**. 예비 −10% 확인됨 |
| **②** | **분석** | AnLF 추론 + MLMPS 모델 서빙 (Ardestani: CPU 50%+) | ①로 부족하면 추가 |
| **③** | **NF 간 통신** | NWDAF↔SMF/PCF/NRF SBI 구독·알림 (inter-NF signaling) | 멀티 NF 환경 필요 |
| **④** | **집행(action)** | SMF/PCF가 PFCP/QER로 UPF 직접 개입 (intervention effect) | UPF hot path 직접 건드림 → 잠식 큼 |

**조사 원칙 (당신 전략)**: ①부터 측정 → **효과(잠식)가 유의하면 그 선에서 성립**, 약하면 ②③④를
순차 누적하여 **"closed-loop 전체 누적 비용이 유의한가"**로 확장. 어느 단계든 누적 비용이 제약
노드에서 유의하면 **최소한 measurement 논문은 성립**(Plan B의 강화판).

- **①②가 1차 범위** (수집/분석) — 깔끔, 검증됨, 멀티NF 불필요.
- **③④는 2차/확장** — 멀티 NF + SMF/PCF 집행 구현 필요(현재 free5GC 미배포). future work 또는
  2차 실험. 특히 ④는 "고치려는 action이 자원을 더 잠식한다"는 **intervention effect** → AI가
  "관측 조절"뿐 아니라 "**개입 여부/빈도**"까지 비용-인지 결정하는 확장 각도.
- **AI action 공간 확장 근거**: on/off(수집) → 관측 수준 → (2차) 집행 빈도까지. 비용 모델이
  다차원(①~④)이 될수록 trade-off가 풍부 → 학습 당위성↑.

### de-risking (Plan A/B)
- **Plan A (메인, 방법 기여)**: 학습 컨트롤러가 고정 대비 우위 (C6). 성공 시 AI 프로젝트로 강함.
- **Plan B (measurement 기여)**: C6 실패 시 → observer effect 실측 + NWDAF 모듈별 잠식 분해 +
  소형 자원 운영 가이드라인 (아래 측정 내용). C6 실패해도 논문 성립.
- **공통 생명줄**: trade-off 실재 = observer effect(−10%, 확인) + 문제 간헐성(실험에서 설계/확인).
  always-on/off가 둘 다 지는 구간이 충분히 넓어야 Plan A 성립 ← 실험 1순위.

### 이직(대기업 AI) 관점 메모
- 면접 스토리: "부분 관측 하 비용-인지 제어를 RL로 정형화, 지도/RL 비교 + ablation, 고정 대비
  Pareto 우위" = 명확한 AI 결과물.
- 주의: trade-off 부재 시 "모든 모델이 고정 못 이김"이 되므로, **문제를 trade-off가 확실한
  시나리오로 설계**하는 게 선결(문제 빈도·심각도 통제).

---

> ───── 이하는 환경·근거·Plan B 재료 (measurement 내용). 메인은 위 AI 프레이밍. ─────

---

## 선행연구 링크 (빠른 참조)

| # | 논문 | Abstract / HTML / PDF |
|---|------|----------------------|
| 1 | **Kestrel** — Fine-Grained Anomaly Detection in 5G User Planes (2025-10-31) | abs: https://arxiv.org/abs/2510.27664 · html: https://arxiv.org/html/2510.27664 · pdf: https://arxiv.org/pdf/2510.27664 |
| 2 | **NWDAF Closed-Loop Automation** (NOMS 2026) | abs: https://arxiv.org/abs/2505.06789 · html: https://ar5iv.labs.arxiv.org/html/2505.06789 · pdf: https://arxiv.org/pdf/2505.06789 |
| 3 | **Ardestani 석사논문** — From User-Plane Telemetry to Closed-Loop Control (2026) | 전문: https://dspacemainprd01.lib.uwaterloo.ca/server/api/core/bitstreams/f8d6cf18-1c71-4fa5-8436-aa605e19a6e6/content |
| 4 | **RADAR** — RL+entropy adaptive trace sampling (microservices) | abs: https://arxiv.org/abs/2609.31292 · html: https://arxiv.org/html/2609.31292 |

- **코드 (Waterloo, Open5GS 기반)**: https://github.com/fatemeshafiee/closed-loop-nwdaf
- 석사논문 요약/틈분석: `reference/related-work/ardestani-thesis-2026.md` (knowledge 인덱싱됨)
- 추가 경쟁/유사: 2611.11372(LLM+DRL UPF selection), 2507.17843(NWDAF edge gaming), 2505.13160(eBPF QoS 진단), 2603.27618(Serverless5GC)

---

## 한 줄 요약 (구 drop-원인 방향 — 참고용, 메인 아님)

자원제약 **소프트웨어** UPF(eBPF/virtio, 가속 불가 엣지)에서, 집계 메트릭이 가리는
**경로별 packet drop 원인**(NIC ring / backlog / qdisc / socket / CNI)을 eBPF로
분해하고, 이 세분화 신호를 NWDAF(커스텀 AnLF)가 소비하여 **세션 관리 액션**(무중단

---

## ★ 방향 피벗 (2026-11-15 오후): Observer Effect 기반 adaptive NWDAF on/off

위 "drop 원인 귀속" 방향은 Kestrel/Ardestani(Waterloo)와 틈이 좁다는 결론(아래 분석).
탐색 끝에 **Waterloo 전제를 뒤집는** 다음 방향으로 피벗 검토 중:

> **자원제약 엣지에서 NWDAF/텔레메트리 관측은 공짜가 아니다 — 포화 상태에서 관측이
> UPF(또는 포워딩 노드)의 처리 성능을 잠식한다(observer effect). 따라서 always-on이
> 아니라, 관측의 이익(가시성) vs 손해(UPF 잠식)를 따져 on/off를 적응적으로 결정해야
> 한다. 문제가 불규칙하게 섞인 테스트셋에서 탐지성능(F1류) vs 잠식비용을 Always-on /
> Always-off / Adaptive(학습) 로 비교한다.**

- Waterloo 전제("UPF EES 오버헤드 미미, +6.5%")를 **제약 엣지에서 반증** → 그늘 벗어남.
- RADAR(마이크로서비스 trace sampling)와 구별: RADAR는 **collector 자원** 절감, 우리는
  **관측 대상(UPF) 잠식(observer effect)** + 5G UPF + 상태기반 on/off(RADAR future work).
- observer effect 논문(2406.09093)은 분석 프레임만, 5G UPF 실측·제어는 아무도 안 함.

### 예비 측정 (대체 측정, 2026-11-15) — observer effect 실재 확인

cpu0 포화 상태(UDP flood, 단일코어 100%)에서 eBPF류 관측(perf skb:kfree_skb -a) on/off의
**실제 처리량(work done)** 비교:

| 상태 | cpu0 처리량 (10s) |
|------|------------------|
| 관측 OFF | 평균 1,204,841 |
| 관측 ON | 평균 1,079,459 |
| **잠식** | **−10.4%** |

- **포화 상태에서만** 나타남 (여유/loopback 비포화에선 0% — 차이 없음).
- 관측 ON의 분산 큼(drop 양에 비례) → **부하↑ → 잠식↑ 비선형** 단서.
- ⚠️ **한계**: loopback+perf 대체 측정. 진짜 gtp5g UPF + eBPF(CO-RE)에서 재확인 필요.
  관측 방식(perf vs eBPF vs 수집주기)에 따라 잠식 크기 달라짐 → 그 자체가 연구 변수.

### Scope 명시 — "포화 근처"에서 성립

- observer effect는 **CPU가 포화에 가까운 구간에서만 유의**하다(여유 구간엔 거의 0).
- 따라서 연구의 valid scope = **"자원제약 + 포화가 자주/빠르게 발생하는 엣지"**.
  스마트팩토리 온프레미스(소수 COTS, 트래픽 급변으로 주기적 포화)가 대표 사례.
- 이는 **약점이 아니라 범위 정의**: "항상 성립"을 주장하지 않고 "포화 가능 제약 엣지에서
  always-on 전제가 깨짐"을 주장 → 반증 논리로 더 명확. 데이터센터 여유 환경은 scope 밖
  (거기선 Waterloo의 always-on이 맞음 — 우리가 그 경계를 규명).

### 대상 환경 및 플랫폼 정당화 (왜 소규모 공장 / 왜 ARM)

**대상 = 소규모 공장 / 중소기업(SME) private 5G의 저비용 소형 엣지 배포.**
- 대기업 데이터센터급이 아니라, 비용·전력·공간이 제약된 소형 온프레미스 배포를 겨냥.
- 근거: private 5G가 CBRS·저가 HW·구독형(Hitachi/AWS/MS 장비 저가 제공)으로 **중소기업에도
  접근 가능**해짐(metrowireless, netmanias). SME digital sovereignty + 로컬 AI가 mini/micro
  server 엣지 시장을 견인(Alibaba mini-server). → 4코어급 소형 노드는 이 배포의 하단에 실재
  (Intel/Dell Xeon D-2700도 4~20코어). "작다"가 약점이 아니라 **타겟 조건**.

**왜 ARM (톤: 저렴함 자체보다 저전력·저비용 엣지 적합성).**
- 소규모 엣지는 전력·공간·운영비가 제약된다. ARM 엣지 플랫폼(Ampere Altra/Neoverse)은
  **perf/watt 및 TCO 이점**(ARM 공식: perf/watt 2~3.5배)으로 이런 **저전력·저비용 소형 배포에
  적합**하며, 데이터센터 밖 엣지를 위해 설계됨(boston.co.uk: 45W TDP 엣지 서버). 산업 엣지
  채택 사례도 존재(Ampere edge 솔루션; ARM TrustZone Industry 4.0 게이트웨이, arXiv 2410.02529).
- **본 testbed = Oracle OCI Ampere A1 = ARM Neoverse-N1** → 임의 선택이 아니라 실제 ARM 엣지
  인프라 등급을 실험적으로 대리한다.
- **ARM vs x86**: 지금까지 측정에서 아키텍처 고유 이슈 없음. observer effect는 "포화 시 관측이
  CPU를 경쟁 소비"라는 **아키텍처 무관 메커니즘**이라 x86에도 전이될 것으로 기대(단 정량치는
  플랫폼별로 다를 수 있음 — 한계로 명시).

### 논문 축 (메인/배경)

- **메인 기여 (B)**: observer effect(관측이 UPF를 잠식) → always-on 전제 반증 → **adaptive
  on/off 필요성** 실증.
- **배경 (A)**: 저비용 ARM 소형 엣지에서 NWDAF 적용 가능성/오버헤드 특성화. A를 다루는 과정에서
  B를 핵심 기여로 도출. (단순 feasibility(A)만이면 약함 → B가 날카로운 주장.)

### NWDAF 모듈 분해 — 기여이자 Plan B의 핵심

Serverless5GC/PP5GS가 **control-plane NF를 쪼개** 유휴 자원 낭비를 줄인 것과 유사하게, 본 연구는
**NWDAF 자신을 모듈 단위로 분해 측정**한다. NWDAF는 기능이 여럿(SBI 수집 / AnLF 추론 / MTLF 학습 /
MLMPS)이고 모듈마다 자원 부담이 크게 다르다 — Ardestani thesis도 **MLMPS가 NWDAF CPU의 50%+**를
차지함을 관찰(단 x86 여유 환경, 독립 스케일 권고까지만). 아무도 **제약 ARM 소형 엣지에서 "어느 모듈이
UPF를 잠식하고(observer effect 주범), 무엇을 상시 켜고/끄고/오프로드해야 지속 가능한지"**를 실측
분해하지 않았다. → **공백.**

- 모듈 분해 기여: 각 모듈의 UPF 자원 잠식 프로파일 + observer effect 주범 식별 + 소형 자원 지속가능
  운영 가이드라인(상시/온디맨드/오프로드 분류).
- **adaptive와 연결**: 전체 on/off가 아니라 **모듈별 on/off**로 정밀화. 싼 모듈(SBI)을 상시 트리거로
  두고 비싼 모듈(MTLF/MLMPS)만 선택적 → "끄면 눈 먼다"는 순환 문제도 완화(2단 구조).
- 선행 선긋기: Serverless5GC=control NF 쪼개기, MLOps-NWDAF=AnLF/MTLF 분리+모델수명주기,
  Salhab(Boutaba ICC'20)=NWDAF 클라우드 오프로드. **우리=제약 엣지에서 NWDAF 모듈의 UPF 잠식
  실측 분해** (대상·목적 다름).

### 단계적 기여 구조 (de-risking / Plan A·B)

C6(adaptive가 고정을 이김)은 실험 전 미검증 → 실패 대비 **2단 안전장치**:

```
Level 1 (Plan B, measurement) : observer effect 실측 + NWDAF 모듈별 UPF 잠식 분해
                                 + 소형 자원 지속가능 운영 경계/가이드라인
                                 → Ardestani "오버헤드 미미"를 제약 엣지에서 반증/보정.
                                 → C6 실패해도 measurement 기여로 성립. 예비데이터(−10%) 있음.
Level 2 (Plan A, method)      : (모듈별) adaptive on/off가 Always-on/off 대비 우수
                                 → 탐지성능(F1류) vs 잠식비용 Pareto 비교. 성공 시 방법 기여.
```

- **Plan A/B 공통 생명줄 = observer effect가 실 UPF에서도 실재(C3)**. 예비(−10%)는 긍정,
  실 free5GC UPF 재확인이 결정적(다른 세션에서 진행 중). 이게 0이면 Level 1도 약화.
- 당신 최종 목적("소형 엣지에서 NWDAF 안정 구동")은 **Level 1과 일치** — "안정 구동 = 경계를
  알고 그 안에서/모듈별로 운영". 따라서 Plan B도 목적 달성.

---
자원 조정 / 원인별 대응 / 롤백 판단)까지 수행했을 때, 집계 메트릭 기반 기존 방식보다
세션 관리가 우수함을 end-to-end로 실증한다.

---

## 동기 (문제의식)

- 현재 UPF/NWDAF가 보는 메트릭은 **집계값**(loss%, cpu%, per-QFI 평균)이다. "loss 1%"는
  **어느 경로에서 왜 드롭됐는지**를 알려주지 않는다.
- 자원제약 엣지(4 vCPU, virtio_net, 가속 불가 — 본 testbed 실측)에서는 drop이 대부분
  **CNI 층이 아니라 그 아래**(softirq/backlog/ring overflow)에서 발생한다. 집계 메트릭은
  이 원인 경로를 구분하지 못한다.
- 같은 "1% drop"이라도 **원인 경로가 다르면 올바른 대응이 다르다**(예: ring overflow →
  버퍼/튜닝, CPU 경합 → 자원 조정, 버전 회귀 → 롤백). 집계만 보면 잘못된 대응을 하기 쉽다.
- 특히 스마트팩토리처럼 트래픽이 **소패킷(제어)↔대패킷(영상)으로 교차**하는 환경에서는,
  배포 시점/고정 설정의 "안전" 판정이 트래픽이 바뀌면 무효가 된다(static 결정의 조건부성).

---

## 연구 질문

> 자원제약 소프트웨어 UPF에서, **경로별 drop 원인을 분해한 세분화 메트릭**을 NWDAF가
> 소비하여 세션 관리 결정을 내리면, **집계 메트릭 기반 기존 방식(고정 임계 Rule / 표준
> per-QFI 카운터)보다 세션 관리가 실제로 우수한가?**

핵심은 "메트릭을 더 잘게 쪼갠다"가 아니라 **"세분화 메트릭 → NWDAF 판단 → 세션관리
액션의 end-to-end가 집계 기반보다 낫다"**를 실증하는 것이다.

---

## 기여 (목표)

1. **소프트웨어 UPF 경로별 drop 귀속 계측(eBPF)**: virtio/커널 데이터패스에서 drop이
   발생하는 지점(ring / backlog / qdisc / socket / CNI)을 eBPF로 분해하는 경량 계측.
2. **세분화 메트릭의 NWDAF 통합**: 분해된 고차원 신호를 feature로 쓰는 커스텀 AnLF가
   drop 원인을 분류/귀속하고, 원인별 세션관리 액션으로 연결(인프라 집행).
3. **end-to-end 우수성 실증(ablation)**: 집계 vs 세분화 × 규칙 vs AI 의 2×2 비교로
   "세분화의 기여"와 "AI의 기여"를 분리 증명.

---

## 선행연구 및 틈 (정직한 포지셔닝)

가장 가까운 선행은 **Waterloo(Boutaba 랩)** 그룹이며, 이 공간을 체계적으로 선점 중이다.
진행 전 반드시 아래 3개 문서를 정독하여 틈을 재확인해야 한다.

### 반드시 읽을 선행 문서 (링크)

1. **Kestrel — Fine-Grained Anomaly Detection in 5G User Planes (2025-10-31)**
   - abstract: https://arxiv.org/abs/2510.27664
   - HTML: https://arxiv.org/html/2510.27664
   - 저자: Niloy Saha, Noura Limam, Yang Xiao, Raouf Boutaba (University of Waterloo)
   - **한 것**: UPF에서 집계(per-QFI)는 transient/per-flow 이상을 가린다는 문제제기 →
     per-TEID 분포(latency tail, IAT) 세분화 메트릭을 sketch로 생성 → XGBoost 이상탐지 →
     **3GPP-PM(집계) 대비 2배 정확도**. **Tofino/P4 하드웨어** 데이터플레인.

2. **Towards NWDAF-enabled Analytics and Closed-Loop Automation (NOMS 2026)**
   - abstract: https://arxiv.org/abs/2505.06789
   - HTML: https://ar5iv.labs.arxiv.org/html/2505.06789
   - 저자: F. S. Ardestani, N. Saha, N. Limam, R. Boutaba (Waterloo)
   - **한 것**: 3GPP 준수 UPF event exposure + MLflow 모델 제공 + **SMF가 NWDAF analytics를
     소비하도록 개조**한 end-to-end closed-loop (보안/bot 관리).

3. **석사논문: From User-Plane Telemetry to Closed-Loop Control (Ardestani, 2026) ★핵심**
   - https://dspacemainprd01.lib.uwaterloo.ca/server/api/core/bitstreams/f8d6cf18-1c71-4fa5-8436-aa605e19a6e6/content
   - 위 2편을 묶은 thesis. **Conclusion/Future Work 장에서 "안 했다"고 적은 부분이 곧
     우리의 후보 틈.** (다음 작업: 이 장을 정밀 추출)

### 선행이 이미 한 것 vs 남은 틈

| 축 | Kestrel / Waterloo | 본 방향(후보 틈) |
|----|-------------------|-----------------|
| 플랫폼 | **하드웨어(Tofino/P4)** | **소프트웨어 데이터플레인(eBPF/virtio)** ← Kestrel이 future work로 지목 |
| 세분화 대상 | latency/IAT 분포(큐 단위) | **경로별 drop 원인**(ring/backlog/qdisc/socket/CNI) — Kestrel은 drop 경로 분해 안 함 |
| 환경 | 데이터센터급 라인레이트 | **자원제약 엣지**(4 vCPU, 가속 불가, CPU 병목) |
| 폐루프 | 탐지까지(action 약함) | **탐지 → NWDAF → 세션관리 액션**까지 end-to-end |
| 목적 | QoS 이상 탐지 | **{CPU 경합·drop 원인} 기반 세션관리 개선** |

→ **남은 틈 = "소프트웨어 UPF(eBPF) + drop 원인 경로 분해 + 자원제약 엣지 + NWDAF
세션관리 액션까지 end-to-end".** Kestrel이 명시적으로 안 했고, 스스로 future work로
지목한 영역.

### Ardestani 석사논문 정독 결과 (Q4 — 틈 확정, 2026-11-15)

thesis 전문 확보 → `related-work/ardestani-thesis-2026.md`에 정리(knowledge 인덱싱됨).

**그들이 이미 한 것(중복 주의)**: free5GC 아닌 **Open5GS** 위에서 NWDAF closed-loop
end-to-end(수집→분석→집행), UPF EES 표준 데이터 수집+오버헤드 실측, ML 수명주기(MLflow),
SMF(session release)/PCF(rate 조정) 집행, congestion을 delay/loss로 판정+confidence heuristic.

**Table 2.1이 드러낸 빈칸**: free5GC 기반 연구([14],[20])는 **UPF EES·ML Lifecycle·
Closed-Loop 전부 ✗**. 즉 **free5GC + closed-loop 집행은 비어 있음.**

**thesis Future Work가 명시적으로 연 문(= 우리 틈의 공식 근거)**:
- FW#2: "Chapter 5의 **heuristic rate 조정을 learning-based로 교체**하면 non-stationary
  트래픽을 더 잘 다룰 수 있다" → **우리 학습 기반 판단과 정확히 연결.**
- FW#3: "PCF·SMF를 **독립적으로** 연구했고, 여러 NF가 동시에 집행할 때의 **조율은 미해결**"
  → 멀티 NF race 조율 여지.
- 그들의 UPF EES는 **표준 이벤트 노출이지 drop 경로 분해가 아님**(drop은 egress 전송실패
  카운트 수준). → **"경로별 drop 원인 귀속"은 EES에 없는 차원.**

### 리스크 (정직하게)

- **틈이 좁다**: "세분화가 집계보다 낫다"는 Kestrel(2510.27664)이 이미 보였으므로,
  novelty 무게중심을 **"drop 원인 경로 분해 + 학습 기반 판단 + 세션관리 액션"**에 두지
  않으면 중복으로 보인다. (단순 세분화 일반 X)
- **경쟁 그룹**: Waterloo(Boutaba 랩)가 Open5GS 기반으로 이 공간을 빠르게 선점 중.
  코드 공개(github.com/fatemeshafiee/closed-loop-nwdaf). → 우리는 **free5GC + eBPF +
  자원제약 엣지 + drop 경로귀속**으로 선 긋기.
- **application novelty 성격**: 새 메커니즘보다 "기존 방법을 소프트웨어·엣지·액션으로 확장".
  단, FW#2/#3을 정면으로 인용해 "그들이 남긴 과제를 푼다"로 포지셔닝하면 방어력 상승.

---

## 진행 전 결판낼 질문 (Q1~Q4)

| # | 질문 | 확인 방법 | 상태 |
|---|------|----------|------|
| Q1 | 집계 메트릭이 실제로 drop 원인을 못 가려 **오대응**을 유발하는가 | 측정 | ❓ |
| Q2 | 트래픽 교차 시 "올바른 대응"이 조건별로 달라지는가(trade-off 실재) | 측정 | ❓ |
| Q3 | virtio/gtp5g 데이터패스에서 **경로별 drop을 eBPF로 분해** 가능한가 | PoC | ❓ |
| Q4 | Kestrel/Waterloo 대비 틈이 방어 가능한가(석사논문 future work 확인) | 문헌 | ⚠️ 부분확인 |

> Q3(eBPF 계측 PoC)와 Q4(석사논문 정독)가 1순위. 둘 중 하나라도 막히면 방향 재검토.

---

## 환경 전제 (기존 testbed 재사용, PROPOSAL.md와 공유)

- aarch64 Neoverse-N1, 4 vCPU, virtio_net(SR-IOV VF 미지원), HugePages 0, 단일 노드.
- cgroup v2, containerd 2.2.1, K8s v1.32.3 (In-place Pod Resize는 alpha — feature gate
  필요, 또는 1.33+ 업그레이드 시 GA).
- 기존 자산 재사용: Multus/CNI 측정 환경, NWDAF 커스텀 엔진(`arm_k8s/nwdaf/`),
  gating/sens 실측 데이터(softirq/backlog/time_squeeze 포함).

---

## 시스템 설계 (초안)

```
① eBPF 세분화 계측 (경로별 drop: ring/backlog/qdisc/socket/CNI)   ← 수단(AI 아님, 토대)
        │
② NWDAF 커스텀 AnLF: 세분화 feature → drop 원인 분류/귀속 (지도학습)
        │
③ 세션관리 액션: 원인별 대응 (무중단 자원조정 / 튜닝 / 롤백 판단)   ← 인프라 집행
        │
④ 검증: 집계 메트릭 기반 대비 end-to-end 우수성
```

### 검증 구도 (2×2 ablation)

| 전략 | 메트릭 | 판정 | 역할 |
|------|--------|------|------|
| A | 집계(loss%, cpu%) | 규칙(임계) | baseline |
| B | 집계 | AI | 메트릭 효과 통제 |
| C | **세분화(eBPF)** | 규칙 | AI 효과 통제 |
| D | **세분화** | **AI** | **본 연구 제안** |

- D vs A: 전체 개선 / D vs B: 세분화 메트릭 기여 / D vs C: AI 기여.
- 평가지표(후보): drop 원인 귀속 정확도, 오탐/미탐률, 세션 QoS 회복속도, 불필요 액션 수.

### 방법 선택 메모 (지도학습 vs RL)

- 핵심은 **attribution(원인 분류/판별)** → 지도학습이 자연스럽다. 실측 데이터로 라벨 가능,
  sim-to-real gap 없음. 2611.11372(LLM+DRL UPF selection, 합성 메트릭)와의 차별점도 됨.
- RL은 "세션 누적 동역학 장기 최적화" 같은 **다른 문제**일 때만. 현재 아이디어엔 과함.

---

## 다음 작업 (TODO)

1. **Q4**: 석사논문(링크 3) Conclusion/Future Work 정밀 추출 → 틈 확정, Kestrel과 선긋기.
2. **Q3**: gtp5g/virtio 데이터패스에서 eBPF 경로별 drop 계측 PoC (softnet_stat, kfree_skb
   추적, ethtool ring stats 등).
3. **Q1/Q2**: 트래픽 소↔대 교차 시 (a)집계가 원인을 못 가리는 사례, (b)조건별 최적 대응이
   갈리는 trade-off를 기존 gating/sens 데이터 재분석 + 소규모 재측정으로 확인.
4. 위가 긍정적이면 → 정식 PROPOSAL로 승격, novelty 무게중심을 "drop 경로분해 + 세션관리
   액션"으로 확정.

---

## 부록 — 2026-11-15 아이디어 탐색에서 기각/보류한 방향 (재방문 방지용)

| 방향 | 기각/보류 사유 |
|------|---------------|
| CNI 전환(ipvlan/macvlan) | 부하 시 ipvlan 거의 항상 우세 → 교차(trade-off) 약함. 데이터가 전제 불충족 |
| sysctl 튜닝 선택 | budget_hi가 거의 항상 최적 → 교차 약함 |
| UPF 세션 라우팅(SMF) | free5GC SMF는 정적 선택+경로 캐싱(동적 재선택 없음); 선행 많음(2611.11372 등) |
| 드라이버 교체 집행 | virtio 고정, 대체 드라이버 없음 → 환경적 불가 |
| XDP/eBPF 가속 | 레드오션; AI 자리 모호 |
| 리소스 거버넌스(in-place resize) | VPA/오토스케일링 레드오션; gap 좁음(1.33가 stateful 겨냥) |
| 특화 Pod hot standby 전환 | UPF 세션 상태 이전 불가(hot라도 세션 cold) → 무중단 깨짐 |
| ULCL 분기 | 표준 교과서 용례 + 특허 존재 → novelty 약함 |
| Flux/GitOps 엮기 | Flagger/continuous verification이 이미 함; 느린 루프라 런타임 적응과 미스매치 |
| 롤백=인과진단(active probe) | 아이디어 신선하나 프로덕션 진단롤백 위험 + 트래픽 비통제성; 보류 |

> 공통 교훈: 대부분의 방향이 두 벽에 부딪힘 — (1) 5G+AI+UPF 공간 포화(novelty),
> (2) 4 vCPU 포화 testbed가 "조건별 최적이 바뀌는 trade-off"를 잘 안 만듦(Q2).
> eBPF 세분화 방향은 (2)를 우회(측정/방법론 기여)한다는 점에서 상대적으로 유리.
