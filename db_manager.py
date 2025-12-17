from dotenv import load_dotenv
load_dotenv()

import os
import mysql.connector.pooling
from datetime import datetime, timedelta
import random
import json
from openai import OpenAI

_pool = None

# ------------------------------
# DATABASE CONNECTION
# ------------------------------
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

# ------------------------------
# INITIALIZE DATABASE
# ------------------------------
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
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT,
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

    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT,
        reference VARCHAR(100),
        poll_url TEXT,
        amount DECIMAL(5,2),
        status VARCHAR(20),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.commit()
    cur.close()
    c.close()

# ------------------------------
# USER MANAGEMENT
# ------------------------------
def get_user_by_phone(phone):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE phone=%s", (phone,))
    user = cur.fetchone()
    cur.close()
    c.close()
    return user

def create_new_user(phone, gender=None):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute(
        "INSERT INTO users (phone, gender, chat_state) VALUES (%s,%s,'NEW')",
        (phone, gender)
    )
    c.commit()
    cur.execute("SELECT * FROM users WHERE id=LAST_INSERT_ID()")
    user = cur.fetchone()
    cur.close()
    c.close()
    return user

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
# PROFILE MANAGEMENT
# ------------------------------
def create_profile(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("INSERT INTO profiles (user_id) VALUES (%s)", (uid,))
    c.commit()
    cur.close()
    c.close()

def update_profile(uid, field, value):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute(
        "SELECT id FROM profiles WHERE user_id=%s ORDER BY id DESC LIMIT 1",
        (uid,)
    )
    p = cur.fetchone()
    if p:
        cur.execute(
            f"UPDATE profiles SET {field}=%s WHERE id=%s",
            (value, p["id"])
        )
        c.commit()
    cur.close()
    c.close()

# ------------------------------
# MATCHMAKING
# ------------------------------
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_matches(uid, limit=2):
    c = conn()
    cur = c.cursor(dictionary=True)

    cur.execute("""
        SELECT u.gender AS my_gender, p.*
        FROM profiles p
        JOIN users u ON u.id = p.user_id
        WHERE u.id=%s
        ORDER BY p.id DESC LIMIT 1
    """, (uid,))
    me = cur.fetchone()

    if not me:
        cur.close()
        c.close()
        return []

    cur.execute("""
        SELECT p.*, u.gender AS user_gender, u.id AS user_id
        FROM profiles p
        JOIN users u ON u.id = p.user_id
        WHERE u.id != %s
    """, (uid,))
    candidates = cur.fetchall()

    cur.close()
    c.close()

    if not candidates:
        return []

    data = [{
        "id": c["user_id"],
        "name": c["name"],
        "age": c["age"],
        "gender": c["user_gender"],
        "intent": c["intent"],
        "preferred_gender": c["preferred_gender"],
        "location": c["location"],
        "score": random.randint(50, 100)
    } for c in candidates]

    data.sort(key=lambda x: x["score"], reverse=True)

    for m in data[:limit]:
        m["more_available"] = len(data) > limit

    return data[:limit]

# ------------------------------
# PAYMENTS
# ------------------------------
def create_tx(uid, ref, poll, amount):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        INSERT INTO transactions (user_id, reference, poll_url, amount, status)
        VALUES (%s,%s,%s,%s,'PENDING')
    """, (uid, ref, poll, amount))
    c.commit()
    cur.close()
    c.close()

def mark_paid(ref):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE transactions SET status='PAID' WHERE reference=%s", (ref,))
    cur.execute("""
        UPDATE users
        SET is_active=1, subscription_expiry=%s
        WHERE id=(SELECT user_id FROM transactions WHERE reference=%s)
    """, (datetime.utcnow() + timedelta(days=1), ref))
    c.commit()
    cur.close()
    c.close()
