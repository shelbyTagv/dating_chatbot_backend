from dotenv import load_dotenv
load_dotenv()

import os
import random
import mysql.connector.pooling
from datetime import datetime

# -------------------------------------------------
# DB CONNECTION POOL
# -------------------------------------------------
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
# INIT (Drops and Creates)
# -------------------------------------------------
def init_db():
    c = conn()
    cur = c.cursor()

    # 1. Users Table (No drop, only create if missing)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            phone VARCHAR(20) UNIQUE,
            chat_state VARCHAR(32) DEFAULT 'NEW',
            is_paid TINYINT DEFAULT 0,
            paid_at DATETIME
        )
    """)

    # 2. Profiles Table (Corrected with Picture)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            user_id INT PRIMARY KEY,
            gender VARCHAR(10),
            name VARCHAR(100),
            age INT,
            location VARCHAR(100),
            intent VARCHAR(50),
            preferred_gender VARCHAR(10),
            age_min INT,
            age_max INT,
            contact_phone VARCHAR(20),
            picture TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # 3. Payments Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            reference VARCHAR(50) UNIQUE,
            poll_url TEXT,
            paid TINYINT DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            paid_at DATETIME,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    c.commit()
    cur.close()
    c.close()
    print("✅ Database connection verified. Tables checked/created.")

# -------------------------------------------------
# MATCHING LOGIC
# -------------------------------------------------
import random

def get_matches(user_id):
    c = conn()
    cur = c.cursor(dictionary=True)

    # 1. Get current user's profile
    cur.execute("SELECT * FROM profiles WHERE user_id=%s", (user_id,))
    user = cur.fetchone()
    if not user or not user.get('intent'):
        cur.close()
        c.close()
        return []

    user_type = user.get('user_type', 'CITIZEN')
    user_intent = user['intent'].lower()
    user_location = (user.get('location') or "").strip().lower()
    
    # 2. Fetch potential candidates (Opposite Gender + Completed Profile)
    # We exclude the user themselves and only pick those in the matching state
    cur.execute("""
        SELECT * FROM profiles 
        WHERE user_id != %s 
        AND gender = %s 
        AND chat_state = 'AWAITING_MATCHES'
    """, (user_id, user.get('preferred_gender')))
    
    candidates = cur.fetchall()
    cur.close()
    c.close()

    valid_matches = []

    for cand in candidates:
        # Safety fix: Handle NoneType for intent
        c_intent = (cand.get('intent') or "").lower()
        c_type = cand.get('user_type', 'CITIZEN')
        
        # --- BRANCH 1: UNIVERSITY STUDENT LOGIC ---
        if user_type == 'STUDENT':
            # Students ONLY match with other Students
            if c_type == 'STUDENT':
                # Check if candidate is at the university the user is targeting
                # AND user matches the university the candidate is targeting
                same_uni_path = (cand.get('university') == user.get('target_university'))
                
                # Check Student Intents (Must be identical: e.g., both want 'chills')
                if same_uni_path and user_intent == c_intent:
                    valid_matches.append(cand)
            continue # Move to next candidate, don't run citizen logic for students

        # --- BRANCH 2: CITIZEN LOGIC (Original Rules) ---
        if c_type == 'CITIZEN':
            match_found = False

            # RULE A: Sugar Mummy + Benten
            if (user_intent == "sugar mummy" and c_intent == "benten"):
                if user['age'] > cand['age']: match_found = True
            elif (user_intent == "benten" and c_intent == "sugar mummy"):
                if cand['age'] > user['age']: match_found = True

            # RULE B: Sugar Daddy + Girlfriend 
            elif (user_intent == "sugar daddy" and c_intent == "girlfriend"):
                if user['age'] > cand['age']: match_found = True
            elif (user_intent == "girlfriend" and c_intent == "sugar daddy"):
                if cand['age'] > user['age']: match_found = True

            # RULE C: Boyfriend + Girlfriend or Casual/Friends
            elif (user_intent == c_intent) or \
                 (user_intent in ["boyfriend", "girlfriend"] and c_intent in ["boyfriend", "girlfriend"]):
                # Standard Age Range Check
                if (user['age_min'] <= cand['age'] <= user['age_max']) and \
                   (cand['age_min'] <= user['age'] <= cand['age_max']):
                    match_found = True

            if match_found:
                valid_matches.append(cand)

    # 3. LOCATION SORTING & SAMPLING
    if valid_matches:
        local_matches = []
        other_matches = []
        
        for m in valid_matches:
            cand_location = (m.get('location') or "").strip().lower()
            # If student, location is less important than Uni, but we still check
            if user_location and (user_location in cand_location or cand_location in user_location):
                local_matches.append(m)
            else:
                other_matches.append(m)
        
        random.shuffle(local_matches)
        random.shuffle(other_matches)
        
        # Return top 4 results, prioritizing local ones
        return (local_matches + other_matches)[:4]
    
    return []
# -------------------------------------------------
# USER & PROFILE HELPERS
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
    cur.execute("INSERT INTO users (phone, chat_state) VALUES (%s, 'NEW')", (phone,))
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

def ensure_profile(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT user_id FROM profiles WHERE user_id=%s", (uid,))
    if not cur.fetchone():
        cur.execute("INSERT INTO profiles (user_id) VALUES (%s)", (uid,))
        c.commit()
    cur.close()
    c.close()

def update_profile(user_id, field, value):
    c = conn()
    cur = c.cursor()
    # Ensure your SQL table has these columns!
    query = f"UPDATE profiles SET {field} = %s WHERE user_id = %s"
    cur.execute(query, (value, user_id))
    c.commit()
    cur.close()
    c.close()

def reset_profile(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        UPDATE profiles SET
            gender=NULL, name=NULL, age=NULL, location=NULL, intent=NULL,
            preferred_gender=NULL, age_min=NULL, age_max=NULL, 
            contact_phone=NULL, picture=NULL
        WHERE user_id = %s
    """, (uid,))
    c.commit()
    cur.close()
    c.close()

# -------------------------------------------------
# PAYMENT HELPERS
# -------------------------------------------------
def create_payment(uid, reference, poll_url):
    c = conn()
    cur = c.cursor()
    cur.execute("INSERT INTO payments (user_id, reference, poll_url) VALUES (%s, %s, %s)", 
                (uid, reference, poll_url))
    c.commit()
    cur.close()
    c.close()

def mark_payment_paid(reference):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE payments SET paid = 1, paid_at = %s WHERE reference = %s",
                (datetime.utcnow(), reference))
    c.commit()
    cur.close()
    c.close()

def activate_user(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE users SET is_paid=1, paid_at=%s WHERE id=%s",
                (datetime.utcnow(), uid))
    c.commit()
    cur.close()
    c.close()

def reset_user_payment(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE users SET is_paid = 0 WHERE id = %s", (uid,))
    c.commit()
    cur.close()
    c.close()

def get_pending_payments():
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM payments WHERE paid = 0")
    rows = cur.fetchall()
    cur.close()
    c.close()
    return rows

def get_user_phone(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT phone FROM users WHERE id=%s", (uid,))
    row = cur.fetchone()
    cur.close()
    c.close()
    return row[0] if row else None

def get_profile_name(uid):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT name FROM profiles WHERE user_id = %s", (uid,))
    row = cur.fetchone()
    cur.close()
    c.close()
    return row[0] if row and row[0] else "Customer"

def get_pending_payments_for_user(uid):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM payments WHERE user_id=%s AND paid=0 ORDER BY created_at DESC", (uid,))
    rows = cur.fetchall()
    cur.close()
    c.close()
    return rows

def get_profile(uid):
    c = conn() # Using your existing conn() function
    cur = c.cursor()
    # Explicitly naming columns to ensure we know exactly which index they are in
    cur.execute("SELECT name, age, location, intent, contact_phone, picture FROM profiles WHERE user_id = %s", (uid,))
    row = cur.fetchone()
    cur.close()
    c.close()
    
    if row:
        return {
            "name": row[0],
            "age": row[1],
            "location": row[2],
            "intent": row[3],
            "contact_phone": row[4],
            "picture": row[5] # This is the photo URL/ID
        }
    return None