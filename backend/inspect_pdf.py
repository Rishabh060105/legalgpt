import os
from pypdf import PdfReader

# Configuration
DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "RAG document")
OUTPUT_FILE = "pdf_structure_dump.txt"

def inspect_pdf():
    if not os.path.exists(DOCS_DIR):
        print(f"Directory not found: {DOCS_DIR}")
        return

    pdf_files = [f for f in os.listdir(DOCS_DIR) if f.endswith('.pdf')]
    if not pdf_files:
        print("No PDF files found.")
        return

    target_pdf = os.path.join(DOCS_DIR, pdf_files[0])
    print(f"Inspecting: {target_pdf}")

    reader = PdfReader(target_pdf)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        # Dump first 50 pages to see structure
        for i in range(min(50, len(reader.pages))):
            text = reader.pages[i].extract_text()
            f.write(f"\n--- PAGE {i+1} ---\n")
            f.write(text)
            
    print(f"Dumped first 50 pages to {OUTPUT_FILE}")

if __name__ == "__main__":
    inspect_pdf()
