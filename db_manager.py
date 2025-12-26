import os
import mysql.connector.pooling
from datetime import datetime

_pool = None

def conn():
    global _pool
    if not _pool:
        # Railway environment variables
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
    """
    Drops existing tables and recreates them to ensure 
    the schema is perfectly aligned with the chatbot logic.
    """
    c = conn()
    cur = c.cursor()
    try:
        print("🛠 Resetting Database...")
        # Disable foreign key checks to drop tables safely
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        cur.execute("DROP TABLE IF EXISTS applications")
        cur.execute("DROP TABLE IF EXISTS users")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")

        # Table 1: Users (Tracks state and temporary application data)
        cur.execute("""
            CREATE TABLE users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                phone VARCHAR(20) UNIQUE,
                name VARCHAR(100), -- Used to store ID Number temporarily
                chat_state VARCHAR(50) DEFAULT 'START',
                selected_product VARCHAR(100),
                amount VARCHAR(50),
                selfie_url TEXT,
                biz_desc TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table 2: Applications (Final stored loan records)
        cur.execute("""
            CREATE TABLE applications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                product_type VARCHAR(100),
                national_id VARCHAR(30),
                selfie_url TEXT,
                amount_requested VARCHAR(50),
                business_desc TEXT,
                status VARCHAR(20) DEFAULT 'PENDING',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        c.commit()
        print("✅ Database Initialized with all required columns.")
    except Exception as e:
        print(f"❌ Error during DB init: {e}")
    finally:
        cur.close()
        c.close()

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
    """
    Updates specific user fields (chat_state, name, amount, etc.)
    """
    c = conn()
    cur = c.cursor()
    # Parameterized query to prevent SQL Injection
    query = f"UPDATE users SET {field}=%s WHERE id=%s"
    cur.execute(query, (value, uid))
    c.commit()
    cur.close()
    c.close()

def save_final_application(uid):
    """
    Moves data from the 'users' temporary fields into the 'applications' table
    once the user confirms with 'YES'.
    """
    user = None
    c = conn()
    cur = c.cursor(dictionary=True)
    
    # Get the latest data from the user session
    cur.execute("SELECT * FROM users WHERE id=%s", (uid,))
    user = cur.fetchone()
    
    if user:
        cur.execute("""
            INSERT INTO applications (user_id, product_type, national_id, selfie_url, amount_requested, business_desc)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            user['id'], 
            user['selected_product'], 
            user['name'], # We used the 'name' column for National ID
            user['selfie_url'], 
            user['amount'], 
            user['biz_desc']
        ))
        c.commit()
        
    cur.close()
    c.close()