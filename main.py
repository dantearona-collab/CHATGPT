from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import ollama
import sqlite3
import json
import os
from pydantic import BaseModel

DB_PATH = os.path.join(os.path.dirname(__file__), "propiedades.db")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class Message(BaseModel):
    message: str

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

@app.post("/chat")
async def chat(msg: Message):
    user_text = msg.message
    filters = {}
    text_lower = user_text.lower()
    if any(k in text_lower for k in ["buscar", "mostrar", "propiedad", "departamento", "casa"]):
        import re
        m_barrio = re.search(r"en ([a-zA-Záéíóúñ ]+)", text_lower)
        if m_barrio:
            filters["neighborhood"] = m_barrio.group(1).strip()
        m_price = re.search(r"hasta \$?\s*([0-9\.]+)", text_lower)
        if m_price:
            filters["max_price"] = int(m_price.group(1).replace('.', ''))

        results = query_properties(filters)
        if results:
            bullets = []
            for r in results[:5]:
                bullets.append(f"{r['title']} — {r['neighborhood']} — ${r['price']} — {r['rooms']} amb — {r['sqm']} m2")
            text_for_llm = (
                "El usuario pide propiedades. Aquí hay resultados de la base local:\n" + "\n".join(bullets)
                + "\n\nRedactá una respuesta amable que resuma los resultados y ofrezca tomar datos de contacto."
            )
        else:
            text_for_llm = (
                "El usuario pide propiedades pero no encontramos resultados con esos filtros."
                "Sugerí alternativas cercanas y preguntá por más detalles."
            )
    else:
        text_for_llm = (
            "Actuá como asistente inmobiliario para Dante Propiedades. "
            "Respondé la siguiente consulta de forma breve y profesional:\n" + user_text
        )
    try:
        resp = ollama.chat(
            model="llama3",
            messages=[{"role": "user", "content": text_for_llm}],
        )
        answer = resp["message"]["content"] if isinstance(resp, dict) and "message" in resp else str(resp)
    except Exception as e:
        answer = "Error en el motor de IA: " + str(e)
    return {"response": answer}
