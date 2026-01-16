from flask import Flask, render_template, request, jsonify, redirect, session
import uuid
import qrcode
from io import BytesIO
import base64
import os
import requests
import cloudinary
import cloudinary.uploader
from database import init_db, add_pet, get_pet, get_user_by_email, make_user_admin, get_all_pets, delete_pet, update_user_session_token
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import secrets
import time

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
# DECORADORES
# -------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        
        # Verificar token de sesión
        user = get_user_by_email(session["user_email"])
        if not user or user.get("session_token") != session.get("session_token"):
            session.clear()
            return redirect("/login?message=invalid_session")
        
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        
        # Verificar token de sesión
        user = get_user_by_email(session["user_email"])
        if not user or user.get("session_token") != session.get("session_token"):
            session.clear()
            return redirect("/login?message=invalid_session")
        
        if not user.get("is_admin"):
            return "<h2>Acceso denegado</h2>", 403
        
        return f(*args, **kwargs)
    return decorated_function

def check_inactivity(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("logged_in"):
            # Verificar token primero
            user = get_user_by_email(session["user_email"])
            if not user or user.get("session_token") != session.get("session_token"):
                session.clear()
                return redirect("/login?message=invalid_session")
            
            last_activity = session.get("last_activity", 0)
            if time.time() - last_activity > 900:  # 15 minutos
                session.clear()
                return redirect("/login?message=timeout")
        
        if session.get("logged_in"):
            session["last_activity"] = time.time()
        
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
# RUTAS DE LOGIN
# -------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    message = ""
    if request.args.get("message") == "timeout":
        message = "Tu sesión expiró por inactividad. Por favor, inicia sesión nuevamente."
    
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        
        user = get_user_by_email(email)
        if not user:
            message = "Correo o contraseña incorrectos."
        elif not check_password_hash(user["password_hash"], password):
            message = "Correo o contraseña incorrectos."
        else:
            # Verificar si ya hay una sesión activa
            if user.get("session_token"):
                message = "Ya hay una sesión activa para esta cuenta. No se permiten múltiples accesos simultáneos."
            else:
                # Generar y guardar token de sesión
                session_token = secrets.token_urlsafe(32)
                update_user_session_token(email, session_token)
                
                session["logged_in"] = True
                session["user_email"] = email
                session["session_token"] = session_token
                session["last_activity"] = time.time()
                
                return redirect("/")
    
    return render_template("login.html", error=message)

@app.route("/logout")
def logout():
    # Limpiar token en la base de datos si hay un usuario logueado
    if session.get("logged_in") and session.get("user_email"):
        try:
            update_user_session_token(session["user_email"], None)
        except Exception as e:
            print(f"Error al limpiar token de sesión: {e}")
    
    # Limpiar sesión del navegador
    session.clear()
    return redirect("/login")

# -------------------------------------------------
# RUTAS PROTEGIDAS
# -------------------------------------------------
@app.route("/")
@login_required
@check_inactivity
def home():
    return render_template("register.html")

@app.route("/register", methods=["POST"])
@login_required
@check_inactivity
def register():
    try:
        name = request.form.get("name", "").strip()
        breed = request.form.get("breed", "").strip()
        description = request.form.get("description", "").strip()
        owner_name = request.form.get("owner_name", "").strip()
        owner_email = session["user_email"]
        owner_phone = request.form.get("phone", "").strip()

        if not name or not owner_name:
            return render_template("register.html", error="El nombre de la mascota y del dueño son obligatorios.")

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
        add_pet(pet_id, name, breed, description, owner_name, owner_email, owner_phone, photo_url)

        # Guardar datos en sesión para mostrar en la página de éxito
        session['registration_success'] = f"¡Mascota '{name}' registrada! Usa el QR para ayudar a encontrarla."
        
        if IS_PRODUCTION:
            session['qr_url'] = f"https://{request.host}/pet/{pet_id}"
        else:
            session['qr_url'] = f"{request.url_root}pet/{pet_id}"

        qr_img = qrcode.make(session['qr_url'])
        buffered = BytesIO()
        qr_img.save(buffered, format="PNG")
        session['qr_base64'] = base64.b64encode(buffered.getvalue()).decode()

        return redirect("/register/success")

    except Exception as e:
        print("❌ Error en /register:", repr(e))
        return render_template("register.html", error="Ocurrió un error. Inténtalo de nuevo.")

@app.route("/register/success")
@login_required
@check_inactivity
def register_success():
    success = session.pop('registration_success', None)
    qr = session.pop('qr_base64', None)
    qr_url = session.pop('qr_url', None)
    
    if not success:
        return redirect("/")
        
    return render_template("register.html", success=success, qr=qr, qr_url=qr_url)

# -------------------------------------------------
# RUTAS PÚBLICAS
# -------------------------------------------------

@app.route("/my-pets")
@login_required
@check_inactivity
def my_pets():
    """Muestra solo las mascotas del usuario actual."""
    from database import get_all_pets
    pets = get_all_pets(owner_email=session["user_email"])
    return render_template("my_pets.html", pets=pets)

@app.route("/pet/<pet_id>")
def pet_page(pet_id):
    pet = get_pet(pet_id)
    if not pet:
        return "<h2>❌ Mascota no encontrada o ya fue reportada.</h2>", 404

    # Generar el QR para esta mascota
    if IS_PRODUCTION:
        qr_url = f"https://{request.host}/pet/{pet_id}"
    else:
        qr_url = f"{request.url_root}pet/{pet_id}"

    qr_img = qrcode.make(qr_url)
    buffered = BytesIO()
    qr_img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode()

    return render_template("pet.html", pet=pet, qr=qr_base64, qr_url=qr_url)

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

        clean_phone = ''.join(filter(str.isdigit, owner_phone))
        if not clean_phone.startswith('57') and len(clean_phone) == 10:
            clean_phone = '57' + clean_phone

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
# RUTA DE ADMINISTRACIÓN
# -------------------------------------------------
@app.route("/admin", methods=["GET", "POST"])
@admin_required
@check_inactivity
def admin_panel():
    from database import get_db_connection, add_user, get_all_pets
    
    message = ""
    
    if request.method == "POST":
        action = request.form.get("action")
        
        # Crear/eliminar usuarios
        if action in ["create", "delete"]:
            email = request.form.get("email", "").strip()
            password = request.form.get("password", "")
            
            if action == "create" and email and password:
                try:
                    add_user(email, generate_password_hash(password))
                    message = f"✅ Usuario {email} creado."
                except Exception as e:
                    message = f"❌ Error: {str(e)}"
                
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
        
        # Eliminar mascota
        elif action == "delete_pet":
            pet_id = request.form.get("pet_id", "").strip()
            if pet_id:
                if delete_pet(pet_id):
                    message = f"✅ Mascota {pet_id} eliminada."
                else:
                    message = f"⚠️ Mascota {pet_id} no encontrada."

    # Obtener datos actualizados
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("SELECT email, is_admin FROM users ORDER BY created_at DESC")
    else:
        cur.execute("SELECT email, is_admin FROM users ORDER BY rowid DESC")
    users = cur.fetchall()
    cur.close()
    conn.close()

    pets = get_all_pets()  # Todas las mascotas

    return render_template("admin.html", users=users, pets=pets, message=message)

# -------------------------------------------------
# SERVIDOR
# -------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=not IS_PRODUCTION)