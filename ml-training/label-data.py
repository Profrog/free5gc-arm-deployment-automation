#!/usr/bin/env python3
"""
label-data.py — Ground Truth 라벨링

ipvlan 고정(A) 실험과 macvlan 고정(B) 실험 결과를 비교하여,
각 트래픽 조건에서 "어떤 인터페이스가 더 좋았는가"를 라벨링한다.

입력: monitor-data/ 디렉토리의 A/B 실험 결과 (JSONL)
출력: ml-training/data/training_data.jsonl (학습용 라벨된 데이터)

사용법:
    python3 label-data.py --a-dir monitor-data/exp_A-T1_* --b-dir monitor-data/exp_B-T1_*
    python3 label-data.py --auto   # monitor-data에서 A/B 매칭 자동 탐색

판단 기준:
    같은 트래픽 조건에서:
    - throughput 높은 쪽 = 우수
    - packet_loss 낮은 쪽 = 우수
    - 종합 점수 = throughput / (1 + packet_loss_pct) 로 비교
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from collections import defaultdict

FEATURES = ["throughput_mbps", "packet_loss_pct", "total_pps", "cpu_milli", "mem_mi"]
OUTPUT_DIR = Path(__file__).parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "training_data.jsonl"
MONITOR_DATA_DIR = Path("/home/ubuntu/free5gc-k8s-arm/traffic-profiles/monitor-data")


def load_kpi_from_dir(exp_dir: Path) -> list:
    """실험 디렉토리에서 KPI 데이터 로드"""
    kpi_list = []
    
    # kpi.jsonl 또는 metrics.jsonl 파일 탐색
    for jsonl_file in exp_dir.glob("*.jsonl"):
        with open(jsonl_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    # KPI 필드가 있는 레코드만
                    if any(k in record for k in FEATURES):
                        kpi_list.append(record)
                except json.JSONDecodeError:
                    continue
    
    return kpi_list


def compute_score(kpi: dict) -> float:
    """KPI를 단일 점수로 변환 (높을수록 좋음)"""
    throughput = kpi.get("throughput_mbps", 0)
    loss = kpi.get("packet_loss_pct", 0)
    # throughput 높고 loss 낮을수록 좋음
    return throughput / (1 + loss)


def average_kpi(kpi_list: list) -> dict:
    """KPI 리스트의 평균"""
    if not kpi_list:
        return {f: 0 for f in FEATURES}
    
    avg = {}
    for feat in FEATURES:
        values = [r.get(feat, 0) for r in kpi_list if feat in r]
        avg[feat] = sum(values) / len(values) if values else 0
    return avg


def label_from_comparison(a_kpi: dict, b_kpi: dict) -> str:
    """A(ipvlan)와 B(macvlan) 비교 → 더 좋은 쪽의 label 반환"""
    score_a = compute_score(a_kpi)
    score_b = compute_score(b_kpi)
    
    if score_b > score_a:
        return "macvlan"
    else:
        return "ipvlan"


def find_matching_experiments() -> list:
    """monitor-data에서 A/B 매칭 쌍 자동 탐색
    
    exp_A-T1_* 과 exp_B-T1_* 을 매칭
    """
    if not MONITOR_DATA_DIR.exists():
        return []
    
    experiments = defaultdict(dict)
    
    for d in MONITOR_DATA_DIR.iterdir():
        if not d.is_dir():
            continue
        name = d.name
        # exp_A-T1_rep1_... 패턴
        match = re.match(r"exp_(A|B|C|D)-T(\d+)_", name)
        if match:
            group = match.group(1)  # A or B
            traffic = f"T{match.group(2)}"  # T1, T2, T3
            key = traffic
            experiments[key][group] = d
    
    pairs = []
    for traffic, groups in experiments.items():
        if "A" in groups and "B" in groups:
            pairs.append((traffic, groups["A"], groups["B"]))
    
    return sorted(pairs)


def generate_training_data(pairs: list) -> list:
    """A/B 실험 쌍에서 라벨된 학습 데이터 생성"""
    training_data = []
    
    for traffic, a_dir, b_dir in pairs:
        print(f"\n[{traffic}] Comparing:")
        print(f"  A (ipvlan): {a_dir.name}")
        print(f"  B (macvlan): {b_dir.name}")
        
        a_kpis = load_kpi_from_dir(a_dir)
        b_kpis = load_kpi_from_dir(b_dir)
        
        if not a_kpis and not b_kpis:
            print(f"  ⚠ No KPI data found, skipping")
            continue
        
        a_avg = average_kpi(a_kpis)
        b_avg = average_kpi(b_kpis)
        
        label = label_from_comparison(a_avg, b_avg)
        score_a = compute_score(a_avg)
        score_b = compute_score(b_avg)
        
        print(f"  A score: {score_a:.2f} | B score: {score_b:.2f}")
        print(f"  → Label: {label}")
        
        # A 실험의 각 KPI 포인트에 라벨 부여
        for kpi in a_kpis:
            record = {f: kpi.get(f, 0) for f in FEATURES}
            record["label"] = label
            record["source_traffic"] = traffic
            training_data.append(record)
        
        # B 실험의 각 KPI 포인트에도 같은 라벨
        for kpi in b_kpis:
            record = {f: kpi.get(f, 0) for f in FEATURES}
            record["label"] = label
            record["source_traffic"] = traffic
            training_data.append(record)
    
    return training_data


def save_training_data(data: list, output: Path):
    """JSONL로 저장"""
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        for record in data:
            f.write(json.dumps(record) + "\n")
    print(f"\n[SAVED] {len(data)} samples → {output}")


def main():
    parser = argparse.ArgumentParser(description="Ground Truth 라벨링")
    parser.add_argument("--a-dir", type=str, help="ipvlan 고정 실험 디렉토리")
    parser.add_argument("--b-dir", type=str, help="macvlan 고정 실험 디렉토리")
    parser.add_argument("--auto", action="store_true", 
                        help="monitor-data에서 A/B 매칭 자동 탐색")
    parser.add_argument("--output", type=str, default=str(OUTPUT_FILE),
                        help=f"출력 파일 (default: {OUTPUT_FILE})")
    args = parser.parse_args()

    if args.auto:
        print("[AUTO] Searching for A/B experiment pairs in monitor-data/...")
        pairs = find_matching_experiments()
        if not pairs:
            print("  No matching A/B pairs found.")
            print(f"  Expected directory pattern: exp_A-T*_* and exp_B-T*_* in {MONITOR_DATA_DIR}")
            sys.exit(1)
        print(f"  Found {len(pairs)} pair(s): {[p[0] for p in pairs]}")
        data = generate_training_data(pairs)
    
    elif args.a_dir and args.b_dir:
        a_dir = Path(args.a_dir)
        b_dir = Path(args.b_dir)
        if not a_dir.exists() or not b_dir.exists():
            print(f"ERROR: Directory not found")
            sys.exit(1)
        pairs = [("manual", a_dir, b_dir)]
        data = generate_training_data(pairs)
    
    else:
        parser.print_help()
        sys.exit(1)
    
    if data:
        save_training_data(data, Path(args.output))
    else:
        print("\nNo training data generated. Run experiments first:")
        print("  ./run.sh --experiment experiments/experiment-a-t1.yaml")
        print("  ./run.sh --experiment experiments/experiment-b-t1.yaml")


if __name__ == "__main__":
    main()
