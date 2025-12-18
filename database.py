import sqlite3
import os

# Nombre del archivo de la base de datos
DB_PATH = "pets.db"

def init_db():
    """
    Crea la base de datos y la tabla 'pets' si no existe.
    """
    if not os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE pets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                breed TEXT,
                description TEXT,
                owner_email TEXT NOT NULL,
                found BOOLEAN DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()
        print("✅ Base de datos creada: pets.db")

def add_pet(pet_id, name, breed, description, owner_email):
    """
    Agrega una nueva mascota a la base de datos.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO pets (id, name, breed, description, owner_email)
        VALUES (?, ?, ?, ?, ?)
    """, (pet_id, name, breed, description, owner_email))
    conn.commit()
    conn.close()
    print(f"✅ Mascota '{name}' registrada con ID: {pet_id}")

def get_pet(pet_id):
    """
    Busca una mascota por su ID y devuelve sus datos (solo si no está marcada como 'encontrada').
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pets WHERE id = ? AND found = 0", (pet_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "id": row[0],
            "name": row[1],
            "breed": row[2],
            "description": row[3],
            "owner_email": row[4],
            "found": bool(row[5])
        }
    return None