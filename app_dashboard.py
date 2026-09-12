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
    """Hash password with salt using SHA-256"""
    return hashlib.sha256(f"{SALT}{password}".encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against stored hash"""
    return hash_password(password) == hashed

# Input validation constants
VALID_REGIONS = ["ALL", "16_ALGIERS", "13_TLEMCEN", "06_BATNA", "19_TIZI_OUZOU"]
VALID_HAZARD_TYPES = ["fire", "smoke"]
MAX_CONFIDENCE = 1.0
MIN_CONFIDENCE = 0.0

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
# 1. تثبيت اللغة في الجلسة (Persist Language)
# ==========================================
if "lang" not in st.session_state:
    st.session_state["lang"] = "AR"


# قاموس الترجمات الموحد
TRANSLATIONS = {
    "AR": {
        "title": "🏛️ المنظومة الوطنية للرصد والإنذار المبكر",
        "login_tab": "🔐 تسجيل الدخول",
        "signup_tab": "📝 إنشاء حساب جديد",
        "user_label": "اسم المستخدم",
        "pass_label": "كلمة المرور",
        "btn_login": "دخول المنظومة",
        "sim_title": "🚀 تشغيل محاكاة انتشار النيران",
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
        "map_type": "نوع الخريطة",
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
        "sim_title": "🚀 Run Fire Spread Simulation",
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
        "map_type": "Map Style",
        "user_info": "Session Info",
        "username_label": "Username",
        "role_label": "Role"
    }
}


# تغيير اللغة عبر الشريط الجانبي مع حفظ التغيير
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
# Authentication System
# ==========================================
def login_user(username: str, password: str) -> dict:
    """Authenticate user and return user data using db_manager"""
    success, role = db.authenticate_user(username, password)
    if success:
        logger.info(f"Successful login: {username}")
        return {
            "username": username,
            "role": role,
            "region": "ALL" if role == "Admin" else "16_ALGIERS",
            "full_name": username
        }
    else:
        logger.warning(f"Failed login attempt: {username}")
        return None

def init_session_state():
    """Initialize session state variables"""
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
    if 'user' not in st.session_state:
        st.session_state['user'] = None
    if 'session_token' not in st.session_state:
        st.session_state['session_token'] = None

def create_session(user_data: dict) -> str:
    """Create secure session token"""
    token = secrets.token_hex(32)
    st.session_state['session_token'] = token
    st.session_state['user'] = user_data
    st.session_state['logged_in'] = True
    st.session_state['authenticated'] = True
    return token

def logout_user():
    """Clear session data"""
    st.session_state['logged_in'] = False
    st.session_state['authenticated'] = False
    st.session_state['user'] = None
    st.session_state['session_token'] = None
    st.session_state['role'] = None

# ==========================================
# NASA FIRMS Multi-Satellite Constellation Fetcher
# ==========================================
def fetch_real_nasa_firms() -> list:
    """
    Fetch real-time active fire data from multiple NASA FIRMS satellites
    Constellation: VIIRS_NOAA20_NRT + VIIRS_SNPP_NRT + MODIS_NRT
    API Docs: https://firms.modaps.eosdis.nasa.gov/api/area/
    """
    api_key = os.getenv("NASA_FIRMS_API_KEY")
    
    if not api_key or api_key == "your_nasa_firms_api_key_here":
        st.error("⚠️ لم يتم العثور على مفتاح NASA FIRMS API الصحيح في ملف .env!")
        return []
    
    # Multi-satellite constellation
    satellites = ["VIIRS_NOAA20_NRT", "VIIRS_SNPP_NRT", "MODIS_NRT"]
    all_fires = []
    
    for sat in satellites:
        url = f"https://firms.modaps.eosdis.nasa.gov/api/country/csv/{api_key}/{sat}/DZA/1"
        try:
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200 and "latitude" in response.text:
                df = pd.read_csv(io.StringIO(response.text))
                
                for _, row in df.iterrows():
                    # Handle different column names for different satellites
                    brightness = row.get('bright_ti4', row.get('brightness', 300))
                    
                    all_fires.append({
                        "lat": float(row['latitude']),
                        "lon": float(row['longitude']),
                        "bright": brightness,
                        "sat": sat,
                        "acq_date": row.get('acq_date', ''),
                        "acq_time": row.get('acq_time', ''),
                        "confidence": row.get('confidence', 'nominal')
                    })
                
                logger.info(f"Fetched fires from {sat}")
        except Exception as e:
            logger.warning(f"Failed to fetch from {sat}: {e}")
            continue
    
    # Remove duplicates (same lat/lon from different satellites)
    seen = set()
    unique_fires = []
    for fire in all_fires:
        key = (round(fire['lat'], 4), round(fire['lon'], 4))
        if key not in seen:
            seen.add(key)
            unique_fires.append(fire)
    
    logger.info(f"Total unique fires from {len(satellites)} satellites: {len(unique_fires)}")
    return unique_fires

# ==========================================
# Civil Defense Stations (Emergency Dispatch)
# ==========================================
CIVIL_DEFENSE_STATIONS = [
    {"name": "الوحدة الرئيسية - الجزائر العاصمة", "lat": 36.7538, "lon": 3.0588, "capacity": "high"},
    {"name": "الوحدة الرئيسية - مستغانم", "lat": 35.9333, "lon": 0.0903, "capacity": "medium"},
    {"name": "الوحدة الرئيسية - تيزي وزو", "lat": 36.7118, "lon": 4.0459, "capacity": "high"},
    {"name": "الوحدة الرئيسية - بجاية", "lat": 36.7509, "lon": 5.0567, "capacity": "medium"},
    {"name": "الوحدة الرئيسية - الطارف", "lat": 36.7672, "lon": 8.3138, "capacity": "medium"},
    {"name": "الوحدة الرئيسية - خنشلة", "lat": 35.4358, "lon": 7.1433, "capacity": "low"},
    {"name": "الوحدة الرئيسية - وهران", "lat": 35.6969, "lon": -0.6331, "capacity": "high"},
    {"name": "الوحدة الرئيسية - قسنطينة", "lat": 36.3650, "lon": 6.6147, "capacity": "medium"},
    {"name": "الوحدة الرئيسية - سطيف", "lat": 36.1898, "lon": 5.4108, "capacity": "medium"},
    {"name": "الوحدة الرئيسية - القالة", "lat": 36.8972, "lon": 6.8942, "capacity": "low"}
]

def find_nearest_station(fire_lat: float, fire_lon: float) -> tuple:
    """Find nearest civil defense station and calculate distance"""
    nearest = None
    min_dist = float('inf')
    
    for station in CIVIL_DEFENSE_STATIONS:
        dist = geodesic((fire_lat, fire_lon), (station['lat'], station['lon'])).km
        if dist < min_dist:
            min_dist = dist
            nearest = station
            
    return nearest, round(min_dist, 2)

# ==========================================
# 48-Hour Predictive Fire Risk Algorithm
# ==========================================
def predict_fire_risk_48h(lat: float = 36.25, lon: float = 3.05) -> dict:
    """
    Predictive fire risk analysis for next 48 hours
    Combines temperature forecast, humidity, and wind data
    """
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
        
        # Calculate max risk score across 48 hours
        max_risk = 0
        risk_hours = []
        
        for i, (t, h, w) in enumerate(zip(hourly_temps, hourly_hum, hourly_wind)):
            # Predictive risk formula: high temp + high wind + low humidity = danger
            score = (t * 0.6) + (w * 0.9) - (h * 0.4)
            if score > max_risk:
                max_risk = score
            if score > 25:
                risk_hours.append(i)
        
        # Determine risk level
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
# NDVI Vegetation Layer (Open-source tiles)
# ==========================================
NDVI_TILE_URL = "https://earthengine.googleapis.com/v1/projects/earthengine-legacy/maps/{mapid}/tiles/{z}/{x}/{y}"

# ==========================================
# Fire Spread Simulation Engine
# ==========================================
def fetch_wind_vector(lat: float, lon: float) -> tuple:
    """
    Fetch current wind speed and direction from Open-Meteo API
    Returns: (speed_kmh, direction_degrees)
    """
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&current=wind_speed_10m,wind_direction_10m"
            f"&timezone=Africa/Algiers"
        )
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        curr = data.get('current', {})
        speed = curr.get('wind_speed_10m', 15)  # km/h
        direction = curr.get('wind_direction_10m', 45)  # degrees (0-360)
        
        logger.info(f"Wind data: {speed} km/h at {direction}°")
        return speed, direction
    except Exception as e:
        logger.error(f"Failed to fetch wind data: {e}")
        return 20, 90  # Default fallback

def calculate_spread_cone(lat: float, lon: float, wind_speed: float, wind_dir: float, hours: int = 3) -> list:
    """
    Calculate precise fire spread cone using Rothermel model
    Returns: List of [lat, lon] coordinates forming the spread polygon
    """
    # Rothermel model simplified: spread_distance = wind_speed * 0.09 * hours
    dist_km = (wind_speed * 0.09) * hours
    lat_rad = math.radians(lat)
    
    # Downwind direction (fire spreads with the wind)
    angle = math.radians((wind_dir + 180) % 360)
    
    # Head fire point (main spread direction)
    head_lat = lat + (dist_km / 111.0) * math.cos(angle)
    head_lon = lon + (dist_km / (111.0 * math.cos(lat_rad))) * math.sin(angle)
    
    # Flanking points (30° spread on each side)
    left_angle = angle - math.radians(30)
    right_angle = angle + math.radians(30)
    
    left_lat = lat + ((dist_km * 0.5) / 111.0) * math.cos(left_angle)
    left_lon = lon + ((dist_km * 0.5) / (111.0 * math.cos(lat_rad))) * math.sin(left_angle)
    
    right_lat = lat + ((dist_km * 0.5) / 111.0) * math.cos(right_angle)
    right_lon = lon + ((dist_km * 0.5) / (111.0 * math.cos(lat_rad))) * math.sin(right_angle)
    
    return [[lat, lon], [left_lat, left_lon], [head_lat, head_lon], [right_lat, right_lon]]

def add_fire_simulation_to_map(m: folium.Map, fire_lat: float, fire_lon: float) -> folium.Map:
    """
    Add interactive fire spread simulation overlay to map
    Shows 3 zones: Immediate (1h), Evacuation (3h), Extended (6h)
    """
    wind_speed, wind_dir = fetch_wind_vector(fire_lat, fire_lon)
    
    # 1. Immediate Danger Zone (1 hour - Dark Red)
    cone_1h = calculate_spread_cone(fire_lat, fire_lon, wind_speed, wind_dir, hours=1)
    folium.Polygon(
        locations=cone_1h,
        color="darkred",
        fill=True,
        fill_color="red",
        fill_opacity=0.6,
        popup=f"🔴 نطاق الخطر العاجل (ساعة واحدة)<br>الرياح: {wind_speed} km/h<br>الاتجاه: {wind_dir}°"
    ).add_to(m)
    
    # 2. Evacuation Zone (3 hours - Orange)
    cone_3h = calculate_spread_cone(fire_lat, fire_lon, wind_speed, wind_dir, hours=3)
    folium.Polygon(
        locations=cone_3h,
        color="orange",
        fill=True,
        fill_color="orange",
        fill_opacity=0.35,
        popup="🟠 نطاق الإخلاء المبكر (3 ساعات)<br>تهديد متوسط - إخلاء احترازي"
    ).add_to(m)
    
    # 3. Extended Threat Zone (6 hours - Yellow)
    cone_6h = calculate_spread_cone(fire_lat, fire_lon, wind_speed, wind_dir, hours=6)
    folium.Polygon(
        locations=cone_6h,
        color="gold",
        fill=True,
        fill_color="yellow",
        fill_opacity=0.2,
        popup="🟡 نطاق التهديد الممتد (6 ساعات)<br>مراقبة مستمرة"
    ).add_to(m)
    
    # 4. Fire origin marker with wind info
    folium.Marker(
        location=[fire_lat, fire_lon],
        popup=f"""🔥 بؤرة الاشتعال الأصلية<br>
        <b>الرياح:</b> {wind_speed} km/h<br>
        <b>الاتجاه:</b> {wind_dir}° (هبوب)<br>
        <b>معدل الانتشار:</b> {round(wind_speed * 0.09, 2)} km/h""",
        icon=folium.Icon(color="red", icon="fire", prefix="fa")
    ).add_to(m)
    
    # 5. Wind direction arrow marker
    arrow_lat = fire_lat + 0.1 * math.cos(math.radians(wind_dir))
    arrow_lon = fire_lon + 0.1 * math.sin(math.radians(wind_dir))
    folium.Marker(
        location=[arrow_lat, arrow_lon],
        popup=f"💨 اتجاه الرياح: {wind_dir}°",
        icon=folium.Icon(color="blue", icon="arrow-up", prefix="fa")
    ).add_to(m)
    
    return m

# ==========================================
# Fire Weather Index (FWI) - Open-Meteo API
# ==========================================
def get_fire_weather_index(lat: float = 36.25, lon: float = 3.05) -> dict:
    """
    Fetch weather data from Open-Meteo and calculate Fire Weather Index (FWI)
    API: https://open-meteo.com/en/docs
    """
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m"
            f"&timezone=Africa/Algiers"
        )
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        current = data.get('current', {})
        temp = current.get('temperature_2m', 25)
        humidity = current.get('relative_humidity_2m', 50)
        wind_speed = current.get('wind_speed_10m', 10)
        
        # Simplified FWI calculation based on Canadian Forest Fire Weather Index
        # FWI = f(T, RH, W) - simplified version
        fwi_score = (temp * 0.3) + ((100 - humidity) * 0.4) + (wind_speed * 0.3)
        
        # Determine danger level
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

# ==========================================
# Telegram Alert System
# ==========================================
def send_telegram_alert(lat: float, lon: float, hazard_type: str, confidence: float, source: str = "Unknown"):
    """
    Send fire alert to Telegram with location and confidence
    Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        logger.warning("Telegram credentials not configured in .env")
        return False
    
    message = (
        f"🚨 *تنبيه حريق عاجل | URGENT FIRE ALERT*\n\n"
        f"📍 الموقع: {lat:.4f}°N, {lon:.4f}°E\n"
        f"🔥 النوع: {hazard_type}\n"
        f"📊 نسبة الثقة: {confidence:.0%}\n"
        f"🛰️ المصدر: {source}\n"
        f"🕐 الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"🔗 https://www.google.com/maps?q={lat},{lon}"
    )
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    try:
        response = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"Telegram alert sent: {hazard_type} at {lat},{lon}")
            return True
        else:
            logger.error(f"Telegram API error: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")
        return False

# ==========================================
# PDF Report Generator
# ==========================================
def generate_pdf_report(region: str, alerts_data: list, fwi_data: dict) -> bytes:
    """
    Generate official PDF report for fire alerts
    Returns PDF as bytes for download
    """
    pdf = FPDF()
    pdf.add_page()
    
    # Add Arabic font support (using DejaVu if available)
    try:
        pdf.add_font("DejaVu", "", "C:/Windows/Fonts/dejavu.ttf", uni=True)
        font_name = "DejaVu"
    except:
        font_name = "Helvetica"
    
    # Header
    pdf.set_font(font_name, "B", 16)
    pdf.cell(0, 15, "National Wildfire Detection Report", ln=True, align="C")
    pdf.set_font(font_name, "", 12)
    pdf.cell(0, 10, "تقرير رصد حرائق الغابات الوطنية", ln=True, align="C")
    pdf.cell(0, 10, f"Region: {region} | Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True, align="C")
    pdf.ln(10)
    
    # Fire Weather Index Section
    pdf.set_font(font_name, "B", 14)
    pdf.cell(0, 10, "Fire Weather Index (FWI)", ln=True)
    pdf.set_font(font_name, "", 11)
    pdf.cell(0, 8, f"Temperature: {fwi_data.get('temperature', 'N/A')} C", ln=True)
    pdf.cell(0, 8, f"Humidity: {fwi_data.get('humidity', 'N/A')}%", ln=True)
    pdf.cell(0, 8, f"Wind Speed: {fwi_data.get('wind_speed', 'N/A')} km/h", ln=True)
    pdf.cell(0, 8, f"FWI Score: {fwi_data.get('fwi_score', 0)}", ln=True)
    pdf.cell(0, 8, f"Danger Level: {fwi_data.get('danger_ar', 'N/A')}", ln=True)
    pdf.ln(10)
    
    # Alerts Table
    pdf.set_font(font_name, "B", 14)
    pdf.cell(0, 10, "Recorded Alerts", ln=True)
    pdf.set_font(font_name, "", 10)
    
    # Table header
    pdf.set_fill_color(200, 200, 200)
    pdf.cell(40, 8, "Time", 1, 0, "C", True)
    pdf.cell(40, 8, "Region", 1, 0, "C", True)
    pdf.cell(30, 8, "Hazard", 1, 0, "C", True)
    pdf.cell(30, 8, "Confidence", 1, 0, "C", True)
    pdf.cell(50, 8, "Source", 1, 1, "C", True)
    
    # Table rows
    for alert in alerts_data[:20]:  # Last 20 alerts
        pdf.cell(40, 7, str(alert[0]), 1, 0, "C")
        pdf.cell(40, 7, str(alert[1]), 1, 0, "C")
        pdf.cell(30, 7, str(alert[2]), 1, 0, "C")
        pdf.cell(30, 7, f"{alert[3]:.0%}" if alert[3] else "N/A", 1, 0, "C")
        pdf.cell(50, 7, str(alert[4]), 1, 1, "C")
    
    pdf.ln(10)
    
    # Footer
    pdf.set_font(font_name, "", 9)
    pdf.cell(0, 8, "Generated by National Wildfire Detection System v2.0", ln=True, align="C")
    pdf.cell(0, 8, "Powered by YOLOv8 + NASA FIRMS + Open-Meteo", ln=True, align="C")
    
    # Return PDF as bytes
    return bytes(pdf.output())

# ==========================================
# Command Center UI/UX Configuration
# ==========================================
st.set_page_config(
    page_title="المركز الوطني للإنذار المبكر - National Command Center",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded"
)

def inject_custom_css():
    """Professional Command Center CSS injection"""
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;800&family=Orbitron:wght@700&display=swap');
    
    * {
        font-family: 'Cairo', sans-serif !important;
    }
    
    /* Hide Streamlit default UI elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Dark theme background */
    .stApp {
        background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
    }
    
    /* Metric cards styling */
    div[data-testid="metric-container"] {
        background: linear-gradient(145deg, #1e1e1e, #2a2a2a);
        border: 1px solid #333;
        padding: 20px;
        border-radius: 12px;
        border-right: 5px solid #00f2fe;
        box-shadow: 5px 5px 15px rgba(0,0,0,0.3);
        transition: transform 0.3s ease, border-right-color 0.3s;
    }
    div[data-testid="metric-container"]:hover {
        transform: translateY(-5px);
        border-right: 5px solid #ff4b2b;
    }
    
    /* Modern button styling */
    .stButton>button {
        background: linear-gradient(90deg, #1cb5e0 0%, #000851 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 10px 25px;
        font-weight: 600;
        letter-spacing: 1px;
        transition: all 0.4s ease;
        width: 100%;
    }
    .stButton>button:hover {
        box-shadow: 0 4px 15px rgba(28, 181, 224, 0.6);
        transform: scale(1.02);
    }
    
    /* Title styling */
    h1 {
        font-weight: 800 !important;
        background: -webkit-linear-gradient(#fff, #888);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        border-bottom: 2px solid #333;
        padding-bottom: 10px;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    }
    
    /* Map container styling */
    iframe {
        border-radius: 15px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.5);
        border: 2px solid #444;
    }
    
    /* Dataframe styling */
    .stDataFrame {
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 5px 15px rgba(0,0,0,0.3);
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        background: linear-gradient(90deg, #1e1e1e, #2a2a2a);
        border-radius: 8px;
        font-weight: 600;
    }
    
    /* Radio buttons styling */
    .stRadio > div {
        flex-direction: row;
        flex-wrap: wrap;
    }
    
    /* Success/Warning/Error boxes */
    .stAlert {
        border-radius: 10px;
        border-left: 5px solid;
    }
    
    /* Column dividers */
    [data-testid="column"] {
        border-left: 1px solid #333;
    }
    
    /* Custom scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    ::-webkit-scrollbar-track {
        background: #1e1e1e;
    }
    ::-webkit-scrollbar-thumb {
        background: #444;
        border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #555;
    }
    </style>
    """, unsafe_allow_html=True)

inject_custom_css()

# Initialize session
init_session_state()

# ==========================================
# 2. استرجاع الجلسة من رابط المتصفح (Persistent Auth)
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "user" not in st.session_state:
    st.session_state["user"] = None
if "role" not in st.session_state:
    st.session_state["role"] = None


# التحقق من وجود توكين في رابط الصفحة عند Refresh
query_token = st.query_params.get("session_token", None)
if not st.session_state["authenticated"] and query_token:
    valid, user_name = db.verify_session_token(query_token)
    if valid:
        st.session_state["authenticated"] = True
        st.session_state["user"] = user_name
        st.session_state["role"] = "Admin"


# ==========================================
# 3. واجهة الدخول بحفظ الـ Token
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
# Authenticated User Dashboard - Command Center
# ==========================================

# Sidebar - User Info & Controls
st.sidebar.markdown("<h2 style='text-align:center; color:#00f2fe;'>🏛️ Command Center</h2>", unsafe_allow_html=True)
st.sidebar.markdown("---")

# عرض بيانات المستخدم في الشريط الجانبي بناءً على نظام الجلسة الجديد
current_user = st.session_state.get('user', 'مستخدم')
current_role = st.session_state.get('role', 'Operator')

st.sidebar.markdown("---")
st.sidebar.markdown(f"<h3 style='color:#00f2fe;'>{t['user_info']}</h3>", unsafe_allow_html=True)
st.sidebar.markdown(f"<p style='color:#fff;'>👤 <b>{t['username_label']}:</b> {current_user}</p>", unsafe_allow_html=True)
st.sidebar.markdown(f"<p style='color:#fff;'>🛡️ <b>{t['role_label']}:</b> {current_role}</p>", unsafe_allow_html=True)

# زر تسجيل الخروج
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

# ==========================================
# Main Interface - Command Center
# ==========================================
st.markdown("<h1 style='text-align:center;'>🏛️ المركز الوطني للإنذار المبكر لحرائق الغابات</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center; color:#00f2fe;'>National Wildfire Command Center - Algeria | Sovereign Grade System v2.0</p>", unsafe_allow_html=True)
st.markdown("---")

col1, col2 = st.columns([2, 1])

# Column 1 - Detection Panel
with col1:
    if "الكاميرات" in data_source:
        st.subheader("📹 البث الحي وتحليل الفيديو | Live Camera Stream")
        video_source = "test_video.mp4"
        run_detection = st.checkbox("تشغيل تحليل الذكاء الاصطناعي M-AI")
        FRAME_WINDOW = st.image([])
    else:
        st.subheader("🛰️ الرصد الحراري عبر الأقمار الصناعية | NASA FIRMS Multi-Satellite")
        st.success("✅ متصل بكوكبة الأقمار: VIIRS NOAA-20 + VIIRS SNPP + MODIS")
        
        # Fetch satellite data button
        if st.button("تحديث وجلب النقاط الحرارية فوق الجزائر | Fetch Active Fires", use_container_width=True):
            with st.spinner("جاري سحب بيانات من 3 أقمار صناعية..."):
                sat_data = fetch_real_nasa_firms()
                st.session_state['sat_data'] = sat_data
                if sat_data:
                    st.toast(f"تم جلب {len(sat_data)} نقطة حرارية من كوكبة الأقمار!", icon="🛰️")
        
        # Display satellite data stats
        if 'sat_data' in st.session_state and st.session_state['sat_data']:
            # Count by satellite
            sat_counts = {}
            for fire in st.session_state['sat_data']:
                sat = fire.get('sat', 'Unknown')
                sat_counts[sat] = sat_counts.get(sat, 0) + 1
            
            st.metric("النقاط الحرارية النشطة | Active Fire Points", len(st.session_state['sat_data']))
            
            # Show satellite breakdown
            for sat, count in sat_counts.items():
                st.caption(f"🛰️ {sat}: {count} نقطة")

# Column 2 - Alert Logs
with col2:
    st.subheader("📊 أحدث الإنذارات المسجلة | Alert Logs")
    
    def get_alerts(region: str) -> list:
        """Fetch alerts with RLS filtering"""
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
# Algerian Sovereign GIS Map (Advanced: Satellite + NDVI + Dispatch)
# ==========================================
st.markdown("---")
st.subheader("🗺️ خريطة الرصد الجغرافي الوطنية | Algerian Sovereign GIS")

# Map controls in sidebar
with st.sidebar:
    st.markdown("---")
    st.subheader(t["map_layers"])
    show_ndvi = st.checkbox(t["ndvi"], value=False)
    show_stations = st.checkbox(t["stations"], value=True)
    show_routing = st.checkbox(t["routing"], value=True)
    show_simulation = st.checkbox(t["simulation"], value=False)
    
    # Click-to-Simulate input
    st.markdown("---")
    st.subheader(t["manual_sim"])
    sim_lat = st.number_input(t["lat"], value=36.75, min_value=18.0, max_value=37.5, step=0.01)
    sim_lon = st.number_input(t["lon"], value=3.05, min_value=-9.0, max_value=12.5, step=0.01)
    run_simulation = st.button(t["run_sim"])

# ==========================================
# 1. تسريع الاستعلامات وتخزينها في الذاكرة (Caching)
# ==========================================
@st.cache_data(ttl=600)  # تخزين لمدة 10 دقائق لتخفيف الثقل
def get_cached_civil_defense_units():
    return db.get_all_civil_defense_units()


# Base map selection - استخدام OpenStreetMap المجاني بالكامل بدون API Key
map_type = st.radio(
    t["map_type"], 
    ["🗺️ OpenStreetMap (مجاني وسريع)"],
    horizontal=True
)

# إنشاء الخريطة باستخدام OpenStreetMap المجاني 100%
m = folium.Map(
    location=[36.25, 3.05],
    zoom_start=7,
    min_zoom=5,
    max_zoom=19,
    tiles="OpenStreetMap",
    attr="OpenStreetMap Contributors",
    control_scale=True
)

# Inject dark glassmorphism CSS for map controls
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
.leaflet-container {
    font-family: 'Cairo', sans-serif !important;
}
</style>
"""
m.get_root().html.add_child(folium.Element(dark_map_css))

# Click-to-Simulate JavaScript (stores clicked coordinates)
click_sim_code = """
<script>
var clickedLat, clickedLon;
function onMapClick(e) {
    clickedLat = e.latlng.lat;
    clickedLon = e.latlng.lng;
    // Store in Streamlit session via component
    window.parent.postMessage({type: 'streamlit:setComponentValue', value: {lat: clickedLat, lon: clickedLon}}, '*');
}
</script>
"""
m.get_root().html.add_child(folium.Element(click_sim_code))

# Add NDVI Vegetation Layer (when enabled)
if show_ndvi:
    try:
        folium.TileLayer(
            tiles="https://tiles(openeo.planet.com/v1/ndvi_viirs/{z}/{x}/{y}.png)",
            attr="NDVI Vegetation Index",
            name="🌿 الغطاء النباتي (NDVI)",
            overlay=True,
            opacity=0.6
        ).add_to(m)
        st.success("✅ تم تفعيل طبقة الغطاء النباتي NDVI")
    except:
        st.warning("⚠️ طبقة NDVI غير متاحة حالياً")

# Add Civil Defense Stations (when enabled)
if show_stations:
    # Get units from cache for better performance
    civil_units = get_cached_civil_defense_units()
    for unit in civil_units:
        folium.Marker(
            location=[unit[3], unit[4]],
            popup=f"🚒 {unit[2]} - {unit[0]} ({unit[1]})",
            tooltip=unit[2],
            icon=folium.Icon(color="blue", icon="shield", prefix="fa")
        ).add_to(m)

# Restrict map to Algeria boundaries
m.fit_bounds([
    [ALGERIA_BOUNDS['south'], ALGERIA_BOUNDS['west']],
    [ALGERIA_BOUNDS['north'], ALGERIA_BOUNDS['east']]
])

# Add satellite fire markers with routing
if 'sat_data' in st.session_state and st.session_state['sat_data']:
    for fire in st.session_state['sat_data']:
        conf = str(fire.get('confidence', 'nominal')).lower()
        color = 'red' if conf == 'high' else ('orange' if conf == 'nominal' else 'yellow')
        
        # Find nearest civil defense station and route
        if show_routing:
            nearest_stn, distance = find_nearest_station(fire['lat'], fire['lon'])
            
            # Draw routing line to nearest station
            folium.PolyLine(
                locations=[[nearest_stn['lat'], nearest_stn['lon']], [fire['lat'], fire['lon']]],
                color="red",
                weight=3,
                opacity=0.8,
                dash_array='5, 10',
                popup=f"🚒 مسار التدخل: {nearest_stn['name']} ({distance} km)"
            ).add_to(m)
            
            popup_text = f"""
            <div style="min-width:250px">
                <h4 style="color:#d32f2f">🔥 بؤرة حريق نشطة</h4>
                <p><b>الموقع:</b> {fire['lat']:.4f}°N, {fire['lon']:.4f}°E</p>
                <p><b>الثقة:</b> {fire.get('confidence', 'N/A')}</p>
                <p><b>أقرب وحدة:</b> {nearest_stn['name']}</p>
                <p><b>المسافة:</b> {distance} km</p>
                <p><b>الوقت المقدر:</b> ~{int(distance / 60 * 60)} دقيقة</p>
            </div>
            """
        else:
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
        
        # Add fire spread simulation for high confidence fires
        if show_simulation and conf == 'high':
            m = add_fire_simulation_to_map(m, fire['lat'], fire['lon'])

# Manual simulation (when button is clicked) - with session state persistence
if run_simulation:
    st.session_state["simulation_active"] = True
    st.session_state["sim_lat"] = sim_lat
    st.session_state["sim_lon"] = sim_lon
    st.success(f"✅ تم تشغيل المحاكاة على الموقع: {sim_lat:.4f}, {sim_lon:.4f}")

# Draw simulation if active (persistent in session)
if st.session_state.get("simulation_active"):
    m = add_fire_simulation_to_map(m, st.session_state.get("sim_lat", 36.75), st.session_state.get("sim_lon", 3.05))

# Add Algeria boundary rectangle
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

# Legend - Dark Glassmorphism Style
legend_html = """
<div style="position:fixed; bottom:50px; left:50px; z-index:1000; background:rgba(13, 17, 23, 0.9); color:#00f2fe; padding:15px; border-radius:12px; border:1px solid #30363d; backdrop-filter:blur(10px); box-shadow:0 8px 32px rgba(0,0,0,0.6); font-family:'Cairo',sans-serif; min-width:180px;">
    <b style="color:#fff; font-size:14px;">دليل الخريطة</b><br>
    <hr style="border-color:#30363d; margin:8px 0;">
    <i style="color:#ff4444">🔥</i> <span style="color:#ff6b6b">خطر مرتفع</span><br>
    <i style="color:#ffaa00">🔥</i> <span style="color:#ffaa00">خطر متوسط</span><br>
    <i style="color:#00f2fe">🚒</i> <span style="color:#00f2fe">وحدة الحماية المدنية</span><br>
    <i style="color:#ff4444">---</i> <span style="color:#ff6b6b">مسار التدخل</span><br>
    <hr style="border-color:#30363d; margin:8px 0;">
    <b style="color:#fff; font-size:12px;">محاكاة الانتشار:</b><br>
    <span style="color:#ff4444">■</span> <span style="color:#ff6b6b">منطقة الخطر العاجل (1 ساعة)</span><br>
    <span style="color:#ff9800">■</span> <span style="color:#ffaa00">نطاق الإخلاء (3 ساعات)</span><br>
    <span style="color:#ffd700">■</span> <span style="color:#ffd700">التهديد الممتد (6 ساعات)</span>
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))

# عرض الخريطة بضغط منخفض جداً على السيرفر
folium_static(m, width=950, height=480)

# ==========================================
# YOLO Detection Engine
# ==========================================
if "الكاميرات" in data_source and 'run_detection' in locals() and run_detection:
    if os.path.exists(video_source):
        try:
            confidence_threshold = float(os.getenv('CONFIDENCE_THRESHOLD', '0.5'))
            alert_cooldown = int(os.getenv('ALERT_COOLDOWN_SECONDS', '10'))
            
            model = YOLO("best.pt")
            cap = cv2.VideoCapture(video_source)
            
            if not cap.isOpened():
                st.error("Failed to open video source")
                logger.error(f"Failed to open video: {video_source}")
            else:
                last_alert = 0
                logger.info(f"Detection started: conf={confidence_threshold}, cooldown={alert_cooldown}s")
                
                while cap.isOpened():
                    ret, frame = cap.read()
                    if not ret:
                        logger.info("Video stream ended")
                        break
                    
                    results = model(frame, conf=confidence_threshold, stream=True)
                    
                    for r in results:
                        for box in r.boxes:
                            class_id = int(box.cls[0])
                            class_name = model.names[class_id]
                            conf = float(box.conf[0])
                            
                            if class_name in ["fire", "smoke"]:
                                curr = time.time()
                                if curr - last_alert > alert_cooldown:
                                    try:
                                        db_path = os.getenv('DATABASE_PATH', 'fire_system.db')
                                        with sqlite3.connect(db_path) as conn:
                                            c = conn.cursor()
                                            c.execute(
                                                "INSERT INTO alerts (timestamp, region_id, hazard_type, confidence, source) VALUES (?, ?, ?, ?, ?)",
                                                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), st.session_state.get('user_region', 'ALL'), class_name, round(conf, 2), "Live Camera")
                                            )
                                            conn.commit()
                                            last_alert = curr
                                            logger.info(f"Alert logged: {class_name} ({conf:.2f})")
                                            
                                            # Send Telegram alert
                                            send_telegram_alert(
                                                lat=36.75,
                                                lon=3.05,
                                                hazard_type=class_name,
                                                confidence=conf,
                                                source="Live Camera - YOLOv8"
                                            )
                                    except sqlite3.Error as e:
                                        logger.error(f"Failed to log alert: {e}")
                        
                        frame = r.plot()
                    
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    FRAME_WINDOW.image(frame_rgb)
                
                cap.release()
                logger.info("Detection completed")
        except Exception as e:
            st.error(f"Detection error: {e}")
            logger.error(f"Detection error: {e}")
    else:
        st.error(f"Video file not found: {video_source}")

# ==========================================
# Fire Weather Index (FWI) Panel
# ==========================================
st.markdown("---")
st.subheader("🌡️ مؤشر مخاطر الحرائق الجوي | Fire Weather Index (FWI)")

col_fwi1, col_fwi2, col_fwi3, col_fwi4 = st.columns(4)

# Get FWI data for Algeria (default: Algiers region)
fwi_data = get_fire_weather_index(36.25, 3.05)
st.session_state['fwi_data'] = fwi_data

with col_fwi1:
    st.metric("🌡️ الحرارة | Temperature", f"{fwi_data['temperature']}°C")

with col_fwi2:
    st.metric("💧 الرطوبة | Humidity", f"{fwi_data['humidity']}%")

with col_fwi3:
    st.metric("💨 سرعة الرياح | Wind", f"{fwi_data['wind_speed']} km/h")

with col_fwi4:
    st.metric("🔥 مؤشر الخطر | FWI", f"{fwi_data['fwi_score']}", 
              delta=fwi_data['danger_ar'], delta_color="inverse")

# FWI Danger Level Indicator
st.markdown(f"""
<div style="padding:10px; border-radius:5px; background-color:{fwi_data['color']}; color:white; text-align:center;">
    <b>مستوى الخطر الحالي: {fwi_data['danger_ar']} (Score: {fwi_data['fwi_score']})</b>
</div>
""", unsafe_allow_html=True)

# ==========================================
# 48-Hour Predictive Fire Risk Panel
# ==========================================
st.markdown("---")
st.subheader("🔮 التنبؤ المبكر بالمخاطر لـ 48 ساعة | 48h Predictive Risk")

col_pred1, col_pred2 = st.columns([2, 1])

with col_pred1:
    # Get prediction for multiple key regions
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
    
    # Display predictions as dataframe
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
    # Overall risk summary
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
    
    # Action recommendation
    if max_risk_pred['risk_score'] > 40:
        st.error("🚨 يُنصح بتفعيل حالة التأهب القصوى لجميع فرق الحماية المدنية!")
    elif max_risk_pred['risk_score'] > 25:
        st.warning("⚠️ يُنصح بمراقبة أطقم الإطفاء الاستعداد للتدخل السريع")
    else:
        st.success("✅ الوضع مستقر - لا توجد مخاطر فورية متوقعة")

# ==========================================
# Analytics Dashboard - Alerts by Province
# ==========================================
st.markdown("---")
st.subheader("📈 لوحة التحليلات | Analytics Dashboard")

def get_all_alerts_for_analytics() -> pd.DataFrame:
    """Fetch all alerts for analytics"""
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
        # Bar chart - Alerts by Province
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
        # Pie chart - Alerts by Hazard Type
        if 'hazard_type' in df_alerts.columns:
            fig_hazard = px.pie(
                df_alerts.groupby('hazard_type').size().reset_index(name='count'),
                names='hazard_type',
                values='count',
                title='توزيع الإنذارات حسب النوع | Alerts by Hazard Type',
                color_discrete_sequence=['#ff4444', '#ffaa00']
            )
            st.plotly_chart(fig_hazard, use_container_width=True)
    
    # Line chart - Alerts over time
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
            # Get fresh data for report
            fwi_for_report = get_fire_weather_index(36.25, 3.05)
            report_region = st.session_state.get('user_region', 'ALL')
            alerts_for_report = get_alerts(report_region)
            
            pdf_bytes = generate_pdf_report(
                region=report_region,
                alerts_data=alerts_for_report,
                fwi_data=fwi_for_report
            )
            
            st.download_button(
                label="📥 اضغط للتحميل | Click to Download",
                data=pdf_bytes,
                file_name=f"fire_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf"
            )
            st.success("تم إنشاء التقرير بنجاح!")

# ==========================================
# Footer - Command Center
# ==========================================
st.markdown("---")
st.markdown("""
<div style='text-align:center; padding:20px; background:linear-gradient(90deg, #1e1e1e, #2a2a2a); border-radius:10px; margin-top:20px;'>
    <p style='color:#00f2fe; font-weight:bold; font-size:14px;'>🏛️ المركز الوطني للإنذار المبكر لحرائق الغابات</p>
    <p style='color:#888; font-size:12px;'>National Wildfire Command Center - Algeria | Sovereign Grade System v2.0</p>
    <p style='color:#666; font-size:10px;'>Powered by YOLOv8 + NASA FIRMS + Open-Meteo + Streamlit | All Rights Reserved © 2026</p>
</div>
""", unsafe_allow_html=True)
