import os
import mysql.connector.pooling
from datetime import datetime

_pool = None

def conn():
    global _pool
    if not _pool:
        _pool = mysql.connector.pooling.MySQLConnectionPool(
            pool_name="ip4sbps_pool",
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
    # Drop old dating tables
    cur.execute("SET FOREIGN_KEY_CHECKS = 0")
    cur.execute("DROP TABLE IF EXISTS profiles, users, payments, documents")
    cur.execute("SET FOREIGN_KEY_CHECKS = 1")

    # Applicants Table
    cur.execute("""
        CREATE TABLE applicants (
            id INT AUTO_INCREMENT PRIMARY KEY,
            phone VARCHAR(20) UNIQUE,
            chat_state VARCHAR(50) DEFAULT 'NEW',
            first_name VARCHAR(100),
            surname VARCHAR(100),
            national_id VARCHAR(30),
            address TEXT,
            mode_of_entry VARCHAR(50),
            cohort VARCHAR(50),
            email VARCHAR(100),
            gender VARCHAR(10),
            highest_qual VARCHAR(100),
            exp_years INT,
            level_taught VARCHAR(50),
            special_needs TEXT,
            is_paid TINYINT DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Documents Table
    cur.execute("""
        CREATE TABLE documents (
            id INT AUTO_INCREMENT PRIMARY KEY,
            applicant_id INT,
            doc_type VARCHAR(50), -- 'ID', 'O_LEVEL', 'A_LEVEL', 'PROFESSIONAL'
            file_url TEXT,
            FOREIGN KEY (applicant_id) REFERENCES applicants(id) ON DELETE CASCADE
        )
    """)

    # Payments Table
    cur.execute("""
        CREATE TABLE payments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            applicant_id INT,
            reference VARCHAR(50) UNIQUE,
            poll_url TEXT,
            amount DECIMAL(10,2),
            currency VARCHAR(10),
            paid TINYINT DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (applicant_id) REFERENCES applicants(id) ON DELETE CASCADE
        )
    """)
    c.commit()
    cur.close()
    c.close()

# --- Helpers ---
def get_applicant(phone):
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM applicants WHERE phone=%s", (phone,))
    res = cur.fetchone()
    cur.close()
    c.close()
    return res

def create_applicant(phone):
    c = conn()
    cur = c.cursor()
    cur.execute("INSERT INTO applicants (phone) VALUES (%s)", (phone,))
    c.commit()
    cur.close()
    c.close()
    return get_applicant(phone)

def update_applicant(aid, field, value):
    c = conn()
    cur = c.cursor()
    cur.execute(f"UPDATE applicants SET {field}=%s WHERE id=%s", (value, aid))
    c.commit()
    cur.close()
    c.close()

def save_document(aid, doc_type, url):
    c = conn()
    cur = c.cursor()
    cur.execute("INSERT INTO documents (applicant_id, doc_type, file_url) VALUES (%s, %s, %s)", (aid, doc_type, url))
    c.commit()
    cur.close()
    c.close()

def set_state(aid, state):
    update_applicant(aid, "chat_state", state)

def create_payment(aid, ref, poll, amt, curr):
    c = conn()
    cur = c.cursor()
    cur.execute("INSERT INTO payments (applicant_id, reference, poll_url, amount, currency) VALUES (%s, %s, %s, %s, %s)", 
                (aid, ref, poll, amt, curr))
    c.commit()
    cur.close()
    c.close()

def mark_as_paid(ref):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE payments SET paid=1 WHERE reference=%s", (ref,))
    # Get applicant_id from ref to activate them
    cur.execute("SELECT applicant_id FROM payments WHERE reference=%s", (ref,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE applicants SET is_paid=1 WHERE id=%s", (row[0],))
    c.commit()
    cur.close()
    c.close()