# LegalGPT — Planning README

## Project Overview
**LegalGPT** is a full-stack application that provides accurate, explainable answers to legal questions. The language model runs on the backend (self-hosted or via an API) while the frontend delivers a sleek, Apple-style UI with refined animations and micro-interactions. The app will be optimized for readability, trust, and compliance for legal-domain usage.

> Notebook analysis summary:
```
Notebook path: /mnt/data/Cognitivelab_assignment_notebook_Rishabh_Jain-3.ipynb
Total cells: 24
Found markdown headings (top 10):
  - # CognitiveLab Research Internship Assignment
  - ## Synthetic Data Generation and LLM Fine-tuning
  - ### Overview
  - ### What is Synthetic Data?
  - ### Task Description
  - ### Potential Use Cases
  - ### Requirements
  - ## 1. What is you Idea and use case you are trying to solve?
  - ## 2. Environment Setup
  - ## 3. Synthetic Data Generation
Top imports detected: datasets, evaluate, google, groq, huggingface_hub, json, matplotlib, numpy, os, pandas, peft, torch, tqdm, transformers, trl
Top-level functions detected: generate_qa_batch, format_dataset_entry, pre_format_example, generate_response, autolabel
```

---

## Goals & Features
- Natural-language Q&A for legal questions (statutes, case law, contracts, compliance).
- Retrieval-Augmented Generation (RAG): combine an LLM with a legal document vector store for source-grounded answers.
- Sleek, minimal, and animated UI inspired by the Apple website. Use animation examples from `https://github.com/DavidHDev/react-bits`.
- Source-citation and confidence levels for each answer.
- Conversation history, follow-up question support and clarifying-question prompts.
- Feedback loop for users to mark answers as **helpful / not helpful** and to flag incorrect legal content.
- Strong privacy, logging, and audit trail for regulatory compliance.

---

## High-level Architecture
1. **Frontend** (React)
   - Single Page Application (SPA) using React + TypeScript.
   - Styling: Tailwind CSS (utility-first), with design tokens for spacing, radius, colors.
   - Animation: Framer Motion + CSS transitions inspired by react-bits components and Apple-like micro-interactions.
   - Key libraries:
     - `react`, `react-dom`, `typescript`, `tailwindcss`, `framer-motion`, `react-router`, `axios`, `zustand` or `redux` for state.

2. **Backend API**
   - Framework: Node.js (Express / Fastify) or Python (FastAPI) — FastAPI recommended for rapid async and typed endpoints.
   - Endpoints:
     - `POST /api/ask` — ask a legal question (body: { "question": string, "context": optional })
     - `GET /api/session/:id/history` — conversation history
     - `POST /api/feedback` — user feedback on answers
     - `POST /api/upload` — upload documents to augment the knowledge base (requires strict validation)
   - Core services:
     - **RAG service**: vector DB (Milvus / Pinecone / Weaviate / Qdrant) + embedding model to retrieve relevant documents.
     - **LLM service**: self-hosted LLM (e.g., Llama 3 / local LLM infra) or API-based (OpenAI, Anthropic). Use a middleware to standardize prompts.
     - **Auth**: JWT / OAuth 2.0 for users and admin.
     - **Rate limiting, caching, request throttling.**

3. **Storage**
   - Vector DB for embeddings.
   - Document store (S3 / Blob Storage) for original legal PDFs and attachments (encrypted at rest).
   - RDBMS (Postgres) for users, sessions, metadata, logs.
   - Logs & monitoring (ELK / OpenSearch or hosted alternatives).

4. **Deployment**
   - Docker-compose / Kubernetes for production.
   - CI/CD: GitHub Actions for test -> build -> deploy.

---

## UI / Frontend Design & Animations
- Reference: `https://github.com/DavidHDev/react-bits` and Apple website micro-interactions.
- Visual language:
  - Clean surfaces, generous whitespace, crisp typography (Inter / SF Pro equivalent).
  - Soft shadows, large rounded cards, subtle parallax effects for hero sections.
- Animation patterns to implement:
  1. **Fluid page transitions** (Framer Motion `AnimatePresence`) — fade + slide with acceleration curves.
  2. **Micro-interactions**: button hover, subtle scale & glow, animated underlines for nav items.
  3. **Content reveal**: staggered reveal of answer components (source cards slide-in with fade).
  4. **Interactive search box**: expanding search with typeahead suggestions and token chips.
  5. **Citation preview**: hovering a citation shows a small floating card (glass effect) with source excerpt.
- Use `react-bits` components as building blocks for pattern inspiration (buttons, cards, animated lists).
- Accessibility:
  - Ensure animations respect `prefers-reduced-motion`.
  - Keyboard navigable components and ARIA labels.

---

## Prompting & RAG Strategy
- **Indexer**: preprocess legal PDFs (OCR if needed), extract metadata (jurisdiction, date), chunk with overlap (e.g. 500 tokens, 100 token overlap).
- **Embeddings**: use an embedding model appropriate to the chosen LLM provider.
- **Retriever**: top-k (k=5-10) semantic retrieval, then relevance filtering by jurisdiction and date.
- **Reranker** (optional): learn a small model to reorder retrieved docs.
- **Answer generation**:
  - Construct a composable prompt:
    - System: role, legal compliance constraints, list of allowed behaviors, non-creative (no hallucinations).
    - Context: top retrieved passages + metadata.
    - User question and explicit instructions to cite sources inline and return a `sources` array.
  - Postprocess to extract `answer_text`, `sources`, `confidence_score`, `explainability` metadata.
- **Cite sources**: include links to original docs and paragraph references.

---

## API Spec (example)
**POST /api/ask**
Request:
```json
{
  "question": "Does non-compete clause signed in California enforceable?",
  "session_id": "string (optional)",
  "jurisdiction": "US-CA",
  "max_tokens": 800
}
```
Response:
```json
{
  "answer_id": "uuid",
  "answer_text": "Short direct answer followed by explanation...",
  "sources": [
    {"id": "doc_123", "title": "California Labor Code", "excerpt": "...", "url": "/api/document/doc_123#p45"}
  ],
  "confidence": 0.72,
  "follow_up": ["Would you like examples?", "Show case law?"]
}
```

---

## Security, Compliance & Legal Risks
- **Disclaimers**: Prominently show that the tool is educational and not a substitute for licensed attorney advice.
- **Data retention & privacy**:
  - Allow users to opt-in/opt-out of saving conversations for model improvement.
  - PII redaction pipelines before storing or indexing documents.
  - Encrypt data at rest and in transit (TLS).
- **Audit & Logging**:
  - Keep immutable logs of model outputs and inputs for audits (access controlled).
- **Jurisdiction**:
  - Clearly display jurisdiction used for answers; do not use documents from other jurisdictions unless explicitly requested.
- **Legal features**:
  - Consent capture when uploading documents.
  - Secure file handling and anti-malware scanning for uploads.
- **Regulatory**:
  - Check local regulations for legal advice software (may require partnership with legal services).

---

## Testing & Evaluation
- Unit tests for components and backend endpoints.
- Integration tests for the RAG pipeline using a small corpus of canonical legal documents.
- Human evaluation: hire contract attorneys to rate answers on correctness, helpfulness, and risk.
- Automated checks for hallucination rate by verifying source coverage in responses.

---

## Implementation Roadmap (suggested sprints)
**Sprint 0 — Discovery & infra (1 week)**
- Finalize LLM provider and vector DB.
- Create minimal design language & tokens.

**Sprint 1 — MVP backend (2 weeks)**
- Implement `/api/ask` with a stub LLM response.
- Simple document ingestion and vector index.
- Basic auth and DB models.

**Sprint 2 — Frontend MVP (2 weeks)**
- Implement core UI: question composer, answer card, history.
- Add basic transitions and Hero page inspired by react-bits.

**Sprint 3 — RAG + citations (2 weeks)**
- Hook real embedding model + retrieval.
- Implement citation extraction and display.

**Sprint 4 — Improvements (2-4 weeks)**
- Add feedback loop, analytics, rate limits, file uploads, admin tools.
- Perform legal audits and privacy reviews.

---

## Developer Notes & Implementation Tips
- Use feature flags to roll out the model-backed behavior.
- Keep generation deterministic for audits where possible (temperature=0 for final answers).
- Store only metadata + encrypted pointer to user content by default; store full content only with explicit consent.

---

## Appendix: Notebook-derived notes
- The uploaded notebook appears to include the following (automatically extracted):
- Headings: CognitiveLab Research Internship Assignment, Synthetic Data Generation and LLM Fine-tuning, Overview, What is Synthetic Data?, Task Description, Potential Use Cases, Requirements, 1. What is you Idea and use case you are trying to solve?, 2. Environment Setup, 3. Synthetic Data Generation
- Detected imports: datasets, evaluate, google, groq, huggingface_hub, json, matplotlib, numpy, os, pandas, peft, torch, tqdm, transformers, trl
- Functions: generate_qa_batch, format_dataset_entry, pre_format_example, generate_response, autolabel
- Classes: None

> Use the notebook content as a reference for project-specific data processing steps or experiments already present in the notebook.

---

## Next steps (practical)
1. Review and pick LLM provider (OpenAI, Anthropic, self-hosted).
2. Prepare a small canonical legal corpus (contracts, statutes, case law) to index and test the RAG pipeline.
3. Prototype the frontend hero and question composer using `react-bits` examples and Framer Motion transitions.
4. Schedule a legal review for disclaimers and compliance before public launch.

---

## Contact
If you'd like, I can:
- Generate a detailed component tree and example React code (with Framer Motion + Tailwind) for the UI.
- Produce a sample FastAPI backend implementation with example endpoints and a mock RAG pipeline.
- Create deployment manifests (Docker Compose / Kubernetes) and CI workflows.

---

*Disclaimer: This README is a planning document. The service should not be used as an authoritative source of legal advice without review by licensed attorneys.*
