from dotenv import load_dotenv
import os
import mysql.connector
from mysql.connector import pooling
from datetime import datetime, timedelta

load_dotenv()

_connection_pool = None

# -------------------------------------------------
# CONNECTION POOL (LAZY LOAD)
# -------------------------------------------------
def get_db_pool():
    global _connection_pool

    if _connection_pool is None:
        dbconfig = {
            "host": os.getenv("MYSQL_HOST"),
            "user": os.getenv("MYSQL_USER"),
            "password": os.getenv("MYSQL_PASSWORD"),
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
# DB INITIALIZATION (AUTO-RUN ON STARTUP)
# -------------------------------------------------
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            phone_number VARCHAR(20) UNIQUE NOT NULL,
            chat_state VARCHAR(50) DEFAULT 'START',
            is_active BOOLEAN DEFAULT 0,
            subscription_expiry DATETIME NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT UNIQUE NOT NULL,
            name VARCHAR(100),
            age INT,
            gender VARCHAR(20),
            location VARCHAR(100),
            motive VARCHAR(50),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
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
        cur.execute(
            "SELECT id, phone_number, chat_state, is_active FROM users WHERE phone_number=%s",
            (phone,),
        )
        user = cur.fetchone()

        if not user:
            cur.execute(
                "INSERT INTO users (phone_number) VALUES (%s)",
                (phone,),
            )
            conn.commit()

            cur.execute(
                "SELECT id, phone_number, chat_state, is_active FROM users WHERE phone_number=%s",
                (phone,),
            )
            user = cur.fetchone()

    finally:
        cur.close()
        conn.close()

    return user


def update_chat_state(user_id, state):
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute(
            "UPDATE users SET chat_state=%s WHERE id=%s",
            (state, user_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

# -------------------------------------------------
# PROFILES
# -------------------------------------------------
ALLOWED_PROFILE_FIELDS = {"name", "age", "gender", "location", "motive"}


def ensure_profile(user_id):
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute(
            "INSERT IGNORE INTO profiles (user_id) VALUES (%s)",
            (user_id,),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def update_profile_field(user_id, field, value):
    if field not in ALLOWED_PROFILE_FIELDS:
        raise ValueError("Invalid profile field")

    ensure_profile(user_id)

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute(
            f"UPDATE profiles SET {field}=%s WHERE user_id=%s",
            (value, user_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def get_user_profile(user_id):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    try:
        cur.execute(
            "SELECT * FROM profiles WHERE user_id=%s",
            (user_id,),
        )
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()

# -------------------------------------------------
# PAYMENTS
# -------------------------------------------------
def create_transaction(user_id, reference, poll_url, amount):
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            INSERT INTO transactions
            (user_id, paynow_reference, poll_url, amount, status)
            VALUES (%s,%s,%s,%s,'PENDING')
            """,
            (user_id, reference, poll_url, amount),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def get_transaction_by_reference(reference):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    try:
        cur.execute(
            "SELECT * FROM transactions WHERE paynow_reference=%s LIMIT 1",
            (reference,),
        )
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def mark_transaction_paid(tx_id):
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute(
            "UPDATE transactions SET status='PAID' WHERE id=%s",
            (tx_id,),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def activate_subscription(user_id):
    expiry = datetime.utcnow() + timedelta(days=30)

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            UPDATE users
            SET is_active=1,
                subscription_expiry=%s,
                chat_state='ACTIVE_SEARCH'
            WHERE id=%s
            """,
            (expiry, user_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

# -------------------------------------------------
# MATCHING (SAFE VERSION)
# -------------------------------------------------
def find_potential_matches(user_id, location):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    try:
        cur.execute(
            """
            SELECT
                U.id AS match_user_id,
                P.name AS match_name,
                P.age AS match_age,
                P.motive AS match_motive,
                U.phone_number AS match_phone
            FROM users U
            JOIN profiles P ON U.id = P.user_id
            WHERE
                U.is_active = 1
                AND U.id != %s
                AND P.location = %s
            LIMIT 1
            """,
            (user_id, location),
        )
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()
