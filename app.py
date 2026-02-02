import streamlit as st
import pandas as pd
import plotly.express as px
from st_supabase_connection import SupabaseConnection
import time

st.set_page_config(page_title="Sensor Monitor", layout="wide")

st.title("📡 Real-Time Sensor Feed")

# 1. Initialize Connection
conn = st.connection("supabase", type=SupabaseConnection)

# 2. Fresh Data Fetch (No decorator to ensure it never gets stuck)
def fetch_live_data():
    try:
        # Fetch last 500 rows to keep it fast but comprehensive
        response = conn.table("sensor_data").select("*").order("timestamp", desc=True).limit(500).execute()
        df = pd.DataFrame(response.data)
        
        if not df.empty:
            # Convert to datetime and localize to your system's time
            df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_convert('Europe/London') # Change to your timezone if needed
            
            # Remove duplicates to fix the "twice data" line issue
            df = df.drop_duplicates(subset=['timestamp'])
            
            # Sort ascending for a clean left-to-right line
            df = df.sort_values(by="timestamp")
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Database Fetch Error: {e}")
        return pd.DataFrame()

# 3. Execution
df = fetch_live_data()

if not df.empty:
    # Latest Reading Metric
    latest_val = df["reading_value"].iloc[-1]
    st.metric("Current Reading", f"{latest_val} units")

    # 4. Clean Plotly Chart
    fig = px.line(
        df, 
        x="timestamp", 
        y="reading_value",
        title="Interactive Sensor History",
        template="plotly_dark",
        markers=True
    )

    # Force the X-axis to focus on the data, not a fixed window
    fig.update_layout(
        xaxis=dict(rangeslider=dict(visible=True), autorange=True),
        yaxis=dict(autorange=True),
        hovermode="x unified"
    )

    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Connected but waiting for fresh data...")

# 5. Stable Rerun Logic (10-second heartbeat)
st.empty()
time.sleep(10)
st.rerun()