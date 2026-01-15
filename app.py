from flask import Flask, render_template, request, jsonify, redirect, session
import uuid
import qrcode
from io import BytesIO
import base64
import os
import requests
import cloudinary
import cloudinary.uploader
from database import init_db, add_pet, get_pet, get_user_by_email
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import secrets

# -------------------------------------------------
# CONFIGURACIÓN DE ENTORNO
# -------------------------------------------------
IS_PRODUCTION = os.environ.get("RENDER") is not None

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
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(16))
init_db()

# -------------------------------------------------
# DECORADOR: Requiere login
# -------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

# -------------------------------------------------
# MIDDLEWARE
# -------------------------------------------------
@app.before_request
def force_https():
    if IS_PRODUCTION:
        if request.headers.get('X-Forwarded-Proto', 'http') != 'https':
            return redirect(request.url.replace('http://', 'https://'), code=301)

@app.after_request
def add_security_headers(response):
    response.headers["Permissions-Policy"] = "geolocation=(*), microphone=(), camera=()"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer-when-downgrade"
    return response

# -------------------------------------------------
# RUTAS DE LOGIN (MULTIUSUARIO)
# -------------------------------------------------
# ¡¡¡ RUTA TEMPORAL PARA CREAR USUARIO EN RENDER !!!
# Eliminar después de usar
@app.route("/create-first-user")
def create_first_user():
    from werkzeug.security import generate_password_hash
    from database import add_user
    email = "carlospalta91@hotmail.com"          # ← Cámbialo
    password = "cc1144150851"      # ← Cámbialo
    add_user(email, generate_password_hash(password))
    return f"✅ Usuario creado: {email}. ¡Elimina esta ruta ahora!"

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        
        user = get_user_by_email(email)
        if user and check_password_hash(user["password_hash"], password):
            session["logged_in"] = True
            session["user_email"] = email
            return redirect("/")
        else:
            return render_template("login.html", error="Correo o contraseña incorrectos.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    session.pop("user_email", None)
    return redirect("/login")

# -------------------------------------------------
# RUTAS PROTEGIDAS
# -------------------------------------------------
@app.route("/")
@login_required
def home():
    return render_template("register.html")

@app.route("/register", methods=["POST"])
@login_required
def register():
    try:
        name = request.form.get("name", "").strip()
        breed = request.form.get("breed", "").strip()
        description = request.form.get("description", "").strip()
        owner_email = request.form.get("email", "").strip()
        owner_phone = request.form.get("phone", "").strip()

        if not name or not owner_email:
            return render_template("register.html", error="El nombre y correo son obligatorios.")

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

# -------------------------------------------------
# RUTAS PÚBLICAS
# -------------------------------------------------
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
        if data is None:
            return jsonify({"error": "No se recibieron datos"}), 400

        pet_id = data.get("pet_id")
        lat = data.get("lat")
        lng = data.get("lng")

        if not pet_id or lat is None or lng is None:
            return jsonify({"error": "Faltan datos requeridos"}), 400

        pet = get_pet(pet_id)
        if not pet:
            return jsonify({"error": "Mascota no encontrada"}), 400

        owner_phone = pet.get("owner_phone")
        if not owner_phone:
            return jsonify({"error": "Dueño no tiene número de teléfono registrado"}), 400

        # Limpiar el número: solo dígitos (WhatsApp requiere formato internacional sin + ni espacios)
        clean_phone = ''.join(filter(str.isdigit, owner_phone))
        if not clean_phone.startswith('57') and len(clean_phone) == 10:
            # Asumir Colombia si no tiene prefijo
            clean_phone = '57' + clean_phone

        # Crear enlace de WhatsApp
        map_link = f"https://www.google.com/maps?q={lat},{lng}"
        message = f"¡Tu mascota '{pet['name']}' fue vista!\n\nUbicación:\n{map_link}"
        whatsapp_url = f"https://wa.me/{clean_phone}?text={requests.utils.quote(message)}"

        return jsonify({"status": "success", "whatsapp_url": whatsapp_url})

    except Exception as e:
        print("❌ Error en /report:", repr(e))
        return jsonify({"error": "Error interno"}), 500
@app.route("/thanks")
def thanks():
    return render_template("thanks.html")

# -------------------------------------------------
# SERVIDOR
# -------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=not IS_PRODUCTION)