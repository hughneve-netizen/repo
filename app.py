import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from st_supabase_connection import SupabaseConnection
import time
from datetime import datetime, timedelta

# 1. Page Configuration
st.set_page_config(page_title="Nant Cledlyn Monitor", page_icon="🌊", layout="wide")

# 2. Database Connection
conn = st.connection("supabase", type=SupabaseConnection)

# --- TIDE PREDICTION HELPER ---
def get_high_tides(start_date, end_date):
    """
    Generates approximate high tide times for Aberystwyth.
    In a real scenario, you'd use a harmonic prediction or an API.
    This example uses a simplified 12h 25m cycle for demonstration.
    """
    high_tides = []
    # Known reference: High Tide on April 26, 2026 was approx 04:32 and 17:22
    ref_tide = datetime(2026, 4, 26, 4, 32)
    cycle = timedelta(hours=12, minutes=25.2)
    
    # Step backward to find first tide before start_date
    current_tide = ref_tide
    while current_tide > datetime.combine(start_date, datetime.min.time()):
        current_tide -= cycle
        
    # Step forward and collect tides in range
    while current_tide <= datetime.combine(end_date, datetime.max.time()):
        if current_tide >= datetime.combine(start_date, datetime.min.time()):
            high_tides.append(current_tide)
        current_tide += cycle
    return high_tides

# 3. Sidebar
st.sidebar.header("🎛️ Dashboard Controls")
MIN_DATA_DATE = datetime(2026, 4, 11).date()
today = datetime.now().date()
default_start = max(today - timedelta(days=3), MIN_DATA_DATE)

date_range = st.sidebar.date_input("Select Date Range", value=(default_start, today), 
                                  min_value=MIN_DATA_DATE, max_value=today)

show_tides = st.sidebar.checkbox("Show Aberystwyth High Tides", value=True)
window_size = st.sidebar.slider("Trend Smoothing", 1, 100, 20)
refresh_rate = st.sidebar.slider("Auto-Refresh (seconds)", 5, 60, 10)

# 4. Data Fetching (Using the paginated logic from before)
def fetch_paginated_data(query_builder):
    all_rows = []
    page_size, offset = 1000, 0
    while True:
        res = query_builder.range(offset, offset + page_size - 1).execute()
        all_rows.extend(res.data)
        if len(res.data) < page_size: break
        offset += page_size
    return pd.DataFrame(all_rows)

@st.cache_data(ttl=refresh_rate)
def fetch_filtered_data(dates):
    if not isinstance(dates, (list, tuple)) or len(dates) != 2: return pd.DataFrame()
    q = conn.table("sensor_data").select("*")\
        .gte("timestamp", dates[0].isoformat())\
        .lte("timestamp", dates[1].isoformat())\
        .order("timestamp", desc=True)
    df = fetch_paginated_data(q)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["reading_value"] = pd.to_numeric(df["reading_value"], errors='coerce')
        df = df.dropna(subset=['reading_value']).sort_values("timestamp")
        df["rolling_avg"] = df["reading_value"].rolling(window=window_size, win_type='gaussian', center=True, min_periods=1).mean(std=window_size/4)
    return df

# 5. Build Dashboard
st.title("🌊 Nant Cledlyn Water Level Analysis")
df = fetch_filtered_data(date_range)

if not df.empty:
    fig = go.Figure()

    # Raw Data & Trend
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["reading_value"], name='River Depth', line=dict(color='#33C3F0')))
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["rolling_avg"], name='Trend', line=dict(color='#FFA500', dash='dot')))

    # TIDE MARKERS
    if show_tides:
        tide_times = get_high_tides(date_range[0], date_range[1])
        # Add vertical lines for each high tide
        for t in tide_times:
            fig.add_vline(x=t.timestamp() * 1000, line_width=1, line_dash="dash", line_color="rgba(255,255,255,0.3)")
        
        # Add markers on top axis
        fig.add_trace(go.Scatter(
            x=tide_times,
            y=[df["reading_value"].max() * 1.05] * len(tide_times),
            mode='markers',
            name='High Tide (Aberystwyth)',
            marker=dict(symbol='triangle-down', size=10, color='white'),
            hoverinfo='text',
            text=[f"High Tide: {t.strftime('%H:%M')}" for t in tide_times]
        ))

    fig.update_layout(template="plotly_dark", height=600, margin=dict(t=50))
    st.plotly_chart(fig, use_container_width=True)
    st.metric("Latest Depth", f"{df['reading_value'].iloc[-1]:.1f} cm")
else:
    st.info("No data found for this range.")

time.sleep(refresh_rate)
st.rerun()
