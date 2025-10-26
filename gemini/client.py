import requests
from config import API_KEYS, ENDPOINT  # ← Importación absoluta desde raíz del proyecto

def call_gemini(prompt, api_key):
    headers = {"Content-Type": "application/json"}
    params = {"key": api_key}
    body = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ]
    }

    try:
        res = requests.post(ENDPOINT, headers=headers, params=params, json=body, timeout=30)
        res.raise_for_status()
        data = res.json()

        if "candidates" not in data or not data["candidates"]:
            return "Gemini no devolvió contenido. ¿Querés que lo intentemos de nuevo?"

        content = data["candidates"][0].get("content", {})
        parts = content.get("parts", [])
        if not parts or "text" not in parts[0]:
            return "La respuesta de Gemini está vacía o mal formada."

        return parts[0]["text"]

    except requests.exceptions.HTTPError as http_err:
        return f"Error HTTP {http_err.response.status_code}: {http_err.response.text}"
    except Exception as e:
        return f"Error al conectar con Gemini: {str(e)}"

# 🔁 Función de rotación de claves
def call_gemini_with_rotation(prompt):
    for key in API_KEYS:
        print("=" * 60)
        print(f"🔁 Probando clave: {key[:10]}...")
        response = call_gemini(prompt, key)
        print(f"📩 Respuesta: {response}")
        print("=" * 60)

        if not any(err in response for err in ["403", "429", "Quota exceeded", "Error HTTP"]):
            print(f"✅ Clave aceptada: {key[:10]}...")
            return response

    print("❌ Ninguna clave fue aceptada por Gemini.")
    return "Todas las claves están agotadas o no autorizadas. Verificá la configuración."