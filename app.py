import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from st_supabase_connection import SupabaseConnection
import time
from datetime import datetime, timedelta
import math
import requests

# 1. Page Configuration
st.set_page_config(page_title="Nant Cledlyn Monitor", page_icon="🌊", layout="wide")

# 2. Database Connection
conn = st.connection("supabase", type=SupabaseConnection)

# --- RAINFALL FETCHING ---
@st.cache_data(ttl=3600)
def fetch_rainfall_data(dates):
    lat, lon = 52.0505, -4.3444 
    # Use forecast endpoint to ensure today/yesterday are included
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=precipitation&timezone=GMT&past_days=92&forecast_days=1&models=ukmo_ukv"
    try:
        response = requests.get(url).json()
        hourly = response.get('hourly', {})
        temp_df = pd.DataFrame({
            "timestamp": pd.to_datetime(hourly.get('time')),
            "rainfall": hourly.get('precipitation')
        })
        mask = (temp_df['timestamp'].dt.date >= dates[0]) & (temp_df['timestamp'].dt.date <= dates[1])
        return temp_df.loc[mask]
    except:
        return pd.DataFrame()

# --- SOLAR CALCULATION ---
def get_solar_events(start_date, end_date):
    sunrises, sunsets = [], []
    lat, lon = 52.4, -4.0
    curr_date = start_date
    while curr_date <= end_date:
        n = curr_date.timetuple().tm_yday
        decl = 23.45 * math.sin(math.radians(360 / 365 * (n - 81)))
        try:
            cos_h = (math.sin(math.radians(-0.83)) - math.sin(math.radians(lat)) * math.sin(math.radians(decl))) / \
                    (math.cos(math.radians(lat)) * math.cos(math.radians(decl)))
            h = math.degrees(math.acos(cos_h))
            noon = 12 - (lon / 15) + 1 # BST
            base_dt = datetime.combine(curr_date, datetime.min.time())
            sunrises.append(base_dt + timedelta(hours=noon - (h / 15)))
            sunsets.append(base_dt + timedelta(hours=noon + (h / 15)))
        except: pass
        curr_date += timedelta(days=1)
    return sunrises, sunsets

# 3. Sidebar
st.sidebar.header("🎛️ Dashboard Controls")
MIN_DATA_DATE = datetime(2026, 4, 11).date()
today = datetime.now().date()
date_range = st.sidebar.date_input("Select Date Range", value=(MIN_DATA_DATE, today), min_value=MIN_DATA_DATE, max_value=today)

show_rain = st.sidebar.checkbox("Overlay Met Office Rainfall", value=True)
show_solar = st.sidebar.checkbox("Show Sunrise/Sunset", value=True)
window_size = st.sidebar.slider("Trend Smoothing", 1, 100, 20)
refresh_rate = st.sidebar.slider("Auto-Refresh (secs)", 5, 60, 10)

if st.sidebar.button("🔄 Force Refresh"):
    st.cache_data.clear()
    st.rerun()

# --- DATA FETCHING ---
def fetch_paginated_data(query_builder):
    all_rows = []
    page_size, offset = 1000, 0
    while True:
        res = query_builder.range(offset, offset + page_size - 1).execute()
        all_rows.extend(res.data)
        if len(res.data) < page_size: break
        offset += page_size
    return pd.DataFrame(all_rows)

@st.cache_data(ttl=refresh_rate)
def fetch_filtered_data(dates):
    if not isinstance(dates, (list, tuple)) or len(dates) != 2: return pd.DataFrame()
    start_dt, end_dt = datetime.combine(dates[0], datetime.min.time()).isoformat(), datetime.combine(dates[1], datetime.max.time()).isoformat()
    q = conn.table("sensor_data").select("*").gte("timestamp", start_dt).lte("timestamp", end_dt).order("timestamp", desc=True)
    df = fetch_paginated_data(q)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["reading_value"] = pd.to_numeric(df["reading_value"], errors='coerce')
        df = df.dropna(subset=['reading_value']).sort_values("timestamp")
        df["rolling_avg"] = df["reading_value"].rolling(window=window_size, win_type='gaussian', center=True, min_periods=1).mean(std=window_size/4)
        df["date_label"] = df["timestamp"].dt.date.astype(str)
        df["time_of_day"] = df["timestamp"].dt.hour + df["timestamp"].dt.minute/60
        daily_stats = df.groupby("date_label")["reading_value"].agg(['min', 'max']).reset_index()
        df = df.merge(daily_stats, on="date_label")
        df["daily_pct"] = (df["reading_value"] - df["min"]) / (df["max"] - df["min"]) * 100
        df.loc[df["max"] == df["min"], "daily_pct"] = 0 
    return df

# 4. Main UI Execution
st.title("🌊 Nant Cledlyn Water Level Analysis")
st.subheader("by Hugh Neve")

df = fetch_filtered_data(date_range)

if not df.empty:
    latest_time = df.iloc[-1]["timestamp"].strftime("%d %b %Y, %H:%M")
    st.info(f"🕒 **Last Update:** {latest_time} | Status: 201 Created")

    # --- PLOT 1: TIMELINE ---
    fig1 = go.Figure()
    
    # Initialize max_rain default
    max_rain = 5
    
    if show_rain:
        rain_df = fetch_rainfall_data(date_range)
        if not rain_df.empty:
            max_rain = max(rain_df["rainfall"].max() * 2, 5)
            fig1.add_trace(go.Bar(
                x=rain_df["timestamp"], y=rain_df["rainfall"],
                name='Rain (mm)', yaxis='y2',
                marker_color='rgba(51, 195, 240, 0.4)',
                hovertemplate='%{y} mm'
            ))

    fig1.add_trace(go.Scatter(x=df["timestamp"], y=df["reading_value"], name='Depth (cm)', line=dict(color='#33C3F0', width=2)))
    fig1.add_trace(go.Scatter(x=df["timestamp"], y=df["rolling_avg"], name='Trend', line=dict(color='#FFA500', dash='dot')))

    if show_solar:
        sunrises, sunsets = get_solar_events(date_range[0], date_range[1])
        y_max = df["reading_value"].max() * 1.05
        fig1.add_trace(go.Scatter(x=sunrises, y=[y_max]*len(sunrises), mode='markers', name='Sunrise', marker=dict(symbol='triangle-up', size=10, color='#FFD700'), hoverinfo='skip'))
        fig1.add_trace(go.Scatter(x=sunsets, y=[y_max]*len(sunsets), mode='markers', name='Sunset', marker=dict(symbol='triangle-down', size=10, color='#FF4500'), hoverinfo='skip'))

    fig1.update_layout(
        template="plotly_dark", height=450,
        xaxis=dict(rangeslider=dict(visible=True)),
        yaxis=dict(title="River Depth (cm)", side="left"),
        yaxis2=dict(title="Rainfall (mm)", overlaying='y', side='right', range=[max_rain, 0], showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig1, use_container_width=True)

    # --- PLOT 2: DIURNAL ---
    st.markdown("### 🕒 Diurnal Overlay (%)")
    fig2 = go.Figure()
    unique_days = sorted(df["date_label"].unique())
    colors = px.colors.sample_colorscale("Viridis", [i/(len(unique_days) or 1) for i in range(len(unique_days))])
    
    for i, day in enumerate(unique_days):
        day_df = df[df["date_label"] == day]
        fig2.add_trace(go.Scatter(x=day_df["time_of_day"], y=day_df["daily_pct"], mode='lines', name=day, line=dict(width=1, color=colors[i]), opacity=0.2, hoverinfo='skip'))
    
    agg_trend = df.groupby(df["time_of_day"].round(1))["daily_pct"].mean().reset_index()
    fig2.add_trace(go.Scatter(x=agg_trend["time_of_day"], y=agg_trend["daily_pct"], name='Avg Trend', line=dict(color='red', width=4)))
    
    fig2.update_layout(template="plotly_dark", height=450, xaxis=dict(title="Hour of Day", range=[0, 24]), yaxis=dict(title="Daily Range (%)"))
    st.plotly_chart(fig2, use_container_width=True)

    # Download Button
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download View CSV", data=csv, file_name="nant_cledlyn.csv", mime="text/csv")
    
    # Trigger refresh only after everything is rendered
    time.sleep(refresh_rate)
    st.rerun()

else:
    st.info("No river data found. Try expanding the date range.")
    # Stop execution here if no data, preventing the rerun loop from firing empty charts
    st.stop()
