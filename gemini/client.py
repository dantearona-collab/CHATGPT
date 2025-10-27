import requests
import time
from config import API_KEYS, WORKING_MODEL  # ← Cambiar ENDPOINT por WORKING_MODEL


def call_gemini(prompt, key):
    # ⚠️ CORREGIR ESTA LÍNEA - usar el modelo que SÍ funciona
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{WORKING_MODEL}:generateContent"
    
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    # 🔍 Log de entrada
    print(f"🔗 URL final: {url}?key={key[:10]}...")
    print(f"🔧 Modelo: {WORKING_MODEL}")
    print(f"📩 Prompt: {prompt}")
    print(f"📦 Payload: {payload}")

    try:
        response = requests.post(f"{url}?key={key}", headers=headers, json=payload, timeout=30)
        print(f"📥 Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ Error HTTP {response.status_code}: {response.text[:200]}")
            return f"❌ Error HTTP {response.status_code}"
            
        data = response.json()
        print(f"✅ Respuesta exitosa")

        # 🧠 Validación defensiva
        content = data.get("candidates", [{}])[0].get("content", {})
        parts = content.get("parts", [])
        if not parts or "text" not in parts[0]:
            return "La respuesta de Gemini está vacía o mal formada."

        text_response = parts[0]["text"]
        print(f"💬 Respuesta: {text_response}")
        return text_response

    except requests.exceptions.HTTPError as http_err:
        return f"❌ Error HTTP {http_err.response.status_code}: {http_err.response.text}"
    except Exception as e:
        return f"❌ Error al conectar con Gemini: {str(e)}"

# 🔁 Función de rotación de claves
def call_gemini_with_rotation(prompt):
    print(f"\n🎯 INICIANDO ROTACIÓN DE CLAVES")
    print(f"🔧 Modelo configurado: {WORKING_MODEL}")
    print(f"🔑 Claves disponibles: {len(API_KEYS)}")
    
    for key in API_KEYS:
        print("=" * 60)
        print(f"Probando clave: {key[:10]}...")
        start = time.time()
        response = call_gemini(prompt, key)
        duration = time.time() - start
        print(f"⏱️ Duración: {duration:.2f} segundos")
        
        # Verificar si la respuesta es exitosa
        if not any(err in response for err in ["❌ Error", "Error HTTP", "403", "404", "429", "Quota exceeded"]):
            print(f"✅ ✅ ✅ CLAVE ACEPTADA: {key[:10]}...")
            return response
        else:
            print(f"❌ Clave rechazada: {key[:10]}... - {response[:100]}")
        print("=" * 60)

    print("❌ Ninguna clave fue aceptada por Gemini.")
    return "Todas las claves están agotadas o no autorizadas. Verificá la configuración."

# Test opcional
if __name__ == "__main__":
    test_response = call_gemini_with_rotation("Responde solo con OK")
    print(f"\n🎯 TEST FINAL: {test_response}")