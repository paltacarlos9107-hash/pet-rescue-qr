from flask import Flask, render_template, request, jsonify
import sqlite3
import uuid
import qrcode
from io import BytesIO
import base64
import smtplib
from email.mime.text import MIMEText
import os
from database import init_db, add_pet, get_pet

# -------- DETECTAR ENTORNO --------
IS_PRODUCTION = os.environ.get("RENDER") is not None

# -------- CONFIGURACIÓN DE CORREO --------
if IS_PRODUCTION:
    # En Render: usa variables de entorno (seguro)
    EMAIL_USER = "paltacarlos9107@gmail.com"
    EMAIL_PASS = "nivtfemzgtsqbfau"
else:
    # En local: usa valores directos (¡solo para pruebas!)
    EMAIL_USER = "paltacarlos9107@gmail.com"          # ← TU CORREO
    EMAIL_PASS = "nivtfemzgtsqbfau"              # ← TU CONTRASEÑA DE APLICACIÓN

# Validación
if not EMAIL_USER or not EMAIL_PASS:
    raise ValueError("❌ Faltan credenciales de correo. Configura EMAIL_USER y EMAIL_PASS.")

# -------- APP FLASK --------
app = Flask(__name__)
init_db()

# -------- RUTAS --------
@app.route("/")
def home():
    return render_template("register.html")

@app.route("/register", methods=["POST"])
def register():
    name = request.form["name"]
    breed = request.form.get("breed", "")
    description = request.form.get("description", "")
    owner_email = request.form["email"]
    pet_id = str(uuid.uuid4())[:8].upper()
    add_pet(pet_id, name, breed, description, owner_email)

    # Generar URL del QR (HTTP en local, HTTPS en Render)
    if IS_PRODUCTION:
        qr_url = f"https://pet-rescue-qr.onrender.com/pet/{pet_id}"
    else:
        qr_url = f"{request.url_root}pet/{pet_id}"

    # Generar imagen QR
    qr_img = qrcode.make(qr_url)
    buffered = BytesIO()
    qr_img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode()

    return render_template("register.html", qr=qr_base64, qr_url=qr_url)

@app.route("/pet/<pet_id>")
def pet_page(pet_id):
    pet = get_pet(pet_id)
    if not pet:
        return "<h2>❌ Mascota no encontrada o ya fue reportada como encontrada.</h2>", 404
    return render_template("pet.html", pet=pet)

@app.route("/report", methods=["POST"])
def report_location():
    data = request.get_json()
    pet_id = data.get("pet_id")
    lat = data.get("lat")
    lng = data.get("lng")
    pet = get_pet(pet_id)
    if not pet:
        return jsonify({"error": "Mascota no válida"}), 400

    map_link = f"https://www.google.com/maps?q={lat},{lng}"
    msg = MIMEText(f"¡Tu mascota '{pet['name']}' fue vista!\n\nUbicación:\n{map_link}")
    msg["Subject"] = f"⚠️ ¡{pet['name']} fue encontrado!"
    msg["From"] = EMAIL_USER
    msg["To"] = pet["owner_email"]

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, pet["owner_email"], msg.as_string())
        return jsonify({"status": "success"})
    except Exception as e:
        print("❌ Error al enviar correo:", e)
        return jsonify({"error": "No se pudo notificar al dueño"}), 500

# -------- INICIAR SERVIDOR --------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)