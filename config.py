import os
from dotenv import load_dotenv
from pathlib import Path

# Intentar cargar .env localmente, pero en Render usar variables de entorno
try:
    # Solo cargar .env si estamos en desarrollo local
    if not os.environ.get('RENDER'):  # Render establece esta variable
        dotenv_path = Path(".env")  # Ruta relativa, no absoluta
        if dotenv_path.exists():
            load_dotenv(dotenv_path)
            print("✅ .env cargado localmente")
        else:
            print("ℹ️  No se encontró .env, usando variables de entorno")
except:
    print("ℹ️  Usando variables de entorno del sistema")

# Leer GEMINI_KEYS de variables de entorno
raw_keys = os.getenv("GEMINI_API_KEYS", "")  # 🔥 CAMBIAR NOMBRE
print("🧪 Variable cruda:", raw_keys[:50] + "..." if len(raw_keys) > 50 else raw_keys)

API_KEYS = [key.strip() for key in raw_keys.split(",") if key.strip()]
print(f"🔧 Claves cargadas: {[key[:8] + '...' for key in API_KEYS]}")

# Configuración del modelo y endpoint
WORKING_MODEL = "gemini-2.0-flash-001"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{WORKING_MODEL}:generateContent"
MODEL = WORKING_MODEL

print(f"🔧 Modelo configurado: {WORKING_MODEL}")
print(f"🔧 Endpoint: {ENDPOINT}")