"""
chat.py - Grounded AI question-answering module for IP-SAKTI Sahayak.

This module:
  1. Retrieves relevant passages from the vector store using hybrid retrieval (retriever.py).
  2. For non-English queries, also leverages query translation/expansion as a safety net,
     then merges results using reciprocal-rank fusion.
  3. Builds a grounded prompt with jurisdiction and language awareness.
  4. Calls the LLM to generate a structured, citation-backed answer.
  5. Validates that citations reference actual retrieved passages.
  6. Enforces confidence/evidence consistency rules.
  7. Returns structured JSON with answer, citations, evidence status,
     confidence, and disclaimer.
"""

from __future__ import annotations

import json
import logging
import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from retriever import Retriever, IndexNotBuiltError, RetrieverInitError
from llm_provider import LLMProvider, LLMConfigError, LLMProviderError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DISCLAIMER = "This information is for general guidance only and is not legal advice."

RETRIEVAL_TOP_K = 10  # number of passages to retrieve for grounding

MIN_EVIDENCE_SCORE = 0.35  # passages below this score are deemed insufficient

RRF_K = 60  # reciprocal-rank fusion constant

# ---------------------------------------------------------------------------
# Enums and models
# ---------------------------------------------------------------------------

class Jurisdiction(str, Enum):
    india = "India"
    international = "International"


class Language(str, Enum):
    english = "English"
    hindi = "Hindi"
    marathi = "Marathi"
    tamil = "Tamil"
    telugu = "Telugu"
    bengali = "Bengali"


class EvidenceStatus(str, Enum):
    sufficient = "sufficient"
    partial = "partial"
    insufficient = "insufficient"


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000,
                          description="The legal/IP question to answer")
    jurisdiction: Jurisdiction = Field(
        Jurisdiction.india,
        description="Jurisdiction context: India or International"
    )
    language: Language = Field(
        Language.english,
        description="Desired answer language: English, Hindi, Marathi, Tamil, Telugu, or Bengali"
    )

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question must not be blank")
        return v.strip()


class Citation(BaseModel):
    source_filename: str
    page: int | None = None
    excerpt: str = Field(..., description="Brief excerpt from the retrieved passage")
    source_url: str | None = None


from claim_verifier import (
    ClaimVerifier,
    ClaimStatus,
    VerifiedClaim,
    ClaimVerificationInfo,
    validate_citations_against_passages,
)


class ModuleStatus(str, Enum):
    success = "success"
    partial = "partial"
    failed = "failed"
    blocked = "blocked"
    insufficient_evidence = "insufficient_evidence"


class FailureInfo(BaseModel):
    failure_type: str | None = None
    module: str | None = None
    message: str | None = None
    recovery_attempted: bool = False
    recovered: bool = False


class AdaptiveRetrievalInfo(BaseModel):
    retry_attempted: bool = False
    retry_recovered: bool = False
    initial_evidence_sufficient: bool = True
    expansion_query: str | None = None
    passages_retrieved: int = 0


class ClaimProvenance(BaseModel):
    claim_text: str
    status: ClaimStatus
    source_filename: str | None = None
    page: int | None = None
    excerpt: str | None = None
    chunk_id: str | None = None


class ProvenanceInfo(BaseModel):
    grounded_citations_count: int = 0
    provenance_links: list[ClaimProvenance] = Field(default_factory=list)
    evidence_explanation: str = ""
    uncertainty_notes: list[str] = Field(default_factory=list)


class ModuleDiagnostics(BaseModel):
    adaptive_retrieval: ModuleStatus = ModuleStatus.blocked
    claim_verification: ModuleStatus = ModuleStatus.blocked
    failure_attribution: ModuleStatus = ModuleStatus.blocked
    explainability_provenance: ModuleStatus = ModuleStatus.blocked
    failures: list[FailureInfo] = Field(default_factory=list)
    adaptive_retrieval_info: AdaptiveRetrievalInfo = Field(default_factory=AdaptiveRetrievalInfo)
    claim_verification_info: ClaimVerificationInfo = Field(default_factory=ClaimVerificationInfo)
    provenance_info: ProvenanceInfo = Field(default_factory=ProvenanceInfo)


class UserFailureNotice(BaseModel):
    failure_type: str = Field(..., description="User-facing failure category")
    reason: str = Field(..., description="Short explanation of why it occurred")
    next_action: str = Field(..., description="Helpful next action for the user")


class ChatResponse(BaseModel):
    question: str
    jurisdiction: str
    language: str
    answer: str
    citations: list[Citation]
    evidence_status: EvidenceStatus
    confidence: str = Field(
        ..., description="Evidence strength: high, medium, or low"
    )
    disclaimer: str = DISCLAIMER
    diagnostics: ModuleDiagnostics = Field(
        default_factory=ModuleDiagnostics
    )
    claims: list[VerifiedClaim] = Field(
        default_factory=list
    )
    evidence_explanation: str = ""
    user_failure: Optional[UserFailureNotice] = None



# ---------------------------------------------------------------------------
# Query translation / expansion helper
# ---------------------------------------------------------------------------

def _contains_devanagari(text: str) -> bool:
    """Check if text contains Devanagari script characters."""
    return bool(re.search(r"[\u0900-\u097F]", text))


def _contains_indic(text: str) -> bool:
    """Check if text contains Indic script characters (Devanagari, Tamil, Telugu, Bengali, etc.)."""
    return bool(re.search(r"[\u0900-\u0D7F]", text))


def _rule_based_query_expansion(query: str) -> str:
    """
    Deterministic rule-based query expansion for legal IP corpus retrieval:
    - Normalizes Devanagari numerals to ASCII digits.
    - Maps multilingual domain terms (Hindi/Marathi/Indic) to English statutory terms.
    - Preserves statutory section references like '3(p)'.
    - Strips conversational boilerplate.
    """
    from retriever import DEV_DIGIT_MAP, MULTILINGUAL_LEGAL_MAP

    norm_query = query.translate(DEV_DIGIT_MAP)
    words = re.findall(r"[a-zA-Z0-9]+(?:\([a-zA-Z0-9]+\))?|[^\W\d_]+|\b\d+\b", norm_query, re.UNICODE)

    expanded_terms: list[str] = []
    # Conversational stopwords to drop
    stopwords = {
        "what", "is", "the", "can", "could", "would", "please", "tell", "me", "about",
        "explain", "how", "to", "in", "of", "and", "or", "for", "a", "an", "does",
        "का", "काय", "आहे", "सांगा", "माहिती", "द्या", "करा", "स्पष्ट", "मिळू", "शकते",
        "क्या", "है", "बताएं", "जानकारी", "दीजिए",
    }

    for w in words:
        w_lower = w.lower()
        if w_lower in stopwords:
            continue
        if w in MULTILINGUAL_LEGAL_MAP:
            expanded_terms.extend(MULTILINGUAL_LEGAL_MAP[w].split())
        else:
            expanded_terms.append(w)

    return " ".join(expanded_terms) if expanded_terms else query


def _expand_query_for_retrieval(llm: LLMProvider, question: str, language: Language) -> str:
    """
    Controlled query expansion / translation for legal RAG retrieval.
    Tries LLM-guided legal term extraction if configured; falls back to rule-based expansion.
    """
    if llm and llm.is_configured:
        try:
            prompt = (
                "You are an expert Indian Ayurveda & Intellectual Property search assistant.\n"
                "The user asked a legal question. Extract or formulate 3 to 6 essential English search keywords, "
                "statutory section references (e.g. Section 3(p), Patents Act 1970, Biological Diversity Act 2002), "
                "and core legal concepts needed to retrieve relevant legal passages from the knowledge base.\n"
                "Return ONLY the concise space-separated keywords without punctuation or preamble.\n\n"
                f"Question ({language.value}): {question}"
            )
            raw = llm.generate(prompt, temperature=0.0)
            clean = raw.replace("```json", "").replace("```", "").strip(' \t\n\r"')
            if clean and len(clean) >= 3:
                return clean
        except Exception as exc:
            logger.warning("LLM query expansion failed: %s; using rule-based expansion", exc)

    return _rule_based_query_expansion(question)


def _evaluate_evidence_sufficiency(passages: list[dict], query: str) -> tuple[bool, str]:
    """
    Evaluate whether retrieved passages provide sufficient initial evidence.
    Returns (is_sufficient, reason).

    NOTE: Retrieval scores are heuristic ordinal ranking metrics in [0.0, 1.0],
    NOT calibrated posterior probabilities of relevance or correctness.
    """
    if not passages:
        return False, "No passages retrieved"

    qualifying = [p for p in passages if p.get("score", 0.0) >= MIN_EVIDENCE_SCORE]
    if not qualifying:
        return False, f"All {len(passages)} passages scored below relevance threshold ({MIN_EVIDENCE_SCORE})"

    top_score = max((p.get("score", 0.0) for p in qualifying), default=0.0)
    if top_score < 0.50 and len(qualifying) < 2:
        return False, f"Marginal relevance: top score {top_score:.2f} with {len(qualifying)} qualifying passages"

    return True, "Sufficient candidate passages found"


def _translate_query_to_english(llm: LLMProvider, question: str) -> str | None:
    """
    Use the LLM to translate/expand a non-English query to English.
    Preserves exact statutory numbers, section references (e.g. 3(p)), and act names.
    Returns None if LLM is unavailable or translation fails.
    """
    try:
        if not llm.is_configured:
            return None

        prompt = (
            "Translate the following question to English. "
            "Preserve all statutory numbers, section references (e.g. 3(p)), act names, "
            "and legal terminology accurately. Return ONLY the English translation without preamble.\n\n"
            f"Question: {question}"
        )
        translated = llm.generate(prompt, temperature=0.0)
        # Strip potential markdown fences or quotes
        clean_translation = translated.replace("```json", "").replace("```", "").strip(' \t\n\r"')
        logger.info("Translated query: %s -> %s", question[:50], clean_translation[:100])
        return clean_translation
    except Exception as exc:
        logger.warning("Query translation failed: %s", exc)
        return None


def _merge_results_rrf(
    primary: list[dict],
    secondary: list[dict],
    k: int = RRF_K,
) -> list[dict]:
    """
    Merge and deduplicate two ranked lists using Reciprocal Rank Fusion.
    """
    scores: dict[str, float] = {}
    chunks: dict[str, dict] = {}

    for rank, hit in enumerate(primary):
        cid = hit["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.2 / (k + rank + 1)
        chunks[cid] = hit

    for rank, hit in enumerate(secondary):
        cid = hit["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
        if cid not in chunks or hit["score"] > chunks[cid]["score"]:
            chunks[cid] = hit

    sorted_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)
    return [chunks[cid] for cid in sorted_ids]


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _build_system_prompt(
    jurisdiction: Jurisdiction,
    language: Language,
) -> str:
    """Build the system-level instructions for the LLM."""

    jurisdiction_instruction = ""
    if jurisdiction == Jurisdiction.india:
        jurisdiction_instruction = (
            "The user is asking about INDIAN law and regulations. "
            "Focus strictly on Indian statutes (Patents Act 1970, Biological Diversity Act 2002, "
            "Drugs & Cosmetics Rules 1945, etc.) and Indian judicial precedents. "
            "Do NOT treat international treaties (PCT, TRIPS, Budapest Treaty, WIPO) or foreign regulations "
            "(US FDA, EU directives) as automatically applicable in India."
        )
    else:
        jurisdiction_instruction = (
            "The user is asking about INTERNATIONAL law and cross-border IP frameworks. "
            "Reference relevant treaties (TRIPS, PCT, Nagoya Protocol, WIPO) and foreign regulatory systems. "
            "Clearly distinguish international standards from domestic Indian law."
        )

    language_instruction = ""
    if language == Language.marathi:
        language_instruction = (
            "\n\nCRITICAL LANGUAGE INSTRUCTION: The user has selected MARATHI / Marathi (मराठी). "
            "You MUST write the entire 'answer' field in natural, grammatically correct Marathi (मराठी) using Devanagari script. "
            "Retain English statutory names and section citations in brackets if helpful (उदा. पेटंट कायदा, १९७० चे कलम ३(p)). "
            "Keep the 'citations', 'evidence_status', and 'confidence' fields in English."
        )
    elif language == Language.hindi:
        language_instruction = (
            "\n\nCRITICAL LANGUAGE INSTRUCTION: The user has selected HINDI / Hindi (हिन्दी). "
            "You MUST write the entire 'answer' field in natural, grammatically correct Hindi (हिन्दी) using Devanagari script. "
            "Keep the 'citations', 'evidence_status', and 'confidence' fields in English."
        )
    elif language == Language.tamil:
        language_instruction = "\n\nCRITICAL LANGUAGE INSTRUCTION: Write the entire answer in natural, grammatically correct Tamil (தமிழ்). Keep legal names and citations accurate."
    elif language == Language.telugu:
        language_instruction = "\n\nCRITICAL LANGUAGE INSTRUCTION: Write the entire answer in natural, grammatically correct Telugu (తెలుగు). Keep legal names and citations accurate."
    elif language == Language.bengali:
        language_instruction = "\n\nCRITICAL LANGUAGE INSTRUCTION: Write the entire answer in natural, grammatically correct Bengali (বাংলা). Keep legal names and citations accurate."
    else:
        language_instruction = (
            "\n\nWrite the 'answer' field in clear, professional English."
        )

    return f"""You are IP-SAKTI Sahayak, an authoritative multilingual legal AI assistant for Ayurveda intellectual property rights and regulatory compliance.

{jurisdiction_instruction}

STRICT LEGAL ACCURACY & EVIDENCE RULES:
1. Grounding: Answer ONLY based on the provided evidence passages. Do not assume, extrapolate, or invent facts.
2. Anti-Hallucination: Never invent legal sections, statutory provisions, government filing fees, application forms, deadlines, or document titles.
3. If the user asks about a fictional law, an unmentioned government fee, or an unsupported scenario, you MUST explicitly state that the available legal documents do not establish this, and set evidence_status to "insufficient" and confidence to "low".
4. Distinguish clearly between exact statutory text (e.g. verbatim wording of Section 3(p)), official plain-language summaries, and practical guidance.
5. Avoid overbroad or categorical assertions: do NOT state that all Ayurvedic inventions cannot be patented when the law specifies only inventions that are mere traditional knowledge or mere aggregations under Section 3(p).
6. Citations: Every item in 'citations' MUST come from the supplied evidence passages. The 'source_filename' must match the passage filename exactly.
7. Verified URLs: Only provide a 'source_url' if an official, verified URL appears explicitly in the text of the passage. Never fabricate URLs.
8. Evidence Status & Confidence:
   - "sufficient": The passages provide direct, authoritative legal text answering the question.
   - "partial": The passages answer only one part of the question or provide related background without complete resolution. State what is supported and what remains unsupported.
   - "insufficient": The passages do not support the query or the query involves nonexistent/unsupported regulations.
{language_instruction}

Respond with valid JSON matching this schema:
{{
  "answer": "string",
  "citations": [
    {{
      "source_filename": "string (exact filename from evidence)",
      "page": null or integer,
      "excerpt": "string (verbatim quote of 10-30 words from the passage)",
      "source_url": null or "string"
    }}
  ],
  "evidence_status": "sufficient" | "partial" | "insufficient",
  "confidence": "high" | "medium" | "low"
}}"""


def _build_user_prompt(question: str, passages: list[dict]) -> str:
    """Format the user prompt with question and evidence passages."""
    passage_parts = []
    for i, p in enumerate(passages, 1):
        page_str = f"Page {p['page']}" if p.get("page") else "Unspecified page"
        passage_parts.append(
            f"--- PASSAGE {i} ---\n"
            f"Source File: {p['source_filename']} ({page_str})\n"
            f"Relevance Score: {p['score']:.4f}\n"
            f"Content:\n{p['text']}\n"
        )

    passages_block = "\n".join(passage_parts)
    if not passages:
        passages_block = "(No relevant passages found in the knowledge base.)"

    return f"""QUESTION:
{question}

RETRIEVED LEGAL EVIDENCE PASSAGES:
{passages_block}

Provide a grounded, legally accurate answer adhering to all system rules."""


# ---------------------------------------------------------------------------
# Confidence consistency post-processing
# ---------------------------------------------------------------------------

def _enforce_confidence_consistency(
    evidence_status: EvidenceStatus,
    confidence: str,
    citations: list[Citation],
    passages: list[dict],
) -> str:
    """
    Deterministic consistency rules:
      - insufficient -> confidence MUST be 'low'
      - partial -> confidence CANNOT be 'high' (capped at 'medium')
      - sufficient -> confidence depends on verified citations and retrieval score
    """
    if evidence_status == EvidenceStatus.insufficient:
        return "low"

    if evidence_status == EvidenceStatus.partial:
        if confidence == "high":
            return "medium"
        return confidence if confidence in ("medium", "low") else "medium"

    # For sufficient status:
    if not citations or not passages:
        return "low"

    # Check top passage score
    top_score = max((p.get("score", 0.0) for p in passages), default=0.0)
    if top_score < 0.60:
        return "medium"

    return confidence if confidence in ("high", "medium", "low") else "medium"


def _no_evidence_answer(language: Language) -> str:
    """Return a human-friendly fallback message in the requested language."""
    if language == Language.marathi:
        return (
            "उपलब्ध कायदेशीर कागदपत्रांमध्ये या प्रश्नाचे निश्चित किंवा पुरेसे उत्तर सापडत नाही. "
            "अशा बाबतीत स्वतः कोणताही कायदेशीर निष्कर्ष न काढता, कृपया पात्र बौद्धिक संपदा (IP) वकील "
            "किंवा अधिकृत आयुर्वेद नियामक सल्लागाराचा सल्ला घ्या."
        )
    elif language == Language.hindi:
        return (
            "उपलब्ध कानूनी दस्तावेजों में इस प्रश्न का पर्याप्त या स्पष्ट उत्तर उपलब्ध नहीं है। "
            "कृपया किसी योग्य बौद्धिक संपदा (IP) अधिवक्ता या आयुर्वेद नियामक सलाहकार से परामर्श करें।"
        )
    return (
        "The available legal documents in the knowledge base do not establish an answer to this question. "
        "Please consult a qualified intellectual property attorney or Ayurveda regulatory facilitator for specific guidance."
    )


# ---------------------------------------------------------------------------
# Provenance and JSON Recovery Helpers
# ---------------------------------------------------------------------------

def _recover_json_from_text(text: str) -> tuple[dict | None, bool]:
    """
    Attempt to parse or safely recover JSON from LLM response text.
    Handles code fences, embedded JSON objects, and trailing commas.
    Returns (data, was_recovered).
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = [l for l in cleaned.split("\n") if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    try:
        return json.loads(cleaned), False
    except json.JSONDecodeError:
        pass

    # Recovery attempt: extract outermost {...}
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        candidate = match.group(0)
        try:
            return json.loads(candidate), True
        except json.JSONDecodeError:
            # Try removing trailing commas before closing braces/brackets
            candidate_fixed = re.sub(r",\s*([\]}])", r"\1", candidate)
            try:
                return json.loads(candidate_fixed), True
            except json.JSONDecodeError:
                pass

    return None, False


def _build_provenance_and_explanation(
    evidence_status: EvidenceStatus,
    confidence: str,
    passages: list[dict],
    verified_claims: list[VerifiedClaim],
    citations: list[Citation],
) -> ProvenanceInfo:
    """
    Constructs provenance links from claims to actual retrieved passages
    and produces an honest explanation of evidence sufficiency and uncertainty.
    Never invents source details.
    """
    links: list[ClaimProvenance] = []
    passages_by_file = {p.get("source_filename"): p for p in passages if p.get("source_filename")}

    for vc in verified_claims:
        chunk_id = None
        if vc.source_filename and vc.source_filename in passages_by_file:
            chunk_id = passages_by_file[vc.source_filename].get("chunk_id")
        links.append(
            ClaimProvenance(
                claim_text=vc.claim_text,
                status=vc.status,
                source_filename=vc.source_filename,
                page=vc.page,
                excerpt=vc.excerpt,
                chunk_id=chunk_id,
            )
        )

    # Uncertainty notes and evidence explanation
    uncertainty_notes: list[str] = []
    if evidence_status == EvidenceStatus.insufficient:
        explanation = (
            "The retrieved legal corpus does not contain statutory or regulatory provisions "
            "establishing an answer to this query. Any specific claims remain unestablished."
        )
        uncertainty_notes.append("No authoritative passages met the relevance threshold in the knowledge base.")
    elif evidence_status == EvidenceStatus.partial:
        sup_claims = [c.claim_text for c in verified_claims if c.status == ClaimStatus.supported]
        unsup_claims = [c.claim_text for c in verified_claims if c.status in (ClaimStatus.unsupported, ClaimStatus.unverifiable)]
        explanation = (
            f"Partial evidence available: {len(sup_claims)} claim(s) supported by retrieved statutes, "
            f"while {len(unsup_claims)} claim(s) remain unverified or unsupported by the corpus."
        )
        if unsup_claims:
            uncertainty_notes.append(f"Unverified or unsupported claims: {'; '.join(c[:60] for c in unsup_claims)}")
    else:
        explanation = (
            f"Evidence is sufficient. Answer claims are directly grounded in {len(citations)} "
            f"verified citation(s) from official legal passages."
        )

    return ProvenanceInfo(
        grounded_citations_count=len(citations),
        provenance_links=links,
        evidence_explanation=explanation,
        uncertainty_notes=uncertainty_notes,
    )


def _determine_user_failure(
    evidence_status: EvidenceStatus,
    failures: list[FailureInfo],
    verified_claims: list[VerifiedClaim],
    citations: list[Citation],
    dropped_citations_count: int,
) -> UserFailureNotice | None:
    """
    Determine whether a real failure occurred and produce a simple user-facing notice
    alongside the AI answer.
    Categories:
    - 'Insufficient Evidence'
    - 'Document Search Failed'
    - 'Answer Verification Failed'
    - 'Source Verification Failed'
    - 'AI Service Unavailable'

    Never exposes stack traces, technical diagnostics, or raw internal errors.
    Returns None if no real failure occurred.
    """
    # 1. Document Search Failed: unrecovered retrieval or index errors
    if any(
        f.failure_type in ("retrieval_error", "index_not_built", "retriever_init_error")
        and not f.recovered
        for f in failures
    ):
        return UserFailureNotice(
            failure_type="Document Search Failed",
            reason="The legal document search service encountered an issue accessing the reference corpus.",
            next_action="Please try your search again in a few moments or ensure the document index is available.",
        )

    # 2. AI Service Unavailable: unrecovered LLM config or provider errors
    if any(
        f.failure_type in ("llm_config_error", "llm_provider_error", "provider_error")
        and not f.recovered
        for f in failures
    ):
        return UserFailureNotice(
            failure_type="AI Service Unavailable",
            reason="The AI reasoning service is currently unavailable or encountered a connection error.",
            next_action="Please try your request again in a few moments or verify server configuration.",
        )

    # 3. Answer Verification Failed: claims in the answer are unsupported by retrieved text or verification failed
    has_unsupported_claim = any(c.status == ClaimStatus.unsupported for c in verified_claims)
    has_verification_error = any(
        f.failure_type == "llm_verification_error" and not f.recovered
        for f in failures
    )
    if has_unsupported_claim or has_verification_error:
        return UserFailureNotice(
            failure_type="Answer Verification Failed",
            reason="One or more statements in the generated response could not be verified against the official legal texts.",
            next_action="Review the cited legal texts directly or consult an IP professional before relying on this answer.",
        )

    # 4. Source Verification Failed: citations could not be validated or hallucinated citations left no valid sources
    has_invalid_citations = any(
        f.failure_type == "invalid_citations" and not f.recovered
        for f in failures
    )
    if has_invalid_citations or (dropped_citations_count > 0 and len(citations) == 0):
        return UserFailureNotice(
            failure_type="Source Verification Failed",
            reason="The citations or source references could not be verified against the retrieved knowledge base.",
            next_action="Verify the statutory section numbers and act names directly in the official gazette notifications.",
        )

    # 5. Insufficient Evidence: when evidence status is insufficient or no qualifying passages
    if evidence_status == EvidenceStatus.insufficient:
        return UserFailureNotice(
            failure_type="Insufficient Evidence",
            reason="The curated legal corpus does not contain enough verified passages to answer this question definitively.",
            next_action="Try rephrasing your question with specific Act names, section numbers, or legal terms, or consult an IP attorney.",
        )

    # No real failure! Fully supported or cleanly recovered.
    return None


# ---------------------------------------------------------------------------
# ChatEngine
# ---------------------------------------------------------------------------

class ChatEngine:
    """
    Orchestrates retrieval + multilingual query expansion + LLM generation for grounded Q&A.
    Reuses the shared Retriever instance.
    """

    def __init__(self, retriever: Retriever) -> None:
        self._retriever = retriever
        self._llm = LLMProvider()
        self._claim_verifier = ClaimVerifier(self._llm)

    @property
    def is_configured(self) -> bool:
        return self._llm.is_configured

    def answer(self, request: ChatRequest) -> ChatResponse:
        """
        Execute full grounded QA pipeline with adaptive retrieval, claim verification,
        failure attribution, and explainability provenance.
        """
        failures: list[FailureInfo] = []

        # Step 1: Hybrid retrieval with the original query
        try:
            primary_passages = self._retriever.search(
                request.question, top_k=RETRIEVAL_TOP_K
            )
        except (IndexNotBuiltError, RetrieverInitError):
            raise

        # Step 2: Assess initial evidence sufficiency
        initial_sufficient, reason = _evaluate_evidence_sufficiency(primary_passages, request.question)
        needs_multilingual_expansion = (
            _contains_indic(request.question) or request.language != Language.english
        )

        retry_attempted = False
        retry_recovered = False
        expansion_query: str | None = None
        combined_passages = primary_passages

        # Controlled query expansion/retry when initial retrieval finds insufficient evidence
        # or when multilingual queries need cross-lingual grounding
        if not initial_sufficient or needs_multilingual_expansion:
            expansion_query = _expand_query_for_retrieval(self._llm, request.question, request.language)
            if expansion_query and expansion_query.strip().lower() != request.question.strip().lower():
                retry_attempted = True
                try:
                    retry_passages = self._retriever.search(
                        expansion_query, top_k=RETRIEVAL_TOP_K
                    )
                    # Check if retry recovered relevant evidence
                    retry_qualifying = [p for p in retry_passages if p.get("score", 0.0) >= MIN_EVIDENCE_SCORE]
                    if retry_qualifying:
                        initial_top = max((p.get("score", 0.0) for p in primary_passages), default=0.0)
                        retry_top = retry_qualifying[0].get("score", 0.0)
                        if not primary_passages or retry_top >= initial_top or not initial_sufficient:
                            retry_recovered = True

                    combined_passages = _merge_results_rrf(primary_passages, retry_passages)
                except (IndexNotBuiltError, RetrieverInitError):
                    raise
                except Exception as exc:
                    logger.warning("Retry search failed: %s", exc)

            if not initial_sufficient:
                failures.append(
                    FailureInfo(
                        module="adaptive_retrieval",
                        failure_type="initial_retrieval_insufficient",
                        message=f"Initial retrieval had insufficient evidence ({reason}). Retry executed: {retry_attempted}.",
                        recovery_attempted=retry_attempted,
                        recovered=retry_recovered,
                    )
                )

        # Step 3: Filter by minimum evidence threshold
        strong_passages = [
            p for p in combined_passages if p.get("score", 0.0) >= MIN_EVIDENCE_SCORE
        ][:8]

        # Determine adaptive retrieval module status
        if strong_passages:
            retrieval_status = ModuleStatus.success if (initial_sufficient or retry_recovered) else ModuleStatus.partial
        else:
            retrieval_status = ModuleStatus.insufficient_evidence

        adaptive_info = AdaptiveRetrievalInfo(
            retry_attempted=retry_attempted,
            retry_recovered=retry_recovered,
            initial_evidence_sufficient=initial_sufficient,
            expansion_query=expansion_query,
            passages_retrieved=len(strong_passages),
        )

        # Step 4: If no passages qualify, return graceful insufficient response without calling LLM
        if not strong_passages:
            provenance = _build_provenance_and_explanation(
                evidence_status=EvidenceStatus.insufficient,
                confidence="low",
                passages=[],
                verified_claims=[],
                citations=[],
            )
            diag = ModuleDiagnostics(
                adaptive_retrieval=ModuleStatus.insufficient_evidence,
                claim_verification=ModuleStatus.blocked,  # Blocked because passage inputs are unavailable
                failure_attribution=ModuleStatus.success,  # Attributed the failure honestly
                explainability_provenance=ModuleStatus.insufficient_evidence,
                failures=failures,
                adaptive_retrieval_info=adaptive_info,
                claim_verification_info=ClaimVerificationInfo(),
                provenance_info=provenance,
            )
            return ChatResponse(
                question=request.question,
                jurisdiction=request.jurisdiction.value,
                language=request.language.value,
                answer=_no_evidence_answer(request.language),
                citations=[],
                evidence_status=EvidenceStatus.insufficient,
                confidence="low",
                disclaimer=DISCLAIMER,
                diagnostics=diag,
                claims=[],
                evidence_explanation=provenance.evidence_explanation,
                user_failure=UserFailureNotice(
                    failure_type="Insufficient Evidence",
                    reason="The curated legal corpus does not contain enough verified passages to answer this question definitively.",
                    next_action="Try rephrasing your question with specific Act names, section numbers, or legal terms, or consult an IP attorney.",
                ),
            )

        # Step 5: Build prompt and invoke LLM
        system_prompt = _build_system_prompt(request.jurisdiction, request.language)
        user_prompt = _build_user_prompt(request.question, strong_passages)
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        raw_response = self._llm.generate(full_prompt)

        # Step 6: Parse JSON response with safe recovery
        data, was_recovered = _recover_json_from_text(raw_response)
        if was_recovered:
            failures.append(
                FailureInfo(
                    module="failure_attribution",
                    failure_type="malformed_llm_response",
                    message="Malformed LLM JSON response safely recovered via extractor",
                    recovery_attempted=True,
                    recovered=True,
                )
            )
        elif data is None:
            failures.append(
                FailureInfo(
                    module="failure_attribution",
                    failure_type="malformed_llm_response",
                    message="Malformed LLM response could not be parsed as JSON; fell back to plain text",
                    recovery_attempted=True,
                    recovered=False,
                )
            )

        parsed = _parse_llm_response(raw_response, request, strong_passages)
        raw_citations = data.get("citations", []) if (data and isinstance(data, dict)) else []

        # Step 7: Claim Verification against actual retrieved passage contents
        verified_claims, valid_cites, dropped_cites, verif_failures = self._claim_verifier.verify(
            parsed.answer, strong_passages, raw_citations if raw_citations else parsed.citations
        )

        for vf in verif_failures:
            failures.append(FailureInfo(**vf))

        if dropped_cites:
            failures.append(
                FailureInfo(
                    module="claim_verification",
                    failure_type="invalid_citations",
                    message=f"{len(dropped_cites)} invalid citation(s) filtered: {[d.get('reason') for d in dropped_cites]}",
                    recovery_attempted=True,
                    recovered=(len(valid_cites) > 0),
                )
            )

        # Update citations to only validated citations
        parsed.citations = [Citation(**c) for c in valid_cites]
        parsed.claims = verified_claims

        # Calculate claim support counts
        sup_count = sum(1 for c in verified_claims if c.status == ClaimStatus.supported)
        unsup_count = sum(1 for c in verified_claims if c.status == ClaimStatus.unsupported)
        unverif_count = sum(1 for c in verified_claims if c.status == ClaimStatus.unverifiable)

        # Record unsupported claim failure if detected
        if unsup_count > 0:
            failures.append(
                FailureInfo(
                    module="claim_verification",
                    failure_type="unsupported_claims",
                    message=f"{unsup_count} unsupported claim(s) detected and penalized in evidence status/confidence",
                    recovery_attempted=True,
                    recovered=True,
                )
            )

        # Calibrate evidence_status and confidence based on claim verification
        if unsup_count > 0:
            if sup_count == 0:
                parsed.evidence_status = EvidenceStatus.insufficient
                parsed.confidence = "low"
            else:
                parsed.evidence_status = EvidenceStatus.partial
                if parsed.confidence == "high":
                    parsed.confidence = "medium"
        elif sup_count == 0 and unverif_count > 0:
            parsed.evidence_status = EvidenceStatus.insufficient
            parsed.confidence = "low"
        elif not parsed.citations:
            parsed.evidence_status = EvidenceStatus.insufficient
            parsed.confidence = "low"

        # Determine claim verification status
        if any(f.get("failure_type") == "llm_verification_error" for f in verif_failures):
            claim_verif_status = ModuleStatus.failed
            parsed.confidence = "low"
        elif unsup_count == 0 and unverif_count == 0 and sup_count > 0:
            claim_verif_status = ModuleStatus.success
        elif sup_count > 0:
            claim_verif_status = ModuleStatus.partial
        else:
            claim_verif_status = ModuleStatus.insufficient_evidence

        claim_info = ClaimVerificationInfo(
            verified_claims=verified_claims,
            supported_count=sup_count,
            unsupported_count=unsup_count,
            unverifiable_count=unverif_count,
            dropped_citations_count=len(dropped_cites),
        )

        # Step 8: Construct Explainability and Provenance
        provenance = _build_provenance_and_explanation(
            evidence_status=parsed.evidence_status,
            confidence=parsed.confidence,
            passages=strong_passages,
            verified_claims=verified_claims,
            citations=parsed.citations,
        )
        parsed.evidence_explanation = provenance.evidence_explanation

        if parsed.evidence_status == EvidenceStatus.sufficient and len(parsed.citations) > 0:
            explain_status = ModuleStatus.success
        elif parsed.evidence_status == EvidenceStatus.partial:
            explain_status = ModuleStatus.partial
        else:
            explain_status = ModuleStatus.insufficient_evidence

        parsed.diagnostics = ModuleDiagnostics(
            adaptive_retrieval=retrieval_status,
            claim_verification=claim_verif_status,
            failure_attribution=ModuleStatus.success,  # Honest attribution of execution outcomes
            explainability_provenance=explain_status,
            failures=failures,
            adaptive_retrieval_info=adaptive_info,
            claim_verification_info=claim_info,
            provenance_info=provenance,
        )

        parsed.user_failure = _determine_user_failure(
            evidence_status=parsed.evidence_status,
            failures=failures,
            verified_claims=verified_claims,
            citations=parsed.citations,
            dropped_citations_count=len(dropped_cites),
        )

        return parsed


def _parse_llm_response(
    raw: str,
    request: ChatRequest,
    passages: list[dict],
    claim_verifier: Optional[ClaimVerifier] = None,
    verify_claims: bool = False,
) -> ChatResponse:
    """Parse and validate the structured JSON from the LLM."""
    data, was_recovered = _recover_json_from_text(raw)
    if data is None:
        logger.warning("LLM returned non-JSON text; falling back to clean text response")
        text = raw.strip()
        if text.startswith("```"):
            lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        return ChatResponse(
            question=request.question,
            jurisdiction=request.jurisdiction.value,
            language=request.language.value,
            answer=text,
            citations=[],
            evidence_status=EvidenceStatus.partial,
            confidence="low",
            disclaimer=DISCLAIMER,
            user_failure=UserFailureNotice(
                failure_type="Answer Verification Failed",
                reason="The AI response could not be verified against the structured legal corpus.",
                next_action="Review the official legal texts directly or consult an IP attorney.",
            ),
        )

    text = data.get("answer", raw.strip())

    # Validate citations against actual retrieved passages
    valid_filenames = {p["source_filename"] for p in passages}
    validated_citations: list[Citation] = []

    for cite in data.get("citations", []):
        filename = cite.get("source_filename", "")
        if filename in valid_filenames:
            # Verified citation
            validated_citations.append(
                Citation(
                    source_filename=filename,
                    page=cite.get("page"),
                    excerpt=cite.get("excerpt", "")[:300],
                    source_url=cite.get("source_url") if isinstance(cite.get("source_url"), str) and cite.get("source_url").startswith("http") else None,
                )
            )
        else:
            logger.warning(
                "Filtered hallucinated citation: '%s' is not in retrieved passages",
                filename,
            )

    # Map evidence status
    evidence_raw = data.get("evidence_status", "partial").lower()
    try:
        evidence_status = EvidenceStatus(evidence_raw)
    except ValueError:
        evidence_status = EvidenceStatus.partial

    # Map confidence
    confidence_raw = data.get("confidence", "medium").lower()
    if confidence_raw not in ("high", "medium", "low"):
        confidence_raw = "medium"

    # Enforce deterministic confidence consistency
    final_confidence = _enforce_confidence_consistency(
        evidence_status=evidence_status,
        confidence=confidence_raw,
        citations=validated_citations,
        passages=passages,
    )

    response = ChatResponse(
        question=request.question,
        jurisdiction=request.jurisdiction.value,
        language=request.language.value,
        answer=data.get("answer", text),
        citations=validated_citations,
        evidence_status=evidence_status,
        confidence=final_confidence,
        disclaimer=DISCLAIMER,
    )

    if verify_claims and claim_verifier is not None:
        verified_claims, valid_cites, dropped_cites, failures = claim_verifier.verify(
            response.answer, passages, response.citations
        )
        response.citations = [Citation(**c) for c in valid_cites]
        response.claims = verified_claims
        sup_count = sum(1 for c in verified_claims if c.status == ClaimStatus.supported)
        unsup_count = sum(1 for c in verified_claims if c.status == ClaimStatus.unsupported)
        unverif_count = sum(1 for c in verified_claims if c.status == ClaimStatus.unverifiable)

        if unsup_count > 0:
            if sup_count == 0:
                response.evidence_status = EvidenceStatus.insufficient
                response.confidence = "low"
            else:
                response.evidence_status = EvidenceStatus.partial
                if response.confidence == "high":
                    response.confidence = "medium"
        elif sup_count == 0 and unverif_count > 0:
            response.evidence_status = EvidenceStatus.insufficient
            response.confidence = "low"

        claim_info = ClaimVerificationInfo(
            verified_claims=verified_claims,
            supported_count=sup_count,
            unsupported_count=unsup_count,
            unverifiable_count=unverif_count,
            dropped_citations_count=len(dropped_cites),
        )
        provenance = _build_provenance_and_explanation(
            evidence_status=response.evidence_status,
            confidence=response.confidence,
            passages=passages,
            verified_claims=verified_claims,
            citations=response.citations,
        )
        response.evidence_explanation = provenance.evidence_explanation
        response.diagnostics.claim_verification_info = claim_info
        response.diagnostics.provenance_info = provenance
        response.diagnostics.claim_verification = (
            ModuleStatus.success if (unsup_count == 0 and unverif_count == 0 and sup_count > 0)
            else (ModuleStatus.partial if sup_count > 0 else ModuleStatus.insufficient_evidence)
        )
        response.diagnostics.failure_attribution = ModuleStatus.success
        response.diagnostics.explainability_provenance = (
            ModuleStatus.success if response.evidence_status == EvidenceStatus.sufficient and len(response.citations) > 0
            else (ModuleStatus.partial if response.evidence_status == EvidenceStatus.partial else ModuleStatus.insufficient_evidence)
        )
        response.user_failure = _determine_user_failure(
            evidence_status=response.evidence_status,
            failures=[],
            verified_claims=verified_claims,
            citations=response.citations,
            dropped_citations_count=len(dropped_cites),
        )
    else:
        if response.evidence_status == EvidenceStatus.insufficient:
            response.user_failure = UserFailureNotice(
                failure_type="Insufficient Evidence",
                reason="The curated legal corpus does not contain enough verified passages to answer this question definitively.",
                next_action="Try rephrasing your question with specific Act names, section numbers, or legal terms, or consult an IP attorney.",
            )

    return response
