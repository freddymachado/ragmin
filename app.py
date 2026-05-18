from pypdf import PdfReader
import requests
import json
import chromadb

docPath = "docs/Gaceta Conticinio Trujillo_260505_184820.pdf"
chroma = chromadb.PersistentClient(path="./chroma_db")
collection = chroma.get_or_create_collection("pdf_rag")

def load_pdf(path):
    reader = PdfReader(path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def chunk_text(text, chunk_size=500, overlap=100):
    words = text.split()
    chunks = []
    start = 0

    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += chunk_size - overlap

    return chunks

def embed_text(text, model="nomic-embed-text"):
    response = requests.post(
        "http://localhost:11434/api/embeddings",
        json={"model":model, "prompt":text}
    )
    return response.json()["embedding"]

def index_pdf(path):
    text = load_pdf(path)
    chunks = chunk_text(text)

    for i, chunk in enumerate(chunks):
        vector = embed_text(chunk)
        collection.add(
            ids=[f"chunk_{i}"],
            embeddings=[vector],
            documents=[chunk]
        )
    return chunks
    

chunks = index_pdf(docPath)
print(f"Chunks indexados: {len(chunks)}")

