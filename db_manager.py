import sqlite3
import hashlib
import os
import secrets

DB_NAME = "national_cmd.db"


def init_db():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                region_id TEXT,
                hazard_type TEXT,
                confidence REAL,
                source TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS session_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                token TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Init Error: {e}")


def init_civil_defense_table():
    conn = sqlite3.connect(DB_NAME)
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
    count = cursor.fetchone()[0]
    if count >= 55:
        conn.close()
        return

    cursor.execute("DELETE FROM civil_defense_units")

    units_sample = [
        ("Algeria", "Alger", "الوحدة الرئيسية للحماية المدنية - الجزائر", 36.7538, 3.0588, "1021"),
        ("Tizi Ouzou", "Tizi Ouzou", "الوحدة الرئيسية - تيزي وزو", 36.7118, 4.0459, "1021"),
        ("Bejaia", "Bejaia", "الوحدة الرئيسية - بجاية", 36.7511, 5.0642, "1021"),
        ("Khenchela", "Bouhamama", "وحدة التدخل السريع - الأوراس", 35.3081, 6.7461, "1021"),
        ("El Tarf", "El Kala", "وحدة التدخل للغابات - القالة", 36.8970, 8.4431, "1021"),
        ("Jijel", "El Aouana", "وحدة الحماية المدنية - العوانة", 36.7725, 5.6078, "1021"),
        ("Skikda", "Skikda", "الوحدة الرئيسية - سكيكدة", 36.8761, 6.9094, "1021"),
        ("Annaba", "Annaba", "الوحدة الرئيسية - عنابة", 36.9000, 7.7667, "1021"),
        ("Guelma", "Guelma", "الوحدة الرئيسية - قالمة", 36.4625, 7.4264, "1021"),
        ("Constantine", "Constantine", "الوحدة الرئيسية - قسنطينة", 36.3650, 6.6147, "1021"),
        ("M'sila", "M'sila", "الوحدة الرئيسية - المسيلة", 35.7000, 4.5425, "1021"),
        ("Batna", "Batna", "الوحدة الرئيسية - باتنة", 35.5567, 6.1742, "1021"),
        ("Setif", "Setif", "الوحدة الرئيسية - سطيف", 36.1898, 5.4108, "1021"),
        ("Blida", "Blida", "الوحدة الرئيسية - البليدة", 36.4697, 2.8278, "1021"),
        ("Tlemcen", "Tlemcen", "الوحدة الرئيسية - تلمسان", 34.8828, -1.3167, "1021"),
        ("Oran", "Oran", "الوحدة الرئيسية - وهران", 35.6969, -0.6331, "1021"),
        ("Mascara", "Mascara", "الوحدة الرئيسية - معسكر", 35.3983, 0.1403, "1021"),
        ("Chlef", "Chlef", "الوحدة الرئيسية - الشلف", 36.1650, 1.3317, "1021"),
        ("Medea", "Medea", "الوحدة الرئيسية - المدية", 36.2675, 2.7542, "1021"),
        ("Djelfa", "Djelfa", "الوحدة الرئيسية - الجلفة", 34.6700, 3.2500, "1021"),
        ("Biskra", "Biskra", "الوحدة الرئيسية - بسكرة", 34.8481, 5.7269, "1021"),
        ("Ouargla", "Ouargla", "الوحدة الرئيسية - ورقلة", 31.9497, 5.3253, "1021"),
        ("Bechar", "Bechar", "الوحدة الرئيسية - بشار", 31.6167, -2.2167, "1021"),
        ("Tamanrasset", "Tamanrasset", "الوحدة الرئيسية - تمنراست", 22.7850, 5.5228, "1021"),
        ("Ghardaia", "Ghardaia", "الوحدة الرئيسية - غرداية", 32.4912, 3.6736, "1021"),
        ("Illizi", "Illizi", "الوحدة الرئيسية - إيليزي", 26.5000, 8.4667, "1021"),
        ("Bordj Bou Arreridj", "Bordj Bou Arreridj", "الوحدة الرئيسية - برج بوعريريج", 36.0686, 4.7631, "1021"),
        ("Bouira", "Bouira", "الوحدة الرئيسية - البيرة", 36.3733, 3.9008, "1021"),
        ("Tebessa", "Tebessa", "الوحدة الرئيسية - تبسة", 35.4042, 8.1211, "1021"),
        ("Tlemcen", "Maghnia", "وحدة التدخل السريع - مغنية", 34.8631, -1.7108, "1021"),
        ("Bejaia", "Akbou", "وحدة التدخل لحرائق الغابات - أقبو", 36.4592, 4.5364, "1021"),
        ("Tizi Ouzou", "Azazga", "وحدة الحماية المدنية - عزازقة", 36.7500, 4.3667, "1021"),
        ("Jijel", "Taher", "وحدة التدخل السريع - الطاهير", 36.7558, 5.8958, "1021"),
        ("Skikda", "Collo", "وحدة الحماية المدنية - القل", 37.0000, 6.5500, "1021"),
        ("Annaba", "El Bouni", "وحدة التدخل - البوني", 36.9000, 7.7333, "1021"),
        ("El Tarf", "Bouhadjar", "وحدة الحماية المدنية - بوحجر", 36.7500, 8.1333, "1021"),
        ("Khenchela", "Ain Touila", "وحدة التدخل - عين الطويلة", 35.4000, 7.1000, "1021"),
        ("Batna", "Barika", "وحدة الحماية المدنية - بريكة", 35.3500, 5.3500, "1021"),
        ("Setif", "Ain Oulmene", "وحدة التدخل - عين وسلمان", 36.1500, 5.4500, "1021"),
        ("Blida", "Boufarik", "وحدة الحماية المدنية - بوفاريك", 36.5750, 2.9100, "1021"),
        ("Tlemcen", "Ghazaouet", "وحدة التدخل السريع - الغزوات", 35.0833, -1.8500, "1021"),
        ("Oran", "Ain Turk", "وحدة الحماية المدنية - عين الترك", 35.7500, -1.1333, "1021"),
        ("Chlef", "Tenes", "وحدة التدخل - تنّس", 36.5167, 1.3000, "1021"),
        ("Medea", "Ksar Boukhari", "وحدة الحماية المدنية - قصر البخاري", 35.9000, 2.7500, "1021"),
        ("Djelfa", "Hassi Bahbah", "وحدة التدخل - حاسي بهbah", 34.4500, 3.0167, "1021"),
        ("Biskra", "Tolga", "وحدة الحماية المدنية - تولجة", 34.8833, 5.3667, "1021"),
        ("Ghardaia", "Metlili", "وحدة التدخل - متليلي", 32.2500, 3.6333, "1021"),
        ("Bouira", "Sour El Ghozlane", "وحدة الحماية المدنية - سور الغزلان", 36.1000, 3.8833, "1021"),
        ("M'sila", "Bou Saada", "وحدة التدخل - بوسعادة", 35.2167, 4.1833, "1021"),
        ("Tebessa", "Negrine", "وحدة الحماية المدنية - نقرينة", 35.2500, 8.2667, "1021"),
        ("Constantine", "El Khroub", "وحدة التدخل - الخروب", 36.2500, 6.6833, "1021"),
        ("Mascara", "Tighennif", "وحدة الحماية المدنية - تيغنينف", 35.4167, 0.2667, "1021"),
        ("Guelma", "Bouati Mahmoud", "وحدة التدخل - بوعتي محمود", 36.3333, 7.7500, "1021"),
        ("Tizi Ouzou", "Draa Ben Khedda", "وحدة الحماية المدنية - ذراع بن خدة", 36.7333, 3.9667, "1021"),
        ("Alger", "Dar El Beida", "وحدة التدخل - الدار البيضاء", 36.7167, 3.2500, "1021"),
        ("Tipaza", "Tipaza", "الوحدة الرئيسية - تيبازة", 36.5897, 2.4484, "1021"),
        ("Jijel", "Jijel", "الوحدة الرئيسية - جيجل", 36.8211, 5.7667, "1021"),
        ("Bejaia", "Bejaia", "الوحدة الرئيسية - بجاية", 36.7511, 5.0642, "1021"),
    ]

    cursor.executemany("""
        INSERT OR IGNORE INTO civil_defense_units (wilaya, daira_baladia, unit_name, lat, lon, contact_phone)
        VALUES (?, ?, ?, ?, ?, ?)
    """, units_sample)
    conn.commit()
    conn.close()


def get_all_civil_defense_units():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT wilaya, daira_baladia, unit_name, lat, lon, contact_phone FROM civil_defense_units")
        data = cursor.fetchall()
        conn.close()
        return data
    except Exception:
        return []


def hash_password(password, salt=None):
    if not salt:
        salt = os.urandom(16).hex()
    hashed = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
    return hashed, salt


def register_user(username, password, role="Operator"):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        pwd_hash, salt = hash_password(password)
        cursor.execute("INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)",
                       (username.strip(), pwd_hash, salt, role))
        cursor.execute("INSERT INTO alerts (region_id, hazard_type, confidence, source) VALUES (?, ?, ?, ?)",
                       (username.strip(), f"User Registered: {role}", 0.0, "system"))
        conn.commit()
        conn.close()
        return True, "تم إنشاء الحساب بنجاح! يمكنك الآن تسجيل الدخول."
    except sqlite3.IntegrityError:
        return False, "اسم المستخدم مسجل بالفعل."
    except Exception as e:
        return False, f"حدث خطأ أثناء التسجيل: {str(e)}"


def authenticate_user(username, password):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash, salt, role FROM users WHERE LOWER(username) = LOWER(?)", (username.strip(),))
        user = cursor.fetchone()
        conn.close()

        if user:
            stored_hash, salt, role = user
            check_hash, _ = hash_password(password.strip(), salt)
            if check_hash == stored_hash:
                return True, role
        return False, None
    except Exception as e:
        print(f"Auth Error: {e}")
        return False, None


def generate_session_token(username):
    token = secrets.token_hex(16)
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO session_tokens (username, token) VALUES (?, ?)", (username, token))
        conn.commit()
        conn.close()
        return token
    except Exception:
        return None


def verify_session_token(token):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM session_tokens WHERE token = ?", (token,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return True, row[0]
        return False, None
    except Exception:
        return False, None
