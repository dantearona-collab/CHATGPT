"""Backend para Dante Propiedades: procesamiento de consultas, filtros y generación de respuestas vía Gemini."""
import os
import re
import json
import sqlite3
from datetime import datetime
import requests
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import API_KEYS, ENDPOINT
from gemini.client import call_gemini_with_rotation
from routes.chat import router as chat_router

app = FastAPI()
app.include_router(chat_router)

@asynccontextmanager
async def lifespan(app):
    print("🔄 Iniciando ciclo de vida...")
    yield
    print("✅ Finalizando ciclo de vida...")

app = FastAPI(lifespan=lifespan)

app.include_router(chat_router)

@app.get("/status")
def status():
    test_prompt = "Respondé solo con OK"
    response = call_gemini_with_rotation(test_prompt)
    return {"gemini_api": "OK" if "OK" in response else response}


# Test de claves API al inicio
for i, key in enumerate(API_KEYS):
    test = call_gemini_with_rotation("Respondé solo con OK")
    print(f"🔑 Clave {i+1} ({key[:10]}...): {test}")
    
DB_PATH = os.path.join(os.path.dirname(__file__), "propiedades.db")
LOG_PATH = os.path.join(os.path.dirname(__file__), "conversaciones.db")

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

def cargar_propiedades_json(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Error al cargar {filename}: {e}")
        return []

def extraer_barrios(propiedades):
    return sorted(set(p.get("neighborhood", "").lower() for p in propiedades if p.get("neighborhood")))

def extraer_tipos(propiedades):
    return sorted(set(p.get("tipo", "").lower() for p in propiedades if p.get("tipo")))

def extraer_operaciones(propiedades):
    return sorted(set(p.get("operacion", "").lower() for p in propiedades if p.get("operacion")))

async def chat_endpoint(request: Request):
    data = await request.json()
    message = data.get("message")
    channel = data.get("channel", "web")

    respuesta = call_gemini_with_rotation(message)

    return {
        "mensaje_recibido": message,
        "respuesta_bot": respuesta
    }


@app.get("/debug/model")
def debug_model():
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": "Hola, ¿cómo estás?"}]}]
    }
    params = {"key": API_KEYS[0]}
    response = requests.post(ENDPOINT, headers=headers, params=params, json=payload, timeout=25)
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
            
        # ⚠️ TEMPORAL: Comentar el filtro por operación hasta que la BD tenga la columna
        # if filters.get("operacion"):
        #     where_clauses.append("operacion LIKE ?")
        #     params.append(f"%{filters['operacion']}%")
        
        if where_clauses:
            q += " WHERE " + " AND ".join(where_clauses)
    
    print(f"🔍 Query ejecutada: {q}")
    print(f"🔍 Parámetros: {params}")
    
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

from fastapi.responses import JSONResponse

@app.post("/chat")
async def chat(request: Request):
    try:
        data = await request.json()
        user_text = data.get("message", "").strip()
        channel = data.get("channel", "").strip()

        # 🔒 Validación del archivo JSON por canal
        filename = f"data/{channel}.json"
        if not os.path.exists(filename):
            return JSONResponse(
                content={
                    "error": f"❌ No existe el archivo: {filename}",
                    "canal_recibido": channel
                },
                media_type="application/json; charset=utf-8"
            )

        propiedades_json = cargar_propiedades_json(filename)
        barrios_disponibles = extraer_barrios(propiedades_json)
        tipos_disponibles = extraer_tipos(propiedades_json)
        operaciones_disponibles = extraer_operaciones(propiedades_json)

        historial = get_historial_canal(channel)
        contexto_historial = "\nHistorial reciente:\n" + "\n".join(f"- {m}" for m in historial)

        contexto_dinamico = (
            f"Barrios disponibles: {', '.join(barrios_disponibles)}.\n"
            f"Tipos de propiedad: {', '.join(tipos_disponibles)}.\n"
            f"Operaciones disponibles: {', '.join(operaciones_disponibles)}."
            "\nEjemplo: 'venta de departamento en Palermo' indica búsqueda de compra."
        )

        text_lower = user_text.lower()
        filters, results = None, None

        if any(k in text_lower for k in ["buscar", "mostrar", "propiedad", "departamento", "casa"]):
            filters = {}
            
            # Extraer barrio
            m_barrio = re.search(r"en ([a-zA-Záéíóúñ ]+)", text_lower)
            if m_barrio:
                filters["neighborhood"] = m_barrio.group(1).strip()

            # Extraer precio máximo
            m_price = re.search(r"hasta \$?\s*([0-9\.]+)", text_lower)
            if m_price:
                filters["max_price"] = int(m_price.group(1).replace('.', ''))

            # Extraer operación
            m_operacion = re.search(r"(venta|alquiler|temporario|comprar|alquilar)", text_lower)
            if m_operacion:
                op = m_operacion.group(1)
                filters["operacion"] = (
                    "venta" if op in ["venta", "comprar"] else
                    "alquiler" if op in ["alquiler", "alquilar"] else 
                    "temporario"
                )

            results = query_properties(filters)
            # 🧠 Generar prompt para Gemini
            prompt = build_prompt(
                user_text=user_text,
                results=results,
                filters=filters,
                channel=channel
            )

            # 🤖 Llamar a Gemini para obtener respuesta
            respuesta_bot = call_gemini_with_rotation(prompt)

            # 📝 Guardar en logs
            log_conversation(user_text, respuesta_bot, channel)
        # 🔍 Adaptar el tono según el canal
        if channel == "whatsapp":
            style_hint = "Respondé de forma breve, directa y cálida como si fuera un mensaje de WhatsApp."
        elif channel == "web":
            style_hint = "Respondé de forma explicativa, profesional y cálida como si fuera una consulta web."
        else:
            style_hint = "Respondé de forma clara y útil."

        prompt = build_prompt(user_text, results, filters, channel, style_hint + "\n" + contexto_dinamico + "\n" + contexto_historial)
        print("🧠 Prompt enviado a Gemini:\n", prompt)
        answer = call_gemini_with_rotation(prompt)

        # ✅ Normalizar caracteres problemáticos
        def normalizar_texto(texto):
            """Normaliza caracteres problemáticos"""
            if texto is None:
                return ""
            
            # Reemplazar caracteres problemáticos comunes
            reemplazos = {
                'Â¡': '¡', 'Â¿': '¿', 'Ã¡': 'á', 'Ã©': 'é', 
                'Ã­': 'í', 'Ã³': 'ó', 'Ãº': 'ú', 'Ã±': 'ñ',
                'Ã': 'í', '¢': 'ó', '£': 'ú', '¤': 'ñ',
                '¥': 'Á', '¦': 'É', '§': 'Í', '¨': 'Ó',
                '©': 'Ú', 'ª': 'Ñ', '«': '¡', '¬': '¿',
                'Â': ''  # Eliminar Â residual
            }
            
            texto_normalizado = texto
            for malo, bueno in reemplazos.items():
                texto_normalizado = texto_normalizado.replace(malo, bueno)
            
            return texto_normalizado

        # Aplicar normalización
        answer = normalizar_texto(answer)

        log_conversation(user_text, answer, channel)
        
        # ✅ SOLUCIÓN PRINCIPAL: Usar JSONResponse con encoding UTF-8 explícito
        return JSONResponse(
            content={"response": answer},
            media_type="application/json; charset=utf-8"
        )
    
    except Exception as e:
        return JSONResponse(
            content={"error": f"Error interno del servidor: {str(e)}"},
            media_type="application/json; charset=utf-8"
        )


if __name__ == "__main__":
    import uvicorn
    print("🎯 INICIANDO SERVIDOR DE DANTE PROPIEDADES...")
    print("🔗 URL: http://0.0.0.0:8000")
    print("📄 Docs: http://0.0.0.0:8000/docs")
    print("🌟 LISTO PARA RENDER.COM")
    print("#" * 50)
    
    uvicorn.run(
        "main:app", 
        host="0.0.0.0",      # ⭐ CAMBIAR de "127.0.0.1" a "0.0.0.0"
        port=8000, 
        reload=False         # ⭐ CAMBIAR de True a False (producción)
    )



# if __name__ == "__main__":
#     import uvicorn
#     print("✅ Iniciando servidor de Dante Propiedades...")
#     print("🔗 URL: http://127.0.0.1:8000")
#     print("📄 Docs: http://127.0.0.1:8000/docs")
#     print("*" * 50)
#     uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)