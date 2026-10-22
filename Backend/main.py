
from pathlib import Path
import re
import logging
import sqlite3
import secrets
import hashlib
import hmac
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from retriever import Retriever, IndexNotBuiltError, RetrieverInitError, MAX_TOP_K
from chat import ChatEngine, ChatRequest, ChatResponse
from llm_provider import LLMConfigError, LLMProviderError
from pdf_service import get_secure_pdf_path, is_pdf_available, generate_answer_report_pdf

# Load .env file (secrets stay out of source control)
load_dotenv()

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="IP-SAKTI Sahayak API",
    description="Ayurveda IPR and Regulatory Guidance",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8443",
        "http://127.0.0.1:8443",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single shared retriever instance - index and model are loaded lazily
# on the first /search call, keeping startup time fast.
_retriever = Retriever()

# Chat engine reuses the same retriever (no second vector DB)
_chat_engine = ChatEngine(_retriever)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str = Field(..., description="Natural-language question or keywords")
    top_k: int = Field(5, ge=1, le=MAX_TOP_K, description="Number of passages to return")

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("query must not be blank")
        return v.strip()


class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    source_filename: str
    page: int | None
    text: str
    score: float


class SearchResponse(BaseModel):
    query: str
    top_k: int
    results: list[SearchResult]


# ---------------------------------------------------------------------------
# Existing endpoints (preserved unchanged)
# ---------------------------------------------------------------------------

@app.get("/")
def home():
    return {
        "message": "IP-SAKTI Sahayak backend is running"
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "ip-sakti-sahayak-api",
    }


# ---------------------------------------------------------------------------
# RAG retrieval endpoint
# ---------------------------------------------------------------------------

@app.post("/search", response_model=SearchResponse)
def search(body: SearchRequest):
    """
    Retrieve the most relevant passages from the Ayurveda legal corpus.

    - **query**: natural-language question (non-empty)
    - **top_k**: number of passages to return (1-20, default 5)

    Returns retrieved text, source filename, page number, and cosine
    similarity score.  No AI-generated answers are produced at this stage.
    """
    try:
        hits = _retriever.search(body.query, top_k=body.top_k)
    except IndexNotBuiltError as exc:
        logging.error("Search failed because vector index was not built: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=(
                "The knowledge-base index has not been built yet. "
                "Please run  python build_index.py  on the server."
            ),
        ) from exc
    except RetrieverInitError as exc:
        logging.error("Search failed due to retriever initialization error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="The retrieval service encountered an initialization failure. Please try again later.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return SearchResponse(
        query=body.query,
        top_k=body.top_k,
        results=[SearchResult(**h) for h in hits],
    )


# ---------------------------------------------------------------------------
# Grounded AI Q&A endpoint
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest):
    """
    Ask a legal/IP question about Ayurveda and receive a grounded AI answer.

    - **question**: natural-language question (3-1000 chars)
    - **jurisdiction**: "India" or "International"
    - **language**: "English", "Hindi", or "Marathi"

    Returns a structured answer with citations from actual documents,
    evidence status, confidence level, and a legal disclaimer.
    """
    try:
        return _chat_engine.answer(body)

    except LLMConfigError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "The AI language model is not configured. "
                "Set the GEMINI_API_KEY environment variable on the server."
            ),
        ) from exc

    except LLMProviderError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "The AI language model returned an error. "
                "Please try again in a few moments."
            ),
        ) from exc

    except IndexNotBuiltError as exc:
        logging.error("Chat failed because vector index was not built: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=(
                "The knowledge-base index has not been built yet. "
                "Please run  python build_index.py  on the server."
            ),
        ) from exc

    except RetrieverInitError as exc:
        logging.error("Chat failed due to retriever initialization error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="The retrieval engine encountered an initialization failure. Please try again later.",
        ) from exc

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# PDF Access and Document Serving endpoints
# ---------------------------------------------------------------------------

class DownloadAnswerPdfRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Question asked by the user")
    answer: str = Field(..., min_length=1, description="AI grounded answer")
    evidence_status: str = Field(default="sufficient", description="Evidence status")
    confidence: str = Field(default="medium", description="Confidence level")
    citations: list[dict] = Field(default_factory=list, description="Verified citations")
    jurisdiction: str = Field(default="India", description="Legal jurisdiction")
    language: str = Field(default="English", description="Response language")
    disclaimer: str = Field(
        default="This information is for general guidance only and is not legal advice.",
        description="Legal disclaimer",
    )


@app.get("/documents/{filename}/view")
def view_document_pdf(filename: str):
    """
    Securely view a real, verified legal source document inline.
    Protected against path traversal and unauthorized access.
    """
    safe_path = get_secure_pdf_path(filename)
    return FileResponse(
        path=safe_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{safe_path.name}"'},
    )


@app.get("/documents/{filename}/download")
def download_document_pdf(filename: str):
    """
    Securely download a real, verified legal source document as an attachment.
    Protected against path traversal and unauthorized access.
    """
    safe_path = get_secure_pdf_path(filename)
    return FileResponse(
        path=safe_path,
        media_type="application/pdf",
        filename=safe_path.name,
    )


@app.get("/documents/{filename}/status")
def document_pdf_status(filename: str):
    """Check availability of a source document PDF without raising exceptions."""
    available = is_pdf_available(filename)
    return {
        "filename": Path(filename).name if filename else "",
        "available": available,
        "message": (
            "Source PDF document is available."
            if available
            else "The requested PDF document is currently unavailable in the legal repository."
        ),
    }


@app.post("/chat/download-pdf")
def download_answer_pdf(body: DownloadAnswerPdfRequest):
    """
    Generate and download a comprehensive PDF report containing:
    the user question, AI grounded answer, evidence status, confidence level,
    citations (source filenames, page numbers, excerpts), and legal disclaimer.
    """
    try:
        pdf_bytes = generate_answer_report_pdf(
            question=body.question,
            answer=body.answer,
            evidence_status=body.evidence_status,
            confidence=body.confidence,
            citations=body.citations,
            disclaimer=body.disclaimer,
            jurisdiction=body.jurisdiction,
            language=body.language,
        )
        safe_title = re.sub(r"[^\w\-]", "_", body.question[:30]).strip("_") or "Answer"
        filename = f"IP-SAKTI-Sahayak-Guidance-{safe_title}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        logging.error("Failed to generate answer PDF: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to generate the PDF guidance report. Please try again later.",
        ) from exc


# ---------------------------------------------------------------------------
# Local account system: SQLite-backed registration/login and user-owned data.
# Passwords are PBKDF2 hashes; raw passwords are never stored.
# ---------------------------------------------------------------------------
AUTH_DB = Path(__file__).resolve().parent / "data" / "users.sqlite3"
AUTH_DB.parent.mkdir(parents=True, exist_ok=True)
_sessions: dict[str, int] = {}

def _db():
    conn = sqlite3.connect(AUTH_DB)
    conn.row_factory = sqlite3.Row
    return conn

def _init_auth_db():
    with _db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS user_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            language TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""")

_init_auth_db()

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=8, max_length=128)

class LoginRequest(BaseModel):
    email: str
    password: str

def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
    return salt.hex() + ":" + digest.hex()

def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split(":", 1)
        candidate = _password_hash(password, bytes.fromhex(salt_hex)).split(":", 1)[1]
        return hmac.compare_digest(candidate, digest_hex)
    except (ValueError, TypeError):
        return False

def _public_user(row):
    return {"id": row["id"], "name": row["name"], "email": row["email"], "created_at": row["created_at"]}

def _current_user(authorization: str | None):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    token = authorization.split(" ", 1)[1].strip()
    user_id = _sessions.get(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    with _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        _sessions.pop(token, None)
        raise HTTPException(status_code=401, detail="Account not found.")
    return row

@app.post("/auth/register")
def register_user(payload: RegisterRequest):
    name, email = payload.name.strip(), payload.email.strip().lower()
    if not name or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=422, detail="Enter a valid name and email address.")
    if len(payload.password) < 8:
        raise HTTPException(status_code=422, detail="Password must contain at least 8 characters.")
    now = datetime.now(timezone.utc).isoformat()
    try:
        with _db() as conn:
            cur = conn.execute("INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                               (name, email, _password_hash(payload.password), now))
            user_id = cur.lastrowid
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    token = secrets.token_urlsafe(32)
    _sessions[token] = user_id
    return {"token": token, "user": _public_user(row)}

@app.post("/auth/login")
def login_user(payload: LoginRequest):
    with _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email=?", (payload.email.strip().lower(),)).fetchone()
    if not row or not _verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    token = secrets.token_urlsafe(32)
    _sessions[token] = row["id"]
    return {"token": token, "user": _public_user(row)}

@app.get("/auth/me")
def get_current_user(authorization: str | None = Header(default=None)):
    row = _current_user(authorization)
    return {"user": _public_user(row)}

@app.post("/auth/logout")
def logout_user(authorization: str | None = Header(default=None)):
    if authorization and authorization.lower().startswith("bearer "):
        _sessions.pop(authorization.split(" ", 1)[1].strip(), None)
    return {"ok": True}

@app.get("/auth/history")
def get_user_history(authorization: str | None = Header(default=None)):
    row = _current_user(authorization)
    with _db() as conn:
        items = conn.execute(
            "SELECT id,question,answer,language,created_at FROM user_history WHERE user_id=? ORDER BY id DESC LIMIT 100",
            (row["id"],)
        ).fetchall()
    return {"items": [dict(item) for item in items]}

@app.post("/auth/history")
def save_user_history(payload: dict, authorization: str | None = Header(default=None)):
    row = _current_user(authorization)
    question = str(payload.get("question", "")).strip()[:4000]
    answer = str(payload.get("answer", "")).strip()[:20000]
    language = str(payload.get("language", "English"))[:40]
    if not question or not answer:
        raise HTTPException(status_code=422, detail="Question and answer are required.")
    with _db() as conn:
        conn.execute("INSERT INTO user_history(user_id,question,answer,language,created_at) VALUES(?,?,?,?,?)",
                     (row["id"], question, answer, language, datetime.now(timezone.utc).isoformat()))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin / corpus stats endpoint
# ---------------------------------------------------------------------------

_DOCUMENTS_JSON = Path(__file__).parent / "data" / "processed" / "documents.json"
_CHUNKS_JSON = Path(__file__).parent / "data" / "vector_store" / "chunks.json"
_LEGAL_DOCS_DIR = Path(__file__).parent / "data" / "legal_docs"


@app.get("/admin/corpus")
def admin_corpus():
    """
    Return real corpus statistics and document list from documents.json.
    No authentication required for read-only corpus overview (data is non-sensitive).
    """
    import json as _json

    docs_list: list[dict] = []
    total_chars = 0
    total_pages = 0

    if _DOCUMENTS_JSON.exists():
        try:
            raw = _json.loads(_DOCUMENTS_JSON.read_text(encoding="utf-8"))
            for doc in raw:
                filename = doc.get("filename", "")
                pdf_available = (_LEGAL_DOCS_DIR / filename).exists() if filename else False
                pages_count = len(doc.get("pages", []))
                char_count = int(doc.get("character_count", 0))
                total_chars += char_count
                total_pages += pages_count
                docs_list.append({
                    "filename": filename,
                    "document_id": doc.get("document_id", ""),
                    "file_type": doc.get("file_type", ".pdf"),
                    "pages": pages_count,
                    "character_count": char_count,
                    "status": doc.get("status", "extracted"),
                    "pdf_available": pdf_available,
                })
        except Exception as exc:
            logging.warning("admin_corpus: failed to read documents.json: %s", exc)

    chunk_count = 0
    if _CHUNKS_JSON.exists():
        try:
            chunks_raw = _json.loads(_CHUNKS_JSON.read_text(encoding="utf-8"))
            chunk_count = len(chunks_raw) if isinstance(chunks_raw, list) else 0
        except Exception as exc:
            logging.warning("admin_corpus: failed to read chunks.json: %s", exc)

    index_built = (_LEGAL_DOCS_DIR.parent / "vector_store" / "index.faiss").exists()

    return {
        "total_documents": len(docs_list),
        "total_pages": total_pages,
        "total_characters": total_chars,
        "total_chunks": chunk_count,
        "index_built": index_built,
        "documents": docs_list,
    }
