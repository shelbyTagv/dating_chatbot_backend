from dotenv import load_dotenv
load_dotenv()

import os
import mysql.connector
from mysql.connector import pooling
from datetime import datetime, timedelta

_pool = None

def get_pool():
    global _pool
    if _pool is None:
        _pool = mysql.connector.pooling.MySQLConnectionPool(
            pool_name="dating_pool",
            pool_size=5,
            host=os.getenv("MYSQLHOST"),
            user=os.getenv("MYSQLUSER"),
            password=os.getenv("MYSQLPASSWORD"),
            database=os.getenv("MYSQL_DATABASE"),
            port=int(os.getenv("MYSQL_PORT", 3306)),
        )
    return _pool

def conn():
    return get_pool().get_connection()

# -------------------------------------------------
# INIT DB
# -------------------------------------------------
def init_db():
    c = conn()
    cur = c.cursor()

    cur.execute("DROP TABLE IF EXISTS feedback")
    cur.execute("DROP TABLE IF EXISTS transactions")
    cur.execute("DROP TABLE IF EXISTS profiles")
    cur.execute("DROP TABLE IF EXISTS users")

    cur.execute("""
    CREATE TABLE users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        phone VARCHAR(20) UNIQUE,
        gender VARCHAR(10),
        chat_state VARCHAR(50),
        is_active BOOLEAN DEFAULT 0,
        subscription_expiry DATETIME,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE profiles (
        user_id INT PRIMARY KEY,
        name VARCHAR(100),
        age INT,
        location VARCHAR(100),
        intent VARCHAR(50),
        age_min INT,
        age_max INT,
        photo_url TEXT,
        contact_phone VARCHAR(20),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    cur.execute("""
    CREATE TABLE transactions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT,
        reference VARCHAR(100),
        poll_url TEXT,
        status VARCHAR(20),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE feedback (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT,
        message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# USERS
# -------------------------------------------------
def get_or_create_user(phone):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE phone=%s", (phone,))
    u = cur.fetchone()
    if not u:
        cur.execute(
            "INSERT INTO users (phone, chat_state) VALUES (%s,'WELCOME')",
            (phone,)
        )
        c.commit()
        cur.execute("SELECT * FROM users WHERE phone=%s", (phone,))
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

# -------------------------------------------------
# PROFILE
# -------------------------------------------------
def upsert_profile(uid, field, value):
    c = conn()
    cur = c.cursor()
    cur.execute("INSERT IGNORE INTO profiles (user_id) VALUES (%s)", (uid,))
    cur.execute(f"UPDATE profiles SET {field}=%s WHERE user_id=%s", (value, uid))
    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# MATCHING
# -------------------------------------------------
INTENT_MAP = {
    "boyfriend": ("male", "girlfriend"),
    "girlfriend": ("female", "boyfriend"),
    "sugar mummy": ("female", "benten"),
    "benten": ("male", "sugar mummy"),
    "1 night stand": ("any", "1 night stand"),
    "just vibes": ("any", "just vibes"),
    "friend": ("any", "friend"),
}

def get_matches(uid, limit=2):
    c = conn()
    cur = c.cursor(dictionary=True)

    cur.execute("""
    SELECT u.gender, p.*
    FROM users u JOIN profiles p ON u.id=p.user_id
    WHERE u.id=%s
    """, (uid,))
    me = cur.fetchone()
    if not me:
        return []

    my_gender, target_intent = INTENT_MAP.get(me["intent"], ("any", me["intent"]))

    cur.execute("""
    SELECT p.name,p.age,p.location,p.intent,p.photo_url,u.id
    FROM profiles p
    JOIN users u ON u.id=p.user_id
    WHERE u.id!=%s
      AND p.intent=%s
      AND p.age BETWEEN %s AND %s
      AND (%s='any' OR u.gender=%s)
    ORDER BY ABS(p.age-%s)
    LIMIT %s
    """, (
        uid,
        target_intent,
        me["age_min"],
        me["age_max"],
        my_gender,
        my_gender,
        me["age"],
        limit
    ))

    res = cur.fetchall()
    cur.close()
    c.close()
    return res

# -------------------------------------------------
# PAYMENTS
# -------------------------------------------------
def create_tx(uid, ref, poll):
    c = conn()
    cur = c.cursor()
    cur.execute("""
    INSERT INTO transactions (user_id,reference,poll_url,status)
    VALUES (%s,%s,%s,'PENDING')
    """, (uid, ref, poll))
    c.commit()
    cur.close()
    c.close()

def mark_paid(ref):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE transactions SET status='PAID' WHERE reference=%s", (ref,))
    cur.execute("""
        UPDATE users SET is_active=1,
        subscription_expiry=%s WHERE id=(
            SELECT user_id FROM transactions WHERE reference=%s
        )
    """, (datetime.utcnow()+timedelta(days=1), ref))
    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# FEEDBACK
# -------------------------------------------------
def save_feedback(uid, text):
    c = conn()
    cur = c.cursor()
    cur.execute("INSERT INTO feedback (user_id,message) VALUES (%s,%s)", (uid,text))
    c.commit()
    cur.close()
    c.close()
