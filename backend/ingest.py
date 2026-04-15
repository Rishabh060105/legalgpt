import os
import re
import uuid

import chromadb
from chromadb.utils import embedding_functions
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

# Paths
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BACKEND_DIR, "..", "RAG document")
CHROMA_DB_DIR = os.path.join(BACKEND_DIR, "chroma_db")

SECTION_PATTERN = re.compile(r"(?m)(?:^|\n)(\d+[A-Za-z]*)\.\s+([^\n]+)")
SUBSECTION_PATTERN = re.compile(r"\((\d+)\)")
CLAUSE_PATTERN = re.compile(r"\(([a-z])\)", re.IGNORECASE)
SUBCLAUSE_PATTERN = re.compile(r"\(([ivx]+)\)", re.IGNORECASE)


def _build_embedding_function():
    try:
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2",
            local_files_only=True,
        )
    except Exception:
        return embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")


def clean_text(text: str) -> str:
    """Fix common PDF extraction artifacts while preserving legal structure."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"\b(?:[A-Za-z]\s+){1,7}[A-Za-z]\b", _merge_spaced_letters, text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_sections(text: str) -> list[dict]:
    """Parse top-level sections like `132. Heading`."""
    raw_matches = list(SECTION_PATTERN.finditer(text))
    matches, intro_start = _trim_toc_section_matches(text, raw_matches)
    if not matches:
        return [
            {
                "section": None,
                "title": None,
                "text": text.strip(),
            }
        ]

    sections = []
    intro = text[intro_start : matches[0].start()].strip()
    if intro:
        sections.append(
            {
                "section": None,
                "title": None,
                "text": intro,
            }
        )

    for index, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        title, body_text = _split_inline_section_body(
            match.group(2).strip(),
            text[body_start:body_end].strip(),
        )
        sections.append(
            {
                "section": match.group(1).upper(),
                "title": title,
                "text": body_text,
            }
        )

    return sections


def parse_subsections(section_dict: dict) -> list[dict]:
    """Parse subsections like `(1)`, `(2)` inside a section."""
    lead_text, items = _split_structural_units(section_dict.get("text", ""), SUBSECTION_PATTERN, "subsection")
    if not items:
        return [
            {
                **section_dict,
                "subsection": None,
                "lead_text": "",
                "text": section_dict.get("text", "").strip(),
            }
        ]

    return [
        {
            **section_dict,
            "subsection": item["label"],
            "lead_text": lead_text,
            "text": item["text"],
        }
        for item in items
    ]


def parse_clauses(node_dict: dict) -> list[dict]:
    """Parse clauses like `(a)`, `(b)` inside a section or subsection."""
    lead_text, items = _split_structural_units(node_dict.get("text", ""), CLAUSE_PATTERN, "clause")
    if not items:
        return [
            {
                **node_dict,
                "clause": None,
                "lead_text": "",
                "text": node_dict.get("text", "").strip(),
            }
        ]

    return [
        {
            **node_dict,
            "clause": item["label"],
            "lead_text": lead_text,
            "text": item["text"],
        }
        for item in items
    ]


def parse_subclauses(node_dict: dict) -> list[dict]:
    """Parse sub-clauses like `(i)`, `(ii)` inside a clause."""
    lead_text, items = _split_structural_units(node_dict.get("text", ""), SUBCLAUSE_PATTERN, "subclause")
    if not items:
        return [
            {
                **node_dict,
                "subclause": None,
                "lead_text": "",
                "text": node_dict.get("text", "").strip(),
            }
        ]

    return [
        {
            **node_dict,
            "subclause": item["label"],
            "lead_text": lead_text,
            "text": item["text"],
        }
        for item in items
    ]


def build_hierarchy(full_text: str, filename: str) -> list[dict]:
    """Build structured legal chunks, falling back to naive chunking when needed."""
    cleaned_text = clean_text(full_text)
    sections = parse_sections(cleaned_text)
    fallback_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    final_chunks = []
    structured_found = False

    for section in sections:
        section_base = {
            "document": filename,
            "section": section.get("section"),
            "title": section.get("title"),
            "subsection": None,
            "clause": None,
            "subclause": None,
        }

        if not section.get("section"):
            final_chunks.extend(
                _build_unstructured_chunks(
                    section.get("text", ""),
                    section_base,
                    fallback_splitter,
                )
            )
            continue

        section_chunks = _build_section_chunks(section, section_base)
        if section_chunks:
            structured_found = True
            final_chunks.extend(section_chunks)
        else:
            final_chunks.extend(
                _build_unstructured_chunks(
                    section.get("text", ""),
                    {
                        **section_base,
                        "citation_path": f"Section {section['section']}",
                    },
                    fallback_splitter,
                )
            )

    if structured_found:
        return final_chunks

    return _build_unstructured_chunks(
        cleaned_text,
        {
            "document": filename,
            "section": None,
            "title": None,
            "subsection": None,
            "clause": None,
            "subclause": None,
            "citation_path": "Unstructured Context",
        },
        fallback_splitter,
    )


def store_in_chromadb(chunks: list[dict], collection):
    """Store chunks with hierarchy metadata in ChromaDB."""
    documents = []
    metadatas = []
    ids = []

    for chunk in chunks:
        chunk_text = chunk.get("text", "").strip()
        if not chunk_text:
            continue

        documents.append(chunk_text)
        metadata = {
            "document": chunk.get("document", ""),
            "title": chunk.get("title") or "",
            "section": chunk.get("section") or "",
            "subsection": chunk.get("subsection") or "",
            "clause": chunk.get("clause") or "",
            "subclause": chunk.get("subclause") or "",
            "citation": chunk.get("citation_path", ""),
            "type": chunk.get("type", "structured"),
        }
        metadatas.append(metadata)

        safe_citation = re.sub(r"[^A-Za-z0-9]+", "_", chunk.get("citation_path", "unstructured")).strip("_")
        ids.append(f"{chunk.get('document', 'document')}_{safe_citation}_{uuid.uuid4().hex[:8]}")

    print(f"Upserting {len(documents)} chunks to ChromaDB...")
    batch_size = 166
    total_batches = (len(documents) + batch_size - 1) // batch_size

    for index in range(0, len(documents), batch_size):
        collection.upsert(
            documents=documents[index : index + batch_size],
            metadatas=metadatas[index : index + batch_size],
            ids=ids[index : index + batch_size],
        )
        print(f"  - Processed batch {index // batch_size + 1}/{total_batches}")


def ingest_documents():
    print(f"Initializing ChromaDB at {CHROMA_DB_DIR}...")
    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    print("Loading embedding model (all-MiniLM-L6-v2)...")
    ef = _build_embedding_function()

    try:
        client.delete_collection(name="legal_docs")
        print("Deleted existing collection.")
    except Exception:
        pass

    collection = client.get_or_create_collection(
        name="legal_docs",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    if not os.path.exists(DATA_DIR):
        print(f"Data directory not found: {DATA_DIR}")
        return

    print(f"Scanning {DATA_DIR} for documents...")
    all_chunks = []
    for filename in os.listdir(DATA_DIR):
        if not filename.endswith(".pdf"):
            continue

        filepath = os.path.join(DATA_DIR, filename)
        print(f"Processing {filename}...")

        try:
            reader = PdfReader(filepath)
            full_text = ""
            for page in reader.pages:
                extracted_text = page.extract_text()
                if extracted_text:
                    full_text += extracted_text + "\n"

            chunks = build_hierarchy(full_text, filename)
            all_chunks.extend(chunks)
            print(f"  - Built hierarchy with {len(chunks)} chunks")
        except Exception as exc:
            print(f"Error reading {filename}: {exc}")

    if all_chunks:
        store_in_chromadb(all_chunks, collection)
        print("Ingestion complete!")


def _build_section_chunks(section: dict, base_metadata: dict) -> list[dict]:
    chunks = []
    subsections = parse_subsections(section)
    has_subsections = any(item.get("subsection") for item in subsections)

    if has_subsections:
        for subsection in subsections:
            chunks.extend(_build_subsection_chunks(base_metadata, subsection))
        return chunks

    section_clauses = parse_clauses({**section, **base_metadata})
    has_direct_clauses = any(item.get("clause") for item in section_clauses)

    if has_direct_clauses:
        for clause in section_clauses:
            chunks.extend(_build_clause_chunks(base_metadata, {}, clause))
        return chunks

    leaf_text = _join_text_parts(section.get("text"))
    if leaf_text:
        chunks.append(
            _make_structured_chunk(
                {**base_metadata, "text": leaf_text},
            )
        )

    return chunks


def _build_subsection_chunks(base_metadata: dict, subsection: dict) -> list[dict]:
    chunks = []
    subsection_metadata = {
        **base_metadata,
        "subsection": subsection.get("subsection"),
    }

    clauses = parse_clauses(subsection)
    has_clauses = any(item.get("clause") for item in clauses)

    if has_clauses:
        for clause in clauses:
            chunks.extend(
                _build_clause_chunks(
                    subsection_metadata,
                    {"subsection": subsection.get("lead_text", "")},
                    clause,
                )
            )
        return chunks

    direct_text = _join_text_parts(subsection.get("lead_text"), subsection.get("text"))
    if direct_text:
        chunks.append(
            _make_structured_chunk(
                {
                    **subsection_metadata,
                    "text": direct_text,
                }
            )
        )

    return chunks


def _build_clause_chunks(base_metadata: dict, inherited_text: dict, clause: dict) -> list[dict]:
    chunks = []
    clause_metadata = {
        **base_metadata,
        "clause": clause.get("clause"),
    }

    subclauses = parse_subclauses(clause)
    has_subclauses = any(item.get("subclause") for item in subclauses)
    clause_prefix = _join_text_parts(inherited_text.get("subsection"), clause.get("lead_text"))

    if has_subclauses:
        for subclause in subclauses:
            leaf_text = _join_text_parts(clause_prefix, subclause.get("lead_text"), subclause.get("text"))
            if not leaf_text:
                continue

            chunks.append(
                _make_structured_chunk(
                    {
                        **clause_metadata,
                        "subclause": subclause.get("subclause"),
                        "text": leaf_text,
                    }
                )
            )
        return chunks

    leaf_text = _join_text_parts(inherited_text.get("subsection"), clause.get("lead_text"), clause.get("text"))
    if leaf_text:
        chunks.append(
            _make_structured_chunk(
                {
                    **clause_metadata,
                    "subclause": None,
                    "text": leaf_text,
                }
            )
        )

    return chunks


def _build_unstructured_chunks(text: str, metadata: dict, splitter: RecursiveCharacterTextSplitter) -> list[dict]:
    cleaned_text = text.strip()
    if not cleaned_text:
        return []

    chunks = []
    for piece in splitter.split_text(cleaned_text):
        chunk_metadata = {
            **metadata,
            "citation_path": metadata.get("citation_path", "Unstructured Context"),
            "type": "unstructured",
            "text": piece.strip(),
        }
        if chunk_metadata["text"]:
            chunks.append(chunk_metadata)

    return chunks


def _make_structured_chunk(metadata: dict) -> dict:
    chunk = metadata.copy()
    chunk["citation_path"] = _build_citation_path(chunk)
    chunk["type"] = "structured"
    return chunk


def _split_structural_units(text: str, pattern: re.Pattern, level: str) -> tuple[str, list[dict]]:
    text = text.strip()
    if not text:
        return "", []

    candidates = []
    for match in pattern.finditer(text):
        label = match.group(1).lower()
        if not _is_structural_boundary(text, match.start()):
            continue
        candidates.append(
            {
                "label": label,
                "start": match.start(),
                "end": match.end(),
            }
        )

    accepted = _select_sequential_markers(candidates, level)
    if not accepted:
        return text, []

    lead_text = text[: accepted[0]["start"]].strip()
    items = []
    for index, marker in enumerate(accepted):
        content_start = marker["end"]
        content_end = accepted[index + 1]["start"] if index + 1 < len(accepted) else len(text)
        items.append(
            {
                "label": marker["label"],
                "text": text[content_start:content_end].strip(),
            }
        )

    return lead_text, items


def _select_sequential_markers(candidates: list[dict], level: str) -> list[dict]:
    if not candidates:
        return []

    start_index = _find_start_index(candidates, level)
    if start_index is None:
        return []

    accepted = [candidates[start_index]]
    for candidate in candidates[start_index + 1 :]:
        if _is_next_label(accepted[-1]["label"], candidate["label"], level):
            accepted.append(candidate)

    return accepted


def _find_start_index(candidates: list[dict], level: str) -> int | None:
    expected_start = {
        "subsection": "1",
        "clause": "a",
        "subclause": "i",
    }[level]

    for index, candidate in enumerate(candidates):
        if candidate["label"] == expected_start:
            return index

    if len(candidates) != 1:
        return None

    only_label = candidates[0]["label"]
    if level == "clause" and only_label in {"i", "v", "x"}:
        return None

    return 0


def _is_next_label(previous: str, current: str, level: str) -> bool:
    if level == "subsection":
        return current.isdigit() and previous.isdigit() and int(current) == int(previous) + 1

    if level == "clause":
        return len(previous) == 1 and len(current) == 1 and ord(current) == ord(previous) + 1

    previous_roman = _roman_to_int(previous)
    current_roman = _roman_to_int(current)
    if previous_roman is None or current_roman is None:
        return False

    return current_roman == previous_roman + 1


def _is_structural_boundary(text: str, index: int) -> bool:
    prefix = text[:index].rstrip(" \t")
    if not prefix:
        return True

    previous_char = prefix[-1]
    return previous_char in {"\n", ":", ";", "-", ".", "(", "[", "—", "–"}


def _trim_toc_section_matches(text: str, matches: list[re.Match]) -> tuple[list[re.Match], int]:
    """Drop table-of-contents matches when section numbering restarts in the full document."""
    if not matches:
        return [], 0

    start_index = 0
    previous_key = _section_match_sort_key(matches[0])
    for index, match in enumerate(matches[1:], start=1):
        current_key = _section_match_sort_key(match)
        if current_key < previous_key:
            start_index = index
            break
        previous_key = current_key

    intro_start = matches[start_index - 1].end() if start_index > 0 else 0
    return matches[start_index:], intro_start


def _section_match_sort_key(match: re.Match) -> tuple[int, tuple[int, ...], str]:
    value = match.group(1).upper()
    number_match = re.fullmatch(r"(\d+)([A-Z]*)", value)
    if not number_match:
        return (-1, (), value)

    number = int(number_match.group(1))
    suffix = number_match.group(2)
    suffix_key = tuple(ord(character) - ord("A") + 1 for character in suffix)
    return (number, suffix_key, value)


def _split_inline_section_body(title: str, body_text: str) -> tuple[str, str]:
    inline_body_match = re.search(r"^(.*?)[\-\u2013\u2014]\s*(\(\d+\).*)$", title)
    if not inline_body_match:
        return title, body_text

    clean_title = inline_body_match.group(1).rstrip(" -–—:")
    inline_body = inline_body_match.group(2).strip()
    combined_body = _join_text_parts(inline_body, body_text)
    return clean_title, combined_body


def _build_citation_path(chunk: dict) -> str:
    if not chunk.get("section"):
        return "Unstructured Context"

    citation = f"Section {chunk['section']}"
    if chunk.get("subsection"):
        citation += f"({chunk['subsection']})"
    if chunk.get("clause"):
        citation += f"({chunk['clause']})"
    if chunk.get("subclause"):
        citation += f"({chunk['subclause']})"
    return citation


def _join_text_parts(*parts: str | None) -> str:
    cleaned_parts = [part.strip() for part in parts if part and part.strip()]
    return "\n".join(cleaned_parts)


def _merge_spaced_letters(match: re.Match) -> str:
    return match.group(0).replace(" ", "")


def _roman_to_int(value: str) -> int | None:
    numerals = {"i": 1, "v": 5, "x": 10}
    value = value.lower()
    total = 0
    previous = 0

    for character in reversed(value):
        current = numerals.get(character)
        if current is None:
            return None
        if current < previous:
            total -= current
        else:
            total += current
            previous = current

    return total if total > 0 else None


if __name__ == "__main__":
    ingest_documents()
