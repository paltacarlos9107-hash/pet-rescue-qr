import os

# Detectar entorno
IS_PRODUCTION = os.environ.get("RENDER") is not None

def get_db_connection():
    if IS_PRODUCTION:
        import psycopg2
        from psycopg2.extras import RealDictCursor
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

def init_users_table():
    """Crea la tabla de usuarios si no existe."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    if IS_PRODUCTION:
        # PostgreSQL
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        # SQLite
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
    conn.commit()
    cur.close()
    conn.close()

def add_user(email, password_hash):
    """Agrega un nuevo usuario a la base de datos."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    if IS_PRODUCTION:
        cur.execute(
            "INSERT INTO users (email, password_hash) VALUES (%s, %s)",
            (email, password_hash)
        )
    else:
        cur.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email, password_hash)
        )
    
    conn.commit()
    cur.close()
    conn.close()

def get_user_by_email(email):
    """Obtiene un usuario por su correo electrónico."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    if IS_PRODUCTION:
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    else:
        cur.execute("SELECT * FROM users WHERE email = ?", (email,))
    
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

def init_db():
    """Inicializa todas las tablas de la base de datos."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    if IS_PRODUCTION:
        # PostgreSQL - Tabla pets
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
        # Asegurar columnas adicionales
        try:
            cur.execute("ALTER TABLE pets ADD COLUMN IF NOT EXISTS owner_phone TEXT")
            cur.execute("ALTER TABLE pets ADD COLUMN IF NOT EXISTS photo_url TEXT")
        except Exception as e:
            print("⚠️ Advertencia al agregar columnas en pets:", e)
    else:
        # SQLite - Tabla pets
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

    # Inicializar tabla de usuarios
    init_users_table()

def add_pet(pet_id, name, breed, description, owner_email, owner_phone=None, photo_url=None):
    """Agrega una mascota a la base de datos."""
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
    """Obtiene una mascota por su ID."""
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