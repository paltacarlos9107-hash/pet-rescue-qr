#!/usr/bin/env python3
"""
Script para crear usuarios en la base de datos de Pet Rescue QR.
Uso:
    python create_user.py correo@ejemplo.com contraseña
Ejemplo:
    python create_user.py voluntario@fundacion.org mipass123
"""

import os
import sys
import argparse

# Asegurar que el script pueda importar database.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from werkzeug.security import generate_password_hash
from database import add_user

def main():
    # Configurar análisis de argumentos
    parser = argparse.ArgumentParser(description="Crear un nuevo usuario en la base de datos.")
    parser.add_argument("email", help="Correo electrónico del nuevo usuario")
    parser.add_argument("password", help="Contraseña del nuevo usuario")
    
    args = parser.parse_args()
    
    email = args.email.strip()
    password = args.password
    
    if not email or not password:
        print("❌ Error: Debes proporcionar un correo y una contraseña.")
        sys.exit(1)
    
    if "@" not in email:
        print("❌ Error: El correo no es válido.")
        sys.exit(1)
    
    # Generar hash de la contraseña
    password_hash = generate_password_hash(password)
    
    try:
        # Agregar usuario a la base de datos
        add_user(email, password_hash)
        print(f"✅ Usuario creado exitosamente:")
        print(f"   Correo: {email}")
        print(f"   Contraseña: {'*' * len(password)} (guarda esta contraseña en un lugar seguro)")
    except Exception as e:
        print(f"❌ Error al crear el usuario: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()