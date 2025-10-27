import requests
import time
from config import API_KEYS, ENDPOINT  # ← Importación absoluta desde raíz del proyecto


def call_gemini(prompt, key):
    url = "https://generative-language.googleapis.com/v1/models/gemini-pro:generateContent"
    
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
    print(f"🔗 URL final: {url}?key={key}")
    print(f"📩 Prompt enviado: {prompt}")
    print(f"📦 Payload: {payload}")

    try:
        response = requests.post(f"{url}?key={key}", headers=headers, json=payload)
        print(f"📥 Respuesta cruda: {response.text}")
        response.raise_for_status()
        data = response.json()

        # 🧠 Validación defensiva
        content = data.get("candidates", [{}])[0].get("content", {})
        parts = content.get("parts", [])
        if not parts or "text" not in parts[0]:
            return "La respuesta de Gemini está vacía o mal formada."

        return parts[0]["text"]

    except requests.exceptions.HTTPError as http_err:
        return f"❌ Error HTTP {http_err.response.status_code}: {http_err.response.text}"
    except Exception as e:
        return f"❌ Error al conectar con Gemini: {str(e)}"
    
print(call_gemini("Hola, ¿qué propiedades hay en Palermo?", "AIzaSyCNHuDW5ytZwQzwy3og5ZxYBjV0Tc6oyLU"))

# 🔁 Función de rotación de claves
def call_gemini_with_rotation(prompt):
    for key in API_KEYS:
        print("=" * 60)
        print(f"Probando clave: {key[:10]}")
        start = time.time()
        response = call_gemini(prompt, key)
        duration = time.time() - start
        print(f"⏱️ Duración con clave {key[:10]}: {duration:.2f} segundos")
        print(f"Respuesta: {response}")
        print("=" * 60)
        if "404" in response:
            print(f"❌ Clave rechazada: {key[:10]} (modelo no habilitado)")
        if not any(err in response for err in ["403", "429", "Quota exceeded", "Error HTTP"]):
            print(f"✅ Clave aceptada: {key[:10]}")
            return response



    print("❌ Ninguna clave fue aceptada por Gemini.")
    return "Todas las claves están agotadas o no autorizadas. Verificá la configuración."