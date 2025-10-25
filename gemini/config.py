import os

# Claves separadas por coma en variable de entorno GEMINI_KEYS
API_KEYS = os.getenv("GEMINI_KEYS", "").split(",")

# Modelo compatible con tu clave actual
MODEL = "gemini-2.5-pro-preview-03-25"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"