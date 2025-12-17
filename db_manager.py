from dotenv import load_dotenv
load_dotenv()

import os
import mysql.connector.pooling
import random
from datetime import datetime

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
# INIT DB
# -------------------------------------------------
def init_db():
    c = conn()
    cur = c.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        phone VARCHAR(20) UNIQUE,
        chat_state VARCHAR(20),
        is_active BOOLEAN DEFAULT 0
    )""")

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
        contact_phone VARCHAR(20)
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT,
        reference VARCHAR(50),
        poll_url TEXT,
        status VARCHAR(20) DEFAULT 'PENDING',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# PAYMENT FUNCTIONS
# -------------------------------------------------
def create_payment(uid, ref, poll_url):
    c = conn()
    cur = c.cursor()
    cur.execute(
        "INSERT INTO payments (user_id, reference, poll_url) VALUES (%s,%s,%s)",
        (uid, ref, poll_url)
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

def mark_payment_paid(pid):
    c = conn()
    cur = c.cursor()
    cur.execute(
        "UPDATE payments SET status='PAID' WHERE id=%s", (pid,)
    )
    c.commit()
    cur.close()
    c.close()

def activate_user(uid):
    c = conn()
    cur = c.cursor()
    cur.execute(
        "UPDATE users SET is_active=1 WHERE id=%s", (uid,)
    )
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
# MATCHING (UNCHANGED)
# -------------------------------------------------
def get_matches(uid, limit=2):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("""
        SELECT p.*, u.phone
        FROM profiles p
        JOIN users u ON u.id=p.user_id
        WHERE p.user_id!=%s AND p.contact_phone IS NOT NULL
    """, (uid,))
    rows = cur.fetchall()
    random.shuffle(rows)
    cur.close()
    c.close()
    return rows[:limit]
