"""
claim_verifier.py - Deep claim and citation verification against retrieved passages.

This module:
1. Validates citation filenames, page numbers (when available), and excerpts
   against the actual text of retrieved passages.
2. Extracts discrete factual claims from generated answers.
3. Classifies each claim as 'supported', 'unsupported', or 'unverifiable'.
4. Enforces the strict invariant: NEVER mark unverified claims as verified.
5. Safely catches and handles LLM generation errors without crashing.
"""

from __future__ import annotations

import json
import logging
import re
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums and Data Models
# ---------------------------------------------------------------------------

class ClaimStatus(str, Enum):
    supported = "supported"
    unsupported = "unsupported"
    unverifiable = "unverifiable"


class VerifiedClaim(BaseModel):
    claim_text: str
    status: ClaimStatus
    source_filename: str | None = None
    page: int | None = None
    excerpt: str | None = None
    reasoning: str | None = None


class ClaimVerificationInfo(BaseModel):
    verified_claims: list[VerifiedClaim] = Field(default_factory=list)
    supported_count: int = 0
    unsupported_count: int = 0
    unverifiable_count: int = 0
    dropped_citations_count: int = 0


# ---------------------------------------------------------------------------
# Text Normalization & Excerpt Matching
# ---------------------------------------------------------------------------

def _normalize_for_matching(text: str) -> str:
    """Normalize text by lowercasing, converting punctuation to space, collapsing whitespace."""
    if not text:
        return ""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower(), flags=re.UNICODE)
    return " ".join(cleaned.split())


def _excerpt_matches_passage(excerpt: str, passage_text: str) -> bool:
    """
    Check if citation excerpt is substantively contained in the passage text.
    Handles minor whitespace/punctuation differences and sliding window overlap.
    """
    norm_ex = _normalize_for_matching(excerpt)
    norm_pa = _normalize_for_matching(passage_text)

    if not norm_ex or not norm_pa:
        return False

    # 1. Exact normalized containment
    if norm_ex in norm_pa:
        return True

    # 2. Sliding window n-gram match for longer excerpts with minor OCR/truncation differences
    words = norm_ex.split()
    if len(words) >= 4:
        window_size = min(6, len(words))
        for i in range(len(words) - window_size + 1):
            subphrase = " ".join(words[i : i + window_size])
            if subphrase in norm_pa:
                return True

    return False


# ---------------------------------------------------------------------------
# Citation Validation
# ---------------------------------------------------------------------------

def validate_citations_against_passages(
    raw_citations: list[dict | Any],
    passages: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Validate citation filenames, page numbers (when available), and excerpts
    against actual retrieved passages.

    Returns:
        (valid_citations, dropped_citations)
    """
    if not passages:
        dropped = []
        for c in raw_citations:
            c_dict = c if isinstance(c, dict) else c.model_dump()
            dropped.append({"citation": c_dict, "reason": "No retrieved passages available"})
        return [], dropped

    # Group passages by source filename
    passages_by_file: dict[str, list[dict]] = {}
    for p in passages:
        fn = p.get("source_filename")
        if fn:
            passages_by_file.setdefault(fn, []).append(p)

    valid: list[dict] = []
    dropped: list[dict] = []

    for c in raw_citations:
        c_dict = c if isinstance(c, dict) else c.model_dump()
        fn = c_dict.get("source_filename")
        cite_page = c_dict.get("page")
        excerpt = c_dict.get("excerpt", "")

        # 1. Filename validation
        if not fn or fn not in passages_by_file:
            dropped.append({
                "citation": c_dict,
                "reason": f"Filename '{fn}' does not match any retrieved passage",
            })
            continue

        candidate_passages = passages_by_file[fn]

        # 2. Page number validation (when available on candidate passages)
        known_pages = {p.get("page") for p in candidate_passages if p.get("page") is not None}
        if cite_page is not None and known_pages and cite_page not in known_pages:
            dropped.append({
                "citation": c_dict,
                "reason": f"Page {cite_page} does not match retrieved passage pages {sorted(list(known_pages))}",
            })
            continue

        # 3. Excerpt validation against actual passage text
        matched_passage = None
        for p in candidate_passages:
            p_text = p.get("text", "")
            if _excerpt_matches_passage(excerpt, p_text):
                matched_passage = p
                break

        if not matched_passage:
            dropped.append({
                "citation": c_dict,
                "reason": f"Excerpt not found in retrieved passage text of '{fn}'",
            })
            continue

        # If citation page was None but matched passage has a page, we can preserve or inherit
        if cite_page is None and matched_passage.get("page") is not None:
            c_dict["page"] = matched_passage.get("page")

        valid.append(c_dict)

    return valid, dropped


# ---------------------------------------------------------------------------
# Claim Extraction
# ---------------------------------------------------------------------------

DISCLAIMER_KEYWORDS = [
    "general guidance only",
    "not legal advice",
    "consult a qualified",
    "कायदेशीर सल्ला",
    "सल्ला घ्या",
    "परामर्श करें",
]


def extract_claims(text: str) -> list[str]:
    """
    Split generated answer into individual factual assertions.
    Preserves English sentence boundaries, Devanagari purna virama (।),
    and numbered or bulleted list points.
    Filters out disclaimer sentences and very short fragments.
    """
    if not text or not text.strip():
        return []

    # Normalize line breaks and list bullets
    cleaned_text = re.sub(r"^\s*[-*•]\s*", "", text, flags=re.MULTILINE)
    cleaned_text = re.sub(r"^\s*\d+[\.\)]\s*", "", cleaned_text, flags=re.MULTILINE)

    # Split on sentence boundaries (. ! ? । or newlines)
    raw_sentences = re.split(r"(?<=[.!?।])\s+|\n{2,}", cleaned_text)

    claims: list[str] = []
    for sent in raw_sentences:
        s = sent.strip()
        if len(s) < 15:
            continue
        # Skip disclaimer / generic advisory sentences
        s_lower = s.lower()
        if any(dk in s_lower for dk in DISCLAIMER_KEYWORDS):
            continue
        claims.append(s)

    if not claims and text.strip():
        claims = [text.strip()]

    return claims


# ---------------------------------------------------------------------------
# ClaimVerifier
# ---------------------------------------------------------------------------

class ClaimVerifier:
    """
    Verifies factual claims in generated answers against actual retrieved passage contents.
    Identifies supported, unsupported, and unverifiable claims.
    Never marks unverified claims as verified.
    Safely handles LLM errors.
    """

    def __init__(self, llm: Optional[Any] = None) -> None:
        self._llm = llm

    def verify(
        self,
        answer: str,
        passages: list[dict],
        citations: list[dict | Any],
    ) -> tuple[list[VerifiedClaim], list[dict], list[dict], list[dict]]:
        """
        Execute deep verification:
        1. Validate citations against actual passage texts.
        2. Extract claims from answer.
        3. Verify claims against passage contents.
        4. Guarantee no unverified claim is marked supported.

        Returns:
            (verified_claims, valid_citations, dropped_citations, failures)
        """
        # Step 1: Validate citations
        valid_citations, dropped_citations = validate_citations_against_passages(
            citations, passages
        )

        # Step 2: Extract claims
        claims = extract_claims(answer)
        if not claims:
            return [], valid_citations, dropped_citations, []

        failures: list[dict] = []
        verified_claims: list[VerifiedClaim] = []

        # Step 3: Verify claims using LLM if available, else deterministic verification
        if self._llm and getattr(self._llm, "is_configured", False):
            try:
                verified_claims = self._verify_with_llm(claims, passages)
            except Exception as exc:
                logger.warning("LLM claim verification failed: %s; marking claims as unverifiable", exc)
                failures.append({
                    "module": "claim_verification",
                    "failure_type": "llm_verification_error",
                    "message": f"LLM claim verification failed: {exc}",
                    "recovery_attempted": False,
                    "recovered": False,
                })
                # Safety invariant: On verification error, never mark unverified claims as supported!
                verified_claims = [
                    VerifiedClaim(
                        claim_text=c,
                        status=ClaimStatus.unverifiable,
                        reasoning=f"Unverified due to verification error: {exc}",
                    )
                    for c in claims
                ]
        else:
            verified_claims = self._verify_deterministic(claims, passages, valid_citations)

        # Step 4: Strict double-check invariant: NEVER mark an unverified claim as supported.
        passages_by_file = {p.get("source_filename"): p for p in passages if p.get("source_filename")}
        for vc in verified_claims:
            if vc.status == ClaimStatus.supported:
                # Must have an actual matching passage and excerpt
                fn = vc.source_filename
                ex = vc.excerpt
                if not fn or fn not in passages_by_file or not ex:
                    vc.status = ClaimStatus.unverifiable
                    vc.reasoning = "Downgraded: passage or excerpt not provided to substantiate support"
                else:
                    target_passage = passages_by_file[fn]
                    if not _excerpt_matches_passage(ex, target_passage.get("text", "")):
                        vc.status = ClaimStatus.unverifiable
                        vc.reasoning = f"Downgraded: supporting excerpt was not found in passage '{fn}'"

        return verified_claims, valid_citations, dropped_citations, failures

    def _verify_with_llm(self, claims: list[str], passages: list[dict]) -> list[VerifiedClaim]:
        """Call LLM to evaluate claims against passages with structured JSON output."""
        passages_text_blocks = []
        for i, p in enumerate(passages, 1):
            fn = p.get("source_filename", "Unknown")
            pg = p.get("page")
            pg_str = f"Page {pg}" if pg else "Unspecified page"
            passages_text_blocks.append(f"Passage [{i}] (File: {fn}, {pg_str}):\n{p.get('text', '')}")

        passages_formatted = "\n\n".join(passages_text_blocks)
        claims_formatted = "\n".join(f"{i+1}. {c}" for i, c in enumerate(claims))

        prompt = f"""You are a strict legal claim verification engine for intellectual property and regulatory law.
Verify whether each claim in the answer is factually supported by the retrieved passages.

RETRIEVED PASSAGES:
{passages_formatted}

CLAIMS TO VERIFY:
{claims_formatted}

INSTRUCTIONS:
For each claim, determine its status:
- "supported": The claim is directly and factually backed by the text in the retrieved passages. You MUST quote the exact verbatim excerpt and source_filename.
- "unsupported": The claim contradicts the passages, or makes an affirmative assertion that is contradicted by the legal texts.
- "unverifiable": The passages do not mention or provide sufficient factual basis to prove or disprove the claim.

NEVER mark a claim as "supported" unless you can identify the exact verbatim text from the passages that proves it.
Return JSON with format:
{{
  "claims": [
    {{
      "claim_text": "string",
      "status": "supported" | "unsupported" | "unverifiable",
      "source_filename": "string or null",
      "page": integer or null,
      "excerpt": "verbatim excerpt or null",
      "reasoning": "brief explanation"
    }}
  ]
}}"""

        raw_output = self._llm.generate(prompt, temperature=0.0)
        # Parse output
        text = raw_output.strip()
        if text.startswith("```"):
            lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        data = json.loads(text)
        claims_data = data.get("claims", [])

        results: list[VerifiedClaim] = []
        for item in claims_data:
            st = item.get("status", "unverifiable").lower()
            if st not in ("supported", "unsupported", "unverifiable"):
                st = "unverifiable"

            results.append(
                VerifiedClaim(
                    claim_text=item.get("claim_text", ""),
                    status=ClaimStatus(st),
                    source_filename=item.get("source_filename"),
                    page=item.get("page"),
                    excerpt=item.get("excerpt"),
                    reasoning=item.get("reasoning"),
                )
            )

        # In case LLM missed any claim, pad with unverifiable
        if len(results) < len(claims):
            existing_texts = {r.claim_text for r in results}
            for c in claims:
                if c not in existing_texts:
                    results.append(
                        VerifiedClaim(
                            claim_text=c,
                            status=ClaimStatus.unverifiable,
                            reasoning="Unverified by verification model",
                        )
                    )

        return results

    def _verify_deterministic(
        self,
        claims: list[str],
        passages: list[dict],
        valid_citations: list[dict],
    ) -> list[VerifiedClaim]:
        """
        Deterministic verification when LLM is unavailable or offline.
        Uses lexical overlap, generalized contradiction detection, and validated citation containment.
        Strictly abides by: Never mark unverified claims as supported.
        """
        combined_passage_text = " ".join(p.get("text", "") for p in passages).lower()
        results: list[VerifiedClaim] = []

        for claim in claims:
            c_lower = claim.lower()
            norm_c = _normalize_for_matching(claim)

            # Check for contradiction: e.g. positive patentability assertion vs statutory exclusions
            is_contradicted = False
            negative_in_corpus = any(neg in combined_passage_text for neg in ["not an invention", "not patentable", "excludes", "prohibits", "non-patentable", "ineligible"])
            positive_assertion_in_claim = any(pos in c_lower for pos in ["automatically patentable", "can be patented", "are patentable", "is patentable", "all ayurvedic", "always patentable", "entitled to patent"])
            if negative_in_corpus and positive_assertion_in_claim:
                if "traditional knowledge" in c_lower or "ayurved" in c_lower or "formulation" in c_lower or "knowledge" in c_lower:
                    is_contradicted = True

            if is_contradicted:
                results.append(
                    VerifiedClaim(
                        claim_text=claim,
                        status=ClaimStatus.unsupported,
                        reasoning="Contradicts statutory exclusions in retrieved passages",
                    )
                )
                continue

            # Check if claim is directly backed by a validated citation
            matched_citation = None
            for vc in valid_citations:
                ex = vc.get("excerpt", "")
                if ex and (_normalize_for_matching(ex) in norm_c or norm_c in _normalize_for_matching(ex)):
                    matched_citation = vc
                    break

            if matched_citation:
                results.append(
                    VerifiedClaim(
                        claim_text=claim,
                        status=ClaimStatus.supported,
                        source_filename=matched_citation.get("source_filename"),
                        page=matched_citation.get("page"),
                        excerpt=matched_citation.get("excerpt"),
                        reasoning="Directly backed by validated citation excerpt in retrieved passage",
                    )
                )
            else:
                # Check if claim directly matches a passage text clause
                matched_passage = None
                matched_snippet = None
                for p in passages:
                    p_text = p.get("text", "")
                    if norm_c and len(norm_c) >= 20 and _normalize_for_matching(p_text).find(norm_c) != -1:
                        matched_passage = p
                        matched_snippet = claim
                        break

                if matched_passage:
                    results.append(
                        VerifiedClaim(
                            claim_text=claim,
                            status=ClaimStatus.supported,
                            source_filename=matched_passage.get("source_filename"),
                            page=matched_passage.get("page"),
                            excerpt=matched_snippet,
                            reasoning="Directly grounded in retrieved passage text",
                        )
                    )
                else:
                    results.append(
                        VerifiedClaim(
                            claim_text=claim,
                            status=ClaimStatus.unverifiable,
                            reasoning="No direct passage excerpt or validated citation proves this assertion",
                        )
                    )

        return results
