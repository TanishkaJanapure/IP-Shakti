"""
test_chat.py - Tests for the grounded AI Q&A pipeline.

Run with:
    python test_chat.py

Tests cover:
  1. ChatRequest validation (blank question, invalid jurisdiction/language).
  2. Prompt construction (jurisdiction awareness, language instruction).
  3. Citation validation (hallucinated filenames are dropped).
  4. No-evidence fallback (returns insufficient status without LLM call).
  5. LLM config error handling (missing API key -> 503).
  6. Live end-to-end test (requires GEMINI_API_KEY in .env).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Load .env if present
from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

from chat import (
    ChatEngine,
    ChatRequest,
    ChatResponse,
    Citation,
    EvidenceStatus,
    Jurisdiction,
    Language,
    _build_system_prompt,
    _build_user_prompt,
    _parse_llm_response,
    _no_evidence_answer,
    DISCLAIMER,
)
from retriever import Retriever, IndexNotBuiltError
from llm_provider import LLMProvider, LLMConfigError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _banner(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print("=" * 60)


passed = 0
failed = 0


def _pass(msg: str) -> None:
    global passed
    passed += 1
    print(f"  [OK] {msg}")


def _fail(msg: str) -> None:
    global failed
    failed += 1
    print(f"  [FAIL] {msg}")


# ---------------------------------------------------------------------------
# Test 1: Input validation
# ---------------------------------------------------------------------------

def test_input_validation():
    _banner("TEST: ChatRequest input validation")

    # Blank question
    try:
        ChatRequest(question="   ", jurisdiction="India", language="English")
        _fail("Blank question should be rejected")
    except Exception:
        _pass("Blank question correctly rejected")

    # Too short
    try:
        ChatRequest(question="ab", jurisdiction="India", language="English")
        _fail("Too-short question should be rejected")
    except Exception:
        _pass("Too-short question correctly rejected")

    # Invalid jurisdiction
    try:
        ChatRequest(question="Test question?", jurisdiction="Mars", language="English")
        _fail("Invalid jurisdiction should be rejected")
    except Exception:
        _pass("Invalid jurisdiction correctly rejected")

    # Invalid language
    try:
        ChatRequest(question="Test question?", jurisdiction="India", language="Klingon")
        _fail("Invalid language should be rejected")
    except Exception:
        _pass("Invalid language correctly rejected")

    # Valid request
    try:
        req = ChatRequest(
            question="Can turmeric be patented?",
            jurisdiction="India",
            language="English",
        )
        assert req.question == "Can turmeric be patented?"
        assert req.jurisdiction == Jurisdiction.india
        assert req.language == Language.english
        _pass("Valid request accepted")
    except Exception as exc:
        _fail(f"Valid request rejected: {exc}")


# ---------------------------------------------------------------------------
# Test 2: Prompt construction
# ---------------------------------------------------------------------------

def test_prompt_construction():
    _banner("TEST: Prompt construction")

    # India jurisdiction
    prompt = _build_system_prompt(Jurisdiction.india, Language.english)
    assert "INDIAN law" in prompt, "India prompt missing jurisdiction"
    assert "NOT treat international" in prompt
    _pass("India jurisdiction prompt correct")

    # International jurisdiction
    prompt = _build_system_prompt(Jurisdiction.international, Language.english)
    assert "INTERNATIONAL law" in prompt
    _pass("International jurisdiction prompt correct")

    # Hindi language instruction
    prompt = _build_system_prompt(Jurisdiction.india, Language.hindi)
    assert "Hindi" in prompt
    _pass("Hindi language instruction present")

    # Marathi language instruction
    prompt = _build_system_prompt(Jurisdiction.india, Language.marathi)
    assert "Marathi" in prompt
    _pass("Marathi language instruction present")

    # User prompt with passages
    passages = [
        {"source_filename": "Test.pdf", "page": 3, "score": 0.85, "text": "Sample text"},
    ]
    user_prompt = _build_user_prompt("Test question?", passages)
    assert "Test question?" in user_prompt
    assert "Test.pdf" in user_prompt
    assert "Sample text" in user_prompt
    _pass("User prompt includes question and passages")

    # Empty passages
    user_prompt = _build_user_prompt("Test?", [])
    assert "No relevant passages" in user_prompt
    _pass("Empty passages case handled")


# ---------------------------------------------------------------------------
# Test 3: Citation validation
# ---------------------------------------------------------------------------

def test_citation_validation():
    _banner("TEST: Citation validation (hallucination filtering)")

    passages = [
        {"source_filename": "Patent_Act_1970.pdf", "page": 1, "score": 0.8,
         "text": "Section 3(p) traditional knowledge"},
        {"source_filename": "TRIPS_Patent.pdf", "page": 2, "score": 0.7,
         "text": "Article 27 patentable subject matter"},
    ]

    # LLM response with one valid and one hallucinated citation
    raw_json = json.dumps({
        "answer": "Yes, Section 3(p) addresses this.",
        "citations": [
            {"source_filename": "Patent_Act_1970.pdf", "page": 1,
             "excerpt": "Section 3(p)"},
            {"source_filename": "INVENTED_FILE.pdf", "page": 99,
             "excerpt": "This does not exist"},
        ],
        "evidence_status": "sufficient",
        "confidence": "high",
    })

    request = ChatRequest(
        question="Can traditional knowledge be patented?",
        jurisdiction="India",
        language="English",
    )

    result = _parse_llm_response(raw_json, request, passages)

    assert len(result.citations) == 1, f"Expected 1 citation, got {len(result.citations)}"
    assert result.citations[0].source_filename == "Patent_Act_1970.pdf"
    _pass("Hallucinated citation correctly dropped")
    _pass(f"Valid citation preserved: {result.citations[0].source_filename}")


def test_claim_support_gap():
    """A valid filename does not prove a claim is supported."""
    passages = [
        {
            "source_filename": "Patent_Act_1970.pdf",
            "page": 1,
            "score": 0.8,
            "text": "Section 3(p) concerns traditional knowledge."
        }
    ]

    raw_json = json.dumps({
        "answer": "Every Ayurvedic formulation is automatically patentable.",
        "citations": [
            {
                "source_filename": "Patent_Act_1970.pdf",
                "page": 1,
                "excerpt": "Section 3(p) concerns traditional knowledge."
            }
        ],
        "evidence_status": "sufficient",
        "confidence": "high",
    })

    request = ChatRequest(
        question="Is every Ayurvedic formulation automatically patentable?",
        jurisdiction="India",
        language="English",
    )

    result = _parse_llm_response(raw_json, request, passages)

    # This documents the current limitation: filename validation
    # alone can accept a citation that does not support the answer.
    assert len(result.citations) == 1
    assert result.evidence_status == EvidenceStatus.sufficient


# ---------------------------------------------------------------------------
# Test 4: No-evidence fallback
# ---------------------------------------------------------------------------

def test_no_evidence_fallback():
    _banner("TEST: No-evidence fallback")

    # English
    msg = _no_evidence_answer(Language.english)
    assert "do not establish" in msg
    assert "consult" in msg.lower()
    _pass("English no-evidence message correct")

    # Hindi
    msg = _no_evidence_answer(Language.hindi)
    assert len(msg) > 20
    _pass("Hindi no-evidence message present")

    # Marathi
    msg = _no_evidence_answer(Language.marathi)
    assert len(msg) > 20
    _pass("Marathi no-evidence message present")


# ---------------------------------------------------------------------------
# Test 5: LLM config error handling
# ---------------------------------------------------------------------------

def test_llm_config_error():
    _banner("TEST: LLM config error (missing API key)")

    # Temporarily remove API key
    original = os.environ.pop("GEMINI_API_KEY", None)
    try:
        provider = LLMProvider()
        assert not provider.is_configured, "Should not be configured without key"
        _pass("LLMProvider.is_configured = False when key missing")

        try:
            provider.generate("test")
            _fail("Should raise LLMConfigError")
        except LLMConfigError:
            _pass("LLMConfigError raised correctly")
    finally:
        if original:
            os.environ["GEMINI_API_KEY"] = original


# ---------------------------------------------------------------------------
# Test 6: Disclaimer always present
# ---------------------------------------------------------------------------

def test_disclaimer():
    _banner("TEST: Disclaimer always present")

    response = ChatResponse(
        question="Test",
        jurisdiction="India",
        language="English",
        answer="Test answer",
        citations=[],
        evidence_status=EvidenceStatus.partial,
        confidence="medium",
    )
    assert response.disclaimer == DISCLAIMER
    _pass(f"Disclaimer: '{response.disclaimer}'")


# ---------------------------------------------------------------------------
# Test 7: Live end-to-end (requires API key)
# ---------------------------------------------------------------------------

def test_live_chat():
    _banner("TEST: Live end-to-end chat (requires GEMINI_API_KEY)")

    if not os.environ.get("GEMINI_API_KEY"):
        print("  [SKIP] GEMINI_API_KEY not set -- skipping live test")
        print("         Set it in .env to run this test")
        return

    retriever = Retriever()
    if not retriever.is_ready:
        print("  [SKIP] Vector index not built -- run build_index.py first")
        return

    engine = ChatEngine(retriever)

    # Test 1: Supported question
    req = ChatRequest(
        question="Can traditional Ayurvedic knowledge be patented in India?",
        jurisdiction="India",
        language="English",
    )
    resp = engine.answer(req)
    print(f"  Question: {resp.question}")
    print(f"  Evidence: {resp.evidence_status}")
    print(f"  Confidence: {resp.confidence}")
    print(f"  Citations: {len(resp.citations)}")
    print(f"  Answer preview: {resp.answer[:200]}...")

    assert resp.answer, "Answer should not be empty"
    assert resp.disclaimer == DISCLAIMER
    _pass("Live Q&A returned a grounded answer")

    # Verify citations reference actual files
    for cite in resp.citations:
        print(f"    - {cite.source_filename} p.{cite.page}: {cite.excerpt[:80]}")
    if resp.citations:
        _pass(f"{len(resp.citations)} citations present")
    else:
        print("  [WARN] No citations returned (may indicate weak grounding)")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    global passed, failed

    print("\nIP-SAKTI Sahayak - Chat API Test Suite")
    print("=" * 60)

    tests = [
        test_input_validation,
        test_prompt_construction,
        test_citation_validation,
        test_no_evidence_fallback,
        test_llm_config_error,
        test_disclaimer,
        test_live_chat,
    ]

    for test in tests:
        try:
            test()
        except Exception as exc:
            failed += 1
            print(f"\n  [FAIL] {test.__name__}: {type(exc).__name__}: {exc}")

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
