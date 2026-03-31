import os
import chromadb
import requests

CHROMA_DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
collection = client.get_collection(name="legal_docs")

print("--- Hierarchy Validation ---")
data = collection.get(limit=15)
for m in data['metadatas']:
    print(f"Sec: {m.get('section')} | Sub: {m.get('subsection')} | Clause: {m.get('clause')} | Subclause: {m.get('subclause')} | Type: {m.get('type')} \n-> Cite: {m.get('citation')}")

print("\n--- Testing API Search for a Deep Subsection ---")
payload = {
    "question": "What does Section 132(2)(a) say?",
    "use_rag": True
}
try:
    response = requests.post("http://127.0.0.1:8000/api/ask", json=payload, stream=True)
    print(f"Status Code: {response.status_code}")
    for line in response.iter_lines():
        if line:
            print(line.decode('utf-8'))
            if b"sources" in line:
                break
except Exception as e:
    print(f"API request failed: {e}")
