# create_user.py
import os
import sys
from werkzeug.security import generate_password_hash
from database import add_user

if len(sys.argv) != 3:
    print("Uso: python create_user.py correo@ejemplo.com contraseña")
    sys.exit(1)

email = sys.argv[1]
password = sys.argv[2]
password_hash = generate_password_hash(password)

add_user(email, password_hash)
print(f"✅ Usuario creado: {email}")