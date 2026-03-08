import os
import chromadb
from chromadb.utils import embedding_functions
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
import re

# Paths
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
# Handle spaces in folder name "RAG document"
DATA_DIR = os.path.join(BACKEND_DIR, "..", "RAG document")
CHROMA_DB_DIR = os.path.join(BACKEND_DIR, "chroma_db")

def extract_section(text):
    # Pattern to find "Section 123" or "Sec. 123"
    match = re.search(r"(?:Section|Sec\.?)\s+(\d+)", text, re.IGNORECASE)
    if match:
        return f"Section {match.group(1)}"
    return None

def ingest_documents():
    print(f"Initializing ChromaDB at {CHROMA_DB_DIR}...")
    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    
    print("Loading embedding model (all-MiniLM-L6-v2)...")
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    
    # recreate collection to clean up old chunks
    try:
        client.delete_collection(name="legal_docs")
        print("Deleted existing collection.")
    except:
        pass

    collection = client.get_or_create_collection(
        name="legal_docs",
        embedding_function=ef
    )

    # Secondary splitter for long sections
    char_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

    if not os.path.exists(DATA_DIR):
        print(f"Data directory not found: {DATA_DIR}")
        return

    print(f"Scanning {DATA_DIR} for documents...")
    
    documents = []
    metadatas = []
    ids = []
    
    # Regex to find "123. Title.—"
    # Matches: start of line, digits, dot, space, title chars, dot-dash
    SECTION_PATTERN = re.compile(r"\n(\d+)\.\s+([A-Za-z\s,]+)\.—")

    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".pdf"):
            filepath = os.path.join(DATA_DIR, filename)
            print(f"Processing {filename}...")
            
            try:
                reader = PdfReader(filepath)
                full_text = ""
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        full_text += text + "\n"
                
                # Find all section matches
                matches = list(SECTION_PATTERN.finditer(full_text))
                print(f"  - Found {len(matches)} logical sections")

                if not matches:
                    sub_chunks = char_splitter.split_text(full_text)
                    for j, sub_chunk in enumerate(sub_chunks):
                        documents.append(sub_chunk)
                        metadatas.append({
                            "source": filename,
                            "section": "Entire Document",
                            "title": "Document Text",
                            "chunk_id": f"part{j}",
                            "type": "document_part"
                        })
                        ids.append(f"{filename}_part{j}")
                else:
                    for i, match in enumerate(matches):
                        sec_num = match.group(1)
                    sec_title = match.group(2).strip()
                    
                    start_idx = match.start()
                    # End at the start of the next match, or end of text
                    end_idx = matches[i+1].start() if i + 1 < len(matches) else len(full_text)
                    
                    section_text = full_text[start_idx:end_idx].strip()
                    
                    # If section is too long, split it further
                    if len(section_text) > 1500:
                        sub_chunks = char_splitter.split_text(section_text)
                        for j, sub_chunk in enumerate(sub_chunks):
                            documents.append(sub_chunk)
                            metadatas.append({
                                "source": filename,
                                "section": f"Section {sec_num}", # Standardized format
                                "title": sec_title,
                                "chunk_id": f"{sec_num}_{j}",
                                "type": "section_part"
                            })
                            ids.append(f"{filename}_sec{sec_num}_part{j}")
                    else:
                        documents.append(section_text)
                        metadatas.append({
                            "source": filename,
                            "section": f"Section {sec_num}",
                            "title": sec_title,
                            "chunk_id": f"{sec_num}",
                            "type": "full_section"
                        })
                        ids.append(f"{filename}_sec{sec_num}")
                    
            except Exception as e:
                print(f"Error reading {filename}: {e}")

    if documents:
        print(f"Upserting {len(documents)} structured chunks to ChromaDB...")
        BATCH_SIZE = 166 
        total_batches = (len(documents) + BATCH_SIZE - 1) // BATCH_SIZE
        
        for i in range(0, len(documents), BATCH_SIZE):
            batch_docs = documents[i:i + BATCH_SIZE]
            batch_metas = metadatas[i:i + BATCH_SIZE]
            batch_ids = ids[i:i + BATCH_SIZE]
            
            collection.upsert(
                documents=batch_docs,
                metadatas=batch_metas,
                ids=batch_ids
            )
            print(f"  - Processed batch {i // BATCH_SIZE + 1}/{total_batches}")
            
        print("Ingestion complete!")

if __name__ == "__main__":
    ingest_documents()
