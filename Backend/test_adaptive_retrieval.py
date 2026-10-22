"""
test_adaptive_retrieval.py - Deterministic unit tests for Module 1: Adaptive Retrieval.

Tests:
1. Multilingual query handling: Devanagari digit translation, tokenization,
   and cross-lingual BM25 lexical expansion using MULTILINGUAL_LEGAL_MAP.
2. Non-calibrated probability check: Retrieval scores are heuristic ranking metrics,
   not calibrated probabilities.
3. Adaptive retrieval: Initial retrieval sufficient -> no retry needed.
4. Adaptive retrieval: Initial retrieval insufficient -> retry triggered and recovers relevant evidence.
5. Adaptive retrieval: Initial retrieval insufficient -> retry triggered but fails to recover (fictional query).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import pytest

from retriever import BM25Index, Retriever, DEV_DIGIT_MAP, MULTILINGUAL_LEGAL_MAP
from chat import (
    ChatEngine,
    ChatRequest,
    ChatResponse,
    EvidenceStatus,
    Jurisdiction,
    Language,
    ModuleStatus,
    _evaluate_evidence_sufficiency,
    _rule_based_query_expansion,
    MIN_EVIDENCE_SCORE,
)


def test_bm25_multilingual_tokenization_and_digit_normalization():
    """Verify Devanagari numerals are translated and legal section references preserved."""
    sample_text = "कलम ३(p) पेटंट कायदा १९७०"
    tokens = BM25Index._tokenize(sample_text)

    # Devanagari numerals ३ -> 3 and १९७० -> 1970
    assert "3(p)" in tokens, f"Expected '3(p)' in tokens, got: {tokens}"
    assert "1970" in tokens, f"Expected '1970' in tokens, got: {tokens}"
    assert "कलम" in tokens or "पेटंट" in tokens, f"Expected Indic words preserved, got: {tokens}"


def test_bm25_cross_lingual_expansion():
    """Verify BM25 search expands Indic terms to match English legal corpus."""
    corpus = [
        "The Patents Act 1970 Section 3(p) excludes traditional knowledge from patentability.",
        "The Biological Diversity Act 2002 governs access to biological resources.",
    ]
    bm25 = BM25Index(corpus)

    # Query in Marathi/Hindi with Devanagari numbers
    query = "भारतात पारंपरिक ज्ञानाला पेटंट कायदा १९७० मधील कलम ३(p) स्पष्ट करा"
    matches = bm25.search(query, top_k=2)

    assert len(matches) > 0, "BM25 should return matches via cross-lingual expansion"
    top_idx, top_score = matches[0]
    assert top_idx == 0, f"Expected passage 0 (Patent Act) to rank highest, got {top_idx}"
    assert top_score > 0.0, "Score should be positive"


def test_retrieval_scores_not_calibrated_probabilities():
    """
    Retrieval scores are ordinal heuristic ranking metrics, NOT calibrated
    posterior probabilities (e.g. they do not sum to 1.0 and do not imply Bayesian certainty).
    """
    corpus = [
        "Patent Act 1970 section 3(p) traditional knowledge.",
        "Patent Act 1970 section 3(e) mere admixture.",
        "Biological diversity act national biodiversity authority.",
    ]
    bm25 = BM25Index(corpus)
    matches = bm25.search("patent act 1970", top_k=3)

    assert len(matches) > 0
    scores = [s for _, s in matches]

    # Scores do not sum to 1.0
    total = sum(scores)
    assert abs(total - 1.0) > 0.01, f"Scores should not sum to 1.0 like a probability distribution: {total}"

    # Individual scores are heuristic ranking indicators
    for s in scores:
        assert isinstance(s, float)
        assert s >= 0.0


def test_adaptive_retrieval_initial_sufficient():
    """When initial retrieval finds strong evidence, no retry is needed."""
    mock_retriever = MagicMock(spec=Retriever)
    mock_retriever.is_ready = True
    # Initial search returns strong evidence
    mock_retriever.search.return_value = [
        {
            "chunk_id": "c1",
            "document_id": "doc1",
            "source_filename": "Patent_Act_1970.pdf",
            "page": 1,
            "text": "Section 3(p) excludes traditional knowledge from patentability.",
            "score": 0.85,
        },
        {
            "chunk_id": "c2",
            "document_id": "doc2",
            "source_filename": "Patent_Act_1970.pdf",
            "page": 2,
            "text": "Further provisions on patentable subject matter.",
            "score": 0.72,
        },
    ]

    engine = ChatEngine(mock_retriever)
    engine._llm = MagicMock()
    engine._llm.is_configured = True
    engine._llm.generate.return_value = json.dumps({
        "answer": "Under Section 3(p), traditional knowledge cannot be patented.",
        "citations": [
            {
                "source_filename": "Patent_Act_1970.pdf",
                "page": 1,
                "excerpt": "Section 3(p) excludes traditional knowledge",
            }
        ],
        "evidence_status": "sufficient",
        "confidence": "high",
    })

    req = ChatRequest(
        question="Can traditional knowledge be patented under Section 3(p)?",
        jurisdiction=Jurisdiction.india,
        language=Language.english,
    )
    resp = engine.answer(req)

    # Search should have been called only once (initial search, no retry)
    assert mock_retriever.search.call_count == 1
    assert resp.diagnostics.adaptive_retrieval_info.retry_attempted is False
    assert resp.diagnostics.adaptive_retrieval_info.retry_recovered is False
    assert resp.diagnostics.adaptive_retrieval == ModuleStatus.success


def test_adaptive_retrieval_retry_recovers_evidence():
    """When initial retrieval has insufficient evidence, retry triggers and recovers evidence."""
    mock_retriever = MagicMock(spec=Retriever)
    mock_retriever.is_ready = True

    # Call 1 (initial): returns insufficient/low-scoring passages
    initial_passages = [
        {
            "chunk_id": "c_weak",
            "document_id": "doc_weak",
            "source_filename": "General_Intro.pdf",
            "page": 1,
            "text": "Introduction to Indian intellectual property concepts.",
            "score": 0.20,  # Below MIN_EVIDENCE_SCORE (0.35)
        }
    ]

    # Call 2 (retry with expanded query): recovers strong passages
    recovered_passages = [
        {
            "chunk_id": "c_strong",
            "document_id": "Patent_Act_1970.pdf",
            "source_filename": "Patent_Act_1970.pdf",
            "page": 1,
            "text": "Section 3(p) excludes traditional knowledge from patentability.",
            "score": 0.88,
        }
    ]

    mock_retriever.search.side_effect = [initial_passages, recovered_passages]

    engine = ChatEngine(mock_retriever)
    engine._llm = MagicMock()
    engine._llm.is_configured = True
    # Mock LLM for both expansion and generation
    engine._llm.generate.side_effect = [
        # LLM query expansion response
        "Patents Act 1970 Section 3(p) traditional knowledge",
        # LLM answer generation response
        json.dumps({
            "answer": "Section 3(p) excludes traditional knowledge from being patented.",
            "citations": [
                {
                    "source_filename": "Patent_Act_1970.pdf",
                    "page": 1,
                    "excerpt": "Section 3(p) excludes traditional knowledge",
                }
            ],
            "evidence_status": "sufficient",
            "confidence": "high",
        }),
        # Claim verification LLM response
        json.dumps({
            "claims": [
                {
                    "claim_text": "Section 3(p) excludes traditional knowledge from being patented.",
                    "status": "supported",
                    "source_filename": "Patent_Act_1970.pdf",
                    "page": 1,
                    "excerpt": "Section 3(p) excludes traditional knowledge",
                    "reasoning": "Directly confirmed by statutory text",
                }
            ]
        }),
    ]

    req = ChatRequest(
        question="Tell me about that rule that stops patenting old ayurvedic knowledge",
        jurisdiction=Jurisdiction.india,
        language=Language.english,
    )
    resp = engine.answer(req)

    # Retriever.search was called twice: initial + retry
    assert mock_retriever.search.call_count == 2
    assert resp.diagnostics.adaptive_retrieval_info.retry_attempted is True
    assert resp.diagnostics.adaptive_retrieval_info.retry_recovered is True
    assert resp.diagnostics.adaptive_retrieval == ModuleStatus.success

    # Verified that failure was recorded with recovery
    retrieval_failures = [f for f in resp.diagnostics.failures if f.module == "adaptive_retrieval"]
    assert len(retrieval_failures) == 1
    assert retrieval_failures[0].recovery_attempted is True
    assert retrieval_failures[0].recovered is True


def test_adaptive_retrieval_retry_fails_to_recover_fictional():
    """When query is fictional, initial retrieval fails, retry fails, and insufficient evidence is reported."""
    mock_retriever = MagicMock(spec=Retriever)
    mock_retriever.is_ready = True

    # Both initial and retry return zero qualifying passages
    mock_retriever.search.side_effect = [[], []]

    engine = ChatEngine(mock_retriever)
    engine._llm = MagicMock()
    engine._llm.is_configured = True
    engine._llm.generate.return_value = "Fictional Act 2099 filing fee"

    req = ChatRequest(
        question="What is the government fee under the Fictional Act 2099?",
        jurisdiction=Jurisdiction.india,
        language=Language.english,
    )
    resp = engine.answer(req)

    assert resp.diagnostics.adaptive_retrieval_info.retry_attempted is True
    assert resp.diagnostics.adaptive_retrieval_info.retry_recovered is False
    assert resp.diagnostics.adaptive_retrieval == ModuleStatus.insufficient_evidence
    assert resp.evidence_status == EvidenceStatus.insufficient
    assert resp.confidence == "low"
    assert len(resp.citations) == 0
