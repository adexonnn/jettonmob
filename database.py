# database.py
import sqlite3
import os
from config import DB_PATH

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

def init_db():
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            tokens REAL,
            monitoring INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS last_price (
            id INTEGER PRIMARY KEY, 
            price REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS banned_users (
            user_id INTEGER PRIMARY KEY
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO last_price (id, price) VALUES (1, 0)")
    conn.commit()

def get_last_price():
    cursor.execute("SELECT price FROM last_price WHERE id=1")
    row = cursor.fetchone()
    return row[0] if row else 0

def update_last_price(price):
    cursor.execute("INSERT OR REPLACE INTO last_price (id, price) VALUES (1, ?)", (price,))
    conn.commit()

def is_banned(user_id):
    cursor.execute("SELECT user_id FROM banned_users WHERE user_id=?", (user_id,))
    return cursor.fetchone() is not None

def block_user(user_id):
    cursor.execute("INSERT OR REPLACE INTO banned_users (user_id) VALUES (?)", (user_id,))
    conn.commit()

init_db()