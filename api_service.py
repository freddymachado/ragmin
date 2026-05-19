import os
import requests
import json
from datetime import datetime
from pathlib import Path
import chromadb
import google.generativeai as genai
from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# --- Configuración de GenAI ---
GENAI_API_KEY = os.getenv("GENAI_API_KEY", "")
if not GENAI_API_KEY:
    print("WARNING: GENAI_API_KEY no encontrada en .env")
genai.configure(api_key=GENAI_API_KEY)

# --- Configuración de ChromaDB ---
# Usamos una ruta relativa al archivo para que funcione sin importar desde dónde se ejecute
DB_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")
print(f"Conectando a ChromaDB en: {DB_PATH}")

chroma = chromadb.PersistentClient(path=DB_PATH)
collection = chroma.get_or_create_collection("pdf_rag")

# --- Seguridad: API Key compartida con Vercel ---
# Esta clave debe estar en el .env local y en las variables de entorno de Vercel
SHARED_API_KEY = os.getenv("SHARED_API_KEY", "cambiame_por_algo_seguro")

# --- Configuración de Rate Limiting (3 solicitudes por minuto) ---
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="RAG Local API Service")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- Configuración de CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permitir todos los orígenes para desarrollo local
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QuestionRequest(BaseModel):
    question: str

# --- Configuración de logging ---
LOG_DIR = Path(os.path.dirname(__file__)) / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "api_requests.log"

def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"

def get_ip_info(ip: str) -> dict:
    if not ip or ip == "unknown":
        return {"error": "no ip available"}
    try:
        url = f"https://ip.guide/{ip}"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        return {
            "error": str(exc),
            "source": "ip.puide",
            "api_url": f"https://ip.puide.com/ip/{ip}"
        }

def parse_user_agent(user_agent: str) -> dict:
    info = {
        "raw": user_agent or "",
        "device_type": "unknown",
        "platform": "unknown",
        "browser": "unknown"
    }
    if not user_agent:
        return info

    ua = user_agent.lower()
    if "mobile" in ua or "android" in ua or "iphone" in ua:
        info["device_type"] = "mobile"
    elif "ipad" in ua or "tablet" in ua:
        info["device_type"] = "tablet"
    else:
        info["device_type"] = "desktop"

    if "windows" in ua:
        info["platform"] = "Windows"
    elif "macintosh" in ua or "mac os" in ua:
        info["platform"] = "macOS"
    elif "linux" in ua and "android" not in ua:
        info["platform"] = "Linux"
    elif "android" in ua:
        info["platform"] = "Android"
    elif "iphone" in ua or "ipad" in ua:
        info["platform"] = "iOS"

    if "chrome" in ua and "edg" not in ua and "chromium" not in ua:
        info["browser"] = "Chrome"
    elif "firefox" in ua:
        info["browser"] = "Firefox"
    elif "safari" in ua and "chrome" not in ua:
        info["browser"] = "Safari"
    elif "edg" in ua or "edge" in ua:
        info["browser"] = "Edge"
    elif "opera" in ua or "opr" in ua:
        info["browser"] = "Opera"
    elif "msie" in ua or "trident" in ua:
        info["browser"] = "Internet Explorer"

    return info

def write_log(entry: dict):
    try:
        with LOG_FILE.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"WARNING: no se pudo escribir el log: {exc}")

def log_request(request: Request, status_code: int, question: str = None, answer: str = None):
    client_ip = get_client_ip(request)
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "method": request.method,
        "path": request.url.path,
        "status_code": status_code,
        "client_ip": client_ip,
        "ip_info": get_ip_info(client_ip),
        "user_agent": request.headers.get("user-agent", ""),
        "device_info": parse_user_agent(request.headers.get("user-agent", "")),
        "question": question,
        "answer": answer,
    }
    write_log(log_entry)

def embed_text(text, model="nomic-embed-text"):
    """Genera embeddings usando Ollama local."""
    try:
        response = requests.post(
            "http://localhost:11434/api/embeddings",
            json={"model": model, "prompt": text}
        )
        return response.json()["embedding"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en Ollama: {str(e)}")

def retrieve(query, n=3):
    """Recupera fragmentos relevantes de ChromaDB."""
    print(f"Buscando fragmentos para: '{query}'")
    query_vec = embed_text(query) 
    results = collection.query(
        query_embeddings=[query_vec],
        n_results=n 
    )
    return results["documents"][0]

def ask_llm(question, context, model="gemini-3.1-flash-lite-preview"):
    """Consulta a Gemini con el contexto recuperado."""
    print(f"contexto: {context}")
    prompt = f"Usa el contexto siguiente: \n\n{context}\n\nPara resolver esta pregunta: {question}"
    model_client = genai.GenerativeModel(model)
    response = model_client.generate_content(prompt)
    return response.text

@app.post("/ask")
@limiter.limit("3/minute")
async def ask(
    request_data: QuestionRequest, 
    request: Request
):
    """Endpoint principal consumido por la web app."""
    try:
        # 1. Recuperar contexto
        context_docs = retrieve(request_data.question)
        context = "\n".join(context_docs)
        
        # 2. Generar respuesta con LLM
        if not context.strip():
            print("Aviso: El contexto está vacío. No hay documentos en la base de datos.")
            answer = "No hay documentos en la base de datos."
        else:            
            answer = ask_llm(request_data.question, context)
        
        response_data = {
            "status": "success",
            "answer": answer,
            "context_used": context_docs # Opcional: para depuración
        }
        log_request(request, status_code=200, question=request_data.question, answer=answer)
        return response_data
    except Exception as e:
        log_request(request, status_code=500, question=request_data.question, answer=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health(request: Request):
    log_request(request, status_code=200)
    return {"status": "online"}

if __name__ == "__main__":
    import uvicorn
    # Ejecutar en el puerto 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
