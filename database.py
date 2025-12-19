import os
import psycopg2
from psycopg2.extras import RealDictCursor

# Detectar entorno
IS_PRODUCTION = os.environ.get("RENDER") is not None

def get_db_connection():
    if IS_PRODUCTION:
        # Usar PostgreSQL en Render
        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            database=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASS"],
            port=os.environ.get("DB_PORT", "5432"),
            cursor_factory=RealDictCursor
        )
    else:
        # En local, puedes seguir usando SQLite si quieres
        import sqlite3
        conn = sqlite3.connect("pets.db")
        conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    if IS_PRODUCTION:
        # PostgreSQL
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                breed TEXT,
                description TEXT,
                owner_email TEXT NOT NULL,
                found BOOLEAN DEFAULT FALSE
            )
        """)
    else:
        # SQLite
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                breed TEXT,
                description TEXT,
                owner_email TEXT NOT NULL,
                found BOOLEAN DEFAULT 0
            )
        """)
    
    conn.commit()
    cur.close()
    conn.close()

def add_pet(pet_id, name, breed, description, owner_email):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO pets (id, name, breed, description, owner_email) VALUES (%s, %s, %s, %s, %s)",
        (pet_id, name, breed, description, owner_email)
    )
    conn.commit()
    cur.close()
    conn.close()

def get_pet(pet_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM pets WHERE id = %s AND found = FALSE", (pet_id,))
    pet = cur.fetchone()
    cur.close()
    conn.close()
    return pet