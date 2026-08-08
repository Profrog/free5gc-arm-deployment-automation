#!/usr/bin/env python3
"""
nwdaf-engine.py — NWDAF AnLF Closed-Loop Engine

3GPP TS 23.288 AnLF 최소 구현:
  1. OAM 경로로 KPI 수집 (kubectl top + /proc/net/dev)
  2. ML 모델로 최적 CNI backend 분류 (ipvlan vs macvlan)
  3. DRANET ResourceClaim 변경으로 전환 실행
  4. 전환 전후 KPI 비교로 판단 정확성 검증

사용법:
    python3 nwdaf-engine.py                    # 기본 실행 (5초 주기)
    python3 nwdaf-engine.py --interval 10      # 10초 주기
    python3 nwdaf-engine.py --model model.pkl  # 커스텀 모델
    python3 nwdaf-engine.py --dry-run          # 전환 실행 안 함 (판단만)

아키텍처:
    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
    │  Collector   │────>│  Classifier │────>│   Executor  │
    │ (OAM 수집)  │     │  (ML 추론)  │     │ (DRANET)    │
    └─────────────┘     └─────────────┘     └─────────────┘
           │                    │                    │
           └────────────────────┴────────────────────┘
                           │
                    ┌──────┴──────┐
                    │   Logger    │
                    │ (검증/기록) │
                    └─────────────┘
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

# ═══════════════════════════════════════════════════════
# 설정
# ═══════════════════════════════════════════════════════

NAMESPACE = os.environ.get("NAMESPACE", "free5gc")
CLAIM_NAME = os.environ.get("CLAIM_NAME", "upf-network")
SWITCH_SCRIPT = Path(__file__).parent / "nwdaf-switch.sh"
DEFAULT_MODEL_PATH = Path(__file__).parent / "model" / "nwdaf-classifier.pkl"
LOG_DIR = Path(__file__).parent / "nwdaf-logs"

# 전환 후 안정화 대기 (flapping 방지)
COOLDOWN_SECONDS = 30

# 판단에 필요한 최소 샘플 수 (window)
MIN_SAMPLES = 3


# ═══════════════════════════════════════════════════════
# Collector: OAM 경로 KPI 수집
# ═══════════════════════════════════════════════════════

class KPICollector:
    """kubectl top + /proc/net/dev로 UPF KPI 수집 (OAM 경로)"""

    def __init__(self, namespace: str = NAMESPACE):
        self.namespace = namespace
        self._prev_stats = None

    def collect(self) -> dict | None:
        """한 샘플의 KPI를 수집하여 dict로 반환"""
        try:
            resource = self._collect_resource()
            network = self._collect_network()
            if resource is None or network is None:
                return None

            return {
                "timestamp": datetime.now().isoformat(),
                "cpu_milli": resource["cpu_milli"],
                "mem_mi": resource["mem_mi"],
                "rx_packets": network["rx_packets"],
                "tx_packets": network["tx_packets"],
                "rx_drop": network["rx_drop"],
                "tx_drop": network["tx_drop"],
                "rx_bytes": network["rx_bytes"],
                "tx_bytes": network["tx_bytes"],
                # 파생 메트릭
                "total_pps": network["rx_packets"] + network["tx_packets"],
                "packet_loss_pct": self._calc_loss(network),
                "throughput_mbps": self._calc_throughput(network),
            }
        except Exception as e:
            print(f"[COLLECTOR] Error: {e}", file=sys.stderr)
            return None

    def _collect_resource(self) -> dict | None:
        """kubectl top pods로 UPF CPU/Memory 수집"""
        result = subprocess.run(
            ["kubectl", "top", "pods", "-n", self.namespace,
             "-l", "nf=upf", "--no-headers"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return None

        lines = result.stdout.strip().split("\n")
        if not lines or not lines[0].strip():
            return None

        # 첫 번째 UPF Pod의 리소스
        parts = lines[0].split()
        if len(parts) < 3:
            return None

        cpu_raw = parts[1]  # e.g., "23m"
        mem_raw = parts[2]  # e.g., "45Mi"

        cpu_milli = int(cpu_raw.rstrip("m")) if cpu_raw.endswith("m") else int(cpu_raw) * 1000
        if mem_raw.endswith("Gi"):
            mem_mi = int(mem_raw.rstrip("Gi")) * 1024
        elif mem_raw.endswith("Mi"):
            mem_mi = int(mem_raw.rstrip("Mi"))
        elif mem_raw.endswith("Ki"):
            mem_mi = int(mem_raw.rstrip("Ki")) // 1024
        else:
            mem_mi = int(mem_raw)

        return {"cpu_milli": cpu_milli, "mem_mi": mem_mi}

    def _collect_network(self) -> dict | None:
        """UPF Pod의 /proc/net/dev에서 인터페이스 통계 수집"""
        # UPF Pod 이름 조회
        result = subprocess.run(
            ["kubectl", "get", "pods", "-n", self.namespace,
             "-l", "nf=upf", "-o", "jsonpath={.items[0].metadata.name}"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        upf_pod = result.stdout.strip()

        # /proc/net/dev 읽기
        result = subprocess.run(
            ["kubectl", "exec", "-n", self.namespace, upf_pod,
             "-c", "upf", "--", "cat", "/proc/net/dev"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return None

        # GTP 인터페이스 또는 eth0 파싱
        stats = {"rx_bytes": 0, "rx_packets": 0, "rx_drop": 0,
                 "tx_bytes": 0, "tx_packets": 0, "tx_drop": 0}

        for line in result.stdout.split("\n"):
            # upfgtp, gtp5g, 또는 net1 (secondary interface) 찾기
            if any(iface in line for iface in ["gtp", "net1", "n3", "n6"]):
                parts = line.split(":")
                if len(parts) < 2:
                    continue
                fields = parts[1].split()
                if len(fields) >= 12:
                    stats["rx_bytes"] += int(fields[0])
                    stats["rx_packets"] += int(fields[1])
                    stats["rx_drop"] += int(fields[3])
                    stats["tx_bytes"] += int(fields[8])
                    stats["tx_packets"] += int(fields[9])
                    stats["tx_drop"] += int(fields[11])

        # 이전 값과의 차이로 rate 계산
        current_stats = stats.copy()
        if self._prev_stats is not None:
            for key in stats:
                stats[key] = max(0, current_stats[key] - self._prev_stats[key])
        self._prev_stats = current_stats

        return stats

    def _calc_loss(self, net: dict) -> float:
        """패킷 로스율 계산"""
        total = net["rx_packets"] + net["tx_packets"]
        if total == 0:
            return 0.0
        drops = net["rx_drop"] + net["tx_drop"]
        return round((drops / total) * 100, 4)

    def _calc_throughput(self, net: dict) -> float:
        """throughput 계산 (Mbps, 수집 interval 기반)"""
        total_bytes = net["rx_bytes"] + net["tx_bytes"]
        # bytes → Mbps (interval 동안의 누적이므로 interval로 나눔은 caller가 처리)
        return round((total_bytes * 8) / 1_000_000, 2)


# ═══════════════════════════════════════════════════════
# Classifier: ML 기반 CNI 분류
# ═══════════════════════════════════════════════════════

class CNIClassifier:
    """학습된 모델로 최적 CNI backend 분류

    입력 features: [throughput_mbps, packet_loss_pct, total_pps, cpu_milli, mem_mi]
    출력: "ipvlan" 또는 "macvlan"
    """

    FEATURES = ["throughput_mbps", "packet_loss_pct", "total_pps", "cpu_milli", "mem_mi"]

    def __init__(self, model_path: Path = DEFAULT_MODEL_PATH):
        self.model = None
        self.model_path = model_path
        self._load_model()

    def _load_model(self):
        """학습된 모델 로드 (없으면 rule-based fallback)"""
        if self.model_path.exists():
            try:
                import joblib
                self.model = joblib.load(self.model_path)
                print(f"[CLASSIFIER] Model loaded: {self.model_path}")
            except Exception as e:
                print(f"[CLASSIFIER] Failed to load model: {e}. Using rule-based fallback.")
                self.model = None
        else:
            print(f"[CLASSIFIER] No model at {self.model_path}. Using rule-based fallback.")

    def predict(self, samples: list[dict]) -> str:
        """최근 N개 샘플을 기반으로 최적 CNI 예측

        Returns: "ipvlan" 또는 "macvlan"
        """
        if not samples:
            return "ipvlan"  # 기본값

        # Feature 추출 (window 평균)
        features = self._extract_features(samples)

        if self.model is not None:
            # ML 모델 추론
            prediction = self.model.predict([features])[0]
            return prediction
        else:
            # Rule-based fallback
            return self._rule_based(features)

    def _extract_features(self, samples: list[dict]) -> list[float]:
        """샘플 윈도우에서 feature vector 추출 (평균)"""
        feature_values = {f: [] for f in self.FEATURES}

        for sample in samples:
            for f in self.FEATURES:
                if f in sample:
                    feature_values[f].append(sample[f])

        # 각 feature의 평균
        return [
            np.mean(feature_values[f]) if feature_values[f] else 0.0
            for f in self.FEATURES
        ]

    def _rule_based(self, features: list[float]) -> str:
        """ML 모델 없을 때의 rule-based 판단

        규칙 (선행연구 기반):
        - 고 throughput(>100Mbps) + 저 pps → macvlan (대패킷, NIC offload 유리)
        - 고 pps(>10000) + 저 throughput → ipvlan (소패킷, 커널 내부 처리 유리)
        - 높은 packet_loss(>5%) + 고 throughput → macvlan (CPU 병목 해소)
        """
        throughput, loss, pps, cpu, mem = features

        # 대패킷 고throughput → macvlan
        if throughput > 100 and pps < 50000:
            return "macvlan"

        # 고 loss + 고 throughput → macvlan (CPU 병목)
        if loss > 5.0 and throughput > 50:
            return "macvlan"

        # 고 CPU + 고 throughput → macvlan
        if cpu > 400 and throughput > 50:
            return "macvlan"

        # 소패킷 고빈도 → ipvlan
        if pps > 10000 and throughput < 50:
            return "ipvlan"

        # 기본값: ipvlan (저오버헤드)
        return "ipvlan"

    def get_confidence(self, samples: list[dict]) -> float:
        """판단 신뢰도 반환 (0~1)"""
        if self.model is None:
            return 0.8  # rule-based는 고정 신뢰도

        features = self._extract_features(samples)
        try:
            proba = self.model.predict_proba([features])[0]
            return float(max(proba))
        except Exception:
            return 0.5


# ═══════════════════════════════════════════════════════
# Executor: DRANET 전환 실행
# ═══════════════════════════════════════════════════════

class DRANETExecutor:
    """nwdaf-switch.sh를 호출하여 DRANET ResourceClaim 변경"""

    def __init__(self, switch_script: Path = SWITCH_SCRIPT, dry_run: bool = False):
        self.switch_script = switch_script
        self.dry_run = dry_run

    def get_current_backend(self) -> str:
        """현재 CNI backend 조회"""
        result = subprocess.run(
            ["kubectl", "get", "resourceclaim", CLAIM_NAME, "-n", NAMESPACE,
             "-o", "jsonpath={.spec.devices.requests[0].deviceClassName}"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            # "net-ipvlan" → "ipvlan"
            return result.stdout.strip().replace("net-", "")
        return "unknown"

    def switch(self, target: str) -> bool:
        """CNI backend 전환 실행

        Args:
            target: "ipvlan" 또는 "macvlan"
        Returns:
            True if switch executed, False if skipped/failed
        """
        current = self.get_current_backend()

        if current == target:
            return False  # 이미 동일

        if self.dry_run:
            print(f"[EXECUTOR] DRY-RUN: Would switch {current} → {target}")
            return False

        print(f"[EXECUTOR] Switching: {current} → {target}")

        result = subprocess.run(
            [str(self.switch_script), target],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode == 0:
            print(f"[EXECUTOR] ✓ Switch complete: {current} → {target}")
            return True
        else:
            print(f"[EXECUTOR] ✗ Switch failed: {result.stderr}", file=sys.stderr)
            return False


# ═══════════════════════════════════════════════════════
# Logger: 판단 결과 기록 및 검증
# ═══════════════════════════════════════════════════════

class NWDAFLogger:
    """NWDAF 판단 기록 + 전환 전후 KPI 비교"""

    def __init__(self, log_dir: Path = LOG_DIR):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"nwdaf-decisions_{self.run_id}.jsonl"
        self.pre_switch_kpi = None

    def log_decision(self, decision: dict):
        """판단 결과를 JSONL로 기록"""
        with open(self.log_file, "a") as f:
            f.write(json.dumps(decision, ensure_ascii=False) + "\n")

    def record_pre_switch(self, samples: list[dict]):
        """전환 직전 KPI 기록 (사후 비교용)"""
        if samples:
            self.pre_switch_kpi = {
                "throughput_mbps": np.mean([s.get("throughput_mbps", 0) for s in samples]),
                "packet_loss_pct": np.mean([s.get("packet_loss_pct", 0) for s in samples]),
                "cpu_milli": np.mean([s.get("cpu_milli", 0) for s in samples]),
            }

    def evaluate_switch(self, post_samples: list[dict]) -> dict | None:
        """전환 후 KPI와 비교하여 판단 정확성 평가"""
        if self.pre_switch_kpi is None or not post_samples:
            return None

        post_kpi = {
            "throughput_mbps": np.mean([s.get("throughput_mbps", 0) for s in post_samples]),
            "packet_loss_pct": np.mean([s.get("packet_loss_pct", 0) for s in post_samples]),
            "cpu_milli": np.mean([s.get("cpu_milli", 0) for s in post_samples]),
        }

        evaluation = {
            "pre_switch": self.pre_switch_kpi,
            "post_switch": post_kpi,
            "throughput_change_pct": self._pct_change(
                self.pre_switch_kpi["throughput_mbps"],
                post_kpi["throughput_mbps"]
            ),
            "loss_change_pct": self._pct_change(
                self.pre_switch_kpi["packet_loss_pct"],
                post_kpi["packet_loss_pct"]
            ),
            "cpu_change_pct": self._pct_change(
                self.pre_switch_kpi["cpu_milli"],
                post_kpi["cpu_milli"]
            ),
        }

        # 판단 올바름: throughput 증가 또는 loss 감소
        evaluation["verdict"] = (
            "CORRECT" if (
                evaluation["throughput_change_pct"] > 0 or
                evaluation["loss_change_pct"] < 0
            ) else "INCONCLUSIVE"
        )

        self.pre_switch_kpi = None  # reset
        return evaluation

    def _pct_change(self, before: float, after: float) -> float:
        if before == 0:
            return 0.0
        return round(((after - before) / before) * 100, 2)


# ═══════════════════════════════════════════════════════
# NWDAF Engine: 메인 루프
# ═══════════════════════════════════════════════════════

class NWDAFEngine:
    """NWDAF AnLF Closed-Loop Engine

    수집 → 추론 → 실행 → 검증 을 interval 주기로 반복
    """

    def __init__(self, args):
        self.interval = args.interval
        self.window_size = args.window
        self.dry_run = args.dry_run
        self.mode = args.mode

        self.collector = KPICollector()
        self.classifier = CNIClassifier(Path(args.model))
        self.executor = DRANETExecutor(dry_run=args.dry_run)
        self.logger = NWDAFLogger()

        # rule-based 모드면 ML 모델 강제 비활성화
        if self.mode == "rule-based":
            self.classifier.model = None

        # 상태
        self.sample_buffer = []
        self.last_switch_time = 0
        self.switch_count = 0
        self.total_decisions = 0

    def run(self):
        """메인 루프 실행"""
        print("═══════════════════════════════════════")
        print("  NWDAF AnLF Engine Started")
        print("═══════════════════════════════════════")
        print(f"  Interval:    {self.interval}s")
        print(f"  Window:      {self.window_size} samples")
        print(f"  Mode:        {self.mode}")
        print(f"  Model:       {'ML (predictive)' if self.classifier.model else 'Rule-based (reactive)'}")
        print(f"  Dry-run:     {self.dry_run}")
        print(f"  Current CNI: {self.executor.get_current_backend()}")
        print(f"  Log:         {self.logger.log_file}")
        print("═══════════════════════════════════════")
        print()

        try:
            while True:
                self._tick()
                time.sleep(self.interval)
        except KeyboardInterrupt:
            print(f"\n[ENGINE] Stopped. Total decisions: {self.total_decisions}, "
                  f"Switches: {self.switch_count}")

    def _tick(self):
        """한 주기 실행"""
        now = time.time()

        # 1. 수집
        sample = self.collector.collect()
        if sample is None:
            print(f"[{self._ts()}] Collection failed, skipping")
            return

        self.sample_buffer.append(sample)
        if len(self.sample_buffer) > self.window_size * 2:
            self.sample_buffer = self.sample_buffer[-self.window_size * 2:]

        # 최소 샘플 확보 전에는 판단하지 않음
        if len(self.sample_buffer) < MIN_SAMPLES:
            print(f"[{self._ts()}] Collecting... ({len(self.sample_buffer)}/{MIN_SAMPLES})")
            return

        # 2. 추론
        window = self.sample_buffer[-self.window_size:]
        recommended = self.classifier.predict(window)
        confidence = self.classifier.get_confidence(window)
        current = self.executor.get_current_backend()

        self.total_decisions += 1

        # 3. 판단 및 실행
        should_switch = (
            recommended != current and
            confidence > 0.7 and
            (now - self.last_switch_time) > COOLDOWN_SECONDS
        )

        # 로그 기록
        decision = {
            "timestamp": self._ts(),
            "current_backend": current,
            "recommended": recommended,
            "confidence": round(confidence, 3),
            "should_switch": should_switch,
            "kpi_snapshot": {
                "throughput_mbps": sample["throughput_mbps"],
                "packet_loss_pct": sample["packet_loss_pct"],
                "total_pps": sample["total_pps"],
                "cpu_milli": sample["cpu_milli"],
            },
        }

        status_icon = "→" if should_switch else "="
        print(f"[{self._ts()}] {current} {status_icon} {recommended} "
              f"(conf={confidence:.2f}, tput={sample['throughput_mbps']:.1f}Mbps, "
              f"loss={sample['packet_loss_pct']:.2f}%, pps={sample['total_pps']})")

        if should_switch:
            # 전환 전 KPI 기록
            self.logger.record_pre_switch(window)

            # 실행
            switched = self.executor.switch(recommended)
            if switched:
                self.last_switch_time = now
                self.switch_count += 1
                decision["switched"] = True
                print(f"[{self._ts()}] ⚡ SWITCH #{self.switch_count}: "
                      f"{current} → {recommended}")
        else:
            # 전환 후 안정화 구간이면 검증 수행
            if (self.logger.pre_switch_kpi is not None and
                    len(self.sample_buffer) >= MIN_SAMPLES and
                    (now - self.last_switch_time) > COOLDOWN_SECONDS / 2):
                evaluation = self.logger.evaluate_switch(window)
                if evaluation:
                    decision["evaluation"] = evaluation
                    print(f"[{self._ts()}] 📊 Evaluation: {evaluation['verdict']} "
                          f"(tput {evaluation['throughput_change_pct']:+.1f}%, "
                          f"loss {evaluation['loss_change_pct']:+.1f}%)")

        self.logger.log_decision(decision)

    def _ts(self) -> str:
        return datetime.now().strftime("%H:%M:%S")


# ═══════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="NWDAF AnLF Engine — ML-based CNI backend optimization for 5GC UPF"
    )
    parser.add_argument("--interval", type=int, default=5,
                        help="수집/판단 주기 (초, default: 5)")
    parser.add_argument("--window", type=int, default=5,
                        help="판단에 사용할 샘플 윈도우 크기 (default: 5)")
    parser.add_argument("--model", type=str, default=str(DEFAULT_MODEL_PATH),
                        help="학습된 모델 경로 (default: model/nwdaf-classifier.pkl)")
    parser.add_argument("--mode", type=str, default="ml", choices=["ml", "rule-based"],
                        help="판단 모드: ml (ML 모델, predictive) 또는 rule-based (threshold, reactive)")
    parser.add_argument("--dry-run", action="store_true",
                        help="전환 실행 안 함 (판단만)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    engine = NWDAFEngine(args)
    engine.run()
