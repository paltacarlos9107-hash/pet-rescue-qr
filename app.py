from flask import Flask, render_template, request, jsonify, redirect
import sqlite3
import uuid
import qrcode
from io import BytesIO
import base64
import os
import requests
import cloudinary
import cloudinary.uploader
from database import init_db, add_pet, get_pet

# -------------------------------------------------
# CONFIGURACIÓN DE ENTORNO (¡DEBE IR AL INICIO!)
# -------------------------------------------------
IS_PRODUCTION = os.environ.get("RENDER") is not None

# Configurar Cloudinary solo en producción
if IS_PRODUCTION:
    cloudinary.config(
        cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
        api_key=os.environ.get("CLOUDINARY_API_KEY"),
        api_secret=os.environ.get("CLOUDINARY_API_SECRET")
    )

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
        if request.headers.get('X-Forwarded-Proto', 'http') != 'https':
            return redirect(request.url.replace('http://', 'https://'), code=301)

# -------------------------------------------------
# MIDDLEWARE: Cabeceras de seguridad
# -------------------------------------------------
@app.after_request
def add_security_headers(response):
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
    owner_phone = request.form.get("phone", "")

    # Subir foto si se proporciona
    photo_url = None
    if "photo" in request.files:
        photo = request.files["photo"]
        if photo and photo.filename:
            try:
                upload_result = cloudinary.uploader.upload(
                    photo,
                    folder="pet_rescue_qr",
                    resource_type="image"
                )
                photo_url = upload_result["secure_url"]
            except Exception as e:
                print("📷 Error al subir foto:", e)

    pet_id = str(uuid.uuid4())[:8].upper()
    add_pet(pet_id, name, breed, description, owner_email, owner_phone, photo_url)

    # Generar URL del QR (siempre HTTPS en Render)
    if IS_PRODUCTION:
        qr_url = f"https://{request.host}/pet/{pet_id}"
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
            return jsonify({"error": "Dueño no tiene correo registrado"}), 400

        map_link = f"https://www.google.com/maps?q={lat},{lng}"

        SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
        SENDGRID_FROM_EMAIL = os.environ.get("SENDGRID_FROM_EMAIL", "paltacarlos9107@gmail.com")

        if SENDGRID_API_KEY:
            payload = {
                "personalizations": [
                    {
                        "to": [{"email": owner_email}],
                        "subject": f"⚠️ ¡{pet['name']} fue encontrado!"
                    }
                ],
                "from": {"email": SENDGRID_FROM_EMAIL},
                "content": [
                    {
                        "type": "text/plain",
                        "value": f"¡Tu mascota '{pet['name']}' fue vista!\n\nUbicación:\n{map_link}"
                    }
                ]
            }

            headers = {
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json"
            }

            response = requests.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers=headers,
                json=payload
            )

            if response.status_code != 202:
                print(f"📧 SendGrid error ({response.status_code}): {response.text}")
                return jsonify({"error": "No se pudo enviar la notificación"}), 500
        else:
            print(f"📧 [LOCAL] Simulando correo a {owner_email}")
            print(f"📍 Ubicación: {map_link}")

        return jsonify({"status": "success"})

    except Exception as e:
        print("❌ Error en /report:", repr(e))
        return jsonify({"error": "Error interno del servidor"}), 500

# -------------------------------------------------
# EJECUTAR SERVIDOR
# -------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = "0.0.0.0"
    debug = not IS_PRODUCTION
    app.run(host=host, port=port, debug=debug)