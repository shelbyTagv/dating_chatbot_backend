import os
import mysql.connector
import mysql.connector.pooling
from mysql.connector import Error
from datetime import datetime

# -------------------------------------------------
# CONNECTION POOL
# -------------------------------------------------

_pool = None


def _init_pool():
    global _pool
    if _pool is None:
        _pool = mysql.connector.pooling.MySQLConnectionPool(
            pool_name="microhub_pool",
            pool_size=10,
            pool_reset_session=True,
            host=os.getenv("MYSQLHOST"),
            user=os.getenv("MYSQLUSER"),
            password=os.getenv("MYSQLPASSWORD"),
            database=os.getenv("MYSQL_DATABASE"),
            port=int(os.getenv("MYSQL_PORT", 3306)),
        )


def conn():
    if _pool is None:
        _init_pool()
    return _pool.get_connection()


# -------------------------------------------------
# DATABASE RESET (MANUAL USE ONLY)
# -------------------------------------------------

def reset_db():
    c = None
    cur = None
    try:
        c = conn()
        cur = c.cursor()

        print("🛠 Dropping and recreating tables...")

        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        cur.execute("DROP TABLE IF EXISTS applications")
        cur.execute("DROP TABLE IF EXISTS users")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")

        cur.execute("""
            CREATE TABLE users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                phone VARCHAR(20) UNIQUE,
                full_name VARCHAR(100),
                age INT,
                gender VARCHAR(20),
                address VARCHAR(200),
                national_id VARCHAR(30),
                chat_state VARCHAR(50) DEFAULT 'START',
                selected_product VARCHAR(100),
                amount VARCHAR(50),
                selfie_url TEXT,
                biz_desc TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE applications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                product_type VARCHAR(100),
                national_id VARCHAR(30),
                selfie_url TEXT,
                amount_requested VARCHAR(50),
                business_desc TEXT,
                status VARCHAR(20) DEFAULT 'PENDING',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)

        c.commit()
        print("✅ Database reset complete.")

    except Error as e:
        if c:
            c.rollback()
        raise RuntimeError(f"Database reset failed: {e}")

    finally:
        if cur:
            cur.close()
        if c:
            c.close()


# -------------------------------------------------
# USER OPERATIONS
# -------------------------------------------------

def get_user(phone: str):
    c = None
    cur = None
    try:
        c = conn()
        cur = c.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE phone = %s", (phone,))
        return cur.fetchone()
    finally:
        if cur:
            cur.close()
        if c:
            c.close()


def create_user(phone: str):
    c = None
    cur = None
    try:
        c = conn()
        cur = c.cursor()
        cur.execute("INSERT INTO users (phone) VALUES (%s)", (phone,))
        c.commit()
    finally:
        if cur:
            cur.close()
        if c:
            c.close()

    return get_user(phone)


def update_user(user_id: int, field: str, value):
    if field not in {
        "full_name", "age", "gender", "address",
        "national_id", "chat_state", "selected_product",
        "amount", "selfie_url", "biz_desc"
    }:
        raise ValueError("Invalid field update attempt")

    c = None
    cur = None
    try:
        c = conn()
        cur = c.cursor()
        cur.execute(
            f"UPDATE users SET {field} = %s WHERE id = %s",
            (value, user_id)
        )
        c.commit()
    finally:
        if cur:
            cur.close()
        if c:
            c.close()


# -------------------------------------------------
# APPLICATIONS
# -------------------------------------------------

def save_final_application(user_id: int):
    c = None
    cur = None
    try:
        c = conn()
        cur = c.cursor(dictionary=True)

        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()

        if not user:
            raise ValueError("User not found")

        cur.execute("""
            INSERT INTO applications (
                user_id,
                product_type,
                national_id,
                selfie_url,
                amount_requested,
                business_desc
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            user["id"],
            user["selected_product"],
            user["national_id"],
            user["selfie_url"],
            user["amount"],
            user["biz_desc"]
        ))

        c.commit()

    except Error:
        if c:
            c.rollback()
        raise

    finally:
        if cur:
            cur.close()
        if c:
            c.close()
