import streamlit as st
import pandas as pd
import plotly.express as px
from st_supabase_connection import SupabaseConnection

st.set_page_config(layout="wide")
conn = st.connection("supabase", type=SupabaseConnection)

# NO CACHE FOR DEBUGGING
response = conn.table("sensor_data").select("*").order("timestamp", desc=True).limit(200).execute()
df = pd.DataFrame(response.data)
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
df = df.sort_values("timestamp")

st.subheader("Time Diagnostic")
st.write(f"Newest Row in DB: {df['timestamp'].max()}")
st.write(f"Current Time UTC: {pd.Timestamp.now(tz='UTC')}")

fig = px.line(df, x="timestamp", y="reading_value")
# This forces the X-axis to show the actual data range
fig.update_xaxes(autorange=True) 
st.plotly_chart(fig, use_container_width=True)

import time
time.sleep(10)
st.rerun()