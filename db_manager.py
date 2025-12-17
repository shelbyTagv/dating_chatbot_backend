from dotenv import load_dotenv
load_dotenv()

import os
import mysql.connector.pooling
from datetime import datetime, timedelta
import random
from openai import OpenAI

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
        cur.execute("INSERT INTO users (phone, chat_state) VALUES (%s,'NEW')", (phone,))
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
def create_profile(uid, name="", age=None, location="", intent="", preferred_gender="any", age_min=None, age_max=None, contact_phone=""):
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
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM profiles WHERE user_id=%s ORDER BY id DESC LIMIT 1", (uid,))
    profile = cur.fetchone()

    if profile and (profile.get(field) is None or profile.get(field) == ""):
        cur.execute(f"UPDATE profiles SET {field}=%s WHERE id=%s", (value, profile["id"]))
    else:
        create_profile(uid)
        cur.execute("SELECT * FROM profiles WHERE user_id=%s ORDER BY id DESC LIMIT 1", (uid,))
        profile = cur.fetchone()
        cur.execute(f"UPDATE profiles SET {field}=%s WHERE id=%s", (value, profile["id"]))

    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# AI MATCHMAKING
# -------------------------------------------------
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_KEY)

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

    # Fetch all other candidates
    cur.execute("""
        SELECT p.*, u.gender as user_gender, u.id as user_id
        FROM profiles p
        JOIN users u ON u.id = p.user_id
        WHERE u.id != %s
    """, (uid,))
    candidates = cur.fetchall()
    cur.close()
    c.close()

    if not candidates:
        return []

    # Prepare data for AI
    user_data = {
        "name": me.get("name"),
        "age": me.get("age"),
        "gender": me.get("my_gender"),
        "intent": me.get("intent"),
        "preferred_gender": me.get("preferred_gender"),
        "location": me.get("location")
    }

    candidate_data = []
    for cand in candidates:
        candidate_data.append({
            "id": cand["user_id"],
            "name": cand.get("name"),
            "age": cand.get("age"),
            "gender": cand.get("user_gender"),
            "intent": cand.get("intent"),
            "preferred_gender": cand.get("preferred_gender"),
            "location": cand.get("location")
        })

    # Build prompt for AI
    prompt = f"""
    You are an AI matchmaking assistant.

    User profile:
    {user_data}

    Candidate profiles:
    {candidate_data}

    Based on the user's gender, intent, preferred_gender, and age, rank the candidates in order of best match.
    Only return a JSON list with objects containing "id" and "score" (0-100) for compatibility.
    """

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        result_text = response.choices[0].message.content
    except Exception as e:
        print("AI error:", e)
        # fallback to random matching
        random.shuffle(candidate_data)
        return candidate_data[:limit]

    import json
    try:
        scores = json.loads(result_text)
    except Exception as e:
        print("AI JSON parse error:", e)
        # fallback to random matching
        random.shuffle(candidate_data)
        return candidate_data[:limit]

    # Merge scores with candidate info
    for c in candidate_data:
        for s in scores:
            if s["id"] == c["id"]:
                c["score"] = s["score"]

    candidate_data.sort(key=lambda x: x.get("score", 0), reverse=True)

    top_matches = candidate_data[:limit]
    for m in top_matches:
        m["more_available"] = len(candidate_data) > limit

    return top_matches

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
