import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from st_supabase_connection import SupabaseConnection
import time
from datetime import datetime

# 1. Page Configuration
st.set_page_config(
    page_title="Nant Cledlyn Monitor",
    page_icon="🌊",
    layout="wide"
)

# 2. Sidebar Controls
st.sidebar.header("🎛️ Dashboard Controls")

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

st.sidebar.info(f"📅 **Fixed Range:** \n{START_DATE_FIXED.strftime('%d %b %Y')} to Present")

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
def fetch_data(start_dt, end_dt):
    try:
        # Convert datetime objects to ISO format strings for Supabase
        start_str = start_dt.isoformat()
        end_str = end_dt.isoformat()

        # Query Supabase using the fixed start and dynamic end
        query = conn.table("sensor_data").select("*")\
            .gte("timestamp", start_str)\
            .lte("timestamp", end_str)\
            .order("timestamp", desc=True)
            
        response = query.execute()
        df = pd.DataFrame(response.data)
        
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["reading_value"] = pd.to_numeric(df["reading_value"], errors='coerce')
            df = df.dropna(subset=['reading_value']).sort_values(by="timestamp")
            
            # Gaussian Rolling Average for smoothing
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

# 5. Execute Fetch (Using the fixed start and current end)
df = fetch_data(START_DATE_FIXED, end_date_now)

if not df.empty:
    # --- METRICS ---
    latest_val = df["reading_value"].iloc[-1]
    
    c1, c2 = st.columns(2)
    c1.metric("Latest Depth", f"{latest_val:.1f} cm")
    c2.metric("Total Records since April 11", len(df))

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
        label="📥 Download Full Dataset (CSV)",
        data=csv,
        file_name=f"nant_cledlyn_full_data_{end_date_now.strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )
else:
    st.info("No data found starting from 11 April 2026.")

# 6. Heartbeat Refresh
time.sleep(refresh_rate)
st.rerun()
