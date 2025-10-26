import os
from dotenv import load_dotenv
from pathlib import Path

# Cargar el archivo .env desde ruta absoluta
dotenv_path = Path("C:/Users/artar/downloads/chatgpt/.env")
load_dotenv(dotenv_path)

# Leer y procesar la variable GEMINI_KEYS
raw_keys = os.getenv("GEMINI_KEYS", "")
print("🧪 Variable cruda:", raw_keys)

API_KEYS = [key.strip() for key in raw_keys.split(",") if key.strip()]
print(f"🔧 Claves cargadas: {[key[:10] for key in API_KEYS]}")

# Configuración del modelo y endpoint
MODEL = "gemini-2.5-pro-preview-03-25"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"