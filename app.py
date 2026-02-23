from flask import Flask, render_template, request, jsonify, redirect, session, send_file
import uuid
import qrcode
from io import BytesIO
import base64
import os
import requests
import cloudinary
import cloudinary.uploader
import zipfile
from database import init_db, add_pet, get_pet, get_user_by_email, make_user_admin, get_all_pets, delete_pet, update_user_session_token, clear_user_session_token, toggle_user_active_status, get_db_connection, is_token_valid, add_vaccine, get_vaccines_by_pet, delete_vaccine
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import secrets
import time
from datetime import datetime

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
# FUNCIONES AUXILIARES
# -------------------------------------------------
def clear_user_session():
    try:
        if session.get("logged_in") and session.get("user_email"):
            clear_user_session_token(session["user_email"])
    except Exception as e:
        print(f"Error al limpiar sesión: {e}")
    finally:
        session.clear()

# -------------------------------------------------
# DECORADORES
# -------------------------------------------------
def qr_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("qr_logged_in"):
            return redirect("/qr-login")
        last_activity = session.get("last_activity", 0)
        if time.time() - last_activity > 900:
            session.clear()
            return redirect("/qr-login?message=timeout")
        session["last_activity"] = time.time()
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        user = get_user_by_email(session["user_email"])
        if not user:
            clear_user_session()
            return redirect("/login?message=invalid_session")
        if (user.get("session_token") != session.get("session_token") or
            not is_token_valid(user) or
            not user.get("is_active", True)):
            clear_user_session()
            return redirect("/login?message=account_disabled")
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        user = get_user_by_email(session["user_email"])
        if not user:
            clear_user_session()
            return redirect("/login?message=invalid_session")
        if (user.get("session_token") != session.get("session_token") or
            not is_token_valid(user) or
            not user.get("is_active", True)):
            clear_user_session()
            return redirect("/login?message=account_disabled")
        if not user.get("is_admin"):
            return "<h2>Acceso denegado</h2>", 403
        return f(*args, **kwargs)
    return decorated_function

def check_inactivity(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("logged_in"):
            user = get_user_by_email(session["user_email"])
            if not user:
                clear_user_session()
                return redirect("/login?message=invalid_session")
            if (user.get("session_token") != session.get("session_token") or
                not is_token_valid(user) or
                not user.get("is_active", True)):
                clear_user_session()
                return redirect("/login?message=account_disabled")
            last_activity = session.get("last_activity", 0)
            if time.time() - last_activity > 900:
                clear_user_session()
                return redirect("/login?message=timeout")
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
    elif request.args.get("message") == "invalid_session":
        message = "Sesión inválida. Por favor, inicia sesión nuevamente."
    elif request.args.get("message") == "expired_session":
        message = "Tu sesión ha expirado. Por favor, inicia sesión nuevamente."
    elif request.args.get("message") == "account_disabled":
        message = "Esta cuenta ha sido desactivada por el administrador."
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        user = get_user_by_email(email)
        if not user:
            message = "Correo o contraseña incorrectos."
        elif not user.get("is_active", True):
            message = "Esta cuenta ha sido desactivada por el administrador."
        elif not check_password_hash(user["password_hash"], password):
            message = "Correo o contraseña incorrectos."
        else:
            if user.get("session_token"):
                message = "Ya hay una sesión activa para esta cuenta. No se permiten múltiples accesos simultáneos."
            else:
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
    clear_user_session()
    return redirect("/login")

# -------------------------------------------------
# RUTAS PROTEGIDAS
# -------------------------------------------------
@app.route("/")
@login_required
@check_inactivity
def home():
    user = get_user_by_email(session["user_email"])
    is_admin = user.get("is_admin", False) if user else False
    return render_template("dashboard.html", user_email=session["user_email"], is_admin=is_admin, year=datetime.now().year)

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
        city = request.form.get("city", "").strip()
        address = request.form.get("address", "").strip()
        if not name or not owner_name:
            return render_template("register.html", error="El nombre de la mascota y del dueño son obligatorios.")
        photo_url = None
        if "photo" in request.files:
            photo = request.files["photo"]
            if photo and photo.filename:
                try:
                    upload_result = cloudinary.uploader.upload(photo, folder="pet_rescue_qr", resource_type="image")
                    photo_url = upload_result.get("secure_url")
                except Exception as e:
                    print("📷 Error al subir foto:", str(e))
        pet_id = str(uuid.uuid4())[:8].upper()
        add_pet(pet_id, name, breed, description, owner_name, owner_email, owner_phone, photo_url, city, address)
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
@app.route("/generate-qr")
@login_required
@check_inactivity
def generate_qr():
    pet_id = str(uuid.uuid4())[:8].upper()
    temp_email = "unregistered@petrescue.qr"
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("INSERT INTO pets (id, name, owner_name, is_registered, owner_email) VALUES (%s, %s, %s, %s, %s)", (pet_id, "", "", False, temp_email))
    else:
        cur.execute("INSERT INTO pets (id, name, owner_name, is_registered, owner_email) VALUES (?, ?, ?, ?, ?)", (pet_id, "", "", False, temp_email))
    conn.commit()
    cur.close()
    conn.close()
    if IS_PRODUCTION:
        qr_url = f"https://{request.host}/activate/{pet_id}"
    else:
        qr_url = f"{request.url_root}activate/{pet_id}"
    qr_img = qrcode.make(qr_url)
    buffered = BytesIO()
    qr_img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode()
    return render_template("generate_qr.html", qr=qr_base64, qr_url=qr_url, pet_id=pet_id)

@app.route("/generate-qr-bulk", methods=["GET", "POST"])
@login_required
@check_inactivity
def generate_qr_bulk():
    if request.method == "POST":
        try:
            quantity = int(request.form.get("quantity", 1))
            if quantity < 1 or quantity > 50:
                return render_template("generate_qr_bulk.html", error="Cantidad debe estar entre 1 y 50.")
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                qr_data = []
                for i in range(quantity):
                    pet_id = str(uuid.uuid4())[:8].upper()
                    temp_email = "unregistered@petrescue.qr"
                    conn = get_db_connection()
                    cur = conn.cursor()
                    if IS_PRODUCTION:
                        cur.execute("INSERT INTO pets (id, name, owner_name, is_registered, owner_email) VALUES (%s, %s, %s, %s, %s)", (pet_id, "", "", False, temp_email))
                    else:
                        cur.execute("INSERT INTO pets (id, name, owner_name, is_registered, owner_email) VALUES (?, ?, ?, ?, ?)", (pet_id, "", "", False, temp_email))
                    conn.commit()
                    cur.close()
                    conn.close()
                    if IS_PRODUCTION:
                        qr_url = f"https://{request.host}/activate/{pet_id}"
                    else:
                        qr_url = f"{request.url_root}activate/{pet_id}"
                    qr_img = qrcode.make(qr_url)
                    img_buffer = BytesIO()
                    qr_img.save(img_buffer, format="PNG")
                    img_buffer.seek(0)
                    filename = f"QR_{pet_id}.png"
                    zip_file.writestr(filename, img_buffer.getvalue())
                    qr_data.append({"id": pet_id, "filename": filename})
                ids_text = "\n".join([f"{item['id']} -> {item['filename']}" for item in qr_data])
                zip_file.writestr("IDs_de_QR.txt", ids_text)
            zip_buffer.seek(0)
            return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name=f'QR_vacios_{quantity}_unidades.zip')
        except ValueError:
            return render_template("generate_qr_bulk.html", error="Cantidad inválida.")
        except Exception as e:
            print(f"❌ Error en generación masiva: {repr(e)}")
            return render_template("generate_qr_bulk.html", error="Error al generar QRs.")
    return render_template("generate_qr_bulk.html")

@app.route("/qr/<pet_id>")
def qr_only(pet_id):
    pet = get_pet(pet_id)
    if not pet:
        return "<h2>❌ Mascota no encontrada.</h2>", 404
    if IS_PRODUCTION:
        qr_url = f"https://{request.host}/pet/{pet_id}"
    else:
        qr_url = f"{request.url_root}pet/{pet_id}"
    qr_img = qrcode.make(qr_url)
    buffered = BytesIO()
    qr_img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode()
    return render_template("qr_only.html", pet=pet, qr=qr_base64, qr_url=qr_url)

@app.route("/activate/<pet_id>", methods=["GET", "POST"])
def activate_pet(pet_id):
    try:
        pet = get_pet(pet_id)
        if not pet:
            return "<h2>❌ QR no válido o ya eliminado.</h2>", 404
        if pet.get("is_registered"):
            if IS_PRODUCTION:
                return redirect(f"https://{request.host}/pet/{pet_id}")
            else:
                return redirect(f"{request.url_root}pet/{pet_id}")
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            breed = request.form.get("breed", "").strip()
            description = request.form.get("description", "").strip()
            owner_name = request.form.get("owner_name", "").strip()
            owner_email = request.form.get("email", "").strip()
            owner_phone = request.form.get("phone", "").strip()
            city = request.form.get("city", "").strip()
            address = request.form.get("address", "").strip()
            password = request.form.get("password", "")
            if not name or not owner_name or not password:
                return render_template("activate_form.html", pet_id=pet_id, error="Nombre, dueño y contraseña son obligatorios.")
            photo_url = None
            if "photo" in request.files:
                photo = request.files["photo"]
                if photo and photo.filename:
                    try:
                        upload_result = cloudinary.uploader.upload(photo, folder="pet_rescue_qr/activated", resource_type="image")
                        photo_url = upload_result.get("secure_url")
                    except Exception as e:
                        print("📷 Error al subir foto en activación:", str(e))
            conn = get_db_connection()
            cur = conn.cursor()
            if IS_PRODUCTION:
                cur.execute("""
                    UPDATE pets SET name=%s, breed=%s, description=%s, owner_name=%s, owner_email=%s, owner_phone=%s,
                    city=%s, address=%s, photo_url=%s, is_registered=TRUE, registration_password=%s WHERE id=%s
                """, (name, breed, description, owner_name, owner_email, owner_phone, city, address, photo_url, password, pet_id))
            else:
                cur.execute("""
                    UPDATE pets SET name=?, breed=?, description=?, owner_name=?, owner_email=?, owner_phone=?,
                    city=?, address=?, photo_url=?, is_registered=TRUE, registration_password=? WHERE id=?
                """, (name, breed, description, owner_name, owner_email, owner_phone, city, address, photo_url, password, pet_id))
            conn.commit()
            cur.close()
            conn.close()
            if IS_PRODUCTION:
                return redirect(f"https://{request.host}/pet/{pet_id}")
            else:
                return redirect(f"{request.url_root}pet/{pet_id}")
        return render_template("activate_form.html", pet_id=pet_id)
    except Exception as e:
        print(f"❌ Error en /activate/{pet_id}: {repr(e)}")
        return "<h2>❌ Error al activar el QR.</h2>", 500

@app.route("/edit/<pet_id>/password", methods=["GET", "POST"])
def edit_pet_password(pet_id):
    pet = get_pet(pet_id)
    if not pet or not pet.get("is_registered") or not pet.get("registration_password"):
        return "<h2>❌ Esta mascota no tiene edición habilitada.</h2>", 403
    if request.method == "POST":
        password = request.form.get("password", "")
        if password != pet.get("registration_password"):
            return render_template("edit_password.html", pet=pet, error="❌ Contraseña incorrecta.")
        session[f"edit_access_{pet_id}"] = True
        return redirect(f"/edit/{pet_id}/form")
    return render_template("edit_password.html", pet=pet)

@app.route("/edit/<pet_id>/form", methods=["GET", "POST"])
def edit_pet_form(pet_id):
    if not session.get(f"edit_access_{pet_id}"):
        return redirect(f"/edit/{pet_id}/password")
    pet = get_pet(pet_id)
    if not pet:
        return "<h2>❌ Mascota no encontrada.</h2>", 404
    if request.method == "POST":
        photo_url = pet.get("photo_url")
        if "photo" in request.files:
            photo = request.files["photo"]
            if photo and photo.filename:
                try:
                    upload_result = cloudinary.uploader.upload(photo, folder="pet_rescue_qr/edited", resource_type="image")
                    photo_url = upload_result.get("secure_url")
                except Exception as e:
                    print("📷 Error al subir foto en edición:", str(e))
        name = request.form.get("name", pet["name"]).strip()
        breed = request.form.get("breed", pet["breed"] or "").strip()
        description = request.form.get("description", pet["description"] or "").strip()
        owner_name = request.form.get("owner_name", pet["owner_name"]).strip()
        owner_email = request.form.get("email", pet["owner_email"]).strip()
        owner_phone = request.form.get("phone", pet["owner_phone"] or "").strip()
        city = request.form.get("city", pet["city"] or "").strip()
        address = request.form.get("address", pet["address"] or "").strip()
        if not name or not owner_name:
            return render_template("edit_form.html", pet_id=pet_id, pet=pet, error="Nombre y dueño son obligatorios.")
        conn = get_db_connection()
        cur = conn.cursor()
        if IS_PRODUCTION:
            cur.execute("""
                UPDATE pets SET name=%s, breed=%s, description=%s, owner_name=%s, owner_email=%s, owner_phone=%s,
                city=%s, address=%s, photo_url=%s WHERE id=%s
            """, (name, breed, description, owner_name, owner_email, owner_phone, city, address, photo_url, pet_id))
        else:
            cur.execute("""
                UPDATE pets SET name=?, breed=?, description=?, owner_name=?, owner_email=?, owner_phone=?,
                city=?, address=?, photo_url=? WHERE id=?
            """, (name, breed, description, owner_name, owner_email, owner_phone, city, address, photo_url, pet_id))
        conn.commit()
        cur.close()
        conn.close()
        return f"""
        <script>
        alert('✅ Información actualizada exitosamente.');
        window.location.href='/pet/{pet_id}';
        </script>
        """
    return render_template("edit_form.html", pet_id=pet_id, pet=pet)

@app.route("/edit-my-pet/<pet_id>", methods=["GET", "POST"])
@login_required
@check_inactivity
def edit_my_pet(pet_id):
    pet = get_pet(pet_id)
    if not pet:
        return "<h2>❌ Mascota no encontrada.</h2>", 404
    if pet["owner_email"] != session["user_email"]:
        return "<h2>❌ No tienes permiso para editar esta mascota.</h2>", 403
    if request.method == "POST":
        photo_url = pet.get("photo_url")
        if "photo" in request.files:
            photo = request.files["photo"]
            if photo and photo.filename:
                try:
                    upload_result = cloudinary.uploader.upload(photo, folder="pet_rescue_qr/edited", resource_type="image")
                    photo_url = upload_result.get("secure_url")
                except Exception as e:
                    print("📷 Error al subir foto en edición:", str(e))
        name = request.form.get("name", pet["name"]).strip()
        breed = request.form.get("breed", pet["breed"] or "").strip()
        description = request.form.get("description", pet["description"] or "").strip()
        owner_name = request.form.get("owner_name", pet["owner_name"]).strip()
        owner_phone = request.form.get("phone", pet["owner_phone"] or "").strip()
        city = request.form.get("city", pet["city"] or "").strip()
        address = request.form.get("address", pet["address"] or "").strip()
        if not name or not owner_name:
            return render_template("edit_my_pet_form.html", pet=pet, error="Nombre y dueño son obligatorios.")
        conn = get_db_connection()
        cur = conn.cursor()
        if IS_PRODUCTION:
            cur.execute("""
                UPDATE pets SET name=%s, breed=%s, description=%s, owner_name=%s, owner_phone=%s,
                city=%s, address=%s, photo_url=%s WHERE id=%s
            """, (name, breed, description, owner_name, owner_phone, city, address, photo_url, pet_id))
        else:
            cur.execute("""
                UPDATE pets SET name=?, breed=?, description=?, owner_name=?, owner_phone=?,
                city=?, address=?, photo_url=? WHERE id=?
            """, (name, breed, description, owner_name, owner_phone, city, address, photo_url, pet_id))
        conn.commit()
        cur.close()
        conn.close()
        return f"""
        <script>
        alert('✅ Información actualizada exitosamente.');
        window.location.href='/my-pets';
        </script>
        """
    return render_template("edit_my_pet_form.html", pet=pet)

@app.route("/register", methods=["GET"])
@login_required
@check_inactivity
def show_register_form():
    return render_template("register.html")

@app.route("/my-pets")
@login_required
@check_inactivity
def my_pets():
    pets = get_all_pets(owner_email=session["user_email"])
    return render_template("my_pets.html", pets=pets)

@app.route("/pet/<pet_id>")
def pet_detail(pet_id):
    pet = get_pet(pet_id)
    if not pet:
        return "Mascota no encontrada", 404
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("SELECT * FROM vaccines WHERE pet_id = %s AND type = 'deworming' ORDER BY date_administered DESC", (pet_id,))
    else:
        cur.execute("SELECT * FROM vaccines WHERE pet_id = ? AND type = 'deworming' ORDER BY date_administered DESC", (pet_id,))
    deworming_records = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("pet.html", pet=pet, deworming=deworming_records)

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
        message = f"¡Tu mascota '{pet['name']}' fue vista!\nUbicación:\n{map_link}"
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
    message = ""
    if request.method == "POST":
        action = request.form.get("action")
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
        elif action == "toggle_active":
            email = request.form.get("email", "").strip()
            is_active = request.form.get("is_active") == "true"
            if email and email != session["user_email"]:
                toggle_user_active_status(email, is_active)
                status = "activada" if is_active else "desactivada"
                message = f"✅ Cuenta {email} {status}."
            else:
                message = "⚠️ No puedes modificar tu propia cuenta o el correo es inválido."
        elif action == "delete_pet":
            pet_id = request.form.get("pet_id", "").strip()
            if pet_id:
                if delete_pet(pet_id):
                    message = f"✅ Mascota {pet_id} eliminada."
                else:
                    message = f"⚠️ Mascota {pet_id} no encontrada."
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("SELECT email, is_admin, is_active FROM users ORDER BY created_at DESC")
    else:
        cur.execute("SELECT email, is_admin, is_active FROM users ORDER BY rowid DESC")
    users = cur.fetchall()
    cur.close()
    conn.close()
    pets = get_all_pets()
    return render_template("admin.html", users=users, pets=pets, message=message)

@app.route("/pet/<pet_id>/vaccines")
def view_vaccines(pet_id):
    pet = get_pet(pet_id)
    if not pet:
        return "<h2>❌ Mascota no encontrada.</h2>", 404
    vaccines = get_vaccines_by_pet(pet_id)
    return render_template("vaccines.html", pet=pet, vaccines=vaccines, is_owner=False)

@app.route("/my-pet/<pet_id>/vaccines")
@login_required
@check_inactivity
def view_my_vaccines(pet_id):
    pet = get_pet(pet_id)
    if not pet or pet["owner_email"] != session["user_email"]:
        return "<h2>❌ No tienes permiso para ver esta mascota.</h2>", 403
    vaccines = get_vaccines_by_pet(pet_id)
    return render_template("vaccines.html", pet=pet, vaccines=vaccines, is_owner=True)

@app.route("/my-pet/<pet_id>/vaccines/add", methods=["GET", "POST"])
@login_required
@check_inactivity
def add_vaccine_record(pet_id):
    pet = get_pet(pet_id)
    if not pet or pet["owner_email"] != session["user_email"]:
        return "<h2>❌ No tienes permiso para editar esta mascota.</h2>", 403
    if request.method == "POST":
        vaccine_name = request.form.get("vaccine_name", "").strip()
        date_administered = request.form.get("date_administered", "").strip()
        next_due_date = request.form.get("next_due_date", "").strip() or None
        veterinarian = request.form.get("veterinarian", "").strip() or None
        notes = request.form.get("notes", "").strip() or None
        if not vaccine_name or not date_administered:
            return render_template("add_vaccine.html", pet=pet, error="Nombre de vacuna y fecha son obligatorios.")
        add_vaccine(pet_id, vaccine_name, date_administered, next_due_date, veterinarian, notes)
        return redirect(f"/my-pet/{pet_id}/vaccines")
    return render_template("add_vaccine.html", pet=pet)

@app.route("/vaccine/<int:vaccine_id>/delete", methods=["POST"])
@login_required
@check_inactivity
def delete_vaccine_record(vaccine_id):
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("SELECT pet_id FROM vaccines WHERE id = %s", (vaccine_id,))
    else:
        cur.execute("SELECT pet_id FROM vaccines WHERE id = ?", (vaccine_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    if not result:
        return jsonify({"error": "Vacuna no encontrada"}), 404
    pet_id = result["pet_id"]
    pet = get_pet(pet_id)
    if not pet or pet["owner_email"] != session["user_email"]:
        return jsonify({"error": "No tienes permiso"}), 403
    if delete_vaccine(vaccine_id):
        return jsonify({"success": True})
    else:
        return jsonify({"error": "No se pudo eliminar"}), 400

@app.route("/pet/<pet_id>/vaccines/manage", methods=["GET", "POST"])
def manage_vaccines_password(pet_id):
    pet = get_pet(pet_id)
    if not pet or not pet.get("is_registered") or not pet.get("registration_password"):
        return "<h2>❌ Esta mascota no tiene gestión de vacunas habilitada.</h2>", 403
    if request.method == "POST":
        password = request.form.get("password", "")
        if password != pet.get("registration_password"):
            return render_template("manage_vaccines_password.html", pet=pet, error="❌ Contraseña incorrecta.")
        session[f"vaccine_access_{pet_id}"] = True
        return redirect(f"/pet/{pet_id}/vaccines/edit")
    return render_template("manage_vaccines_password.html", pet=pet)

@app.route("/pet/<pet_id>/vaccines/edit")
def edit_vaccines_session(pet_id):
    if not session.get(f"vaccine_access_{pet_id}"):
        return redirect(f"/pet/{pet_id}/vaccines/manage")
    pet = get_pet(pet_id)
    if not pet:
        return "<h2>❌ Mascota no encontrada.</h2>", 404
    vaccines = get_vaccines_by_pet(pet_id)
    return render_template("vaccines_edit.html", pet=pet, vaccines=vaccines)

@app.route("/pet/<pet_id>/vaccines/add", methods=["GET", "POST"])
def add_vaccine_password(pet_id):
    if not session.get(f"vaccine_access_{pet_id}"):
        return redirect(f"/pet/{pet_id}/vaccines/manage")
    pet = get_pet(pet_id)
    if not pet:
        return "<h2>❌ Mascota no encontrada.</h2>", 404
    if request.method == "POST":
        vaccine_name = request.form.get("vaccine_name", "").strip()
        date_administered = request.form.get("date_administered", "").strip()
        next_due_date = request.form.get("next_due_date", "").strip() or None
        veterinarian = request.form.get("veterinarian", "").strip() or None
        notes = request.form.get("notes", "").strip() or None
        if not vaccine_name or not date_administered:
            return render_template("add_vaccine_simple.html", pet=pet, error="Nombre de vacuna y fecha son obligatorios.")
        add_vaccine(pet_id, vaccine_name, date_administered, next_due_date, veterinarian, notes)
        return redirect(f"/pet/{pet_id}/vaccines/edit")
    return render_template("add_vaccine_simple.html", pet=pet)

@app.route("/vaccine/<int:vaccine_id>/delete/simple", methods=["POST"])
def delete_vaccine_simple(vaccine_id):
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("SELECT pet_id FROM vaccines WHERE id = %s", (vaccine_id,))
    else:
        cur.execute("SELECT pet_id FROM vaccines WHERE id = ?", (vaccine_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    if not result:
        return jsonify({"error": "Vacuna no encontrada"}), 404
    pet_id = result["pet_id"]
    if not session.get(f"vaccine_access_{pet_id}"):
        return jsonify({"error": "Acceso no autorizado"}), 403
    if delete_vaccine(vaccine_id):
        return jsonify({"success": True})
    else:
        return jsonify({"error": "No se pudo eliminar"}), 400

# -------------------------------------------------
# RUTAS PARA USUARIOS QR
# -------------------------------------------------
@app.route("/qr-login", methods=["GET", "POST"])
def qr_login():
    error = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        if not email or not password:
            error = "Correo y contraseña son obligatorios."
        else:
            conn = get_db_connection()
            cur = conn.cursor()
            if IS_PRODUCTION:
                cur.execute("SELECT id FROM pets WHERE owner_email = %s AND registration_password = %s AND is_registered = TRUE LIMIT 1", (email, password))
            else:
                cur.execute("SELECT id FROM pets WHERE owner_email = ? AND registration_password = ? AND is_registered = TRUE LIMIT 1", (email, password))
            result = cur.fetchone()
            cur.close()
            conn.close()
            if result:
                session["qr_logged_in"] = True
                session["qr_email"] = email
                session["last_activity"] = time.time()
                return redirect("/my-pets-qr")
            else:
                error = "Correo o contraseña incorrectos."
    return render_template("qr_login.html", error=error)

@app.route("/my-pets-qr")
@qr_login_required
def my_pets_qr():
    email = session["qr_email"]
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("SELECT * FROM pets WHERE owner_email = %s AND is_registered = TRUE", (email,))
    else:
        cur.execute("SELECT * FROM pets WHERE owner_email = ? AND is_registered = TRUE", (email,))
    pets = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("my_pets_qr.html", pets=pets, user_email=email)

@app.route("/qr-logout")
def qr_logout():
    session.clear()
    return redirect("https://petrescueqr-sales.onrender.com/")

@app.route("/edit-my-pet-qr/<pet_id>", methods=["GET", "POST"])
@qr_login_required
def edit_my_pet_qr(pet_id):
    email = session["qr_email"]
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("SELECT * FROM pets WHERE id = %s AND owner_email = %s AND is_registered = TRUE", (pet_id, email))
    else:
        cur.execute("SELECT * FROM pets WHERE id = ? AND owner_email = ? AND is_registered = TRUE", (pet_id, email))
    pet = cur.fetchone()
    cur.close()
    conn.close()
    if not pet:
        return "<h2>❌ No tienes permiso para editar esta mascota.</h2>", 403
    if request.method == "POST":
        photo_url = pet.get("photo_url")
        if "photo" in request.files:
            photo = request.files["photo"]
            if photo and photo.filename:
                try:
                    upload_result = cloudinary.uploader.upload(photo, folder="pet_rescue_qr/edited", resource_type="image")
                    photo_url = upload_result.get("secure_url")
                except Exception as e:
                    print("📷 Error al subir foto en edición:", str(e))
        name = request.form.get("name", pet["name"]).strip()
        breed = request.form.get("breed", pet["breed"] or "").strip()
        description = request.form.get("description", pet["description"] or "").strip()
        owner_name = request.form.get("owner_name", pet["owner_name"]).strip()
        owner_phone = request.form.get("phone", pet["owner_phone"] or "").strip()
        city = request.form.get("city", pet["city"] or "").strip()
        address = request.form.get("address", pet["address"] or "").strip()
        if not name or not owner_name:
            return render_template("edit_my_pet_form_qr.html", pet=pet, error="Nombre y dueño son obligatorios.")
        conn = get_db_connection()
        cur = conn.cursor()
        if IS_PRODUCTION:
            cur.execute("""
                UPDATE pets SET name=%s, breed=%s, description=%s, owner_name=%s, owner_phone=%s,
                city=%s, address=%s, photo_url=%s WHERE id=%s
            """, (name, breed, description, owner_name, owner_phone, city, address, photo_url, pet_id))
        else:
            cur.execute("""
                UPDATE pets SET name=?, breed=?, description=?, owner_name=?, owner_phone=?,
                city=?, address=?, photo_url=? WHERE id=?
            """, (name, breed, description, owner_name, owner_phone, city, address, photo_url, pet_id))
        conn.commit()
        cur.close()
        conn.close()
        return f"""
        <script>
        alert('✅ Información actualizada exitosamente.');
        window.location.href='/my-pets-qr';
        </script>
        """
    return render_template("edit_my_pet_form_qr.html", pet=pet)

@app.route("/my-pet-qr/<pet_id>/vaccines")
@qr_login_required
def view_my_vaccines_qr(pet_id):
    email = session["qr_email"]
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("SELECT * FROM pets WHERE id = %s AND owner_email = %s AND is_registered = TRUE", (pet_id, email))
    else:
        cur.execute("SELECT * FROM pets WHERE id = ? AND owner_email = ? AND is_registered = TRUE", (pet_id, email))
    pet = cur.fetchone()
    cur.close()
    conn.close()
    if not pet:
        return "<h2>❌ No tienes permiso para ver esta mascota.</h2>", 403
    vaccines = get_vaccines_by_pet(pet_id)  # ← Ahora solo vacunas
    return render_template("vaccines.html", pet=pet, vaccines=vaccines, is_owner=True)

@app.route("/my-pet-qr/<pet_id>/vaccines/add", methods=["GET", "POST"])
@qr_login_required
def add_vaccine_record_qr(pet_id):
    email = session["qr_email"]
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("SELECT * FROM pets WHERE id = %s AND owner_email = %s AND is_registered = TRUE", (pet_id, email))
    else:
        cur.execute("SELECT * FROM pets WHERE id = ? AND owner_email = ? AND is_registered = TRUE", (pet_id, email))
    pet = cur.fetchone()
    cur.close()
    conn.close()
    if not pet:
        return "<h2>❌ No tienes permiso para esta mascota.</h2>", 403
    if request.method == "POST":
        vaccine_name = request.form.get("vaccine_name", "").strip()
        date_administered = request.form.get("date_administered", "").strip()
        next_due_date = request.form.get("next_due_date", "") or None
        veterinarian = request.form.get("veterinarian", "") or None
        notes = request.form.get("notes", "") or None
        if not vaccine_name or not date_administered:
            return render_template("add_vaccine.html", pet=pet, error="Nombre de vacuna y fecha son obligatorios.")
        conn = get_db_connection()
        cur = conn.cursor()
        if IS_PRODUCTION:
            cur.execute("INSERT INTO vaccines (pet_id, vaccine_name, date_administered, next_due_date, veterinarian, notes) VALUES (%s, %s, %s, %s, %s, %s)", (pet_id, vaccine_name, date_administered, next_due_date, veterinarian, notes))
        else:
            cur.execute("INSERT INTO vaccines (pet_id, vaccine_name, date_administered, next_due_date, veterinarian, notes) VALUES (?, ?, ?, ?, ?, ?)", (pet_id, vaccine_name, date_administered, next_due_date, veterinarian, notes))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(f"/my-pet-qr/{pet_id}/vaccines")
    return render_template("add_vaccine.html", pet=pet)

@app.route("/vaccine-qr/<int:vaccine_id>/delete", methods=["POST"])
@qr_login_required
def delete_vaccine_qr(vaccine_id):  # ← Nombre único
    """Elimina un registro de vacuna (solo dueños QR)."""
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("SELECT pet_id FROM vaccines WHERE id = %s", (vaccine_id,))
    else:
        cur.execute("SELECT pet_id FROM vaccines WHERE id = ?", (vaccine_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    
    if not result:
        return jsonify({"error": "Vacuna no encontrada"}), 404
    
    pet_id = result["pet_id"]
    email = session["qr_email"]
    
    # Verificar que la mascota pertenezca al usuario QR
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("SELECT id FROM pets WHERE id = %s AND owner_email = %s", (pet_id, email))
    else:
        cur.execute("SELECT id FROM pets WHERE id = ? AND owner_email = ?", (pet_id, email))
    pet_result = cur.fetchone()
    cur.close()
    conn.close()
    
    if not pet_result:
        return jsonify({"error": "No tienes permiso"}), 403
    
    if delete_vaccine(vaccine_id):
        return jsonify({"success": True})
    else:
        return jsonify({"error": "No se pudo eliminar"}), 400
    
@app.route("/my-pet-qr/<pet_id>/deworming/add", methods=["GET", "POST"])
@qr_login_required
def add_deworming_record_qr(pet_id):
    email = session["qr_email"]
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("SELECT * FROM pets WHERE id = %s AND owner_email = %s", (pet_id, email))
    else:
        cur.execute("SELECT * FROM pets WHERE id = ? AND owner_email = ?", (pet_id, email))
    pet = cur.fetchone()
    cur.close()
    conn.close()
    if not pet:
        return "<h2>❌ No tienes permiso para esta mascota.</h2>", 403

    if request.method == "POST":
        medicine_name = request.form.get("medicine_name", "").strip()
        date_administered = request.form.get("date_administered", "").strip()
        next_due_date = request.form.get("next_due_date", "") or None
        veterinarian = request.form.get("veterinarian", "") or None
        notes = request.form.get("notes", "") or None

        if not medicine_name or not date_administered:
            return render_template("add_deworming.html", pet=pet, error="Medicamento y fecha son obligatorios.")

        conn = get_db_connection()
        cur = conn.cursor()
        if IS_PRODUCTION:
            cur.execute("""
                INSERT INTO vaccines (pet_id, vaccine_name, date_administered, next_due_date, veterinarian, notes, type)
                VALUES (%s, %s, %s, %s, %s, %s, 'deworming')
            """, (pet_id, medicine_name, date_administered, next_due_date, veterinarian, notes))
        else:
            cur.execute("""
                INSERT INTO vaccines (pet_id, vaccine_name, date_administered, next_due_date, veterinarian, notes, type)
                VALUES (?, ?, ?, ?, ?, ?, 'deworming')
            """, (pet_id, medicine_name, date_administered, next_due_date, veterinarian, notes))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(f"/my-pet-qr/{pet_id}/deworming")

    return render_template("add_deworming.html", pet=pet)

@app.route("/my-pet-qr/<pet_id>/deworming")
@qr_login_required
def view_my_deworming_qr(pet_id):
    email = session["qr_email"]
    conn = get_db_connection()
    cur = conn.cursor()
    if IS_PRODUCTION:
        cur.execute("SELECT * FROM pets WHERE id = %s AND owner_email = %s AND is_registered = TRUE", (pet_id, email))
    else:
        cur.execute("SELECT * FROM pets WHERE id = ? AND owner_email = ? AND is_registered = TRUE", (pet_id, email))
    pet = cur.fetchone()
    cur.close()
    conn.close()
    if not pet:
        return "<h2>❌ No tienes permiso para ver esta mascota.</h2>", 403
    deworming = get_deworming_by_pet(pet_id)  # ← Solo desparasitaciones
    return render_template("deworming.html", pet=pet, deworming=deworming, is_owner=True)
# -------------------------------------------------
# SERVIDOR
# -------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=not IS_PRODUCTION)