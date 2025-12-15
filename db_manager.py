from dotenv import load_dotenv
load_dotenv()

import os
import mysql.connector.pooling

from datetime import datetime, timedelta

dbconfig = {
    "host": os.getenv("MYSQL_HOST"),
    "user": os.getenv("MYSQL_USER"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": os.getenv("MYSQL_DATABASE"),
}

pool = mysql.connector.pooling.MySQLConnectionPool(
    pool_name="dating_pool",
    pool_size=5,
    **dbconfig
)

def get_conn():
    return pool.get_connection()

# ---------- USERS ----------

def get_or_create_user(phone):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT * FROM users WHERE phone_number=%s", (phone,))
    user = cur.fetchone()

    if not user:
        cur.execute("INSERT INTO users (phone_number) VALUES (%s)", (phone,))
        conn.commit()
        cur.execute("SELECT * FROM users WHERE phone_number=%s", (phone,))
        user = cur.fetchone()

    cur.close()
    conn.close()
    return user

def update_chat_state(user_id, state):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET chat_state=%s WHERE id=%s", (state, user_id))
    conn.commit()
    cur.close()
    conn.close()

# ---------- PROFILES ----------

def ensure_profile(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT IGNORE INTO profiles (user_id, gender, motive) VALUES (%s,'Other','Unknown')", (user_id,))
    conn.commit()
    cur.close()
    conn.close()

def update_profile_field(user_id, field, value):
    ensure_profile(user_id)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"UPDATE profiles SET {field}=%s WHERE user_id=%s", (value, user_id))
    conn.commit()
    cur.close()
    conn.close()

# ---------- PAYMENTS ----------

def create_transaction(user_id, reference, poll_url, amount):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO transactions (user_id, paynow_reference, poll_url, amount)
        VALUES (%s,%s,%s,%s)
    """, (user_id, reference, poll_url, amount))
    conn.commit()
    cur.close()
    conn.close()

def get_pending_transactions():
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM transactions WHERE status='PENDING'")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def mark_transaction_paid(tx_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE transactions SET status='PAID' WHERE id=%s", (tx_id,))
    conn.commit()
    cur.close()
    conn.close()

def activate_subscription(user_id):
    expiry = datetime.now() + timedelta(days=30)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE users
        SET is_active=1, subscription_expiry=%s, chat_state='ACTIVE_SEARCH'
        WHERE id=%s
    """, (expiry, user_id))
    conn.commit()
    cur.close()
    conn.close()

# ---------- MATCHMAKING ----------

def find_match(user_id, motive):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT p.*
        FROM profiles p
        JOIN users u ON p.user_id=u.id
        WHERE u.is_active=1
          AND p.motive=%s
          AND p.user_id != %s
        LIMIT 1
    """, (motive, user_id))
    match = cur.fetchone()
    cur.close()
    conn.close()
    return match
