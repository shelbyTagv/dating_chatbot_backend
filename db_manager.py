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

    # ---------------- USERS ----------------
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

    # ---------------- PROFILES ----------------
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
        "embedding": "JSON",
        "latitude": "DECIMAL(9,6)",
        "longitude": "DECIMAL(9,6)",
        "temp_contact_phone": "VARCHAR(20)"
    }

    for col, col_type in profile_columns.items():
        if not column_exists(cur, "profiles", col):
            cur.execute(f"ALTER TABLE profiles ADD {col} {col_type}")

    # ---------------- PAYMENTS ----------------
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
    cur.execute("""
        UPDATE users
        SET is_paid=1, paid_at=%s, chat_state='PAID'
        WHERE id=%s
    """, (datetime.utcnow(), uid))
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
# EMBEDDINGS
# -------------------------------------------------
def build_profile_text(p):
    return (
        f"{p.get('age','')} year old {p.get('gender','')} in {p.get('location','')}.\n"
        f"Looking for {p.get('intent','')}.\n"
        f"Hobbies: {p.get('hobbies','')}.\n"
        f"Personality: {p.get('personality_traits','')}.\n"
        f"Bio: {p.get('bio','')}."
    )

def update_embedding(uid):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM profiles WHERE user_id=%s", (uid,))
    p = cur.fetchone()
    if not p:
        cur.close()
        c.close()
        return

    text = build_profile_text(p)
    emb = client.embeddings.create(
        model="text-embedding-3-large",
        input=text
    ).data[0].embedding

    cur.execute(
        "UPDATE profiles SET embedding=%s WHERE user_id=%s",
        (json.dumps(emb), uid)
    )
    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# MATCHING (AI)
# -------------------------------------------------
def cosine_similarity(v1, v2):
    dot = sum(a*b for a,b in zip(v1,v2))
    n1 = sum(a*a for a in v1) ** 0.5
    n2 = sum(b*b for b in v2) ** 0.5
    return dot / (n1*n2) if n1 and n2 else 0

def haversine(lat1, lon1, lat2, lon2):
    if None in [lat1, lon1, lat2, lon2]:
        return 999
    lon1, lat1, lon2, lat2 = map(radians,[lon1,lat1,lon2,lat2])
    dlon = lon2-lon1
    dlat = lat2-lat1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 6371 * 2 * asin(sqrt(a))
