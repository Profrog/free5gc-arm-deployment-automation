"""
free5gc UPF Monitor Dashboard — Streamlit App
접속: http://152.69.227.31:8501

테스트 실행 결과(monitor-data/)를 시각화하는 대시보드.
- Pod별 CPU/Memory 시계열
- UPF Packet Loss
- Anomaly Detection 결과
- Run 간 비교
"""

import streamlit as st
import json
import os
from pathlib import Path
from datetime import datetime

st.set_page_config(
    page_title="free5gc UPF Monitor",
    page_icon="📡",
    layout="wide",
)

# ═══════════════════════════════════════════════════════
# 설정
# ═══════════════════════════════════════════════════════
MONITOR_DATA_DIR = Path("/home/ubuntu/free5gc-k8s-arm/traffic-profiles/monitor-data")
PROFILES_DIR = Path("/home/ubuntu/free5gc-k8s-arm/traffic-profiles/profiles")


# ═══════════════════════════════════════════════════════
# 데이터 로딩
# ═══════════════════════════════════════════════════════

def get_available_runs():
    """사용 가능한 테스트 실행 목록"""
    if not MONITOR_DATA_DIR.exists():
        return []
    runs = []
    for d in sorted(MONITOR_DATA_DIR.iterdir(), reverse=True):
        if d.is_dir() and (d / "metadata.json").exists():
            runs.append(d.name)
    return runs


def load_jsonl(filepath):
    data = []
    if not filepath.exists():
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


def load_run_data(run_id):
    """특정 run의 전체 데이터 로딩"""
    run_dir = MONITOR_DATA_DIR / run_id
    pods_dir = run_dir / "pods"

    metadata = {}
    if (run_dir / "metadata.json").exists():
        with open(run_dir / "metadata.json") as f:
            metadata = json.load(f)

    summary = {}
    if (run_dir / "summary.json").exists():
        with open(run_dir / "summary.json") as f:
            summary = json.load(f)

    anomalies = {}
    if (run_dir / "anomalies.json").exists():
        with open(run_dir / "anomalies.json") as f:
            anomalies = json.load(f)

    pods = {}
    if pods_dir.exists():
        for pod_dir in sorted(pods_dir.iterdir()):
            if pod_dir.is_dir():
                pods[pod_dir.name] = {
                    "resources": load_jsonl(pod_dir / "resources.jsonl"),
                    "packet_loss": load_jsonl(pod_dir / "packet_loss.jsonl"),
                }

    return metadata, summary, anomalies, pods


# ═══════════════════════════════════════════════════════
# NF 색상
# ═══════════════════════════════════════════════════════
NF_COLORS = {
    "upf": "#e74c3c", "smf": "#3498db", "amf": "#2ecc71",
    "nrf": "#9b59b6", "ausf": "#f39c12", "udm": "#1abc9c",
    "udr": "#34495e", "pcf": "#e67e22", "nssf": "#95a5a6",
    "gnb": "#2c3e50", "ue": "#8e44ad",
}


def get_nf_type(pod_name):
    for nf in NF_COLORS:
        if nf in pod_name.lower():
            return nf
    return "unknown"


# ═══════════════════════════════════════════════════════
# UI 렌더링
# ═══════════════════════════════════════════════════════

st.title("📡 free5gc UPF Monitor Dashboard")
st.caption("APN Profile 기반 트래픽 테스트 모니터링")

# 사이드바: Run 선택
with st.sidebar:
    st.header("🔍 Test Run 선택")

    runs = get_available_runs()
    if not runs:
        st.warning("아직 테스트 데이터가 없습니다.\n\n"
                   "```bash\n"
                   "cd /home/ubuntu/free5gc-k8s-arm/traffic-profiles\n"
                   "./run.sh profiles/upf-stress.yaml\n"
                   "```")
        st.stop()

    selected_run = st.selectbox("Run ID", runs)

    st.divider()
    st.header("📋 프로파일 목록")
    if PROFILES_DIR.exists():
        for p in sorted(PROFILES_DIR.glob("*.yaml")):
            if p.name != "schema.yaml":
                st.code(p.name, language=None)

# 데이터 로딩
metadata, summary, anomalies, pods = load_run_data(selected_run)

# ── 상단: 메타정보 & 요약 ──
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("⏱ Duration", f"{metadata.get('duration_sec', '?')}s")
with col2:
    st.metric("📊 Samples", metadata.get('total_samples', '?'))
with col3:
    st.metric("🏗 Pods", metadata.get('pods_monitored', len(pods)))
with col4:
    classification = anomalies.get('classification', 'N/A')
    color = "🟢" if classification == "NORMAL" else "🟡" if classification == "POD_SPECIFIC" else "🔴"
    st.metric(f"{color} Status", classification)

st.divider()

# ── 탭 구성 ──
tab_cpu, tab_mem, tab_loss, tab_anomaly, tab_summary, tab_compare = st.tabs(
    ["📈 CPU", "💾 Memory", "📉 Packet Loss", "⚠️ Anomalies", "📋 Summary", "🔀 Compare"]
)

# ── CPU 탭 ──
with tab_cpu:
    st.subheader("Pod별 CPU 사용량 (millicores)")

    if pods:
        import pandas as pd

        chart_data = {}
        for pod_name, data in pods.items():
            resources = data["resources"]
            if resources:
                cpus = [r["cpu_milli"] for r in resources]
                # 시간축 생성 (인덱스 기반)
                chart_data[pod_name[:25]] = cpus

        if chart_data:
            # 길이 맞추기
            max_len = max(len(v) for v in chart_data.values())
            for k in chart_data:
                chart_data[k] = chart_data[k] + [None] * (max_len - len(chart_data[k]))

            df = pd.DataFrame(chart_data)
            st.line_chart(df, height=400)

            # 선택한 Pod 상세
            selected_pod = st.selectbox("Pod 상세 보기", list(pods.keys()), key="cpu_pod")
            if selected_pod and pods[selected_pod]["resources"]:
                res = pods[selected_pod]["resources"]
                cpus = [r["cpu_milli"] for r in res]
                st.line_chart(cpus, height=200)
                st.caption(f"Mean: {sum(cpus)/len(cpus):.1f}m | Max: {max(cpus)}m | Samples: {len(cpus)}")

# ── Memory 탭 ──
with tab_mem:
    st.subheader("Pod별 Memory 사용량 (MiB)")

    if pods:
        chart_data = {}
        for pod_name, data in pods.items():
            resources = data["resources"]
            if resources:
                mems = [r["mem_mi"] for r in resources]
                chart_data[pod_name[:25]] = mems

        if chart_data:
            max_len = max(len(v) for v in chart_data.values())
            for k in chart_data:
                chart_data[k] = chart_data[k] + [None] * (max_len - len(chart_data[k]))

            df = pd.DataFrame(chart_data)
            st.line_chart(df, height=400)

# ── Packet Loss 탭 ──
with tab_loss:
    st.subheader("UPF Packet Loss")

    upf_pods = {k: v for k, v in pods.items() if "upf" in k.lower()}
    if upf_pods:
        for pod_name, data in upf_pods.items():
            pl = data["packet_loss"]
            if pl:
                st.write(f"**{pod_name}**")
                losses = [r.get("loss_pct", 0) for r in pl]
                st.line_chart(losses, height=200)

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Mean Loss", f"{sum(losses)/len(losses):.4f}%")
                with col2:
                    st.metric("Max Loss", f"{max(losses):.4f}%")
                with col3:
                    st.metric("Samples", len(losses))
    else:
        st.info("UPF packet loss 데이터 없음")

# ── Anomaly 탭 ──
with tab_anomaly:
    st.subheader("이상 탐지 결과")

    if anomalies:
        severity_counts = anomalies.get("severity_counts", {})
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("🔴 CRITICAL", severity_counts.get("CRITICAL", 0))
        with col2:
            st.metric("🟡 WARNING", severity_counts.get("WARNING", 0))
        with col3:
            st.metric("🟠 DEGRADATION", severity_counts.get("DEGRADATION", 0))

        anomaly_list = anomalies.get("anomalies", [])
        if anomaly_list:
            st.dataframe(
                [{"Severity": a["severity"], "Pod": a["pod"][:30],
                  "KPI": a["kpi"], "Value": a["value"],
                  "Baseline": a["baseline"], "Reason": a["reason"][:50]}
                 for a in anomaly_list],
                use_container_width=True,
            )
        else:
            st.success("✓ 이상 없음")
    else:
        st.info("anomaly detection 미실행")

# ── Summary 탭 ──
with tab_summary:
    st.subheader("Pod별 통계 요약")

    if summary:
        rows = []
        for pod_name, s in sorted(summary.items()):
            row = {
                "Pod": pod_name[:30],
                "CPU Mean (m)": s["cpu_milli"]["mean"],
                "CPU Max (m)": s["cpu_milli"]["max"],
                "CPU p99 (m)": s["cpu_milli"]["p99"],
                "Mem Mean (Mi)": s["mem_mi"]["mean"],
                "Mem Max (Mi)": s["mem_mi"]["max"],
            }
            if "packet_loss_pct" in s:
                row["Loss Mean (%)"] = s["packet_loss_pct"]["mean"]
                row["Loss Max (%)"] = s["packet_loss_pct"]["max"]
            rows.append(row)

        st.dataframe(rows, use_container_width=True)
    else:
        st.info("summary.json 미생성 (시각화 스크립트 실행 필요)")

    # Raw metadata
    with st.expander("📄 Run Metadata"):
        st.json(metadata)

# ── 하단 ──
st.divider()

# ── Compare 탭 ──
with tab_compare:
    st.subheader("🔀 Run 간 비교")
    st.caption("두 개 이상의 Run을 선택하여 동일 그래프에서 KPI를 비교합니다.")

    compare_runs = st.multiselect("비교할 Run 선택", runs, default=[selected_run] if runs else [])

    if len(compare_runs) < 2:
        st.info("2개 이상의 Run을 선택하세요.")
    else:
        import pandas as pd

        # CPU 비교
        st.markdown("### CPU 사용량 비교 (UPF)")
        cpu_compare = {}
        for run_id in compare_runs:
            _, _, _, run_pods = load_run_data(run_id)
            for pod_name, data in run_pods.items():
                if "upf" in pod_name.lower() and data["resources"]:
                    cpus = [r["cpu_milli"] for r in data["resources"]]
                    label = f"{run_id[:30]}"
                    cpu_compare[label] = cpus
                    break

        if cpu_compare:
            max_len = max(len(v) for v in cpu_compare.values())
            for k in cpu_compare:
                cpu_compare[k] = cpu_compare[k] + [None] * (max_len - len(cpu_compare[k]))
            df = pd.DataFrame(cpu_compare)
            st.line_chart(df, height=400)
        else:
            st.warning("UPF CPU 데이터 없음")

        # Packet Loss 비교
        st.markdown("### Packet Loss 비교 (UPF)")
        loss_compare = {}
        for run_id in compare_runs:
            _, _, _, run_pods = load_run_data(run_id)
            for pod_name, data in run_pods.items():
                if "upf" in pod_name.lower() and data["packet_loss"]:
                    losses = [r.get("loss_pct", 0) for r in data["packet_loss"]]
                    label = f"{run_id[:30]}"
                    loss_compare[label] = losses
                    break

        if loss_compare:
            max_len = max(len(v) for v in loss_compare.values())
            for k in loss_compare:
                loss_compare[k] = loss_compare[k] + [None] * (max_len - len(loss_compare[k]))
            df = pd.DataFrame(loss_compare)
            st.line_chart(df, height=400)
        else:
            st.warning("UPF Packet Loss 데이터 없음")

        # Memory 비교
        st.markdown("### Memory 비교 (UPF)")
        mem_compare = {}
        for run_id in compare_runs:
            _, _, _, run_pods = load_run_data(run_id)
            for pod_name, data in run_pods.items():
                if "upf" in pod_name.lower() and data["resources"]:
                    mems = [r["mem_mi"] for r in data["resources"]]
                    label = f"{run_id[:30]}"
                    mem_compare[label] = mems
                    break

        if mem_compare:
            max_len = max(len(v) for v in mem_compare.values())
            for k in mem_compare:
                mem_compare[k] = mem_compare[k] + [None] * (max_len - len(mem_compare[k]))
            df = pd.DataFrame(mem_compare)
            st.line_chart(df, height=400)
        else:
            st.warning("UPF Memory 데이터 없음")

        # 요약 테이블
        st.markdown("### 요약 비교")
        summary_rows = []
        for run_id in compare_runs:
            _, _, _, run_pods = load_run_data(run_id)
            for pod_name, data in run_pods.items():
                if "upf" in pod_name.lower():
                    row = {"Run": run_id[:30]}
                    if data["resources"]:
                        cpus = [r["cpu_milli"] for r in data["resources"]]
                        row["CPU Mean (m)"] = round(sum(cpus) / len(cpus), 1)
                        row["CPU Max (m)"] = max(cpus)
                    if data["packet_loss"]:
                        losses = [r.get("loss_pct", 0) for r in data["packet_loss"]]
                        row["Loss Mean (%)"] = round(sum(losses) / len(losses), 4)
                        row["Loss Max (%)"] = round(max(losses), 4)
                    summary_rows.append(row)
                    break

        if summary_rows:
            st.dataframe(summary_rows, use_container_width=True)

st.caption(f"Monitor Data: `{MONITOR_DATA_DIR}/{selected_run}/` | "
           f"Server: 152.69.227.31:8501")
