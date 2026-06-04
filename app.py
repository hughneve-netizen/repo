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

# --- HYDROLOGICAL ANALYSIS FUNCTIONS ---
def estimate_lag_time(df, rain_df):
    if df.empty or rain_df.empty: return None
    sig_rain = rain_df[rain_df['rainfall'] > 0.5].copy()
    if sig_rain.empty: return "No heavy rain in view"
    sig_rain['timestamp'] = sig_rain['timestamp'].dt.tz_localize(None)
    rain_peak_time = sig_rain.loc[sig_rain['rainfall'].idxmax(), 'timestamp']
    df_compare = df.copy()
    df_compare['timestamp'] = df_compare['timestamp'].dt.tz_localize(None)
    response_window = df_compare[(df_compare['timestamp'] > rain_peak_time) & 
                                 (df_compare['timestamp'] < rain_peak_time + timedelta(hours=12))]
    if response_window.empty or response_window['roc'].dropna().empty:
        return "Awaiting river response..."
    if response_window['roc'].max() <= 0:
        return "No significant rise detected"
    river_peak_time = response_window.loc[response_window['roc'].idxmax(), 'timestamp']
    lag_hrs = (river_peak_time - rain_peak_time).total_seconds() / 3600
    return round(lag_hrs, 2)

def estimate_recession_index(df):
    if df.empty or len(df) < 24: return None
    recent = df.tail(24) 
    valid_roc = recent['roc'].dropna()
    if not valid_roc.empty and valid_roc.mean() < 0:
        k = abs(valid_roc.mean() / recent['reading_value'].mean())
        return round(k, 4)
    return "Steady/Rising"

# --- RAINFALL FETCHING ---
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_rainfall_data(dates):
    lat, lon = 52.0505, -4.3444 
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=precipitation&timezone=GMT&past_days=31&forecast_days=1"
    
    max_retries = 2
    for attempt in range(max_retries):
        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            
            hourly = r.json().get('hourly', {})
            if not hourly: 
                st.warning("Rainfall API connected, but returned no data.")
                return pd.DataFrame()
                
            temp_df = pd.DataFrame({
                "timestamp": pd.to_datetime(hourly.get('time')), 
                "rainfall": hourly.get('precipitation', [])
            })
            temp_df['timestamp'] = temp_df['timestamp'].dt.tz_localize(None)
            
            mask = (temp_df['timestamp'].dt.date >= dates[0]) & (temp_df['timestamp'].dt.date <= dates[1])
            final_df = temp_df.loc[mask].copy()
            
            if final_df.empty:
                st.info("Rainfall data fetched, but none falls within your selected Date Range.")
                
            return final_df
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                st.error("⚠️ Rainfall API Rate Limit Reached: Please try again in 15 minutes.")
            else:
                st.error(f"⚠️ Rainfall API Error: HTTP {e.response.status_code}")
            return pd.DataFrame()
            
        except requests.exceptions.ReadTimeout:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            else:
                st.error("⚠️ Rainfall API Error: The Open-Meteo server timed out.")
                return pd.DataFrame()
                
        except Exception as e: 
            st.error(f"⚠️ Rainfall API Error: {e}")
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
            noon = 12 - (lon / 15) + 1 
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

show_rain = st.sidebar.checkbox("Overlay Rainfall Data", value=True)
show_raw_data = st.sidebar.checkbox("Show Raw Data Points", value=True)
show_diurnal_adj = st.sidebar.checkbox("Show Diurnal Adjusted Depth (Stable)", value=True)
show_solar = st.sidebar.checkbox("Show Sunrise/Sunset", value=True)
window_size = st.sidebar.slider("Trend Smoothing", 1, 100, 20)

refresh_rate = st.sidebar.slider("Auto-Refresh (secs)", min_value=300, max_value=1800, value=300, step=60)

if st.sidebar.button("🔄 Force Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# --- DATA FETCHING (Supabase) ---
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
        df = df.dropna(subset=['reading_value']).sort_values("timestamp").reset_index(drop=True)
        
        # 1. Base Time Mapping
        df["date_label"] = df["timestamp"].dt.date.astype(str)
        df["min_of_day"] = df["timestamp"].dt.hour * 60 + df["timestamp"].dt.minute
        
        # Calculate daily stats
        daily_stats = df.groupby("date_label")["reading_value"].agg(['min', 'max', 'mean']).reset_index()
        daily_stats["range"] = daily_stats["max"] - daily_stats["min"]
        df = df.merge(daily_stats, on="date_label")
        
        # Calculate daily percentage
        df["daily_pct"] = (df["reading_value"] - df["min"]) / df["range"].replace(0, 1) * 100
        df.loc[df["range"] == 0, "daily_pct"] = 50.0 

        # 2. SCIENTIFIC DIURNAL CORRECTION
        df["deviation_cm"] = df["reading_value"] - df["mean"]
        avg_diurnal_cm_trend = df.groupby("min_of_day")["deviation_cm"].transform("mean")
        df["adjusted_depth"] = df["reading_value"] - avg_diurnal_cm_trend

        # MATH: Rolling Average
        df["rolling_avg"] = df["reading_value"].rolling(window=window_size, win_type='gaussian', center=True, min_periods=1).mean(std=window_size/4)
        
        # MATH: Rate of Change
        val_future, val_past = df["reading_value"].shift(-5), df["reading_value"].shift(5)
        t_future, t_past = df["timestamp"].shift(-5), df["timestamp"].shift(5)
        df["roc"] = (val_future - val_past) / ((t_future - t_past).dt.total_seconds() / 60)
        
        df["time_of_day"] = df["timestamp"].dt.hour + df["timestamp"].dt.minute/60
        return df
    return pd.DataFrame()

# 4. Main UI Execution
st.title("🌊 Nant Cledlyn Water Level Analysis")
st.subheader("by Hugh Neve")

# --- INTRODUCTION SECTION ---
st.markdown("""
Welcome to the Nant Cledlyn Water Level Analysis dashboard. 

*Insert your plain text introduction here. You can use this space to describe the purpose of the dashboard, details about the Nant Cledlyn catchment, or instructions on how to use the analytical tools below.*
""")
st.markdown("---")
# -----------------------------

df = fetch_filtered_data(date_range)

if show_rain:
    with st.spinner("☁️ Fetching live rainfall data from Open-Meteo..."):
        rain_df = fetch_rainfall_data(date_range)
else:
    rain_df = pd.DataFrame()

if not df.empty:
    latest_time = df.iloc[-1]["timestamp"].strftime("%d %b %Y, %H:%M")
    st.info(f"🕒 **Last Update:** {latest_time} UTC | Records Viewable: {len(df):,}")

    # Plot 1
    st.markdown("### 📈 Chronological Depth & Rainfall")
    fig1 = go.Figure()
    rain_max_val = 5
    if not rain_df.empty:
        rain_max_val = max(rain_df["rainfall"].max() * 1.5, 5)
        fig1.add_trace(go.Bar(x=rain_df["timestamp"], y=rain_df["rainfall"], name='Rain (mm)', yaxis='y2', marker_color='rgba(100, 149, 237, 0.4)', hovertemplate='Rain: %{y}mm'))

    if show_raw_data:
        fig1.add_trace(go.Scatter(
            x=df["timestamp"], 
            y=df["reading_value"], 
            name='Actual Depth (cm)', 
            mode='markers',
            marker=dict(color='#33C3F0', size=4)
        ))
    
    if show_diurnal_adj:
        fig1.add_trace(go.Scatter(x=df["timestamp"], y=df["adjusted_depth"], name='Diurnal Adjusted (Stable)', line=dict(color='#C70039', width=1.5, dash='dash')))

    fig1.add_trace(go.Scatter(x=df["timestamp"], y=df["rolling_avg"], name='Smooth Trend', line=dict(color='#FFA500', dash='dot')))

    if show_solar:
        sunrises, sunsets = get_solar_events(date_range[0], date_range[1])
        y_max_val = df["reading_value"].max() * 1.05
        fig1.add_trace(go.Scatter(x=sunrises, y=[y_max_val]*len(sunrises), mode='markers', name='Sunrise', marker=dict(symbol='triangle-up', size=8, color='#FFD700'), hoverinfo='skip'))
        fig1.add_trace(go.Scatter(x=sunsets, y=[y_max_val]*len(sunsets), mode='markers', name='Sunset', marker=dict(symbol='triangle-down', size=8, color='#FF4500'), hoverinfo='skip'))

    fig1.update_layout(
        template="plotly_dark", height=400, margin=dict(t=20, b=20),
        xaxis=dict(title="Time", showticklabels=True), 
        yaxis=dict(title="River Depth (cm)", side="left", range=[df["reading_value"].min() * 0.9, df["reading_value"].max() * 1.15]),
        yaxis2=dict(title="Rainfall (mm)", overlaying='y', side='right', range=[rain_max_val, 0], showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig1, use_container_width=True)

    # Plot 2
    st.markdown("### ⚡ Velocity of Rise / Fall with Rainfall Overlay")
    fig_roc = go.Figure()
    if not rain_df.empty:
        fig_roc.add_trace(go.Bar(x=rain_df["timestamp"], y=rain_df["rainfall"], name='Rain (mm)', yaxis='y2', marker_color='rgba(100, 149, 237, 0.2)', hovertemplate='Rain: %{y}mm'))
    fig_roc.add_trace(go.Scatter(x=df["timestamp"], y=df["roc"], name='RoC (cm/min)', line=dict(color='#FF4B4B', width=1.5), fill='tozeroy', fillcolor='rgba(255, 75, 75, 0.1)'))
    fig_roc.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
    
    fig_roc.update_layout(
        template="plotly_dark", height=300, margin=dict(t=10, b=10), 
        xaxis=dict(title="Time", matches="x"), 
        yaxis=dict(title="Velocity (cm / min)", side="left"), 
        yaxis2=dict(title="Rainfall (mm)", overlaying='y', side='right', range=[rain_max_val, 0], showgrid=False), 
        showlegend=False
    )
    st.plotly_chart(fig_roc, use_container_width=True)

    # Plot 3
    st.markdown("### 🕒 Diurnal Overlay (%)")
    fig2 = go.Figure()
    unique_days = sorted(df["date_label"].unique())
    colors = px.colors.sample_colorscale("Viridis", [i/(len(unique_days) or 1) for i in range(len(unique_days))])
    for i, day in enumerate(unique_days):
        day_df = df[df["date_label"] == day]
        fig2.add_trace(go.Scatter(x=day_df["time_of_day"], y=day_df["daily_pct"], mode='lines', name=day, line=dict(width=1, color=colors[i]), opacity=0.2, hoverinfo='skip'))
    agg_trend = df.groupby(df["time_of_day"].round(1))["daily_pct"].mean().reset_index()
    fig2.add_trace(go.Scatter(x=agg_trend["time_of_day"], y=agg_trend["daily_pct"], name='Avg Trend', line=dict(color='red', width=4)))
    fig2.update_layout(template="plotly_dark", height=450, xaxis=dict(title="Hour of Day (0-24)", range=[0, 24]), yaxis=dict(title="Daily Range (%)"))
    st.plotly_chart(fig2, use_container_width=True)

    # Intelligence Section
    st.markdown("---")
    st.header("🧠 Hydrological Catchment Intelligence")
    lag_val = estimate_lag_time(df, rain_df)
    k_val = estimate_recession_index(df)
    c1, c2 = st.columns(2)
    with c1:
        st.metric("Estimated Catchment Lag", f"{lag_val} Hours" if isinstance(lag_val, float) else lag_val)
        st.caption("The delay between peak rainfall and peak river rise velocity.")
    with c2:
        st.metric("Recession Index (k)", f"{k_val}" if isinstance(k_val, float) else k_val)
        st.caption("The rate of drainage (higher = faster drainage).")

    with st.expander("📚 View Mathematical Definitions & Equations"):
        st.markdown("### 1. Catchment Lag Time")
        st.latex(r"T_{lag} = t_{RoC_{max}} - t_{Rain_{max}}")
        st.markdown("### 2. Recession Constant ($k$)")
        st.latex(r"h_t = h_0 \cdot e^{-kt}")
        st.latex(r"k \approx \left| \frac{\Delta h / \Delta t}{\bar{h}} \right|")
        st.markdown("### 3. Diurnal Adjustment (Stable Residual Subtraction)")
        st.write("Isolates the absolute centimeter deviation from the day's mean to create an expected baseline wave, avoiding dangerous division artifacts.")
        st.latex(r"\Delta h(t) = h_{\text{actual}}(t) - \bar{h}_{\text{day}}")
        st.latex(r"h_{\text{adjusted}}(t) = h_{\text{actual}}(t) - \overline{\Delta h}(\text{minute of day})")

    st.download_button("📥 Download View CSV", data=df.to_csv(index=False).encode('utf-8'), file_name="nant_cledlyn.csv", mime="text/csv")
    time.sleep(refresh_rate)
    st.rerun()

else:
    st.info("No river data found.")
    time.sleep(refresh_rate)
    st.rerun()
