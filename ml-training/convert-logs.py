#!/usr/bin/env python3
"""
convert-logs.py — 실험 로그 → 학습 데이터셋 변환

monitor-collector 출력(resources.jsonl, packet_loss.jsonl)과
iperf3 결과를 합쳐서 NWDAF ML 학습에 필요한 통합 JSONL을 생성한다.

입력:
  monitor-data/{run_id}/pods/{upf_pod}/resources.jsonl
  monitor-data/{run_id}/pods/{upf_pod}/packet_loss.jsonl
  monitor-data/{run_id}/iperf3_result.json (또는 results/ 내 JSON)

출력:
  ml-training/data/{run_id}_features.jsonl
  (label은 label-data.py에서 별도 부여)

사용법:
    python3 convert-logs.py --run-dir monitor-data/exp_A-T1_rep1_20260809/
    python3 convert-logs.py --all    # monitor-data/ 전체 변환
"""

import argparse
import json
import os
import sys
from pathlib import Path
from collections import defaultdict

MONITOR_DATA_DIR = Path("/home/ubuntu/free5gc-k8s-arm/traffic-profiles/monitor-data")
OUTPUT_DIR = Path(__file__).parent / "data"

FEATURES = ["throughput_mbps", "packet_loss_pct", "total_pps", "cpu_milli", "mem_mi"]


def load_jsonl(filepath: Path) -> list:
    """JSONL 파일 로드"""
    data = []
    if not filepath.exists():
        return data
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return data


def load_iperf3_results(run_dir: Path) -> list:
    """iperf3 결과 파일에서 throughput 추출
    
    iperf3 JSON 출력 형식:
      .end.sum_received.bits_per_second → throughput
      또는 intervals[].sum.bits_per_second → 시계열
    """
    throughput_series = []
    
    # iperf3 결과 파일 찾기
    for json_file in run_dir.rglob("*.json"):
        if "iperf" in json_file.name.lower() or "result" in json_file.name.lower():
            try:
                with open(json_file, "r") as f:
                    data = json.load(f)
                
                # intervals 배열에서 시계열 추출
                if "intervals" in data:
                    for interval in data["intervals"]:
                        s = interval.get("sum", {})
                        bps = s.get("bits_per_second", 0)
                        throughput_series.append(bps / 1_000_000)  # Mbps
                
                # 또는 end.sum
                elif "end" in data:
                    bps = data["end"].get("sum_received", {}).get("bits_per_second", 0)
                    if bps > 0:
                        throughput_series.append(bps / 1_000_000)
            except (json.JSONDecodeError, KeyError):
                continue
    
    return throughput_series


def find_upf_pod_dir(run_dir: Path) -> Path:
    """실험 디렉토리에서 UPF pod 디렉토리 찾기"""
    pods_dir = run_dir / "pods"
    if not pods_dir.exists():
        return None
    
    for d in pods_dir.iterdir():
        if d.is_dir() and "upf" in d.name and "upf2" not in d.name:
            return d
    return None


def merge_timeseries(resources: list, packet_loss: list, throughput: list) -> list:
    """시계열 데이터를 시간 기준으로 병합하여 feature vector 생성
    
    각 소스의 샘플 수가 다를 수 있으므로, 인덱스 기반으로 매칭한다.
    (같은 interval로 수집되었다고 가정)
    """
    # 가장 긴 시계열 기준
    max_len = max(len(resources), len(packet_loss), len(throughput), 1)
    
    merged = []
    for i in range(max_len):
        record = {}
        
        # resources (cpu, mem)
        if i < len(resources):
            record["cpu_milli"] = resources[i].get("cpu_milli", 0)
            record["mem_mi"] = resources[i].get("mem_mi", 0)
        else:
            record["cpu_milli"] = resources[-1].get("cpu_milli", 0) if resources else 0
            record["mem_mi"] = resources[-1].get("mem_mi", 0) if resources else 0
        
        # packet_loss (loss_pct, pps)
        if i < len(packet_loss):
            record["packet_loss_pct"] = packet_loss[i].get("loss_pct", 0)
            rx = packet_loss[i].get("rx_packets", 0)
            tx = packet_loss[i].get("tx_packets", 0)
            record["total_pps"] = rx + tx
        else:
            record["packet_loss_pct"] = packet_loss[-1].get("loss_pct", 0) if packet_loss else 0
            record["total_pps"] = 0
        
        # throughput
        if i < len(throughput):
            record["throughput_mbps"] = round(throughput[i], 2)
        else:
            record["throughput_mbps"] = round(throughput[-1], 2) if throughput else 0
        
        # timestamp (있으면)
        if i < len(resources) and "ts" in resources[i]:
            record["ts"] = resources[i]["ts"]
        
        merged.append(record)
    
    return merged


def convert_run(run_dir: Path) -> list:
    """단일 실험 run을 feature vector 리스트로 변환"""
    upf_dir = find_upf_pod_dir(run_dir)
    
    if upf_dir is None:
        print(f"  ⚠ No UPF pod directory found in {run_dir}")
        return []
    
    # 로드
    resources = load_jsonl(upf_dir / "resources.jsonl")
    packet_loss = load_jsonl(upf_dir / "packet_loss.jsonl")
    throughput = load_iperf3_results(run_dir)
    
    print(f"  resources: {len(resources)} samples")
    print(f"  packet_loss: {len(packet_loss)} samples")
    print(f"  throughput: {len(throughput)} samples")
    
    if not resources and not packet_loss and not throughput:
        print(f"  ⚠ No data found")
        return []
    
    # 병합
    merged = merge_timeseries(resources, packet_loss, throughput)
    print(f"  → merged: {len(merged)} feature vectors")
    
    return merged


def save_features(data: list, output: Path):
    """JSONL로 저장"""
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        for record in data:
            f.write(json.dumps(record) + "\n")
    print(f"  [SAVED] {len(data)} vectors → {output}")


def main():
    parser = argparse.ArgumentParser(description="실험 로그 → 학습 데이터셋 변환")
    parser.add_argument("--run-dir", type=str, help="단일 실험 디렉토리")
    parser.add_argument("--all", action="store_true", help="monitor-data/ 전체 변환")
    parser.add_argument("--output-dir", type=str, default=str(OUTPUT_DIR),
                        help=f"출력 디렉토리 (default: {OUTPUT_DIR})")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    if args.all:
        if not MONITOR_DATA_DIR.exists():
            print(f"ERROR: {MONITOR_DATA_DIR} not found")
            print("Run experiments first:")
            print("  ./run.sh --experiment experiments/experiment-a-t1.yaml")
            sys.exit(1)
        
        all_data = []
        for d in sorted(MONITOR_DATA_DIR.iterdir()):
            if not d.is_dir():
                continue
            print(f"\n[{d.name}]")
            features = convert_run(d)
            if features:
                # run_id를 각 레코드에 추가
                for f in features:
                    f["run_id"] = d.name
                all_data.extend(features)
                save_features(features, output_dir / f"{d.name}_features.jsonl")
        
        if all_data:
            # 전체 합본도 저장
            save_features(all_data, output_dir / "all_features.jsonl")
            print(f"\n[TOTAL] {len(all_data)} vectors from {len(list(MONITOR_DATA_DIR.iterdir()))} runs")
        else:
            print("\nNo data converted. Check monitor-data/ contents.")

    elif args.run_dir:
        run_dir = Path(args.run_dir)
        if not run_dir.exists():
            print(f"ERROR: {run_dir} not found")
            sys.exit(1)
        print(f"[{run_dir.name}]")
        features = convert_run(run_dir)
        if features:
            save_features(features, output_dir / f"{run_dir.name}_features.jsonl")

    else:
        parser.print_help()
        print("\n전체 프로세스:")
        print("  1. 실험 실행:   ./run.sh --experiment experiments/experiment-a-t1.yaml")
        print("  2. 로그 변환:   python3 convert-logs.py --all")
        print("  3. 라벨링:      python3 label-data.py --auto")
        print("  4. 모델 학습:   python3 train-model.py --data data/training_data.jsonl")


if __name__ == "__main__":
    main()
