import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from st_supabase_connection import SupabaseConnection
import time

# 1. Page Configuration
st.set_page_config(page_title="Sensor Monitor Pro", layout="wide")

# 2. Sidebar Controls
st.sidebar.header("🎛️ Settings")
window_size = st.sidebar.slider("Smoothing Window", 1, 100, 20)
view_all = st.sidebar.checkbox("View All History", value=False)
refresh_rate = st.sidebar.slider("Refresh Rate (sec)", 5, 60, 10)

if st.sidebar.button("Clear Cache"):
    st.cache_data.clear()
    st.rerun()

st.title("📡 Live Sensor Analytics")

# 3. Connection
conn = st.connection("supabase", type=SupabaseConnection)

# 4. Data Fetching
@st.cache_data(ttl=refresh_rate)
def fetch_data(show_all):
    try:
        query = conn.table("sensor_data").select("*").order("timestamp", desc=True)
        if not show_all:
            query = query.limit(500)
        
        response = query.execute()
        df = pd.DataFrame(response.data)
        
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["reading_value"] = pd.to_numeric(df["reading_value"], errors='coerce')
            df = df.dropna(subset=['reading_value']).sort_values(by="timestamp")
            
            # MATH: Trend & Velocity
            df["rolling_avg"] = df["reading_value"].rolling(window=window_size, min_periods=1).mean()
            time_diff = df["timestamp"].diff().dt.total_seconds()
            df["rate_of_change"] = df["rolling_avg"].diff() / time_diff
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Database Error: {e}")
        return pd.DataFrame()

# 5. Build UI
df = fetch_data(view_all)

if not df.empty:
    # Logic for Trend Indicators
    latest_vel = df["rate_of_change"].iloc[-1] if not df["rate_of_change"].empty else 0
    if latest_vel > 0.005:
        t_label, t_icon, t_col = "Rising", "📈", "normal"
    elif latest_vel < -0.005:
        t_label, t_icon, t_col = "Falling", "📉", "inverse"
    else:
        t_label, t_icon, t_col = "Stable", "➡️", "off"

    # Metrics
    c1, c2, c3 = st.columns(3)
    c1.metric("Live Reading", f"{df['reading_value'].iloc[-1]:.2f}")
    c2.metric("Trend Velocity", f"{latest_vel:.4f} u/s", delta=f"{t_label} {t_icon}", delta_color=t_col)
    c3.metric("Data Points", len(df))

    # --- CHART BUILDING (Flat Structure) ---
    fig = go.Figure()

    # Trace 1: Blue Raw Data
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["reading_value"], name='Raw', line=dict(color='#33C3F0', width=1.5)))

    # Trace 2: Orange Trend
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["rolling_avg"], name='Trend', line=dict(color='#FFA500', width=2.5, dash='dot')))

    # Trace 3: Purple Velocity (Right Axis)
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["rate_of_change"], name='Velocity', line=dict(color='#BF5AF2', width=1.5, dash='dashdot'), yaxis="y2"))

    # Update Global Layout
    fig.update_layout(
        template="plotly_dark",
        height=600,
        margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(orientation="h", y=1.1, x=1, xanchor="right")
    )

    # Update Axes Individually (Avoids Nesting Errors)
    fig.update_xaxes(title_text="Time", tickfont=dict(size=20), rangeslider=dict(visible=True))
    fig.update_yaxes(title_text="Sensor Value", titlefont=dict(color="#FFA500"))
    
    # Configure Right-hand Axis
    fig.update_layout(
        yaxis2=dict(
            title="Velocity (Change/Sec)",
            titlefont=dict(color="#BF5AF2"),
            tickfont=dict(color="#BF5AF2"),
            anchor="x",
            overlaying="y",
            side="right"
        )
    )

    st.plotly_chart(fig, use_container_width=True)

else:
    st.info("Waiting for data...")

# 6. Refresh
time.sleep(refresh_rate)
st.rerun()