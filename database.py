import os
import psycopg2
from psycopg2.extras import RealDictCursor

IS_PRODUCTION = os.environ.get("RENDER") is not None

def get_db_connection():
    if IS_PRODUCTION:
        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            database=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASS"],
            port=os.environ.get("DB_PORT", "5432"),
            cursor_factory=RealDictCursor
        )
    else:
        import sqlite3
        conn = sqlite3.connect("pets.db")
        conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                breed TEXT,
                description TEXT,
                owner_email TEXT NOT NULL,
                owner_phone TEXT,
                photo_url TEXT,
                found BOOLEAN DEFAULT FALSE
            )
        """)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                breed TEXT,
                description TEXT,
                owner_email TEXT NOT NULL,
                owner_phone TEXT,
                photo_url TEXT,
                found BOOLEAN DEFAULT 0
            )
        """)
    conn.commit()
    cur.close()
    conn.close()

def add_pet(pet_id, name, breed, description, owner_email, owner_phone=None, photo_url=None):
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute(
            "INSERT INTO pets (id, name, breed, description, owner_email, owner_phone, photo_url) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (pet_id, name, breed, description, owner_email, owner_phone, photo_url)
        )
    else:
        cur.execute(
            "INSERT INTO pets (id, name, breed, description, owner_email, owner_phone, photo_url) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (pet_id, name, breed, description, owner_email, owner_phone, photo_url)
        )
    conn.commit()
    cur.close()
    conn.close()

def get_pet(pet_id):
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("SELECT * FROM pets WHERE id = %s AND found = FALSE", (pet_id,))
    else:
        cur.execute("SELECT * FROM pets WHERE id = ? AND found = 0", (pet_id,))
    pet = cur.fetchone()
    cur.close()
    conn.close()
    return pet