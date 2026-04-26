import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from st_supabase_connection import SupabaseConnection
import time
from datetime import datetime, timedelta

# 1. Page Configuration
st.set_page_config(
    page_title="Nant Cledlyn Monitor",
    page_icon="🌊",
    layout="wide"
)

# 2. Database Connection
conn = st.connection("supabase", type=SupabaseConnection)

# --- TIDE PREDICTION LOGIC ---
def get_high_tides(start_date, end_date):
    high_tides = []
    # Known High Tide Reference for Aberystwyth: April 26, 2026 @ 04:32
    # The semi-diurnal cycle is approximately 12.42 hours
    ref_tide = datetime(2026, 4, 26, 4, 32)
    cycle = timedelta(hours=12, minutes=25, seconds=12)
    
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())

    # Align reference to well before the start_dt to catch all events
    current_tide = ref_tide
    while current_tide > start_dt:
        current_tide -= cycle
    
    # Collect all tides within the selected range
    while current_tide <= end_dt:
        if current_tide >= start_dt:
            high_tides.append(current_tide)
        current_tide += cycle
    return high_tides

# 3. Sidebar Controls
st.sidebar.header("🎛️ Dashboard Controls")

MIN_DATA_DATE = datetime(2026, 4, 11).date()
today = datetime.now().date()
default_start = max(today - timedelta(days=3), MIN_DATA_DATE)

date_range = st.sidebar.date_input(
    "Select Date Range",
    value=(default_start, today),
    min_value=MIN_DATA_DATE,
    max_value=today
)

show_tides = st.sidebar.checkbox("Show Aberystwyth High Tides", value=True)
window_size = st.sidebar.slider("Trend Smoothing", 1, 100, 20)
refresh_rate = st.sidebar.slider("Auto-Refresh (seconds)", 5, 60, 10)

if st.sidebar.button("🗑️ Clear Cache"):
    st.cache_data.clear()
    st.rerun()

# --- DATA FETCHING ---
def fetch_paginated_data(query_builder):
    all_rows = []
    page_size, offset = 1000, 0
    while True:
        res = query_builder.range(offset, offset + page_size - 1).execute()
        all_rows.extend(res.data)
        if len(res.data) < page_size:
            break
        offset += page_size
    return pd.DataFrame(all_rows)

@st.cache_data(ttl=refresh_rate)
def fetch_filtered_data(dates):
    if not isinstance(dates, (list, tuple)) or len(dates) != 2:
        return pd.DataFrame()
    
    q = conn.table("sensor_data").select("*")\
        .gte("timestamp", dates[0].isoformat())\
        .lte("timestamp", dates[1].isoformat())\
        .order("timestamp", desc=True)
        
    df = fetch_paginated_data(q)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["reading_value"] = pd.to_numeric(df["reading_value"], errors='coerce')
        df = df.dropna(subset=['reading_value']).sort_values("timestamp")
        df["rolling_avg"] = df["reading_value"].rolling(
            window=window_size, win_type='gaussian', center=True, min_periods=1
        ).mean(std=window_size/4)
    return df

# 4. Main UI Logic
st.title("🌊 Nant Cledlyn Water Level Analysis")
st.subheader("by Hugh Neve")

df = fetch_filtered_data(date_range)

if not df.empty:
    latest_val = df["reading_value"].iloc[-1]
    c1, c2 = st.columns(2)
    c1.metric("Latest Depth", f"{latest_val:.1f} cm")
    c2.metric("Total Records", f"{len(df):,}")

    fig = go.Figure()

    # River Data
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df["reading_value"],
        name='River Depth', line=dict(color='#33C3F0', width=1.5)
    ))

    # Trend Line
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df["rolling_avg"],
        name='Trend', line=dict(color='#FFA500', width=2, dash='dot')
    ))

    # High Tide Markers (Magenta)
    if show_tides:
        tide_times = get_high_tides(date_range[0], date_range[1])
        y_max = df["reading_value"].max() * 1.02  # Place slightly above data
        
        # Add vertical dashed lines
        for t in tide_times:
            fig.add_vline(x=t, line_width=1.5, line_dash="dash", line_color="#FF00FF", opacity=0.4)
        
        # Add the markers
        fig.add_trace(go.Scatter(
            x=tide_times,
            y=[y_max] * len(tide_times),
            mode='markers',
            name='High Tide (Aberystwyth)',
            marker=dict(symbol='triangle-down', size=14, color='#FF00FF'),
            text=[f"High Tide @ {t.strftime('%H:%M')}" for t in tide_times],
            hoverinfo='text'
        ))

    fig.update_layout(
        template="plotly_dark",
        height=600,
        margin=dict(l=50, r=50, t=50, b=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(title="Time", rangeslider=dict(visible=True)),
        yaxis=dict(title="Approx. Depth (cm)", autorange=True)
    )

    st.plotly_chart(fig, use_container_width=True)

    # --- DOWNLOADS ---
    st.markdown("---")
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label=f"📥 Download Filtered Range ({len(df):,} rows)",
        data=csv,
        file_name=f"nant_cledlyn_{date_range[0]}_to_{date_range[1]}.csv",
        mime="text/csv"
    )
else:
    st.info("No data found for the selected range.")

# 5. Refresh Logic (One call at the end)
time.sleep(refresh_rate)
st.rerun()
