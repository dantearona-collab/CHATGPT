import os

# Claves separadas por coma en variable de entorno GEMINI_KEYS
API_KEYS = [key.strip() for key in os.getenv("GEMINI_KEYS", "").split(",") if key.strip()]

# Modelo compatible con tu clave actual
MODEL = "gemini-2.5-pro-preview-03-25"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
print(f"🔧 Claves cargadas: {[key[:10] for key in API_KEYS]}")