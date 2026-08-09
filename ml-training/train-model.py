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

MODEL_OUTPUT = Path(__file__).parent.parent / "nwdaf" / "model" / "nwdaf-classifier.pkl"
FEATURES = ["throughput_mbps", "packet_loss_pct", "total_pps", "cpu_milli", "mem_mi"]
LABELS = ["ipvlan", "macvlan"]

# 합성 데이터 생성 파라미터 (선행연구 기반)
# [SHS2023]: ipvlan이 일반 환경에서 더 나은 network performance
# [Bandewar2015]: ipvlan은 커널 내부 처리, macvlan은 NIC 레벨
# [MDPI2024]: packet size/workload type에 따라 최적 CNI 상이
# [IETF BMWG-02 §4.1.3]: "CNI optimized for high-throughput TCP bulk traffic
#   may perform suboptimally under UDP-heavy traffic"

# ═══════════════════════════════════════════════════════
# 시계열 패턴 기반 학습 데이터 생성
# 학습 패턴(5종)은 실험 패턴과 의도적으로 상이하게 설계하여
# 과적합이 아닌 일반화된 추세 판단 능력을 학습시킴
# ═══════════════════════════════════════════════════════

TRAINING_PATTERNS = {
    "rapid_ramp": {
        # 패턴 1: 급상승 (30초에 10→300Mbps)
        # → "빨리 올라가니까 즉시 전환 필요"
        "description": "급상승 — 빠른 전환 결정 필요",
        "duration_steps": 6,
        "throughput_curve": [10, 60, 130, 200, 260, 300],
        "label_switch_at": 2,  # step 2(130Mbps)부터 macvlan 필요
    },
    "slow_ramp": {
        # 패턴 2: 완상승 (300초에 10→300Mbps)
        # → "천천히 올라가지만 결국 전환 필요"
        "description": "완상승 — 여유 있지만 결국 전환",
        "duration_steps": 10,
        "throughput_curve": [10, 25, 45, 65, 90, 120, 155, 200, 250, 300],
        "label_switch_at": 5,  # step 5(120Mbps)부터 macvlan 필요
    },
    "spike_return": {
        # 패턴 3: spike 후 복귀 (10→200→10)
        # → "일시적이니까 전환하면 안 됨" (false positive 방지)
        "description": "일시적 spike — 전환 불필요",
        "duration_steps": 8,
        "throughput_curve": [10, 50, 150, 200, 180, 80, 30, 10],
        "label_switch_at": None,  # 전환 불필요 (전부 ipvlan 유지)
    },
    "step_plateau": {
        # 패턴 4: 계단식 (10→100 유지→200)
        # → "정체 후 재상승 감지"
        "description": "계단식 상승 — 정체 구간 후 전환",
        "duration_steps": 8,
        "throughput_curve": [10, 60, 100, 100, 100, 150, 200, 200],
        "label_switch_at": 5,  # step 5(150Mbps)부터 macvlan 필요
    },
    "oscillation": {
        # 패턴 5: 진동 (80↔120 반복)
        # → "threshold 근처 왔다갔다 — 전환하면 안 됨" (flapping 방지)
        "description": "threshold 근처 진동 — flapping 방지",
        "duration_steps": 10,
        "throughput_curve": [80, 110, 85, 120, 90, 115, 85, 110, 95, 100],
        "label_switch_at": None,  # 전환 불필요 (진동일 뿐)
    },
}

# Feature 정의 (시계열 추세 포함)
FEATURES = ["throughput_mbps", "throughput_delta", "throughput_slope",
            "packet_loss_pct", "loss_delta", "cpu_milli", "cpu_delta"]
LABELS = ["ipvlan", "macvlan"]


# ═══════════════════════════════════════════════════════
# 합성 데이터 생성 (시계열 패턴 기반)
# ═══════════════════════════════════════════════════════

def generate_synthetic_data(n_variations: int = 100, noise: float = 0.1) -> tuple:
    """시계열 패턴 기반 합성 학습 데이터 생성

    각 패턴을 n_variations만큼 노이즈를 달리하여 생성.
    각 step을 하나의 샘플로 변환 (window feature 포함).

    Args:
        n_variations: 패턴당 변형 횟수
        noise: 가우시안 노이즈 비율

    Returns:
        (X, y) — features array, labels array
    """
    X_all = []
    y_all = []

    for pattern_name, pattern in TRAINING_PATTERNS.items():
        curve = pattern["throughput_curve"]
        switch_at = pattern["label_switch_at"]
        n_steps = len(curve)

        for _ in range(n_variations):
            # 노이즈가 적용된 곡선 생성
            noisy_curve = [max(0, v + np.random.normal(0, v * noise)) for v in curve]

            # 각 step에서의 파생 메트릭 시뮬레이션
            for i in range(n_steps):
                throughput = noisy_curve[i]

                # delta: 이전 step 대비 변화
                throughput_delta = (noisy_curve[i] - noisy_curve[i-1]) if i > 0 else 0

                # slope: 최근 3개 step의 선형 기울기
                if i >= 2:
                    recent = noisy_curve[max(0, i-2):i+1]
                    throughput_slope = (recent[-1] - recent[0]) / len(recent)
                else:
                    throughput_slope = throughput_delta

                # packet_loss: throughput에 비례 (ipvlan 특성 시뮬레이션)
                # ipvlan에서 150Mbps 이상이면 loss 시작
                if throughput > 150:
                    loss = min(30, (throughput - 150) * 0.15) + np.random.normal(0, 0.5)
                elif throughput > 100:
                    loss = (throughput - 100) * 0.02 + np.random.normal(0, 0.3)
                else:
                    loss = max(0, np.random.normal(0.1, 0.2))
                loss = max(0, loss)

                loss_delta = loss - (max(0, (noisy_curve[i-1] - 100) * 0.02) if i > 0 else 0)

                # CPU: throughput에 비례
                cpu = 50 + throughput * 2.5 + np.random.normal(0, 20)
                cpu = max(20, cpu)
                cpu_delta = (cpu - (50 + noisy_curve[i-1] * 2.5)) if i > 0 else 0

                # Feature vector
                features = [
                    throughput,
                    throughput_delta,
                    throughput_slope,
                    loss,
                    loss_delta,
                    cpu,
                    cpu_delta,
                ]
                X_all.append(features)

                # 라벨: switch_at 이전은 ipvlan, 이후는 macvlan
                # None이면 전부 ipvlan (전환 불필요 패턴)
                if switch_at is None:
                    y_all.append("ipvlan")
                elif i >= switch_at:
                    y_all.append("macvlan")
                else:
                    y_all.append("ipvlan")

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
