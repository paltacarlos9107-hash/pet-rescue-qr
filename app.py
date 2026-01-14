from flask import Flask, render_template, request, jsonify, redirect
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
# CONFIGURACIÓN DE ENTORNO
# -------------------------------------------------
IS_PRODUCTION = os.environ.get("RENDER") is not None

if IS_PRODUCTION:
    # Configurar Cloudinary
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
    try:
        name = request.form.get("name", "").strip()
        breed = request.form.get("breed", "").strip()
        description = request.form.get("description", "").strip()
        owner_email = request.form.get("email", "").strip()
        owner_phone = request.form.get("phone", "").strip()

        if not name or not owner_email:
            return render_template("register.html", error="El nombre y correo son obligatorios.")

        # Subir foto a Cloudinary
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
                    photo_url = upload_result.get("secure_url")
                except Exception as e:
                    print("📷 Error al subir foto:", str(e))

        pet_id = str(uuid.uuid4())[:8].upper()
        add_pet(pet_id, name, breed, description, owner_email, owner_phone, photo_url)

        # Generar QR
        if IS_PRODUCTION:
            qr_url = f"https://{request.host}/pet/{pet_id}"
        else:
            qr_url = f"{request.url_root}pet/{pet_id}"

        qr_img = qrcode.make(qr_url)
        buffered = BytesIO()
        qr_img.save(buffered, format="PNG")
        qr_base64 = base64.b64encode(buffered.getvalue()).decode()

        return render_template(
            "register.html",
            qr=qr_base64,
            qr_url=qr_url,
            success=f"¡Mascota '{name}' registrada! Usa el QR para ayudar a encontrarla."
        )

    except Exception as e:
        print("❌ Error en /register:", repr(e))
        return render_template("register.html", error="Ocurrió un error. Inténtalo de nuevo.")

@app.route("/pet/<pet_id>")
def pet_page(pet_id):
    pet = get_pet(pet_id)
    if not pet:
        return "<h2>❌ Mascota no encontrada o ya fue reportada.</h2>", 404
    return render_template("pet.html", pet=pet)

@app.route("/report", methods=["POST"])
def report_location():
    try:
        data = request.get_json()
        if not 
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

        # Enviar con SendGrid
        SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
        SENDGRID_FROM_EMAIL = os.environ.get("SENDGRID_FROM_EMAIL", "paltacarlos9107@gmail.com")

        if not SENDGRID_API_KEY:
            print("⚠️ SENDGRID_API_KEY no configurada")
            return jsonify({"error": "Notificación no disponible"}), 500

        payload = {
            "personalizations": [{"to": [{"email": owner_email}]}],
            "from": {"email": SENDGRID_FROM_EMAIL},
            "subject": f"⚠️ ¡{pet['name']} fue encontrado!",
            "content": [{"type": "text/plain", "value": f"¡Tu mascota '{pet['name']}' fue vista!\n\nUbicación:\n{map_link}"}]
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

        if response.status_code == 202:
            return jsonify({"status": "success"})
        else:
            print("📧 SendGrid error:", response.text)
            return jsonify({"error": "No se pudo notificar"}), 500

    except Exception as e:
        print("❌ Error en /report:", repr(e))
        return jsonify({"error": "Error interno"}), 500

# -------------------------------------------------
# EJECUTAR SERVIDOR
# -------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = "0.0.0.0"
    debug = not IS_PRODUCTION
    app.run(host=host, port=port, debug=debug)