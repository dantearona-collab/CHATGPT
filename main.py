from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import ollama
import sqlite3
import json
import os
import re
from pydantic import BaseModel
from datetime import datetime

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
    user_text = msg.message
    channel = msg.channel
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

    prompt = build_prompt(user_text, results, filters, channel)

    try:
        resp = ollama.chat(
            model="llama3.2:3b",
            messages=[{"role": "user", "content": prompt}],
        )
        answer = resp["message"]["content"] if isinstance(resp, dict) and "message" in resp else str(resp)
    except Exception as e:
        answer = "Error en el motor de IA: " + str(e)

    log_conversation(user_text, answer, channel)
    return {"response": answer}