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
    try:
        # Obtener datos del formulario
        name = request.form.get("name", "").strip()
        breed = request.form.get("breed", "").strip()
        description = request.form.get("description", "").strip()
        owner_email = request.form.get("email", "").strip()
        owner_phone = request.form.get("phone", "").strip()

        # Validación básica
        if not name or not owner_email:
            return render_template(
                "register.html",
                error="El nombre de la mascota y el correo son obligatorios."
            )

        # Subir foto si se proporciona
        photo_url = None
        if "photo" in request.files:
            photo = request.files["photo"]
            if photo and photo.filename:
                try:
                    # Subir a Cloudinary (solo si está configurado)
                    if IS_PRODUCTION:
                        upload_result = cloudinary.uploader.upload(
                            photo,
                            folder="pet_rescue_qr",
                            resource_type="image",
                            timeout=30
                        )
                        photo_url = upload_result.get("secure_url")
                    else:
                        # En local, no subimos, pero podrías guardar en /tmp si quieres
                        photo_url = None
                except Exception as e:
                    print("📷 Advertencia: error al subir foto a Cloudinary:", str(e))
                    # No detenemos el registro si falla la foto
                    photo_url = None

        # Generar ID único
        pet_id = str(uuid.uuid4())[:8].upper()

        # Guardar en base de datos
        add_pet(pet_id, name, breed, description, owner_email, owner_phone, photo_url)

        # Generar URL del QR
        if IS_PRODUCTION:
            qr_url = f"https://{request.host}/pet/{pet_id}"
        else:
            qr_url = f"{request.url_root}pet/{pet_id}"

        # Generar código QR como imagen base64
        qr_img = qrcode.make(qr_url)
        buffered = BytesIO()
        qr_img.save(buffered, format="PNG")
        qr_base64 = base64.b64encode(buffered.getvalue()).decode()

        # Mostrar resultado
        return render_template(
            "register.html",
            qr=qr_base64,
            qr_url=qr_url,
            success=f"¡Mascota '{name}' registrada! Usa el QR para ayudar a encontrarla."
        )

    except Exception as e:
        print("❌ Error en /register:", repr(e))
        return render_template(
            "register.html",
            error="Ocurrió un error al registrar la mascota. Inténtalo de nuevo."
        )

# -------------------------------------------------
# EJECUTAR SERVIDOR
# -------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = "0.0.0.0"
    debug = not IS_PRODUCTION
    app.run(host=host, port=port, debug=debug)