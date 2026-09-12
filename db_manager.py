import sqlite3
import hashlib
import os

DB_NAME = "national_cmd.db"

def init_db():
    """إنشاء قاعدة البيانات والجداول الأساسية مع التشفير"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # جدول المستخدمين
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT DEFAULT 'Operator',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # جدول البلاغات والحوادث
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            risk_level TEXT NOT NULL,
            status TEXT DEFAULT 'Active',
            reported_by TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # جدول سجل العمليات (Audit Trail)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            action TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def hash_password(password, salt=None):
    """تشفير كلمة المرور مع ملح أمني (Salted SHA-256)"""
    if not salt:
        salt = os.urandom(16).hex()
    hashed = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
    return hashed, salt

def register_user(username, password, role="Operator"):
    """تسجيل مستخدم جديد بأمان"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        pwd_hash, salt = hash_password(password)
        cursor.execute("INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)",
                       (username, pwd_hash, salt, role))
        conn.commit()
        conn.close()
        return True, "تم إنشاء الحساب بنجاح!"
    except sqlite3.IntegrityError:
        return False, "اسم المستخدم مسجل بالفعل."

def authenticate_user(username, password):
    """التحقق من صحة بيانات الدخول"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, salt, role FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        stored_hash, salt, role = user
        check_hash, _ = hash_password(password, salt)
        if check_hash == stored_hash:
            return True, role
    return False, None
