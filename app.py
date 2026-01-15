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

@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin_panel():
    from database import get_db_connection
    
    # Obtener todos los usuarios
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("SELECT email, is_admin FROM users ORDER BY created_at DESC")
    else:
        cur.execute("SELECT email, is_admin FROM users ORDER BY created_at DESC")
    users = cur.fetchall()
    cur.close()
    conn.close()

    message = ""
    
    if request.method == "POST":
        action = request.form.get("action")
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        
        if action == "create" and email and password:
            from werkzeug.security import generate_password_hash
            add_user(email, generate_password_hash(password))
            message = f"✅ Usuario {email} creado."
            
        elif action == "delete" and email:
            conn = get_db_connection()
            cur = conn.cursor()
            if IS_PRODUCTION:
                cur.execute("DELETE FROM users WHERE email = %s", (email,))
            else:
                cur.execute("DELETE FROM users WHERE email = ?", (email,))
            conn.commit()
            deleted = cur.rowcount > 0
            cur.close()
            conn.close()
            if deleted:
                message = f"✅ Usuario {email} eliminado."
            else:
                message = f"⚠️ Usuario {email} no encontrado."
    
    return render_template("admin.html", users=users, message=message)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        # Verificar si es admin
        user = get_user_by_email(session["user_email"])
        if not user or not user.get("is_admin"):
            return "<h2>Acceso denegado</h2>", 403
        return f(*args, **kwargs)
    return decorated_function

# ¡¡¡ RUTA TEMPORAL - ELIMINAR DESPUÉS !!!
@app.route("/make-me-admin")
def make_me_admin():
    from database import make_user_admin
    make_user_admin("carlospalta91@hotmail.com")  # ← ¡Cambia esto por tu correo real!
    return "✅ ¡Ahora eres administrador! Elimina esta ruta."

# ¡¡¡ RUTA TEMPORAL PARA AGREGAR USUARIOS- ELIMINAR DESPUÉS !!!
@app.route("/add-user/<email>/<password>")
def add_user_temp(email, password):
    from werkzeug.security import generate_password_hash
    from database import add_user
    add_user(email, generate_password_hash(password))
    return f"✅ Usuario {email} creado. ¡Elimina esta ruta ahora!"

# ¡¡¡ RUTA TEMPORAL PARA ELIMINAR USUARIOS - ELIMINAR DESPUÉS !!!
@app.route("/delete-user/<email>")
def delete_user_temp(email):
    from database import get_db_connection
    conn = get_db_connection()
    cur = conn.cursor()
    if os.environ.get("RENDER"):
        cur.execute("DELETE FROM users WHERE email = %s", (email,))
    else:
        cur.execute("DELETE FROM users WHERE email = ?", (email,))
    conn.commit()
    deleted = cur.rowcount > 0
    cur.close()
    conn.close()
    if deleted:
        return f"✅ Usuario {email} eliminado."
    else:
        return f"⚠️ Usuario {email} no encontrado."

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