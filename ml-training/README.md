# ML Training — NWDAF 모델 학습 파이프라인 (MTLF)

NWDAF AnLF가 사용하는 분류 모델을 학습하는 오프라인 파이프라인.

## 전체 프로세스

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 실험 실행 (NWDAF OFF)                                     │
│    ./run.sh --experiment experiments/experiment-a-t1.yaml     │
│    ./run.sh --experiment experiments/experiment-b-t1.yaml     │
│    (ipvlan 고정 / macvlan 고정 × T1,T2,T3)                   │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
         monitor-data/{run_id}/pods/{upf}/
           ├── resources.jsonl       (cpu, mem)
           ├── packet_loss.jsonl     (pps, loss)
           └── iperf3_result.json    (throughput)
                      │
┌─────────────────────┼───────────────────────────────────────┐
│ 2. 로그 변환                                                  │
│    python3 convert-logs.py --all                              │
│    → data/{run_id}_features.jsonl                            │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
         data/{run_id}_features.jsonl
           {"throughput_mbps":150, "packet_loss_pct":0.5,
            "total_pps":30000, "cpu_milli":200, "mem_mi":80}
                      │
┌─────────────────────┼───────────────────────────────────────┐
│ 3. 라벨링 (A/B 비교)                                         │
│    python3 label-data.py --auto                               │
│    → data/training_data.jsonl                                │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
         data/training_data.jsonl
           {"throughput_mbps":150, ..., "label":"macvlan"}
                      │
┌─────────────────────┼───────────────────────────────────────┐
│ 4. 모델 학습                                                  │
│    python3 train-model.py --data data/training_data.jsonl     │
│    → ../nwdaf/model/nwdaf-classifier.pkl                     │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
         nwdaf/model/nwdaf-classifier.pkl
         (NWDAF AnLF가 로드하여 온라인 추론)
```

## 파일

| 파일 | 역할 |
|------|------|
| `convert-logs.py` | monitor-collector 로그 + iperf3 결과 → 통합 feature JSONL |
| `label-data.py` | A(ipvlan)/B(macvlan) 실험 비교 → 라벨 부여 |
| `train-model.py` | RandomForest 모델 학습 + 5-fold CV + feature importance |
| `data/` | 변환된 feature 데이터 + 라벨된 학습 데이터 |

## Quick Start

```bash
# 실험이 이미 완료된 상태에서:
cd /home/ubuntu/free5gc-k8s-arm/ml-training

# Step 1: 로그 → feature vector 변환
python3 convert-logs.py --all

# Step 2: A/B 비교 → 라벨링
python3 label-data.py --auto

# Step 3: 모델 학습
python3 train-model.py --data data/training_data.jsonl --evaluate

# 결과: ../nwdaf/model/nwdaf-classifier.pkl 생성됨
```

## 학습 데이터 형식

```json
{"throughput_mbps": 150, "packet_loss_pct": 0.5, "total_pps": 30000, "cpu_milli": 200, "mem_mi": 80, "label": "macvlan"}
{"throughput_mbps": 30, "packet_loss_pct": 0.1, "total_pps": 80000, "cpu_milli": 120, "mem_mi": 60, "label": "ipvlan"}
```

## 라벨링 기준

같은 트래픽 조건에서 A(ipvlan)와 B(macvlan) 결과를 비교:
- score = throughput / (1 + packet_loss_pct)
- score 높은 쪽 = 해당 트래픽 조건의 "정답" label

## 모델 스펙

- Algorithm: RandomForestClassifier (100 trees, max_depth=10)
- Pipeline: StandardScaler → RandomForest
- Features (5): throughput_mbps, packet_loss_pct, total_pps, cpu_milli, mem_mi
- Labels (2): "ipvlan", "macvlan"
- Evaluation: 5-fold cross-validation + confusion matrix + feature importance
