"""
공정 조건 CNI 비교 — ipvlan vs macvlan
물리 NIC(enp1s0) 직접 분기, bridge/veth 없음
"""

import streamlit as st
import json
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path
from plotly.subplots import make_subplots

st.set_page_config(page_title="CNI Fair Comparison", page_icon="⚖️", layout="wide")
st.title("⚖️ 공정 조건 CNI 비교: ipvlan vs macvlan")
st.markdown("""
**실험 조건**: 물리 NIC(`enp1s0`) 직접 분기 — bridge/veth 없이 순수 드라이버 성능 비교  
**편향 제거**: 기존 dual-bridge 구조의 ipvlan 불이익(veth 추가 경유) 제거
""")

DATA_DIR = Path("/home/ubuntu/free5gc-k8s-arm/traffic-profiles/monitor/data")


def load_iperf3_json(filepath):
    """iperf3 JSON 결과 파싱"""
    try:
        with open(filepath) as f:
            data = json.load(f)

        end = data.get("end", {})
        sum_data = end.get("sum", {})
        
        # intervals for time series
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
        st.error(f"파일 로드 실패: {filepath} — {e}")
        return None


def find_latest_results():
    """최신 결과 파일 찾기"""
    results = {}
    for pattern, key in [
        ("fair-macvlan-udp64_*.json", "macvlan_64"),
        ("fair-ipvlan-udp64_*.json", "ipvlan_64"),
        ("fair-macvlan-udp1400_*.json", "macvlan_1400"),
        ("fair-ipvlan-udp1400_*.json", "ipvlan_1400"),
    ]:
        files = sorted(DATA_DIR.glob(pattern))
        if files:
            # 가장 큰 파일(성공한 결과)의 최신 버전
            valid = [f for f in files if f.stat().st_size > 1000]
            if valid:
                results[key] = valid[-1]
    return results


# ═══════════════════════════════════════════════════════
# 데이터 로드
# ═══════════════════════════════════════════════════════
files = find_latest_results()

if not files:
    st.warning("실험 결과 파일이 없습니다. `fair-test.sh`를 먼저 실행하세요.")
    st.stop()

data = {}
for key, filepath in files.items():
    data[key] = load_iperf3_json(filepath)

# ═══════════════════════════════════════════════════════
# 요약 메트릭
# ═══════════════════════════════════════════════════════
st.header("📊 종합 결과")

col1, col2 = st.columns(2)

with col1:
    st.subheader("🔹 소패킷 (64B, UDP flood)")
    if "macvlan_64" in data and "ipvlan_64" in data:
        m = data["macvlan_64"]
        i = data["ipvlan_64"]

        metrics_64 = pd.DataFrame({
            "지표": ["Throughput (Mbps)", "Packets", "Lost Packets", "Loss (%)", "Jitter (ms)"],
            "macvlan": [f"{m['throughput_mbps']:.1f}", f"{m['packets']:,}", f"{m['lost_packets']:,}", f"{m['lost_percent']:.2f}", f"{m['jitter_ms']:.3f}"],
            "ipvlan": [f"{i['throughput_mbps']:.1f}", f"{i['packets']:,}", f"{i['lost_packets']:,}", f"{i['lost_percent']:.2f}", f"{i['jitter_ms']:.3f}"],
            "유리": [
                "macvlan" if m['throughput_mbps'] > i['throughput_mbps'] else "ipvlan",
                "macvlan" if m['packets'] > i['packets'] else "ipvlan",
                "ipvlan" if m['lost_packets'] > i['lost_packets'] else "macvlan",
                "ipvlan" if m['lost_percent'] > i['lost_percent'] else "macvlan",
                "ipvlan" if m['jitter_ms'] > i['jitter_ms'] else "macvlan",
            ]
        })
        st.dataframe(metrics_64, use_container_width=True, hide_index=True)
        
        # 판정
        if i['lost_percent'] < m['lost_percent']:
            st.success(f"✅ **소패킷: ipvlan 유리** (loss {i['lost_percent']:.2f}% < {m['lost_percent']:.2f}%)")
        else:
            st.info(f"macvlan 유리 (loss {m['lost_percent']:.2f}% < {i['lost_percent']:.2f}%)")
    else:
        st.warning("소패킷 결과 없음")

with col2:
    st.subheader("🔸 대패킷 (1400B, 500Mbps)")
    if "macvlan_1400" in data and "ipvlan_1400" in data:
        m = data["macvlan_1400"]
        i = data["ipvlan_1400"]

        metrics_1400 = pd.DataFrame({
            "지표": ["Throughput (Mbps)", "Packets", "Lost Packets", "Loss (%)", "Jitter (ms)"],
            "macvlan": [f"{m['throughput_mbps']:.1f}", f"{m['packets']:,}", f"{m['lost_packets']:,}", f"{m['lost_percent']:.2f}", f"{m['jitter_ms']:.3f}"],
            "ipvlan": [f"{i['throughput_mbps']:.1f}", f"{i['packets']:,}", f"{i['lost_packets']:,}", f"{i['lost_percent']:.2f}", f"{i['jitter_ms']:.3f}"],
            "유리": [
                "macvlan" if m['throughput_mbps'] > i['throughput_mbps'] else ("동일" if abs(m['throughput_mbps'] - i['throughput_mbps']) < 1 else "ipvlan"),
                "macvlan" if m['packets'] > i['packets'] else "ipvlan",
                "ipvlan" if m['lost_packets'] > i['lost_packets'] else "macvlan",
                "ipvlan" if m['lost_percent'] > i['lost_percent'] else "macvlan",
                "ipvlan" if m['jitter_ms'] > i['jitter_ms'] else "macvlan",
            ]
        })
        st.dataframe(metrics_1400, use_container_width=True, hide_index=True)
        
        if m['lost_percent'] < i['lost_percent']:
            st.success(f"✅ **대패킷: macvlan 유리** (loss {m['lost_percent']:.2f}% < {i['lost_percent']:.2f}%)")
        else:
            st.info(f"ipvlan 유리 (loss {i['lost_percent']:.2f}% < {m['lost_percent']:.2f}%)")
    else:
        st.warning("대패킷 결과 없음")

# ═══════════════════════════════════════════════════════
# 시각화: 비교 차트
# ═══════════════════════════════════════════════════════
st.header("📈 비교 차트")

# Bar chart: Loss 비교
fig_loss = go.Figure()
categories = []
macvlan_loss = []
ipvlan_loss = []

if "macvlan_64" in data and "ipvlan_64" in data:
    categories.append("소패킷 (64B)")
    macvlan_loss.append(data["macvlan_64"]["lost_percent"])
    ipvlan_loss.append(data["ipvlan_64"]["lost_percent"])

if "macvlan_1400" in data and "ipvlan_1400" in data:
    categories.append("대패킷 (1400B)")
    macvlan_loss.append(data["macvlan_1400"]["lost_percent"])
    ipvlan_loss.append(data["ipvlan_1400"]["lost_percent"])

fig_loss.add_trace(go.Bar(name="macvlan", x=categories, y=macvlan_loss, marker_color="#FF6B6B"))
fig_loss.add_trace(go.Bar(name="ipvlan", x=categories, y=ipvlan_loss, marker_color="#4ECDC4"))
fig_loss.update_layout(
    title="Packet Loss 비교 (낮을수록 좋음)",
    yaxis_title="Packet Loss (%)",
    barmode="group",
    height=400,
)
st.plotly_chart(fig_loss, use_container_width=True)

# Bar chart: Throughput 비교
fig_tp = go.Figure()
macvlan_tp = []
ipvlan_tp = []

if "macvlan_64" in data and "ipvlan_64" in data:
    macvlan_tp.append(data["macvlan_64"]["throughput_mbps"])
    ipvlan_tp.append(data["ipvlan_64"]["throughput_mbps"])

if "macvlan_1400" in data and "ipvlan_1400" in data:
    macvlan_tp.append(data["macvlan_1400"]["throughput_mbps"])
    ipvlan_tp.append(data["ipvlan_1400"]["throughput_mbps"])

fig_tp.add_trace(go.Bar(name="macvlan", x=categories, y=macvlan_tp, marker_color="#FF6B6B"))
fig_tp.add_trace(go.Bar(name="ipvlan", x=categories, y=ipvlan_tp, marker_color="#4ECDC4"))
fig_tp.update_layout(
    title="Throughput 비교 (높을수록 좋음)",
    yaxis_title="Throughput (Mbps)",
    barmode="group",
    height=400,
)
st.plotly_chart(fig_tp, use_container_width=True)

# ═══════════════════════════════════════════════════════
# 시계열 그래프 (interval별)
# ═══════════════════════════════════════════════════════
st.header("📉 시계열 (초별 성능)")

tab1, tab2 = st.tabs(["소패킷 64B", "대패킷 1400B"])

with tab1:
    if "macvlan_64" in data and "ipvlan_64" in data and data["macvlan_64"]["intervals"] and data["ipvlan_64"]["intervals"]:
        df_m = pd.DataFrame(data["macvlan_64"]["intervals"])
        df_i = pd.DataFrame(data["ipvlan_64"]["intervals"])
        
        fig = make_subplots(rows=2, cols=1, subplot_titles=["Throughput (Mbps)", "Packet Loss (per interval)"])
        
        fig.add_trace(go.Scatter(x=df_m["seconds"], y=df_m["bits_per_second"]/1e6, name="macvlan", line=dict(color="#FF6B6B")), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_i["seconds"], y=df_i["bits_per_second"]/1e6, name="ipvlan", line=dict(color="#4ECDC4")), row=1, col=1)
        
        fig.add_trace(go.Scatter(x=df_m["seconds"], y=df_m["lost_packets"], name="macvlan loss", line=dict(color="#FF6B6B", dash="dot")), row=2, col=1)
        fig.add_trace(go.Scatter(x=df_i["seconds"], y=df_i["lost_packets"], name="ipvlan loss", line=dict(color="#4ECDC4", dash="dot")), row=2, col=1)
        
        fig.update_layout(height=600)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("시계열 데이터 없음")

with tab2:
    if "macvlan_1400" in data and "ipvlan_1400" in data and data["macvlan_1400"]["intervals"] and data["ipvlan_1400"]["intervals"]:
        df_m = pd.DataFrame(data["macvlan_1400"]["intervals"])
        df_i = pd.DataFrame(data["ipvlan_1400"]["intervals"])
        
        fig = make_subplots(rows=2, cols=1, subplot_titles=["Throughput (Mbps)", "Packet Loss (per interval)"])
        
        fig.add_trace(go.Scatter(x=df_m["seconds"], y=df_m["bits_per_second"]/1e6, name="macvlan", line=dict(color="#FF6B6B")), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_i["seconds"], y=df_i["bits_per_second"]/1e6, name="ipvlan", line=dict(color="#4ECDC4")), row=1, col=1)
        
        fig.add_trace(go.Scatter(x=df_m["seconds"], y=df_m["lost_packets"], name="macvlan loss", line=dict(color="#FF6B6B", dash="dot")), row=2, col=1)
        fig.add_trace(go.Scatter(x=df_i["seconds"], y=df_i["lost_packets"], name="ipvlan loss", line=dict(color="#4ECDC4", dash="dot")), row=2, col=1)
        
        fig.update_layout(height=600)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("시계열 데이터 없음")

# ═══════════════════════════════════════════════════════
# 결론
# ═══════════════════════════════════════════════════════
st.header("🔑 핵심 발견")
st.markdown("""
### 공정 조건에서의 결과 (선행연구 가설 재현)

| 트래픽 특성 | 최적 CNI | 근거 |
|------------|----------|------|
| 소패킷 고빈도 (64B, max pps) | **ipvlan** | 커널 내부 L3 처리, per-packet overhead 낮음 |
| 대패킷 고throughput (1400B, 500Mbps) | **macvlan** | NIC offload(TSO/GRO), HW multiqueue 활용 |

### 기존 dual-bridge 결과와의 차이

- dual-bridge: macvlan **항상** 우위 → **인프라 편향** (veth pair가 ipvlan에 추가 hop)
- 공정 조건: **트래픽 특성에 따라 갈림** → 동적 전환의 당위성 확인

### 논문 시사점

> "트래픽 특성에 따라 최적 CNI가 달라지므로, NWDAF가 실시간 트래픽을 분석하여
> 전환 시점을 판단하는 것이 의미 있는 최적화 문제임이 확인되었다."
""")

# 파일 정보
with st.expander("📁 결과 파일 경로"):
    for key, filepath in files.items():
        st.text(f"{key}: {filepath}")
