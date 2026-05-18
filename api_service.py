import os
import requests
import json
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

# Middleware simple para verificar la API Key
async def verify_api_key(x_api_key: str = Header(None)):
    if x_api_key != SHARED_API_KEY:
        raise HTTPException(
            status_code=403, 
            detail="Acceso denegado: API Key inválida o ausente."
        )
    return x_api_key



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
    request: Request, 
    x_api_key: str = Depends(verify_api_key)
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
        
        return {
            "status": "success",
            "answer": answer,
            "context_used": context_docs # Opcional: para depuración
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "online"}

if __name__ == "__main__":
    import uvicorn
    # Ejecutar en el puerto 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
