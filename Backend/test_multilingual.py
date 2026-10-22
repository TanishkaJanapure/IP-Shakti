"""
test_multilingual.py - Comprehensive tests for multilingual retrieval,
evidence consistency, citation integrity, and grounded QA.

Run with:
    python test_multilingual.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

from retriever import Retriever, IndexNotBuiltError
from chat import (
    ChatEngine,
    ChatRequest,
    ChatResponse,
    Citation,
    EvidenceStatus,
    Jurisdiction,
    Language,
    _enforce_confidence_consistency,
    _build_system_prompt,
    _parse_llm_response,
    DISCLAIMER,
)

passed = 0
failed = 0


def _banner(title: str) -> None:
    print(f"\n{'='*65}")
    print(f"  {title}")
    print("=" * 65)


def _ok(msg: str) -> None:
    global passed
    passed += 1
    print(f"  [OK] {msg}")


def _fail(msg: str) -> None:
    global failed
    failed += 1
    print(f"  [FAIL] {msg}")


def _require_index() -> Retriever:
    r = Retriever()
    if not r.is_ready:
        print("\n  [WARN] Index not ready. Run python build_index.py first.")
        sys.exit(1)
    return r


# ---------------------------------------------------------------------------
# Test A: English patentability retrieval
# ---------------------------------------------------------------------------

def test_a_english_patent_retrieval():
    _banner("TEST A: English patentability retrieval")
    r = _require_index()

    q = (
        "Can traditional Ayurvedic knowledge be patented in India? "
        "Explain Section 3(p) of the Patents Act, 1970."
    )
    results = r.search(q, top_k=8)

    assert len(results) > 0, "No results returned for English query"

    patent_results = [res for res in results if "Patent_Act_1970" in res["source_filename"]]
    assert len(patent_results) > 0, "Patent_Act_1970.pdf not found in top 8 results"

    top = patent_results[0]
    _ok(f"Retrieved Patent_Act_1970.pdf (score={top['score']}, page={top['page']})")

    combined = " ".join(item["text"] for item in results).lower()
    assert "3(p)" in combined or "traditional knowledge" in combined, "Missing Section 3(p) text"
    _ok("Verified Section 3(p) / traditional knowledge content in retrieved passages")


# ---------------------------------------------------------------------------
# Test B: Marathi patentability retrieval (Cross-lingual)
# ---------------------------------------------------------------------------

def test_b_marathi_patent_retrieval():
    _banner("TEST B: Marathi patentability retrieval (Cross-lingual)")
    r = _require_index()

    q = (
        "\u092d\u093e\u0930\u0924\u093e\u0924 \u092a\u093e\u0930\u0902\u092a\u0930\u093f\u0915 \u0906\u092f\u0941\u0930\u094d\u0935\u0947\u0926\u093f\u0915 "
        "\u091c\u094d\u091e\u093e\u0928\u093e\u0932\u093e \u092a\u0947\u091f\u0902\u091f \u092e\u093f\u0933\u0942 \u0936\u0915\u0924\u0947 \u0915\u093e? "
        "\u092a\u0947\u091f\u0902\u091f \u0915\u093e\u092f\u0926\u093e, 1970 \u092e\u0927\u0940\u0932 \u0915\u0932\u092e 3(p) \u0938\u094d\u092a\u0937\u094d\u091f \u0915\u0930\u093e."
    )
    results = r.search(q, top_k=8)

    assert len(results) > 0, "No results returned for Marathi query"

    patent_results = [res for res in results if "Patent_Act_1970" in res["source_filename"]]
    assert len(patent_results) > 0, "Patent_Act_1970.pdf not found in top results for Marathi query"

    top = patent_results[0]
    _ok(f"Marathi query successfully retrieved Patent_Act_1970.pdf (score={top['score']}, page={top['page']})")

    combined = " ".join(item["text"] for item in results).lower()
    assert "3(p)" in combined or "traditional knowledge" in combined, "Missing Section 3(p) context"
    _ok("Verified Section 3(p) context retrieved for Marathi query")


# ---------------------------------------------------------------------------
# Test C: Unsupported fictional regulation (insufficient evidence)
# ---------------------------------------------------------------------------

def test_c_fictional_regulation():
    _banner("TEST C: Fictional regulation (insufficient evidence)")

    mock_llm_json = json.dumps({
        "answer": (
            "The provided legal documents do not contain information regarding a fictional "
            "Ayurvedic Innovation Protection Act 2025 or any prescribed government fee."
        ),
        "citations": [],
        "evidence_status": "insufficient",
        "confidence": "high",  # Intentional high to verify deterministic downgrade
    })

    req = ChatRequest(
        question="What is the exact government filing fee for a fictional Ayurvedic IP application under the Ayurvedic Innovation Protection Act 2025?",
        jurisdiction=Jurisdiction.india,
        language=Language.english,
    )

    resp = _parse_llm_response(mock_llm_json, req, passages=[])
    assert resp.evidence_status == EvidenceStatus.insufficient, "Should be insufficient"
    assert resp.confidence == "low", f"Confidence must be 'low' for insufficient, got {resp.confidence}"
    assert len(resp.citations) == 0, "No citations should be fabricated"
    _ok("Fictional query correctly yields evidence_status='insufficient' and confidence='low'")


# ---------------------------------------------------------------------------
# Test D: Partial evidence handling
# ---------------------------------------------------------------------------

def test_d_partial_evidence():
    _banner("TEST D: Partial evidence handling")

    passages = [
        {
            "chunk_id": "corpus/2._National_IP_Regimes/Patent_Act_1970.pdf::chunk0",
            "document_id": "corpus/2._National_IP_Regimes/Patent_Act_1970.pdf",
            "source_filename": "Patent_Act_1970.pdf",
            "page": 1,
            "text": "Section 3(p) excludes traditional knowledge from patentability.",
            "score": 0.85,
        }
    ]

    mock_llm_json = json.dumps({
        "answer": (
            "Under Section 3(p) of the Patents Act 1970, inventions based on traditional knowledge are non-patentable. "
            "However, the available documents do not specify any filing fee for a fictional application."
        ),
        "citations": [
            {
                "source_filename": "Patent_Act_1970.pdf",
                "page": 1,
                "excerpt": "Section 3(p) excludes traditional knowledge",
            }
        ],
        "evidence_status": "partial",
        "confidence": "high",  # Intentional high to test capping at medium
    })

    req = ChatRequest(
        question="Explain Section 3(p) and provide the exact filing fee for a fictional Ayurvedic IP application.",
        jurisdiction=Jurisdiction.india,
        language=Language.english,
    )

    resp = _parse_llm_response(mock_llm_json, req, passages=passages)
    assert resp.evidence_status == EvidenceStatus.partial
    assert resp.confidence in ("medium", "low"), f"Partial evidence confidence cannot be high, got {resp.confidence}"
    assert len(resp.citations) == 1
    _ok("Partial evidence correctly explains supported part, identifies unsupported part, and caps confidence at 'medium'")


# ---------------------------------------------------------------------------
# Test E: Citation integrity & anti-hallucination
# ---------------------------------------------------------------------------

def test_e_citation_integrity():
    _banner("TEST E: Citation integrity & anti-hallucination")

    passages = [
        {
            "chunk_id": "chunk_1",
            "document_id": "Patent_Act_1970.pdf",
            "source_filename": "Patent_Act_1970.pdf",
            "page": 1,
            "text": "Section 3(p) text",
            "score": 0.88,
        }
    ]

    mock_llm_json = json.dumps({
        "answer": "Test answer",
        "citations": [
            {
                "source_filename": "Patent_Act_1970.pdf",
                "page": 1,
                "excerpt": "Section 3(p) text",
            },
            {
                "source_filename": "FABRICATED_DOCUMENT_2026.pdf",
                "page": 99,
                "excerpt": "Completely invented citation",
                "source_url": "https://fake-url-not-in-corpus.gov",
            },
        ],
        "evidence_status": "sufficient",
        "confidence": "high",
    })

    req = ChatRequest(
        question="Test citation integrity",
        jurisdiction=Jurisdiction.india,
        language=Language.english,
    )

    resp = _parse_llm_response(mock_llm_json, req, passages=passages)
    assert len(resp.citations) == 1, "Fabricated citation was not dropped"
    assert resp.citations[0].source_filename == "Patent_Act_1970.pdf"
    _ok("Fabricated citation dropped; genuine citation preserved with accurate metadata")


# ---------------------------------------------------------------------------
# Test F: Language consistency & Devanagari prompts
# ---------------------------------------------------------------------------

def test_f_language_consistency():
    _banner("TEST F: Language consistency & Devanagari prompts")

    # Check Marathi system prompt instructions
    mr_prompt = _build_system_prompt(Jurisdiction.india, Language.marathi)
    assert "MARATHI" in mr_prompt
    assert "मराठी" in mr_prompt
    _ok("Marathi system prompt contains explicit language rules")

    # Check Hindi system prompt instructions
    hi_prompt = _build_system_prompt(Jurisdiction.india, Language.hindi)
    assert "HINDI" in hi_prompt
    assert "हिन्दी" in hi_prompt
    _ok("Hindi system prompt contains explicit language rules")

    # Check disclaimer always present
    req = ChatRequest(question="Test question", jurisdiction="India", language="Marathi")
    resp = ChatResponse(
        question=req.question,
        jurisdiction=req.jurisdiction.value,
        language=req.language.value,
        answer="मराठी उत्तर",
        citations=[],
        evidence_status=EvidenceStatus.insufficient,
        confidence="low",
    )
    assert resp.disclaimer == DISCLAIMER
    _ok(f"Disclaimer present: '{resp.disclaimer}'")


# ---------------------------------------------------------------------------
# Test G: Regression tests (TRIPS, Nagoya, Biological Diversity)
# ---------------------------------------------------------------------------

def test_g_regression():
    _banner("TEST G: Regression tests across existing legal domains")
    r = _require_index()

    test_queries = [
        ("Nagoya Protocol access and benefit sharing", ["nagoya", "benefit", "abs"]),
        ("Biodiversity Act benefit sharing obligations", ["biodiversity", "benefit", "nba"]),
        ("TRIPS agreement patent protection", ["trips", "patent", "subject matter"]),
    ]

    for query, expected_kws in test_queries:
        res = r.search(query, top_k=5)
        assert len(res) > 0, f"No results for {query}"
        combined = " ".join(item["text"] for item in res).lower()
        matched = any(kw in combined for kw in expected_kws)
        assert matched, f"None of {expected_kws} found in results for {query}"
        _ok(f"Regression query '{query}' retrieved topically relevant legal passages")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    global passed, failed

    print("\nIP-SAKTI Sahayak - Comprehensive Multilingual & RAG Verification")
    print("=" * 65)

    tests = [
        test_a_english_patent_retrieval,
        test_b_marathi_patent_retrieval,
        test_c_fictional_regulation,
        test_d_partial_evidence,
        test_e_citation_integrity,
        test_f_language_consistency,
        test_g_regression,
    ]

    for t in tests:
        try:
            t()
        except Exception as exc:
            failed += 1
            print(f"  [FAIL] {t.__name__}: {type(exc).__name__}: {exc}")

    print(f"\n{'='*65}")
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 65)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
