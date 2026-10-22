"""
build_index.py - Build the FAISS vector index from documents.json.

Run once (or re-run whenever the corpus changes):

    python build_index.py

Outputs written to  data/vector_store/:
    index.faiss        FAISS flat inner-product index (L2-normalised -> cosine)
    chunks.json        Chunk metadata list (same order as FAISS vectors)
    build_stats.json   Summary statistics for auditing

The model is downloaded on first run from Hugging Face and cached locally.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import faiss  # type: ignore
from sentence_transformers import SentenceTransformer  # type: ignore

from chunker import generate_chunks, DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
VECTOR_STORE_DIR = BASE_DIR / "data" / "vector_store"

DOCUMENTS_JSON = PROCESSED_DIR / "documents.json"
INDEX_PATH = VECTOR_STORE_DIR / "index.faiss"
CHUNKS_PATH = VECTOR_STORE_DIR / "chunks.json"
STATS_PATH = VECTOR_STORE_DIR / "build_stats.json"

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384  # output dimension of paraphrase-multilingual-MiniLM-L12-v2
BATCH_SIZE = 64


def build_index() -> None:
    print("=" * 60)
    print("IP-SAKTI Sahayak - RAG Index Builder")
    print("=" * 60)

    if not DOCUMENTS_JSON.exists():
        raise FileNotFoundError(
            f"documents.json not found at {DOCUMENTS_JSON}.\n"
            "Run ingest.py first."
        )

    # ------------------------------------------------------------------ load
    print(f"\nLoading documents from {DOCUMENTS_JSON} ...")
    with DOCUMENTS_JSON.open(encoding="utf-8") as fh:
        documents = json.load(fh)
    print(f"  Documents loaded : {len(documents)}")

    # ----------------------------------------------------------------- chunk
    print(
        f"\nChunking  (size={DEFAULT_CHUNK_SIZE}, overlap={DEFAULT_CHUNK_OVERLAP}) ..."
    )
    t0 = time.perf_counter()
    chunks = list(generate_chunks(documents))
    print(f"  Chunks produced  : {len(chunks)}  ({time.perf_counter()-t0:.1f}s)")

    if not chunks:
        raise RuntimeError(
            "No chunks were produced. Check that documents.json contains "
            "records with status='extracted' and non-empty pages."
        )

    # --------------------------------------------------------------- embed
    print(f"\nLoading embedding model  '{EMBEDDING_MODEL}' ...")
    model = SentenceTransformer(EMBEDDING_MODEL)

    texts = [c["text"] for c in chunks]
    print(f"  Encoding {len(texts)} chunks in batches of {BATCH_SIZE} ...")
    t0 = time.perf_counter()
    embeddings: np.ndarray = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        normalize_embeddings=True,   # L2-normalise -> inner product = cosine
        convert_to_numpy=True,
    )
    elapsed = time.perf_counter() - t0
    print(f"  Embedding shape  : {embeddings.shape}  ({elapsed:.1f}s)")

    # ----------------------------------------------------------------- FAISS
    print("\nBuilding FAISS index (IndexFlatIP = exact cosine search) ...")
    dim = embeddings.shape[1]
    assert dim == EMBEDDING_DIM, f"Unexpected embedding dim {dim}"

    index = faiss.IndexFlatIP(dim)
    index.add(embeddings.astype(np.float32))
    print(f"  Vectors indexed  : {index.ntotal}")

    # ----------------------------------------------------------------- save
    VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)

    faiss.write_index(index, str(INDEX_PATH))
    print(f"  FAISS index      -> {INDEX_PATH.relative_to(BASE_DIR)}")

    # Strip 'text' from metadata to keep chunks.json lean (text already in index)
    # Actually keep text so retriever can return it without a second look-up.
    with CHUNKS_PATH.open("w", encoding="utf-8") as fh:
        json.dump(chunks, fh, ensure_ascii=False, indent=2)
    print(f"  Chunk metadata   -> {CHUNKS_PATH.relative_to(BASE_DIR)}")

    # Summary stats
    doc_ids = {c["document_id"] for c in chunks}
    stats = {
        "embedding_model": EMBEDDING_MODEL,
        "chunk_size": DEFAULT_CHUNK_SIZE,
        "chunk_overlap": DEFAULT_CHUNK_OVERLAP,
        "total_documents_indexed": len(doc_ids),
        "total_chunks": len(chunks),
        "embedding_dim": dim,
        "faiss_index_type": "IndexFlatIP",
    }
    with STATS_PATH.open("w", encoding="utf-8") as fh:
        json.dump(stats, fh, indent=2)
    print(f"  Build stats      -> {STATS_PATH.relative_to(BASE_DIR)}")

    print("\nIndex build complete.")
    print(f"  {len(doc_ids)} documents  |  {len(chunks)} chunks  |  dim={dim}")


if __name__ == "__main__":
    build_index()
