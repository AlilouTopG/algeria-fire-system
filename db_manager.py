import sqlite3
import hashlib
import os


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
                role TEXT DEFAULT 'Operator',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
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
    except Exception as e:
        print(f"DB Init Error: {e}")


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
        
        # تسجيل العملية في Audit Log
        cursor.execute("INSERT INTO audit_logs (username, action) VALUES (?, ?)",
                       (username.strip(), f"User Registered with role {role}"))
        
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
        # استخدام Parameterized Query لمنع SQL Injection وقبول الحالة بأمان
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
