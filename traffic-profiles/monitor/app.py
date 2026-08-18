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
    st.header("📂 모드 선택")
    page_mode = st.radio("", ["📡 UPF Monitor", "⚖️ Fair CNI 비교"], label_visibility="collapsed")
    st.divider()

# ═══════════════════════════════════════════════════════
# Fair CNI 비교 모드
# ═══════════════════════════════════════════════════════
if page_mode == "⚖️ Fair CNI 비교":
    st.title("⚖️ 공정 조건 CNI 비교: ipvlan vs macvlan")
    st.markdown("""
    **실험 조건**: 물리 NIC(`enp1s0`) 직접 분기 — bridge/veth 없이 순수 드라이버 성능 비교  
    **편향 제거**: 기존 dual-bridge 구조의 ipvlan 불이익(veth 추가 경유) 제거
    """)

    import plotly.graph_objects as go
    import pandas as pd
    from plotly.subplots import make_subplots

    FAIR_DATA_DIR = Path("/home/ubuntu/free5gc-k8s-arm/traffic-profiles/monitor/data")

    def load_iperf3_json(filepath):
        try:
            with open(filepath) as f:
                data = json.load(f)
            end = data.get("end", {})
            sum_data = end.get("sum", {})
            intervals = data.get("intervals", [])
            interval_data = []
            for iv in intervals:
                s = iv.get("sum", {})
                interval_data.append({
                    "seconds": s.get("end", 0),
                    "bits_per_second": s.get("bits_per_second", 0),
                    "packets": s.get("packets", 0),
                    "lost_packets": s.get("lost_packets", 0),
                })
            return {
                "throughput_mbps": sum_data.get("bits_per_second", 0) / 1e6,
                "packets": sum_data.get("packets", 0),
                "lost_packets": sum_data.get("lost_packets", 0),
                "lost_percent": sum_data.get("lost_percent", 0),
                "jitter_ms": sum_data.get("jitter_ms", 0),
                "intervals": interval_data,
            }
        except Exception as e:
            return None

    # 결과 파일 찾기
    fair_files = {}
    for pattern, key in [
        ("fair-macvlan-udp64_*.json", "macvlan_64"),
        ("fair-ipvlan-udp64_*.json", "ipvlan_64"),
        ("fair-macvlan-udp1400_*.json", "macvlan_1400"),
        ("fair-ipvlan-udp1400_*.json", "ipvlan_1400"),
    ]:
        files = sorted(FAIR_DATA_DIR.glob(pattern))
        valid = [f for f in files if f.stat().st_size > 1000]
        if valid:
            fair_files[key] = valid[-1]

    if not fair_files:
        st.warning("실험 결과 파일이 없습니다. `fair-test.sh`를 먼저 실행하세요.")
        st.stop()

    fair_data = {}
    for key, filepath in fair_files.items():
        fair_data[key] = load_iperf3_json(filepath)

    # 종합 결과
    st.header("📊 종합 결과")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔹 소패킷 (64B, UDP flood)")
        if "macvlan_64" in fair_data and "ipvlan_64" in fair_data:
            m = fair_data["macvlan_64"]
            i = fair_data["ipvlan_64"]
            if m and i:
                df = pd.DataFrame({
                    "지표": ["Throughput (Mbps)", "Packets", "Lost", "Loss (%)", "Jitter (ms)"],
                    "macvlan": [f"{m['throughput_mbps']:.1f}", f"{m['packets']:,}", f"{m['lost_packets']:,}", f"{m['lost_percent']:.2f}", f"{m['jitter_ms']:.3f}"],
                    "ipvlan": [f"{i['throughput_mbps']:.1f}", f"{i['packets']:,}", f"{i['lost_packets']:,}", f"{i['lost_percent']:.2f}", f"{i['jitter_ms']:.3f}"],
                })
                st.dataframe(df, use_container_width=True, hide_index=True)
                if i['lost_percent'] < m['lost_percent']:
                    st.success(f"✅ 소패킷: **ipvlan 유리** (loss {i['lost_percent']:.2f}% < {m['lost_percent']:.2f}%)")
                else:
                    st.info(f"소패킷: macvlan 유리")

    with col2:
        st.subheader("🔸 대패킷 (1400B, 500Mbps)")
        if "macvlan_1400" in fair_data and "ipvlan_1400" in fair_data:
            m = fair_data["macvlan_1400"]
            i = fair_data["ipvlan_1400"]
            if m and i:
                df = pd.DataFrame({
                    "지표": ["Throughput (Mbps)", "Packets", "Lost", "Loss (%)", "Jitter (ms)"],
                    "macvlan": [f"{m['throughput_mbps']:.1f}", f"{m['packets']:,}", f"{m['lost_packets']:,}", f"{m['lost_percent']:.2f}", f"{m['jitter_ms']:.3f}"],
                    "ipvlan": [f"{i['throughput_mbps']:.1f}", f"{i['packets']:,}", f"{i['lost_packets']:,}", f"{i['lost_percent']:.2f}", f"{i['jitter_ms']:.3f}"],
                })
                st.dataframe(df, use_container_width=True, hide_index=True)
                if m['lost_percent'] < i['lost_percent']:
                    st.success(f"✅ 대패킷: **macvlan 유리** (loss {m['lost_percent']:.2f}% < {i['lost_percent']:.2f}%)")
                else:
                    st.info(f"대패킷: ipvlan 유리")

    # Bar charts
    st.header("📈 비교 차트")
    categories = []
    macvlan_loss = []
    ipvlan_loss = []
    macvlan_tp = []
    ipvlan_tp = []

    if "macvlan_64" in fair_data and "ipvlan_64" in fair_data and fair_data["macvlan_64"] and fair_data["ipvlan_64"]:
        categories.append("소패킷 (64B)")
        macvlan_loss.append(fair_data["macvlan_64"]["lost_percent"])
        ipvlan_loss.append(fair_data["ipvlan_64"]["lost_percent"])
        macvlan_tp.append(fair_data["macvlan_64"]["throughput_mbps"])
        ipvlan_tp.append(fair_data["ipvlan_64"]["throughput_mbps"])

    if "macvlan_1400" in fair_data and "ipvlan_1400" in fair_data and fair_data["macvlan_1400"] and fair_data["ipvlan_1400"]:
        categories.append("대패킷 (1400B)")
        macvlan_loss.append(fair_data["macvlan_1400"]["lost_percent"])
        ipvlan_loss.append(fair_data["ipvlan_1400"]["lost_percent"])
        macvlan_tp.append(fair_data["macvlan_1400"]["throughput_mbps"])
        ipvlan_tp.append(fair_data["ipvlan_1400"]["throughput_mbps"])

    c1, c2 = st.columns(2)
    with c1:
        fig_loss = go.Figure()
        fig_loss.add_trace(go.Bar(name="macvlan", x=categories, y=macvlan_loss, marker_color="#FF6B6B"))
        fig_loss.add_trace(go.Bar(name="ipvlan", x=categories, y=ipvlan_loss, marker_color="#4ECDC4"))
        fig_loss.update_layout(title="Packet Loss (낮을수록 좋음)", yaxis_title="Loss (%)", barmode="group", height=350)
        st.plotly_chart(fig_loss, use_container_width=True)

    with c2:
        fig_tp = go.Figure()
        fig_tp.add_trace(go.Bar(name="macvlan", x=categories, y=macvlan_tp, marker_color="#FF6B6B"))
        fig_tp.add_trace(go.Bar(name="ipvlan", x=categories, y=ipvlan_tp, marker_color="#4ECDC4"))
        fig_tp.update_layout(title="Throughput (높을수록 좋음)", yaxis_title="Mbps", barmode="group", height=350)
        st.plotly_chart(fig_tp, use_container_width=True)

    # 시계열
    st.header("📉 시계열 (초별)")
    tab1, tab2 = st.tabs(["소패킷 64B", "대패킷 1400B"])
    with tab1:
        if "macvlan_64" in fair_data and "ipvlan_64" in fair_data and fair_data["macvlan_64"] and fair_data["ipvlan_64"]:
            m_iv = fair_data["macvlan_64"]["intervals"]
            i_iv = fair_data["ipvlan_64"]["intervals"]
            if m_iv and i_iv:
                df_m = pd.DataFrame(m_iv)
                df_i = pd.DataFrame(i_iv)
                fig = make_subplots(rows=2, cols=1, subplot_titles=["Throughput (Mbps)", "Lost Packets"])
                fig.add_trace(go.Scatter(x=df_m["seconds"], y=df_m["bits_per_second"]/1e6, name="macvlan", line=dict(color="#FF6B6B")), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_i["seconds"], y=df_i["bits_per_second"]/1e6, name="ipvlan", line=dict(color="#4ECDC4")), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_m["seconds"], y=df_m["lost_packets"], name="macvlan loss", line=dict(color="#FF6B6B", dash="dot")), row=2, col=1)
                fig.add_trace(go.Scatter(x=df_i["seconds"], y=df_i["lost_packets"], name="ipvlan loss", line=dict(color="#4ECDC4", dash="dot")), row=2, col=1)
                fig.update_layout(height=500)
                st.plotly_chart(fig, use_container_width=True)
    with tab2:
        if "macvlan_1400" in fair_data and "ipvlan_1400" in fair_data and fair_data["macvlan_1400"] and fair_data["ipvlan_1400"]:
            m_iv = fair_data["macvlan_1400"]["intervals"]
            i_iv = fair_data["ipvlan_1400"]["intervals"]
            if m_iv and i_iv:
                df_m = pd.DataFrame(m_iv)
                df_i = pd.DataFrame(i_iv)
                fig = make_subplots(rows=2, cols=1, subplot_titles=["Throughput (Mbps)", "Lost Packets"])
                fig.add_trace(go.Scatter(x=df_m["seconds"], y=df_m["bits_per_second"]/1e6, name="macvlan", line=dict(color="#FF6B6B")), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_i["seconds"], y=df_i["bits_per_second"]/1e6, name="ipvlan", line=dict(color="#4ECDC4")), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_m["seconds"], y=df_m["lost_packets"], name="macvlan loss", line=dict(color="#FF6B6B", dash="dot")), row=2, col=1)
                fig.add_trace(go.Scatter(x=df_i["seconds"], y=df_i["lost_packets"], name="ipvlan loss", line=dict(color="#4ECDC4", dash="dot")), row=2, col=1)
                fig.update_layout(height=500)
                st.plotly_chart(fig, use_container_width=True)

    # 결론
    st.header("🔑 핵심 발견")
    st.markdown("""
    | 트래픽 특성 | 최적 CNI | 근거 |
    |------------|----------|------|
    | 소패킷 고빈도 (64B) | **ipvlan** | 커널 내부 L3, per-packet overhead 낮음 |
    | 대패킷 고throughput (1400B) | **macvlan** | NIC offload, HW multiqueue |

    **결론**: 트래픽 특성에 따라 최적 CNI가 달라짐 → **동적 전환의 당위성 확인**
    """)
    st.stop()

# ═══════════════════════════════════════════════════════
# 기존 UPF Monitor 모드
# ═══════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════
# iperf3 전환 실험 시각화 (iperf3_full.json 기반)
# ═══════════════════════════════════════════════════════
st.divider()
st.header("🔄 CNI 전환 실험 (iperf3 Interval)")

# iperf3_full.json이 있는 run 찾기
def get_switch_runs():
    """iperf3_full.json이 있는 run 목록"""
    switch_runs = []
    if not MONITOR_DATA_DIR.exists():
        return switch_runs
    for d in sorted(MONITOR_DATA_DIR.iterdir(), reverse=True):
        if d.is_dir() and (d / "iperf3_full.json").exists():
            switch_runs.append(d.name)
    return switch_runs

switch_runs = get_switch_runs()

if switch_runs:
    import pandas as pd

    selected_switch = st.selectbox("전환 실험 선택", switch_runs, index=0, key="switch_run")

    # 데이터 로딩
    iperf3_path = MONITOR_DATA_DIR / selected_switch / "iperf3_full.json"
    with open(iperf3_path) as f:
        iperf3_data = json.load(f)

    intervals = iperf3_data.get("intervals", [])

    if intervals:
        # 파싱
        times = []
        throughputs = []
        losses = []
        lost_pkts = []
        total_pkts = []

        for iv in intervals:
            streams = iv.get("streams", [{}])
            s = streams[0] if streams else {}
            end = s.get("end", 0)
            mbps = s.get("bits_per_second", 0) / 1e6
            lost = s.get("lost_packets", 0)
            total = s.get("packets", 0)
            loss_pct = (lost / total * 100) if total > 0 else 0

            times.append(end)
            throughputs.append(mbps)
            losses.append(loss_pct)
            lost_pkts.append(lost)
            total_pkts.append(total)

        df = pd.DataFrame({
            "Time (s)": times,
            "Throughput (Mbps)": throughputs,
            "Loss (%)": losses,
            "Packets": total_pkts,
        })

        # 메타 정보
        meta_path = MONITOR_DATA_DIR / selected_switch / "metadata.json"
        switch_meta = {}
        if meta_path.exists():
            with open(meta_path) as f:
                switch_meta = json.load(f)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("🔌 전환", switch_meta.get("cni", selected_switch[:30]))
        with col2:
            traffic_info = switch_meta.get("traffic", {})
            st.metric("📦 패킷", traffic_info.get("packet_size", "?"))
        with col3:
            st.metric("⏱ Duration", f"{len(intervals) * 5}s")

        # Throughput 차트 (핵심!)
        st.markdown("### 📈 Throughput 시계열 (전환 전후)")

        # 전환 시점 표시 (60초)
        st.caption("⚡ 전환 시점: ~60초 | 빨간 점선 = 전환 지점")

        # plotly 사용 가능하면 더 예쁘지만, 기본 line_chart로
        chart_df = df.set_index("Time (s)")[["Throughput (Mbps)"]]
        st.line_chart(chart_df, height=400)

        # 구간 통계
        before = [t for time, t in zip(times, throughputs) if time <= 60]
        after = [t for time, t in zip(times, throughputs) if time > 65]

        col1, col2, col3 = st.columns(3)
        with col1:
            if before:
                st.metric("전환 전 평균", f"{sum(before)/len(before):.1f} Mbps")
        with col2:
            if after:
                st.metric("전환 후 평균", f"{sum(after)/len(after):.1f} Mbps")
        with col3:
            if before and after:
                change = (sum(after)/len(after)) / (sum(before)/len(before)) * 100 - 100
                st.metric("변화율", f"{change:+.1f}%")

        # 상세 테이블
        with st.expander("📋 Interval 상세 데이터"):
            display_df = df.copy()
            display_df["구간"] = display_df["Time (s)"].apply(
                lambda t: "전환 전" if t <= 60 else ("전환!" if t <= 65 else "전환 후")
            )
            st.dataframe(display_df, use_container_width=True)

        # PPS 차트 (초당 패킷 수)
        st.markdown("### 📊 Packets per Second (PPS)")
        df["PPS"] = df["Packets"] / 5  # 5초 interval → 초당
        pps_df = df.set_index("Time (s)")[["PPS"]]
        st.line_chart(pps_df, height=300)

        # PPS 구간 통계
        pps_before = [p / 5 for time, p in zip(times, total_pkts) if time <= 60]
        pps_after = [p / 5 for time, p in zip(times, total_pkts) if time > 65]
        col1, col2 = st.columns(2)
        with col1:
            if pps_before:
                st.caption(f"전환 전: ~{sum(pps_before)/len(pps_before):,.0f} pps")
        with col2:
            if pps_after:
                st.caption(f"전환 후: ~{sum(pps_after)/len(pps_after):,.0f} pps")
    else:
        st.warning("iperf3 interval 데이터가 비어있습니다.")
else:
    st.info("전환 실험 데이터 없음 — iperf3_full.json이 포함된 Run이 필요합니다.")

st.caption(f"Monitor Data: `{MONITOR_DATA_DIR}/{selected_run}/` | "
           f"Server: 152.69.227.31:8501")
