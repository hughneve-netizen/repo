import streamlit as st
from st_supabase_connection import SupabaseConnection
import plotly.express as px

st.set_page_config(page_title="Live Cloud Sensor", layout="wide")

# 1. Initialize Connection
conn = st.connection("supabase", type=SupabaseConnection)

# 2. Fetch Data function
def get_data():
    # Queries the table we created earlier
    query = conn.table("sensor_data").select("timestamp, reading_value").execute()
    return query.data

st.title("📈 Nant Cledlyn Depth,Drefach")

try:
    rows = get_data()
    
    if rows:
        import pandas as pd
        query = conn.table("sensor_data").select("*").execute(ttl=10)
        df = pd.DataFrame(rows)
        
        # Convert timestamp to datetime for better plotting
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values(by="timestamp")
        st.write(f"Last successful fetch: {pd.to_datetime('now')}")
        # 3. Create Plotly Chart
        fig = px.line(
            df, 
            x="timestamp", 
            y="reading_value", 
            title="Interactive Sensor Data",
            template="plotly_dark"
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Display latest value as a big metric
        latest_val = df["reading_value"].iloc[-1]
        st.metric(label="Latest Reading", value=f"{latest_val} Units")
    else:
        st.info("Connected to Supabase, but no data found in the table yet.")

except Exception as e:
    st.error(f"Connection Error: {e}")

# 4. Auto-refresh UI (updates every 10 seconds)
if st.button("Manual Refresh"):
    st.rerun()

# This tells Streamlit to rerun the script automatically
st.empty()
import time
time.sleep(10)
st.rerun()
