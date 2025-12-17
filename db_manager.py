from dotenv import load_dotenv
load_dotenv()

import os
import mysql.connector.pooling
from datetime import datetime, timedelta

_pool = None

# -------------------------------------------------
# DATABASE CONNECTION
# -------------------------------------------------
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
# INITIALIZE DATABASE
# -------------------------------------------------
def init_db():
    c = conn()
    cur = c.cursor()
    cur.execute("DROP TABLE IF EXISTS transactions")
    cur.execute("DROP TABLE IF EXISTS profiles")
    cur.execute("DROP TABLE IF EXISTS users")

    # Users table
    cur.execute("""
    CREATE TABLE users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        phone VARCHAR(20) UNIQUE,
        gender VARCHAR(10),
        chat_state VARCHAR(20),
        is_active BOOLEAN DEFAULT 0,
        subscription_expiry DATETIME
    )
    """)

    # Profiles table (append-only)
    cur.execute("""
    CREATE TABLE profiles (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT,
        name VARCHAR(100),
        age INT,
        location VARCHAR(100),
        intent VARCHAR(50),
        age_min INT,
        age_max INT,
        contact_phone VARCHAR(20),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    # Transactions table
    cur.execute("""
    CREATE TABLE transactions (
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
# USER MANAGEMENT
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

def update_chat_state(uid, state):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE users SET chat_state=%s WHERE id=%s", (state, uid))
    c.commit()
    cur.close()
    c.close()

def reset_user(uid):
    c = conn()
    cur = c.cursor()
    # Do NOT delete previous profiles
    cur.execute("UPDATE users SET chat_state='NEW' WHERE id=%s", (uid,))
    c.commit()
    cur.close()
    c.close()

def update_gender(uid, gender):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE users SET gender=%s WHERE id=%s", (gender, uid))
    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# PROFILE MANAGEMENT
# -------------------------------------------------
def create_profile(uid, name="", age=None, location="", intent="", age_min=None, age_max=None, contact_phone=""):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        INSERT INTO profiles (user_id, name, age, location, intent, age_min, age_max, contact_phone)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (uid, name, age, location, intent, age_min, age_max, contact_phone))
    c.commit()
    cur.close()
    c.close()

def upsert_profile(uid, field, value):
    """
    If the user has a profile row without data, update it; otherwise create a new profile row.
    """
    c = conn()
    cur = c.cursor(dictionary=True)
    # Check if profile exists for this user
    cur.execute("SELECT * FROM profiles WHERE user_id=%s ORDER BY id DESC LIMIT 1", (uid,))
    profile = cur.fetchone()
    if profile:
        cur.execute(f"UPDATE profiles SET {field}=%s WHERE id=%s", (value, profile["id"]))
    else:
        # Create new profile row
        create_profile(uid)
        cur.execute(f"UPDATE profiles SET {field}=%s WHERE user_id=%s ORDER BY id DESC LIMIT 1", (value, uid))
    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# MATCHMAKING
# -------------------------------------------------
def get_matches(uid, limit=2):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("""
        SELECT p.*
        FROM profiles p
        JOIN users u ON u.id=p.user_id
        WHERE u.id != %s
        ORDER BY p.id DESC
        LIMIT %s
    """, (uid, limit))
    res = cur.fetchall()
    cur.close()
    c.close()
    return res

# -------------------------------------------------
# TRANSACTIONS
# -------------------------------------------------
def create_transaction(uid, ref, poll, amount):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        INSERT INTO transactions (user_id,reference,poll_url,amount,status)
        VALUES (%s,%s,%s,%s,'PENDING')
    """, (uid, ref, poll, amount))
    c.commit()
    cur.close()
    c.close()

def mark_transaction_paid(ref):
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
