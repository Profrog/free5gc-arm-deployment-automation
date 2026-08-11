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
                   "./quick-test.sh macvlan 60\n"
                   "```")
        st.stop()

    selected_run = st.selectbox("Run 1 (Primary)", runs, index=0)

    # Run 2 (비교용, optional)
    run2_options = ["(없음)"] + runs
    selected_run2 = st.selectbox("Run 2 (Compare)", run2_options, index=0)
    if selected_run2 == "(없음)":
        selected_run2 = None

    st.divider()
    if selected_run2:
        st.success(f"📊 비교 모드: 2개 Run")
    else:
        st.info("📊 단일 Run 모드")

    st.divider()
    st.header("📋 프로파일 목록")
    if PROFILES_DIR.exists():
        for p in sorted(PROFILES_DIR.glob("*.yaml")):
            if p.name != "schema.yaml":
                st.code(p.name, language=None)

# 데이터 로딩
metadata, summary, anomalies, pods = load_run_data(selected_run)

# ── 상단: 메타정보 & 요약 ──
st.markdown("**Run 1**")
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("🔌 CNI", metadata.get('cni', '?'))
with col2:
    traffic = metadata.get('traffic', {})
    st.metric("📶 Traffic", traffic.get('profile', traffic.get('pattern', '?')))
with col3:
    st.metric("⏱ Duration", f"{metadata.get('duration_sec', '?')}s")
with col4:
    # 트래픽 강도 범위 표시
    desc = traffic.get('description', traffic.get('bandwidth', '?'))
    st.metric("📊 Intensity", desc)
with col5:
    pkt = traffic.get('packet_size', '?')
    st.metric("📦 Packet", pkt)

# Run 2 정보
if selected_run2:
    metadata2, _, _, _ = load_run_data(selected_run2)
    st.markdown("**Run 2**")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("🔌 CNI", metadata2.get('cni', '?'))
    with col2:
        traffic2 = metadata2.get('traffic', {})
        st.metric("📶 Traffic", traffic2.get('profile', traffic2.get('pattern', '?')))
    with col3:
        st.metric("⏱ Duration", f"{metadata2.get('duration_sec', '?')}s")
    with col4:
        desc2 = traffic2.get('description', traffic2.get('bandwidth', '?'))
        st.metric("📊 Intensity", desc2)
    with col5:
        pkt2 = traffic2.get('packet_size', '?')
        st.metric("📦 Packet", pkt2)

st.divider()

# ── 탭 구성 ──
tab_cpu, tab_mem, tab_loss, tab_anomaly, tab_summary, tab_compare = st.tabs(
    ["📈 CPU", "💾 Memory", "📉 Packet Loss", "⚠️ Anomalies", "📋 Summary", "🔀 Compare"]
)

# ── CPU 탭 ──
with tab_cpu:
    if pods:
        import pandas as pd

        # Pod 선택 (기본: UPF)
        pod_list = list(pods.keys())
        upf_default = next((i for i, p in enumerate(pod_list) if "upf" in p.lower() and "upf2" not in p.lower()), 0)
        col_title, col_select = st.columns([1, 2])
        with col_title:
            st.subheader("CPU 사용량 (millicores)")
        with col_select:
            selected_pod = st.selectbox("Pod", pod_list, index=upf_default, key="cpu_pod")

        # 선택된 Pod 차트
        chart_data = {}
        if pods[selected_pod]["resources"]:
            cpus = [r["cpu_milli"] for r in pods[selected_pod]["resources"]]
            chart_data[f"[{selected_run[:15]}] {selected_pod[:20]}"] = cpus

        # Run 2 오버레이 (같은 Pod 이름 또는 같은 NF)
        if selected_run2:
            _, _, _, pods2 = load_run_data(selected_run2)
            # 같은 Pod 이름 또는 같은 NF 타입 찾기
            nf_type = selected_pod.split("-")[0:2]
            for pod_name, data in pods2.items():
                if pod_name.split("-")[0:2] == nf_type and data["resources"]:
                    cpus = [r["cpu_milli"] for r in data["resources"]]
                    chart_data[f"[{selected_run2[:15]}] {pod_name[:20]}"] = cpus
                    break

        if chart_data:
            max_len = max(len(v) for v in chart_data.values())
            for k in chart_data:
                chart_data[k] = chart_data[k] + [None] * (max_len - len(chart_data[k]))
            df = pd.DataFrame(chart_data)
            st.line_chart(df, height=400)

            # 요약 메트릭
            for label, vals in chart_data.items():
                valid = [v for v in vals if v is not None]
                if valid:
                    st.caption(f"{label} — Mean: {sum(valid)/len(valid):.1f}m | Max: {max(valid)}m | Samples: {len(valid)}")

# ── Memory 탭 ──
with tab_mem:
    if pods:
        import pandas as pd

        pod_list = list(pods.keys())
        upf_default = next((i for i, p in enumerate(pod_list) if "upf" in p.lower() and "upf2" not in p.lower()), 0)
        col_title, col_select = st.columns([1, 2])
        with col_title:
            st.subheader("Memory 사용량 (MiB)")
        with col_select:
            selected_mem_pod = st.selectbox("Pod", pod_list, index=upf_default, key="mem_pod")

        chart_data = {}
        if pods[selected_mem_pod]["resources"]:
            mems = [r["mem_mi"] for r in pods[selected_mem_pod]["resources"]]
            chart_data[f"[{selected_run[:15]}] {selected_mem_pod[:20]}"] = mems

        if selected_run2:
            _, _, _, pods2 = load_run_data(selected_run2)
            nf_type = selected_mem_pod.split("-")[0:2]
            for pod_name, data in pods2.items():
                if pod_name.split("-")[0:2] == nf_type and data["resources"]:
                    mems = [r["mem_mi"] for r in data["resources"]]
                    chart_data[f"[{selected_run2[:15]}] {pod_name[:20]}"] = mems
                    break

        if chart_data:
            max_len = max(len(v) for v in chart_data.values())
            for k in chart_data:
                chart_data[k] = chart_data[k] + [None] * (max_len - len(chart_data[k]))
            df = pd.DataFrame(chart_data)
            st.line_chart(df, height=400)

            for label, vals in chart_data.items():
                valid = [v for v in vals if v is not None]
                if valid:
                    st.caption(f"{label} — Mean: {sum(valid)/len(valid):.1f}Mi | Max: {max(valid)}Mi | Samples: {len(valid)}")

# ── Packet Loss 탭 ──
with tab_loss:
    import pandas as pd

    st.subheader("Packet Loss & Throughput — iperf3 interval 기반")

    # iperf3_loss.jsonl 로딩 함수
    def load_iperf3_loss(run_id):
        loss_file = MONITOR_DATA_DIR / run_id / "iperf3_loss.jsonl"
        return load_jsonl(loss_file)

    loss_data1 = load_iperf3_loss(selected_run)
    loss_data2 = load_iperf3_loss(selected_run2) if selected_run2 else []

    if loss_data1 or loss_data2:
        # Throughput 차트
        st.markdown("### Throughput (Mbps)")
        tp_chart = {}
        if loss_data1:
            tp_chart[f"[{selected_run[:20]}]"] = [r.get("bps", 0) / 1e6 for r in loss_data1]
        if loss_data2:
            tp_chart[f"[{selected_run2[:20]}]"] = [r.get("bps", 0) / 1e6 for r in loss_data2]

        if tp_chart:
            max_len = max(len(v) for v in tp_chart.values())
            for k in tp_chart:
                tp_chart[k] = tp_chart[k] + [None] * (max_len - len(tp_chart[k]))
            df = pd.DataFrame(tp_chart)
            st.line_chart(df, height=400)

            for label, vals in tp_chart.items():
                valid = [v for v in vals if v is not None]
                if valid:
                    st.caption(f"{label} — Mean: {sum(valid)/len(valid):.1f} Mbps | Max: {max(valid):.1f} Mbps")

        # Loss 차트 (offered 대비 실제 throughput 차이로 계산)
        st.markdown("### Estimated Loss (%) — offered vs actual")
        loss_chart = {}
        if loss_data1:
            offered1 = loss_data1[0].get("bandwidth_offered", "500M").replace("M", "")
            offered1_mbps = float(offered1)
            loss_pcts1 = [max(0, (offered1_mbps - r.get("bps", 0) / 1e6) / offered1_mbps * 100) for r in loss_data1]
            loss_chart[f"[{selected_run[:20]}]"] = loss_pcts1

        if loss_data2:
            offered2 = loss_data2[0].get("bandwidth_offered", "500M").replace("M", "")
            offered2_mbps = float(offered2)
            loss_pcts2 = [max(0, (offered2_mbps - r.get("bps", 0) / 1e6) / offered2_mbps * 100) for r in loss_data2]
            loss_chart[f"[{selected_run2[:20]}]"] = loss_pcts2

        if loss_chart:
            max_len = max(len(v) for v in loss_chart.values())
            for k in loss_chart:
                loss_chart[k] = loss_chart[k] + [None] * (max_len - len(loss_chart[k]))
            df = pd.DataFrame(loss_chart)
            st.line_chart(df, height=400)

            for label, vals in loss_chart.items():
                valid = [v for v in vals if v is not None]
                if valid:
                    st.caption(f"{label} — Mean: {sum(valid)/len(valid):.2f}% | Max: {max(valid):.2f}%")
    else:
        st.info("iperf3_loss.jsonl 없음 — quick-test.sh (프로파일 모드)로 실행하면 생성됩니다.")

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
