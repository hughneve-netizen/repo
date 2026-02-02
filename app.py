import streamlit as st
import pandas as pd
import plotly.express as px
from st_supabase_connection import SupabaseConnection
import time

st.set_page_config(page_title="Sensor Dashboard", layout="wide")

# 1. Force a "Clear Cache" button in the sidebar if it gets stuck again
if st.sidebar.button("Hard Refresh Cache"):
    st.cache_data.clear()

st.title("📡 Live Sensor Data Feed")

# 2. Initialize Connection
conn = st.connection("supabase", type=SupabaseConnection)

# 3. Aggressive Fetching
@st.cache_data(ttl=10)
def fetch_data():
    # Adding a limit or specific sort here can help the database response
    response = conn.table("sensor_data").select("*").execute()
    df = pd.DataFrame(response.data)
    
    if not df.empty:
        # Convert to datetime
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        
        # FIX FOR "TWICE" DATA: Remove exact duplicates if they exist
        df = df.drop_duplicates(subset=['timestamp', 'reading_value'])
        
        # Sort so the line draws correctly
        df = df.sort_values(by="timestamp")
        return df
    return pd.DataFrame()

# 4. Main App Logic
df = fetch_data()

if not df.empty:
    # Diagnostic: Show the last time the DB was actually queried
    st.caption(f"Database last queried at: {time.strftime('%H:%M:%S')}")
    
    # 5. The Chart
    # Use 'sensor_name' as color to prevent multiple lines from merging
    # If you only have one sensor, this ensures one clean line.
    fig = px.line(
        df, 
        x="timestamp", 
        y="reading_value",
        title="Live Sensor Readings",
        template="plotly_dark",
        color="sensor_name" # This separates data into distinct lines
    )

    fig.update_layout(xaxis=dict(rangeslider=dict(visible=True)))
    st.plotly_chart(fig, use_container_width=True)

    # Diagnostic: Check the very last 3 rows
    st.write("Latest rows in memory:", df.tail(3))

else:
    st.info("No data found. Check Supabase connection.")

# 6. Rerun Logic
time.sleep(10)
st.rerun()