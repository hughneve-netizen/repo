import streamlit as st
import pandas as pd
import plotly.graph_objects as go
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

# --- SOLAR CALCULATION LOGIC (Simplified for Ceredigion approx 52.4°N, 4.0°W) ---
def get_solar_events(start_date, end_date):
    """
    Calculates approximate sunrise and sunset for the Ceredigion area.
    This uses a simplified solar geometry calculation.
    """
    sunrises = []
    sunsets = []
    
    # Coordinates for the Drefach/Aberystwyth area
    lat = 52.4
    lon = -4.0
    
    curr_date = start_date
    while curr_date <= end_date:
        # Day of the year
        n = curr_date.timetuple().tm_yday
        
        # Simplified solar declination
        decl = 23.45 * math.sin(math.radians(360 / 365 * (n - 81)))
        
        # Hour angle (at sunset/sunrise altitude -0.83)
        # cos(h) = (sin(-0.83) - sin(lat)sin(decl)) / (cos(lat)cos(decl))
        try:
            cos_h = (math.sin(math.radians(-0.83)) - math.sin(math.radians(lat)) * math.sin(math.radians(decl))) / \
                    (math.cos(math.radians(lat)) * math.cos(math.radians(decl)))
            h = math.degrees(math.acos(cos_h))
            
            # Equation of time offset (very simplified)
            eot = 9.87 * math.sin(math.radians(2 * (360 / 364 * (n - 81)))) - \
                  7.53 * math.cos(math.radians(360 / 364 * (n - 81))) - \
                  1.5 * math.sin(math.radians(360 / 364 * (n - 81)))
            
            # Solar Noon in UTC (approx)
            # 12:00 - lon/15 - eot/60
            # Note: For April 2026, we must account for BST (+1 hour)
            is_bst = True # April is in BST
            tz_offset = 1 if is_bst else 0
            
            noon = 12 - (lon / 15) - (eot / 60) + tz_offset
            
            sunrise_hour = noon - (h / 15)
            sunset_hour = noon + (h / 15)
            
            # Convert decimal hours to datetime
            base_dt = datetime.combine(curr_date, datetime.min.time())
            sunrises.append(base_dt + timedelta(hours=sunrise_hour))
            sunsets.append(base_dt + timedelta(hours=sunset_hour))
        except:
            pass # Handle edge cases for extreme latitudes
            
        curr_date += timedelta(days=1)
        
    return sunrises, sunsets

# 3. Sidebar Controls
st.sidebar.header("🎛️ Dashboard Controls")

MIN_DATA_DATE = datetime(2026, 4, 11).date()
today = datetime.now().date()

date_range = st.sidebar.date_input(
    "Select Date Range",
    value=(MIN_DATA_DATE, today),
    min_value=MIN_DATA_DATE,
    max_value=today
)

show_solar = st.sidebar.checkbox("Show Sunrise/Sunset Markers", value=True)
window_size = st.sidebar.slider("Trend Smoothing (Window)", 1, 100, 20)
refresh_rate = st.sidebar.slider("Auto-Refresh (seconds)", 5, 60, 10)

if st.sidebar.button("🗑️ Clear Cache"):
    st.cache_data.clear()
    st.rerun()

# --- DATA FETCHING ---
def fetch_paginated_data(query_builder):
    all_rows = []
    page_size = 1000
    offset = 0
    while True:
        response = query_builder.range(offset, offset + page_size - 1).execute()
        data = response.data
        all_rows.extend(data)
        if len(data) < page_size:
            break
        offset += page_size
    return pd.DataFrame(all_rows)

@st.cache_data(ttl=refresh_rate)
def fetch_filtered_data(dates):
    if not isinstance(dates, (list, tuple)) or len(dates) != 2:
        return pd.DataFrame()
    start_date = datetime.combine(dates[0], datetime.min.time()).isoformat()
    end_date = datetime.combine(dates[1], datetime.max.time()).isoformat()
    
    query = conn.table("sensor_data").select("*")\
        .gte("timestamp", start_date)\
        .lte("timestamp", end_date)\
        .order("timestamp", desc=True)
        
    df = fetch_paginated_data(query)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["reading_value"] = pd.to_numeric(df["reading_value"], errors='coerce')
        df = df.dropna(subset=['reading_value']).sort_values(by="timestamp")
        df["rolling_avg"] = df["reading_value"].rolling(
            window=window_size, win_type='gaussian', center=True, min_periods=1
        ).mean(std=window_size/4)
    return df

# 4. Main Page Content
st.title("🌊 Nant Cledlyn Water Level Analysis")
st.subheader("by Hugh Neve")

df = fetch_filtered_data(date_range)

if not df.empty:
    latest_val = df["reading_value"].iloc[-1]
    c1, c2 = st.columns(2)
    c1.metric("Latest Depth", f"{latest_val:.1f} cm")
    c2.metric("Records in View", f"{len(df):,}")

    fig = go.Figure()

    # River Data
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df["reading_value"],
        name='Raw Depth', line=dict(color='#33C3F0', width=1.5)
    ))

    # Trend Line
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df["rolling_avg"],
        name='Trend', line=dict(color='#FFA500', width=2, dash='dot')
    ))

    # Solar Markers
    if show_solar:
        sunrises, sunsets = get_solar_events(date_range[0], date_range[1])
        y_max = df["reading_value"].max() * 1.05
        
        # Add Sunrises (Yellow Triangles Up)
        fig.add_trace(go.Scatter(
            x=sunrises, y=[y_max] * len(sunrises),
            mode='markers', name='Sunrise',
            marker=dict(symbol='triangle-up', size=12, color='#FFD700'),
            text=[f"Sunrise: {s.strftime('%H:%M')}" for s in sunrises],
            hoverinfo='text'
        ))
        
        # Add Sunsets (Orange-Red Triangles Down)
        fig.add_trace(go.Scatter(
            x=sunsets, y=[y_max] * len(sunsets),
            mode='markers', name='Sunset',
            marker=dict(symbol='triangle-down', size=12, color='#FF4500'),
            text=[f"Sunset: {s.strftime('%H:%M')}" for s in sunsets],
            hoverinfo='text'
        ))

    fig.update_layout(
        template="plotly_dark", height=600,
        margin=dict(l=50, r=50, t=50, b=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(title="Time", rangeslider=dict(visible=True)),
        yaxis=dict(title="Approx. Depth (cm)")
    )

    st.plotly_chart(fig, use_container_width=True)

    # Download Button
    st.markdown("---")
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label=f"📥 Download Filtered Range ({len(df):,} rows)",
        data=csv,
        file_name=f"nant_cledlyn_{date_range[0]}_to_{date_range[1]}.csv",
        mime="text/csv"
    )
else:
    st.info("No data found for the selected range.")

time.sleep(refresh_rate)
st.rerun()
