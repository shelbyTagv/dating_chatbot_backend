from dotenv import load_dotenv
load_dotenv()

import os
import mysql.connector.pooling
import random
from openai import OpenAI

# -------------------------------------------------
# CONNECTION POOL
# -------------------------------------------------
_pool = None

def conn():
    global _pool
    if not _pool:
        _pool = mysql.connector.pooling.MySQLConnectionPool(
            pool_name="dating_pool",
            pool_size=12,
            host=os.getenv("MYSQLHOST"),
            user=os.getenv("MYSQLUSER"),
            password=os.getenv("MYSQLPASSWORD"),
            database=os.getenv("MYSQL_DATABASE"),
            port=int(os.getenv("MYSQL_PORT", 3306)),
        )
    return _pool.get_connection()

# -------------------------------------------------
# INIT DB (DROP & CREATE TABLES)
# -------------------------------------------------
def init_db():
    c = conn()
    cur = c.cursor()
    try:
        # Drop tables if they exist
        cur.execute("DROP TABLE IF EXISTS profiles")
        cur.execute("DROP TABLE IF EXISTS users")

        # Create users table
        cur.execute("""
        CREATE TABLE users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            phone VARCHAR(20) UNIQUE NOT NULL,
            gender VARCHAR(10),
            chat_state VARCHAR(20),
            is_active BOOLEAN DEFAULT 0,
            subscription_expiry DATETIME
        )
        """)

        # Create profiles table with user_id as PRIMARY KEY (no duplicate)
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
        c.commit()
    finally:
        cur.close()
        c.close()

# -------------------------------------------------
# USER FUNCTIONS
# -------------------------------------------------
def get_user_by_phone(phone):
    c = conn()
    cur = c.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM users WHERE phone=%s", (phone,))
        return cur.fetchone()
    finally:
        cur.close()
        c.close()

def create_new_user(phone):
    c = conn()
    cur = c.cursor(dictionary=True)
    try:
        cur.execute(
            "INSERT INTO users (phone, chat_state) VALUES (%s,'NEW')",
            (phone,)
        )
        c.commit()
        cur.execute("SELECT * FROM users WHERE id=LAST_INSERT_ID()")
        return cur.fetchone()
    finally:
        cur.close()
        c.close()

def set_state(uid, state):
    c = conn()
    cur = c.cursor()
    try:
        cur.execute("UPDATE users SET chat_state=%s WHERE id=%s", (state, uid))
        c.commit()
    finally:
        cur.close()
        c.close()

def set_gender(uid, gender):
    c = conn()
    cur = c.cursor()
    try:
        cur.execute("UPDATE users SET gender=%s WHERE id=%s", (gender, uid))
        c.commit()
    finally:
        cur.close()
        c.close()

# -------------------------------------------------
# PROFILE FUNCTIONS
# -------------------------------------------------
def ensure_profile(uid):
    c = conn()
    cur = c.cursor()
    try:
        cur.execute("""
            INSERT INTO profiles (user_id)
            VALUES (%s)
            ON DUPLICATE KEY UPDATE user_id=user_id
        """, (uid,))
        c.commit()
    finally:
        cur.close()
        c.close()

def reset_profile(uid):
    c = conn()
    cur = c.cursor()
    try:
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
    finally:
        cur.close()
        c.close()

def update_profile(uid, field, value):
    c = conn()
    cur = c.cursor()
    try:
        cur.execute(f"UPDATE profiles SET {field}=%s WHERE user_id=%s", (value, uid))
        c.commit()
    finally:
        cur.close()
        c.close()

# -------------------------------------------------
# MATCHING
# -------------------------------------------------
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

def get_matches(uid, limit=2):
    c = conn()
    cur = c.cursor(dictionary=True, buffered=True)  # ✅ buffered to avoid unread result
    try:
        # Fetch current user's profile
        cur.execute("""
            SELECT p.*, u.gender
            FROM profiles p
            JOIN users u ON u.id = p.user_id
            WHERE p.user_id = %s
        """, (uid,))
        me = cur.fetchone()
        if not me:
            return []

        # Fetch all other candidates
        cur.execute("""
            SELECT p.*, u.gender
            FROM profiles p
            JOIN users u ON u.id = p.user_id
            WHERE p.user_id != %s
              AND p.intent IS NOT NULL
              AND p.age IS NOT NULL
        """, (uid,))
        candidates = cur.fetchall()
    finally:
        cur.close()
        c.close()

    if not candidates:
        return []

    # Format and randomize matches
    data = []
    for c in candidates:
        data.append({
            "id": c["user_id"],
            "name": c["name"],
            "age": c["age"],
            "location": c["location"],
            "intent": c["intent"],
            "gender": c["gender"]
        })

    random.shuffle(data)
    for d in data:
        d["score"] = random.randint(50, 100)

    return data[:limit]
