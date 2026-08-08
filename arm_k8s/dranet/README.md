# NWDAF + DRANET: Dynamic CNI Backend Switching for 5GC UPF

NWDAF AnLF가 UPF KPI를 분석하여 최적 CNI backend(ipvlan↔macvlan)를 판단하고,
DRANET ResourceClaim 변경으로 런타임 전환하는 closed-loop 시스템.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    NWDAF Engine (nwdaf-engine.py)             │
├──────────────┬───────────────┬───────────────┬───────────────┤
│  Collector   │  Classifier   │   Executor    │    Logger     │
│  (OAM 수집) │  (ML 추론)    │  (DRANET)     │  (검증/기록)  │
├──────────────┼───────────────┼───────────────┼───────────────┤
│ kubectl top  │ RandomForest  │ nwdaf-switch  │ JSONL 기록    │
│ /proc/net/dev│ (sklearn)     │ .sh           │ 전후 비교     │
└──────┬───────┴───────┬───────┴───────┬───────┴───────┬───────┘
       │               │               │               │
       ▼               ▼               ▼               ▼
   UPF Pod         model.pkl      ResourceClaim    nwdaf-logs/
  (N3/N6 KPI)                    (DeviceClass)
```

## Quick Start

```bash
# 1. 모델 학습 (합성 데이터)
python3 train-model.py

# 2. NWDAF 엔진 실행
python3 nwdaf-engine.py

# 3. 또는 dry-run (판단만, 전환 안 함)
python3 nwdaf-engine.py --dry-run
```

## Files

| 파일 | 역할 |
|------|------|
| `nwdaf-engine.py` | NWDAF AnLF 메인 엔진 (수집→추론→실행→검증 루프) |
| `train-model.py` | ML 모델 학습 (합성/실측 데이터) |
| `nwdaf-switch.sh` | DRANET ResourceClaim 변경 실행 |
| `device-classes.yaml` | DeviceClass 정의 (net-ipvlan, net-macvlan) |
| `model/nwdaf-classifier.pkl` | 학습된 모델 |
| `model/training_data.jsonl` | 학습 데이터 |
| `nwdaf-logs/` | 판단 결과 로그 (JSONL) |

## Dependencies

```bash
pip install numpy scikit-learn joblib
```

- kubectl (configured with free5gc namespace access)
- DRANET DaemonSet 실행 중
- Kubernetes v1.32+ (DRA beta) 또는 v1.34+ (DRA GA)

## NWDAF Engine Options

```
python3 nwdaf-engine.py [OPTIONS]

Options:
  --interval INT    수집/판단 주기 (초, default: 5)
  --window INT      판단 윈도우 크기 (샘플 수, default: 5)
  --model PATH      학습된 모델 경로
  --dry-run         전환 실행 안 함 (판단만)
```

## Model Training

```bash
# 합성 데이터로 학습 (선행연구 기반 4 프로파일)
python3 train-model.py

# 실측 데이터로 학습
python3 train-model.py --data training_data.jsonl

# 데이터 내보내기
python3 train-model.py --export-data model/training_data.jsonl
```

### ML Model

- Algorithm: RandomForestClassifier (n_estimators=100, max_depth=10)
- Pipeline: StandardScaler → RandomForest
- Features: `[throughput_mbps, packet_loss_pct, total_pps, cpu_milli, mem_mi]`
- Labels: `ipvlan` / `macvlan`

### Training Profiles (선행연구 기반)

| Profile | 트래픽 특성 | 최적 CNI | 근거 |
|---------|------------|----------|------|
| ipvlan_optimal | 소패킷, 고pps, 저throughput (mMTC/VoNR) | ipvlan | [SHS2023, Bandewar2015] |
| macvlan_optimal | 대패킷, 고throughput (eMBB) | macvlan | [MDPI2024, IETF BMWG] |
| ipvlan_degraded | ipvlan 사용 중 CPU 병목 | macvlan | [NetDev2023] |
| macvlan_overhead | macvlan 사용 중 MAC lookup 과부하 | ipvlan | [Bandewar2015] |

## Decision Logic

```
매 interval마다:
  1. KPI 수집 (OAM: kubectl top + /proc/net/dev)
  2. window 평균으로 feature vector 구성
  3. ML 모델 추론 → recommended CNI
  4. 전환 조건 확인:
     - recommended ≠ current
     - confidence > 0.7
     - cooldown (30초) 경과
  5. 조건 충족 시 DRANET 전환 실행
  6. 전환 후 KPI 비교 → 판단 정확성 검증
```

## Experiment Protocol

```
실험 매트릭스 (3×3):

        A. ipvlan 고정    B. macvlan 고정    C. NWDAF 동적 전환
T1 대규모     ✓                ✓                 ✓
T2 소규모     ✓                ✓                 ✓
T3 소→대      ✓                ✓                 ✓ (핵심)

실행:
  # A: ipvlan 고정
  ./nwdaf-switch.sh ipvlan
  ./run.sh --scenario streaming-dl.yaml  # T1

  # B: macvlan 고정
  ./nwdaf-switch.sh macvlan
  ./run.sh --scenario streaming-dl.yaml  # T1

  # C: NWDAF 동적 전환
  python3 nwdaf-engine.py &
  ./run.sh --scenario iot-burst.yaml     # T2 시작
  sleep 60
  ./run.sh --scenario streaming-dl.yaml  # T1로 전환 → NWDAF가 감지 후 전환
```

## 3GPP Compliance

| TS 23.288 기능 | 구현 | 방식 |
|----------------|------|------|
| AnLF — 데이터 수집 | ✅ | OAM 경로 (kubectl + /proc/net/dev) |
| AnLF — 분석/추론 | ✅ | RandomForest 분류 |
| AnLF — 결과 출력 | ✅ | DRANET 전환 실행 |
| MTLF — 모델 학습 | ✅ | offline (train-model.py) |
| Analytics ID | Network Performance | throughput, packet loss, CPU |
| Nnwdaf 서비스 인터페이스 | ❌ | scope out (단일 시스템 내부 연동) |

## Log Format

`nwdaf-logs/nwdaf-decisions_YYYYMMDD_HHMMSS.jsonl`:

```json
{
  "timestamp": "16:30:45",
  "current_backend": "ipvlan",
  "recommended": "macvlan",
  "confidence": 0.92,
  "should_switch": true,
  "switched": true,
  "kpi_snapshot": {
    "throughput_mbps": 180.5,
    "packet_loss_pct": 7.2,
    "total_pps": 35000,
    "cpu_milli": 450
  },
  "evaluation": {
    "pre_switch": {"throughput_mbps": 150.3, "packet_loss_pct": 7.2, "cpu_milli": 450},
    "post_switch": {"throughput_mbps": 195.8, "packet_loss_pct": 1.1, "cpu_milli": 320},
    "throughput_change_pct": 30.2,
    "loss_change_pct": -84.7,
    "verdict": "CORRECT"
  }
}
```
