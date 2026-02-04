import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.figure_factory as ff # For the distribution plot
from st_supabase_connection import SupabaseConnection
import time

st.set_page_config(page_title="Sensor Monitor", layout="wide")

# 1. Sidebar Controls
st.sidebar.header("Settings")
view_all = st.sidebar.checkbox("View All Data", value=False)
refresh_rate = st.sidebar.slider("Refresh Rate (seconds)", 5, 60, 10)

st.title("📡 Live Sensor Data & Statistical Analysis")

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
            df = df.drop_duplicates(subset=['timestamp']).sort_values(by="timestamp")
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame()

df = fetch_data(view_all)

if not df.empty:
    # --- SECTION 1: Time Series Line Chart ---
    st.subheader("Time Series History")
    fig_line = px.line(df, x="timestamp", y="reading_value", template="plotly_dark")
    fig_line.update_layout(xaxis=dict(rangeslider=dict(visible=True)))
    st.plotly_chart(fig_line, use_container_width=True)

    # --- SECTION 2: Statistical Distribution ---
    st.divider()
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Normalised Distribution (KDE)")
        
        # Prepare data for Distplot (must be a list of lists)
        hist_data = [df['reading_value'].dropna().tolist()]
        group_labels = ['Sensor Readings'] 

        # Create distplot with curve
        fig_dist = ff.create_distplot(
            hist_data, 
            group_labels, 
            bin_size=.5, # Adjust this based on your data precision
            curve_type='kde', # 'kde' or 'normal'
            colors=['#33C3F0']
        )
        fig_dist.update_layout(template="plotly_dark", showlegend=False)
        st.plotly_chart(fig_dist, use_container_width=True)

    with col2:
        st.subheader("Quick Stats")
        # Display key metrics for the distribution
        st.metric("Mean (Average)", f"{df['reading_value'].mean():.2f}")
        st.metric("Std Deviation", f"{df['reading_value'].std():.2f}")
        st.metric("Max Reading", f"{df['reading_value'].max():.2f}")
        st.metric("Min Reading", f"{df['reading_value'].min():.2f}")

else:
    st.warning("No data found.")

# Auto-Refresh
time.sleep(refresh_rate)
st.rerun()