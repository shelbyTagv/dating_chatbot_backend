from dotenv import load_dotenv
load_dotenv()

import os
import random
import mysql.connector.pooling
from datetime import datetime

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
# INIT (Drops and Creates)
# -------------------------------------------------
def init_db():
    c = conn()
    cur = c.cursor()

    # 1. Users Table (No drop, only create if missing)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            phone VARCHAR(20) UNIQUE,
            chat_state VARCHAR(32) DEFAULT 'NEW',
            is_paid TINYINT DEFAULT 0,
            paid_at DATETIME
        )
    """)

    # 2. Profiles Table (Corrected with Picture)
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
            picture TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # 3. Payments Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            reference VARCHAR(50) UNIQUE,
            poll_url TEXT,
            paid TINYINT DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            paid_at DATETIME,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    c.commit()
    cur.close()
    c.close()
    print("✅ Database connection verified. Tables checked/created.")

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

    # Basic matching: Heterosexual, within age range, matching intent
    cur.execute("""
        SELECT * FROM profiles 
        WHERE user_id != %s 
        AND gender = %s 
        AND age BETWEEN %s AND %s
    """, (user_id, user['preferred_gender'], user['age_min'], user['age_max']))
    
    candidates = cur.fetchall()
    cur.close()
    c.close()

    # Filter by intent and mutual age preference
    valid_matches = []
    for cand in candidates:
        # Check if user fits in candidate's age range
        if cand['age_min'] <= user['age'] <= cand['age_max']:
            valid_matches.append(cand)

    if valid_matches:
        return random.sample(valid_matches, min(2, len(valid_matches)))
    return []

# -------------------------------------------------
# USER & PROFILE HELPERS
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
    cur.execute("INSERT INTO users (phone, chat_state) VALUES (%s, 'NEW')", (phone,))
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
    query = f"UPDATE profiles SET {field}=%s WHERE user_id=%s"
    cur.execute(query, (value, uid))
    c.commit()
    cur.close()
    c.close()

def reset_profile(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        UPDATE profiles SET
            gender=NULL, name=NULL, age=NULL, location=NULL, intent=NULL,
            preferred_gender=NULL, age_min=NULL, age_max=NULL, 
            contact_phone=NULL, picture=NULL
        WHERE user_id = %s
    """, (uid,))
    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# PAYMENT HELPERS
# -------------------------------------------------
def create_payment(uid, reference, poll_url):
    c = conn()
    cur = c.cursor()
    cur.execute("INSERT INTO payments (user_id, reference, poll_url) VALUES (%s, %s, %s)", 
                (uid, reference, poll_url))
    c.commit()
    cur.close()
    c.close()

def mark_payment_paid(reference):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE payments SET paid = 1, paid_at = %s WHERE reference = %s",
                (datetime.utcnow(), reference))
    c.commit()
    cur.close()
    c.close()

def activate_user(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE users SET is_paid=1, paid_at=%s WHERE id=%s",
                (datetime.utcnow(), uid))
    c.commit()
    cur.close()
    c.close()

def reset_user_payment(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE users SET is_paid = 0 WHERE id = %s", (uid,))
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

def get_user_phone(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT phone FROM users WHERE id=%s", (uid,))
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

def get_pending_payments_for_user(uid):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM payments WHERE user_id=%s AND paid=0 ORDER BY created_at DESC", (uid,))
    rows = cur.fetchall()
    cur.close()
    c.close()
    return rows