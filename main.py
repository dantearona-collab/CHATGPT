from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import sqlite3
import json
import os
import re
import requests
import logging
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

# Configurar logging
logging.basicConfig(level=logging.DEBUG)

def call_gemini(prompt):
    # Mostrar debug en la interfaz de Streamlit
    with st.expander("🔧 Debug Info", expanded=False):
        st.write("**Debug Mode Activado**")
        st.write(f"Prompt: `{prompt}`")
    
    url = "https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent"
    headers = {"Content-Type": "application/json"}
    params = {"key": "AIzaSyALNEvJuxb5FYX6q04XAF6ppzuf4avnOig"}
    
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ]
    }

    try:
        # Debug: mostrar info antes del request
        logging.debug(f"🔍 Making request to: {url}")
        
        res = requests.post(url, headers=headers, params=params, json=body, timeout=30)
        
        # Debug: mostrar respuesta HTTP
        logging.debug(f"📡 Response status: {res.status_code}")
        
        res.raise_for_status()
        data = res.json()
        
        # Debug: mostrar estructura completa
        logging.debug(f"📊 Full response: {data}")
        
        response_text = data["candidates"][0]["content"]["parts"][0]["text"]
        
        # Debug: mostrar respuesta exitosa
        logging.debug(f"✅ Success! Response: {response_text[:100]}...")
        
        return response_text
        
    except Exception as e:
        # Debug: mostrar error completo
        logging.error(f"❌ Error details: {str(e)}", exc_info=True)
        
        # Mostrar más detalles en Streamlit
        with st.expander("🚨 Error Details", expanded=False):
            st.error(f"Error completo: {str(e)}")
            if 'res' in locals():
                st.write(f"Status Code: {res.status_code}")
                st.write(f"Response Text: {res.text}")
        
        return f"Error al conectar con Gemini: {str(e)}"

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

    prompt = build_prompt(user_text, results, filters, channel)
    answer = call_gemini(prompt)

    log_conversation(user_text, answer, channel)
    return {"response": answer}