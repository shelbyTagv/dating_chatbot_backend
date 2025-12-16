from dotenv import load_dotenv
import os
import mysql.connector
from mysql.connector import pooling
from datetime import datetime, timedelta

# Load environment variables from .env file (primarily for local development)
load_dotenv() 

# Global variable to hold the pool instance (Initialized to None for Lazy Loading)
_connection_pool = None

# -------------------------------------------------
# Database Pool Management (LAZY LOADING IMPLEMENTED)
# -------------------------------------------------

def get_db_pool():
    """
    Initializes the database connection pool the first time it is called (Lazy Loading).
    This prevents application crashes at startup if the database isn't ready.
    """
    global _connection_pool
    if _connection_pool is None:
        
        # NOTE: Using standard environment variable names (MYSQL_HOST, not MYSQLHOST)
        dbconfig = {
            "host": os.getenv("MYSQLHOST"),      
            "user": os.getenv("MYSQLUSER"),      
            "password": os.getenv("MYSQLPASSWORD"), 
            "database": os.getenv("MYSQL_DATABASE"), 
            # Convert port to int, defaulting to 3306 if MYSQL_PORT is not set
            "port": int(os.getenv("MYSQL_PORT", 3306)) 
        }
        
        # Initialize the pool
        _connection_pool = mysql.connector.pooling.MySQLConnectionPool(
            pool_name="dating_pool",
            pool_size=5,
            **dbconfig
        )
        
    return _connection_pool

def get_conn():
    """Retrieves a connection from the lazily loaded pool."""
    pool = get_db_pool() # Ensure pool is initialized
    return pool.get_connection()

# -------------------------------------------------
# USERS
# -------------------------------------------------
def get_or_create_user(phone):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    try:
        cur.execute("SELECT id, phone_number, chat_state, is_active FROM users WHERE phone_number=%s", (phone,))
        user = cur.fetchone()

        if not user:
            cur.execute("""
                INSERT INTO users (phone_number, chat_state, is_active)
                VALUES (%s, 'START', 0)
            """, (phone,))
            conn.commit()

            cur.execute("SELECT id, phone_number, chat_state, is_active FROM users WHERE phone_number=%s", (phone,))
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
            (state, user_id)
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
        cur.execute("""
            INSERT IGNORE INTO profiles (user_id, gender, motive)
            VALUES (%s, 'Other', 'Unknown')
        """, (user_id,))
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
            (value, user_id)
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

def get_user_profile(user_id):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM profiles WHERE user_id=%s", (user_id,))
        profile = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    return profile

# -------------------------------------------------
# PAYMENTS
# -------------------------------------------------
def create_transaction(user_id, reference, poll_url, amount):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO transactions
            (user_id, paynow_reference, poll_url, amount, status, created_at)
            VALUES (%s,%s,%s,%s,'PENDING',NOW())
        """, (user_id, reference, poll_url, amount))
        conn.commit()
    finally:
        cur.close()
        conn.close()

def get_pending_transactions():
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT *
            FROM transactions
            WHERE status='PENDING'
        """)
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return rows

def get_transaction_by_reference(reference):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT *
            FROM transactions
            WHERE paynow_reference=%s
            LIMIT 1
        """, (reference,))
        tx = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    return tx

def mark_transaction_paid(tx_id):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE transactions SET status='PAID' WHERE id=%s",
            (tx_id,)
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
        cur.execute("""
            UPDATE users
            SET is_active=1,
                subscription_expiry=%s,
                chat_state='ACTIVE_SEARCH'
            WHERE id=%s
        """, (expiry, user_id))
        conn.commit()
    finally:
        cur.close()
        conn.close()

# -------------------------------------------------
# MATCHMAKING (The Core Logic - Advanced Query)
# -------------------------------------------------

def find_potential_matches(user_id, user_location):
    """
    Finds a potential match based on strict mutual preference criteria.
    """
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    
    # U1 = Current User, U2 = Potential Match
    query = """
    SELECT
        U2.id AS match_user_id,
        P2.name AS match_name,
        P2.age AS match_age,
        P2.motive AS match_motive,
        U2.phone_number AS match_phone
    FROM
        users U1
    JOIN
        profiles P1 ON U1.id = P1.user_id
    JOIN
        preferences PR1 ON U1.id = PR1.user_id
    JOIN
        users U2 ON U1.id != U2.id  -- Cannot match self
    JOIN
        profiles P2 ON U2.id = P2.user_id
    JOIN
        preferences PR2 ON U2.id = PR2.user_id
    WHERE
        U1.id = %s                               -- 1. Current user filter (U1)
        AND U2.is_active = 1                     -- 2. Match must be active (U2)
        AND P2.location = %s                     -- 3. Filter by current user's location
        AND P1.location = P2.location            -- 4. Must be in the same location (Proximity)
        
        -- MUTUAL CRITERIA A: USER 1's preferences match USER 2's profile
        AND P2.gender = PR1.pref_gender          -- U2's gender matches U1's preference
        AND P2.age BETWEEN PR1.pref_min_age AND PR1.pref_max_age -- U2's age is in U1's preferred range
        AND P2.motive = PR1.pref_motive          -- U2's motive matches U1's preference
        
        -- MUTUAL CRITERIA B: USER 2's preferences match USER 1's profile (MUTUALITY)
        AND P1.gender = PR2.pref_gender          -- U1's gender matches U2's preference
        AND P1.age BETWEEN PR2.pref_min_age AND PR2.pref_max_age -- U1's age is in U2's preferred range
        AND P1.motive = PR2.pref_motive          -- U1's motive matches U2's preference
        
    LIMIT 1;
    """
    params = (user_id, user_location)
    
    try:
        cur.execute(query, params)
        match = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    return match