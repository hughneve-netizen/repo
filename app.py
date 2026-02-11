import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from st_supabase_connection import SupabaseConnection
import time

# 1. Page Configuration
st.set_page_config(
    page_title="Sensor Monitor Pro",
    page_icon="📡",
    layout="wide"
)

# 2. Sidebar Controls
st.sidebar.header("🎛️ Dashboard Controls")
window_size = st.sidebar.slider("Rolling Average Window", 1, 100, 20, 
                                 help="Number of samples used to calculate the trend line.")
view_all = st.sidebar.checkbox("View All Data", value=False, 
                                help="Uncheck to only load the last 500 points (faster).")
refresh_rate = st.sidebar.slider("Auto-Refresh (seconds)", 5, 60, 10)

if st.sidebar.button("🗑️ Clear Cache"):
    st.cache_data.clear()
    st.rerun()

st.title("📡 Real-Time Sensor Data & Trend Analysis")

# 3. Database Connection
conn = st.connection("supabase", type=SupabaseConnection)

# 4. Data Fetching Logic
@st.cache_data(ttl=refresh_rate)
def fetch_data(show_all):
    try:
        # Build query
        query = conn.table("sensor_data").select("*").order("timestamp", desc=True)
        
        if not show_all:
            query = query.limit(500)
            
        response = query.execute()
        df = pd.DataFrame(response.data)
        
        if not df.empty:
            # CLEANING DATA
            # Convert timestamp and handle timezones
            df["timestamp"] = pd.to_datetime(df["timestamp"])