#!/usr/bin/env python3
"""
monitor-visualize.py — Pod별 리소스 사용량 & 패킷로스 시각화

monitoring-eyes 대시보드 패턴을 경량 matplotlib 차트로 구현.
수집된 JSONL 데이터를 읽어 PNG 차트를 생성합니다.

사용법:
    python3 monitor-visualize.py <monitor-data-dir>
    python3 monitor-visualize.py monitor-data/20260807_091500 --output charts/

출력:
    <output-dir>/
    ├── cpu_all_pods.png          # 전체 Pod CPU 시계열 (겹쳐그리기)
    ├── mem_all_pods.png          # 전체 Pod Memory 시계열
    ├── packet_loss_upf.png       # UPF 패킷로스 시계열
    ├── cpu_per_pod/              # Pod별 개별 차트
    │   ├── free5gc-upf-xxx.png
    │   └── ...
    └── summary.json              # 요약 통계 (mean, max, p99)
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import matplotlib
    matplotlib.use('Agg')  # headless
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
except ImportError:
    print("ERROR: matplotlib not installed. Run: pip3 install matplotlib")
    sys.exit(1)


# ═══════════════════════════════════════════════════════
# 데이터 로딩
# ═══════════════════════════════════════════════════════

def load_jsonl(filepath):
    """JSONL 파일 → list of dict"""
    data = []
    if not os.path.exists(filepath):
        return data
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    data.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return data


def parse_timestamp(ts_str):
    """ISO timestamp → datetime"""
    try:
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return None


def load_all_pods(data_dir):
    """전체 Pod 데이터 로딩"""
    pods_dir = Path(data_dir) / "pods"
    if not pods_dir.exists():
        return {}

    pods = {}
    for pod_dir in sorted(pods_dir.iterdir()):
        if pod_dir.is_dir():
            pod_name = pod_dir.name
            pods[pod_name] = {
                "resources": load_jsonl(pod_dir / "resources.jsonl"),
                "packet_loss": load_jsonl(pod_dir / "packet_loss.jsonl"),
                "iface_stats": load_jsonl(pod_dir / "iface_stats.jsonl"),
            }
    return pods


# ═══════════════════════════════════════════════════════
# 차트 생성
# ═══════════════════════════════════════════════════════

# 색상 팔레트 (NF별)
NF_COLORS = {
    "upf": "#e74c3c",
    "smf": "#3498db",
    "amf": "#2ecc71",
    "nrf": "#9b59b6",
    "ausf": "#f39c12",
    "udm": "#1abc9c",
    "udr": "#34495e",
    "pcf": "#e67e22",
    "nssf": "#95a5a6",
    "gnb": "#2c3e50",
    "ue": "#8e44ad",
}


def get_pod_color(pod_name):
    """Pod 이름에서 NF 타입 추출 → 색상 매핑"""
    for nf, color in NF_COLORS.items():
        if nf in pod_name.lower():
            return color
    return "#7f8c8d"


def plot_cpu_all(pods, output_dir):
    """전체 Pod CPU 시계열 — 한 차트에 겹침"""
    fig, ax = plt.subplots(figsize=(14, 6))

    for pod_name, data in pods.items():
        resources = data["resources"]
        if not resources:
            continue

        times = [parse_timestamp(r["ts"]) for r in resources]
        cpus = [r["cpu_milli"] for r in resources]

        times = [t for t in times if t is not None]
        if not times:
            continue

        # Pod 이름 축약 (긴 hash 제거)
        short_name = pod_name[:30] if len(pod_name) > 30 else pod_name
        ax.plot(times[:len(cpus)], cpus, label=short_name,
                color=get_pod_color(pod_name), linewidth=1.2, alpha=0.8)

    ax.set_xlabel("Time")
    ax.set_ylabel("CPU (millicores)")
    ax.set_title("Pod CPU Usage Over Time")
    ax.legend(loc='upper left', fontsize=7, ncol=2)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    fig.autofmt_xdate()
    plt.tight_layout()

    filepath = Path(output_dir) / "cpu_all_pods.png"
    fig.savefig(filepath, dpi=150)
    plt.close(fig)
    print(f"  ✓ {filepath}")


def plot_mem_all(pods, output_dir):
    """전체 Pod Memory 시계열"""
    fig, ax = plt.subplots(figsize=(14, 6))

    for pod_name, data in pods.items():
        resources = data["resources"]
        if not resources:
            continue

        times = [parse_timestamp(r["ts"]) for r in resources]
        mems = [r["mem_mi"] for r in resources]

        times = [t for t in times if t is not None]
        if not times:
            continue

        short_name = pod_name[:30]
        ax.plot(times[:len(mems)], mems, label=short_name,
                color=get_pod_color(pod_name), linewidth=1.2, alpha=0.8)

    ax.set_xlabel("Time")
    ax.set_ylabel("Memory (Mi)")
    ax.set_title("Pod Memory Usage Over Time")
    ax.legend(loc='upper left', fontsize=7, ncol=2)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    fig.autofmt_xdate()
    plt.tight_layout()

    filepath = Path(output_dir) / "mem_all_pods.png"
    fig.savefig(filepath, dpi=150)
    plt.close(fig)
    print(f"  ✓ {filepath}")


def plot_packet_loss(pods, output_dir):
    """UPF 패킷로스 시계열"""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    has_data = False
    for pod_name, data in pods.items():
        if "upf" not in pod_name.lower():
            continue

        pl_data = data["packet_loss"]
        if not pl_data:
            continue

        has_data = True
        times = [parse_timestamp(r["ts"]) for r in pl_data]
        loss_pct = [r.get("loss_pct", 0) for r in pl_data]
        rx_pkts = [r.get("rx_packets", 0) for r in pl_data]
        tx_pkts = [r.get("tx_packets", 0) for r in pl_data]

        times = [t for t in times if t is not None]

        # 상단: 패킷로스율
        ax1.plot(times[:len(loss_pct)], loss_pct, label=pod_name[:25],
                 color="#e74c3c", linewidth=1.5)

        # 하단: 패킷 카운터 (delta로 변환하여 pps 추정)
        rx_delta = [0] + [max(0, rx_pkts[i] - rx_pkts[i-1]) for i in range(1, len(rx_pkts))]
        tx_delta = [0] + [max(0, tx_pkts[i] - tx_pkts[i-1]) for i in range(1, len(tx_pkts))]
        ax2.plot(times[:len(rx_delta)], rx_delta, label=f"{pod_name[:20]} RX",
                 color="#3498db", linewidth=1, alpha=0.8)
        ax2.plot(times[:len(tx_delta)], tx_delta, label=f"{pod_name[:20]} TX",
                 color="#2ecc71", linewidth=1, alpha=0.8)

    if not has_data:
        plt.close(fig)
        return

    ax1.set_ylabel("Packet Loss (%)")
    ax1.set_title("UPF Packet Loss Rate")
    ax1.legend(fontsize=8)
    ax1.grid(True, alpha=0.3)
    ax1.axhline(y=1.0, color='orange', linestyle='--', alpha=0.5, label='1% threshold')

    ax2.set_xlabel("Time")
    ax2.set_ylabel("Packets (delta per interval)")
    ax2.set_title("UPF Packet Counter (RX/TX delta)")
    ax2.legend(fontsize=8)
    ax2.grid(True, alpha=0.3)

    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    fig.autofmt_xdate()
    plt.tight_layout()

    filepath = Path(output_dir) / "packet_loss_upf.png"
    fig.savefig(filepath, dpi=150)
    plt.close(fig)
    print(f"  ✓ {filepath}")


def plot_per_pod(pods, output_dir):
    """Pod별 개별 CPU+Mem 차트"""
    per_pod_dir = Path(output_dir) / "cpu_per_pod"
    per_pod_dir.mkdir(parents=True, exist_ok=True)

    for pod_name, data in pods.items():
        resources = data["resources"]
        if len(resources) < 3:
            continue

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)

        times = [parse_timestamp(r["ts"]) for r in resources]
        cpus = [r["cpu_milli"] for r in resources]
        mems = [r["mem_mi"] for r in resources]
        times = [t for t in times if t is not None]

        color = get_pod_color(pod_name)

        ax1.plot(times[:len(cpus)], cpus, color=color, linewidth=1.2)
        ax1.fill_between(times[:len(cpus)], cpus, alpha=0.1, color=color)
        ax1.set_ylabel("CPU (m)")
        ax1.set_title(f"{pod_name}")
        ax1.grid(True, alpha=0.3)

        ax2.plot(times[:len(mems)], mems, color=color, linewidth=1.2)
        ax2.fill_between(times[:len(mems)], mems, alpha=0.1, color=color)
        ax2.set_ylabel("Memory (Mi)")
        ax2.set_xlabel("Time")
        ax2.grid(True, alpha=0.3)

        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        fig.autofmt_xdate()
        plt.tight_layout()

        # 파일명에서 위험 문자 제거
        safe_name = pod_name.replace("/", "_").replace(" ", "_")[:50]
        filepath = per_pod_dir / f"{safe_name}.png"
        fig.savefig(filepath, dpi=120)
        plt.close(fig)

    print(f"  ✓ {per_pod_dir}/ ({len(list(per_pod_dir.iterdir()))} files)")


# ═══════════════════════════════════════════════════════
# 요약 통계
# ═══════════════════════════════════════════════════════

def compute_summary(pods):
    """Pod별 요약 통계 (mean, max, p99) — monitoring-eyes의 checkpoint 스타일"""
    summary = {}
    for pod_name, data in pods.items():
        resources = data["resources"]
        if not resources:
            continue

        cpus = [r["cpu_milli"] for r in resources]
        mems = [r["mem_mi"] for r in resources]

        def percentile(values, p):
            sorted_v = sorted(values)
            idx = int(len(sorted_v) * p / 100)
            return sorted_v[min(idx, len(sorted_v) - 1)]

        pod_summary = {
            "samples": len(resources),
            "cpu_milli": {
                "mean": round(sum(cpus) / len(cpus), 1),
                "max": max(cpus),
                "p99": percentile(cpus, 99),
            },
            "mem_mi": {
                "mean": round(sum(mems) / len(mems), 1),
                "max": max(mems),
                "p99": percentile(mems, 99),
            },
        }

        # 패킷로스 통계
        pl_data = data["packet_loss"]
        if pl_data:
            losses = [r.get("loss_pct", 0) for r in pl_data]
            pod_summary["packet_loss_pct"] = {
                "mean": round(sum(losses) / len(losses), 4),
                "max": round(max(losses), 4),
                "p99": round(percentile(losses, 99), 4),
            }

        summary[pod_name] = pod_summary

    return summary


# ═══════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 monitor-visualize.py <monitor-data-dir> [--output <dir>]")
        sys.exit(1)

    data_dir = sys.argv[1]
    output_dir = data_dir  # 기본: 데이터 디렉토리에 차트 저장

    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        output_dir = sys.argv[idx + 1]

    if not os.path.isdir(data_dir):
        print(f"ERROR: Directory not found: {data_dir}")
        sys.exit(1)

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    print(f"\n{'═' * 50}")
    print(f"  Monitor Visualizer")
    print(f"  Input:  {data_dir}")
    print(f"  Output: {output_dir}")
    print(f"{'═' * 50}\n")

    # 데이터 로딩
    print("[1/5] Loading data...")
    pods = load_all_pods(data_dir)
    if not pods:
        print("  No pod data found.")
        sys.exit(1)
    print(f"  Found {len(pods)} pods")

    # 차트 생성
    print("[2/5] Generating CPU chart...")
    plot_cpu_all(pods, output_dir)

    print("[3/5] Generating Memory chart...")
    plot_mem_all(pods, output_dir)

    print("[4/5] Generating Packet Loss chart...")
    plot_packet_loss(pods, output_dir)

    print("[5/5] Generating per-pod charts...")
    plot_per_pod(pods, output_dir)

    # 요약 통계
    print("\nComputing summary statistics...")
    summary = compute_summary(pods)
    summary_path = Path(output_dir) / "summary.json"
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"  ✓ {summary_path}")

    # 콘솔 요약 출력
    print(f"\n{'─' * 60}")
    print(f"{'Pod':<30} {'CPU avg':<10} {'CPU max':<10} {'Mem avg':<10} {'Loss%':<8}")
    print(f"{'─' * 60}")
    for pod_name, s in sorted(summary.items()):
        loss = s.get("packet_loss_pct", {}).get("mean", "—")
        print(f"{pod_name[:29]:<30} "
              f"{s['cpu_milli']['mean']:<10} "
              f"{s['cpu_milli']['max']:<10} "
              f"{s['mem_mi']['mean']:<10} "
              f"{str(loss):<8}")
    print(f"{'─' * 60}")
    print(f"\nDone. Charts saved to: {output_dir}/\n")


if __name__ == "__main__":
    main()
