from pypdf import PdfReader

docPath = "docs/Gaceta Conticinio Trujillo_260505_184820.pdf"

def load_pdf(path):
    reader = PdfReader(path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

pdf_text = load_pdf(docPath)
print(pdf_text)