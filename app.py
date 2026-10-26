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
@st.cache_data(ttl=3600)
def fetch_rainfall_data(dates):
    lat, lon = 52.0505, -4.3444 
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=precipitation&timezone=GMT&past_days=31&forecast_days=1"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        hourly = r.json().get('hourly', {})
        if not hourly: return pd.DataFrame()
        temp_df = pd.DataFrame({"timestamp": pd.to_datetime(hourly.get('time')), "rainfall": hourly.get('precipitation', [])})
        temp_df['timestamp'] = temp_df['timestamp'].dt.tz_localize(None)
        mask = (temp_df['timestamp'].dt.date >= dates[0]) & (temp_df['timestamp'].dt.date <= dates[1])
        return temp_df.loc[mask].copy()
    except: return pd.DataFrame()

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

# Updated: Renamed caption and defaulted all checkboxes to False
show_rain = st.sidebar.checkbox("Show Rainfall data (last 30 days)", value=False)
show_raw_data = st.sidebar.checkbox("Show Raw Data Points", value=False)
show_diurnal_adj = st.sidebar.checkbox("Show Diurnal Adjusted Depth (Stable)", value=False)
show_solar = st.sidebar.checkbox("Show Sunrise/Sunset", value=False)
window_size = st.sidebar.slider("Trend Smoothing", 1, 100, 20)

refresh_rate = st.sidebar.slider("Auto-Refresh (secs)", 60, 180, 60)

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
        df["roc"] = (val_future - val_past) / ((t_future - t_past).dt.total_seconds() /
