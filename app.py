import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from st_supabase_connection import SupabaseConnection
import time
from datetime import datetime, timedelta
import math

# 1. Page Configuration
st.set_page_config(
    page_title="Nant Cledlyn Monitor",
    page_icon="🌊",
    layout="wide"
)

# 2. Database Connection
conn = st.connection("supabase", type=SupabaseConnection)

# --- SOLAR CALCULATION LOGIC ---
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
            eot = 9.87 * math.sin(math.radians(2 * (360 / 364 * (n - 81)))) - \
                  7.53 * math.cos(math.radians(360 / 364 * (n - 81))) - 1.5 * math.sin(math.radians(360 / 364 * (n - 81)))
            tz_offset = 1 
            noon = 12 - (lon / 15) - (eot / 60) + tz_offset
            base_dt = datetime.combine(curr_date, datetime.min.time())
            sunrises.append(base_dt + timedelta(hours=noon - (h / 15)))
            sunsets.append(base_dt + timedelta(hours=noon + (h / 15)))
        except: pass
        curr_date += timedelta(days=1)
    return sunrises, sunsets

# 3. Sidebar Controls
st.sidebar.header("🎛️ Dashboard Controls")
MIN_DATA_DATE = datetime(2026, 4, 11).date()
today = datetime.now().date()

date_range = st.sidebar.date_input("Select Date Range", value=(MIN_DATA_DATE, today), min_value=MIN_DATA_DATE, max_value=today)
show_solar = st.sidebar.checkbox("Show Sunrise/Sunset Markers", value=True)
window_size = st.sidebar.slider("Trend Smoothing (Window)", 1, 100, 20)
refresh_rate = st.sidebar.slider("Auto-Refresh (seconds)", 5, 60, 10)

if st.sidebar.button("🗑️ Clear Cache"):
    st.cache_data.clear()
    st.rerun()

# --- DATA FETCHING ---
def fetch_paginated_data(query_builder):
    all_rows = []
    page_size, offset = 1000, 0
    while True:
        response = query_builder.range(offset, offset + page_size - 1).execute()
        data = response.data
        all_rows.extend(data)
        if len(data) < page_size: break
        offset += page_size
    return pd.DataFrame(all_rows)

@st.cache_data(ttl=refresh_rate)
def fetch_filtered_data(dates):
    if not isinstance(dates, (list, tuple)) or len(dates) != 2: return pd.DataFrame()
    q = conn.table("sensor_data").select("*").gte("timestamp", dates[0].isoformat()).lte("timestamp", dates[1].isoformat()).order("timestamp", desc=True)
    df = fetch_paginated_data(q)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["reading_value"] = pd.to_numeric(df["reading_value"], errors='coerce')
        df = df.dropna(subset=['reading_value']).sort_values(by="timestamp")
        df["rolling_avg"] = df["reading_value"].rolling(window=window_size, win_type='gaussian', center=True, min_periods=1).mean(std=window_size/4)
        
        # Prepare data for diurnal plot
        df["date_label"] = df["timestamp"].dt.date.astype(str)
        # Round time to nearest 5 minutes for smoother aggregate trendline
        df["time_of_day"] = df["timestamp"].dt.hour + df["timestamp"].dt.minute/60 + df["timestamp"].dt.second/3600
        df["time_bin"] = (df["time_of_day"] * 12).round() / 12  # 5-minute bins
        
        daily_stats = df.groupby("date_label")["reading_value"].agg(['min', 'max']).reset_index()
        df = df.merge(daily_stats, on="date_label")
        df["daily_pct"] = (df["reading_value"] - df["min"]) / (df["max"] - df["min"]) * 100
        df.loc[df["max"] == df["min"], "daily_pct"] = 0 
        
    return df

# 4. Main Page Content
st.title("🌊 Nant Cledlyn Water Level Analysis")
st.subheader("by Hugh Neve")

df = fetch_filtered_data(date_range)

if not df.empty:
    # --- CHART 1: TIMELINE ---
    st.markdown("### 📈 Chronological Timeline")
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=df["timestamp"], y=df["reading_value"], name='Raw Depth (cm)', line=dict(color='#33C3F0', width=1.5)))
    fig1.add_trace(go.Scatter(x=df["timestamp"], y=df["rolling_avg"], name='Trend', line=dict(color='#FFA500', width=2, dash='dot')))
    
    if show_solar:
        sunrises, sunsets = get_solar_events(date_range[0], date_range[1])
        y_max = df["reading_value"].max() * 1.05
        fig1.add_trace(go.Scatter(x=sunrises, y=[y_max]*len(sunrises), mode='markers', name='Sunrise', marker=dict(symbol='triangle-up', size=10, color='#FFD700'), hoverinfo='text', text=[f"Sunrise: {s.strftime('%H:%M')}" for s in sunrises]))
        fig1.add_trace(go.Scatter(x=sunsets, y=[y_max]*len(sunsets), mode='markers', name='Sunset', marker=dict(symbol='triangle-down', size=10, color='#FF4500'), hoverinfo='text', text=[f"Sunset: {s.strftime('%H:%M')}" for s in sunsets]))

    fig1.update_layout(template="plotly_dark", height=400, margin=dict(t=30), xaxis=dict(rangeslider=dict(visible=True)), yaxis=dict(title="Depth (cm)"))
    st.plotly_chart(fig1, use_container_width=True)

    # --- CHART 2: DIURNAL OVERLAY (NORMALIZED PERCENTAGE) ---
    st.markdown("### 🕒 Diurnal Overlay with Aggregate Trend")
    
    fig2 = go.Figure()
    unique_days = sorted(df["date_label"].unique())
    # Faded colors for individual days to let the trendline pop
    colors = px.colors.sample_colorscale("Viridis", [i/(len(unique_days) or 1) for i in range(len(unique_days))])

    for i, day in enumerate(unique_days):
        day_df = df[df["date_label"] == day]
        fig2.add_trace(go.Scatter(
            x=day_df["time_of_day"], y=day_df["daily_pct"],
            mode='lines', name=day,
            line=dict(width=1, color=colors[i]),
            opacity=0.4, # Make individual days slightly transparent
            hoverinfo='skip'
        ))

    # --- ADD THICK RED TRENDLINE ---
    # Aggregate all days by the time bins
    agg_trend = df.groupby("time_bin")["daily_pct"].mean().reset_index().sort_values("time_bin")
    
    fig2.add_trace(go.Scatter(
        x=agg_trend["time_bin"], 
        y=agg_trend["daily_pct"],
        mode='lines',
        name='Overall Average Trend',
        line=dict(color='red', width=4), # Thicker and Red
        hovertemplate="<b>Avg Trend</b><br>Time: %{x:.2f}h<br>Avg Relative: %{y:.1f}%<extra></extra>"
    ))

    fig2.update_layout(
        template="plotly_dark", height=500, margin=dict(t=30),
        xaxis=dict(
            title="Hour of Day",
            tickvals=[0, 3, 6, 9, 12, 15, 18, 21, 24],
            ticktext=['00:00', '03:00', '06:00', '09:00', '12:00', '15:00', '18:00', '21:00', '24:00'],
            range=[0, 24]
        ),
        yaxis=dict(title="Daily Range (%)", range=[-5, 105]),
        legend=dict(title="Legend", orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig2, use_container_width=True)

    # Download Button
    st.markdown("---")
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(label=f"📥 Download Data ({len(df):,} rows)", data=csv, file_name=f"nant_cledlyn_analysis.csv", mime="text/csv")
else:
    st.info("No data found for the selected range.")

time.sleep(refresh_rate)
st.rerun()
