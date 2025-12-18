from dotenv import load_dotenv
load_dotenv()

import os
import random
import mysql.connector.pooling
from datetime import datetime

_pool = None

# -------------------------------------------------
# CONNECTION POOL
# -------------------------------------------------
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
# INIT DB (DROP + RECREATE)
# -------------------------------------------------
def init_db():
    c = conn()
    cur = c.cursor()

    # DROP IN CORRECT ORDER (FK SAFETY)
    cur.execute("DROP TABLE IF EXISTS payments")
    cur.execute("DROP TABLE IF EXISTS profiles")
    cur.execute("DROP TABLE IF EXISTS users")

    # USERS
    cur.execute("""
        CREATE TABLE users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            phone VARCHAR(20) UNIQUE NOT NULL,
            chat_state VARCHAR(30) DEFAULT 'NEW',
            is_active BOOLEAN DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # PROFILES (1:1 WITH USERS)
    cur.execute("""
        CREATE TABLE profiles (
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

    # PAYMENTS
    cur.execute("""
        CREATE TABLE payments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            reference VARCHAR(100),
            poll_url TEXT,
            status VARCHAR(20) DEFAULT 'PENDING',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# USER FUNCTIONS
# -------------------------------------------------
def get_user_by_phone(phone):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE phone=%s", (phone,))
    user = cur.fetchone()
    cur.close()
    c.close()
    return user

def create_new_user(phone):
    c = conn()
    cur = c.cursor()
    cur.execute(
        "INSERT INTO users (phone, chat_state) VALUES (%s, 'NEW')",
        (phone,)
    )
    c.commit()
    uid = cur.lastrowid
    cur.close()
    c.close()
    return {"id": uid, "phone": phone}

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
    cur.execute("UPDATE users SET is_active=1 WHERE id=%s", (uid,))
    c.commit()
    cur.close()
    c.close()

def get_user_phone(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT phone FROM users WHERE id=%s", (uid,))
    phone = cur.fetchone()[0]
    cur.close()
    c.close()
    return phone

# -------------------------------------------------
# PROFILE FUNCTIONS
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

def reset_profile(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        UPDATE profiles SET
            name=NULL,
            age=NULL,
            location=NULL,
            intent=NULL,
            preferred_gender=NULL,
            age_min=NULL,
            age_max=NULL,
            contact_phone=NULL
        WHERE user_id=%s
    """, (uid,))
    c.commit()
    cur.close()
    c.close()

def update_profile(uid, field, value):
    if field not in {
        "name", "age", "location", "intent",
        "preferred_gender", "age_min",
        "age_max", "contact_phone"
    }:
        raise ValueError("Invalid profile field")

    c = conn()
    cur = c.cursor()
    cur.execute(
        f"UPDATE profiles SET {field}=%s WHERE user_id=%s",
        (value, uid)
    )
    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# PAYMENT FUNCTIONS
# -------------------------------------------------
def create_payment(uid, reference, poll_url):
    c = conn()
    cur = c.cursor()
    cur.execute(
        "INSERT INTO payments (user_id, reference, poll_url) VALUES (%s,%s,%s)",
        (uid, reference, poll_url)
    )
    c.commit()
    cur.close()
    c.close()

def get_pending_payments():
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM payments WHERE status='PENDING'")
    rows = cur.fetchall()
    cur.close()
    c.close()
    return rows

def mark_payment_paid(payment_id):
    c = conn()
    cur = c.cursor()
    cur.execute(
        "UPDATE payments SET status='PAID' WHERE id=%s",
        (payment_id,)
    )
    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# MATCHES
# -------------------------------------------------
def get_matches(uid, limit=2):
    c = conn()
    cur = c.cursor(dictionary=True)

    cur.execute("""
        SELECT
            p.name,
            p.age,
            p.location,
            p.intent,
            p.contact_phone
        FROM profiles p
        JOIN users u ON u.id = p.user_id
        WHERE
            p.user_id != %s
            AND p.contact_phone IS NOT NULL
            AND u.is_active = 1
    """, (uid,))

    rows = cur.fetchall()
    random.shuffle(rows)

    cur.close()
    c.close()
    return rows[:limit]
