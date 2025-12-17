from dotenv import load_dotenv
load_dotenv()

import os, random
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
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT,
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
# USER MANAGEMENT
# -------------------------------------------------
def get_or_create_user(phone):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE phone=%s", (phone,))
    u = cur.fetchone()
    if not u:
        # Create new user and always a new row
        cur.execute("INSERT INTO users (phone, chat_state) VALUES (%s,'NEW')", (phone,))
        c.commit()
        cur.execute("SELECT * FROM users WHERE id=LAST_INSERT_ID()")
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

def set_gender(uid, gender):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE users SET gender=%s WHERE id=%s", (gender, uid))
    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# PROFILE MANAGEMENT
# -------------------------------------------------
def create_profile(uid, name="", age=None, location="", intent="", preferred_gender=None, age_min=None, age_max=None, contact_phone=""):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        INSERT INTO profiles (user_id, name, age, location, intent, preferred_gender, age_min, age_max, contact_phone)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (uid, name, age, location, intent, preferred_gender, age_min, age_max, contact_phone))
    c.commit()
    cur.close()
    c.close()

def upsert_profile(uid, field, value):
    """
    Updates last incomplete profile if exists, otherwise creates a new profile row.
    """
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM profiles WHERE user_id=%s ORDER BY id DESC LIMIT 1", (uid,))
    profile = cur.fetchone()

    if not profile or all(v is not None and v != "" for k,v in profile.items() if k not in ["id","user_id"]):
        # Last profile filled or doesn't exist -> create new
        create_profile(uid)
        cur.execute("SELECT * FROM profiles WHERE user_id=%s ORDER BY id DESC LIMIT 1", (uid,))
        profile = cur.fetchone()

    cur.execute(f"UPDATE profiles SET {field}=%s WHERE id=%s", (value, profile["id"]))
    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# MATCHMAKING
# -------------------------------------------------
def get_matches(uid, limit=2):
    c = conn()
    cur = c.cursor(dictionary=True)

    # Fetch current user's latest profile
    cur.execute("""
        SELECT u.gender as my_gender, u.id as user_id, p.*
        FROM profiles p
        JOIN users u ON u.id = p.user_id
        WHERE u.id=%s
        ORDER BY p.id DESC
        LIMIT 1
    """, (uid,))
    me = cur.fetchone()
    if not me:
        return []

    my_gender = me["my_gender"].lower()
    my_age = me["age"]
    my_intent = me["intent"].lower()
    my_pref_gender = me["preferred_gender"].lower()

    # Define intent match mapping
    intent_pairs = {
        "girlfriend": "boyfriend",
        "boyfriend": "girlfriend",
        "sugar mummy": "benten",
        "benten": "sugar mummy",
        "sugar daddy": "sugar baby",
        "sugar baby": "sugar daddy",
        "1 night stand": "1 night stand",
        "friend": "friend",
        "just vibes": "just vibes"
    }

    # Fetch all potential matches
    cur.execute("""
        SELECT p.*, u.gender as user_gender, u.id as user_id
        FROM profiles p
        JOIN users u ON u.id = p.user_id
        WHERE u.id != %s
          AND p.age_min IS NOT NULL
          AND p.age_max IS NOT NULL
          AND p.preferred_gender IS NOT NULL
          AND p.intent IS NOT NULL
          AND u.gender IS NOT NULL
    """, (uid,))
    candidates = cur.fetchall()
    cur.close()
    c.close()

    # Filter candidates based on all 3 checks
    matches = []
    for c in candidates:
        cand_age_min = c["age_min"]
        cand_age_max = c["age_max"]
        cand_intent = c["intent"].lower()
        cand_gender = c["user_gender"].lower()
        cand_pref_gender = c["preferred_gender"].lower()

        # 1️⃣ Age check: current user's age in candidate's preferred age range
        if not (cand_age_min <= my_age <= cand_age_max):
            continue

        # 2️⃣ Intent check: candidate's intent matches the mapping
        if intent_pairs.get(my_intent) != cand_intent:
            continue

        # 3️⃣ Preferred gender check: mutual preference
        if my_pref_gender != "any" and cand_gender != my_pref_gender:
            continue
        if cand_pref_gender != "any" and my_gender != cand_pref_gender:
            continue

        matches.append(c)

    # Randomize the matches
    random.shuffle(matches)

    # Limit to the requested number of matches
    limited_matches = matches[:limit]

    # Add info about more matches
    for m in limited_matches:
        m["more_available"] = len(matches) > limit

    return limited_matches


# -------------------------------------------------
# TRANSACTIONS
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

def get_transaction_by_reference(ref):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM transactions WHERE reference=%s", (ref,))
    tx = cur.fetchone()
    cur.close()
    c.close()
    return tx

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

def unlock_full_profiles(uid):
    # Placeholder if you want extra functionality after payment
    pass
