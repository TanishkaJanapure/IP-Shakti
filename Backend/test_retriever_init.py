"""
test_retriever_init.py - Deterministic unit tests for retriever safe initialization:
1. Ensure uninitialized retriever raises RetrieverInitError when search() is called if components fail to load.
2. Ensure initialization failure raises RetrieverInitError and does not leave partial state.
3. Thread safety: concurrent searches do not observe a partially initialized model.
4. FastAPI endpoints (/search and /chat) map RetrieverInitError to clean HTTP 503 instead of 500.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from retriever import Retriever, RetrieverInitError, IndexNotBuiltError
from main import app


def test_uninitialized_model_raises_retriever_init_error():
    """Verify that calling search() when model is None raises RetrieverInitError instead of AttributeError."""
    retriever = Retriever()
    # Mock _ensure_loaded to simulate a bug where _ensure_loaded returns without populating _model
    with patch.object(retriever, "_ensure_loaded", return_value=None):
        retriever._model = None
        retriever._index = MagicMock()
        retriever._bm25 = MagicMock()
        retriever._chunks = [{"text": "sample"}]

        with pytest.raises(RetrieverInitError) as exc_info:
            retriever.search("Can turmeric be patented?", top_k=3)

        assert "not initialized" in str(exc_info.value).lower()
        # Verify it is NOT AttributeError
        assert not isinstance(exc_info.value, AttributeError)


def test_initialization_failure_raises_clear_error_and_cleans_up(tmp_path):
    """Verify that an exception during model/index loading raises RetrieverInitError and leaves state clean (None)."""
    retriever = Retriever(index_path=tmp_path / "missing.faiss", chunks_path=tmp_path / "missing.json")

    with pytest.raises(IndexNotBuiltError):
        retriever._ensure_loaded()

    # Now create genuine temporary index and chunk files on disk
    idx_file = tmp_path / "index.faiss"
    idx_file.write_bytes(b"dummy faiss index")
    chunks_file = tmp_path / "chunks.json"
    chunks_file.write_text(json.dumps([{"text": "passage"}]), encoding="utf-8")

    import sentence_transformers
    import faiss

    with patch.object(faiss, "read_index", return_value=MagicMock()), \
         patch.object(sentence_transformers, "SentenceTransformer", side_effect=RuntimeError("Weights download failed")):

        r2 = Retriever(index_path=idx_file, chunks_path=chunks_file)
        with pytest.raises(RetrieverInitError) as exc_info:
            r2._ensure_loaded()

        assert "Weights download failed" in str(exc_info.value)
        # Ensure all components were reset to None to prevent partial state
        assert r2._model is None
        assert r2._index is None
        assert r2._bm25 is None
        assert r2._chunks is None
        assert not r2.is_loaded


def test_concurrent_initialization_thread_safety(tmp_path):
    """Verify multiple concurrent requests never observe a partially initialized model."""
    idx_file = tmp_path / "index.faiss"
    idx_file.write_bytes(b"dummy faiss index")
    chunks_file = tmp_path / "chunks.json"
    chunks_file.write_text(
        json.dumps([{"text": "sample text", "source_filename": "act.pdf", "page": 1}]),
        encoding="utf-8",
    )

    retriever = Retriever(index_path=idx_file, chunks_path=chunks_file)
    observed_none_count = 0
    errors = []

    mock_model = MagicMock()
    mock_model.encode.return_value = MagicMock(astype=lambda x: MagicMock())

    def slow_model_init(model_name):
        time.sleep(0.05)
        return mock_model

    import sentence_transformers
    import faiss

    mock_idx = MagicMock()
    mock_idx.search.return_value = (MagicMock(), [[0]])

    with patch.object(faiss, "read_index", return_value=mock_idx), \
         patch.object(sentence_transformers, "SentenceTransformer", side_effect=slow_model_init):

        def worker():
            nonlocal observed_none_count
            try:
                res = retriever.search("Ayurveda patent", top_k=1)
                if retriever._model is None:
                    observed_none_count += 1
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert not errors, f"Concurrent workers encountered errors: {errors}"
    assert observed_none_count == 0, "A worker observed an uninitialized model!"
    assert retriever.is_loaded


def test_main_search_endpoint_handles_init_error():
    """Test that /search returns HTTP 503 with clean detail when RetrieverInitError occurs."""
    client = TestClient(app)
    with patch("main._retriever.search", side_effect=RetrieverInitError("Corrupted index file")):
        response = client.post("/search", json={"query": "patenting neem"})
        assert response.status_code == 503
        data = response.json()
        assert "retrieval service encountered an initialization failure" in data["detail"].lower()


def test_main_chat_endpoint_handles_init_error():
    """Test that /chat returns HTTP 503 with clean detail when RetrieverInitError occurs."""
    client = TestClient(app)
    with patch("main._chat_engine.answer", side_effect=RetrieverInitError("Model loading timeout")):
        response = client.post(
            "/chat",
            json={"question": "Can I patent an Ayurvedic formulation?", "jurisdiction": "India", "language": "English"},
        )
        assert response.status_code == 503
        data = response.json()
        assert "retrieval engine encountered an initialization failure" in data["detail"].lower()
