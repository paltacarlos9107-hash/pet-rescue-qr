from database import init_db, add_pet, get_pet

# Inicializa la base de datos
init_db()

# Registra una mascota de prueba
add_pet("TEST123", "Max", "Golden", "Pelaje dorado, collar azul", "dueño@example.com")

# Búscala
pet = get_pet("TEST123")
print("Mascota encontrada:", pet)