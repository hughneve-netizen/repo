import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from st_supabase_connection import SupabaseConnection
import time

# 1. Page Configuration
st.set_page_config(
    page_title="Sensor Monitor Pro",
    page_icon="📡",
    layout="wide"
)

# 2. Sidebar Controls
st.sidebar.header("🎛️ Dashboard Controls")
window_size = st.sidebar.slider("Trend Smoothing (Window)", 1, 100, 20)
view_all = st.sidebar.checkbox("View All History", value=False)
refresh_rate = st.sidebar.slider("Refresh Rate (sec)", 5, 60, 10)

if st.sidebar.button("🗑️ Clear Cache"):
    st.cache_data.clear()
    st.rerun()

st.title("📡 Live Sensor Analytics: Deopth of Nant Cledlyn, Drefach, Ceredigion")

# 3. Database Connection
conn = st.connection("supabase", type=SupabaseConnection)

# 4. Data Fetching & Processing Logic
@st.cache_data(ttl=refresh_rate)
def fetch_data(show_all):
    try:
        # Build query
        query = conn.table("sensor_data").select("*").order("timestamp", desc=True)
        if not show_all:
            query = query.limit(500)
            
        response = query.execute()
        df = pd.DataFrame(response.data)
        
        if not df.empty:
            # Type enforcement
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["reading_value"] = pd.to_numeric(df["reading_value"], errors='coerce')
            
            # Remove NaNs and sort for time-series flow
            df = df.dropna(subset=['reading_value'])
            df = df.sort_values(by="timestamp")
            
            # MATH: Rolling Average
            df["rolling_avg"] = df["reading_value"].rolling(window=window_size, min_periods=1).mean()
            
            # MATH: Rate of Change (Velocity)
            # Calculated as change in units per second
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

    # --- METRIC CARDS ---
    c1, c2, c3 = st.columns(3)
    c1.metric("Live Reading", f"{df['reading_value'].iloc[-1]:.2f}")
    c2.metric("Trend Velocity", f"{latest_vel:.4f} u/s", 
              delta=f"{t_label} {t_icon}", delta_color=t_col)
    c3.metric("Data Points", len(df))

    # --- CHART BUILDING ---
    fig = go.Figure()

    # Trace 1: Raw Data (Blue)
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df["reading_value"],
        name='Raw Reading', line=dict(color='#33C3F0', width=1.5)
    ))

    # Trace 2: Rolling Trend (Orange Dotted)
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df["rolling_avg"],
        name='Trend Line', line=dict(color='#FFA500', width=2.5, dash='dot')
    ))

    # Trace 3: Rate of Change (Purple Dash-Dot - Secondary Y)
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df["rate_of_change"],
        name='Velocity (Rate)', 
        line=dict(color='#BF5AF2', width=1.5, dash='dashdot'),
        yaxis="y2"
    ))

    # Global Layout Configuration
    fig.update_layout(
        template="plotly_dark",
        height=650,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1),
        margin=dict(l=50, r=50, t=100, b=50),
        # Secondary Y-Axis Configuration
        yaxis2=dict(
            title=dict(text="Velocity (Change/Sec)", font=dict(color="#BF5AF2")),
            tickfont=dict(color="#BF5AF2"),
            anchor="x",
            overlaying="y",
            side="right"
        )
    )

    # Configure X-Axis (Large Font)
    fig.update_xaxes(
        title=dict(text="Time", font=dict(size=18)),
        tickfont=dict(size=20),
        rangeslider=dict(visible=True),
        autorange=True
    )

    # Configure Primary Y-Axis (Left)
    fig.update_yaxes(
        title=dict(text="Depth (cm)", font=dict(color="#FFA500")),
        tickfont=dict(color="#FFA500")
    )

    st.plotly_chart(fig, use_container_width=True)

else:
    st.info("No data found. Ensure your Pico 2 W is connected and uploading.")

# 6. Heartbeat Refresh
time.sleep(refresh_rate)
st.rerun()