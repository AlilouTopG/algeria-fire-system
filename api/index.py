import os
import io
import requests
import pandas as pd
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Algeria Wildfire Early Warning API", version="2.0")

# تفعيل الـ CORS لتتمكن الواجهة من التخاطب مع الـ API بحرية
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# قاعدة بيانات تخزين مؤقتة للإنذارات اللحظية في السحابة
IN_MEMORY_ALERTS = [
    {
        "id": 1,
        "region": "Bordj Bou Arreridj",
        "hazard_type": "FIRE",
        "confidence": 0.89,
        "source": "AI Camera - Sector 1",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
]

NASA_FIRMS_API_KEY = os.getenv("NASA_FIRMS_API_KEY", "b7a1a0de499d32758672ad0cb7bae6da")

CIVIL_DEFENSE_STATIONS = [
    {"wilaya": "Bordj Bou Arreridj", "unit_name": "الوحدة الرئيسية - برج بوعريريج", "lat": 36.0686, "lon": 4.7631, "phone": "1021"},
    {"wilaya": "Tizi Ouzou", "unit_name": "الوحدة الرئيسية - تيزي وزو (جرجرة)", "lat": 36.7118, "lon": 4.0459, "phone": "1021"},
    {"wilaya": "Bejaia", "unit_name": "الوحدة الرئيسية - بجاية (قورايا)", "lat": 36.7511, "lon": 5.0642, "phone": "1021"},
    {"wilaya": "Jijel", "unit_name": "وحدة حرائق الغابات - جيجل", "lat": 36.8211, "lon": 5.7667, "phone": "1021"},
    {"wilaya": "Skikda", "unit_name": "وحدة التدخل السريع - القل", "lat": 37.0000, "lon": 6.5500, "phone": "1021"},
    {"wilaya": "El Tarf", "unit_name": "وحدة الحماية المدنية - القالة", "lat": 36.8970, "lon": 8.4431, "phone": "1021"},
    {"wilaya": "Tipaza", "unit_name": "الوحدة الرئيسية - تيبازة (شنوة)", "lat": 36.5897, "lon": 2.4484, "phone": "1021"},
    {"wilaya": "Khenchela", "unit_name": "وحدة التدخل السريع - الأوراس", "lat": 35.3081, "lon": 6.7461, "phone": "1021"},
    {"wilaya": "Blida", "unit_name": "وحدة التدخل الجبلي - الشريعة", "lat": 36.4250, "lon": 2.8770, "phone": "1021"},
    {"wilaya": "Bouira", "unit_name": "وحدة الحماية المدنية - تيكجدة", "lat": 36.4550, "lon": 4.1350, "phone": "1021"},
    {"wilaya": "Alger", "unit_name": "الوحدة المركزية للحماية المدنية - العاصمة", "lat": 36.7538, "lon": 3.0588, "phone": "1021"}
]


class AlertPayload(BaseModel):
    region_id: str
    hazard_type: str
    confidence: float
    source: str = "Live Camera (AI)"


@app.get("/api/health")
def health_check():
    return {"status": "online", "system": "Algerian Wildfire Early Warning Core", "version": "2.0"}


@app.get("/api/alerts")
def get_alerts():
    """جلب سجل الإنذارات"""
    return {"alerts": sorted(IN_MEMORY_ALERTS, key=lambda x: x["id"], reverse=True)}


@app.post("/api/alerts")
def receive_alert(alert: AlertPayload):
    """نقطة نهاية لاستقبال الإنذارات القادمة من كاميرات الذكاء الاصطناعي الميدانية"""
    new_alert = {
        "id": len(IN_MEMORY_ALERTS) + 1,
        "region": alert.region_id,
        "hazard_type": alert.hazard_type.upper(),
        "confidence": round(alert.confidence, 3),
        "source": alert.source,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    IN_MEMORY_ALERTS.append(new_alert)
    return {"status": "success", "message": "Alert registered in National System", "alert": new_alert}


@app.get("/api/weather")
def get_weather_and_fwi(lat: float = 36.0686, lon: float = 4.7631):
    """حساب مؤشر مخاطر الحرائق FWI لولاية برج بوعريريج أو أي ولاية مطلوبة"""
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m"
            f"&timezone=Africa/Algiers"
        )
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        current = data.get('current', {})

        temp = current.get('temperature_2m', 25)
        humidity = current.get('relative_humidity_2m', 50)
        wind = current.get('wind_speed_10m', 10)

        fwi = (temp * 0.3) + ((100 - humidity) * 0.4) + (wind * 0.3)

        if fwi >= 70:
            danger, color = "خطر شديد جداً (Extreme)", "#d32f2f"
        elif fwi >= 50:
            danger, color = "خطر مرتفع (High)", "#ff5722"
        elif fwi >= 30:
            danger, color = "خطر متوسط (Moderate)", "#ff9800"
        elif fwi >= 15:
            danger, color = "خطر منخفض (Low)", "#4caf50"
        else:
            danger, color = "خطر ضئيل (Minimal)", "#8bc34a"

        return {
            "temperature": temp,
            "humidity": humidity,
            "wind_speed": wind,
            "fwi_score": round(fwi, 1),
            "danger_level": danger,
            "color": color
        }
    except Exception as e:
        return {
            "temperature": 25, "humidity": 45, "wind_speed": 15,
            "fwi_score": 38.5, "danger_level": "خطر متوسط (تقديري)", "color": "#ff9800"
        }


@app.get("/api/firms")
def get_nasa_fires():
    """جلب النقاط الحرارية فوق التراب الوطني من أقمار NASA FIRMS"""
    all_fires = []
    seen = set()
    for sat in ["VIIRS_NOAA20_NRT", "VIIRS_SNPP_NRT"]:
        try:
            url = f"https://firms.modaps.eosdis.nasa.gov/api/country/csv/{NASA_FIRMS_API_KEY}/{sat}/DZA/1"
            res = requests.get(url, timeout=10)
            if res.status_code == 200 and "latitude" in res.text:
                df = pd.read_csv(io.StringIO(res.text))
                for _, row in df.iterrows():
                    key = (round(float(row['latitude']), 3), round(float(row['longitude']), 3))
                    if key not in seen:
                        seen.add(key)
                        all_fires.append({
                            "lat": float(row['latitude']),
                            "lon": float(row['longitude']),
                            "confidence": row.get('confidence', 'nominal'),
                            "satellite": sat
                        })
        except Exception:
            continue
    return {"active_fires": all_fires, "total": len(all_fires)}


@app.get("/api/stations")
def get_stations():
    """قائمة مراكز ووحدات الحماية المدنية"""
    return {"stations": CIVIL_DEFENSE_STATIONS}