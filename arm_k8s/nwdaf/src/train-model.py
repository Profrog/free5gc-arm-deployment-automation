#!/usr/bin/env python3
"""
train-model.py — NWDAF CNI 분류 모델 학습

두 가지 모드:
  1. 실측 데이터 기반 학습 (monitor-data/ 디렉토리에서 labeled data 로드)
  2. 합성 데이터 기반 학습 (선행연구 기반 파라미터로 시뮬레이션 데이터 생성)

출력: model/nwdaf-classifier.pkl (sklearn Pipeline)

사용법:
    python3 train-model.py                     # 합성 데이터로 학습
    python3 train-model.py --data training_data.jsonl  # 실측 데이터로 학습
    python3 train-model.py --evaluate          # 학습 후 성능 평가 출력

모델:
    - RandomForestClassifier (경량, ARM64 추론에 적합)
    - 입력: [throughput_mbps, packet_loss_pct, total_pps, cpu_milli, mem_mi]
    - 출력: "ipvlan" 또는 "macvlan"

선행연구 기반 합성 데이터 생성 근거:
    - 소패킷 고빈도 (mMTC/VoNR) → ipvlan 유리 [SHS2023, Bandewar2015]
    - 대패킷 고throughput (eMBB) → macvlan 유리 [MDPI2024, koukis2024]
    - 고 CPU + 고 throughput → macvlan (NIC offload) [NetDev2023]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    import joblib
except ImportError:
    from sklearn.externals import joblib

# ═══════════════════════════════════════════════════════
# 설정
# ═══════════════════════════════════════════════════════

MODEL_OUTPUT = Path(__file__).parent / "model" / "nwdaf-classifier.pkl"
FEATURES = ["throughput_mbps", "packet_loss_pct", "total_pps", "cpu_milli", "mem_mi"]
LABELS = ["ipvlan", "macvlan"]

# 합성 데이터 생성 파라미터 (선행연구 기반)
# [SHS2023]: ipvlan이 일반 환경에서 더 나은 network performance
# [Bandewar2015]: ipvlan은 커널 내부 처리, macvlan은 NIC 레벨
# [MDPI2024]: packet size/workload type에 따라 최적 CNI 상이
# [IETF BMWG-02 §4.1.3]: "CNI optimized for high-throughput TCP bulk traffic
#   may perform suboptimally under UDP-heavy traffic"

SYNTHETIC_PROFILES = {
    "ipvlan_optimal": {
        # mMTC/VoNR: 소패킷, 고빈도, 저throughput, 다수 UE
        "throughput_mbps": (1, 50),       # 1~50 Mbps
        "packet_loss_pct": (0.0, 2.0),   # 정상 범위
        "total_pps": (5000, 100000),     # 높은 pps (소패킷)
        "cpu_milli": (20, 200),          # 낮은 CPU (ipvlan 경량)
        "mem_mi": (30, 80),
        "label": "ipvlan",
    },
    "macvlan_optimal": {
        # eMBB: 대패킷, 고throughput, 저pps
        "throughput_mbps": (100, 500),    # 100~500 Mbps
        "packet_loss_pct": (0.0, 3.0),   # 약간의 loss 허용
        "total_pps": (5000, 50000),      # 상대적 낮은 pps (대패킷)
        "cpu_milli": (100, 500),         # 중~고 CPU
        "mem_mi": (50, 150),
        "label": "macvlan",
    },
    "ipvlan_degraded": {
        # ipvlan 사용 중 고throughput으로 CPU 병목 발생 → macvlan 전환 필요
        "throughput_mbps": (80, 300),
        "packet_loss_pct": (5.0, 30.0),  # 높은 loss (CPU 병목)
        "total_pps": (30000, 80000),
        "cpu_milli": (400, 900),         # CPU 과부하
        "mem_mi": (80, 200),
        "label": "macvlan",
    },
    "macvlan_overhead": {
        # macvlan 사용 중 소패킷 다수 UE로 MAC lookup 오버헤드 → ipvlan 전환 필요
        "throughput_mbps": (5, 40),
        "packet_loss_pct": (0.5, 5.0),
        "total_pps": (50000, 200000),    # 매우 높은 pps
        "cpu_milli": (200, 600),         # MAC lookup으로 CPU 높음
        "mem_mi": (60, 120),
        "label": "ipvlan",
    },
}


# ═══════════════════════════════════════════════════════
# 합성 데이터 생성
# ═══════════════════════════════════════════════════════

def generate_synthetic_data(n_samples_per_profile: int = 500, noise: float = 0.1) -> tuple:
    """선행연구 기반 합성 학습 데이터 생성

    Args:
        n_samples_per_profile: 프로파일당 샘플 수
        noise: 가우시안 노이즈 비율 (0~1)

    Returns:
        (X, y) — features array, labels array
    """
    X_all = []
    y_all = []

    for profile_name, profile in SYNTHETIC_PROFILES.items():
        for _ in range(n_samples_per_profile):
            sample = []
            for feature in FEATURES:
                low, high = profile[feature]
                value = np.random.uniform(low, high)
                # 노이즈 추가
                value += np.random.normal(0, abs(value) * noise)
                value = max(0, value)  # 음수 방지
                sample.append(value)
            X_all.append(sample)
            y_all.append(profile["label"])

    return np.array(X_all), np.array(y_all)


# ═══════════════════════════════════════════════════════
# 실측 데이터 로드
# ═══════════════════════════════════════════════════════

def load_real_data(data_path: Path) -> tuple:
    """실측 데이터 (JSONL) 로드

    JSONL 포맷 예시:
    {"throughput_mbps": 150, "packet_loss_pct": 0.5, "total_pps": 30000,
     "cpu_milli": 200, "mem_mi": 80, "label": "macvlan"}
    """
    X = []
    y = []

    with open(data_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if "label" not in record:
                continue

            features = [record.get(f, 0) for f in FEATURES]
            X.append(features)
            y.append(record["label"])

    if not X:
        raise ValueError(f"No labeled data found in {data_path}")

    return np.array(X), np.array(y)


# ═══════════════════════════════════════════════════════
# 모델 학습
# ═══════════════════════════════════════════════════════

def train_model(X: np.ndarray, y: np.ndarray, evaluate: bool = True) -> Pipeline:
    """RandomForest 모델 학습

    Args:
        X: feature matrix (n_samples, 5)
        y: labels ("ipvlan" or "macvlan")
        evaluate: 학습 후 성능 평가 출력 여부

    Returns:
        학습된 sklearn Pipeline
    """
    print(f"[TRAIN] Dataset: {len(X)} samples, "
          f"ipvlan={sum(y == 'ipvlan')}, macvlan={sum(y == 'macvlan')}")

    # Pipeline: Scaler + RandomForest
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("classifier", RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            random_state=42,
            n_jobs=-1,
        ))
    ])

    if evaluate:
        # Cross-validation
        cv_scores = cross_val_score(pipeline, X, y, cv=5, scoring="accuracy")
        print(f"[TRAIN] Cross-validation accuracy: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

        # Train/test split for detailed report
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        pipeline.fit(X_train, y_train)
        y_pred = pipeline.predict(X_test)

        print("\n[TRAIN] Classification Report:")
        print(classification_report(y_test, y_pred, target_names=LABELS))

        print("[TRAIN] Confusion Matrix:")
        cm = confusion_matrix(y_test, y_pred, labels=LABELS)
        print(f"              {'ipvlan':>8} {'macvlan':>8}")
        print(f"  ipvlan     {cm[0][0]:>8} {cm[0][1]:>8}")
        print(f"  macvlan    {cm[1][0]:>8} {cm[1][1]:>8}")

        # Feature importance
        importances = pipeline.named_steps["classifier"].feature_importances_
        print("\n[TRAIN] Feature Importances:")
        for feat, imp in sorted(zip(FEATURES, importances), key=lambda x: -x[1]):
            print(f"  {feat:<20} {imp:.4f}")

        # 전체 데이터로 최종 학습
        pipeline.fit(X, y)
    else:
        pipeline.fit(X, y)

    return pipeline


# ═══════════════════════════════════════════════════════
# 학습 데이터 내보내기 (다른 도구로 검증용)
# ═══════════════════════════════════════════════════════

def export_training_data(X: np.ndarray, y: np.ndarray, output_path: Path):
    """학습 데이터를 JSONL로 내보내기"""
    with open(output_path, "w") as f:
        for features, label in zip(X, y):
            record = {feat: round(float(val), 4) for feat, val in zip(FEATURES, features)}
            record["label"] = label
            f.write(json.dumps(record) + "\n")
    print(f"[EXPORT] Training data saved: {output_path} ({len(X)} samples)")


# ═══════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="NWDAF CNI Classifier — Model Training"
    )
    parser.add_argument("--data", type=str, default=None,
                        help="실측 학습 데이터 경로 (JSONL). 없으면 합성 데이터 사용.")
    parser.add_argument("--samples", type=int, default=500,
                        help="프로파일당 합성 샘플 수 (default: 500)")
    parser.add_argument("--noise", type=float, default=0.1,
                        help="합성 데이터 노이즈 비율 (default: 0.1)")
    parser.add_argument("--output", type=str, default=str(MODEL_OUTPUT),
                        help="모델 출력 경로")
    parser.add_argument("--evaluate", action="store_true", default=True,
                        help="학습 후 성능 평가 출력 (default: True)")
    parser.add_argument("--export-data", type=str, default=None,
                        help="학습 데이터를 JSONL로 내보내기")
    args = parser.parse_args()

    # 데이터 준비
    if args.data:
        print(f"[TRAIN] Loading real data: {args.data}")
        X, y = load_real_data(Path(args.data))
    else:
        print(f"[TRAIN] Generating synthetic data ({args.samples} per profile, noise={args.noise})")
        X, y = generate_synthetic_data(args.samples, args.noise)

    # 학습 데이터 내보내기 (옵션)
    if args.export_data:
        export_training_data(X, y, Path(args.export_data))

    # 모델 학습
    model = train_model(X, y, evaluate=args.evaluate)

    # 모델 저장
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output_path)
    print(f"\n[TRAIN] ✓ Model saved: {output_path}")
    print(f"[TRAIN] Use with: python3 nwdaf-engine.py --model {output_path}")


if __name__ == "__main__":
    main()
