from dotenv import load_dotenv
load_dotenv()

import os
import mysql.connector.pooling
from datetime import datetime, timedelta
import random

_pool = None

def conn():
    global _pool
    if not _pool:
        _pool = mysql.connector.pooling.MySQLConnectionPool(
            pool_name="dating_pool",
            pool_size=5,
            host=os.getenv("MYSQLHOST"),
            user=os.getenv("MYSQLUSER"),
            password=os.getenv("MYSQLPASSWORD"),
            database=os.getenv("MYSQL_DATABASE"),
            port=int(os.getenv("MYSQL_PORT", 3306)),
        )
    return _pool.get_connection()

def init_db():
    c = conn()
    cur = c.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        phone VARCHAR(20) UNIQUE,
        gender VARCHAR(10),
        chat_state VARCHAR(20),
        is_active BOOLEAN DEFAULT 0,
        subscription_expiry DATETIME
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        user_id INT PRIMARY KEY,
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

    c.commit()
    cur.close()
    c.close()

# ------------------------------
# USERS
# ------------------------------
def get_user_by_phone(phone):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE phone=%s", (phone,))
    u = cur.fetchone()
    cur.close()
    c.close()
    return u

def create_user(phone):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute(
        "INSERT INTO users (phone, chat_state) VALUES (%s,'NEW')",
        (phone,)
    )
    c.commit()
    cur.execute("SELECT * FROM users WHERE id=LAST_INSERT_ID()")
    u = cur.fetchone()
    cur.close()
    c.close()
    return u

def set_state(uid, state):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE users SET chat_state=%s WHERE id=%s", (state, uid))
    c.commit()
    cur.close()
    c.close()

def set_gender(uid, gender):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE users SET gender=%s WHERE id=%s", (gender, uid))
    c.commit()
    cur.close()
    c.close()

# ------------------------------
# PROFILE (ONE PER USER)
# ------------------------------
def ensure_profile(uid):
    c = conn()
    cur = c.cursor()
    cur.execute(
        "INSERT IGNORE INTO profiles (user_id) VALUES (%s)",
        (uid,)
    )
    c.commit()
    cur.close()
    c.close()

def update_profile(uid, field, value):
    c = conn()
    cur = c.cursor()
    cur.execute(
        f"UPDATE profiles SET {field}=%s WHERE user_id=%s",
        (value, uid)
    )
    c.commit()
    cur.close()
    c.close()

# ------------------------------
# MATCHING
# ------------------------------
def get_matches(uid, limit=2):
    c = conn()
    cur = c.cursor(dictionary=True)

    cur.execute("""
        SELECT p.*, u.gender
        FROM profiles p
        JOIN users u ON u.id = p.user_id
        WHERE p.user_id = %s
    """, (uid,))
    me = cur.fetchone()

    if not me:
        cur.close()
        c.close()
        return []

    cur.execute("""
        SELECT p.*, u.gender AS user_gender
        FROM profiles p
        JOIN users u ON u.id = p.user_id
        WHERE p.user_id != %s
    """, (uid,))
    candidates = cur.fetchall()

    cur.close()
    c.close()

    if not candidates:
        return []

    for c in candidates:
        c["score"] = random.randint(50, 100)

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:limit]
