import sqlite3
import hashlib
import os
import secrets
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# توحيد مسار قاعدة البيانات من ملف .env مع قيمة افتراضية موحدة
DB_NAME = os.getenv("DATABASE_PATH", "national_cmd.db")
logger = logging.getLogger("db_manager")


def get_connection():
    """إنشاء اتصال آمن بقاعدة البيانات"""
    return sqlite3.connect(DB_NAME, timeout=10)


def init_db():
    """تهيئة الجداول وإجراء الترقية التلقائية للأعمدة الناقصة"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            # 1. جدول المستخدمين
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    region TEXT DEFAULT 'ALL',
                    role TEXT DEFAULT 'Operator',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 2. جدول الإنذارات
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    region_id TEXT,
                    hazard_type TEXT,
                    confidence REAL,
                    source TEXT DEFAULT 'Camera',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # التحقق من وجود عمود source لترقية القواعد القديمة (حل مشكلة no such column: source)
            cursor.execute("PRAGMA table_info(alerts)")
            columns = [col[1] for col in cursor.fetchall()]
            if "source" not in columns:
                cursor.execute("ALTER TABLE alerts ADD COLUMN source TEXT DEFAULT 'Camera'")
                logger.info("Migrated alerts table: added 'source' column successfully.")

            # 3. جدول جلسات الدخول
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS session_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # إنشاء حساب مسؤول افتراضي إذا لم يوجد
            cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
            if cursor.fetchone()[0] == 0:
                pwd_hash, salt = hash_password("admin123")
                cursor.execute(
                    "INSERT INTO users (username, password_hash, salt, role, region) VALUES (?, ?, ?, ?, ?)",
                    ("admin", pwd_hash, salt, "Admin", "ALL")
                )
            conn.commit()
            logger.info(f"Database initialized successfully: {DB_NAME}")
    except Exception as e:
        logger.error(f"DB Init Error: {e}")


def add_alert(region_id: str, hazard_type: str, confidence: float, source: str = "Camera"):
    """دالة مركزية لتسجيل أي إنذار (من الكاميرات، الأقمار الصناعية، أو الحساسات)"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO alerts (region_id, hazard_type, confidence, source) VALUES (?, ?, ?, ?)",
                (region_id, hazard_type, round(float(confidence), 3), source)
            )
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Failed to insert alert: {e}")
        return False


def get_alerts(region: str = "ALL", limit: int = 15):
    """جلب أحدث التنبيهات لعرضها في الداشبورد"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            if region == "ALL":
                cursor.execute(
                    "SELECT timestamp, region_id, hazard_type, confidence, source FROM alerts ORDER BY id DESC LIMIT ?",
                    (limit,)
                )
            else:
                cursor.execute(
                    "SELECT timestamp, region_id, hazard_type, confidence, source FROM alerts WHERE region_id = ? ORDER BY id DESC LIMIT ?",
                    (region, limit)
                )
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Alert query failed: {e}")
        return []


def get_all_alerts_for_analytics():
    """جلب جميع التنبيهات المعتمدة لتحليلات الرسوم البيانية"""
    import pandas as pd
    try:
        with get_connection() as conn:
            df = pd.read_sql_query(
                "SELECT timestamp, region_id, hazard_type, confidence, source FROM alerts",
                conn
            )
            return df
    except Exception as e:
        logger.error(f"Analytics query failed: {e}")
        import pandas as pd
        return pd.DataFrame()


def init_civil_defense_table():
    """تهيئة وحدات الحماية المدنية الرئيسية عبر ولايات الجزائر"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS civil_defense_units (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wilaya TEXT NOT NULL,
                    daira_baladia TEXT NOT NULL,
                    unit_name TEXT NOT NULL,
                    lat REAL NOT NULL,
                    lon REAL NOT NULL,
                    contact_phone TEXT DEFAULT '1021'
                )
            ''')

            cursor.execute("SELECT COUNT(*) FROM civil_defense_units")
            if cursor.fetchone()[0] >= 30:
                return

            cursor.execute("DELETE FROM civil_defense_units")

            units = [
                ("Alger", "Alger", "الوحدة المركزية للحماية المدنية - العاصمة", 36.7538, 3.0588, "1021"),
                ("Tizi Ouzou", "Tizi Ouzou", "الوحدة الرئيسية - تيزي وزو (غابات جرجرة)", 36.7118, 4.0459, "1021"),
                ("Bejaia", "Bejaia", "الوحدة الرئيسية - بجاية (غابات يما قورايا)", 36.7511, 5.0642, "1021"),
                ("Jijel", "Jijel", "وحدة التدخل لحرائق الغابات - جيجل", 36.8211, 5.7667, "1021"),
                ("Skikda", "Collo", "وحدة التدخل السريع للغابات - القل", 37.0000, 6.5500, "1021"),
                ("El Tarf", "El Kala", "وحدة الحماية المدنية - القالة (الحظيرة الوطنية)", 36.8970, 8.4431, "1021"),
                ("Tipaza", "Tipaza", "الوحدة الرئيسية - تيبازة (غابات شنوة)", 36.5897, 2.4484, "1021"),
                ("Khenchela", "Bouhamama", "وحدة التدخل السريع - بوحمامة (غابات الأوراس)", 35.3081, 6.7461, "1021"),
                ("Blida", "Chrea", "وحدة التدخل الجبلي - الشريعة", 36.4250, 2.8770, "1021"),
                ("Bordj Bou Arreridj", "BBA", "الوحدة الرئيسية - برج بوعريريج", 36.0686, 4.7631, "1021"),
                ("Setif", "Setif", "الوحدة الرئيسية - سطيف", 36.1898, 5.4108, "1021"),
                ("Bouira", "Tikjda", "وحدة الحماية المدنية - تيكجدة", 36.4550, 4.1350, "1021"),
                ("Guelma", "Guelma", "الوحدة الرئيسية - قالمة", 36.4625, 7.4264, "1021"),
                ("Annaba", "Seraidi", "وحدة التدخل الجبلي - سرايدي (جبال إيدوغ)", 36.9167, 7.6667, "1021"),
                ("Tlemcen", "Mansourah", "وحدة الحماية المدنية - المنصورة", 34.8828, -1.3167, "1021"),
                ("Oran", "Ain Turk", "الوحدة الرئيسية - عين الترك", 35.7500, -1.1333, "1021"),
                ("Medea", "Medea", "الوحدة الرئيسية - المدية", 36.2675, 2.7542, "1021"),
                ("Chlef", "Tenes", "وحدة التدخل - تنس", 36.5167, 1.3000, "1021")
            ]

            cursor.executemany("""
                INSERT INTO civil_defense_units (wilaya, daira_baladia, unit_name, lat, lon, contact_phone)
                VALUES (?, ?, ?, ?, ?, ?)
            """, units)
            conn.commit()
    except Exception as e:
        logger.error(f"Civil Defense Table Init Error: {e}")


def get_all_civil_defense_units():
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT wilaya, daira_baladia, unit_name, lat, lon, contact_phone FROM civil_defense_units")
            return cursor.fetchall()
    except Exception:
        return []


def hash_password(password: str, salt: str = None):
    if not salt:
        salt = os.urandom(16).hex()
    hashed = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
    return hashed, salt


def register_user(username, password, role="Operator", region="ALL"):
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            pwd_hash, salt = hash_password(password)
            cursor.execute(
                "INSERT INTO users (username, password_hash, salt, role, region) VALUES (?, ?, ?, ?, ?)",
                (username.strip(), pwd_hash, salt, role, region)
            )
            add_alert(region, f"حساب جديد مسجل: {username} ({role})", 1.0, "System")
            conn.commit()
            return True, "تم إنشاء الحساب بنجاح!"
    except sqlite3.IntegrityError:
        return False, "اسم المستخدم مسجل مسبقاً."
    except Exception as e:
        return False, f"خطأ في التسجيل: {e}"


def authenticate_user(username, password):
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT password_hash, salt, role, region FROM users WHERE LOWER(username) = LOWER(?)",
                (username.strip(),)
            )
            user = cursor.fetchone()
            if user:
                stored_hash, salt, role, region = user
                check_hash, _ = hash_password(password.strip(), salt)
                if check_hash == stored_hash:
                    return True, role
            return False, None
    except Exception as e:
        logger.error(f"Auth Error: {e}")
        return False, None


def generate_session_token(username):
    token = secrets.token_hex(16)
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO session_tokens (username, token) VALUES (?, ?)", (username, token))
            conn.commit()
            return token
    except Exception:
        return None


def verify_session_token(token):
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM session_tokens WHERE token = ?", (token,))
            row = cursor.fetchone()
            if row:
                return True, row[0]
            return False, None
    except Exception:
        return False, None