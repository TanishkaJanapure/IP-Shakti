"""
test_user_failure.py - Tests for user-facing simple failure notices and diagnostics separation:
1. Shows simple failure categories: Insufficient Evidence, Document Search Failed,
   Answer Verification Failed, Source Verification Failed, AI Service Unavailable.
2. Gives a short reason and helpful next action.
3. Shows messages only for real failures (None when fully supported/verified).
4. Never exposes stack traces or technical diagnostics in user_failure.
5. Keeps detailed diagnostics in the backend (resp.diagnostics).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock
import pytest

from chat import (
    ChatEngine,
    ChatRequest,
    ChatResponse,
    Citation,
    EvidenceStatus,
    Jurisdiction,
    Language,
    ModuleStatus,
    ClaimStatus,
    UserFailureNotice,
    _determine_user_failure,
    _no_evidence_answer,
)
from claim_verifier import ClaimVerifier, VerifiedClaim
from retriever import RetrieverInitError, IndexNotBuiltError


def test_successful_query_has_no_user_failure():
    """Verify that a successful, fully supported query produces user_failure=None."""
    mock_retriever = MagicMock()
    mock_retriever.is_ready = True
    passages = [
        {
            "chunk_id": "c1",
            "document_id": "Patent_Act_1970.pdf",
            "source_filename": "Patent_Act_1970.pdf",
            "page": 1,
            "text": "Section 3(p) excludes traditional knowledge from patentability.",
            "score": 0.88,
        }
    ]
    mock_retriever.search.return_value = passages

    mock_llm = MagicMock()
    mock_llm.is_configured = True

    gen_json = json.dumps({
        "answer": "Under Section 3(p) of the Patents Act, traditional knowledge cannot be patented.",
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

    verif_json = json.dumps({
        "claims": [
            {
                "claim_text": "Under Section 3(p) of the Patents Act, traditional knowledge cannot be patented.",
                "status": "supported",
                "source_filename": "Patent_Act_1970.pdf",
                "page": 1,
                "excerpt": "Section 3(p) excludes traditional knowledge",
                "reasoning": "Directly backed by Section 3(p)",
            }
        ]
    })

    mock_llm.generate.side_effect = [gen_json, verif_json]

    engine = ChatEngine(mock_retriever)
    engine._llm = mock_llm
    engine._claim_verifier = ClaimVerifier(mock_llm)

    req = ChatRequest(
        question="Can traditional Ayurvedic knowledge be patented?",
        jurisdiction=Jurisdiction.india,
        language=Language.english,
    )
    resp = engine.answer(req)

    # Success: no user failure notice
    assert resp.user_failure is None
    # Detailed diagnostics preserved in backend
    assert resp.diagnostics.adaptive_retrieval == ModuleStatus.success
    assert resp.diagnostics.claim_verification == ModuleStatus.success


def test_insufficient_evidence_user_failure():
    """Verify that a query with insufficient evidence yields a clean Insufficient Evidence notice."""
    mock_retriever = MagicMock()
    mock_retriever.is_ready = True
    mock_retriever.search.return_value = []  # No qualifying passages

    engine = ChatEngine(mock_retriever)
    req = ChatRequest(
        question="What is the patent term for Martian Ayurvedic remedies?",
        jurisdiction=Jurisdiction.india,
        language=Language.english,
    )
    resp = engine.answer(req)

    assert resp.evidence_status == EvidenceStatus.insufficient
    assert resp.user_failure is not None
    assert resp.user_failure.failure_type == "Insufficient Evidence"
    assert "curated legal corpus does not contain enough verified passages" in resp.user_failure.reason
    assert "rephrasing" in resp.user_failure.next_action.lower() or "consult" in resp.user_failure.next_action.lower()
    # Ensure no technical stack traces or exception reprs
    assert "Traceback" not in resp.user_failure.reason
    assert "Exception" not in resp.user_failure.reason
    # Detailed backend diagnostics still present
    assert resp.diagnostics.adaptive_retrieval == ModuleStatus.insufficient_evidence
    assert resp.diagnostics.claim_verification == ModuleStatus.blocked


def test_answer_verification_failed_user_failure():
    """Verify that unsupported claims trigger Answer Verification Failed notice."""
    mock_retriever = MagicMock()
    mock_retriever.is_ready = True
    passages = [
        {
            "chunk_id": "c1",
            "document_id": "Patent_Act_1970.pdf",
            "source_filename": "Patent_Act_1970.pdf",
            "page": 1,
            "text": "Section 3(p) excludes traditional knowledge.",
            "score": 0.85,
        }
    ]
    mock_retriever.search.return_value = passages

    mock_llm = MagicMock()
    mock_llm.is_configured = True

    gen_json = json.dumps({
        "answer": "All Ayurvedic formulations are globally exempt from patents and taxes.",
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

    # Verifier flags the claim as unsupported
    verif_json = json.dumps({
        "claims": [
            {
                "claim_text": "All Ayurvedic formulations are globally exempt from patents and taxes.",
                "status": "unsupported",
                "source_filename": "Patent_Act_1970.pdf",
                "page": 1,
                "excerpt": "Section 3(p) excludes traditional knowledge",
                "reasoning": "Statute says nothing about global tax exemptions",
            }
        ]
    })

    mock_llm.generate.side_effect = [gen_json, verif_json]

    engine = ChatEngine(mock_retriever)
    engine._llm = mock_llm
    engine._claim_verifier = ClaimVerifier(mock_llm)

    req = ChatRequest(
        question="Are Ayurvedic products exempt from taxes and patents?",
        jurisdiction=Jurisdiction.india,
        language=Language.english,
    )
    resp = engine.answer(req)

    assert resp.user_failure is not None
    assert resp.user_failure.failure_type == "Answer Verification Failed"
    assert "could not be verified" in resp.user_failure.reason.lower()
    assert "consult" in resp.user_failure.next_action.lower() or "review" in resp.user_failure.next_action.lower()
    # Detailed diagnostics preserved
    assert len(resp.diagnostics.failures) >= 1
    assert any(f.failure_type == "unsupported_claims" for f in resp.diagnostics.failures)


def test_source_verification_failed_user_failure():
    """Verify that dropped/hallucinated citations leaving zero sources trigger Source Verification Failed."""
    notice = _determine_user_failure(
        evidence_status=EvidenceStatus.partial,
        failures=[],
        verified_claims=[],
        citations=[],
        dropped_citations_count=2,
    )
    assert notice is not None
    assert notice.failure_type == "Source Verification Failed"
    assert "citations or source references could not be verified" in notice.reason
    assert "gazette" in notice.next_action or "statutory" in notice.next_action


def test_document_search_failed_user_failure():
    """Verify that unrecovered retrieval errors produce Document Search Failed."""
    from chat import FailureInfo

    notice = _determine_user_failure(
        evidence_status=EvidenceStatus.insufficient,
        failures=[
            FailureInfo(
                module="adaptive_retrieval",
                failure_type="retrieval_error",
                message="Vector store connection timeout",
                recovery_attempted=True,
                recovered=False,
            )
        ],
        verified_claims=[],
        citations=[],
        dropped_citations_count=0,
    )
    assert notice is not None
    assert notice.failure_type == "Document Search Failed"
    assert "document search service encountered an issue" in notice.reason
    assert "index is available" in notice.next_action


def test_ai_service_unavailable_user_failure():
    """Verify that unrecovered LLM provider failures produce AI Service Unavailable."""
    from chat import FailureInfo

    notice = _determine_user_failure(
        evidence_status=EvidenceStatus.insufficient,
        failures=[
            FailureInfo(
                module="llm_provider",
                failure_type="llm_provider_error",
                message="HTTP 503 Quota exceeded",
                recovery_attempted=False,
                recovered=False,
            )
        ],
        verified_claims=[],
        citations=[],
        dropped_citations_count=0,
    )
    assert notice is not None
    assert notice.failure_type == "AI Service Unavailable"
    assert "reasoning service is currently unavailable" in notice.reason
    assert "verify server configuration" in notice.next_action
