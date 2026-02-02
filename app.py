import streamlit as st
import pandas as pd
import plotly.express as px
from st_supabase_connection import SupabaseConnection
import time

# 1. Page Configuration
st.set_page_config(
    page_title="Live Sensor Dashboard",
    page_icon="📡",
    layout="wide"
)

st.title("📡 Real-Time Sensor Data Feed")
st.markdown("Fetching live data from Supabase Cloud Storage")

# 2. Initialize Connection
# This looks for SUPABASE_URL and SUPABASE_KEY in your secrets.toml
conn = st.connection("supabase", type=SupabaseConnection)

# 3. Cached Data Fetching
# The 'ttl' ensures the app doesn't stay stuck on old data
@st.cache_data(ttl=10)
def fetch_data():
    try:
        # Fetching all columns from your 'sensor_data' table
        response = conn.table("sensor_data").select("*").execute()
        df = pd.DataFrame(response.data)
        
        if not df.empty:
            # Convert timestamp and sort to fix the 'zigzag' / looping issue
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values(by="timestamp")
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return pd.DataFrame()

# 4. Main App Logic
df = fetch_data()

if not df.empty:
    # Top Row Metrics
    col1, col2 = st.columns(2)
    latest_val = df["reading_value"].iloc[-1]
    latest_time = df["timestamp"].iloc[-1].strftime('%Y-%m-%d %H:%M:%S')
    
    col1.metric("Latest Reading", f"{latest_val} units")
    col2.metric("Last Updated", latest_time)

    # 5. Interactive Plotly Chart
    fig = px.line(
        df, 
        x="timestamp", 
        y="reading_value", 
        title="Sensor History (Zoomable)",
        markers=True,
        template="plotly_dark"
    )

    # Add Zoom/Pan Tools and Range Slider
    fig.update_layout(
        xaxis=dict(
            rangeslider=dict(visible=True), # Allows "All Data" navigation
            type="date"
        ),
        yaxis=dict(autorange=True),
        dragmode="zoom",
        hovermode="x unified"
    )

    st.plotly_chart(fig, use_container_width=True)

    # Optional: Data Table
    with st.expander("View Raw Data Table"):
        st.dataframe(df.sort_values(by="timestamp", ascending=False))

else:
    st.info("Waiting for data... Ensure your sensor is uploading to Supabase.")

# 6. Auto-Refresh Logic
# This forces the browser to refresh the script every 10 seconds
st.empty()
time.sleep(10)
st.rerun()