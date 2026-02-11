import streamlit as st
import pandas as pd
import plotly.express as px
from st_supabase_connection import SupabaseConnection
import time

st.set_page_config(page_title="Nant Cledlyn, Drefach", layout="wide")

# 1. Sidebar Controls
st.sidebar.header("Analysis Settings")
window_size = st.sidebar.slider("Rolling Average Window", 1, 100, 20)
view_all = st.sidebar.checkbox("View All Data", value=False)
refresh_rate = st.sidebar.slider("Refresh Rate (seconds)", 5, 60, 10)

st.title("📡 Live Sensor Data & Trend Analysis")

conn = st.connection("supabase", type=SupabaseConnection)

@st.cache_data(ttl=refresh_rate)
def fetch_data(show_all):
    try:
        query = conn.table("sensor_data").select("*").order("timestamp", desc=True)
        if not show_all:
            query = query.limit(500)
            
        response = query.execute()
        df = pd.DataFrame(response.data)
        
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            # Remove duplicates and sort for time-series integrity
            df = df.drop_duplicates(subset=['timestamp']).sort_values(by="timestamp")
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame()

df = fetch_data(view_all)

if not df.empty:
    # 2. Calculate Rolling Average
    # min_periods=1 ensures the line draws from the very first data point
    df["rolling_avg"] = df["reading_value"].rolling(window=window_size, min_periods=1).mean()

    # 3. Create Primary Chart (Raw Data)
    fig = px.line(
        df, 
        x="timestamp", 
        y="reading_value", 
        title=f"Sensor Readings with {window_size}-Sample Average",
        template="plotly_dark",
        color_discrete_sequence=['#33C3F0'] # Clean Blue for raw data
    )

    # 4. Add the Rolling Average Line
    fig.add_scatter(
        x=df["timestamp"], 
        y=df["rolling_avg"], 
        mode='lines',
        name=f'{window_size}-Sample Avg',
        line=dict(color='rgba(255, 255, 255, 0.6)', width=1.5, dash='dot'),
        hoverinfo='skip'
    )

    # 5. Format X-Axis Font and Layout
    fig.update_layout(
        xaxis=dict(
            rangeslider=dict(visible=True),
            tickfont=dict(size=18), # Large font for readability
            title=dict(font=dict(size=20))
        ),
        yaxis=dict(title="Reading Value"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    st.plotly_chart(fig, use_container_width=True)

    # Show the Latest Stats
    c1, c2, c3 = st.columns(3)
    c1.metric("Live Reading", f"{df['reading_value'].iloc[-1]:.2f}")
    c2.metric("Rolling Average", f"{df['rolling_avg'].iloc[-1]:.2f}")
    c3.metric("Data Points", len(df))

else:
    st.warning("No data found. Check your Pico 2 W connection.")

# 6. Heartbeat Refresh
time.sleep(refresh_rate)
st.rerun()