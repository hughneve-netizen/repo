import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from st_supabase_connection import SupabaseConnection
import time

# 1. Page Configuration
st.set_page_config(page_title="Sensor Monitor Pro", layout="wide")

# 2. Sidebar Controls
st.sidebar.header("🎛️ Settings")
window_size = st.sidebar.slider("Trend Smoothing (Window)", 1, 100, 20)
view_all = st.sidebar.checkbox("View All History", value=False)
refresh_rate = st.sidebar.slider("Refresh Rate (sec)", 5, 60, 10)

if st.sidebar.button("Reset Cache"):
    st.cache_data.clear()
    st.rerun()

st.title("📡 Live Sensor Analytics")

# 3. Database Connection
conn = st.connection("supabase", type=SupabaseConnection)

# 4. Data Fetching & Processing
@st.cache_data(ttl=refresh_rate)
def fetch_data(show_all):
    try:
        query = conn.table("sensor_data").select("*").order("timestamp", desc=True)
        if not show_all:
            query = query.limit(500)
        
        response = query.execute()
        df = pd.DataFrame(response.data)
        
        if not df.empty:
            # Force Types
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["reading_value"] = pd.to_numeric(df["reading_value"], errors='coerce')
            df = df.dropna(subset=['reading_value']).sort_values(by="timestamp")
            
            # MATH 1: Rolling Average
            df["rolling_avg"] = df["reading_value"].rolling(window=window_size, min_periods=1).mean()
            
            # MATH 2: Rate of Change (Velocity)
            # Calculated as change in value per second
            time_diff = df["timestamp"].diff().dt.total_seconds()
            df["rate_of_change"] = df["rolling_avg"].diff() / time_diff
            
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame()

# 5. Build UI
df = fetch_data(view_all)

if not df.empty:
    # Logic for Trend Indicators
    latest_velocity = df["rate_of_change"].iloc[-1]
    if latest_velocity > 0.005:
        trend_label = "Rising"
        trend_icon = "📈"
        trend_color = "normal" # Green in Streamlit
    elif latest_velocity < -0.005:
        trend_label = "Falling"
        trend_icon = "📉"
        trend_color = "inverse" # Red in Streamlit
    else:
        trend_label = "Stable"
        trend_icon = "➡️"
        trend_color = "off"

    # --- METRIC CARDS ---
    c1, c2, c3 = st.columns(3)
    c1.metric("Live Reading", f"{df['reading_value'].iloc[-1]:.2f}")
    c2.metric("Trend Velocity", f"{latest_velocity:.4f} u/s", 
              delta=f"{trend_label} {trend_icon}", delta_color=trend_color)
    c3.metric("Data Points", len(df))

    # --- DUAL AXIS CHART ---
    fig = go.Figure()

    # Raw Reading (Blue)
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df["reading_value"],
        name='Raw Data', line=dict(color='#33C3F0', width=1.5)
    ))

    # Rolling Trend (Orange Dotted)
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df["rolling_avg"],
        name='Trend Line', line=dict(color='#FFA500', width=2.5, dash='dot')
    ))

    # Rate of Change (Purple Dotted - Secondary Y)
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df["rate_of_change"],
        name='Velocity (Rate)', 
        line=dict(color='#BF5AF2', width=1.5, dash='dashdot'),
        yaxis="y2"
    ))

    fig.update_layout(
        template="plotly_dark",
        xaxis=dict(title="Time", tickfont=dict(size=20), rangeslider=dict(visible=True)),
        yaxis=dict(title="Reading Value", titlefont=dict(color="#FFA500")),
        yaxis2=dict(
            title="Velocity (Change/Sec)",
            titlefont=dict(color="#BF5AF2"),
            tickfont=dict(color="#BF5AF2"),
            anchor="x", overlaying="y", side="right"
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=600
    )

    st.plotly_chart(fig, use_container_width=True)

else:
    st.info("Searching for data...")

# 6. Heartbeat
time.sleep(refresh_rate)
st.rerun()