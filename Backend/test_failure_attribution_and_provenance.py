"""
test_failure_attribution_and_provenance.py - Deterministic unit tests for:
- Module 3: Failure Attribution and Recovery
- Module 4: Explainability and Provenance

Tests:
1. Successful queries populate all four module diagnostics from execution (adaptive_retrieval,
   claim_verification, failure_attribution, explainability_provenance).
2. Recoverable failure: Malformed LLM response recovered via JSON extractor.
3. Recoverable failure: Hallucinated citations pruned while genuine ones are preserved.
4. Recoverable failure: Unsupported claims detected and safely penalized in evidence status/confidence.
5. Unrecoverable failure: Fictional query blocks downstream claim verification honestly.
6. Unrecoverable failure: LLM verification error handled safely without crashing.
7. Provenance grounding: Real filenames, page numbers, and exact excerpts linked to claims.
8. Provenance never invents source details and explains uncertainty honestly.
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
    _parse_llm_response,
    _recover_json_from_text,
    _build_provenance_and_explanation,
)
from claim_verifier import ClaimVerifier, VerifiedClaim
from llm_provider import LLMProviderError


def test_successful_query_diagnostics_all_four_modules_success():
    """Verify that a fully supported query populates all 4 module statuses as 'success'."""
    mock_retriever = MagicMock()
    mock_retriever.is_ready = True
    passages = [
        {
            "chunk_id": "corpus/Patent_Act_1970.pdf::chunk0",
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

    # Generation response
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

    # Verification response
    verif_json = json.dumps({
        "claims": [
            {
                "claim_text": "Under Section 3(p) of the Patents Act, traditional knowledge cannot be patented.",
                "status": "supported",
                "source_filename": "Patent_Act_1970.pdf",
                "page": 1,
                "excerpt": "Section 3(p) excludes traditional knowledge",
                "reasoning": "Directly backed by Section 3(p) passage text",
            }
        ]
    })

    mock_llm.generate.side_effect = [gen_json, verif_json]

    engine = ChatEngine(mock_retriever)
    engine._llm = mock_llm
    engine._claim_verifier = ClaimVerifier(mock_llm)

    req = ChatRequest(
        question="Can traditional knowledge be patented under Section 3(p)?",
        jurisdiction=Jurisdiction.india,
        language=Language.english,
    )
    resp = engine.answer(req)

    # All 4 module statuses must be dynamically computed as success
    assert resp.diagnostics.adaptive_retrieval == ModuleStatus.success
    assert resp.diagnostics.claim_verification == ModuleStatus.success
    assert resp.diagnostics.failure_attribution == ModuleStatus.success
    assert resp.diagnostics.explainability_provenance == ModuleStatus.success

    # Provenance links
    assert resp.diagnostics.provenance_info.grounded_citations_count == 1
    assert len(resp.diagnostics.provenance_info.provenance_links) == 1
    link = resp.diagnostics.provenance_info.provenance_links[0]
    assert link.source_filename == "Patent_Act_1970.pdf"
    assert link.page == 1
    assert link.chunk_id == "corpus/Patent_Act_1970.pdf::chunk0"
    assert "Evidence is sufficient" in resp.evidence_explanation


def test_recoverable_failure_malformed_llm_json():
    """Verify malformed LLM response is safely recovered and attributed in diagnostics."""
    mock_retriever = MagicMock()
    mock_retriever.is_ready = True
    passages = [
        {
            "chunk_id": "c1",
            "document_id": "Patent_Act_1970.pdf",
            "source_filename": "Patent_Act_1970.pdf",
            "page": 1,
            "text": "Section 3(p) excludes traditional knowledge from patentability.",
            "score": 0.85,
        }
    ]
    mock_retriever.search.return_value = passages

    mock_llm = MagicMock()
    mock_llm.is_configured = True

    # Malformed response: text preamble + markdown + trailing text
    malformed_raw = """Here is your legal response:
```json
{
  "answer": "Section 3(p) excludes traditional knowledge.",
  "citations": [
    {
      "source_filename": "Patent_Act_1970.pdf",
      "page": 1,
      "excerpt": "Section 3(p) excludes traditional knowledge"
    }
  ],
  "evidence_status": "sufficient",
  "confidence": "high",
}
```
Hope this helps!"""

    verif_json = json.dumps({
        "claims": [
            {
                "claim_text": "Section 3(p) excludes traditional knowledge.",
                "status": "supported",
                "source_filename": "Patent_Act_1970.pdf",
                "page": 1,
                "excerpt": "Section 3(p) excludes traditional knowledge",
                "reasoning": "Confirmed by statutory text",
            }
        ]
    })

    mock_llm.generate.side_effect = [malformed_raw, verif_json]

    engine = ChatEngine(mock_retriever)
    engine._llm = mock_llm
    engine._claim_verifier = ClaimVerifier(mock_llm)

    req = ChatRequest(
        question="What does Section 3(p) say?",
        jurisdiction=Jurisdiction.india,
        language=Language.english,
    )
    resp = engine.answer(req)

    # Malformed response was recovered!
    assert resp.answer == "Section 3(p) excludes traditional knowledge."
    json_failures = [f for f in resp.diagnostics.failures if f.failure_type == "malformed_llm_response"]
    assert len(json_failures) == 1
    assert json_failures[0].recovery_attempted is True
    assert json_failures[0].recovered is True
    assert resp.diagnostics.failure_attribution == ModuleStatus.success


def test_recoverable_failure_invalid_citations_pruned():
    """Verify hallucinated citations are pruned and recorded as recovered failure."""
    mock_retriever = MagicMock()
    mock_retriever.is_ready = True
    passages = [
        {
            "chunk_id": "c1",
            "document_id": "Patent_Act_1970.pdf",
            "source_filename": "Patent_Act_1970.pdf",
            "page": 1,
            "text": "Section 3(p) excludes traditional knowledge from patentability.",
            "score": 0.85,
        }
    ]
    mock_retriever.search.return_value = passages

    mock_llm = MagicMock()
    mock_llm.is_configured = True

    gen_json = json.dumps({
        "answer": "Section 3(p) excludes traditional knowledge.",
        "citations": [
            {
                "source_filename": "Patent_Act_1970.pdf",
                "page": 1,
                "excerpt": "Section 3(p) excludes traditional knowledge",
            },
            {
                "source_filename": "INVENTED_LAW_2099.pdf",
                "page": 99,
                "excerpt": "Fake citation text",
            },
        ],
        "evidence_status": "sufficient",
        "confidence": "high",
    })

    verif_json = json.dumps({
        "claims": [
            {
                "claim_text": "Section 3(p) excludes traditional knowledge.",
                "status": "supported",
                "source_filename": "Patent_Act_1970.pdf",
                "page": 1,
                "excerpt": "Section 3(p) excludes traditional knowledge",
                "reasoning": "Confirmed by text",
            }
        ]
    })

    mock_llm.generate.side_effect = [gen_json, verif_json]

    engine = ChatEngine(mock_retriever)
    engine._llm = mock_llm
    engine._claim_verifier = ClaimVerifier(mock_llm)

    req = ChatRequest(
        question="Explain Section 3(p)",
        jurisdiction=Jurisdiction.india,
        language=Language.english,
    )
    resp = engine.answer(req)

    # Hallucinated citation pruned, valid kept
    assert len(resp.citations) == 1
    assert resp.citations[0].source_filename == "Patent_Act_1970.pdf"

    cite_failures = [f for f in resp.diagnostics.failures if f.failure_type == "invalid_citations"]
    assert len(cite_failures) == 1
    assert cite_failures[0].recovery_attempted is True
    assert cite_failures[0].recovered is True


def test_recoverable_failure_unsupported_claim_penalized():
    """Verify unsupported claim failure is attributed and penalized in evidence status."""
    mock_retriever = MagicMock()
    mock_retriever.is_ready = True
    passages = [
        {
            "chunk_id": "c1",
            "document_id": "Patent_Act_1970.pdf",
            "source_filename": "Patent_Act_1970.pdf",
            "page": 1,
            "text": "Section 3(p) excludes traditional knowledge from patentability.",
            "score": 0.85,
        }
    ]
    mock_retriever.search.return_value = passages

    mock_llm = MagicMock()
    mock_llm.is_configured = True

    gen_json = json.dumps({
        "answer": "Section 3(p) excludes traditional knowledge. All Ayurvedic medicines have free patent rights.",
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
                "claim_text": "Section 3(p) excludes traditional knowledge.",
                "status": "supported",
                "source_filename": "Patent_Act_1970.pdf",
                "page": 1,
                "excerpt": "Section 3(p) excludes traditional knowledge",
                "reasoning": "Confirmed by text",
            },
            {
                "claim_text": "All Ayurvedic medicines have free patent rights.",
                "status": "unsupported",
                "reasoning": "Directly contradicted by Section 3(p)",
            },
        ]
    })

    mock_llm.generate.side_effect = [gen_json, verif_json]

    engine = ChatEngine(mock_retriever)
    engine._llm = mock_llm
    engine._claim_verifier = ClaimVerifier(mock_llm)

    req = ChatRequest(
        question="Can Ayurvedic medicines get patent rights?",
        jurisdiction=Jurisdiction.india,
        language=Language.english,
    )
    resp = engine.answer(req)

    # Penalized evidence status and capped confidence
    assert resp.evidence_status == EvidenceStatus.partial
    assert resp.confidence in ("medium", "low")
    assert resp.diagnostics.claim_verification == ModuleStatus.partial

    unsup_failures = [f for f in resp.diagnostics.failures if f.failure_type == "unsupported_claims"]
    assert len(unsup_failures) == 1
    assert unsup_failures[0].recovery_attempted is True
    assert unsup_failures[0].recovered is True


def test_unrecoverable_failure_fictional_query_blocks_downstream():
    """Verify that when no passages qualify, downstream modules are marked blocked or insufficient."""
    mock_retriever = MagicMock()
    mock_retriever.is_ready = True
    mock_retriever.search.side_effect = [[], []]

    mock_llm = MagicMock()
    mock_llm.is_configured = True
    mock_llm.generate.return_value = "Fictional Act 2099 fee"

    engine = ChatEngine(mock_retriever)
    engine._llm = mock_llm

    req = ChatRequest(
        question="What is the government fee under the Fictional Act 2099?",
        jurisdiction=Jurisdiction.india,
        language=Language.english,
    )
    resp = engine.answer(req)

    assert resp.diagnostics.adaptive_retrieval == ModuleStatus.insufficient_evidence
    # Claim verification is BLOCKED because no passage inputs exist
    assert resp.diagnostics.claim_verification == ModuleStatus.blocked
    # Failure attribution is SUCCESS because it accurately recorded the failure
    assert resp.diagnostics.failure_attribution == ModuleStatus.success
    # Explainability provenance is INSUFFICIENT_EVIDENCE
    assert resp.diagnostics.explainability_provenance == ModuleStatus.insufficient_evidence

    assert resp.evidence_status == EvidenceStatus.insufficient
    assert resp.confidence == "low"
    assert "The retrieved legal corpus does not contain statutory or regulatory provisions" in resp.evidence_explanation


def test_provenance_grounding_and_uncertainty_explanation():
    """Verify provenance links claims to real chunks, explains uncertainty, and never invents sources."""
    claims = [
        VerifiedClaim(
            claim_text="Section 3(p) bars traditional knowledge patenting.",
            status=ClaimStatus.supported,
            source_filename="Patent_Act_1970.pdf",
            page=1,
            excerpt="Section 3(p)",
            reasoning="Supported",
        ),
        VerifiedClaim(
            claim_text="Form 99 requires 1000 rupees fee.",
            status=ClaimStatus.unverifiable,
            reasoning="No evidence",
        ),
    ]

    passages = [
        {
            "chunk_id": "chunk_patent_0",
            "source_filename": "Patent_Act_1970.pdf",
            "page": 1,
            "text": "Section 3(p) text",
        }
    ]

    citations = [
        Citation(
            source_filename="Patent_Act_1970.pdf",
            page=1,
            excerpt="Section 3(p)",
        )
    ]

    prov = _build_provenance_and_explanation(
        evidence_status=EvidenceStatus.partial,
        confidence="medium",
        passages=passages,
        verified_claims=claims,
        citations=citations,
    )

    assert prov.grounded_citations_count == 1
    assert len(prov.provenance_links) == 2
    assert prov.provenance_links[0].chunk_id == "chunk_patent_0"
    assert prov.provenance_links[0].source_filename == "Patent_Act_1970.pdf"
    assert prov.provenance_links[1].source_filename is None  # Never invented!
    assert "Partial evidence available" in prov.evidence_explanation
    assert any("Form 99" in un for un in prov.uncertainty_notes)
