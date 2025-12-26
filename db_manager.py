import os
import mysql.connector.pooling
from datetime import datetime

_pool = None

def conn():
    global _pool
    if not _pool:
        _pool = mysql.connector.pooling.MySQLConnectionPool(
            pool_name="microhub_pool",
            pool_size=10,
            host=os.getenv("MYSQLHOST"),
            user=os.getenv("MYSQLUSER"),
            password=os.getenv("MYSQLPASSWORD"),
            database=os.getenv("MYSQL_DATABASE"),
            port=int(os.getenv("MYSQL_PORT", 3306)),
        )
    return _pool.get_connection()

def init_db():
    c = conn()
    cur = c.cursor()
    cur.execute("SET FOREIGN_KEY_CHECKS = 0")
    cur.execute("DROP TABLE IF EXISTS applications, users")
    cur.execute("SET FOREIGN_KEY_CHECKS = 1")

    cur.execute("""
        CREATE TABLE users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            phone VARCHAR(20) UNIQUE,
            name VARCHAR(100),
            chat_state VARCHAR(50) DEFAULT 'START',
            selected_product VARCHAR(50),
            selected_branch VARCHAR(50)
        )
    """)

    cur.execute("""
        CREATE TABLE applications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            national_id VARCHAR(30),
            selfie_url TEXT,
            amount_requested VARCHAR(50),
            business_desc TEXT,
            status VARCHAR(20) DEFAULT 'PENDING',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    c.commit()
    cur.close()
    c.close()
    print("✅ Database Initialized")

def get_user(phone):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE phone=%s", (phone,))
    res = cur.fetchone()
    cur.close()
    c.close()
    return res

def create_user(phone):
    c = conn()
    cur = c.cursor()
    cur.execute("INSERT INTO users (phone) VALUES (%s)", (phone,))
    c.commit()
    cur.close()
    c.close()
    return get_user(phone)

def update_user(uid, field, value):
    c = conn()
    cur = c.cursor()
    # Safe update using parameterization
    query = f"UPDATE users SET {field}=%s WHERE id=%s"
    cur.execute(query, (value, uid))
    c.commit()
    cur.close()
    c.close()

# Add this to your update_user function or ensure your 'users' table has these columns:
# Columns needed: selfie_url (TEXT), amount (VARCHAR), biz_desc (TEXT)

def save_application(uid, data):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        INSERT INTO applications (user_id, national_id, selfie_url, amount_requested, business_desc)
        VALUES (%s, %s, %s, %s, %s)
    """, (uid, data['id'], data['selfie'], data['amt'], data['desc']))
    c.commit()
    cur.close()
    c.close()