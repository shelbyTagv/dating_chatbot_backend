from dotenv import load_dotenv
load_dotenv()

import os
import mysql.connector.pooling
from datetime import datetime
from math import radians, cos, sin, asin, sqrt

INTENT_COMPATIBILITY = {
    "boyfriend": "girlfriend",
    "girlfriend": "boyfriend",
    "sugar mummy": "benten",
    "benten": "sugar mummy",
    "sugar daddy": "sugar baby",
    "sugar baby": "sugar daddy",
    "1 night stand": "1 night stand",
    "friends": "friends",
    "just vibes": "just vibes",
}

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
# PAYMENTS (PESEPAY)
# -------------------------------------------------
def create_payment(uid, transaction_id, amount):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        INSERT INTO payments (user_id, reference, paid)
        VALUES (%s, %s, 0)
    """, (uid, transaction_id))
    c.commit()
    cur.close()
    c.close()

def mark_payment_paid(transaction_id):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        UPDATE payments
        SET paid = 1, paid_at = %s
        WHERE reference = %s
    """, (datetime.utcnow(), transaction_id))
    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# USER
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
    cur.execute("INSERT INTO users (phone) VALUES (%s)", (phone,))
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

def get_user_phone(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT phone FROM users WHERE id=%s", (uid,))
    row = cur.fetchone()
    cur.close()
    c.close()
    return row[0] if row else None

# -------------------------------------------------
# PROFILE
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

def update_profile(uid, field, value):
    c = conn()
    cur = c.cursor()
    cur.execute(f"UPDATE profiles SET {field}=%s WHERE user_id=%s", (value, uid))
    c.commit()
    cur.close()
    c.close()

def reset_profile(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        UPDATE profiles SET
            gender=NULL,name=NULL,age=NULL,location=NULL,
            intent=NULL,preferred_gender=NULL,
            age_min=NULL,age_max=NULL,
            contact_phone=NULL,temp_contact_phone=NULL
        WHERE user_id=%s
    """, (uid,))
    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# MATCHING
# -------------------------------------------------
def opposite_gender(g):
    return "female" if g == "male" else "male"

def gender_match(user, cand):
    return cand["gender"] == opposite_gender(user["gender"]) and cand["preferred_gender"] == user["gender"]

def age_match(user, cand):
    return (
        user["age_min"] <= cand["age"] <= user["age_max"] and
        cand["age_min"] <= user["age"] <= cand["age_max"]
    )

def intent_match(user, cand):
    return INTENT_COMPATIBILITY.get(user["intent"]) == cand["intent"]

def get_matches(uid):
    c = conn()
    cur = c.cursor(dictionary=True)

    cur.execute("SELECT * FROM profiles WHERE user_id=%s", (uid,))
    user = cur.fetchone()

    cur.execute("SELECT * FROM profiles WHERE user_id != %s", (uid,))
    candidates = cur.fetchall()

    matches = []
    for cand in candidates:
        if gender_match(user, cand) and age_match(user, cand) and intent_match(user, cand):
            matches.append(cand)

    cur.close()
    c.close()
    return matches[:3]
