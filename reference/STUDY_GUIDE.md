# 배경지식 학습 자료 (ML / 네트워크 기초)

논문 심사 및 면접 대비 — 본 연구에서 사용된 개념들의 기초 학습 자료.

연구 계획서: [`PROPOSAL.md`](PROPOSAL.md)

---

## 1. Random Forest (핵심 ML 모델)

### 이해해야 할 것
- Decision Tree가 뭔지 → 여러 개 모아서 투표 = Random Forest
- 왜 단일 트리보다 좋은지 (과적합 방지, 분산 감소)
- feature importance가 뭔지 (어떤 입력이 판단에 가장 중요한가)
- **본 연구에서의 역할**: 트래픽 KPI를 보고 "지금 CNI 전환하면 이득인가?" 판단

### 학습 자료
| 자료 | 언어 | 수준 | 링크 |
|------|------|------|------|
| StatQuest - Random Forest | 영어 (직관적) | 입문 | https://www.youtube.com/watch?v=J4Wdy0Wc_xQ |
| 위키독스 - RF 실습 | 한국어 | 입문+코드 | https://wikidocs.net/42410 |
| sklearn 공식 문서 | 영어 | 중급 | https://scikit-learn.org/stable/modules/ensemble.html#forest |
| Breiman 2001 원논문 | 영어 | 고급(참고만) | https://link.springer.com/article/10.1023/A:1010933404324 |

### 심사에서 나올 수 있는 질문
- "왜 Random Forest인가?" → 경량(ARM64 <1ms 추론), 해석 가능, 소규모 데이터 적합, NWDAF 학계 선례
- "overfitting 안 하나?" → max_depth 제한, cross-validation, 학습/검증 패턴 분리
- "feature importance 어떻게 계산?" → 각 feature로 split했을 때 impurity 감소량 평균
- "왜 LSTM/XGBoost 안 썼나?" → 1차 연구는 RF로 feasibility 실증, 다중 모델 비교는 후속 연구

---

## 2. Cross-Validation (모델 검증)

### 이해해야 할 것
- 왜 train/test를 나누는지
- k-fold가 뭔지 (5-fold: 5번 나눠서 각각 테스트)
- accuracy, precision, recall, F1-score
- **본 연구 추가 메트릭**: Net Gain, False Positive Rate, Reaction Time

### 학습 자료
| 자료 | 링크 |
|------|------|
| StatQuest - Cross Validation | https://www.youtube.com/watch?v=fSytzGwwBVw |
| sklearn - Cross-validation | https://scikit-learn.org/stable/modules/cross_validation.html |

---

## 3. 전환 비용 모델 (Cost-Aware Decision)

### 이해해야 할 것
- Pod 재생성 = downtime 발생 → 그 동안 패킷 loss
- 전환 이득: macvlan로 바꾸면 throughput 증가
- 전환 비용: downtime 동안 받지 못한 데이터
- **판단 기준**: 전체 세션(120초)의 total bytes received로 평가
- 전환해서 이득인 경우 vs 전환하면 손해인 경우 (spike, oscillation)

### 본 연구의 평가 방식
```
점수 = 120초간 서버가 받은 total bytes

D(RF) > A(ipvlan 고정) → RF 전환이 이득
D(RF) > C(Rule-based) → ML이 Rule보다 나음
T3(spike)에서 HOLD → False Positive 억제 성공
```

### 심사에서 나올 수 있는 질문
- "전환 비용을 어떻게 측정?" → 별도 측정 불필요, total bytes에 자연 포함 (downtime=수신 0)
- "Rule-based 대비 RF의 장점은?" → spike/oscillation에서 FP 억제, 시계열 추세 학습

---

## 4. 네트워크 기초 (macvlan / ipvlan)

### 이해해야 할 것
- L2 (MAC) vs L3 (IP) 차이
- macvlan: 독립 MAC → NIC이 MAC으로 분배 → **대패킷에 유리** (offload 가능)
- ipvlan: MAC 공유 → 커널이 IP로 분배 → **소패킷에 유리** (per-packet overhead 낮음)
- **공정 비교의 중요성**: 물리 NIC에서 직접 분기해야 편향 없음

### 본 연구 핵심 발견
| 조건 | macvlan | ipvlan | 유리 |
|------|---------|--------|------|
| 소패킷 64B (high pps) | loss 2.64% | loss 2.42% | ipvlan |
| 대패킷 1400B (500Mbps) | loss 0.16% | loss 0.33% | macvlan |

→ 트래픽 특성에 따라 최적 CNI가 다름 = **동적 전환의 당위성**

### 학습 자료
| 자료 | 링크 |
|------|------|
| macvlan vs ipvlan 설명 (Bandewar 2015) | https://netdevconf.info/0.1/sessions/17.html |
| 컨테이너 네트워킹 시각화 | https://iximiuz.com/en/posts/container-networking-is-simple/ |
| IETF CNI Benchmarking draft | https://datatracker.ietf.org/doc/draft-samizadeh-bmwg-cni-benchmarking/ |

### 심사에서 나올 수 있는 질문
- "왜 ipvlan이 소패킷에서 유리?" → 커널 내부 L3 처리, MAC lookup 불필요, per-packet CPU cost 낮음
- "왜 macvlan이 대패킷에서 유리?" → NIC HW offload(TSO/GRO), multiqueue 활용
- "dual-bridge 편향이 뭔가?" → ipvlan이 veth pair를 추가 경유하면 불공정 → 물리 NIC 직접 분기로 해결

---

## 5. 5G Core 기초 (UPF, NWDAF, PFCP)

### 이해해야 할 것
- UPF = 데이터플레인 게이트웨이 (GTP-U encap/decap)
- NWDAF = AI/ML 분석 함수 (3GPP TS 23.288)
  - AnLF: 추론/판단 실행
  - MTLF: 모델 학습
- PFCP (TS 29.244): SMF↔UPF 제어 프로토콜
- **Pod 재생성 시**: PFCP session 재수립 필요 → 이것이 downtime의 일부

### 학습 자료
| 자료 | 링크 |
|------|------|
| 3GPP 5G 아키텍처 개요 | https://www.3gpp.org/technologies/5g-system-overview |
| free5gc 문서 | https://free5gc.org/guide/ |
| NWDAF 개요 (Ardestani 2025) | https://arxiv.org/abs/2505.06789 |

### 심사에서 나올 수 있는 질문
- "NWDAF가 직접 인프라를 바꿔도 되나?" → 3GPP scope 밖, operator-specific implementation, 표준 위반 아님
- "OAM 수집이면 표준 준수인가?" → TS 23.288에서 OAM은 공식 수집 경로 중 하나

---

## 6. Kubernetes + Pod lifecycle

### 이해해야 할 것
- Pod, Deployment, NetworkAttachmentDefinition (Multus)
- Pod 재생성 = CNI 변경의 유일한 공식 경로
- graceful termination → 새 Pod 생성 → readiness
- **전환 시간**: Pod 삭제~새 Pod ready까지 수 초~십수 초

### 학습 자료
| 자료 | 링크 |
|------|------|
| K8s Pod Lifecycle | https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/ |
| Multus CNI | https://github.com/k8snetworkplumbingwg/multus-cni |

---

## 7. 실험 방법론 (IETF BMWG)

### 이해해야 할 것
- 왜 5회 반복하는지 (통계적 유의성, 95% CI)
- CPU pinning이 왜 필요한지 (변수 격리)
- 동일 시간(120초) 통일이 왜 중요한지 (공정 비교)

### 심사에서 나올 수 있는 질문
- "단일 노드에서 일반화 가능?" → IETF BMWG 준수 + 통계 + Limitation 명시
- "왜 ARM?" → ARM에서 커널 경로 차이가 더 크게 관측 → 실험 민감도 향상

---

## 학습 우선순위 (심사 대비)

1. **학습 방식의 논리적 타당성** ← 아래 섹션 8 (가장 중요, 논문의 근본 질문)
2. **Random Forest + cost-aware 판단** ← 모델 + 핵심 로직 질문 필수
3. **macvlan vs ipvlan 커널 차이 + 공정 비교** ← 논문 핵심 발견
4. **전환 비용 모델 (total bytes 비교)** ← 평가 방법론
5. **5G UPF/NWDAF 역할** ← 기본 배경
6. **K8s Pod lifecycle + 실험 방법론** ← 구현/실험 질문 시

---

## 8. 학습 방식의 논리적 타당성 (★ 핵심)

### 본 연구의 학습 구조

```
[학습 단계]
  입력: 여러 트래픽 패턴에서 수집한 KPI (throughput, pps, loss, cpu, 추세)
  라벨: "이 시점에서 전환하면 이득이었는가?" (사후 oracle 판단)
  출력: RF 모델 → "SWITCH" or "HOLD" 판단 능력 습득

[추론 단계]
  실시간 KPI 관측 → RF가 "지금 전환하면 이득인가?" 판단 → 실행/보류
```

### 이게 논리적인가? — 검증해야 할 질문들

| # | 질문 | 답이 "예"여야 논리 성립 | 관련 학문 |
|---|------|----------------------|----------|
| 1 | ipvlan/macvlan 성능 차이가 트래픽 특성에 의존하는가? | ✅ 실험으로 확인 (소패킷: ipvlan, 대패킷: macvlan) | 커널 네트워킹 |
| 2 | 현재 KPI로 "어떤 CNI가 더 나은지" 판별 가능한가? | throughput/pps로 패킷 크기 추정 가능 → 최적 CNI 추론 가능 | 통계/ML |
| 3 | "전환 이득 > 전환 비용"인 시점이 KPI에서 식별 가능한가? | 고부하 지속 여부를 추세(slope)로 추정 가능 | 시계열 분석 |
| 4 | RF가 이 판단을 학습할 수 있는가? | 비선형 결정 경계 + feature interaction 학습 가능 | ML 이론 |
| 5 | 학습 데이터(합성)가 실제 추론 환경과 충분히 유사한가? | 같은 구조 다른 파라미터 → 일반화 검증 필요 | ML 일반화 |

### 각 질문을 이해하기 위해 공부할 것

#### Q1: 왜 CNI 성능이 트래픽에 따라 다른가? (커널 네트워킹)

```
ipvlan 경로: 패킷 → 커널 netif_receive_skb → ip_rcv → L3 라우팅 → Pod
macvlan 경로: 패킷 → NIC MAC filter → macvlan_handle_frame → Pod (L3 skip)
```

- 소패킷(high pps): ipvlan의 L3 처리가 가벼움 (이미 커널 안에 있으니까 context switch 없음)
- 대패킷(high throughput): macvlan의 NIC offload(TSO/GRO)가 CPU 절약

**공부할 것:**
- Linux 커널 패킷 수신 경로 (NAPI, softirq)
- TSO/GRO/RSS 등 NIC offload 기술
- [Bandewar 2015 — IPVLAN: The Beginning](http://people.netfilter.org/pablo/netdev0.1/papers/IPVLAN-The-beginning.pdf)

#### Q2: KPI로 최적 CNI를 판별할 수 있는가? (통계/특징 공학)

```
핵심 insight:
  throughput_mbps / total_pps = 평균 패킷 크기 (암묵적으로 인코딩됨)
  
  평균 패킷 크기가 크면 → macvlan 유리
  평균 패킷 크기가 작으면 → ipvlan 유리
  
  RF는 이 비율 관계를 feature interaction으로 학습
```

**공부할 것:**
- Feature engineering (파생 feature, interaction)
- RF의 feature space 분할 방식 (decision boundary)
- 정보 이론 (mutual information: feature가 label에 대해 얼마나 정보를 주는가)

#### Q3: 전환 시점을 KPI 추세로 판단할 수 있는가? (시계열 분석)

```
문제: "지금 고부하가 앞으로도 지속될까?"
  → 답을 모르지만 추세(slope)로 추정 가능

throughput_slope > 0 (상승 중): 지속 가능성 높음 → 전환 이득 기대
throughput_slope ≈ 0 (안정): 이미 sustained → 전환 이득 확실
throughput_slope < 0 (하락 중): spike일 수 있음 → HOLD

loss_delta > 0 (악화 중): 현재 CNI 한계 도달 → 전환 시급
```

**공부할 것:**
- 시계열 기초 (추세, 계절성, 정상성)
- 이동 평균, 선형 회귀 기울기 (slope 계산법)
- Changepoint detection (패턴 변화 감지)
- [참고] CUSUM, Bayesian Online Changepoint Detection

#### Q4: RF가 이걸 학습할 수 있는가? (ML 이론)

```
RF의 능력:
  - 비선형 결정 경계 (throughput > X AND slope > Y → SWITCH)
  - Feature interaction (throughput/pps 비율 = 패킷 크기)
  - Robust to noise (ensemble 평균으로 노이즈 상쇄)
  
RF의 한계:
  - 시계열 순서 자체를 학습 못함 (각 샘플이 독립)
  - → 해결: slope, delta를 파생 feature로 넣어서 "순서 정보"를 feature로 인코딩
```

**공부할 것:**
- Decision Tree의 학습 원리 (Gini impurity, information gain)
- Ensemble 방법론 (bagging vs boosting)
- RF가 못하는 것: extrapolation, 순차 의존성
- 왜 시계열 feature(slope, delta)를 수동으로 넣어야 하는가

#### Q5: 합성 데이터로 학습해도 실환경에서 동작하는가? (일반화)

```
학습: 5종 합성 패턴 (노이즈 추가, 100 변형씩)
검증: 같은 구조 + 다른 파라미터의 실제 트래픽

일반화가 가능한 이유:
  - RF가 학습하는 건 "절대값"이 아니라 "패턴" (slope, delta의 부호/크기)
  - 패턴이 같으면 (급상승, spike 등) 구체적 수치가 달라도 판단 가능
  
일반화가 실패할 수 있는 경우:
  - 학습에 없는 완전히 새로운 패턴
  - 환경이 바뀌면 (다른 NIC, 다른 CPU) threshold가 달라짐
  → Limitation에 명시
```

**공부할 것:**
- Generalization theory (bias-variance tradeoff)
- Domain adaptation (학습 환경 ≠ 추론 환경일 때)
- Distribution shift 문제
- Sim-to-real transfer (시뮬레이션 → 실환경 전이)

---

### 이 구조의 유사 사례 (선행연구)

| 분야 | 학습 대상 | 판단 내용 | 유사점 |
|------|----------|----------|--------|
| O-RAN Near-RT RIC | 네트워크 KPI | 셀 간 핸드오버 타이밍 | KPI 기반 전환 시점 판단 |
| 클라우드 오토스케일링 | CPU/메모리 메트릭 | scale-out 타이밍 | 비용(새 VM) vs 이득(응답시간) tradeoff |
| 주식 매매 | 가격/거래량 시계열 | 매수/매도 타이밍 | 거래 비용 포함 최적 시점 |
| TCP 혼잡 제어 (ML 기반) | RTT, loss rate | cwnd 조절 타이밍 | 네트워크 상태 → 파라미터 변경 |

### 심사에서 나올 수 있는 질문

- "KPI만 보고 미래를 예측하는 건 무리 아닌가?"
  → 예측이 아니라 **현재 추세의 지속 가능성 판단**. slope이 양이고 안정적이면 sustained일 확률 높음.

- "왜 단순 threshold 안 쓰고 RF를 쓰나?"
  → threshold는 spike에 속음 (FP). RF는 slope+delta를 종합해서 "일시적 vs 지속적" 구분.

- "합성 데이터로 학습하면 실환경에서 안 될 수 있지 않나?"
  → feature가 "절대값"이 아닌 "패턴"(상승/하락/안정)을 인코딩하므로, 수치가 달라도 패턴이 같으면 동작. 검증 셋으로 확인.

- "이 접근이 실제로 동작한다는 보장은?"
  → 그래서 실험으로 검증. D(RF) > A(고정)이면 동작하는 것. 이론적 보장이 아닌 실증적 검증.
