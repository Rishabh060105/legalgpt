import json
import os
import re
from contextlib import asynccontextmanager

import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from groq import Groq

from schemas import ChatRequest, Source, TranscriptionResponse

load_dotenv()

# Global variables
groq_client = None
chroma_collection = None

PRIMARY_DOCUMENT = "Indian_Corporate_Act_2013.pdf"
MAX_CONTEXT_CHUNKS = 12
MAX_CONTEXT_CHARS = 9000
MAX_SEMANTIC_MATCHES = 6
MAX_SUPPORT_MATCHES = 2
SEMANTIC_QUERY_RESULTS = 50
SEMANTIC_DISTANCE_THRESHOLD = 1.1
SEMANTIC_PRIMARY_FALLBACK_THRESHOLD = 3
SEMANTIC_EMPTY_RESULT_FALLBACK = 3
MIN_SEMANTIC_TEXT_CHARS = 40
MIN_SEMANTIC_WORDS = 6

CITATION_QUERY_PATTERN = re.compile(
    r"Section\s+(\d+[A-Za-z]*)(?:\((\d+)\))?(?:\(([a-z])\))?(?:\(([ivx]+)\))?",
    re.IGNORECASE,
)

PRECEDENT_QUERY_KEYWORDS = (
    "case law",
    "precedent",
    "judgment",
    "judgement",
    "ruling",
    "held",
    "court",
    "decided",
)

STATUTE_QUERY_KEYWORDS = (
    "section ",
    "under the act",
    "under companies act",
    "under the corporate act",
    "what does section",
)

PRECEDENT_DOCUMENT_KEYWORDS = ("precedent", "judgment", "judgement", "ruling", "case")
RELEVANCE_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "detail",
        "does",
        "explain",
        "for",
        "from",
        "has",
        "have",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "say",
        "section",
        "tell",
        "that",
        "the",
        "this",
        "to",
        "under",
        "what",
        "which",
        "with",
    }
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global groq_client, chroma_collection
    print("Initializing services...")

    try:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            print("Warning: GROQ_API_KEY not found in .env")
        else:
            groq_client = Groq(api_key=api_key)
            print("Groq client initialized successfully!")
    except Exception as exc:
        print(f"Error initializing Groq client: {exc}")

    try:
        chroma_db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
        if os.path.exists(chroma_db_dir):
            client = chromadb.PersistentClient(path=chroma_db_dir)
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
            chroma_collection = client.get_collection(name="legal_docs", embedding_function=ef)
            print("ChromaDB collection loaded successfully!")
        else:
            print("Warning: ChromaDB directory not found. Please run ingest.py first.")
    except Exception as exc:
        print(f"Error initializing ChromaDB: {exc}")

    yield

    groq_client = None
    chroma_collection = None


app = FastAPI(title="LegalGPT API", version="0.1.0", lifespan=lifespan)

origins = [
    "http://localhost:5173",
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
        context_text = ""
        sources = []

        question = request.question.strip()
        if request.use_rag and len(question) > 10 and question.lower() not in {"hi", "hello", "hey"}:
            if chroma_collection:
                try:
                    retrieval = _retrieve_matches(chroma_collection, question)
                    context_text = _build_context_text(retrieval["context_matches"])
                    sources = _build_sources(retrieval["source_matches"])
                except Exception as exc:
                    print(f"RAG Error: {exc}")

        system_prompt = """You are a helpful legal assistant specialized in Indian Corporate Law.
        Use the provided context to answer the user's question accurately.
        If the context doesn't contain the answer, rely on your general knowledge but mention that this is general information.
        Always cite the section number or source document if available in the context."""

        if context_text:
            system_prompt += f"\n\nContext:\n{context_text}"

        async def generate():
            try:
                if sources:
                    yield f"data: {json.dumps({'sources': [source.model_dump() for source in sources]})}\n\n"

                stream = groq_client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": request.question},
                    ],
                    model="llama-3.3-70b-versatile",
                    temperature=0.3,
                    max_tokens=1024,
                    top_p=1,
                    stop=None,
                    stream=True,
                )

                for chunk in stream:
                    content = chunk.choices[0].delta.content
                    if content:
                        yield f"data: {json.dumps({'content': content})}\n\n"

                yield "data: [DONE]\n\n"
            except Exception as exc:
                print(f"Stream error: {exc}")
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")
    except Exception as exc:
        print(f"Error generating response: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(audio: UploadFile = File(...)):
    if groq_client is None:
        raise HTTPException(status_code=503, detail="Speech-to-text service is not ready")

    if not audio.filename:
        raise HTTPException(status_code=400, detail="Audio filename is required")

    try:
        file_bytes = await audio.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Audio file is empty")

        transcription = groq_client.audio.transcriptions.create(
            file=(audio.filename, file_bytes),
            model="whisper-large-v3-turbo",
            prompt=(
                "Transcribe Indian English legal questions accurately. "
                "Common terms may include Companies Act, tribunal, memorandum, "
                "articles of association, debenture, director, auditor, and compliance."
            ),
            response_format="json",
            temperature=0.0,
        )

        text = (transcription.text or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="No speech could be transcribed")

        return TranscriptionResponse(text=text)
    except HTTPException:
        raise
    except Exception as exc:
        print(f"Transcription error: {exc}")
        raise HTTPException(status_code=500, detail="Failed to transcribe audio")


def _retrieve_matches(collection, question: str) -> dict:
    citation_reference = _extract_citation_reference(question)
    where_filter = _build_where_filter(citation_reference) if citation_reference else None
    intent = _classify_query_intent(question, citation_reference)
    search_query = _expand_search_query(question)

    exact_matches = []
    if where_filter and intent != "precedent":
        exact_matches = _fetch_staged_exact_matches(collection, where_filter)

    if exact_matches:
        support_matches = []
        if intent in {"mixed", "general"}:
            support_matches = _fetch_semantic_matches(collection, search_query, role_preference="precedent")
            support_matches = _limit_semantic_matches(support_matches, MAX_SUPPORT_MATCHES)

        exact_context_budget = MAX_CONTEXT_CHUNKS - len(support_matches)
        context_matches = exact_matches[:exact_context_budget] + support_matches
        source_matches = _merge_matches(exact_matches, support_matches)
        return {
            "intent": intent,
            "citation_reference": citation_reference,
            "context_matches": context_matches,
            "source_matches": source_matches,
        }

    semantic_matches = _retrieve_semantic_matches(collection, search_query, intent, where_filter)
    limited_matches = _limit_semantic_matches(semantic_matches, MAX_CONTEXT_CHUNKS)
    return {
        "intent": intent,
        "citation_reference": citation_reference,
        "context_matches": limited_matches,
        "source_matches": limited_matches,
    }


def _extract_citation_reference(question: str) -> dict | None:
    match = CITATION_QUERY_PATTERN.search(question)
    if not match:
        return None

    return {
        "section": _normalize_section_label(match.group(1)),
        "subsection": match.group(2),
        "clause": match.group(3).lower() if match.group(3) else None,
        "subclause": match.group(4).lower() if match.group(4) else None,
    }


def _classify_query_intent(question: str, citation_reference: dict | None) -> str:
    normalized_question = question.lower()
    has_precedent_signal = any(keyword in normalized_question for keyword in PRECEDENT_QUERY_KEYWORDS)
    has_statute_signal = citation_reference is not None or any(
        keyword in normalized_question for keyword in STATUTE_QUERY_KEYWORDS
    )

    if has_precedent_signal and has_statute_signal:
        return "mixed"
    if has_precedent_signal:
        return "precedent"
    if has_statute_signal:
        return "statute"
    return "general"


def _build_where_filter(reference: dict | None) -> dict | None:
    if not reference or not reference.get("section"):
        return None

    conditions = [{"section": reference["section"]}]
    if reference.get("subsection"):
        conditions.append({"subsection": reference["subsection"]})
    if reference.get("clause"):
        conditions.append({"clause": reference["clause"]})
    if reference.get("subclause"):
        conditions.append({"subclause": reference["subclause"]})

    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


def _fetch_staged_exact_matches(collection, where_filter: dict) -> list[dict]:
    primary_filter = _combine_filters(where_filter, {"document": PRIMARY_DOCUMENT})
    primary_matches = _fetch_exact_matches(collection, primary_filter)
    if primary_matches:
        print(f"Exact citation retrieval matched {len(primary_matches)} primary chunks for {where_filter}")
        return primary_matches

    fallback_matches = _fetch_exact_matches(collection, where_filter)
    if fallback_matches:
        print(f"Exact citation fallback matched {len(fallback_matches)} chunks for {where_filter}")
    return fallback_matches


def _fetch_exact_matches(collection, where_filter: dict) -> list[dict]:
    results = collection.get(
        where=where_filter,
        include=["documents", "metadatas"],
    )
    matches = _zip_matches(
        results.get("ids") or [],
        results.get("documents") or [],
        results.get("metadatas") or [],
    )
    matches.sort(key=_exact_sort_key)
    return matches


def _retrieve_semantic_matches(collection, search_query: str, intent: str, where_filter: dict | None = None) -> list[dict]:
    statute_filter = where_filter if intent in {"statute", "mixed", "general"} else None

    primary_matches = _fetch_semantic_matches(
        collection,
        search_query,
        where_filter=_combine_filters(statute_filter, {"document": PRIMARY_DOCUMENT}),
        role_preference="primary",
    )

    if intent == "precedent":
        precedent_matches = _fetch_semantic_matches(collection, search_query, role_preference="precedent")
        primary_support = _limit_semantic_matches(primary_matches, MAX_SUPPORT_MATCHES)
        return _merge_matches(
            _limit_semantic_matches(precedent_matches, MAX_SEMANTIC_MATCHES),
            primary_support,
        )

    if intent in {"mixed", "general"}:
        precedent_support = _fetch_semantic_matches(collection, search_query, role_preference="precedent")
        primary_selected = _limit_semantic_matches(primary_matches, MAX_SEMANTIC_MATCHES)
        support_selected = _limit_semantic_matches(precedent_support, MAX_SUPPORT_MATCHES)
        return _merge_matches(primary_selected, support_selected)

    primary_selected = _limit_semantic_matches(primary_matches, MAX_SEMANTIC_MATCHES)
    if len(primary_selected) >= SEMANTIC_PRIMARY_FALLBACK_THRESHOLD:
        return primary_selected

    fallback_matches = _fetch_semantic_matches(collection, search_query, where_filter=statute_filter, role_preference="statute")
    return _limit_semantic_matches(_merge_matches(primary_selected, fallback_matches), MAX_SEMANTIC_MATCHES)


def _fetch_semantic_matches(
    collection,
    search_query: str,
    where_filter: dict | None = None,
    role_preference: str = "statute",
) -> list[dict]:
    query_params = {
        "query_texts": [search_query],
        "n_results": SEMANTIC_QUERY_RESULTS,
        "include": ["documents", "metadatas", "distances"],
    }
    if where_filter:
        query_params["where"] = where_filter
        print(f"Semantic search within filter {where_filter}")

    results = collection.query(**query_params)
    documents = results.get("documents", [[]])
    if not documents or not documents[0]:
        return []

    matches = _zip_matches(
        results.get("ids", [[]])[0],
        documents[0],
        results.get("metadatas", [[]])[0] if results.get("metadatas") else [],
        results.get("distances", [[]])[0] if results.get("distances") else [],
    )

    filtered_matches = [match for match in matches if _match_role(match["metadata"], role_preference)]
    filtered_matches.sort(key=lambda item: _semantic_sort_key(item, role_preference, search_query))
    return filtered_matches


def _zip_matches(ids: list, documents: list, metadatas: list, distances: list | None = None) -> list[dict]:
    distances = distances or [0.0] * len(documents)
    matches = []

    for doc_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
        if not document:
            continue
        matches.append(
            {
                "id": doc_id,
                "document": document,
                "metadata": metadata or {},
                "distance": float(distance),
            }
        )

    matches.sort(key=lambda item: _metadata_sort_key(item["metadata"]))
    return matches


def _match_role(metadata: dict, role_preference: str) -> bool:
    role = _infer_document_role(metadata.get("document"))

    if role_preference == "primary":
        return metadata.get("document") == PRIMARY_DOCUMENT
    if role_preference == "precedent":
        return role == "precedent"
    if role_preference == "statute":
        return role != "precedent"
    return True


def _semantic_sort_key(match: dict, role_preference: str, search_query: str) -> tuple:
    metadata = match["metadata"]
    document_role = _infer_document_role(metadata.get("document"))
    phrase_hits, overlap_count = _query_relevance_key(search_query, match)

    if role_preference == "primary":
        role_rank = 0 if metadata.get("document") == PRIMARY_DOCUMENT else 1
    elif role_preference == "precedent":
        role_rank = 0 if document_role == "precedent" else 1
    else:
        role_rank = 1 if document_role == "precedent" else 0

    return (
        role_rank,
        1 if _is_low_signal_match(match) else 0,
        -phrase_hits,
        -overlap_count,
        match["distance"],
        -_content_quality_score(match),
        _metadata_sort_key(metadata),
    )


def _build_context_text(matches: list[dict]) -> str:
    blocks = []
    total_chars = 0

    for match in matches:
        block = _build_context_block(match)
        if not block:
            continue

        remaining_chars = MAX_CONTEXT_CHARS - total_chars
        if remaining_chars <= 0:
            break

        if len(block) <= remaining_chars:
            blocks.append(block)
            total_chars += len(block)
            continue

        if not blocks:
            blocks.append(block[:remaining_chars].rstrip())
        break

    return "\n\n".join(blocks)


def _build_context_block(match: dict) -> str:
    metadata = match["metadata"]
    document_text = match["document"].strip()
    if not document_text:
        return ""

    citation = metadata.get("citation") or "Unknown Section"
    return f"{citation}\n{document_text}"


def _build_sources(matches: list[dict]) -> list[Source]:
    sources = []
    seen_keys = set()

    for match in matches:
        dedupe_key = _match_dedupe_key(match)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)

        document_text = match["document"].strip()
        if not document_text:
            continue

        sources.append(
            Source(
                id=match["id"],
                title=match["metadata"].get("citation") or "Unknown Section",
                url=match["metadata"].get("document") or "Unknown Document",
                excerpt=_build_excerpt(document_text),
                full_text=document_text,
            )
        )

    return sources


def _limit_semantic_matches(matches: list[dict], limit: int) -> list[dict]:
    high_signal_matches = [match for match in matches if not _is_low_signal_match(match)]
    candidate_groups = [high_signal_matches, matches] if high_signal_matches else [matches]

    for candidate_group in candidate_groups:
        selected = []
        for match in candidate_group:
            if match["distance"] > SEMANTIC_DISTANCE_THRESHOLD:
                continue
            selected.append(match)
            if len(selected) >= limit:
                break

        if selected:
            return selected

    if high_signal_matches:
        return high_signal_matches[: min(limit, SEMANTIC_EMPTY_RESULT_FALLBACK)]

    return matches[: min(limit, SEMANTIC_EMPTY_RESULT_FALLBACK)]


def _merge_matches(primary_matches: list[dict], secondary_matches: list[dict]) -> list[dict]:
    merged = []
    seen_keys = set()

    for match in primary_matches + secondary_matches:
        dedupe_key = _match_dedupe_key(match)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        merged.append(match)

    return merged


def _combine_filters(left: dict | None, right: dict | None) -> dict | None:
    if left and right:
        conditions = []
        if "$and" in left:
            conditions.extend(left["$and"])
        else:
            conditions.append(left)
        if "$and" in right:
            conditions.extend(right["$and"])
        else:
            conditions.append(right)
        return {"$and": conditions}
    return left or right


def _infer_document_role(document_name: str | None) -> str:
    if not document_name:
        return "unknown"
    if document_name == PRIMARY_DOCUMENT:
        return "primary"

    normalized_name = document_name.lower()
    if any(keyword in normalized_name for keyword in PRECEDENT_DOCUMENT_KEYWORDS):
        return "precedent"
    return "secondary"


def _expand_search_query(question: str) -> str:
    return re.sub(r"\bOPC\b", "One Person Company", question, flags=re.IGNORECASE)


def _exact_sort_key(match: dict) -> tuple:
    return (
        _metadata_sort_key(match["metadata"]),
        1 if _is_low_signal_match(match) else 0,
        -_content_quality_score(match),
        -len(_compact_text(match["document"])),
    )


def _match_dedupe_key(match: dict) -> tuple:
    metadata = match["metadata"]
    document_name = metadata.get("document") or ""
    citation = metadata.get("citation") or ""
    if document_name or citation:
        return (document_name, citation)
    return ("id", match["id"])


def _query_relevance_key(search_query: str, match: dict) -> tuple[int, int]:
    query_tokens = _tokenize_relevance_text(search_query)
    if not query_tokens:
        return (0, 0)

    searchable_text = _searchable_text(match).lower()
    searchable_tokens = set(_tokenize_relevance_text(searchable_text))
    overlap_count = len(set(query_tokens) & searchable_tokens)

    phrase_hits = 0
    for phrase_size in range(min(3, len(query_tokens)), 1, -1):
        for index in range(len(query_tokens) - phrase_size + 1):
            phrase = " ".join(query_tokens[index : index + phrase_size])
            if phrase in searchable_text:
                phrase_hits += 1

    return (phrase_hits, overlap_count)


def _searchable_text(match: dict) -> str:
    metadata = match["metadata"]
    return " ".join(
        part
        for part in (
            metadata.get("citation", ""),
            metadata.get("title", ""),
            match.get("document", ""),
        )
        if part
    )


def _tokenize_relevance_text(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [token for token in tokens if token not in RELEVANCE_STOPWORDS]


def _content_quality_score(match: dict) -> int:
    metadata = match["metadata"]
    compact_text = _compact_text(match["document"])
    word_count = len(compact_text.split())
    structure_depth = sum(1 for key in ("subsection", "clause", "subclause") if metadata.get(key))
    structured_bonus = 5 if metadata.get("type") == "structured" else 0
    title_bonus = 3 if metadata.get("title") else 0

    return min(word_count, 80) + (structure_depth * 12) + structured_bonus + title_bonus


def _is_low_signal_match(match: dict) -> bool:
    compact_text = _compact_text(match["document"])
    if not compact_text:
        return True

    if len(compact_text) < MIN_SEMANTIC_TEXT_CHARS:
        return True

    return len(compact_text.split()) < MIN_SEMANTIC_WORDS


def _compact_text(text: str) -> str:
    return " ".join(text.split())


def _build_excerpt(text: str, max_length: int = 200) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_length:
        return compact
    return compact[:max_length].rstrip() + "..."


def _metadata_sort_key(metadata: dict) -> tuple:
    return (
        0 if metadata.get("document") == PRIMARY_DOCUMENT else 1,
        _section_sort_key(metadata.get("section")),
        _safe_int(metadata.get("subsection")),
        _safe_alpha_index(metadata.get("clause")),
        _safe_roman_index(metadata.get("subclause")),
        metadata.get("citation", ""),
    )


def _safe_int(value: str | None) -> int:
    try:
        return int(value) if value else -1
    except (TypeError, ValueError):
        return -1


def _section_sort_key(value: str | None) -> tuple[int, tuple[int, ...], str]:
    normalized = _normalize_section_label(value)
    if not normalized:
        return (-1, (), "")

    match = re.fullmatch(r"(\d+)([A-Z]*)", normalized)
    if not match:
        return (-1, (), normalized)

    number = int(match.group(1))
    suffix = match.group(2)
    suffix_key = tuple(ord(character) - ord("A") + 1 for character in suffix)
    return (number, suffix_key, normalized)


def _normalize_section_label(value: str | None) -> str | None:
    if not value:
        return None

    value = value.strip()
    match = re.fullmatch(r"(\d+)([A-Za-z]*)", value)
    if not match:
        return value

    return f"{match.group(1)}{match.group(2).upper()}"


def _safe_alpha_index(value: str | None) -> int:
    if not value:
        return -1
    return ord(value.lower()[0]) - ord("a")


def _safe_roman_index(value: str | None) -> int:
    if not value:
        return -1
    return _roman_to_int(value.lower())


def _roman_to_int(value: str) -> int:
    numerals = {"i": 1, "v": 5, "x": 10}
    total = 0
    previous = 0

    for character in reversed(value):
        current = numerals.get(character)
        if current is None:
            return -1
        if current < previous:
            total -= current
        else:
            total += current
            previous = current

    return total


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
