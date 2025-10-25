from fastapi import FastAPI
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

DB_PATH = os.path.join(os.path.dirname(__file__), "propiedades.db")
LOG_PATH = os.path.join(os.path.dirname(__file__), "conversaciones.db")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # en producción, usar tu dominio GitHub Pages
    allow_methods=["*"],
    allow_headers=["*"],
)

class Message(BaseModel):
    message: str
    channel: str = "web"  # opcional: "web", "whatsapp", etc.

@app.get("/")
def root():
    return {
        "status": "Backend activo",
        "endpoint": "/chat",
        "método": "POST",
        "uso": "Enviar mensaje como JSON: { message: '...', channel: 'web' }"
    }

@app.get("/logs")
def get_logs(limit: int = 10):
    conn = sqlite3.connect(LOG_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT timestamp, channel, user_message, bot_response FROM logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/status")
def status():
    test_prompt = "Respondé solo con OK"
    response = call_gemini_with_rotation(test_prompt)
    return {"gemini_api": "OK" if "OK" in response else response}

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
        if where_clauses:
            q += " WHERE " + " AND ".join(where_clauses)
    cur.execute(q, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def build_prompt(user_text, results=None, filters=None, channel="web"):
    whatsapp_tone = channel == "whatsapp"
    if results is not None:
        if results:
            bullets = [
                f"{r['title']} — {r['neighborhood']} — ${r['price']} — {r['rooms']} amb — {r['sqm']} m2"
                for r in results[:5]
            ]
            return (
                "El usuario está buscando propiedades. Aquí hay resultados relevantes:\n"
                + "\n".join(bullets)
                + "\n\nRedactá una respuesta cálida y profesional que resuma los resultados, "
                "ofrezca ayuda personalizada y sugiera continuar la conversación por WhatsApp. "
                "Cerrá con un agradecimiento y tono amable."
                + ("\nUsá emojis si el canal es WhatsApp." if whatsapp_tone else "")
            )
        else:
            return (
                "El usuario busca propiedades pero no hay resultados con esos filtros. "
                "Redactá una respuesta amable que sugiera alternativas cercanas, pida más detalles "
                "y ofrezca continuar la conversación por WhatsApp. Cerrá con un agradecimiento."
                + ("\nUsá emojis si el canal es WhatsApp." if whatsapp_tone else "")
            )
    else:
        return (
            "Actuá como asistente inmobiliario para Dante Propiedades. "
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
        results = query_properties(filters)

    # 🔍 Adaptar el tono según el canal
    if channel == "whatsapp":
        style_hint = "Respondé de forma breve, directa y cálida como si fuera un mensaje de WhatsApp."
    elif channel == "web":
        style_hint = "Respondé de forma explicativa, profesional y cálida como si fuera una consulta web."
    else:
        style_hint = "Respondé de forma clara y útil."

    # 🔧 Incluir el estilo en el prompt
    prompt = build_prompt(user_text, results, filters, channel, style_hint)
    
    answer = call_gemini_with_rotation(prompt)

    log_conversation(user_text, answer, channel)
    return {"response": answer}

# Ejecutar prueba automática al importar
if __name__ == "__main__":
    import uvicorn
    print("🚀 Iniciando servidor de Dante Propiedades...")
    print("📍 URL: http://127.0.0.1:8000")
    print("📚 Docs: http://127.0.0.1:8000/docs")

    resultado = call_gemini_with_rotation("Hola, responde solo con 'OK'")
    print(f"📝 Resultado final: {resultado}")
    print("=" * 50)

    uvicorn.run(app, host="127.0.0.1", port=8000)