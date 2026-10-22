"""
retriever.py - Reusable RAG retrieval module with hybrid (dense semantic + lexical BM25/keyword) search.

Usage
-----
    from retriever import Retriever

    r = Retriever()               # loads index lazily on first call
    results = r.search("Can traditional Ayurvedic knowledge be patented?", top_k=5)
    for hit in results:
        print(hit["score"], hit["source_filename"], hit["page"], hit["text"][:200])

The retriever is designed to be imported by the FastAPI app and also used
standalone in scripts / tests. It never exposes local filesystem paths
in its output.
"""

from __future__ import annotations

import json
import logging
import math
import re
import threading
from collections import Counter
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths (relative to this file so the module is portable)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
VECTOR_STORE_DIR = BASE_DIR / "data" / "vector_store"
INDEX_PATH = VECTOR_STORE_DIR / "index.faiss"
CHUNKS_PATH = VECTOR_STORE_DIR / "chunks.json"

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Maximum chunks the API will ever return (safety cap)
MAX_TOP_K = 20

# Reciprocal Rank Fusion parameter
RRF_K = 60

# Devanagari numeral translation to ASCII digits
DEV_DIGIT_MAP = str.maketrans("०१२३४५६७८९", "0123456789")

# Domain-specific cross-lingual terminology mapping for BM25 lexical alignment
MULTILINGUAL_LEGAL_MAP: dict[str, str] = {
    # Marathi & Hindi
    "पारंपरिक": "traditional",
    "परंपरागत": "traditional",
    "पारम्परिक": "traditional",
    "ज्ञान": "knowledge",
    "ज्ञानाला": "knowledge",
    "ज्ञानाचा": "knowledge",
    "ज्ञानाचे": "knowledge",
    "ज्ञानकोश": "knowledge",
    "आयुर्वेदिक": "ayurvedic ayurveda",
    "आयुर्वेद": "ayurveda",
    "आयुर्वेदातील": "ayurveda",
    "पेटंट": "patent",
    "पेटंटला": "patent",
    "पेटंट्स": "patent",
    "एकस्व": "patent",
    "कायदा": "act",
    "कायद्यानुसार": "act",
    "अधिनियम": "act",
    "कानून": "act law",
    "कलम": "section",
    "धारा": "section",
    "भारतात": "india",
    "भारत": "india",
    "भारतीय": "indian",
    "औषध": "drug medicine",
    "औषधे": "drug medicine",
    "औषधी": "drug medicine",
    "दवा": "drug medicine",
    "दवाई": "drug medicine",
    "जैवविविधता": "biodiversity",
    "विविधता": "diversity",
    "हक्क": "rights",
    "अधिकार": "rights",
    "शोध": "invention",
    "संशोधन": "research invention",
    "आविष्कार": "invention",
    "नियम": "rules",
    "नियमावली": "rules",
    "उल्लंघन": "infringement",
    # Tamil / Telugu / Bengali common statutory terms
    "பாரம்பரிய": "traditional",
    "அறிவு": "knowledge",
    "காப்புரிமை": "patent",
    "சட்டம்": "act law",
    "பிரிவு": "section",
    "సనాతన": "traditional",
    "జ్ఞానం": "knowledge",
    "పేటెంట్": "patent",
    "చట్టం": "act law",
    "సాంప్రదాయ": "traditional",
    "ঐতিহ্যবাহী": "traditional",
    "পেটেন্ট": "patent",
    "আইন": "act law",
}
# Maintain backwards-compatible alias
MARATHI_HINDI_LEGAL_MAP = MULTILINGUAL_LEGAL_MAP


class RetrieverInitError(RuntimeError):
    """Raised when the retriever fails to initialize (model, index, or metadata)."""


class IndexNotBuiltError(RetrieverInitError):
    """Raised when the FAISS index has not been built yet."""


class BM25Index:
    """
    Lightweight, dependency-free BM25 implementation for legal corpus passages.
    Specifically indexes alphanumeric terms, section references like '3(p)',
    '158B', act names, Indic terms, and year tokens.
    """

    def __init__(self, corpus: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus)
        self.doc_lengths = []
        self.doc_freqs: dict[str, int] = Counter()
        self.term_freqs: list[dict[str, int]] = []

        total_length = 0
        for doc in corpus:
            tokens = self._tokenize(doc)
            length = len(tokens)
            self.doc_lengths.append(length)
            total_length += length
            
            tf = Counter(tokens)
            self.term_freqs.append(tf)
            for token in tf:
                self.doc_freqs[token] += 1

        self.avg_doc_len = total_length / self.corpus_size if self.corpus_size > 0 else 0

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """
        Tokenizes text preserving legal section numbers, acronyms, and alphanumeric terms.
        Normalizes Devanagari numerals to ASCII digits (e.g. ३(p) -> 3(p)).
        Preserves statutory tokens: '3(p)', '158b', '1970', 'patent', 'ayurvedic', and Unicode terms.
        """
        if not text:
            return []
        text = text.translate(DEV_DIGIT_MAP)
        # Match tokens like 3(p), 158B, statutory alphanumeric terms, and Unicode words
        raw_tokens = re.findall(r"[a-zA-Z0-9]+(?:\([a-zA-Z0-9]+\))?|[^\W\d_]+|\b\d+\b", text.lower(), re.UNICODE)
        return [t for t in raw_tokens if len(t) > 1 or t.isdigit()]

    def search(self, query: str, top_k: int = 15) -> list[tuple[int, float]]:
        """Return top_k matching doc indices with BM25 scores."""
        # Translate Devanagari numerals
        query = query.translate(DEV_DIGIT_MAP)
        tokens = self._tokenize(query)
        if not tokens:
            return []

        # Cross-lingual expansion: inject corresponding English legal keywords
        # so queries in Hindi/Marathi/etc. match English corpus passages in BM25
        expanded_tokens = list(tokens)
        for t in tokens:
            if t in MULTILINGUAL_LEGAL_MAP:
                expanded_tokens.extend(MULTILINGUAL_LEGAL_MAP[t].split())

        scores: list[float] = [0.0] * self.corpus_size

        for token in expanded_tokens:
            if token not in self.doc_freqs:
                continue
            df = self.doc_freqs[token]
            idf = math.log(1.0 + (self.corpus_size - df + 0.5) / (df + 0.5))

            # Weight specific statutory indicators higher
            token_weight = 1.0
            if "(" in token and ")" in token:  # e.g., '3(p)'
                token_weight = 3.0
            elif token.isdigit() and len(token) == 4:  # e.g., '1970'
                token_weight = 1.5

            for idx, tf_dict in enumerate(self.term_freqs):
                if token in tf_dict:
                    freq = tf_dict[token]
                    doc_len = self.doc_lengths[idx]
                    denom = freq + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avg_doc_len))
                    score = idf * (freq * (self.k1 + 1.0)) / denom
                    scores[idx] += score * token_weight

        ranked = sorted(
            [(i, s) for i, s in enumerate(scores) if s > 0.0],
            key=lambda x: x[1],
            reverse=True,
        )
        return ranked[:top_k]


class Retriever:
    """
    Thread-safe, lazily-loaded FAISS + BM25 hybrid retriever.

    Uses reciprocal-rank fusion (RRF) between multilingual dense vector similarity
    and lexical BM25 matching to achieve robust retrieval across English, Marathi,
    and statutory section citations (e.g., 'Section 3(p)').
    """

    def __init__(
        self,
        index_path: Path = INDEX_PATH,
        chunks_path: Path = CHUNKS_PATH,
        model_name: str = EMBEDDING_MODEL,
    ) -> None:
        self._index_path = index_path
        self._chunks_path = chunks_path
        self._model_name = model_name
        self._lock = threading.Lock()
        self._index = None
        self._chunks: list[dict] | None = None
        self._model = None
        self._bm25: BM25Index | None = None

    def _ensure_loaded(self) -> None:
        """Load index + metadata + model on first call in a thread-safe manner."""
        if (
            self._index is not None
            and self._bm25 is not None
            and self._chunks is not None
            and self._model is not None
        ):
            return

        with self._lock:
            if (
                self._index is not None
                and self._bm25 is not None
                and self._chunks is not None
                and self._model is not None
            ):
                return

            if not self._index_path.exists() or not self._chunks_path.exists():
                raise IndexNotBuiltError(
                    "Vector index not found. Run  python build_index.py  first."
                )

            try:
                import faiss  # type: ignore
                from sentence_transformers import SentenceTransformer  # type: ignore

                logger.info("Loading vector index from %s", self._index_path)
                loaded_index = faiss.read_index(str(self._index_path))

                logger.info("Loading metadata chunks from %s", self._chunks_path)
                with self._chunks_path.open(encoding="utf-8") as fh:
                    loaded_chunks = json.load(fh)

                # Build BM25 index on chunk text
                corpus_texts = [c["text"] for c in loaded_chunks]
                loaded_bm25 = BM25Index(corpus_texts)

                logger.info("Loading embedding model %s", self._model_name)
                loaded_model = SentenceTransformer(self._model_name)

                # Atomically assign all attributes once everything is successfully loaded
                self._index = loaded_index
                self._chunks = loaded_chunks
                self._bm25 = loaded_bm25
                self._model = loaded_model

            except IndexNotBuiltError:
                raise
            except Exception as exc:
                logger.error("Failed to initialize retriever components: %s", exc, exc_info=True)
                self._index = None
                self._chunks = None
                self._bm25 = None
                self._model = None
                raise RetrieverInitError(f"Retriever initialization failed: {exc}") from exc

    @property
    def is_ready(self) -> bool:
        """True when both the index and chunks files exist on disk."""
        return self._index_path.exists() and self._chunks_path.exists()

    @property
    def is_loaded(self) -> bool:
        """True when index, chunks, bm25, and embedding model are loaded in memory."""
        return (
            self._index is not None
            and self._bm25 is not None
            and self._chunks is not None
            and self._model is not None
        )

    def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """
        Return the top-k most relevant chunks for *query* using hybrid retrieval.

        Dense: multilingual MiniLM embeddings on FAISS IndexFlatIP (cosine).
        Lexical: BM25 keyword matching (crucial for exact sections like '3(p)').
        Fusion: Reciprocal Rank Fusion (RRF).
        """
        if not query or not query.strip():
            raise ValueError("query must be a non-empty string")

        top_k = max(1, min(top_k, MAX_TOP_K))

        self._ensure_loaded()

        if self._model is None or self._index is None or self._bm25 is None or self._chunks is None:
            raise RetrieverInitError("Retriever components are not initialized.")

        # 1. Dense Semantic Search
        query_vec: np.ndarray = self._model.encode(
            [query.strip()],
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype(np.float32)

        # Retrieve a candidate pool for dense search
        candidate_k = min(len(self._chunks), max(top_k * 4, 30))
        dense_scores, dense_indices = self._index.search(query_vec, candidate_k)

        # 2. Lexical BM25 Search
        bm25_matches = self._bm25.search(query, top_k=candidate_k)

        # 3. Reciprocal Rank Fusion (RRF)
        rrf_scores: dict[int, float] = {}
        original_dense_scores: dict[int, float] = {}
        bm25_ranks: dict[int, int] = {}

        for rank, (score, idx) in enumerate(zip(dense_scores[0], dense_indices[0])):
            if idx < 0:
                continue
            original_dense_scores[idx] = float(score)
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + 1.0 / (RRF_K + rank + 1)

        # Give strong weight to exact statutory/keyword matches
        for rank, (idx, bm25_score) in enumerate(bm25_matches):
            bm25_ranks[idx] = rank
            # If BM25 score is strong, give high ranking weight
            lex_weight = 2.0 if bm25_score > 15.0 else 1.2
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + lex_weight / (RRF_K + rank + 1)

        # Sort by combined RRF score
        sorted_indices = sorted(rrf_scores.keys(), key=lambda i: rrf_scores[i], reverse=True)

        results: list[dict] = []
        for idx in sorted_indices[:top_k]:
            chunk = self._chunks[idx]
            dense_score = original_dense_scores.get(idx, 0.0)
            has_bm25 = idx in bm25_ranks

            # Compute balanced heuristic relevance ranking score.
            # NOTE: This is an ordinal heuristic ranking score, NOT a calibrated posterior probability.
            if dense_score > 0 and has_bm25:
                # Confirmed by both dense semantic & lexical match
                combined_score = min(0.95, max(dense_score, 0.72 + (0.20 / (bm25_ranks[idx] + 1))))
            elif dense_score > 0:
                # Dense-only match
                combined_score = dense_score
            else:
                # Strong lexical-only match
                bm25_rank = bm25_ranks.get(idx, 10)
                combined_score = max(0.60, 0.75 - (bm25_rank * 0.03))

            results.append(
                {
                    "chunk_id": chunk["chunk_id"],
                    "document_id": chunk["document_id"],
                    "source_filename": chunk["source_filename"],
                    "page": chunk["page"],
                    "text": chunk["text"],
                    "score": round(float(combined_score), 4),
                }
            )

        return results

    def stats(self) -> dict:
        """Return basic stats about the loaded index (for health checks)."""
        self._ensure_loaded()
        return {
            "total_chunks": len(self._chunks),  # type: ignore[arg-type]
            "index_type": type(self._index).__name__,
            "embedding_model": self._model_name,
            "hybrid_bm25_indexed": self._bm25 is not None,
        }
