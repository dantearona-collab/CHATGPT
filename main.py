from fastapi import FastAPI
from config import API_KEYS  # Importa las claves desde config.py
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import sqlite3
import json
import os
import re
import requests
from pydantic import BaseModel
from datetime import datetime
from gemini.client import call_gemini_with_rotation


from config import API_KEYS
for i, key in enumerate(API_KEYS):
    test = call_gemini_with_rotation("Respondé solo con OK")
    print(f"🔑 Clave {i+1} ({key[:10]}...): {test}")
    
DB_PATH = os.path.join(os.path.dirname(__file__), "propiedades.db")
LOG_PATH = os.path.join(os.path.dirname(__file__), "conversaciones.db")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # en producción, usar tu dominio
    allow_methods=["*"],
    allow_headers=["*"],
)

class Message(BaseModel):
    message: str
    channel: str = "web"  # opcional: "web", "whatsapp", etc.

JSON_PATH = os.path.join(os.path.dirname(__file__), "properties.json")

def cargar_propiedades_json():
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Error al cargar properties.json: {e}")
        return []

def extraer_barrios(propiedades):
    return sorted(set(p.get("neighborhood", "").lower() for p in propiedades if p.get("neighborhood")))

def extraer_tipos(propiedades):
    return sorted(set(p.get("tipo", "").lower() for p in propiedades if p.get("tipo")))

def extraer_operaciones(propiedades):
    return sorted(set(p.get("operacion", "").lower() for p in propiedades if p.get("operacion")))

app = FastAPI()

from fastapi import FastAPI
from config import API_KEYS, MODEL, ENDPOINT
import requests

app = FastAPI()

@app.get("/debug/model")
def debug_model():
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": "Hola, ¿cómo estás?"}]}]
    }
    params = {"key": API_KEYS[0]}
    response = requests.post(ENDPOINT, headers=headers, params=params, json=payload)
    return {
        "status": response.status_code,
        "response": response.json() if response.ok else response.text
    }

@app.get("/debug/env")
def debug_env():
    return {
        "keys_loaded": len(API_KEYS),
        "first_key": API_KEYS[0][:10] if API_KEYS else None
    }
    
@app.get("/")
def root():
    return {
        "status": "Backend activo",
        "endpoint": "/chat",
        "método": "POST",
        "uso": "Enviar mensaje como JSON: { message: '...', channel: 'web' }"
    }

@app.get("/status")
def status():
    test_prompt = "Respondé solo con OK"
    response = call_gemini_with_rotation(test_prompt)
    return {"gemini_api": "OK" if "OK" in response else response}

@app.get("/logs")
def get_logs(limit: int = 10):
    conn = sqlite3.connect(LOG_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT timestamp, channel, user_message, bot_response FROM logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_historial_canal(canal="web", limite=3):
    conn = sqlite3.connect(LOG_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT user_message FROM logs WHERE channel = ? ORDER BY id DESC LIMIT ?",
        (canal, limite)
    )
    rows = cur.fetchall()
    conn.close()
    return [r["user_message"] for r in reversed(rows)]

def query_properties(filters=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    q = "SELECT id, title, neighborhood, price, rooms, sqm, description FROM properties"
    params = []
    if filters:
        where_clauses = []
        if filters.get("neighborhood"):
            where_clauses.append("neighborhood LIKE ?")
            params.append(f"%{filters['neighborhood']}%")
        if filters.get("max_price") is not None:
            where_clauses.append("price <= ?")
            params.append(filters["max_price"])
        if filters.get("operacion"):
            where_clauses.append("operacion LIKE ?")
            params.append(f"%{filters['operacion']}%") 
        
        if where_clauses:
            q += " WHERE " + " AND ".join(where_clauses)
    cur.execute(q, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def build_prompt(user_text, results=None, filters=None, channel="web", style_hint=""):
    whatsapp_tone = channel == "whatsapp"
    if results is not None:
        if results:
            bullets = [
                f"{r['title']} — {r['neighborhood']} — ${r['price']} — {r['rooms']} amb — {r['sqm']} m2"
                for r in results[:5]
            ]
            return (
                style_hint + f"\n\nEl usuario está buscando propiedades para {filters.get('operacion', 'consultar')} en {filters.get('neighborhood', 'varios barrios')}. Aquí hay resultados relevantes:\n"
                + "\n".join(bullets)
                + "\n\nRedactá una respuesta cálida y profesional que resuma los resultados, "
                "ofrezca ayuda personalizada y sugiera continuar la conversación por WhatsApp. "
                "Cerrá con un agradecimiento y tono amable."
                + ("\nUsá emojis si el canal es WhatsApp." if whatsapp_tone else "")
            )
        else:
            return (
                f"{style_hint}\n\nEl usuario busca propiedades pero no hay resultados con esos filtros. "
                "Redactá una respuesta amable que sugiera alternativas cercanas, pida más detalles "
                "y ofrezca continuar la conversación por WhatsApp. Cerrá con un agradecimiento."
                + ("\nUsá emojis si el canal es WhatsApp." if whatsapp_tone else "")
            )
    else:
        return (
            f"{style_hint}\n\nActuá como asistente inmobiliario para Dante Propiedades. "
            "Respondé la siguiente consulta de forma cálida, profesional y breve. "
            "Si es posible, ofrecé continuar por WhatsApp y agradecé el contacto."
            + ("\nUsá emojis si el canal es WhatsApp." if whatsapp_tone else "")
            + "\nConsulta: " + user_text
        )

def log_conversation(user_text, response_text, channel="web"):
    conn = sqlite3.connect(LOG_PATH)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            channel TEXT,
            user_message TEXT,
            bot_response TEXT
        )
    ''')
    cur.execute('INSERT INTO logs (timestamp, channel, user_message, bot_response) VALUES (?, ?, ?, ?)',
                (datetime.now().isoformat(), channel, user_text, response_text))
    conn.commit()
    conn.close()

@app.post("/chat")
async def chat(msg: Message):
    user_text = msg.message.strip()
    channel = msg.channel
    propiedades_json = cargar_propiedades_json()
    barrios_disponibles = extraer_barrios(propiedades_json)
    tipos_disponibles = extraer_tipos(propiedades_json)

    operaciones_disponibles = extraer_operaciones(propiedades_json)
    historial = get_historial_canal(channel)
    contexto_historial = "\nHistorial reciente del usuario:\n" + "\n".join(f"- {m}" for m in historial)
    
    # Agregar contexto dinámico al estilo
    contexto_dinamico = (
        f"Barrios disponibles: {', '.join(barrios_disponibles)}.\n"
        f"Tipos de propiedad disponibles: {', '.join(tipos_disponibles)}.\n"
        f"Tipos de operación disponibles: {', '.join(operaciones_disponibles)}."
    )
    contexto_dinamico += (
        "\nEjemplo: si el usuario escribe 'venta de departamento en Palermo', ya está indicando que busca comprar."
    )

    if not user_text:
        return {"response": "Por favor, escribí tu consulta para que pueda ayudarte 😊"}

    text_lower = user_text.lower()
    filters = None
    results = None

    if any(k in text_lower for k in ["buscar", "mostrar", "propiedad", "departamento", "casa"]):
        filters = {}
        m_barrio = re.search(r"en ([a-zA-Záéíóúñ ]+)", text_lower)
        if m_barrio:
            filters["neighborhood"] = m_barrio.group(1).strip()
        m_price = re.search(r"hasta \$?\s*([0-9\.]+)", text_lower)
        if m_price:
            filters["max_price"] = int(m_price.group(1).replace('.', ''))
       
        m_operacion = re.search(r"(venta|alquiler|temporario|comprar|alquilar)", text_lower)
        if m_operacion:
            op = m_operacion.group(1)
            filters["operacion"] = (
                "venta" if op in ["venta", "comprar"]
                else "alquiler" if op in ["alquiler", "alquilar"]
                else "temporario"
            )
        eresults = query_properties(filters)
    
    # 🔍 Adaptar el tono según el canal (fuera del bloque condicional)
    if channel == "whatsapp":
        style_hint = "Respondé de forma breve, directa y cálida como si fuera un mensaje de WhatsApp."
    elif channel == "web":
        style_hint = "Respondé de forma explicativa, profesional y cálida como si fuera una consulta web."
    else:
        style_hint = "Respondé de forma clara y útil."

    prompt = build_prompt(user_text, results, filters, channel, style_hint + "\n" + contexto_dinamico + "\n" + contexto_historial)
    print("🧠 Prompt enviado a Gemini:\n", prompt)
    answer = call_gemini_with_rotation(prompt)

    log_conversation(user_text, answer, channel)
    return {"response": answer}

if __name__ == "__main__":
    import uvicorn
    print("🚀 Iniciando servidor de Dante Propiedades...")
    print("📍 URL: http://127.0.0.1:8000")
    print("📚 Docs: http://127.0.0.1:8000/docs")

    resultado = call_gemini_with_rotation("Hola, responde solo con 'OK'")
    print(f"📝 Resultado final: {resultado}")
    print("=" * 50)

    uvicorn.run(app, host="127.0.0.1", port=8000)