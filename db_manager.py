from dotenv import load_dotenv
load_dotenv()

import os
import json
import mysql.connector.pooling
from datetime import datetime
from math import radians, cos, sin, asin, sqrt
from openai import OpenAI

# -------------------------------------------------
# OPENAI
# -------------------------------------------------
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
# PAYMENTS
# -------------------------------------------------
def create_payment(uid, reference, poll_url):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        INSERT INTO payments (user_id, reference, poll_url)
        VALUES (%s, %s, %s)
    """, (uid, reference, poll_url))
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

def mark_payment_paid(payment_id):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE payments SET paid = 1, paid_at = %s WHERE id = %s",
                (datetime.utcnow(), payment_id))
    c.commit()
    cur.close()
    c.close()

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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            reference VARCHAR(50),
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
# USER
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

# -------------------------------------------------
# PROFILE
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

# -------------------------------------------------
# DISTANCE
# -------------------------------------------------
def compute_distance(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    c = 2*asin(sqrt(a))
    return R*c

# -------------------------------------------------
# RESET PROFILE
# -------------------------------------------------
def reset_profile(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        UPDATE profiles SET
            gender = NULL,
            name = NULL,
            age = NULL,
            location = NULL,
            intent = NULL,
            preferred_gender = NULL,
            age_min = NULL,
            age_max = NULL,
            contact_phone = NULL,
            temp_contact_phone = NULL,
            bio = NULL,
            hobbies = NULL,
            personality_traits = NULL,
            latitude = NULL,
            longitude = NULL
        WHERE user_id = %s
    """, (uid,))
    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# MATCHING (AI-BASED WITHOUT EMBEDDINGS)
# -------------------------------------------------
def get_matches(user_id):
    c = conn()
    cur = c.cursor(dictionary=True)

    cur.execute("SELECT * FROM profiles WHERE user_id=%s", (user_id,))
    user = cur.fetchone()
    if not user:
        return []

    # fetch all other candidates
    cur.execute("SELECT * FROM profiles WHERE user_id != %s", (user_id,))
    candidates = cur.fetchall()
    if not candidates:
        return []

    # compute distance for each
    for cand in candidates:
        cand['distance_km'] = compute_distance(
            user.get('latitude'),
            user.get('longitude'),
            cand.get('latitude'),
            cand.get('longitude')
        )

    # prepare candidate descriptions outside f-string
    candidate_texts = []
    for cand in candidates:
        candidate_texts.append(
            f"ID: {cand['user_id']}, Age: {cand['age']}, Gender: {cand['gender']}, Preferred Gender: {cand.get('preferred_gender','')}, Distance: {cand.get('distance_km','Unknown')}, Bio: {cand.get('bio','')}, Hobbies: {cand.get('hobbies','')}, Personality: {cand.get('personality_traits','')}"
        )

    # join outside f-string to avoid backslash inside {}
    candidates_joined = "\n".join(candidate_texts)

    prompt = f"""
You are an AI matchmaking assistant. Current user is a {user['age']} year old {user['gender']} who prefers {user.get('preferred_gender','')}.

Here are the candidate profiles:
{candidates_joined}

Choose and rank the top 3 matches purely based on compatibility, age preference, preferred gender, and proximity.  
Return only a Python list of user IDs, e.g., [3, 7, 15].
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        top_ids = eval(response.choices[0].message['content'])
    except Exception:
        top_ids = [cand['user_id'] for cand in candidates[:3]]

    # fetch full profiles of top matches
    if top_ids:
        format_ids = ",".join(str(i) for i in top_ids)
        cur.execute(f"SELECT * FROM profiles WHERE user_id IN ({format_ids})")
        top_matches = cur.fetchall()
    else:
        top_matches = []

    cur.close()
    c.close()
    return top_matches

def get_user_phone(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT phone FROM users WHERE id=%s", (uid,))
    row = cur.fetchone()
    cur.close()
    c.close()
    return row[0] if row else None




