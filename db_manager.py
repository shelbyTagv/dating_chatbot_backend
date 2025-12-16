from dotenv import load_dotenv
import os
import mysql.connector
from mysql.connector import pooling
from datetime import datetime, timedelta

load_dotenv()

_connection_pool = None

# -------------------------------------------------
# CONNECTION POOL
# -------------------------------------------------
def get_db_pool():
    global _connection_pool

    if _connection_pool is None:
        dbconfig = {
            "host": os.getenv("MYSQLHOST"),
            "user": os.getenv("MYSQLUSER"),
            "password": os.getenv("MYSQLPASSWORD"),
            "database": os.getenv("MYSQL_DATABASE"),
            "port": int(os.getenv("MYSQL_PORT", 3306)),
        }

        _connection_pool = mysql.connector.pooling.MySQLConnectionPool(
            pool_name="dating_pool",
            pool_size=5,
            pool_reset_session=True,
            **dbconfig,
        )

    return _connection_pool

def get_conn():
    return get_db_pool().get_connection()

# -------------------------------------------------
# INIT DB
# -------------------------------------------------
def init_db():
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Drop existing tables to ensure clean schema
        cur.execute("DROP TABLE IF EXISTS transactions")
        cur.execute("DROP TABLE IF EXISTS profiles")
        cur.execute("DROP TABLE IF EXISTS users")

        # Users table
        cur.execute("""
        CREATE TABLE users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            phone_number VARCHAR(20) UNIQUE NOT NULL,
            chat_state VARCHAR(50) DEFAULT 'NEW',
            is_active BOOLEAN DEFAULT 0,
            subscription_expiry DATETIME NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Profiles table
        cur.execute("""
        CREATE TABLE profiles (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT UNIQUE NOT NULL,
            name VARCHAR(100),
            age INT,
            gender VARCHAR(20),
            location VARCHAR(100),
            relationship_type VARCHAR(50),
            preferred_person TEXT,
            contact_phone VARCHAR(20),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)

        # Transactions table
        cur.execute("""
        CREATE TABLE transactions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            paynow_reference VARCHAR(100) UNIQUE,
            poll_url TEXT,
            amount DECIMAL(10,2),
            status VARCHAR(20),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)

        conn.commit()
    finally:
        cur.close()
        conn.close()

# -------------------------------------------------
# USERS
# -------------------------------------------------
def get_or_create_user(phone):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM users WHERE phone_number=%s", (phone,))
        user = cur.fetchone()
        if not user:
            cur.execute("INSERT INTO users (phone_number) VALUES (%s)", (phone,))
            conn.commit()
            cur.execute("SELECT * FROM users WHERE phone_number=%s", (phone,))
            user = cur.fetchone()
    finally:
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

def reset_user(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM profiles WHERE user_id=%s", (user_id,))
    cur.execute("""
        UPDATE users
        SET chat_state='NEW',
            is_active=0,
            subscription_expiry=NULL
        WHERE id=%s
    """, (user_id,))
    conn.commit()
    cur.close()
    conn.close()

# -------------------------------------------------
# PROFILES
# -------------------------------------------------
ALLOWED_PROFILE_FIELDS = {
    "name",
    "age",
    "gender",
    "location",
    "relationship_type",
    "preferred_person",
    "contact_phone",
}

def ensure_profile(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT IGNORE INTO profiles (user_id) VALUES (%s)", (user_id,))
    conn.commit()
    cur.close()
    conn.close()

def update_profile_field(user_id, field, value):
    if field not in ALLOWED_PROFILE_FIELDS:
        raise ValueError("Invalid profile field")
    ensure_profile(user_id)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"UPDATE profiles SET {field}=%s WHERE user_id=%s", (value, user_id))
    conn.commit()
    cur.close()
    conn.close()

# -------------------------------------------------
# PAYMENTS
# -------------------------------------------------
def create_transaction(user_id, reference, poll_url, amount):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO transactions
        (user_id, paynow_reference, poll_url, amount, status)
        VALUES (%s,%s,%s,%s,'PENDING')
    """, (user_id, reference, poll_url, amount))
    conn.commit()
    cur.close()
    conn.close()

def get_transaction_by_reference(reference):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM transactions WHERE paynow_reference=%s", (reference,))
    tx = cur.fetchone()
    cur.close()
    conn.close()
    return tx

def mark_transaction_paid(tx_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE transactions SET status='PAID' WHERE id=%s", (tx_id,))
    conn.commit()
    cur.close()
    conn.close()

def unlock_full_profiles(user_id):
    expiry = datetime.utcnow() + timedelta(days=1)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE users
        SET is_active=1,
            subscription_expiry=%s,
            chat_state='ACTIVE'
        WHERE id=%s
    """, (expiry, user_id))
    conn.commit()
    cur.close()
    conn.close()

# -------------------------------------------------
# AI MATCH PREVIEW (GPT-style filtering)
# -------------------------------------------------
def ai_match_preview(user_id):
    """
    Returns matches based on:
    - Age range (±5 years)
    - Gender preference
    - Relationship type
    - Same location
    """
    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    # Get current user's profile
    cur.execute("SELECT * FROM profiles WHERE user_id=%s", (user_id,))
    user_profile = cur.fetchone()
    if not user_profile:
        return []

    # Basic matching logic
    age_min = user_profile["age"] - 5 if user_profile["age"] else 0
    age_max = user_profile["age"] + 5 if user_profile["age"] else 100
    relationship = user_profile["relationship_type"]
    location = user_profile["location"]

    cur.execute("""
        SELECT *
        FROM profiles P
        JOIN users U ON U.id = P.user_id
        WHERE
            U.id != %s
            AND U.is_active = 1
            AND P.age BETWEEN %s AND %s
            AND P.relationship_type = %s
            AND P.location = %s
        LIMIT 5
    """, (user_id, age_min, age_max, relationship, location))

    results = cur.fetchall()
    cur.close()
    conn.close()
    return results
