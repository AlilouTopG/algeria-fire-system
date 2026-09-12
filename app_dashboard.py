import streamlit as st
import sqlite3
import os
import cv2
import time
import logging
import hashlib
import secrets
import math
import requests
import pandas as pd
import io
import tempfile
from datetime import datetime
from dotenv import load_dotenv
from ultralytics import YOLO
import folium
from streamlit_folium import folium_static
import plotly.express as px
from fpdf import FPDF
from geopy.distance import geodesic
import db_manager as db

# ==========================================
# Logging Configuration
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('dashboard.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# ==========================================
# Security Constants & Helpers
# ==========================================
SALT = os.getenv('PASSWORD_SALT', 'wildfire_system_salt_2026')

def hash_password(password: str) -> str:
    return hashlib.sha256(f"{SALT}{password}".encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

# Algeria bounding box for map restriction
ALGERIA_BOUNDS = {
    "south": 18.96,
    "west": -8.67,
    "north": 37.09,
    "east": 11.99
}

# ==========================================
# Database Initialization
# ==========================================
db.init_db()
db.init_civil_defense_table()

# ==========================================
# Language System (AR / EN)
# ==========================================
if "lang" not in st.session_state:
    st.session_state["lang"] = "AR"

TRANSLATIONS = {
    "AR": {
        "title": "🏛️ المنظومة الوطنية للرصد والإنذار المبكر",
        "login_tab": "🔐 تسجيل الدخول",
        "signup_tab": "📝 إنشاء حساب جديد",
        "user_label": "اسم المستخدم",
        "pass_label": "كلمة المرور",
        "btn_login": "دخول المنظومة",
        "logout": "🚪 تسجيل الخروج",
        "map_layers": "⚙️ خيارات الخريطة",
        "ndvi": "🌿 طبقة الغطاء النباتي (NDVI)",
        "stations": "🚒 مراكز الحماية المدنية",
        "routing": "📍 توجيه التدخل السريع",
        "simulation": "🔥 محاكاة انتشار النار",
        "manual_sim": "🎯 محاكاة يدوية",
        "lat": "خط العرض",
        "lon": "خط الطول",
        "run_sim": "▶️ تشغيل المحاكاة",
        "user_info": "بيانات الجلسة",
        "username_label": "المستخدم",
        "role_label": "الصلاحية"
    },
    "EN": {
        "title": "🏛️ National Early Warning & Command System",
        "login_tab": "🔐 Login",
        "signup_tab": "📝 Sign Up",
        "user_label": "Username",
        "pass_label": "Password",
        "btn_login": "Access System",
        "logout": "🚪 Logout",
        "map_layers": "⚙️ Map Layers",
        "ndvi": "🌿 Vegetation Layer (NDVI)",
        "stations": "🚒 Civil Defense Stations",
        "routing": "📍 Rapid Response Routing",
        "simulation": "🔥 Fire Spread Simulation",
        "manual_sim": "🎯 Manual Simulation",
        "lat": "Latitude",
        "lon": "Longitude",
        "run_sim": "▶️ Run Simulation",
        "user_info": "Session Info",
        "username_label": "Username",
        "role_label": "Role"
    }
}

def change_language():
    if st.session_state["lang_radio"] == "English":
        st.session_state["lang"] = "EN"
    else:
        st.session_state["lang"] = "AR"

selected_radio = "English" if st.session_state["lang"] == "EN" else "العربية"
st.sidebar.radio(
    "🌐 Language / اللغة",
    ["العربية", "English"],
    index=0 if selected_radio == "العربية" else 1,
    key="lang_radio",
    on_change=change_language,
    horizontal=True
)

t = TRANSLATIONS[st.session_state["lang"]]

# ==========================================
# Session State Initialization
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "user" not in st.session_state:
    st.session_state["user"] = None
if "role" not in st.session_state:
    st.session_state["role"] = None
if "simulation_active" not in st.session_state:
    st.session_state["simulation_active"] = False
if "sim_lat" not in st.session_state:
    st.session_state["sim_lat"] = 36.75
if "sim_lon" not in st.session_state:
    st.session_state["sim_lon"] = 3.05

# ==========================================
# Session Persistence via Query Params
# ==========================================
query_token = st.query_params.get("session_token", None)
if not st.session_state["authenticated"] and query_token:
    valid, user_name = db.verify_session_token(query_token)
    if valid:
        st.session_state["authenticated"] = True
        st.session_state["user"] = user_name
        st.session_state["role"] = "Admin"

# ==========================================
# Login Page
# ==========================================
if not st.session_state.get("authenticated", False):
    st.markdown(f"<h2 style='text-align: center; color: #00f2fe;'>{t['title']}</h2>", unsafe_allow_html=True)
    
    tab_login, tab_signup = st.tabs([t["login_tab"], t["signup_tab"]])
    
    with tab_login:
        with st.form(key="login_form"):
            user_in = st.text_input(t["user_label"])
            pass_in = st.text_input(t["pass_label"], type="password")
            if st.form_submit_button(t["btn_login"]):
                if user_in and pass_in:
                    success, role = db.authenticate_user(user_in, pass_in)
                    if success:
                        st.session_state["authenticated"] = True
                        st.session_state["user"] = user_in
                        st.session_state["role"] = role
                        token = db.generate_session_token(user_in)
                        if token:
                            st.query_params["session_token"] = token
                        st.rerun()
                    else:
                        st.error("خطأ في البيانات / Invalid credentials")
    
    with tab_signup:
        with st.form(key="signup_form"):
            new_user = st.text_input("اختر اسم مستخدم جديد")
            new_pass = st.text_input("اختر كلمة مرور قوية", type="password")
            role_sel = st.selectbox("نوع الصلاحية", ["Operator", "Analyst", "Admin"])
            submit_signup = st.form_submit_button("حفظ وإنشاء الحساب")
            
            if submit_signup:
                user_clean = new_user.strip()
                pass_clean = new_pass.strip()
                if user_clean and pass_clean:
                    ok, msg = db.register_user(user_clean, pass_clean, role_sel)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)
                else:
                    st.warning("يرجى ملء جميع الحقول!")

    st.stop()

# ==========================================
# Cached Data Functions
# ==========================================
@st.cache_data(ttl=300)
def get_cached_civil_defense_units():
    try:
        return db.get_all_civil_defense_units()
    except Exception:
        return []

@st.cache_data(ttl=300)
def get_fire_weather_index(lat: float, lon: float) -> dict:
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m"
            f"&timezone=Africa/Algiers"
        )
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        current = data.get('current', {})
        temp = current.get('temperature_2m', 25)
        humidity = current.get('relative_humidity_2m', 50)
        wind_speed = current.get('wind_speed_10m', 10)
        
        fwi_score = (temp * 0.3) + ((100 - humidity) * 0.4) + (wind_speed * 0.3)
        
        if fwi_score >= 70:
            danger_level = "extreme"
            danger_ar = "خطر شديد جداً"
            color = "#d32f2f"
        elif fwi_score >= 50:
            danger_level = "high"
            danger_ar = "خطر مرتفع"
            color = "#ff5722"
        elif fwi_score >= 30:
            danger_level = "moderate"
            danger_ar = "خطر متوسط"
            color = "#ff9800"
        elif fwi_score >= 15:
            danger_level = "low"
            danger_ar = "خطر منخفض"
            color = "#4caf50"
        else:
            danger_level = "minimal"
            danger_ar = "خطر ضئيل"
            color = "#8bc34a"
        
        return {
            "temperature": temp,
            "humidity": humidity,
            "wind_speed": wind_speed,
            "fwi_score": round(fwi_score, 1),
            "danger_level": danger_level,
            "danger_ar": danger_ar,
            "color": color
        }
    except Exception as e:
        logger.error(f"Open-Meteo API error: {e}")
        return {
            "temperature": "N/A",
            "humidity": "N/A",
            "wind_speed": "N/A",
            "fwi_score": 0,
            "danger_level": "unknown",
            "danger_ar": "غير محدد",
            "color": "#9e9e9e"
        }

@st.cache_data(ttl=300)
def predict_fire_risk_48h(lat: float, lon: float) -> dict:
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m"
            f"&forecast_days=2&timezone=Africa/Algiers"
        )
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        hourly_temps = data.get('hourly', {}).get('temperature_2m', [30])
        hourly_hum = data.get('hourly', {}).get('relative_humidity_2m', [30])
        hourly_wind = data.get('hourly', {}).get('wind_speed_10m', [15])
        
        max_risk = 0
        risk_hours = []
        
        for i, (t_val, h, w) in enumerate(zip(hourly_temps, hourly_hum, hourly_wind)):
            score = (t_val * 0.6) + (w * 0.9) - (h * 0.4)
            if score > max_risk:
                max_risk = score
            if score > 25:
                risk_hours.append(i)
        
        if max_risk > 40:
            risk_level = "critical"
            risk_ar = "خطر حرج جداً متوقع"
            color = "#d32f2f"
            emoji = "🔴"
        elif max_risk > 25:
            risk_level = "high"
            risk_ar = "خطر مرتفع متوقع"
            color = "#ff5722"
            emoji = "🟠"
        elif max_risk > 15:
            risk_level = "moderate"
            risk_ar = "خطر متوسط متوقع"
            color = "#ff9800"
            emoji = "🟡"
        else:
            risk_level = "low"
            risk_ar = "حالة مستقرة"
            color = "#4caf50"
            emoji = "🟢"
        
        return {
            "risk_level": risk_level,
            "risk_ar": risk_ar,
            "risk_score": round(max_risk, 1),
            "color": color,
            "emoji": emoji,
            "high_risk_hours": len(risk_hours),
            "avg_temp": round(sum(hourly_temps) / len(hourly_temps), 1),
            "avg_humidity": round(sum(hourly_hum) / len(hourly_hum), 1),
            "avg_wind": round(sum(hourly_wind) / len(hourly_wind), 1)
        }
    except Exception as e:
        logger.error(f"Predictive risk calculation failed: {e}")
        return {
            "risk_level": "unknown",
            "risk_ar": "غير محدد",
            "risk_score": 0,
            "color": "#9e9e9e",
            "emoji": "⚪",
            "high_risk_hours": 0,
            "avg_temp": 0,
            "avg_humidity": 0,
            "avg_wind": 0
        }

# ==========================================
# Sidebar - User Info & Controls
# ==========================================
st.sidebar.markdown("<h2 style='text-align:center; color:#00f2fe;'>🏛️ Command Center</h2>", unsafe_allow_html=True)
st.sidebar.markdown("---")

current_user = st.session_state.get('user', 'مستخدم')
current_role = st.session_state.get('role', 'Operator')

st.sidebar.markdown(f"<h3 style='color:#00f2fe;'>{t['user_info']}</h3>", unsafe_allow_html=True)
st.sidebar.markdown(f"<p style='color:#fff;'>👤 <b>{t['username_label']}:</b> {current_user}</p>", unsafe_allow_html=True)
st.sidebar.markdown(f"<p style='color:#fff;'>🛡️ <b>{t['role_label']}:</b> {current_role}</p>", unsafe_allow_html=True)

if st.sidebar.button(t["logout"]):
    st.session_state['authenticated'] = False
    st.session_state['user'] = None
    st.session_state['role'] = None
    st.rerun()

# Data source selection
data_source = st.sidebar.radio(
    "مصدر البيانات | Data Source:",
    ["📹 الكاميرات المباشرة (Live Cameras)", "🛰️ الأقمار الصناعية (NASA FIRMS Satellite)"]
)

# Map controls in sidebar
with st.sidebar:
    st.markdown("---")
    st.subheader(t["map_layers"])
    show_ndvi = st.checkbox(t["ndvi"], value=False)
    show_stations = st.checkbox(t["stations"], value=True)
    show_routing = st.checkbox(t["routing"], value=True)
    show_simulation = st.checkbox(t["simulation"], value=False)
    
    st.markdown("---")
    st.subheader(t["manual_sim"])
    sim_lat = st.number_input(t["lat"], value=36.75, min_value=18.0, max_value=37.5, step=0.01)
    sim_lon = st.number_input(t["lon"], value=3.05, min_value=-9.0, max_value=12.5, step=0.01)
    run_simulation = st.button(t["run_sim"])

# ==========================================
# Main Interface
# ==========================================
st.markdown("<h1 style='text-align:center;'>🏛️ المركز الوطني للإنذار المبكر لحرائق الغابات</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center; color:#00f2fe;'>National Wildfire Command Center - Algeria | Sovereign Grade System v2.0</p>", unsafe_allow_html=True)
st.markdown("---")

col1, col2 = st.columns([2, 1])

with col1:
    if "الكاميرات" in data_source:
        st.subheader("📹 البث الحي وتحليل الفيديو | Live Camera Stream")
        video_source = "test_video.mp4"
        run_detection = st.checkbox("تشغيل تحليل الذكاء الاصطناعي M-AI")
        FRAME_WINDOW = st.image([])
    else:
        st.subheader("🛰️ الرصد الحراري عبر الأقمار الصناعية | NASA FIRMS Multi-Satellite")
        st.success("✅ متصل بكوكبة الأقمار: VIIRS NOAA-20 + VIIRS SNPP + MODIS")
        
        if st.button("تحديث وجلب النقاط الحرارية فوق الجزائر | Fetch Active Fires", use_container_width=True):
            with st.spinner("جاري سحب بيانات من 3 أقمار صناعية..."):
                try:
                    api_key = os.getenv("NASA_FIRMS_API_KEY")
                    if api_key:
                        satellites = ["VIIRS_NOAA20_NRT", "VIIRS_SNPP_NRT", "MODIS_NRT"]
                        all_fires = []
                        seen = set()
                        
                        for sat in satellites:
                            url = f"https://firms.modaps.eosdis.nasa.gov/api/country/csv/{api_key}/{sat}/DZA/1"
                            response = requests.get(url, timeout=10)
                            if response.status_code == 200 and "latitude" in response.text:
                                df = pd.read_csv(io.StringIO(response.text))
                                for _, row in df.iterrows():
                                    key = (round(float(row['latitude']), 4), round(float(row['longitude']), 4))
                                    if key not in seen:
                                        seen.add(key)
                                        all_fires.append({
                                            "lat": float(row['latitude']),
                                            "lon": float(row['longitude']),
                                            "confidence": row.get('confidence', 'nominal'),
                                            "sat": sat
                                        })
                        
                        st.session_state['sat_data'] = all_fires
                        if all_fires:
                            st.toast(f"تم جلب {len(all_fires)} نقطة حرارية من كوكبة الأقمار!", icon="🛰️")
                except Exception as e:
                    st.error(f"خطأ في جلب البيانات: {e}")
        
        if 'sat_data' in st.session_state and st.session_state['sat_data']:
            sat_counts = {}
            for fire in st.session_state['sat_data']:
                sat = fire.get('sat', 'Unknown')
                sat_counts[sat] = sat_counts.get(sat, 0) + 1
            
            st.metric("النقاط الحرارية النشطة | Active Fire Points", len(st.session_state['sat_data']))
            for sat, count in sat_counts.items():
                st.caption(f"🛰️ {sat}: {count} نقطة")

with col2:
    st.subheader("📊 أحدث الإنذارات المسجلة | Alert Logs")
    
    def get_alerts(region: str) -> list:
        try:
            db_path = os.getenv('DATABASE_PATH', 'fire_system.db')
            with sqlite3.connect(db_path) as conn:
                c = conn.cursor()
                if region == "ALL":
                    c.execute("SELECT timestamp, region_id, hazard_type, confidence, source FROM alerts ORDER BY id DESC LIMIT 10")
                else:
                    c.execute("SELECT timestamp, region_id, hazard_type, confidence, source FROM alerts WHERE region_id = ? ORDER BY id DESC LIMIT 10", (region,))
                return c.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Alert query failed: {e}")
            return []
    
    user_region = st.session_state.get('user_region', 'ALL')
    alerts_data = get_alerts(user_region)
    
    if alerts_data:
        st.dataframe(alerts_data, column_config={
            "0": "الوقت | Time",
            "1": "الولاية | Region",
            "2": "الخطر | Hazard",
            "3": "الدقة | Confidence",
            "4": "المصدر | Source"
        }, use_container_width=True)
    else:
        st.info("لا توجد إنذارات مسجلة بعد | No alerts recorded yet")

# ==========================================
# GIS Map - Sovereign Grade
# ==========================================
st.markdown("---")
st.subheader("🗺️ خريطة الرصد الجغرافي الوطنية | Algerian Sovereign GIS")

# Create clean map with CartoDB positron (free, no API key needed)
m = folium.Map(
    location=[36.75, 3.05],
    zoom_start=6,
    tiles="CartoDB positron",
    control_scale=True
)

# Add Command Center marker
folium.Marker(
    location=[36.75, 3.05],
    popup="<b>المركز الوطني للقيادة والسيطرة - الجزائر العاصمة</b>",
    tooltip="National Command Center",
    icon=folium.Icon(color="red", icon="shield", prefix="fa")
).add_to(m)

# Inject dark CSS for map controls
dark_map_css = """
<style>
.leaflet-control-layers, .leaflet-control-zoom, .leaflet-popup-content-wrapper {
    background: rgba(13, 17, 23, 0.9) !important;
    color: #00f2fe !important;
    border: 1px solid #30363d !important;
    backdrop-filter: blur(10px) !important;
    border-radius: 8px !important;
    box-shadow: 0 4px 16px rgba(0,0,0,0.6) !important;
}
.leaflet-popup-tip {
    background: rgba(13, 17, 23, 0.9) !important;
}
.leaflet-control-zoom a {
    background: rgba(13, 17, 23, 0.9) !important;
    color: #00f2fe !important;
    border-color: #30363d !important;
}
.leaflet-control-zoom a:hover {
    background: rgba(0, 242, 254, 0.2) !important;
}
</style>
"""
m.get_root().html.add_child(folium.Element(dark_map_css))

# Add NDVI Layer (when enabled)
if show_ndvi:
    try:
        folium.TileLayer(
            tiles="https://tiles(openeo.planet.com/v1/ndvi_viirs/{z}/{x}/{y}.png)",
            attr="NDVI Vegetation Index",
            name="🌿 الغطاء النباتي (NDVI)",
            overlay=True,
            opacity=0.6
        ).add_to(m)
    except Exception:
        pass

# Add Civil Defense Units (when enabled)
if show_stations:
    units = get_cached_civil_defense_units()
    if units:
        for unit in units:
            try:
                lat, lon = float(unit[3]), float(unit[4])
                folium.Marker(
                    location=[lat, lon],
                    popup=f"🚒 وحدة الحماية المدنية: {unit[2]} ({unit[1]})",
                    tooltip=unit[2],
                    icon=folium.Icon(color="blue", icon="shield", prefix="fa")
                ).add_to(m)
            except Exception:
                continue

# Add Algeria boundary
folium.Rectangle(
    bounds=[
        [ALGERIA_BOUNDS['south'], ALGERIA_BOUNDS['west']],
        [ALGERIA_BOUNDS['north'], ALGERIA_BOUNDS['east']]
    ],
    color='blue',
    weight=2,
    fill=False,
    popup="حدود الجزائر | Algeria Boundaries"
).add_to(m)

# Add fire markers (when satellite data available)
if 'sat_data' in st.session_state and st.session_state['sat_data']:
    for fire in st.session_state['sat_data']:
        conf = str(fire.get('confidence', 'nominal')).lower()
        color = 'red' if conf == 'high' else ('orange' if conf == 'nominal' else 'yellow')
        
        popup_text = f"""
        <div style="min-width:200px">
            <h4 style="color:#d32f2f">🔥 نقطة حرارية نشطة</h4>
            <p><b>الموقع:</b> {fire['lat']:.4f}°N, {fire['lon']:.4f}°E</p>
            <p><b>الثقة:</b> {fire.get('confidence', 'N/A')}</p>
        </div>
        """
        
        folium.Marker(
            [fire['lat'], fire['lon']],
            popup=folium.Popup(popup_text, max_width=280),
            icon=folium.Icon(color=color, icon="fire", prefix="fa")
        ).add_to(m)

# Draw simulation if active
if st.session_state.get("simulation_active"):
    sim_lat_val = st.session_state.get("sim_lat", 36.75)
    sim_lon_val = st.session_state.get("sim_lon", 3.05)
    wind_speed = 35
    
    # 1h danger zone
    cone_1h = [[sim_lat_val, sim_lon_val], [sim_lat_val + 0.1, sim_lon_val + 0.1], [sim_lat_val + 0.15, sim_lon_val]]
    folium.Polygon(
        locations=cone_1h,
        color="red",
        fill=True,
        fill_color="red",
        fill_opacity=0.4,
        popup="🔴 منطقة الخطر العاجل (1 ساعة)"
    ).add_to(m)
    
    # 3h evacuation zone
    cone_3h = [[sim_lat_val, sim_lon_val], [sim_lat_val + 0.2, sim_lon_val + 0.2], [sim_lat_val + 0.25, sim_lon_val - 0.1]]
    folium.Polygon(
        locations=cone_3h,
        color="orange",
        fill=True,
        fill_color="orange",
        fill_opacity=0.25,
        popup="🟠 نطاق الإخلاء (3 ساعات)"
    ).add_to(m)
    
    folium.Marker(
        location=[sim_lat_val, sim_lon_val],
        popup=f"🔥 بؤرة الاشتعال - رياح {wind_speed} كم/سا",
        icon=folium.Icon(color="red", icon="fire", prefix="fa")
    ).add_to(m)

# Handle simulation button
if run_simulation:
    st.session_state["simulation_active"] = True
    st.session_state["sim_lat"] = sim_lat
    st.session_state["sim_lon"] = sim_lon
    st.success(f"✅ تم تشغيل المحاكاة على الموقع: {sim_lat:.4f}, {sim_lon:.4f}")

# Legend
legend_html = """
<div style="position:fixed; bottom:50px; left:50px; z-index:1000; background:rgba(13, 17, 23, 0.9); color:#00f2fe; padding:15px; border-radius:12px; border:1px solid #30363d; backdrop-filter:blur(10px); box-shadow:0 8px 32px rgba(0,0,0,0.6); min-width:180px;">
    <b style="color:#fff; font-size:14px;">دليل الخريطة</b><br>
    <hr style="border-color:#30363d; margin:8px 0;">
    <i style="color:#ff4444">🔥</i> <span style="color:#ff6b6b">خطر مرتفع</span><br>
    <i style="color:#ffaa00">🔥</i> <span style="color:#ffaa00">خطر متوسط</span><br>
    <i style="color:#00f2fe">🚒</i> <span style="color:#00f2fe">وحدة الحماية المدنية</span><br>
    <hr style="border-color:#30363d; margin:8px 0;">
    <b style="color:#fff; font-size:12px;">محاكاة الانتشار:</b><br>
    <span style="color:#ff4444">■</span> <span style="color:#ff6b6b">منطقة الخطر العاجل (1 ساعة)</span><br>
    <span style="color:#ff9800">■</span> <span style="color:#ffaa00">نطاق الإخلاء (3 ساعات)</span>
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))

# Display map
folium_static(m, width=950, height=480)

# ==========================================
# Fire Weather Index Panel
# ==========================================
st.markdown("---")
st.subheader("🌡️ مؤشر مخاطر الحرائق الجوي | Fire Weather Index (FWI)")

col_fwi1, col_fwi2, col_fwi3, col_fwi4 = st.columns(4)

fwi_data = get_fire_weather_index(36.25, 3.05)

with col_fwi1:
    st.metric("🌡️ الحرارة | Temperature", f"{fwi_data['temperature']}°C")

with col_fwi2:
    st.metric("💧 الرطوبة | Humidity", f"{fwi_data['humidity']}%")

with col_fwi3:
    st.metric("💨 سرعة الرياح | Wind", f"{fwi_data['wind_speed']} km/h")

with col_fwi4:
    st.metric("🔥 مؤشر الخطر | FWI", f"{fwi_data['fwi_score']}", 
              delta=fwi_data['danger_ar'], delta_color="inverse")

st.markdown(f"""
<div style="padding:10px; border-radius:5px; background-color:{fwi_data['color']}; color:white; text-align:center;">
    <b>مستوى الخطر الحالي: {fwi_data['danger_ar']} (Score: {fwi_data['fwi_score']})</b>
</div>
""", unsafe_allow_html=True)

# ==========================================
# 48-Hour Predictive Risk Panel
# ==========================================
st.markdown("---")
st.subheader("🔮 التنبؤ المبكر بالمخاطر لـ 48 ساعة | 48h Predictive Risk")

col_pred1, col_pred2 = st.columns([2, 1])

with col_pred1:
    regions_predict = [
        {"name": "الجزائر", "lat": 36.25, "lon": 3.05},
        {"name": "وهران", "lat": 35.69, "lon": -0.63},
        {"name": "تيزي وزو", "lat": 36.71, "lon": 4.05},
        {"name": "بجاية", "lat": 36.75, "lon": 5.06},
        {"name": "سطيف", "lat": 36.19, "lon": 5.41}
    ]
    
    predictions = []
    for region in regions_predict:
        pred = predict_fire_risk_48h(region['lat'], region['lon'])
        predictions.append({
            "region": region['name'],
            "risk_level": pred['risk_ar'],
            "risk_score": pred['risk_score'],
            "emoji": pred['emoji'],
            "avg_temp": pred['avg_temp'],
            "avg_humidity": pred['avg_humidity']
        })
    
    df_pred = pd.DataFrame(predictions)
    st.dataframe(df_pred, use_container_width=True, column_config={
        "region": "الولاية | Province",
        "risk_level": "مستوى الخطر | Risk Level",
        "risk_score": "النتيجة | Score",
        "emoji": "الحالة",
        "avg_temp": "متوسط الحرارة | Avg Temp",
        "avg_humidity": "متوسط الرطوبة | Avg Humidity"
    })

with col_pred2:
    max_risk_pred = max(predictions, key=lambda x: x['risk_score'])
    
    st.markdown(f"""
    <div style="padding:15px; border-radius:10px; background-color:#1a1a2e; color:white;">
        <h3 style="text-align:center; color:#ff5722">⚠️ تنبيه التنبؤ المبكر</h3>
        <hr style="border-color:#ff5722">
        <p><b>أعلى خطر متوقع:</b> {max_risk_pred['region']}</p>
        <p><b>النتيجة:</b> {max_risk_pred['risk_score']}</p>
        <p><b>المستوى:</b> {max_risk_pred['emoji']} {max_risk_pred['risk_level']}</p>
        <p><b>متوسط الحرارة:</b> {max_risk_pred['avg_temp']}°C</p>
        <p><b>متوسط الرطوبة:</b> {max_risk_pred['avg_humidity']}%</p>
    </div>
    """, unsafe_allow_html=True)
    
    if max_risk_pred['risk_score'] > 40:
        st.error("🚨 يُنصح بتفعيل حالة التأهب القصوى لجميع فرق الحماية المدنية!")
    elif max_risk_pred['risk_score'] > 25:
        st.warning("⚠️ يُنصح بمراقبة أطقم الإطفاء الاستعداد للتدخل السريع")
    else:
        st.success("✅ الوضع مستقر - لا توجد مخاطر فورية متوقعة")

# ==========================================
# Analytics Dashboard
# ==========================================
st.markdown("---")
st.subheader("📈 لوحة التحليلات | Analytics Dashboard")

def get_all_alerts_for_analytics() -> pd.DataFrame:
    try:
        db_path = os.getenv('DATABASE_PATH', 'fire_system.db')
        with sqlite3.connect(db_path) as conn:
            query = "SELECT timestamp, region_id, hazard_type, confidence, source FROM alerts"
            df = pd.read_sql_query(query, conn)
            return df
    except Exception as e:
        logger.error(f"Analytics query failed: {e}")
        return pd.DataFrame()

df_alerts = get_all_alerts_for_analytics()

if not df_alerts.empty:
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        fig_province = px.bar(
            df_alerts.groupby('region_id').size().reset_index(name='count'),
            x='region_id',
            y='count',
            title='توزيع الإنذارات حسب الولايات | Alerts by Province',
            labels={'region_id': 'الولاية | Province', 'count': 'عدد الإنذارات | Count'},
            color='count',
            color_continuous_scale='Reds'
        )
        st.plotly_chart(fig_province, use_container_width=True)
    
    with col_chart2:
        if 'hazard_type' in df_alerts.columns:
            fig_hazard = px.pie(
                df_alerts.groupby('hazard_type').size().reset_index(name='count'),
                names='hazard_type',
                values='count',
                title='توزيع الإنذارات حسب النوع | Alerts by Hazard Type',
                color_discrete_sequence=['#ff4444', '#ffaa00']
            )
            st.plotly_chart(fig_hazard, use_container_width=True)
    
    if 'timestamp' in df_alerts.columns:
        df_alerts['date'] = pd.to_datetime(df_alerts['timestamp'], errors='coerce').dt.date
        daily_alerts = df_alerts.groupby('date').size().reset_index(name='count')
        fig_timeline = px.line(
            daily_alerts,
            x='date',
            y='count',
            title='الإنذارات اليومية | Daily Alerts Timeline',
            labels={'date': 'التاريخ | Date', 'count': 'عدد الإنذارات | Count'}
        )
        st.plotly_chart(fig_timeline, use_container_width=True)
else:
    st.info("لا توجد بيانات كافية للتحليل | No alert data available for analytics")

# ==========================================
# PDF Report Download
# ==========================================
st.markdown("---")
st.subheader("📄 تصدير التقارير الرسمية | Export Official Reports")

col_pdf1, col_pdf2 = st.columns([2, 1])

with col_pdf1:
    st.write("إنشاء تقرير PDF رسمي يحتوي على جميع الإنذارات ومؤشرات الطقس الحالية.")

with col_pdf2:
    if st.button("📥 تحميل التقرير الرسمية | Download PDF Report", use_container_width=True):
        with st.spinner("جاري إنشاء التقرير..."):
            try:
                fwi_for_report = get_fire_weather_index(36.25, 3.05)
                report_region = st.session_state.get('user_region', 'ALL')
                alerts_for_report = get_alerts(report_region)
                
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Helvetica", "B", 16)
                pdf.cell(0, 15, "National Wildfire Detection Report", ln=True, align="C")
                pdf.set_font("Helvetica", "", 12)
                pdf.cell(0, 10, f"Region: {report_region} | Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True, align="C")
                pdf.ln(10)
                
                pdf.set_font("Helvetica", "B", 14)
                pdf.cell(0, 10, "Fire Weather Index", ln=True)
                pdf.set_font("Helvetica", "", 11)
                pdf.cell(0, 8, f"Temperature: {fwi_for_report.get('temperature', 'N/A')} C", ln=True)
                pdf.cell(0, 8, f"FWI Score: {fwi_for_report.get('fwi_score', 0)}", ln=True)
                pdf.cell(0, 8, f"Danger: {fwi_for_report.get('danger_ar', 'N/A')}", ln=True)
                pdf.ln(10)
                
                pdf_bytes = bytes(pdf.output())
                
                st.download_button(
                    label="📥 اضغط للتحميل | Click to Download",
                    data=pdf_bytes,
                    file_name=f"fire_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    mime="application/pdf"
                )
                st.success("تم إنشاء التقرير بنجاح!")
            except Exception as e:
                st.error(f"خطأ في إنشاء التقرير: {e}")

# ==========================================
# Footer
# ==========================================
st.markdown("---")
st.markdown("""
<div style='text-align:center; padding:20px; background:linear-gradient(90deg, #1e1e1e, #2a2a2a); border-radius:10px; margin-top:20px;'>
    <p style='color:#00f2fe; font-weight:bold; font-size:14px;'>🏛️ المركز الوطني للإنذار المبكر لحرائق الغابات</p>
    <p style='color:#888; font-size:12px;'>National Wildfire Command Center - Algeria | Sovereign Grade System v2.0</p>
    <p style='color:#666; font-size:10px;'>Powered by YOLOv8 + NASA FIRMS + Open-Meteo + Streamlit | All Rights Reserved © 2026</p>
</div>
""", unsafe_allow_html=True)
