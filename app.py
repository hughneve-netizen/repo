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

# 2. Sidebar Controls
st.sidebar.header("🎛️ Dashboard Controls")

# --- DATE FILTER LOGIC ---
# Fixed earliest date
MIN_DATE = datetime(2026, 4, 11).date()
today = datetime.now().date()
yesterday = today - timedelta(days=1)

# Ensure the default selection doesn't start before the minimum allowed date
default_start = max(yesterday, MIN_DATE)

date_range = st.sidebar.date_input(
    "Select Date Range",
    value=(default_start, today),
    min_value=MIN_DATE,
    max_value=today
)

window_size = st.sidebar.slider("Trend Smoothing (Window)", 1, 100, 20, 
                                help="The trend line will be shifted left by this many samples.")
refresh_rate = st.sidebar.slider("Auto-Refresh (seconds)", 5, 60, 10)

if st.sidebar.button("🗑️ Clear Cache"):
    st.cache_data.clear()
    st.rerun()

st.title("🌊 Nant Cledlyn Water Level Analysis")
st.subheader("by Hugh Neve")

# 3. Database Connection
conn = st.connection("supabase", type=SupabaseConnection)

# 4. Data Fetching Logic
@st.cache_data(ttl=refresh_rate)
def fetch_data(dates):
    try:
        # Check if user has selected both a start and end date
        if not isinstance(dates, (list, tuple)) or len(dates) != 2:
            return pd.DataFrame()
        
        start_date = datetime.combine(dates[0], datetime.min.time()).isoformat()
        end_date = datetime.combine(dates[1], datetime.max.time()).isoformat()

        # Query Supabase with date filters
        query = conn.table("sensor_data").select("*")\
            .gte("timestamp", start_date)\
            .lte("timestamp", end_date)\
            .order("timestamp", desc=True)
            
        response = query.execute()
        df = pd.DataFrame(response.data)
        
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["reading_value"] = pd.to_numeric(df["reading_value"], errors='coerce')
            df = df.dropna(subset=['reading_value']).sort_values(by="timestamp")
            
            # SHIFT: Move the trend line left by the window size
            # Center=True aligns the average with the middle of the window
            df["rolling_avg"] = df["reading_value"].rolling(
                window=window_size, 
                win_type='gaussian', 
                center=True, 
                min_periods=1
            ).mean(std=window_size/4)
            
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Database Error: {e}")
        return pd.DataFrame()

# 5. Execute Fetch
df = fetch_data(date_range)

if not df.empty:
    # --- METRICS ---
    latest_val = df["reading_value"].iloc[-1]
    
    c1, c2 = st.columns(2)
    c1.metric("Latest Depth", f"{latest_val:.1f} cm")
    c2.metric("Records in Range", len(df))

    # --- CHART BUILDING ---
    fig = go.Figure()

    # Trace 1: Raw Data
    fig.add_trace(go.Scatter(
        x=df["timestamp"], 
        y=df["reading_value"], 
        name='Raw Depth', 
        line=dict(color='#33C3F0', width=1.5)
    ))

    # Trace 2: Rolling Trend
    fig.add_trace(go.Scatter(
        x=df["timestamp"], 
        y=df["rolling_avg"], 
        name=f'Trend ({window_size} Sample Window)', 
        line=dict(color='#FFA500', width=2.5, dash='dot')
    ))

    # Layout Configuration
    fig.update_layout(
        title=dict(
            text="Depth of Nant Cledlyn, Drefach, Ceredigion",
            font=dict(size=24)
        ),
        template="plotly_dark",
        height=600,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1),
        margin=dict(l=50, r=50, t=100, b=50)
    )

    # Configure X-Axis
    fig.update_xaxes(
        title=dict(text="Time", font=dict(size=18)),
        tickfont=dict(size=14),
        rangeslider=dict(visible=True),
        autorange=True
    )

    # Configure Y-Axis
    fig.update_yaxes(
        title=dict(text="Approx. depth, cm", font=dict(color="#FFA500", size=18)),
        tickfont=dict(size=16),
        autorange=True
    )

    st.plotly_chart(fig, use_container_width=True)

    # --- DOWNLOAD SECTION ---
    st.markdown("---")
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download This Data Range (CSV)",
        data=csv,
        file_name=f"nant_cledlyn_depth_{date_range[0]}_to_{date_range[1]}.csv",
        mime="text/csv"
    )
else:
    st.info("Select a start and end date to display data (Earliest available: 11 April 2026).")

# 6. Heartbeat Refresh
time.sleep(refresh_rate)
st.rerun()
