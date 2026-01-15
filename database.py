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
    """Crea la tabla de usuarios si no existe, con soporte para administradores."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    if IS_PRODUCTION:
        # PostgreSQL
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Asegurar que la columna is_admin exista (para tablas existentes)
        try:
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE")
        except Exception as e:
            print("⚠️ Advertencia al agregar is_admin en PostgreSQL:", e)
    else:
        # SQLite
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Asegurar que la columna is_admin exista (para tablas existentes)
        try:
            cur.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0")
        except Exception as e:
            # En SQLite, si la columna ya existe, se lanza una excepción
            pass
    
    conn.commit()
    cur.close()
    conn.close()

def init_db():
    """Inicializa todas las tablas de la base de datos."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Tabla de mascotas
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
        # Asegurar columnas adicionales
        try:
            cur.execute("ALTER TABLE pets ADD COLUMN IF NOT EXISTS owner_phone TEXT")
            cur.execute("ALTER TABLE pets ADD COLUMN IF NOT EXISTS photo_url TEXT")
        except Exception as e:
            print("⚠️ Advertencia al agregar columnas en pets:", e)
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
    
    # 👇 ¡Importante! Inicializar la tabla de usuarios con soporte de admin
    init_users_table()

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

def make_user_admin(email):
    """Convierte un usuario en administrador."""
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("UPDATE users SET is_admin = TRUE WHERE email = %s", (email,))
    else:
        cur.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
    conn.commit()
    cur.close()
    conn.close()

# -------------------------------------------------
# Funciones existentes para mascotas (sin cambios)
# -------------------------------------------------

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

def get_all_pets(owner_email=None):
    """Obtiene todas las mascotas o solo las de un usuario específico."""
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        if owner_email:
            cur.execute("SELECT * FROM pets WHERE owner_email = %s ORDER BY id DESC", (owner_email,))
        else:
            cur.execute("SELECT * FROM pets ORDER BY id DESC")
    else:
        if owner_email:
            cur.execute("SELECT * FROM pets WHERE owner_email = ? ORDER BY rowid DESC", (owner_email,))
        else:
            cur.execute("SELECT * FROM pets ORDER BY rowid DESC")
    pets = cur.fetchall()
    cur.close()
    conn.close()
    return pets