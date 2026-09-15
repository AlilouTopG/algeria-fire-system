import streamlit as st
import os
import logging
import requests
import pandas as pd
import io
from datetime import datetime
from dotenv import load_dotenv
import folium
from streamlit_folium import folium_static
import plotly.express as px
from fpdf import FPDF
import db_manager as db

# تحميل متغيرات البيئة
load_dotenv()

# إعداد السجلات
if "logger_configured" not in st.session_state:
    handler = logging.FileHandler('dashboard.log', encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger = logging.getLogger("dashboard")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        logger.addHandler(handler)
        logger.addHandler(logging.StreamHandler())
    st.session_state["logger_configured"] = True

logger = logging.getLogger("dashboard")

# تهيئة قاعدة البيانات ووحدات الحماية المدنية
if "db_initialized" not in st.session_state:
    db.init_db()
    db.init_civil_defense_table()
    st.session_state["db_initialized"] = True

# إعدادات الواجهة
st.set_page_config(
    page_title="المركز الوطني للرصد والإنذار المبكر",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

ALGERIA_BOUNDS = {"south": 18.96, "west": -8.67, "north": 37.09, "east": 11.99}

if "lang" not in st.session_state:
    st.session_state["lang"] = "AR"

TRANSLATIONS = {
    "AR": {
        "title": "المنظومة الوطنية للرصد والإنذار المبكر لحرائق الغابات",
        "subtitle": "Algerian Sovereign Wildfire Early Warning & Command Platform",
        "login_tab": "تسجيل الدخول",
        "signup_tab": "إنشاء حساب جديد",
        "user_label": "اسم المستخدم",
        "pass_label": "كلمة المرور",
        "btn_login": "دخول المنظومة",
        "logout": "تسجيل الخروج",
        "map_layers": "طبقات الخريطة الجغرافية",
        "ndvi": "الصور الفضائية والغطاء النباتي (Satellite/NDVI)",
        "stations": "وحدات التدخل للحماية المدنية",
        "simulation": "محاكاة انتشار النيران",
        "manual_sim": "نقطة المحاكاة التفاعلية",
        "lat": "خط العرض (Latitude)",
        "lon": "خط الطول (Longitude)",
        "run_sim": "بدء محاكاة الانتشار",
        "user_info": "بيانات الجلسة النشطة",
        "username_label": "المستخدم",
        "role_label": "الصلاحية",
        "region_label": "الولاية / القطاع"
    },
    "EN": {
        "title": "National Wildfire Early Warning & Command Center",
        "subtitle": "Algerian Sovereign Wildfire Early Warning & Command Platform",
        "login_tab": "Login",
        "signup_tab": "Sign Up",
        "user_label": "Username",
        "pass_label": "Password",
        "btn_login": "Access System",
        "logout": "Logout",
        "map_layers": "GIS Map Layers",
        "ndvi": "Satellite & Vegetation Layer (NDVI)",
        "stations": "Civil Defense Intervention Units",
        "simulation": "Fire Spread Simulation",
        "manual_sim": "Interactive Simulation Point",
        "lat": "Latitude",
        "lon": "Longitude",
        "run_sim": "Run Fire Spread Model",
        "user_info": "Session Details",
        "username_label": "Username",
        "role_label": "Role",
        "region_label": "Sector / Wilaya"
    }
}

t = TRANSLATIONS[st.session_state["lang"]]

# إدارة حالة الجلسة
for key, val in {
    "authenticated": False, "user": None, "role": None,
    "simulation_active": False, "sim_lat": 36.0686, "sim_lon": 4.7631,
    "user_region": "ALL", "sat_data": []
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

query_token = st.query_params.get("session_token", None)
if not st.session_state["authenticated"] and query_token:
    valid, user_name = db.verify_session_token(query_token)
    if valid:
        st.session_state["authenticated"] = True
        st.session_state["user"] = user_name
        st.session_state["role"] = "Admin"
        st.session_state["user_region"] = "ALL"

# ==========================================
# شاشة الدخول والتسجيل (Login Screen)
# ==========================================
if not st.session_state.get("authenticated", False):
    st.markdown(f"<h1 style='text-align: center; color: #00f2fe; margin-top: 50px;'>{t['title']}</h1>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align: center; color: #888;'>{t['subtitle']}</p>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    col_mid1, col_mid2, col_mid3 = st.columns()

    with col_mid2:
        tab_login, tab_signup = st.tabs([t["login_tab"], t["signup_tab"]])

        with tab_login:
            with st.form(key="login_form"):
                user_in = st.text_input(t["user_label"], value="admin")
                pass_in = st.text_input(t["pass_label"], type="password", value="admin123")
                if st.form_submit_button(t["btn_login"], use_container_width=True):
                    if user_in and pass_in:
                        success, role = db.authenticate_user(user_in, pass_in)
                        if success:
                            st.session_state["authenticated"] = True
                            st.session_state["user"] = user_in
                            st.session_state["role"] = role
                            st.session_state["user_region"] = "ALL" if role == "Admin" else "Bordj Bou Arreridj"
                            token = db.generate_session_token(user_in)
                            if token:
                                st.query_params["session_token"] = token
                            st.rerun()
                        else:
                            st.error("اسم المستخدم أو كلمة المرور غير صحيحة / Invalid credentials")

        with tab_signup:
            with st.form(key="signup_form"):
                new_user = st.text_input("اسم المستخدم الجديد")
                new_pass = st.text_input("كلمة المرور", type="password")
                role_sel = st.selectbox("نوع الحساب", ["Operator", "Analyst", "Admin"])
                region_sel = st.text_input("الولاية / المنطقة التابعة", value="Bordj Bou Arreridj")
                if st.form_submit_button("إنشاء الحساب", use_container_width=True):
                    if new_user.strip() and new_pass.strip():
                        ok, msg = db.register_user(new_user.strip(), new_pass.strip(), role_sel, region_sel)
                        if ok:
                            st.success(msg)
                        else:
                            st.error(msg)
                    else:
                        st.warning("يرجى ملء جميع الحقول المطلوبة.")

    st.stop()


# ==========================================
# الدوال المساعدة للطقس والاستشعار
# ==========================================
@st.cache_data(ttl=600)
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
            danger_ar, color = "خطر شديد جداً (Extreme)", "#d32f2f"
        elif fwi_score >= 50:
            danger_ar, color = "خطر مرتفع (High)", "#ff5722"
        elif fwi_score >= 30:
            danger_ar, color = "خطر متوسط (Moderate)", "#ff9800"
        elif fwi_score >= 15:
            danger_ar, color = "خطر منخفض (Low)", "#4caf50"
        else:
            danger_ar, color = "خطر ضئيل (Minimal)", "#8bc34a"

        return {
            "temperature": temp, "humidity": humidity, "wind_speed": wind_speed,
            "fwi_score": round(fwi_score, 1), "danger_ar": danger_ar, "color": color
        }
    except Exception as e:
        logger.error(f"Open-Meteo API error: {e}")
        return {
            "temperature": "N/A", "humidity": "N/A", "wind_speed": "N/A",
            "fwi_score": 0, "danger_ar": "غير متاح حالياً", "color": "#9e9e9e"
        }


# ==========================================
# القائمة الجانبية (Sidebar)
# ==========================================
st.sidebar.markdown("<h2 style='text-align:center; color:#00f2fe;'>مركز القيادة والتحكم</h2>", unsafe_allow_html=True)
st.sidebar.markdown("---")

current_user = st.session_state.get('user', 'Admin')
current_role = st.session_state.get('role', 'Admin')
current_region = st.session_state.get('user_region', 'ALL')

st.sidebar.markdown(f"**المستخدم:** `{current_user}`")
st.sidebar.markdown(f"**الصلاحية:** `{current_role}`")
st.sidebar.markdown(f"**القطاع:** `{current_region}`")

if st.sidebar.button(t["logout"], use_container_width=True):
    for k in ['authenticated', 'user', 'role', 'user_region']:
        st.session_state[k] = None if k != 'authenticated' else False
    st.query_params.clear()
    st.rerun()

st.sidebar.markdown("---")
data_source = st.sidebar.radio(
    "مصدر الرصد المباشر:",
    ["الكاميرات والذكاء الاصطناعي (AI Live Stream)", "الأقمار الصناعية (NASA FIRMS Satellite)"]
)

st.sidebar.markdown("---")
st.sidebar.subheader(t["map_layers"])
show_ndvi = st.sidebar.checkbox(t["ndvi"], value=True)
show_stations = st.sidebar.checkbox(t["stations"], value=True)

st.sidebar.markdown("---")
st.sidebar.subheader(t["manual_sim"])
sim_lat = st.sidebar.number_input("خط العرض", value=36.0686, min_value=18.0, max_value=37.5, step=0.01)
sim_lon = st.sidebar.number_input("خط الطول", value=4.7631, min_value=-9.0, max_value=12.5, step=0.01)
if st.sidebar.button(t["run_sim"], use_container_width=True):
    st.session_state["simulation_active"] = True
    st.session_state["sim_lat"] = sim_lat
    st.session_state["sim_lon"] = sim_lon
    st.toast("تم تفعيل نموذج محاكاة انتشار الحريق!", icon="🔥")


# ==========================================
# الواجهة الرئيسية (Main View)
# ==========================================
st.markdown(f"<h1 style='text-align:center;'>{t['title']}</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center; color:#00f2fe;'>المنظومة الجزائرية المتكاملة للإنذار المبكر والرصد التنبئي v2.0</p>", unsafe_allow_html=True)
st.markdown("---")

col_main1, col_main2 = st.columns()

with col_main1:
    if "الكاميرات" in data_source:
        st.subheader("📹 بث ومراقبة الكاميرات الذكية (Live Camera Analysis)")
        st.info("الذكاء الاصطناعي يرصد البث بشكل مستمر عبر `run_detector.py`. عند رصد دخان أو نار، يتم التوثيق التلقائي في الجدول أدناه وإشعار فرق الطوارئ.")
        if os.path.exists("fire_alert.jpg"):
            st.image("fire_alert.jpg", caption="آخر صورة ملتقطة تم فحصها وتأكيدها بواسطة YOLOv8", use_container_width=True)
    else:
        st.subheader("🛰️ الرصد الحراري الفضائي (NASA FIRMS)")
        st.caption("متصل بكوكبة الأقمار: VIIRS NOAA-20 + VIIRS SNPP + MODIS")

        if st.button("تحديث وجلب النقاط الحرارية فوق الجزائر الآن", use_container_width=True):
            with st.spinner("جاري الاتصال بالأقمار الصناعية وسحب البيانات..."):
                try:
                    api_key = os.getenv("NASA_FIRMS_API_KEY", "b7a1a0de499d32758672ad0cb7bae6da")
                    all_fires = []
                    seen = set()
                    for sat in ["VIIRS_NOAA20_NRT", "VIIRS_SNPP_NRT", "MODIS_NRT"]:
                        url = f"https://firms.modaps.eosdis.nasa.gov/api/country/csv/{api_key}/{sat}/DZA/1"
                        response = requests.get(url, timeout=12)
                        if response.status_code == 200 and "latitude" in response.text:
                            df_sat = pd.read_csv(io.StringIO(response.text))
                            for _, row in df_sat.iterrows():
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
                        st.success(f"تم رصد {len(all_fires)} نقطة حرارية نشطة فوق التراب الوطني!")
                    else:
                        st.info("لا توجد بؤر حرارية نشطة تم رصدها في آخر مسح فضائي.")
                except Exception as e:
                    st.error(f"خطأ أثناء الاتصال بالأقمار الصناعية: {e}")

        if st.session_state.get('sat_data'):
            st.metric("مجموع البؤر الحرارية المرصودة", len(st.session_state['sat_data']))

with col_main2:
    st.subheader("🚨 سجل الإنذارات اللحظي (Alert Logs)")
    alerts_data = db.get_alerts(region=st.session_state.get('user_region', 'ALL'), limit=10)

    if alerts_data:
        df_alerts = pd.DataFrame(alerts_data, columns=["التوقيت", "المنطقة", "نوع الخطر", "نسبة التأكيد", "المصدر"])
        st.dataframe(df_alerts, use_container_width=True, hide_index=True)
    else:
        st.info("سجل الإنذارات هادئ ومستقر حالياً.")


# ==========================================
# الخريطة الجغرافية التفاعلية (GIS Map)
# ==========================================
st.markdown("---")
st.subheader("🗺️ خريطة الرصد والانتشار التفاعلية (Sovereign GIS Command)")

m = folium.Map(location=[36.0686, 4.7631], zoom_start=7, tiles="OpenStreetMap", control_scale=True)

# إضافة طبقة الصور الجوية والغطاء النباتي
if show_ndvi:
    try:
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri World Imagery",
            name="صور الأقمار والغطاء الأخضر",
            overlay=True,
            opacity=0.65
        ).add_to(m)
    except Exception:
        pass

# إضافة مراكز الحماية المدنية
if show_stations:
    units = db.get_all_civil_defense_units()
    if units:
        stations_group = folium.FeatureGroup(name="🚒 وحدات الحماية المدنية")
        for unit in units:
            try:
                lat, lon = float(unit), float(unit)
                folium.Marker(
                    location=[lat, lon],
                    popup=f"<b>🚒 {unit}</b><br>الولاية: {unit[0]}<br>البلدية: {unit}<br>الهاتف: {unit}",
                    tooltip=unit,
                    icon=folium.Icon(color="blue", icon="shield", prefix="fa")
                ).add_to(stations_group)
            except Exception:
                continue
        stations_group.add_to(m)

# رسم حدود الجزائر
folium.Rectangle(
    bounds=[[ALGERIA_BOUNDS['south'], ALGERIA_BOUNDS['west']],
            [ALGERIA_BOUNDS['north'], ALGERIA_BOUNDS['east']]],
    color='#00f2fe', weight=2, fill=False,
    popup="الحدود الوطنية الجزائرية"
).add_to(m)

# عرض النقاط الحرارية من الأقمار الصناعية
if st.session_state.get('sat_data'):
    fires_group = folium.FeatureGroup(name="🔥 النقاط الحرارية الفضائية")
    for fire in st.session_state['sat_data']:
        folium.CircleMarker(
            location=[fire['lat'], fire['lon']],
            radius=7,
            color="red",
            fill=True,
            fill_color="#ff5722",
            fill_opacity=0.8,
            popup=f"🔥 بؤرة حرارية - قمر {fire.get('sat')} - إحداثيات: {fire['lat']:.3f}, {fire['lon']:.3f}"
        ).add_to(fires_group)
    fires_group.add_to(m)

# تشغيل محاكاة انتشار النيران
if st.session_state.get("simulation_active"):
    sim_lat_val = st.session_state.get("sim_lat", 36.0686)
    sim_lon_val = st.session_state.get("sim_lon", 4.7631)

    sim_group = folium.FeatureGroup(name="🔥 نطاق انتشار النيران المتوقع")
    folium.Polygon(
        locations=[
            [sim_lat_val, sim_lon_val],
            [sim_lat_val + 0.08, sim_lon_val + 0.06],
            [sim_lat_val + 0.12, sim_lon_val - 0.02]
        ],
        color="red", fill=True, fill_color="red", fill_opacity=0.45,
        popup="نطاق الخطر المباشر (1 ساعة)"
    ).add_to(sim_group)
    folium.Marker(
        location=[sim_lat_val, sim_lon_val],
        popup="نقطة الاشتعال المركزية",
        icon=folium.Icon(color="red", icon="fire", prefix="fa")
    ).add_to(sim_group)
    sim_group.add_to(m)

folium.LayerControl().add_to(m)
folium_static(m, width=1100, height=520)


# ==========================================
# مؤشر مخاطر الطقس والتحليلات (FWI & Analytics)
# ==========================================
st.markdown("---")
st.subheader("🌡️ مؤشر مخاطر الحرائق الجوي (Fire Weather Index - FWI)")

fwi = get_fire_weather_index(36.0686, 4.7631)
col_w1, col_w2, col_w3, col_w4 = st.columns(4)

with col_w1:
    st.metric("درجة الحرارة", f"{fwi['temperature']} °C")
with col_w2:
    st.metric("الرطوبة النسبية", f"{fwi['humidity']} %")
with col_w3:
    st.metric("سرعة الرياح", f"{fwi['wind_speed']} km/h")
with col_w4:
    st.metric("نتيجة المؤشر (FWI)", f"{fwi['fwi_score']}", delta=fwi['danger_ar'], delta_color="inverse")

st.markdown(f"""
<div style="padding:12px; border-radius:8px; background-color:{fwi['color']}; color:white; text-align:center; font-weight:bold;">
    حالة التأهب المناخية: {fwi['danger_ar']} (Score: {fwi['fwi_score']})
</div>
""", unsafe_allow_html=True)

# التحليلات البيانية
st.markdown("---")
st.subheader("📊 لوحة التحليلات والإحصائيات البيانية")

df_all = db.get_all_alerts_for_analytics()
if not df_all.empty and len(df_all) > 0:
    c_chart1, c_chart2 = st.columns(2)
    with c_chart1:
        reg_counts = df_all.groupby('region_id').size().reset_index(name='العدد')
        fig_reg = px.bar(reg_counts, x='region_id', y='العدد', title="توزيع الإنذارات حسب المناطق", color='العدد', color_continuous_scale="Reds")
        st.plotly_chart(fig_reg, use_container_width=True)
    with c_chart2:
        src_counts = df_all.groupby('source').size().reset_index(name='العدد')
        fig_src = px.pie(src_counts, names='source', values='العدد', title="توزيع الإنذارات حسب مصدر الرصد", color_discrete_sequence=['#00f2fe', '#ff5722', '#ffaa00'])
        st.plotly_chart(fig_src, use_container_width=True)
else:
    st.info("لا توجد بيانات كافية حالياً لإنشاء المخططات الإحصائية.")

# ==========================================
# التذييل (Footer)
# ==========================================
st.markdown("---")
st.markdown("""
<div style='text-align:center; padding:15px; color:#888;'>
    <p style='color:#00f2fe; font-weight:bold;'>المنظومة الوطنية للرصد والإنذار المبكر لحرائق الغابات</p>
    <p style='font-size:12px;'>Sovereign Wildfire Detection Platform | Powered by YOLOv8 + NASA FIRMS + Open-Meteo</p>
</div>
""", unsafe_allow_html=True)