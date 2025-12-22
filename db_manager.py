from dotenv import load_dotenv
load_dotenv()

import os
import json
import random
import mysql.connector.pooling
from datetime import datetime
from math import radians, cos, sin, asin, sqrt
from openai import OpenAI

# -------------------------------------------------
# CONSTANTS & CONFIG
# -------------------------------------------------
INTENT_COMPATIBILITY = {
    "girlfriend": ["boyfriend"],
    "boyfriend": ["girlfriend"],
    "sugar mummy": ["sugar daddy"],
    "sugar daddy": ["sugar mummy"],
    "1 night stand": ["1 night stand", "just vibes"],
    "just vibes": ["1 night stand", "just vibes"],
    "friend": ["friend"],
    "benten": ["benten"]
}

INTENT_GROUPS = {
    "girlfriend": "SERIOUS",
    "boyfriend": "SERIOUS",

    "1 night stand": "CASUAL",
    "just vibes": "CASUAL",

    "sugar daddy": "SUGAR",
    "sugar mummy": "SUGAR",

    "friend": "SOCIAL",
    "benten": "SOCIAL",
}

GROUP_COMPATIBILITY = {
    "SERIOUS": ["SERIOUS"],
    "CASUAL": ["CASUAL", "SOCIAL"],
    "SUGAR": ["SUGAR"],
    "SOCIAL": ["SOCIAL", "CASUAL"],
}



client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# -------------------------------------------------
# DB CONNECTION POOL
# -------------------------------------------------
_pool = None

def conn():
    global _pool
    if not _pool:
        _pool = mysql.connector.pooling.MySQLConnectionPool(
            pool_name="dating_pool",
            pool_size=10,
            host=os.getenv("MYSQLHOST"),
            user=os.getenv("MYSQLUSER"),
            password=os.getenv("MYSQLPASSWORD"),
            database=os.getenv("MYSQL_DATABASE"),
            port=int(os.getenv("MYSQL_PORT", 3306)),
        )
    return _pool.get_connection()

# -------------------------------------------------
# COLUMN CHECK HELPER
# -------------------------------------------------
def column_exists(cursor, table, column):
    cursor.execute("""
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
    """, (table, column))
    return cursor.fetchone()[0] > 0

# -------------------------------------------------
# INIT + AUTO-MIGRATION
# -------------------------------------------------
def init_db():
    c = conn()
    cur = c.cursor()

    # Users Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            phone VARCHAR(20) UNIQUE,
            chat_state VARCHAR(32) DEFAULT 'NEW',
            is_paid TINYINT DEFAULT 0
        )
    """)

    if not column_exists(cur, "users", "paid_at"):
        cur.execute("ALTER TABLE users ADD paid_at DATETIME")

    # Profiles Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            user_id INT PRIMARY KEY,
            gender VARCHAR(10),
            name VARCHAR(100),
            age INT,
            location VARCHAR(100),
            intent VARCHAR(50),
            preferred_gender VARCHAR(10),
            age_min INT,
            age_max INT,
            contact_phone VARCHAR(20),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    profile_columns = {
        "bio": "TEXT",
        "hobbies": "TEXT",
        "personality_traits": "TEXT",
        "latitude": "DECIMAL(9,6)",
        "longitude": "DECIMAL(9,6)",
        "temp_contact_phone": "VARCHAR(20)"
    }

    for col, col_type in profile_columns.items():
        if not column_exists(cur, "profiles", col):
            cur.execute(f"ALTER TABLE profiles ADD {col} {col_type}")

    # Payments Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            reference VARCHAR(50) UNIQUE,
            poll_url TEXT,
            paid TINYINT DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    if not column_exists(cur, "payments", "paid_at"):
        cur.execute("ALTER TABLE payments ADD paid_at DATETIME")

    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# PAYMENTS
# -------------------------------------------------
def create_payment(uid, reference, poll_url):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        INSERT INTO payments (user_id, reference, poll_url)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE poll_url=%s
    """, (uid, reference, poll_url, poll_url))
    c.commit()
    cur.close()
    c.close()

def get_pending_payments():
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM payments WHERE paid = 0")
    rows = cur.fetchall()
    cur.close()
    c.close()
    return rows

def mark_payment_paid(reference):
    c = conn()
    cur = c.cursor()
    # Check by reference since it's the primary identifier from PesePay
    cur.execute("UPDATE payments SET paid = 1, paid_at = %s WHERE reference = %s",
                (datetime.utcnow(), reference))
    c.commit()
    cur.close()
    c.close()

def update_payment_poll(uid, reference, poll_url):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        INSERT INTO payments (user_id, reference, poll_url)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE poll_url=%s
    """, (uid, reference, poll_url, poll_url))
    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# USER MANAGEMENT
# -------------------------------------------------
def get_user_by_phone(phone):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE phone=%s", (phone,))
    u = cur.fetchone()
    cur.close()
    c.close()
    return u

def create_new_user(phone):
    c = conn()
    cur = c.cursor()
    cur.execute("INSERT INTO users (phone) VALUES (%s)", (phone,))
    c.commit()
    cur.close()
    c.close()
    return get_user_by_phone(phone)

def set_state(uid, state):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE users SET chat_state=%s WHERE id=%s", (state, uid))
    c.commit()
    cur.close()
    c.close()

def activate_user(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE users SET is_paid=1, paid_at=%s, chat_state='PAID' WHERE id=%s",
                (datetime.utcnow(), uid))
    c.commit()
    cur.close()
    c.close()

def get_user_phone(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT phone FROM users WHERE id=%s", (uid,))
    row = cur.fetchone()
    cur.close()
    c.close()
    return row[0] if row else None


def reset_user_payment(uid):
    c=conn()
    try:
        cur = c.cursor()
        # Updating the 'users' table specifically
        query = "UPDATE users SET is_paid = 0 WHERE id = %s"
        cur.execute(query, (uid,))
        c.commit()
        print(f"DEBUG: Payment status reset for User ID {uid}")
    except Exception as e:
        print(f"Error resetting payment for User {uid}: {e}")
    finally:
        cur.close()
        c.close()

# -------------------------------------------------
# PROFILE MANAGEMENT
# -------------------------------------------------
def ensure_profile(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT user_id FROM profiles WHERE user_id=%s", (uid,))
    if not cur.fetchone():
        cur.execute("INSERT INTO profiles (user_id) VALUES (%s)", (uid,))
        c.commit()
    cur.close()
    c.close()

def update_profile(uid, field, value):
    c = conn()
    cur = c.cursor()
    cur.execute(f"UPDATE profiles SET {field}=%s WHERE user_id=%s", (value, uid))
    c.commit()
    cur.close()
    c.close()

def get_user_gender(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT gender FROM profiles WHERE user_id=%s", (uid,))
    row = cur.fetchone()
    cur.close()
    c.close()
    return row[0] if row else None


def get_profile_name(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT name FROM profiles WHERE user_id = %s", (uid,))
    row = cur.fetchone()
    cur.close()
    c.close()
    return row[0] if row and row[0] else "Customer"

def reset_profile(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        UPDATE profiles SET
            gender = NULL, name = NULL, age = NULL, location = NULL,
            intent = NULL, preferred_gender = NULL, age_min = NULL,
            age_max = NULL, contact_phone = NULL, temp_contact_phone = NULL,
            bio = NULL, hobbies = NULL, personality_traits = NULL,
            latitude = NULL, longitude = NULL
        WHERE user_id = %s
    """, (uid,))
    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# MATCHING LOGIC
# -------------------------------------------------
def get_matches(user_id):
    c = conn()
    cur = c.cursor(dictionary=True)

    cur.execute("SELECT * FROM profiles WHERE user_id=%s", (user_id,))
    user = cur.fetchone()
    if not user:
        return []

    cur.execute("SELECT * FROM profiles WHERE user_id != %s", (user_id,))
    candidates = cur.fetchall()
    cur.close()
    c.close()

    matches = []
    for cand in candidates:
        if gender_match(user, cand) and age_match(user, cand) and intent_match(user, cand):
            matches.append(cand)

    if matches:
        matches = random.sample(matches, min(2, len(matches)))

    return matches

def gender_match(user, cand):
    u_g = user.get("gender")
    c_g = cand.get("gender")
    if not u_g or not c_g: return False
    return u_g != c_g  # Basic heterosexual logic

def age_match(user, cand):
    try:
        return (user["age_min"] <= cand["age"] <= user["age_max"] and
                cand["age_min"] <= user["age"] <= cand["age_max"])
    except: return False

def intent_match(user, cand):
    user_intent = user.get("intent")
    cand_intent = cand.get("intent")

    if not user_intent or not cand_intent:
        return False

    user_group = INTENT_GROUPS.get(user_intent)
    cand_group = INTENT_GROUPS.get(cand_intent)

    if not user_group or not cand_group:
        return False

    return cand_group in GROUP_COMPATIBILITY.get(user_group, [])


# -------------------------------------------------
# GEOLOCATION (OPTIONAL)
# -------------------------------------------------
def compute_distance(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2): return None
    R = 6371
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return R * (2 * asin(sqrt(a)))