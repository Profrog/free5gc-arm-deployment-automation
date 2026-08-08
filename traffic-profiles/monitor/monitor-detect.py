#!/usr/bin/env python3
"""
monitor-detect.py — KPI 이상 탐지 (monitoring-eyes rule-based 패턴)

monitoring-eyes의 anomaly detection 알고리즘 차용:
  - CPU: ±2 절대값 (baseline 대비)
  - Memory: ±2% (baseline 대비)
  - Packet Loss: ratio 공식 (loss_total * 5 / sent_total) 또는 절대 threshold
  - Throughput: ±2% (baseline 대비)

Decision Tree (monitoring-eyes 5.3절):
  KPI 변화 감지
    ├── Degradation → 값이 나빠진 방향
    │   ├── 모든 Pod에서 발생? → SW/Config 이슈
    │   ├── 특정 Pod만? → Pod 리소스 문제
    │   └── 간헐적? → 모니터링 지속
    └── Improvement → 의도된 최적화 vs 기능 오작동

사용법:
    python3 monitor-detect.py <monitor-data-dir> [--baseline <prev-run-dir>]
    python3 monitor-detect.py monitor-data/20260807_091500

출력:
    <monitor-data-dir>/anomalies.json
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path


# ═══════════════════════════════════════════════════════
# Rule 정의 (monitoring-eyes tunning_rule.txt 패턴)
# ═══════════════════════════════════════════════════════

RULES = {
    "cpu_milli": {
        "type": "absolute",
        "margin": 20,          # ±20m (monitoring-eyes는 ±2 for %, 여기선 millicores)
        "direction": "higher_is_worse",
        "alert_threshold": 500,  # 500m 이상이면 무조건 경고
        "description": "CPU usage in millicores",
    },
    "mem_mi": {
        "type": "relative_percent",
        "margin_pct": 0.05,    # ±5% (메모리는 좀 더 여유)
        "direction": "higher_is_worse",
        "alert_threshold": 512,  # 512Mi 이상이면 경고 (ARM64 제한 환경)
        "description": "Memory usage in MiB",
    },
    "packet_loss_pct": {
        "type": "absolute",
        "margin": 1.0,         # ±1% (loss는 절대값으로)
        "direction": "higher_is_worse",
        "alert_threshold": 5.0,  # 5% 이상이면 critical
        "critical_threshold": 20.0,  # 20% 이상이면 UPF 한계 초과
        "description": "Packet loss percentage",
    },
}


# ═══════════════════════════════════════════════════════
# 이상 탐지 로직
# ═══════════════════════════════════════════════════════

class AnomalyDetector:
    """monitoring-eyes 5.1절 알고리즘 구현"""

    def __init__(self, rules=None):
        self.rules = rules or RULES
        self.anomalies = []

    def check_absolute(self, kpi_name, values, rule, pod_name):
        """절대값 기반 탐지: baseline ± margin"""
        if not values:
            return

        # Baseline = 초반 20% 평균 (안정 구간)
        warmup = max(1, len(values) // 5)
        baseline = sum(values[:warmup]) / warmup

        margin = rule["margin"]
        threshold_upper = baseline + margin
        alert_threshold = rule.get("alert_threshold", float('inf'))
        critical_threshold = rule.get("critical_threshold", float('inf'))

        for i, val in enumerate(values):
            severity = None
            reason = None

            if val >= critical_threshold:
                severity = "CRITICAL"
                reason = f"{kpi_name}={val} >= critical({critical_threshold})"
            elif val >= alert_threshold:
                severity = "WARNING"
                reason = f"{kpi_name}={val} >= alert({alert_threshold})"
            elif val > threshold_upper:
                severity = "DEGRADATION"
                reason = f"{kpi_name}={val:.1f} > baseline({baseline:.1f}) + margin({margin})"

            if severity:
                self.anomalies.append({
                    "pod": pod_name,
                    "kpi": kpi_name,
                    "severity": severity,
                    "reason": reason,
                    "value": val,
                    "baseline": round(baseline, 2),
                    "threshold": round(threshold_upper, 2),
                    "sample_index": i,
                    "total_samples": len(values),
                })

    def check_relative(self, kpi_name, values, rule, pod_name):
        """비율 기반 탐지: baseline × (1 ± margin_pct)"""
        if not values:
            return

        warmup = max(1, len(values) // 5)
        baseline = sum(values[:warmup]) / warmup

        if baseline == 0:
            return

        margin_pct = rule["margin_pct"]
        threshold_upper = baseline * (1 + margin_pct)
        alert_threshold = rule.get("alert_threshold", float('inf'))

        for i, val in enumerate(values):
            severity = None
            reason = None

            if val >= alert_threshold:
                severity = "WARNING"
                reason = f"{kpi_name}={val}Mi >= alert({alert_threshold}Mi)"
            elif val > threshold_upper:
                pct_change = ((val - baseline) / baseline) * 100
                severity = "DEGRADATION"
                reason = f"{kpi_name}={val:.1f}Mi, +{pct_change:.1f}% from baseline({baseline:.1f}Mi)"

            if severity:
                self.anomalies.append({
                    "pod": pod_name,
                    "kpi": kpi_name,
                    "severity": severity,
                    "reason": reason,
                    "value": val,
                    "baseline": round(baseline, 2),
                    "threshold": round(threshold_upper, 2),
                    "sample_index": i,
                    "total_samples": len(values),
                })

    def check_pod(self, pod_name, resources, packet_loss):
        """단일 Pod 검사"""
        # CPU 검사
        if resources:
            cpu_values = [r["cpu_milli"] for r in resources]
            self.check_absolute("cpu_milli", cpu_values, self.rules["cpu_milli"], pod_name)

            # Memory 검사
            mem_values = [r["mem_mi"] for r in resources]
            self.check_relative("mem_mi", mem_values, self.rules["mem_mi"], pod_name)

        # Packet Loss 검사 (UPF만)
        if packet_loss:
            loss_values = [r.get("loss_pct", 0) for r in packet_loss]
            self.check_absolute("packet_loss_pct", loss_values,
                              self.rules["packet_loss_pct"], pod_name)

    def detect_trends(self, pod_name, resources):
        """
        추세 감지: 시간이 지남에 따라 값이 계속 증가하는지 (메모리 릭 패턴)
        monitoring-eyes의 "Improvement도 이상" 개념 적용
        """
        if not resources or len(resources) < 10:
            return

        mem_values = [r["mem_mi"] for r in resources]

        # 단순 선형 추세: 후반 20% 평균 vs 초반 20% 평균
        chunk = max(1, len(mem_values) // 5)
        first_avg = sum(mem_values[:chunk]) / chunk
        last_avg = sum(mem_values[-chunk:]) / chunk

        if first_avg > 0:
            growth_pct = ((last_avg - first_avg) / first_avg) * 100
            if growth_pct > 10:  # 10% 이상 성장
                self.anomalies.append({
                    "pod": pod_name,
                    "kpi": "mem_trend",
                    "severity": "WARNING",
                    "reason": f"Memory growing trend: {first_avg:.0f}Mi → {last_avg:.0f}Mi (+{growth_pct:.1f}%)",
                    "value": round(last_avg, 1),
                    "baseline": round(first_avg, 1),
                    "threshold": round(first_avg * 1.1, 1),
                    "sample_index": len(mem_values) - 1,
                    "total_samples": len(mem_values),
                })

    def classify_anomaly(self):
        """
        monitoring-eyes 5.3절 분류:
        모든 Pod에서 발생 → SYSTEM_WIDE
        특정 Pod만 → POD_SPECIFIC
        """
        if not self.anomalies:
            return "NORMAL", []

        # Pod별로 그룹핑
        pod_set = set(a["pod"] for a in self.anomalies)
        critical = [a for a in self.anomalies if a["severity"] == "CRITICAL"]
        warnings = [a for a in self.anomalies if a["severity"] == "WARNING"]
        degradations = [a for a in self.anomalies if a["severity"] == "DEGRADATION"]

        if critical:
            return "CRITICAL", critical
        elif len(pod_set) > 3 and warnings:
            return "SYSTEM_WIDE", warnings
        elif warnings or degradations:
            return "POD_SPECIFIC", warnings + degradations
        else:
            return "NORMAL", []

    def generate_report(self):
        """최종 보고서 생성"""
        classification, key_anomalies = self.classify_anomaly()

        # 중복 제거 (같은 Pod/KPI → 최악의 것만)
        deduped = {}
        for a in self.anomalies:
            key = f"{a['pod']}_{a['kpi']}"
            if key not in deduped or a["value"] > deduped[key]["value"]:
                deduped[key] = a

        report = {
            "classification": classification,
            "total_anomalies": len(deduped),
            "severity_counts": {
                "CRITICAL": len([a for a in deduped.values() if a["severity"] == "CRITICAL"]),
                "WARNING": len([a for a in deduped.values() if a["severity"] == "WARNING"]),
                "DEGRADATION": len([a for a in deduped.values() if a["severity"] == "DEGRADATION"]),
            },
            "anomalies": list(deduped.values()),
            "rules_applied": {k: v["description"] for k, v in self.rules.items()},
        }

        return report


# ═══════════════════════════════════════════════════════
# 데이터 로딩 (monitor-visualize.py와 동일)
# ═══════════════════════════════════════════════════════

def load_jsonl(filepath):
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


def load_all_pods(data_dir):
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
            }
    return pods


# ═══════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 monitor-detect.py <monitor-data-dir>")
        sys.exit(1)

    data_dir = sys.argv[1]
    if not os.path.isdir(data_dir):
        print(f"ERROR: Directory not found: {data_dir}")
        sys.exit(1)

    print(f"\n{'═' * 50}")
    print(f"  Anomaly Detection (monitoring-eyes rule-based)")
    print(f"  Input: {data_dir}")
    print(f"{'═' * 50}\n")

    # 데이터 로딩
    pods = load_all_pods(data_dir)
    if not pods:
        print("  No pod data found.")
        sys.exit(1)
    print(f"  Loaded {len(pods)} pods\n")

    # 탐지 실행
    detector = AnomalyDetector()

    for pod_name, data in pods.items():
        detector.check_pod(pod_name, data["resources"], data["packet_loss"])
        detector.detect_trends(pod_name, data["resources"])

    # 보고서 생성
    report = detector.generate_report()

    # 파일 저장
    output_path = Path(data_dir) / "anomalies.json"
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)

    # 콘솔 출력
    print(f"  Classification: {report['classification']}")
    print(f"  Total anomalies: {report['total_anomalies']}")
    print(f"  CRITICAL: {report['severity_counts']['CRITICAL']}")
    print(f"  WARNING:  {report['severity_counts']['WARNING']}")
    print(f"  DEGRADATION: {report['severity_counts']['DEGRADATION']}")

    if report["anomalies"]:
        print(f"\n{'─' * 70}")
        print(f"{'Severity':<12} {'Pod':<25} {'KPI':<18} {'Value':<10} {'Reason'}")
        print(f"{'─' * 70}")
        for a in sorted(report["anomalies"], key=lambda x: x["severity"]):
            print(f"{a['severity']:<12} {a['pod'][:24]:<25} {a['kpi']:<18} "
                  f"{a['value']:<10} {a['reason'][:40]}")
        print(f"{'─' * 70}")

    print(f"\n  Report saved: {output_path}\n")

    # Exit code: 0=normal, 1=degradation, 2=critical
    if report["classification"] == "CRITICAL":
        sys.exit(2)
    elif report["classification"] != "NORMAL":
        sys.exit(1)
    else:
        print("  ✓ No anomalies detected.")
        sys.exit(0)


if __name__ == "__main__":
    main()
