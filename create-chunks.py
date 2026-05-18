from pypdf import PdfReader

docPath = "docs/Gaceta Conticinio Trujillo_260505_184820.pdf"

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

pdf_text = load_pdf(docPath)
text_chunks = chunk_text(pdf_text)
print(f"TOTAL DE CHUNKS CREADOS: {len(text_chunks)}")
