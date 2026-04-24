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

# 3. Sidebar Controls
st.sidebar.header("🎛️ Dashboard Controls")

# --- DATE RANGE LOGIC ---
MIN_DATA_DATE = datetime(2026, 4, 11).date()
today = datetime.now().date()
three_days_ago = today - timedelta(days=3)
default_start = max(three_days_ago, MIN_DATA_DATE)

date_range = st.sidebar.date_input(
    "Select Date Range for Chart",
    value=(default_start, today),
    min_value=MIN_DATA_DATE,
    max_value=today
)

window_size = st.sidebar.slider("Trend Smoothing (Window)", 1, 100, 20)
refresh_rate = 600

if st.sidebar.button("🗑️ Clear Cache"):
    st.cache_data.clear()
    st.rerun()

# --- PAGINATED DATA FETCHING (To bypass the 1000 row limit) ---
def fetch_paginated_data(query_builder):
    """Helper function to loop through Supabase pages until all data is retrieved."""
    all_rows = []
    page_size = 1000  # Standard Supabase page limit
    offset = 0
    
    while True:
        # Request a specific range of rows
        response = query_builder.range(offset, offset + page_size - 1).execute()
        data = response.data
        all_rows.extend(data)
        
        # If we got fewer than 1000 rows, we've reached the end
        if len(data) < page_size:
            break
        
        offset += page_size
    
    return pd.DataFrame(all_rows)

@st.cache_data(ttl=3600)
def fetch_all_data():
    try:
        start_str = datetime(2026, 4, 11).isoformat()
        # Build query but don't execute yet
        query = conn.table("sensor_data").select("*")\
            .gte("timestamp", start_str)\
            .order("timestamp", desc=True)
        
        return fetch_paginated_data(query)
    except Exception as e:
        st.error(f"Error fetching all data: {e}")
        return None

st.sidebar.markdown("---")
st.sidebar.subheader("📥 Export Data")
all_df = fetch_all_data()

if all_df is not None and not all_df.empty:
    csv_all = all_df.to_csv(index=False).encode('utf-8')
    st.sidebar.download_button(
        label=f"Download All Records ({len(all_df)})",
        data=csv_all,
        file_name="nant_cledlyn_full_historical_data.csv",
        mime="text/csv"
    )

# --- MAIN PAGE CONTENT ---
st.title("🌊 Nant Cledlyn Water Level Analysis")
st.subheader("by Hugh Neve")

@st.cache_data(ttl=refresh_rate)
def fetch_filtered_data(dates):
    try:
        if not isinstance(dates, (list, tuple)) or len(dates) != 2:
            return pd.DataFrame()
        
        start_date = datetime.combine(dates[0], datetime.min.time()).isoformat()
        end_date = datetime.combine(dates[1], datetime.max.time()).isoformat()

        # Build query for the specific date range
        query = conn.table("sensor_data").select("*")\
            .gte("timestamp", start_date)\
            .lte("timestamp", end_date)\
            .order("timestamp", desc=True)
            
        df = fetch_paginated_data(query)
        
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["reading_value"] = pd.to_numeric(df["reading_value"], errors='coerce')
            df = df.dropna(subset=['reading_value']).sort_values(by="timestamp")
            
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
df = fetch_filtered_data(date_range)

if not df.empty:
    latest_val = df["reading_value"].iloc[-1]
    
    c1, c2 = st.columns(2)
    c1.metric("Latest Depth", f"{latest_val:.1f} cm")
    c2.metric("Records in Current View", f"{len(df):,}") # Added comma for readability

    # --- CHART BUILDING ---
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["reading_value"], name='Raw Depth', line=dict(color='#33C3F0', width=1.5)))
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["rolling_avg"], name='Trend', line=dict(color='#FFA500', width=2.5, dash='dot')))

    fig.update_layout(
        template="plotly_dark", height=600,
        margin=dict(l=50, r=50, t=50, b=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    csv_filtered = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label=f"📥 Download Filtered Range ({len(df):,} rows)",
        data=csv_filtered,
        file_name=f"nant_cledlyn_{date_range[0]}_to_{date_range[1]}.csv",
        mime="text/csv"
    )
else:
    st.info("No data found for the selected range.")

# 6. Heartbeat Refresh
time.sleep(refresh_rate)
st.rerun()
