from flask import Flask, render_template, request, jsonify, redirect
import sqlite3
import uuid
import qrcode
from io import BytesIO
import base64
import smtplib
from email.mime.text import MIMEText
import os
from database import init_db, add_pet, get_pet

# -------------------------------------------------
# CONFIGURACIÓN DE ENTORNO
# -------------------------------------------------
IS_PRODUCTION = os.environ.get("RENDER") is not None

if IS_PRODUCTION:
    EMAIL_USER = os.environ.get("EMAIL_USER")       
    EMAIL_PASS = os.environ.get("EMAIL_PASS") 
    RENDER_APP_URL = "https://pet-rescue-qr-t3bm.onrender.com"
else:
    # ⚠️ Solo para desarrollo local — ¡NO subir credenciales a GitHub!
    EMAIL_USER = "paltacarlos9107@gmail.com"
    EMAIL_PASS = "mktdkkgdxwyapglx"             
    RENDER_APP_URL = None

if not EMAIL_USER or not EMAIL_PASS:
    raise RuntimeError("❌ Faltan credenciales de correo. Configura EMAIL_USER y EMAIL_PASS.")

# -------------------------------------------------
# INICIALIZAR APP
# -------------------------------------------------
app = Flask(__name__)
init_db()

# -------------------------------------------------
# MIDDLEWARE: Forzar HTTPS en Render
# -------------------------------------------------
@app.before_request
def force_https():
    if IS_PRODUCTION:
        # Render envía 'X-Forwarded-Proto: https' cuando el tráfico original es HTTPS
        if request.headers.get('X-Forwarded-Proto', 'http') != 'https':
            return redirect(request.url.replace('http://', 'https://'), code=301)

# -------------------------------------------------
# MIDDLEWARE: Cabeceras de seguridad
# -------------------------------------------------
@app.after_request
def add_security_headers(response):
    # Permitir geolocalización en todos los contextos
    response.headers["Permissions-Policy"] = "geolocation=(*), microphone=(), camera=()"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer-when-downgrade"
    return response

# -------------------------------------------------
# RUTAS
# -------------------------------------------------
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

    # Generar URL del QR
    if IS_PRODUCTION:
        qr_url = f"{RENDER_APP_URL}/pet/{pet_id}"
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
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No se recibieron datos"}), 400

        pet_id = data.get("pet_id")
        lat = data.get("lat")
        lng = data.get("lng")

        if not pet_id or lat is None or lng is None:
            return jsonify({"error": "Faltan datos requeridos"}), 400

        pet = get_pet(pet_id)
        if not pet:
            return jsonify({"error": "Mascota no encontrada"}), 400

        owner_email = pet.get("owner_email")
        if not owner_email:
            print(f"⚠️ Mascota {pet_id} no tiene owner_email")
            return jsonify({"error": "Dueño no tiene correo registrado"}), 400

        map_link = f"https://www.google.com/maps?q={lat},{lng}"
        msg = MIMEText(f"¡Tu mascota '{pet['name']}' fue vista!\n\nUbicación:\n{map_link}")
        msg["Subject"] = f"⚠️ ¡{pet['name']} fue encontrado!"
        msg["From"] = EMAIL_USER
        msg["To"] = owner_email

        print(f"📧 Enviando correo a: {owner_email}")

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, owner_email, msg.as_string())

        print("✅ Correo enviado exitosamente")
        return jsonify({"status": "success"})

    except Exception as e:
        print("❌ Error en /report:", repr(e))
        return jsonify({"error": "Error interno del servidor"}), 500

# -------------------------------------------------
# EJECUTAR SERVIDOR
# -------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = "0.0.0.0"  # Obligatorio en Render
    debug = not IS_PRODUCTION
    app.run(host=host, port=port, debug=debug)