from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from schemas import ChatRequest, ChatResponse, Source
from contextlib import asynccontextmanager
import uuid
from dotenv import load_dotenv
import os
from groq import Groq
import chromadb
from chromadb.utils import embedding_functions
import json

load_dotenv()

# Global variables
groq_client = None
chroma_collection = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global groq_client, chroma_collection
    print("Initializing services...")
    
    # Initialize Groq
    try:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            print("Warning: GROQ_API_KEY not found in .env")
        else:
            groq_client = Groq(api_key=api_key)
            print("Groq client initialized successfully!")
    except Exception as e:
        print(f"Error initializing Groq client: {e}")

    # Initialize ChromaDB
    try:
        CHROMA_DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
        if os.path.exists(CHROMA_DB_DIR):
            client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
            chroma_collection = client.get_collection(name="legal_docs", embedding_function=ef)
            print("ChromaDB collection loaded successfully!")
        else:
            print("Warning: ChromaDB directory not found. Please run ingest.py first.")
    except Exception as e:
        print(f"Error initializing ChromaDB: {e}")
    
    yield
    
    # Clean up
    groq_client = None
    chroma_collection = None

app = FastAPI(title="LegalGPT API", version="0.1.0", lifespan=lifespan)

# CORS Configuration
origins = [
    "http://localhost:5173",  # Vite default port
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health_check():
    status = "ok"
    message = "LegalGPT API (Groq + RAG) is ready"
    if groq_client is None:
        status = "error"
        message = "Groq client not initialized"
    if chroma_collection is None:
        message += " (ChromaDB not loaded)"
    
    return {"status": status, "message": message}

@app.post("/api/ask")
async def ask_question(request: ChatRequest):
    if groq_client is None:
        raise HTTPException(status_code=503, detail="LLM service is not ready")

    try:
        # RAG: Retrieve context
        context_text = ""
        sources = []
        
        # 1. Skip RAG for short queries or greetings OR if use_rag is False
        if request.use_rag and len(request.question.strip()) > 10 and not request.question.lower().strip() in ["hi", "hello", "hey"]:
            if chroma_collection:
                try:
                    # Hybrid Search: Extract Section Number if present
                    import re
                    section_match = re.search(r"Section\s+(\d+)", request.question, re.IGNORECASE)
                    where_filter = {}
                    if section_match:
                        # If user asks for specific section, filter by it
                        # Note: We index as "Section 123"
                        target_section = f"Section {section_match.group(1)}"
                        # We use $contains or just exact match if our chunk metadata is exact
                        # ingest.py saves it as "Section X", so exact match is best.
                        where_filter = {"section": target_section}
                        print(f"Hybrid Search: Filtering for {target_section}")
                        
                    # Query Expansion for common abbreviations
                    search_query = request.question
                    # Replace whole word OPC (case insensitive)
                    search_query = re.sub(r'\bOPC\b', 'One Person Company', search_query, flags=re.IGNORECASE)
                    
                    query_params = {
                        "query_texts": [search_query],
                        "n_results": 25,
                        "include": ['documents', 'metadatas', 'distances']
                    }
                    if where_filter:
                        query_params["where"] = where_filter

                    results = chroma_collection.query(**query_params)
                    
                    if results['documents']:
                        scored_docs = []
                        for i, doc in enumerate(results['documents'][0]):
                            dist = results['distances'][0][i] if 'distances' in results else 0
                            meta = results['metadatas'][0][i]
                            doc_id = results['ids'][0][i]
                            
                            # Custom Reranking: Prioritize Indian_Corporate_Act_2013.pdf (Primary)
                            if meta.get('source') == 'Indian_Corporate_Act_2013.pdf':
                                dist -= 0.3 # Boost primary act by lowering its distance
                                
                            scored_docs.append((dist, doc, meta, doc_id))
                            
                        # Sort by adjusted distance (lower is better)
                        scored_docs.sort(key=lambda x: x[0])
                        
                        taken = 0
                        for dist, doc, meta, doc_id in scored_docs:
                            if taken >= 6: # Take top 6 chunks for context
                                break
                                
                            # If explicit section filter is used, trust the result even if distance is high
                            # Increased threshold to 2.0 to allow more citations
                            if dist < 2.0 or where_filter: 
                                if not context_text:
                                    context_text = doc
                                else:
                                    context_text += "\n\n" + doc
                                    
                                sources.append(Source(
                                    id=doc_id,
                                    title=meta.get('section', 'Unknown Section'),
                                    url=meta.get('source', 'Unknown Document'),
                                    excerpt=doc[:200] + "...",
                                    full_text=doc
                                ))
                                taken += 1
                except Exception as e:
                    print(f"RAG Error: {e}")

        # Construct Prompt
        system_prompt = """You are a helpful legal assistant specialized in Indian Corporate Law. 
        Use the provided context to answer the user's question accurately. 
        If the context doesn't contain the answer, rely on your general knowledge but mention that this is general information.
        Always cite the section number or source document if available in the context."""

        if context_text:
            system_prompt += f"\n\nContext:\n{context_text}"

        # Generator function for streaming
        async def generate():
            try:
                # First, yield sources if any
                if sources:
                    yield f"data: {json.dumps({'sources': [s.dict() for s in sources]})}\n\n"

                stream = groq_client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": request.question}
                    ],
                    model="llama-3.3-70b-versatile",
                    temperature=0.3, # Lower temperature for factual Q&A
                    max_tokens=1024,
                    top_p=1,
                    stop=None,
                    stream=True,
                )

                for chunk in stream:
                    if chunk.choices[0].delta.content is not None:
                        content = chunk.choices[0].delta.content
                        if content:
                            yield f"data: {json.dumps({'content': content})}\n\n"
                
                # Signal end of stream
                yield "data: [DONE]\n\n"

            except Exception as e:
                print(f"Stream error: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    except Exception as e:
        print(f"Error generating response: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
