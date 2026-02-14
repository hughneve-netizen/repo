import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from st_supabase_connection import SupabaseConnection
import time
from datetime import datetime, timedelta

# 1. Page Configuration
st.set_page_config(
    page_title="Nant Cledlyn, Drefach",
    page_icon="📡",
    layout="wide"
)

# 2. Sidebar Controls
st.sidebar.header("🎛️ Dashboard Controls")

# Date Filter Logic
today = datetime.now().date()
yesterday = today - timedelta(days=1)
date_range = st.sidebar.date_input(
    "Select Date Range",
    value=(yesterday, today),
    max_value=today
)

window_size = st.sidebar.slider("Trend Smoothing (Window)", 1, 100, 20)
refresh_rate = st.sidebar.slider("Auto-Refresh (seconds)", 5, 60, 10)

if st.sidebar.button("🗑️ Clear Cache"):
    st.cache_data.clear()
    st.rerun()

st.title("📡 Depth of Nant Cledlyn, Drefach, Ceredigion")

# 3. Database Connection
conn = st.connection("supabase", type=SupabaseConnection)

# 4. Data Fetching Logic
@st.cache_data(ttl=refresh_rate)
def fetch_data(dates):
    try:
        # Ensure we have both a start and end date
        if len(dates) != 2:
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
            
            # MATH
            df["rolling_avg"] = df["reading_value"].rolling(window=window_size, min_periods=1).mean()
            time_diff = df["timestamp"].diff().dt.total_seconds()
            df["rate_of_change"] = df["rolling_avg"].diff() / time_diff
            
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Database Error: {e}")
        return pd.DataFrame()

# 5. Execute Fetch
df = fetch_data(date_range)

if not df.empty:
    # --- METRICS ---
    latest_vel = df["rate_of_change"].iloc[-1] if not df["rate_of_change"].empty else 0
    t_label, t_icon, t_col = ("Rising", "📈", "normal") if latest_vel > 0.005 else \
                             ("Falling", "📉", "inverse") if latest_vel < -0.005 else \
                             ("Stable", "➡️", "off")

    c1, c2, c3 = st.columns(3)
    c1.metric("Live Reading", f"{df['reading_value'].iloc[-1]:.2f}")
    c2.metric("Trend Velocity", f"{latest_vel:.4f} u/s", delta=f"{t_label} {t_icon}", delta_color=t_col)
    c3.metric("Records Found", len(df))

    # --- DUAL AXIS CHART ---
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["reading_value"], name='Raw Reading', line=dict(color='#33C3F0', width=1.5)))
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["rolling_avg"], name='Trend Line', line=dict(color='#FFA500', width=2.5, dash='dot')))
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["rate_of_change"], name='Velocity', line=dict(color='#BF5AF2', width=1.5, dash='dashdot'), yaxis="y2"))

    fig.update_layout(
        template="plotly_dark", height=600,
        margin=dict(l=50, r=50, t=50, b=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1),
        yaxis2=dict(title=dict(text="Velocity", font=dict(color="#BF5AF2")), tickfont=dict(color="#BF5AF2"), anchor="x", overlaying="y", side="right")
    )
    fig.update_xaxes(title=dict(text="Time", font=dict(size=18)), tickfont=dict(size=20), rangeslider=dict(visible=True))
    fig.update_yaxes(title=dict(text="Value", font=dict(color="#FFA500")), tickfont=dict(color="#FFA500"))

    st.plotly_chart(fig, use_container_width=True)

    # --- DOWNLOAD SECTION ---
    st.markdown("---")
    col_a, col_b = st.columns([3, 1])
    with col_b:
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Data as CSV",
            data=csv,
            file_name=f"sensor_export_{date_range[0]}_to_{date_range[1]}.csv",
            mime="text/csv",
            use_container_width=True
        )
else:
    st.info("No data found for the selected date range.")

# 6. Heartbeat
time.sleep(refresh_rate)
st.rerun()