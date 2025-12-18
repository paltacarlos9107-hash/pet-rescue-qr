from flask import Flask, render_template, request, jsonify
import sqlite3
import uuid
import qrcode
from io import BytesIO
import base64
import smtplib
from email.mime.text import MIMEText
from database import init_db, add_pet, get_pet

# -------- CONFIGURACIÓN --------
app = Flask(__name__)

# ⚠️ CONFIGURA TU CORREO AQUÍ (ver explicación abajo)
EMAIL_USER = "paltacarlos9107@gmail.com"
EMAIL_PASS = "hvuafcqbjpxeckmb"  # ¡No tu contraseña normal!

# Inicializa la base de datos al iniciar
init_db()

# -------- RUTAS --------
@app.route("/")
def home():
    """Página principal: formulario para registrar mascota."""
    return render_template("register.html")

@app.route("/register", methods=["POST"])
def register():
    """Registra una nueva mascota y muestra su QR."""
    name = request.form["name"]
    breed = request.form.get("breed", "")
    description = request.form.get("description", "")
    owner_email = request.form["email"]

    # Genera un ID único (ej: "K7M2P9Q4")
    pet_id = str(uuid.uuid4())[:8].upper()

    # Guarda en la base de datos
    add_pet(pet_id, name, breed, description, owner_email)

    # Genera el enlace del QR
    qr_url = f"{request.url_root}pet/{pet_id}"

    # Genera el código QR como imagen
    qr_img = qrcode.make(qr_url)
    buffered = BytesIO()
    qr_img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode()

    # Muestra el formulario + QR
    return render_template("register.html", qr=qr_base64, qr_url=qr_url)

@app.route("/pet/<pet_id>")
def pet_page(pet_id):
    """Página que ve quien escanea el QR."""
    pet = get_pet(pet_id)
    if not pet:
        return "<h2>❌ Mascota no encontrada o ya fue reportada como encontrada.</h2>", 404
    return render_template("pet.html", pet=pet)

@app.route("/report", methods=["POST"])
def report_location():
    """Recibe la ubicación del escaneador y notifica al dueño."""
    data = request.get_json()
    pet_id = data.get("pet_id")
    lat = data.get("lat")
    lng = data.get("lng")

    pet = get_pet(pet_id)
    if not pet:
        return jsonify({"error": "Mascota no válida"}), 400

    # Enlace de Google Maps
    map_link = f"https://www.google.com/maps?q={lat},{lng}"

    # Prepara el correo
    msg = MIMEText(f"¡Tu mascota '{pet['name']}' fue vista!\n\nUbicación:\n{map_link}")
    msg["Subject"] = f"⚠️ ¡{pet['name']} fue encontrado!"
    msg["From"] = EMAIL_USER
    msg["To"] = pet["owner_email"]

    # Envía el correo
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, pet["owner_email"], msg.as_string())
        return jsonify({"status": "success"})
    except Exception as e:
        print("❌ Error al enviar correo:", e)
        return jsonify({"error": "No se pudo notificar al dueño"}), 500

# -------- EJECUTAR --------
if __name__ == "__main__":
    app.run(debug=True)