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
    """Crea la tabla de usuarios si no existe, con soporte para administradores y estado activo."""
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
                is_active BOOLEAN DEFAULT TRUE,
                session_token TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Asegurar que todas las columnas existan
        columns_to_add = [
            ("session_token", "TEXT"),
            ("is_active", "BOOLEAN DEFAULT TRUE")
        ]
        for col_name, col_type in columns_to_add:
            try:
                cur.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
            except Exception as e:
                print(f"⚠️ Advertencia al agregar {col_name} en users:", e)
    else:
        # SQLite
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin BOOLEAN DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                session_token TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Asegurar que todas las columnas existan
        try:
            cur.execute("ALTER TABLE users ADD COLUMN session_token TEXT")
        except Exception as e:
            # Columna ya existe
            pass
        
        try:
            cur.execute("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1")
        except Exception as e:
            # Columna ya existe
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
                owner_name TEXT,
                owner_email TEXT NOT NULL,
                owner_phone TEXT,
                photo_url TEXT,
                city TEXT,
                address TEXT,
                found BOOLEAN DEFAULT FALSE,
                is_registered BOOLEAN DEFAULT FALSE,
                registration_password TEXT
            )
        """)
        # Asegurar columnas adicionales
        columns_to_add = [
            ("owner_name", "TEXT"),
            ("owner_phone", "TEXT"),
            ("photo_url", "TEXT"),
            ("city", "TEXT"),
            ("address", "TEXT"),
            ("found", "BOOLEAN DEFAULT FALSE"),
            ("is_registered", "BOOLEAN DEFAULT FALSE"),
            ("registration_password", "TEXT")
        ]
        for col_name, col_type in columns_to_add:
            try:
                cur.execute(f"ALTER TABLE pets ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
            except Exception as e:
                print(f"⚠️ Advertencia al agregar {col_name} en pets:", e)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                breed TEXT,
                description TEXT,
                owner_name TEXT,
                owner_email TEXT NOT NULL,
                owner_phone TEXT,
                photo_url TEXT,
                city TEXT,
                address TEXT,
                found BOOLEAN DEFAULT 0,
                is_registered BOOLEAN DEFAULT 0,
                registration_password TEXT
            )
        """)
        # Asegurar columnas adicionales en SQLite
        columns_to_add = ["owner_name", "owner_phone", "photo_url", "city", "address", "found", "is_registered", "registration_password"]
        for col_name in columns_to_add:
            try:
                if col_name in ["found", "is_registered"]:
                    cur.execute(f"ALTER TABLE pets ADD COLUMN {col_name} BOOLEAN DEFAULT 0")
                else:
                    cur.execute(f"ALTER TABLE pets ADD COLUMN {col_name} TEXT")
            except Exception as e:
                # Columna ya existe
                pass
    
    conn.commit()
    cur.close()
    conn.close()
    
    # 👇 ¡Importante! Inicializar la tabla de usuarios con soporte de admin y tokens
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
    """Obtiene un usuario por su correo."""
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("SELECT email, password_hash, is_admin, session_token, is_active FROM users WHERE email = %s", (email,))
    else:
        cur.execute("SELECT email, password_hash, is_admin, session_token, is_active FROM users WHERE email = ?", (email,))
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

def update_user_session_token(email, token):
    """Actualiza el token de sesión del usuario."""
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("UPDATE users SET session_token = %s WHERE email = %s", (token, email))
    else:
        cur.execute("UPDATE users SET session_token = ? WHERE email = ?", (token, email))
    conn.commit()
    cur.close()
    conn.close()

def clear_user_session_token(email):
    """Limpia el token de sesión de un usuario."""
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("UPDATE users SET session_token = NULL WHERE email = %s", (email,))
    else:
        cur.execute("UPDATE users SET session_token = NULL WHERE email = ?", (email,))
    conn.commit()
    cur.close()
    conn.close()

def is_token_valid(user):
    """Verifica si el token del usuario es válido."""
    return user and user.get("session_token") is not None

def add_pet(pet_id, name, breed, description, owner_name, owner_email, owner_phone, photo_url, city, address, is_registered=False, registration_password=None):
    """Registra una nueva mascota."""
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("""
            INSERT INTO pets (id, name, breed, description, owner_name, owner_email, owner_phone, photo_url, city, address, found, is_registered, registration_password)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (pet_id, name, breed, description, owner_name, owner_email, owner_phone, photo_url, city, address, False, is_registered, registration_password))
    else:
        cur.execute("""
            INSERT INTO pets (id, name, breed, description, owner_name, owner_email, owner_phone, photo_url, city, address, found, is_registered, registration_password)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (pet_id, name, breed, description, owner_name, owner_email, owner_phone, photo_url, city, address, False, is_registered, registration_password))
    conn.commit()
    cur.close()
    conn.close()

def get_pet(pet_id):
    """Obtiene una mascota por su ID."""
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("SELECT * FROM pets WHERE id = %s", (pet_id,))
    else:
        cur.execute("SELECT * FROM pets WHERE id = ?", (pet_id,))
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

def delete_pet(pet_id):
    """Elimina una mascota por su ID."""
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("DELETE FROM pets WHERE id = %s", (pet_id,))
    else:
        cur.execute("DELETE FROM pets WHERE id = ?", (pet_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    cur.close()
    conn.close()
    return deleted

def toggle_user_active_status(email, is_active):
    """Activa o desactiva una cuenta de usuario e invalida su sesión."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    if is_active:
        # Activar usuario
        if IS_PRODUCTION:
            cur.execute("UPDATE users SET is_active = TRUE WHERE email = %s", (email,))
        else:
            cur.execute("UPDATE users SET is_active = 1 WHERE email = ?", (email,))
    else:
        # Desactivar usuario e invalidar sesión
        if IS_PRODUCTION:
            cur.execute("UPDATE users SET is_active = FALSE, session_token = NULL WHERE email = %s", (email,))
        else:
            cur.execute("UPDATE users SET is_active = 0, session_token = NULL WHERE email = ?", (email,))
    
    conn.commit()
    cur.close()
    conn.close()

def get_user_by_email_full(email):
    """Obtiene un usuario completo por su correo (incluyendo is_active)."""
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("SELECT email, password_hash, is_admin, session_token, is_active FROM users WHERE email = %s", (email,))
    else:
        cur.execute("SELECT email, password_hash, is_admin, session_token, is_active FROM users WHERE email = ?", (email,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user