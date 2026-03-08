# LegalGPT ⚖️

LegalGPT is an intelligent Legal Assistant powered by Retrieval-Augmented Generation (RAG). It allows users to ask complex legal questions and get accurate, source-grounded answers. The system references specific legal documents (like the Indian Corporate Act of 2013) and prioritizes explicit citations over hallucinations.

![LegalGPT UI Preview](./frontend/public/vite.svg)

---

## 🏗 System Architecture

LegalGPT is divided into two primary systems: a modern React frontend and a robust Python backend with a local vector database.

### 1. Frontend (Vite + React + Tailwind)
The frontend focuses on delivering a sleek, minimal, and highly responsive user experience.
* **Framework**: React 19 (via Vite)
* **Styling**: Tailwind CSS
* **Animations**: Framer Motion and React Spring for fluid micro-interactions
* **Architecture**: 
  * Features a continuous chat interface (`App.tsx` & `ChatInput.tsx`).
  * Markdown rendering is handled natively to format Legal citations and bullet points (`MessageBubble.tsx`).
  * Source Modal viewer to preview the context documents retrieved from the vector database.

### 2. Backend (FastAPI + ChromaDB + Groq)
The backend acts as the RAG orchestration layer. It is responsible for parsing documents, generating embeddings, executing semantic searches, and streaming LLM responses.
* **Framework**: FastAPI (Python) for asynchronous, high-performance API routes.
* **Vector Database**: ChromaDB (Running locally with persistent storage backing in `./chroma_db`).
* **LLM Engine**: Llama-3-8B (via Groq API) for ultra-fast inference.
* **Embeddings**: `BAAI/bge-large-en-v1.5` (via Hugging Face) for state-of-the-art semantic comprehension of legal text.

### 🔄 The RAG Workflow (How it works)
1. **Ingestion (`ingest.py`)**: Legal PDFs are parsed. Text is extracted, chunked securely while respecting paragraph boundaries, embedded via HuggingFace models, and stored seamlessly in the local ChromaDB vector store.
2. **Retrieval (`main.py`)**: When a user asks a question, the query is expanded/optimized (e.g., expanding "OPC" to "One Person Company"). It's then semantic-searched against the ChromaDB to find the most relevant document chunks.
3. **Generation**: The retrieved legal text chunks are securely injected into a strict system prompt, which is fed to Llama-3 to generate a definitive, cited response.

---

## 🚀 Local Development Setup

### Prerequisites
* **Node.js**: v18+ 
* **Python**: 3.10+
* **API Keys**: You will need a `GROQ_API_KEY` and a `HF_TOKEN` (Hugging Face) to run the models.

### Step 1: Set up the Backend
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # Mac/Linux
   source venv/bin/activate 
   # Windows
   .\venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file in the `backend` directory and add your keys:
   ```env
   HF_TOKEN="your_huggingface_token"
   GROQ_API_KEY="your_groq_api_key"
   ```
5. *(Optional)* If you wish to re-ingest the PDFs into the Vector DB:
   ```bash
   python ingest.py
   ```
6. Run the FastAPI server:
   ```bash
   uvicorn main:app --reload
   ```
   *(Server will start on `http://127.0.0.0:8000`)*

### Step 2: Set up the Frontend
1. Open a new terminal and navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install NodeJS dependencies:
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npm run dev
   ```
   *(Server will start on `http://localhost:5173`)*

---

## 🔒 Limitations & Security Disclaimer
**LegalGPT is an educational tool and experimental prototype. It is NOT a substitute for licensed attorney advice.**
* The current setup utilizes a local `chroma_db` folder for persistence. When deploying to the cloud (e.g., AWS EC2 or Render), ensure the server provisions a persistent disk to prevent the vector database from wiping out upon restarts.
* Always cross-reference citations generated with primary legal texts.

---
*Developed by Rishabh Jain*
