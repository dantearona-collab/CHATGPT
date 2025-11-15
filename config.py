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

# 🔥 CORRECCIÓN CRÍTICA: BUSCAR MÚLTIPLES NOMBRES DE VARIABLES
def obtener_claves_gemini():
    """Buscar claves en múltiples variables de entorno posibles"""
    
    # Lista de posibles nombres de variables en Render
    posibles_variables = [
        'GOOGLE_API_KEY', 
        'GEMINI_API_KEY', 
        'GOOGLE_API_KEY_2',
        'GEMINI_API_KEYS',  # Tu variable actual
        'API_KEY'
    ]
    
    claves_encontradas = []
    
    for var_name in posibles_variables:
        clave = os.getenv(var_name)
        if clave and clave.startswith('AIzaSy'):
            print(f"✅ Encontrada variable: {var_name}")
            claves_encontradas.append(clave)
    
    # Si no se encontraron variables, usar claves de emergencia
    if not claves_encontradas:
        print("🚨 No se encontraron variables de entorno - Usando claves de emergencia")
        claves_encontradas = [
            "AIzaSyB5rN9lVhki8mnw3tSHDBtBvnVfI_vY5JU",
            "AIzaSyBa_XEELLVFZOtB7Qd7qmSSnNYFQL4-ww8", 
            "AIzaSyCgO-mUkizhQNZNMhgacQMN7aUhAWaUKUk"
        ]
    
    return claves_encontradas

# Obtener claves
API_KEYS = obtener_claves_gemini()
print(f"🔧 Claves cargadas: {len(API_KEYS)}")
print(f"🔑 Primeras claves: {[key[:8] + '...' for key in API_KEYS[:2]]}")

# Configuración del modelo y endpoint
WORKING_MODEL = "gemini-2.0-flash-001"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{WORKING_MODEL}:generateContent"
MODEL = WORKING_MODEL

print(f"🔧 Modelo configurado: {WORKING_MODEL}")
print(f"🔧 Endpoint: {ENDPOINT}")