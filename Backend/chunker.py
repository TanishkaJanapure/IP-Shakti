"""
chunker.py - Split extracted document pages into overlapping text chunks.

Each chunk preserves:
  - chunk_id       : globally unique identifier  "<document_id>::chunk<N>"
  - document_id    : relative posix path (no local filesystem prefix)
  - source_filename: basename of the source file
  - page           : page number from the original PDF (None for DOCX/TXT)
  - text           : chunk text
"""

from __future__ import annotations

import re
from typing import Generator

# ---------------------------------------------------------------------------
# Constants - can be overridden via environment or constructor args
# ---------------------------------------------------------------------------
DEFAULT_CHUNK_SIZE = 512    # characters
DEFAULT_CHUNK_OVERLAP = 128  # characters
MIN_CHUNK_LENGTH = 50       # discard chunks shorter than this

# document_id of the aggregated corpus file - excluded from indexing
CORPUS_DUMP_ID = "corpus/all_corpus_text.txt"


def _split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """
    Naïve overlapping character-window splitter with sentence-boundary snapping.

    Tries to end each window at the nearest sentence boundary ('. ', '! ',
    '? ', or newline) within the last 20 % of the window so chunks stay
    semantically coherent.
    """
    text = re.sub(r"\s+", " ", text).strip()
    chunks: list[str] = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + chunk_size, length)

        # Try to snap to a sentence boundary in the last 20 % of the window
        if end < length:
            snap_from = max(start, end - chunk_size // 5)
            for sep in (". ", "! ", "? ", "\n"):
                pos = text.rfind(sep, snap_from, end)
                if pos != -1:
                    end = pos + len(sep)
                    break

        chunk = text[start:end].strip()
        if len(chunk) >= MIN_CHUNK_LENGTH:
            chunks.append(chunk)

        if end >= length:
            break
        start = end - chunk_overlap  # slide back for overlap

    return chunks


def generate_chunks(
    documents: list[dict],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    exclude_document_ids: set[str] | None = None,
) -> Generator[dict, None, None]:
    """
    Yield chunk dicts from a list of ingested document records.

    Parameters
    ----------
    documents:
        Records loaded from ``data/processed/documents.json``.
    chunk_size:
        Target window size in characters.
    chunk_overlap:
        How many characters of the previous chunk to repeat.
    exclude_document_ids:
        Set of ``document_id`` values to skip (e.g. the all-corpus dump).
        Defaults to ``{CORPUS_DUMP_ID}``.
    """
    if exclude_document_ids is None:
        exclude_document_ids = {CORPUS_DUMP_ID}

    for doc in documents:
        doc_id: str = doc.get("document_id", "")
        filename: str = doc.get("filename", "")
        pages: list[dict] = doc.get("pages", [])

        # Skip documents that should not be indexed
        if doc_id in exclude_document_ids:
            continue

        # Skip documents whose status was not "extracted"
        if doc.get("status") != "extracted":
            continue

        chunk_counter = 0

        for page_record in pages:
            page_num = page_record.get("page")       # int or None
            text: str = page_record.get("text", "")

            if not text.strip():
                continue

            for fragment in _split_text(text, chunk_size, chunk_overlap):
                yield {
                    "chunk_id": f"{doc_id}::chunk{chunk_counter}",
                    "document_id": doc_id,
                    "source_filename": filename,
                    "page": page_num,
                    "text": fragment,
                }
                chunk_counter += 1
