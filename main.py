"""Backend para Dante Propiedades: procesamiento de consultas, filtros y generación de respuestas vía Gemini."""
import os
import re
import json
import sqlite3
import requests
import time
from functools import lru_cache
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from config import API_KEYS, ENDPOINT
from gemini.client import call_gemini_with_rotation

def diagnosticar_problemas():
    """Función de diagnóstico"""
    print("🔍 INICIANDO DIAGNÓSTICO...")
    
    # 1. Verificar archivos
    print("1. 📁 Verificando archivos...")
    archivos = os.listdir('.')
    print(f"   Archivos en directorio actual: {archivos}")
    
    # 2. Verificar properties.json
    if os.path.exists("properties.json"):
        try:
            with open("properties.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                print(f"   ✅ properties.json: {len(data)} propiedades encontradas")
        except Exception as e:
            print(f"   ❌ Error leyendo properties.json: {e}")
    else:
        print("   ❌ properties.json NO EXISTE")
    
    # 3. Verificar config
    try:
        from config import API_KEYS, ENDPOINT
        print(f"   ✅ Config: {len(API_KEYS)} API keys cargadas")
        print(f"   ✅ Endpoint: {ENDPOINT}")
    except Exception as e:
        print(f"   ❌ Error cargando config: {e}")
    
    # 4. Verificar gemini client
    try:
        from gemini.client import call_gemini_with_rotation
        print("   ✅ Gemini client importado correctamente")
    except Exception as e:
        print(f"   ❌ Error importando gemini client: {e}")

# Ejecutar diagnóstico inmediatamente
diagnosticar_problemas()



# ✅ MODELOS DE DATOS PYDANTIC
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, description="Mensaje del usuario")
    channel: str = Field(default="web", description="Canal de comunicación (web, whatsapp, etc.)")
    filters: Optional[Dict[str, Any]] = Field(default=None, description="Filtros aplicados desde el frontend")

class ChatResponse(BaseModel):
    response: str = Field(..., description="Respuesta del asistente")
    results_count: Optional[int] = Field(None, description="Número de propiedades encontradas")
    search_performed: bool = Field(..., description="Indica si se realizó una búsqueda")

class PropertyResponse(BaseModel):
    id: int
    title: str
    neighborhood: str
    price: float
    rooms: int
    sqm: float
    description: str

# ✅ MÉTRICAS Y ESTADÍSTICAS
class Metrics:
    def __init__(self):
        self.requests_count = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.gemini_calls = 0
        self.search_queries = 0
        self.start_time = time.time()
    
    def increment_requests(self):
        self.requests_count += 1
    
    def increment_success(self):
        self.successful_requests += 1
    
    def increment_failures(self):
        self.failed_requests += 1
    
    def increment_gemini_calls(self):
        self.gemini_calls += 1
    
    def increment_searches(self):
        self.search_queries += 1
    
    def get_uptime(self):
        return time.time() - self.start_time

# ✅ INICIALIZACIÓN
metrics = Metrics()

@asynccontextmanager
async def lifespan(app):
    print("🔄 Iniciando ciclo de vida...")
    # Inicialización de bases de datos y recursos
    initialize_databases()
    yield
    print("✅ Finalizando ciclo de vida...")

# ✅ APP PRINCIPAL
app = FastAPI(
    lifespan=lifespan,
    title="Dante Propiedades API",
    description="Backend para procesamiento de consultas y filtros de propiedades",
    version="1.0.0"
)

# ✅ CONFIGURACIONES
DB_PATH = os.path.join(os.path.dirname(__file__), "propiedades.db")
LOG_PATH = os.path.join(os.path.dirname(__file__), "conversaciones.db")
CACHE_DURATION = 300  # 5 minutos para cache

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ CACHE PARA CONSULTAS FRECUENTES
query_cache = {}

def get_cache_key(filters: Dict[str, Any]) -> str:
    """Genera una clave única para el cache basada en los filtros"""
    return json.dumps(filters, sort_keys=True)

def cache_query_results(filters: Dict[str, Any], results: List[Dict]):
    """Almacena resultados en cache"""
    cache_key = get_cache_key(filters)
    query_cache[cache_key] = {
        'results': results,
        'timestamp': time.time()
    }

def get_cached_results(filters: Dict[str, Any]) -> Optional[List[Dict]]:
    """Obtiene resultados del cache si están disponibles y no han expirado"""
    cache_key = get_cache_key(filters)
    cached = query_cache.get(cache_key)
    
    if cached and (time.time() - cached['timestamp']) < CACHE_DURATION:
        return cached['results']
    return None

# ✅ FUNCIONES MEJORADAS
def cargar_propiedades_a_db():
    """Carga las propiedades del JSON a la base de datos SQLite"""
    try:
        propiedades = cargar_propiedades_json("properties.json")
        if not propiedades:
            print("❌ No hay propiedades para cargar")
            return
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Limpiar tabla existente
        cur.execute("DELETE FROM properties")
        
        # Insertar nuevas propiedades
        for prop in propiedades:
            cur.execute('''
                INSERT INTO properties (id, title, neighborhood, price, rooms, sqm, description, operacion, tipo, direccion, antiguedad, estado, orientacion, piso, expensas, amenities, cochera, balcon, pileta, acepta_mascotas, aire_acondicionado, info_multimedia)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                prop.get('id'),
                prop.get('title'),
                prop.get('neighborhood'),
                prop.get('price'),
                prop.get('rooms'),
                prop.get('sqm'),
                prop.get('description'),
                prop.get('operacion'),
                prop.get('tipo'),
                prop.get('direccion'),
                prop.get('antiguedad'),
                prop.get('estado'),
                prop.get('orientacion'),
                prop.get('piso'),
                prop.get('expensas'),
                prop.get('amenities'),
                prop.get('cochera'),
                prop.get('balcon'),
                prop.get('pileta'),
                prop.get('acepta_mascotas'),
                prop.get('aire_acondicionado'),
                prop.get('info_multimedia')
            ))
        
        conn.commit()
        conn.close()
        print(f"✅ {len(propiedades)} propiedades cargadas en la base de datos")
        
    except Exception as e:
        print(f"❌ Error cargando propiedades a DB: {e}")



def initialize_databases():
    """Inicializa las bases de datos si no existen"""
    try:
        # 🔥 FORZAR ELIMINACIÓN DE BASES DE DATOS VIEJAS EN RENDER
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
            print("🗑️ Base de datos propiedades eliminada forzadamente")
        if os.path.exists(LOG_PATH):
            os.remove(LOG_PATH)
            print("🗑️ Base de datos logs eliminada forzadamente")
        
        # Base de datos de logs (NUEVO ESQUEMA)
        conn = sqlite3.connect(LOG_PATH)
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                channel TEXT,
                user_message TEXT,
                bot_response TEXT,
                response_time REAL,
                search_performed BOOLEAN DEFAULT 0,
                results_count INTEGER DEFAULT 0
            )
        ''')
        conn.commit()
        conn.close()
        
        # Base de datos de propiedades (NUEVO ESQUEMA COMPLETO)
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS properties (
                id INTEGER PRIMARY KEY,
                title TEXT,
                neighborhood TEXT,
                price REAL,
                rooms INTEGER,
                sqm REAL,
                description TEXT,
                operacion TEXT,
                tipo TEXT,
                direccion TEXT,
                antiguedad TEXT,
                estado TEXT,
                orientacion TEXT,
                piso TEXT,
                expensas TEXT,
                amenities TEXT,
                cochera TEXT,
                balcon TEXT,
                pileta TEXT,
                acepta_mascotas TEXT,
                aire_acondicionado TEXT,
                info_multimedia TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

        # ✅ CARGAR PROPIEDADES DESDE JSON
        cargar_propiedades_a_db()
        
        print("✅ Bases de datos inicializadas correctamente con nuevo esquema")
    except Exception as e:
        print(f"❌ Error inicializando bases de datos: {e}")

def cargar_propiedades_json(filename):
    try:
        # Usar utf-8-sig que maneja automáticamente el BOM
        with open(filename, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"⚠️ Archivo {filename} no encontrado")
        return []
    except json.JSONDecodeError as e:
        print(f"⚠️ Error decodificando JSON en {filename}: {e}")
        return []
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
    except Exception as e:
        print(f"❌ Error obteniendo historial: {e}")
        return []

def get_last_bot_response(channel="web"):
    try:
        conn = sqlite3.connect(LOG_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT bot_response FROM logs WHERE channel = ? ORDER BY id DESC LIMIT 1",
            (channel,)
        )
        row = cur.fetchone()
        conn.close()
        return row["bot_response"] if row else None
    except Exception as e:
        print(f"❌ Error obteniendo la última respuesta del bot: {e}")
        return None

@lru_cache(maxsize=100)
def query_properties_cached(filters_json: str):
    """Versión cacheada de query_properties"""
    filters = json.loads(filters_json) if filters_json else {}
    return query_properties(filters)

def query_properties(filters=None):
    try:
        # Verificar cache primero
        if filters:
            cached_results = get_cached_results(filters)
            if cached_results is not None:
                print("🔍 Usando resultados cacheados")
                return cached_results
        
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        q = "SELECT id, title, neighborhood, price, rooms, sqm, description, operacion, tipo, direccion, antiguedad, estado, orientacion, piso, expensas, amenities, cochera, balcon, pileta, acepta_mascotas, aire_acondicionado, info_multimedia FROM properties"
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
                
            if filters.get("tipo"):
                where_clauses.append("LOWER(tipo) LIKE LOWER(?)")
                params.append(f"%{filters['tipo']}%")
                
            if filters.get("min_sqm") is not None:
                where_clauses.append("sqm >= ?")
                params.append(filters["min_sqm"])
                
            if filters.get("max_sqm") is not None:
                where_clauses.append("sqm <= ?")
                params.append(filters["max_sqm"])
                
            if where_clauses:
                q += " WHERE " + " AND ".join(where_clauses)
        
        q += " ORDER BY price ASC LIMIT 50"
        
        print(f"🔍 Query ejecutada: {q}")
        print(f"🔍 Parámetros: {params}")
        
        cur.execute(q, params)
        rows = cur.fetchall()
        conn.close()
        
        results = [dict(r) for r in rows]
        
        # Almacenar en cache si hay filtros
        if filters and results:
            cache_query_results(filters, results)
        
        return results
    except Exception as e:
        print(f"❌ Error en query_properties: {e}")
        return []

def build_prompt(user_text, results=None, filters=None, channel="web", style_hint="", property_details=None):
    whatsapp_tone = channel == "whatsapp"

    if property_details:
        details = "\n".join([f"- {key.replace('_', ' ').capitalize()}: {value}" for key, value in property_details.items()])
        return (
            style_hint + f"\n\nEl usuario está pidiendo más detalles sobre la propiedad '{property_details['title']}'. Aquí están todos los detalles de la propiedad:\n"
            + details
            + "\n\nRedactá una respuesta cálida y profesional que presente estos detalles de forma clara y atractiva. "
            "Ofrecé ayuda personalizada y sugerí continuar la conversación por WhatsApp. "
            "Cerrá con un agradecimiento y tono amable."
            + ("\nUsá emojis si el canal es WhatsApp." if whatsapp_tone else "")
        )
    
    if results is not None and results:
        bullets = [
            f"{r['title']} — {r['neighborhood']} — ${r['price']:,.0f} — {r['rooms']} amb — {r['sqm']} m2"
            for r in results[:8]
        ]
        return (
            style_hint + f"\n\nEl usuario está buscando propiedades con los siguientes filtros: {filters}. Aquí hay resultados relevantes:\n"
            + "\n".join(bullets)
            + "\n\nRedactá una respuesta cálida y profesional que resuma los resultados, "
            "ofrezca ayuda personalizada y sugiera continuar la conversación por WhatsApp. "
            "Cerrá con un agradecimiento y tono amable."
            + ("\nUsá emojis si el canal es WhatsApp." if whatsapp_tone else "")
        )
    elif results is not None:
        return (
            f"{style_hint}\n\nEl usuario busca propiedades con estos filtros: {filters} pero no hay resultados. "
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

def log_conversation(user_text, response_text, channel="web", response_time=0.0, search_performed=False, results_count=0):
    try:
        conn = sqlite3.connect(LOG_PATH)
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO logs (timestamp, channel, user_message, bot_response, response_time, search_performed, results_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (datetime.now().isoformat(), channel, user_text, response_text, response_time, search_performed, results_count))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Error en log: {e}")

def detect_filters(text_lower: str) -> Dict[str, Any]:
    """Detecta y extrae filtros del texto del usuario"""
    filters = {}
    
    # Mapeo de palabras clave a filtros
    barrio_keywords = ['palermo', 'recoleta', 'belgrano', 'almagro', 'caballito', 'microcentro', 'balvanera']
    operacion_keywords = {
        'alquiler': 'alquiler',
        'alquilar': 'alquiler', 
        'renta': 'alquiler',
        'venta': 'venta',
        'comprar': 'venta',
        'compra': 'venta',
        'vender': 'venta'
    }
    tipo_keywords = {
        'departamento': 'departamento',
        'depto': 'departamento',
        'casa': 'casa',
        'ph': 'ph',
        'casaquinta': 'casaquinta',
        'terreno': 'terreno',
        'terrenos': 'terreno'
    }
    
    # Detectar barrio por palabras clave exactas
    for barrio in barrio_keywords:
        if barrio in text_lower:
            filters["neighborhood"] = barrio
            print(f"📍 Barrio detectado (keyword): {filters['neighborhood']}")
            break
    
    # Detectar operación
    for keyword, operacion in operacion_keywords.items():
        if keyword in text_lower:
            filters["operacion"] = operacion
            print(f"🏢 Operación detectada: {filters['operacion']}")
            break
    
    # Detectar tipo de propiedad
    for keyword, tipo in tipo_keywords.items():
        if keyword in text_lower:
            filters["tipo"] = tipo
            print(f"🏠 Tipo detectado: {filters['tipo']}")
            break
    
    # Extraer barrio con patrones regex (como respaldo)
    if "neighborhood" not in filters:
        barrio_patterns = [
            r"en ([a-zA-Záéíóúñ ]+)",
            r"barrio ([a-zA-Záéíóúñ ]+)",
            r"zona ([a-zA-Záéíóúñ ]+)",
            r"de ([a-zA-Záéíóúñ ]+)$"
        ]
        
        for pattern in barrio_patterns:
            m_barrio = re.search(pattern, text_lower)
            if m_barrio:
                potential_neighborhood = m_barrio.group(1).strip()
                if potential_neighborhood not in operacion_keywords:
                    filters["neighborhood"] = potential_neighborhood
                    print(f"📍 Barrio detectado (regex): {filters['neighborhood']}")
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

    return filters

# ✅ ENDPOINTS MEJORADOS
@app.get("/status")
def status():
    """Endpoint de estado del servicio"""
    test_prompt = "Respondé solo con OK"
    try:
        response = call_gemini_with_rotation(test_prompt)
        gemini_status = "OK" if "OK" in response else "ERROR"
    except Exception as e:
        gemini_status = f"ERROR: {str(e)}"
    
    return {
        "status": "activo",
        "gemini_api": gemini_status,
        "uptime_seconds": metrics.get_uptime(),
        "total_requests": metrics.requests_count,
        "successful_requests": metrics.successful_requests,
        "failed_requests": metrics.failed_requests,
        "gemini_calls": metrics.gemini_calls,
        "search_queries": metrics.search_queries
    }

@app.get("/")
def root():
    return {
        "status": "Backend activo",
        "endpoint": "/chat",
        "método": "POST",
        "uso": "Enviar mensaje como JSON: { message: '...', channel: 'web', filters: {...} }",
        "documentación": "/docs"
    }

@app.get("/logs")
def get_logs(limit: int = 10, channel: Optional[str] = None):
    """Obtiene logs de conversaciones con filtros opcionales"""
    try:
        conn = sqlite3.connect(LOG_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        if channel:
            cur.execute(
                "SELECT timestamp, channel, user_message, bot_response, response_time, search_performed, results_count FROM logs WHERE channel = ? ORDER BY id DESC LIMIT ?",
                (channel, limit)
            )
        else:
            cur.execute(
                "SELECT timestamp, channel, user_message, bot_response, response_time, search_performed, results_count FROM logs ORDER BY id DESC LIMIT ?",
                (limit,)
            )
        
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo logs: {str(e)}")

@app.get("/properties")
def get_properties(
    neighborhood: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_rooms: Optional[int] = None,
    operacion: Optional[str] = None,
    tipo: Optional[str] = None,
    min_sqm: Optional[float] = None,
    max_sqm: Optional[float] = None,
    limit: int = 20
):
    """Endpoint directo para buscar propiedades con filtros"""
    filters = {}
    if neighborhood:
        filters["neighborhood"] = neighborhood
    if min_price is not None:
        filters["min_price"] = min_price
    if max_price is not None:
        filters["max_price"] = max_price
    if min_rooms is not None:
        filters["min_rooms"] = min_rooms
    if operacion:
        filters["operacion"] = operacion
    if tipo:
        filters["tipo"] = tipo
    if min_sqm is not None:
        filters["min_sqm"] = min_sqm
    if max_sqm is not None:
        filters["max_sqm"] = max_sqm
    
    results = query_properties(filters)
    return {
        "count": len(results),
        "filters": filters,
        "properties": results[:limit]
    }

@app.get("/debug")
def debug_info():
    """Endpoint de diagnóstico para producción"""
    info = {
        "directorio_actual": os.getcwd(),
        "archivos": os.listdir('.'),
        "existe_properties_json": os.path.exists("properties.json"),
        "existe_config_py": os.path.exists("config.py"),
        "variables_entorno": {
            "GEMINI_API_KEYS": "SET" if os.environ.get("GEMINI_API_KEYS") else "MISSING",
            "PORT": os.environ.get("PORT", "8000")
        },
        "base_datos": {
            "existe_db": os.path.exists(DB_PATH),
            "existe_logs": os.path.exists(LOG_PATH)
        }
    }
    
    # Verificar properties.json
    if os.path.exists("properties.json"):
        try:
            with open("properties.json", "r", encoding="utf-8") as f:
                props = json.load(f)
                info["properties_json"] = f"{len(props)} propiedades"
        except Exception as e:
            info["properties_json"] = f"Error: {e}"
    
    return info




@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Endpoint principal para chat con el asistente inmobiliario"""
    start_time = time.time()
    metrics.increment_requests()
    
    try:
        user_text = request.message.strip()
        channel = request.channel.strip()
        filters_from_frontend = request.filters if request.filters else {}

        if not user_text:
            raise HTTPException(status_code=400, detail="El mensaje no puede estar vacío")

        print(f"📥 Mensaje recibido: {user_text}")
        print(f"📱 Canal: {channel}")
        print(f"🎯 Filtros del frontend: {filters_from_frontend}")

        # Cargar datos de propiedades desde JSON
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
        filters, results = {}, None
        search_performed = False
        property_details = None

        # Check if user is asking for more details
        if any(keyword in text_lower for keyword in ["caracteristicas", "detalles", "mas informacion", "más información"]):
            # Try to find the property from the conversation history
            if historial:
                last_bot_response = get_last_bot_response(channel)
                if last_bot_response:
                    # Extract property title from last bot response
                    match = re.search(r"\* \*\*(.*?):\*\*", last_bot_response)
                    if match:
                        property_title = match.group(1)
                        # Get property details from the database
                        conn = sqlite3.connect(DB_PATH)
                        conn.row_factory = sqlite3.Row
                        cur = conn.cursor()
                        cur.execute("SELECT * FROM properties WHERE title = ?", (property_title,))
                        row = cur.fetchone()
                        if row:
                            property_details = dict(row)
                        conn.close()

        # 🔥 COMBINAR FILTROS: frontend + detección automática
        
        # 1. Agregar filtros del frontend si existen
        if filters_from_frontend:
            filters.update(filters_from_frontend)
            print(f"🎯 Filtros aplicados desde frontend: {filters_from_frontend}")
        
        # 2. Detectar filtros adicionales del texto
        detected_filters = detect_filters(text_lower)
        if detected_filters:
            filters.update(detected_filters)
            print(f"🎯 Filtros detectados del texto: {detected_filters}")

        # Si hay filtros, realizar búsqueda
        if filters and not property_details:
            print("🎯 Activando búsqueda con filtros combinados...")
            search_performed = True
            metrics.increment_searches()
            
            results = query_properties(filters)
            print(f"📊 Resultados encontrados: {len(results)}")

        # Tono según canal
        if channel == "whatsapp":
            style_hint = "Respondé de forma breve, directa y cálida como si fuera un mensaje de WhatsApp."
        else:
            style_hint = "Respondé de forma explicativa, profesional y cálida como si fuera una consulta web."

        prompt = build_prompt(user_text, results, filters, channel, style_hint + "\n" + contexto_dinamico + "\n" + contexto_historial, property_details)
        print("🧠 Prompt enviado a Gemini")
        
        metrics.increment_gemini_calls()
        answer = call_gemini_with_rotation(prompt)
        
        response_time = time.time() - start_time
        log_conversation(user_text, answer, channel, response_time, search_performed, len(results) if results else 0)
        metrics.increment_success()
        
        return ChatResponse(
            response=answer,
            results_count=len(results) if results else None,
            search_performed=search_performed
        )
    
    except HTTPException:
        metrics.increment_failures()
        raise
    except Exception as e:
        metrics.increment_failures()
  # ✅ MOSTRAR EL ERROR REAL EN CONSOLA
        import traceback
        print(f"❌ ERROR DETALLADO en endpoint /chat:")
        print(f"❌ Tipo: {type(e).__name__}")
        print(f"❌ Mensaje: {str(e)}")
        print(f"❌ Traceback completo:")
        traceback.print_exc()
        
        # Respuesta temporal para debugging
        error_message = f"🔧 ERROR ESPECÍFICO: {type(e).__name__}: {str(e)}"
        
        return ChatResponse(
            response=error_message,
            search_performed=False
        )

@app.get("/metrics")
def get_metrics():
    """Endpoint para obtener métricas del servicio"""
    return {
        "uptime_seconds": metrics.get_uptime(),
        "requests_per_second": metrics.requests_count / max(metrics.get_uptime(), 1),
        "success_rate": metrics.successful_requests / max(metrics.requests_count, 1),
        "total_requests": metrics.requests_count,
        "successful_requests": metrics.successful_requests,
        "failed_requests": metrics.failed_requests,
        "gemini_calls": metrics.gemini_calls,
        "search_queries": metrics.search_queries,
        "cache_size": len(query_cache)
    }

@app.delete("/cache")
def clear_cache():
    """Limpia el cache de consultas"""
    query_cache.clear()
    query_properties_cached.cache_clear()
    return {"message": "Cache limpiado correctamente"}

# ✅ DOCUMENTACIÓN PERSONALIZADA
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="Dante Propiedades API",
        version="1.0.0",
        description="Backend para procesamiento de consultas y filtros de propiedades con IA",
        routes=app.routes,
    )
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# ✅ INICIO
if __name__ == "__main__":
    import uvicorn
    
    print("🚀 INICIANDO EN MODO PRODUCCIÓN/RENDER")
    print(f"🔍 Directorio: {os.getcwd()}")
    print(f"🔍 Archivos: {os.listdir('.')}")
    
    # Diagnóstico completo
    diagnosticar_problemas()
    
    port = int(os.environ.get("PORT", 8000))
    print(f"🎯 Servidor iniciando en puerto: {port}")
    
    # En producción, reload=False
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=port, 
        reload=False,  # ⚠️ IMPORTANTE: False en producción
        access_log=True
    )