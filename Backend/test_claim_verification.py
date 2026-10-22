"""
test_claim_verification.py - Deterministic unit tests for Module 2: Claim Verification.

Tests:
1. Validate citation filenames, page numbers (when available), and excerpts against retrieved passages.
2. Identify supported, unsupported, and unverifiable claims.
3. Strict invariant: Never mark unverified claims as verified.
4. Handle LLM errors safely without crashing.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock
import pytest

from claim_verifier import (
    ClaimVerifier,
    ClaimStatus,
    VerifiedClaim,
    validate_citations_against_passages,
    extract_claims,
)
from chat import (
    ChatEngine,
    ChatRequest,
    Citation,
    EvidenceStatus,
    Jurisdiction,
    Language,
    ModuleStatus,
)
from llm_provider import LLMProviderError


# ---------------------------------------------------------------------------
# Citation Validation Tests
# ---------------------------------------------------------------------------

def test_citation_validation_filenames_and_excerpts():
    """Verify citations require matching filenames and genuine passage excerpts."""
    passages = [
        {
            "source_filename": "Patent_Act_1970.pdf",
            "page": 1,
            "text": "Section 3(p) excludes traditional knowledge from patentability.",
        }
    ]

    raw_citations = [
        # Valid citation: matching file and verbatim excerpt
        {
            "source_filename": "Patent_Act_1970.pdf",
            "page": 1,
            "excerpt": "Section 3(p) excludes traditional knowledge",
        },
        # Invalid: hallucinated filename
        {
            "source_filename": "Non_Existent_Act.pdf",
            "page": 1,
            "excerpt": "Section 3(p) excludes traditional knowledge",
        },
        # Invalid: invented excerpt not in passage text
        {
            "source_filename": "Patent_Act_1970.pdf",
            "page": 1,
            "excerpt": "All Ayurvedic formulations receive automatic 20 year patents",
        },
    ]

    valid, dropped = validate_citations_against_passages(raw_citations, passages)

    assert len(valid) == 1, f"Expected 1 valid citation, got {len(valid)}"
    assert valid[0]["source_filename"] == "Patent_Act_1970.pdf"
    assert len(dropped) == 2, f"Expected 2 dropped citations, got {len(dropped)}"
    reasons = [d["reason"] for d in dropped]
    assert any("does not match any retrieved passage" in r for r in reasons)
    assert any("Excerpt not found" in r for r in reasons)


def test_citation_validation_page_numbers():
    """Verify citation page numbers must match when available on passages."""
    passages = [
        {
            "source_filename": "Patent_Act_1970.pdf",
            "page": 5,
            "text": "Section 3(p) excludes traditional knowledge from patentability.",
        }
    ]

    raw_citations = [
        # Matching page
        {
            "source_filename": "Patent_Act_1970.pdf",
            "page": 5,
            "excerpt": "Section 3(p) excludes traditional knowledge",
        },
        # Mismatched page: passage is page 5, citation claims page 99
        {
            "source_filename": "Patent_Act_1970.pdf",
            "page": 99,
            "excerpt": "Section 3(p) excludes traditional knowledge",
        },
    ]

    valid, dropped = validate_citations_against_passages(raw_citations, passages)
    assert len(valid) == 1
    assert valid[0]["page"] == 5
    assert len(dropped) == 1
    assert "Page 99 does not match" in dropped[0]["reason"]


# ---------------------------------------------------------------------------
# Claim Extraction and Classification Tests
# ---------------------------------------------------------------------------

def test_extract_claims():
    """Verify answer text is cleanly decomposed into discrete assertions without boilerplate."""
    answer = (
        "Under Section 3(p) of the Patents Act, traditional knowledge is not patentable. "
        "However, novel processes may qualify. "
        "This information is for general guidance only and is not legal advice."
    )
    claims = extract_claims(answer)
    assert len(claims) == 2
    assert "Section 3(p)" in claims[0]
    assert "novel processes" in claims[1]
    assert not any("guidance only" in c for c in claims)


def test_claim_verification_identifies_supported_unsupported_unverifiable():
    """Verify verifier accurately categorizes supported, unsupported, and unverifiable claims."""
    passages = [
        {
            "source_filename": "Patent_Act_1970.pdf",
            "page": 1,
            "text": "Section 3(p) specifies that an invention which in effect is traditional knowledge is not patentable.",
        }
    ]

    citations = [
        {
            "source_filename": "Patent_Act_1970.pdf",
            "page": 1,
            "excerpt": "traditional knowledge is not patentable",
        }
    ]

    mock_llm = MagicMock()
    mock_llm.is_configured = True
    mock_llm.generate.return_value = json.dumps({
        "claims": [
            {
                "claim_text": "Section 3(p) states traditional knowledge is not patentable.",
                "status": "supported",
                "source_filename": "Patent_Act_1970.pdf",
                "page": 1,
                "excerpt": "traditional knowledge is not patentable",
                "reasoning": "Directly supported by statutory text",
            },
            {
                "claim_text": "All Ayurvedic products are granted unconditional 50 year patent monopolies.",
                "status": "unsupported",
                "reasoning": "Contradicts Section 3(p) exclusion",
            },
            {
                "claim_text": "The government registration fee is exactly 1200 rupees under Rule 9.",
                "status": "unverifiable",
                "reasoning": "No passage mentions Rule 9 or filing fees",
            },
        ]
    })

    verifier = ClaimVerifier(mock_llm)
    answer = (
        "Section 3(p) states traditional knowledge is not patentable. "
        "All Ayurvedic products are granted unconditional 50 year patent monopolies. "
        "The government registration fee is exactly 1200 rupees under Rule 9."
    )

    verified, valid_cites, dropped_cites, failures = verifier.verify(answer, passages, citations)

    statuses = {vc.claim_text: vc.status for vc in verified}
    assert statuses["Section 3(p) states traditional knowledge is not patentable."] == ClaimStatus.supported
    assert statuses["All Ayurvedic products are granted unconditional 50 year patent monopolies."] == ClaimStatus.unsupported
    assert statuses["The government registration fee is exactly 1200 rupees under Rule 9."] == ClaimStatus.unverifiable
    assert len(failures) == 0


def test_never_mark_unverified_claims_as_verified():
    """
    Strict safety invariant: If LLM falsely reports a claim as 'supported'
    but the cited excerpt does NOT exist in the retrieved passage, it MUST be downgraded.
    """
    passages = [
        {
            "source_filename": "Patent_Act_1970.pdf",
            "page": 1,
            "text": "Section 3(p) excludes traditional knowledge from patentability.",
        }
    ]

    # LLM hallucinates that a fake claim is "supported" with a fake excerpt
    mock_llm = MagicMock()
    mock_llm.is_configured = True
    mock_llm.generate.return_value = json.dumps({
        "claims": [
            {
                "claim_text": "Ayurvedic products are exempt from patent examination.",
                "status": "supported",
                "source_filename": "Patent_Act_1970.pdf",
                "page": 1,
                "excerpt": "INVENTED EXCERPT NOT IN PASSAGE TEXT",
                "reasoning": "Fabricated by LLM",
            }
        ]
    })

    verifier = ClaimVerifier(mock_llm)
    verified, valid_cites, dropped_cites, failures = verifier.verify(
        "Ayurvedic products are exempt from patent examination.", passages, []
    )

    assert len(verified) == 1
    # INVARIANT ENFORCED: Downgraded to unverifiable!
    assert verified[0].status == ClaimStatus.unverifiable, (
        f"Claim was marked '{verified[0].status}' despite non-existent excerpt! Must be unverifiable."
    )
    assert "Downgraded" in verified[0].reasoning


def test_claim_verification_safe_llm_error_handling():
    """
    When LLM raises LLMProviderError or network exception during verification,
    the system must handle it safely, never mark unverified claims as supported,
    and record the failure in diagnostics.
    """
    passages = [
        {
            "source_filename": "Patent_Act_1970.pdf",
            "page": 1,
            "text": "Section 3(p) excludes traditional knowledge.",
        }
    ]

    mock_llm = MagicMock()
    mock_llm.is_configured = True
    mock_llm.generate.side_effect = LLMProviderError("Network connection reset")

    verifier = ClaimVerifier(mock_llm)
    answer = "Section 3(p) excludes traditional knowledge. Another unverified statement."

    # Must NOT raise exception
    verified, valid_cites, dropped_cites, failures = verifier.verify(answer, passages, [])

    # All unverified claims must NOT be marked supported
    for vc in verified:
        assert vc.status in (ClaimStatus.unsupported, ClaimStatus.unverifiable)
        assert vc.status != ClaimStatus.supported

    assert len(failures) == 1
    assert failures[0]["module"] == "claim_verification"
    assert failures[0]["failure_type"] == "llm_verification_error"


def test_chat_engine_downgrades_on_unsupported_claim():
    """
    End-to-end integration: An answer containing unsupported claims
    must have its evidence_status downgraded and confidence capped.
    """
    mock_retriever = MagicMock()
    mock_retriever.is_ready = True
    mock_retriever.search.return_value = [
        {
            "chunk_id": "c1",
            "document_id": "Patent_Act_1970.pdf",
            "source_filename": "Patent_Act_1970.pdf",
            "page": 1,
            "text": "Section 3(p) concerns traditional knowledge.",
            "score": 0.85,
        }
    ]

    mock_llm = MagicMock()
    mock_llm.is_configured = True
    # LLM generation returns an overbroad/unsupported answer with high confidence
    generation_json = json.dumps({
        "answer": "Every Ayurvedic formulation is automatically patentable in India.",
        "citations": [
            {
                "source_filename": "Patent_Act_1970.pdf",
                "page": 1,
                "excerpt": "Section 3(p) concerns traditional knowledge.",
            }
        ],
        "evidence_status": "sufficient",
        "confidence": "high",
    })

    # Claim verification returns unsupported
    verification_json = json.dumps({
        "claims": [
            {
                "claim_text": "Every Ayurvedic formulation is automatically patentable in India.",
                "status": "unsupported",
                "reasoning": "Section 3(p) excludes traditional knowledge; formulations are not automatically patentable.",
            }
        ]
    })

    mock_llm.generate.side_effect = [generation_json, verification_json]

    engine = ChatEngine(mock_retriever)
    engine._llm = mock_llm
    engine._claim_verifier = ClaimVerifier(mock_llm)

    req = ChatRequest(
        question="Is every Ayurvedic formulation automatically patentable?",
        jurisdiction=Jurisdiction.india,
        language=Language.english,
    )
    resp = engine.answer(req)

    # Claim verification caught the unsupported claim!
    assert resp.diagnostics.claim_verification_info.unsupported_count == 1
    assert resp.diagnostics.claim_verification_info.supported_count == 0
    # Evidence status MUST be downgraded to insufficient
    assert resp.evidence_status == EvidenceStatus.insufficient
    # Confidence MUST be low
    assert resp.confidence == "low"
    assert resp.diagnostics.claim_verification == ModuleStatus.insufficient_evidence
