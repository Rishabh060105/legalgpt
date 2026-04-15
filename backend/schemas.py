from typing import List, Literal, Optional

from pydantic import BaseModel

class Source(BaseModel):
    id: str
    title: str
    url: str
    excerpt: str
    full_text: Optional[str] = None

class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    use_rag: bool = True
    mode: Literal["legal", "general"] = "legal"

class ChatResponse(BaseModel):
    answer: str
    sources: List[Source]
    confidence: float
    session_id: Optional[str] = None

class TranscriptionResponse(BaseModel):
    text: str
