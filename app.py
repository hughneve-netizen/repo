import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from st_supabase_connection import SupabaseConnection
import time

# 1. Page Configuration
st.set_page_config(page_title="Sensor Monitor Pro", layout="wide")

# 2. Sidebar Controls
st.sidebar.header("🎛️ Controls")
window_size = st.sidebar.slider("Rolling Average Window", 1, 100, 20)
view_all = st.sidebar.checkbox("View All Data", value=False)
refresh_rate = st.sidebar.slider("Refresh Rate (sec)", 5, 60, 10)

if st.sidebar.button("Clear Cache"):
    st.cache_data.clear()
    st.rerun()

st.title("📡 Live Sensor Data Feed")

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
            # FORCE DATA TYPES (The "Invisible Line" Fix)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["reading_value"] = pd.to_numeric(df["reading_value"], errors='coerce')
            
            # Clean up: remove any rows where math failed
            df = df.dropna(subset=['reading_value', 'timestamp'])
            
            # Sort for time-series flow
            df = df.sort_values(by="timestamp")
            
            # Rolling Avg Math
            df["rolling_avg"] = df["reading_value"].rolling(window=window_size, min_periods=1).mean()
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"DB Error: {e}")
        return pd.DataFrame()

# 5. Build UI
df = fetch_data(view_all)

if not df.empty:
    # Diagnostic Banner (Keep this until you see lines!)
    st.caption(f"Status: Plotting {len(df)} points. Latest value: {df['reading_value'].iloc[-1]}")

    # Build Chart
    fig = go.Figure()

    # Add Raw Data Line (Blue)
    fig.add_trace(go.Scatter(
        x=df["timestamp"], 
        y=df["reading_value"],
        mode='lines+markers', # Markers ensure you see data points even if lines break
        name='Raw Reading',
        line=dict(color='#33C3F0', width=2),
        marker=dict(size=4)
    ))

    # Add Rolling Average (Orange Dotted)
    fig.add_trace(go.Scatter(
        x=df["timestamp"], 
        y=df["rolling_avg"],
        mode='lines',
        name='Trend Line',
        line=dict(color='#FFA500', width=2, dash='dot')
    ))

    # Force Layout and Scale
    fig.update_layout(
        template="plotly_dark",
        xaxis=dict(
            title="Time",
            tickfont=dict(size=20), # Large font as requested
            rangeslider=dict(visible=True),
            autorange=True 
        ),
        yaxis=dict(
            title="Sensor Value",
            autorange=True 
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=600
    )

    st.plotly_chart(fig, use_container_width=True)

    # Metrics
    c1, c2 = st.columns(2)
    c1.metric("Live Reading", f"{df['reading_value'].iloc[-1]:.2f}")
    c2.metric("Trend (Avg)", f"{df['rolling_avg'].iloc[-1]:.2f}")

else:
    st.warning("No data found in Supabase. Check your Pico 2 W connection.")

# 6. Heartbeat
time.sleep(refresh_rate)
st.rerun()