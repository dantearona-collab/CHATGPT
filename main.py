"""Backend para Dante Propiedades: procesamiento de consultas, filtros y generación de respuestas vía Gemini."""
import os
import re
import json
import sqlite3
import requests
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime
from config import API_KEYS, ENDPOINT
from gemini.client import call_gemini_with_rotation

@asynccontextmanager
async def lifespan(app):
    print("🔄 Iniciando ciclo de vida...")
    yield
    print("✅ Finalizando ciclo de vida...")

# ✅ APP PRINCIPAL
app = FastAPI(lifespan=lifespan)

# ✅ CONFIGURACIONES
DB_PATH = os.path.join(os.path.dirname(__file__), "propiedades.db")
LOG_PATH = os.path.join(os.path.dirname(__file__), "conversaciones.db")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ FUNCIONES
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

def get_historial_canal(canal="web", limite=3):
    try:
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
    except:
        return []

def query_properties(filters=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        q = "SELECT id, title, neighborhood, price, rooms, sqm, description FROM properties"
        params = []
        
        if filters:
            where_clauses = []
            
            if filters.get("neighborhood"):
                where_clauses.append("LOWER(neighborhood) LIKE LOWER(?)")
                params.append(f"%{filters['neighborhood']}%")
                
            if filters.get("min_price") is not None:
                where_clauses.append("price >= ?")
                params.append(filters["min_price"])
                
            if filters.get("max_price") is not None:
                where_clauses.append("price <= ?")
                params.append(filters["max_price"])
                
            if filters.get("operacion"):
                where_clauses.append("LOWER(operacion) LIKE LOWER(?)")
                params.append(f"%{filters['operacion']}%")
            
            if filters.get("min_rooms") is not None:
                where_clauses.append("rooms >= ?")
                params.append(filters["min_rooms"])
                
            if where_clauses:
                q += " WHERE " + " AND ".join(where_clauses)
        
        print(f"🔍 Query ejecutada: {q}")
        print(f"🔍 Parámetros: {params}")
        
        cur.execute(q, params)
        rows = cur.fetchall()
        conn.close()
        
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"❌ Error en query_properties: {e}")
        return []

def build_prompt(user_text, results=None, filters=None, channel="web", style_hint=""):
    whatsapp_tone = channel == "whatsapp"
    
    if results is not None and results:
        bullets = [
            f"{r['title']} — {r['neighborhood']} — ${r['price']} — {r['rooms']} amb — {r['sqm']} m2"
            for r in results[:8]
        ]
        return (
            style_hint + f"\n\nEl usuario está buscando propiedades para {filters.get('operacion', 'consultar')} en {filters.get('neighborhood', 'varios barrios')}. Aquí hay resultados relevantes:\n"
            + "\n".join(bullets)
            + "\n\nRedactá una respuesta cálida y profesional que resuma los resultados, "
            "ofrezca ayuda personalizada y sugiera continuar la conversación por WhatsApp. "
            "Cerrá con un agradecimiento y tono amable."
            + ("\nUsá emojis si el canal es WhatsApp." if whatsapp_tone else "")
        )
    elif results is not None:
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
    try:
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
    except Exception as e:
        print(f"❌ Error en log: {e}")

# ✅ ENDPOINTS
@app.get("/status")
def status():
    test_prompt = "Respondé solo con OK"
    response = call_gemini_with_rotation(test_prompt)
    return {"gemini_api": "OK" if "OK" in response else response}

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
    try:
        conn = sqlite3.connect(LOG_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT timestamp, channel, user_message, bot_response FROM logs ORDER BY id DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except:
        return []

@app.post("/chat")
async def chat(request: Request):
    try:
        data = await request.json()
        user_text = data.get("message", "").strip()
        channel = data.get("channel", "web").strip()

        print(f"📥 Mensaje recibido: {user_text}")
        print(f"📱 Canal: {channel}")

        # 🔓 Validación flexible de archivos JSON
        filename = f"data/{channel}.json"
        if not os.path.exists(filename):
            filename = "data/web.json"
            print(f"⚠️ Usando archivo por defecto: {filename}")

        propiedades_json = cargar_propiedades_json("properties.json")
        barrios_disponibles = extraer_barrios(propiedades_json)
        tipos_disponibles = extraer_tipos(propiedades_json)
        operaciones_disponibles = extraer_operaciones(propiedades_json)
        

        historial = get_historial_canal(channel)
        contexto_historial = "\nHistorial reciente:\n" + "\n".join(f"- {m}" for m in historial) if historial else ""

        contexto_dinamico = (
            f"Barrios disponibles: {', '.join(barrios_disponibles)}.\n"
            f"Tipos de propiedad: {', '.join(tipos_disponibles)}.\n"
            f"Operaciones disponibles: {', '.join(operaciones_disponibles)}."
        )

        text_lower = user_text.lower()
        filters, results = None, None

        # 🔓 DETECCIÓN DE BÚSQUEDA MEJORADA
        if any(k in text_lower for k in ["buscar", "mostrar", "propiedad", "departamento", "casa", "inmueble", "alquiler", "venta", "precio", "barrio", "necesito", "quiero"]):
            print("🎯 Activando búsqueda con filtros...")
            filters = {}
            
            # Extraer barrio
            barrio_patterns = [
                r"en ([a-zA-Záéíóúñ ]+)",
                r"barrio ([a-zA-Záéíóúñ ]+)",
                r"zona ([a-zA-Záéíóúñ ]+)",
                r"de ([a-zA-Záéíóúñ ]+)$"
            ]
            
            for pattern in barrio_patterns:
                m_barrio = re.search(pattern, text_lower)
                if m_barrio:
                    filters["neighborhood"] = m_barrio.group(1).strip()
                    print(f"📍 Barrio detectado: {filters['neighborhood']}")
                    break
            
            # Extraer precios
            price_patterns = [
                r"hasta \$?\s*([0-9\.]+)",
                r"máximo \$?\s*([0-9\.]+)",
                r"precio.*?\$?\s*([0-9\.]+)",
                r"menos de \$?\s*([0-9\.]+)"
            ]
            
            for pattern in price_patterns:
                m_price = re.search(pattern, text_lower)
                if m_price:
                    filters["max_price"] = int(m_price.group(1).replace('.', ''))
                    print(f"💰 Precio máximo detectado: {filters['max_price']}")
                    break
            
            # Extraer precio mínimo
            m_min_price = re.search(r"desde \$?\s*([0-9\.]+)", text_lower)
            if m_min_price:
                filters["min_price"] = int(m_min_price.group(1).replace('.', ''))
                print(f"💰 Precio mínimo detectado: {filters['min_price']}")
            
            # Extraer ambientes
            m_rooms = re.search(r"(\d+)\s*amb", text_lower)
            if m_rooms:
                filters["min_rooms"] = int(m_rooms.group(1))
                print(f"🚪 Ambientes detectados: {filters['min_rooms']}")
            
            # Extraer operación
            op_patterns = [
                r"(venta|comprar|compro|vendo)",
                r"(alquiler|alquilar|alquilo)",
                r"(temporario|temporal|temporada)"
            ]
            
            for pattern in op_patterns:
                m_operacion = re.search(pattern, text_lower)
                if m_operacion:
                    op = m_operacion.group(1)
                    filters["operacion"] = (
                        "venta" if op in ["venta", "comprar", "compro", "vendo"] else
                        "alquiler" if op in ["alquiler", "alquilar", "alquilo"] else 
                        "temporario"
                    )
                    print(f"🏢 Operación detectada: {filters['operacion']}")
                    break

            # EJECUTAR BÚSQUEDA
            results = query_properties(filters)
            print(f"📊 Resultados encontrados: {len(results)}")

        # Tono según canal
        if channel == "whatsapp":
            style_hint = "Respondé de forma breve, directa y cálida como si fuera un mensaje de WhatsApp."
        else:
            style_hint = "Respondé de forma explicativa, profesional y cálida como si fuera una consulta web."

        prompt = build_prompt(user_text, results, filters, channel, style_hint + "\n" + contexto_dinamico + "\n" + contexto_historial)
        print("🧠 Prompt enviado a Gemini")
        
        answer = call_gemini_with_rotation(prompt)
        log_conversation(user_text, answer, channel)
        
        return JSONResponse(
            content={"response": answer},
            media_type="application/json; charset=utf-8"
        )
    
    except Exception as e:
        error_message = "Lo siento, hubo un problema procesando tu consulta. Por favor, intentá de nuevo."
        print(f"❌ Error: {str(e)}")
        
        return JSONResponse(
            content={"response": error_message},
            media_type="application/json; charset=utf-8"
        )

# ✅ INICIO
if __name__ == "__main__":
    import uvicorn
    
    print("🔑 Probando claves API...")
    for i, key in enumerate(API_KEYS):
        try:
            test = call_gemini_with_rotation("Respondé solo con OK")
            print(f"🔑 Clave {i+1}: {test}")
        except Exception as e:
            print(f"❌ Error con clave {i+1}: {e}")
    
    port = int(os.environ.get("PORT", 8000))
    print(f"🎯 Servidor en: http://127.0.0.1:{port}")
    
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)