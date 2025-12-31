import os
import mysql.connector.pooling
from datetime import datetime

_pool = None

# -------------------------------------------------
# DATABASE CONNECTION
# -------------------------------------------------
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


# -------------------------------------------------
# INITIALIZE DATABASE (RUN MANUALLY, NOT ON IMPORT)
# -------------------------------------------------
def reset_db():
    c = conn()
    cur = c.cursor()
    try:
        print("Dropping and recreating tables...")

        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        cur.execute("DROP TABLE IF EXISTS applications")
        cur.execute("DROP TABLE IF EXISTS users")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")

        cur.execute("""
            CREATE TABLE users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                phone VARCHAR(20) UNIQUE NOT NULL,
                full_name VARCHAR(100),
                age INT,
                gender VARCHAR(20),
                address VARCHAR(200),
                national_id VARCHAR(30),
                id_photo_url TEXT,
                chat_state VARCHAR(50) DEFAULT 'START',
                selected_product VARCHAR(100),
                amount VARCHAR(50),
                biz_desc TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE applications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                product_type VARCHAR(100),
                national_id VARCHAR(30),
                id_photo_url TEXT,
                amount_requested VARCHAR(50),
                business_desc TEXT,
                status VARCHAR(20) DEFAULT 'PENDING',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        c.commit()
        print("Database reset complete")

    except Exception as e:
        print(f"DB reset error: {e}")
    finally:
        cur.close()
        c.close()


# -------------------------------------------------
# USER CRUD
# -------------------------------------------------
def get_user(phone):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE phone=%s", (phone,))
    user = cur.fetchone()
    cur.close()
    c.close()
    return user


def create_user(phone):
    c = conn()
    cur = c.cursor()
    cur.execute("INSERT INTO users (phone) VALUES (%s)", (phone,))
    c.commit()
    cur.close()
    c.close()
    return get_user(phone)


# -------------------------------------------------
# SAFE FIELD UPDATE (STRICT)
# -------------------------------------------------
ALLOWED_FIELDS = {
    "full_name",
    "age",
    "gender",
    "address",
    "national_id",
    "id_photo_url",
    "chat_state",
    "selected_product",
    "amount",
    "biz_desc",
}

def update_user(uid, field, value):
    if field not in ALLOWED_FIELDS:
        raise ValueError(f"Invalid field update attempt: {field}")

    c = conn()
    cur = c.cursor()
    cur.execute(
        f"UPDATE users SET {field}=%s WHERE id=%s",
        (value, uid)
    )
    c.commit()
    cur.close()
    c.close()


# -------------------------------------------------
# FINAL APPLICATION SAVE
# -------------------------------------------------
def save_final_application(uid):
    c = conn()
    cur = c.cursor(dictionary=True)

    cur.execute("SELECT * FROM users WHERE id=%s", (uid,))
    user = cur.fetchone()

    if not user:
        cur.close()
        c.close()
        return

    cur.execute("""
        INSERT INTO applications (
            user_id,
            product_type,
            national_id,
            id_photo_url,
            amount_requested,
            business_desc
        )
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        user["id"],
        user["selected_product"],
        user["national_id"],
        user["id_photo_url"],
        user["amount"],
        user["biz_desc"]
    ))

    c.commit()
    cur.close()
    c.close()
