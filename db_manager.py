from dotenv import load_dotenv
load_dotenv()

import os
import mysql.connector.pooling
from datetime import datetime, timedelta

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

# -------------------------------------------------
def init_db():
    c = conn()
    cur = c.cursor()

    # Create tables only if they do not exist
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

# -------------------------------------------------
def get_or_create_user(phone):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE phone=%s", (phone,))
    u = cur.fetchone()
    if not u:
        cur.execute("INSERT INTO users (phone,chat_state) VALUES (%s,'NEW')", (phone,))
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

def reset_user(uid):
    # Only reset chat state, do not delete profiles
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE users SET chat_state='NEW' WHERE id=%s", (uid,))
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

def upsert_profile(uid, field, value):
    c = conn()
    cur = c.cursor()
    # Insert a new profile row if it doesn't exist
    cur.execute("INSERT IGNORE INTO profiles (user_id) VALUES (%s)", (uid,))
    # Update the specified field
    cur.execute(f"UPDATE profiles SET {field}=%s WHERE user_id=%s", (value, uid))
    c.commit()
    cur.close()
    c.close()

def get_matches(uid, limit=2):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("""
    SELECT p.*
    FROM profiles p
    JOIN users u ON u.id=p.user_id
    WHERE u.id != %s
    LIMIT %s
    """, (uid, limit))
    res = cur.fetchall()
    cur.close()
    c.close()
    return res

# -------------------------------------------------
def create_tx(uid, ref, poll, amount):
    c = conn()
    cur = c.cursor()
    cur.execute("""
    INSERT INTO transactions (user_id,reference,poll_url,amount,status)
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
    UPDATE users SET is_active=1, subscription_expiry=%s
    WHERE id=(SELECT user_id FROM transactions WHERE reference=%s)
    """, (datetime.utcnow()+timedelta(days=1), ref))
    c.commit()
    cur.close()
    c.close()

def get_transaction_by_reference(ref):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM transactions WHERE reference=%s", (ref,))
    tx = cur.fetchone()
    cur.close()
    c.close()
    return tx

def unlock_full_profiles(uid):
    # No-op for now, just placeholder
    pass
