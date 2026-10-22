"""
test_pdf_service.py - Tests for secure PDF document access and dynamic report generation:
1. View PDF and Download PDF for real, accessible source documents.
2. Download Answer as PDF generates report with question, answer, evidence status,
   citations (source filenames, page numbers), and disclaimer.
3. Directory traversal and unauthorized access protection.
4. Friendly message when a PDF is unavailable.
"""

from __future__ import annotations

import io
from pathlib import Path
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from pypdf import PdfReader
from main import app
from pdf_service import (
    LEGAL_DOCS_DIR,
    get_secure_pdf_path,
    is_pdf_available,
    generate_answer_report_pdf,
)

client = TestClient(app)

SAMPLE_DOC = "Drugs_And_Cosmetics_Rules_1945_Rule_158B.pdf"


def test_secure_pdf_path_valid_document():
    """Verify that an existing legal source document is securely resolved."""
    # Ensure sample document exists
    path = get_secure_pdf_path(SAMPLE_DOC)
    assert path.exists()
    assert path.is_file()
    assert path.name == SAMPLE_DOC
    assert is_pdf_available(SAMPLE_DOC) is True


def test_secure_pdf_path_directory_traversal_prevention():
    """Verify that path traversal attempts are rejected with HTTP 400."""
    traversal_attacks = [
        "../secrets.env",
        "../../etc/passwd",
        "..\\..\\Windows\\System32\\calc.exe",
        "sub/../../Patent_Act_1970.pdf",
        "/absolute/path/doc.pdf",
        "C:\\Windows\\win.ini",
    ]
    for attack in traversal_attacks:
        with pytest.raises(HTTPException) as exc_info:
            get_secure_pdf_path(attack)
        assert exc_info.value.status_code == 400
        assert "not permitted" in exc_info.value.detail or "Only PDF" in exc_info.value.detail or "Invalid" in exc_info.value.detail


def test_secure_pdf_path_non_pdf_rejection():
    """Verify that non-PDF files cannot be retrieved via document endpoints."""
    with pytest.raises(HTTPException) as exc_info:
        get_secure_pdf_path("users.sqlite3")
    assert exc_info.value.status_code == 400
    assert "Only PDF" in exc_info.value.detail


def test_secure_pdf_path_unavailable_document_friendly_message():
    """Verify that requesting a missing PDF returns HTTP 404 with a helpful, friendly message."""
    with pytest.raises(HTTPException) as exc_info:
        get_secure_pdf_path("Unpublished_Notification_2099.pdf")
    assert exc_info.value.status_code == 404
    assert "currently unavailable in the legal repository" in exc_info.value.detail
    assert is_pdf_available("Unpublished_Notification_2099.pdf") is False


def test_generate_answer_report_pdf():
    """Verify dynamic answer report generation produces a valid, readable PDF with all required sections."""
    question = "Can traditional Ayurvedic formulations be patented under Indian Law?"
    answer = "Under Section 3(p) of the Patents Act 1970, an invention which in effect is traditional knowledge cannot be patented."
    evidence_status = "sufficient"
    confidence = "high"
    citations = [
        {
            "source_filename": "Patent_Act_1970.pdf",
            "page": 1,
            "excerpt": "Section 3(p) excludes traditional knowledge from patentability.",
        }
    ]
    disclaimer = "This information is for general guidance only and is not legal advice."

    pdf_bytes = generate_answer_report_pdf(
        question=question,
        answer=answer,
        evidence_status=evidence_status,
        confidence=confidence,
        citations=citations,
        disclaimer=disclaimer,
        jurisdiction="India",
        language="English",
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 500
    assert pdf_bytes.startswith(b"%PDF")

    # Read generated PDF with pypdf to verify text content
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1
    full_text = " ".join(p.extract_text() or "" for p in reader.pages)
    assert "IP-SAKTI Sahayak" in full_text
    assert "Section 3(p)" in full_text
    assert "Patent_Act_1970.pdf" in full_text
    assert "Page 1" in full_text
    assert "legal advice" in full_text.lower()


def test_api_view_document_pdf():
    """Test GET /documents/{filename}/view serves the PDF inline."""
    response = client.get(f"/documents/{SAMPLE_DOC}/view")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "inline" in response.headers["content-disposition"]
    assert SAMPLE_DOC in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")


def test_api_download_document_pdf():
    """Test GET /documents/{filename}/download serves the PDF as an attachment."""
    response = client.get(f"/documents/{SAMPLE_DOC}/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")


def test_api_document_status_available_and_unavailable():
    """Test GET /documents/{filename}/status endpoint."""
    res_avail = client.get(f"/documents/{SAMPLE_DOC}/status")
    assert res_avail.status_code == 200
    data_avail = res_avail.json()
    assert data_avail["available"] is True
    assert "available" in data_avail["message"].lower()

    res_missing = client.get("/documents/Missing_Gazette_Doc.pdf/status")
    assert res_missing.status_code == 200
    data_missing = res_missing.json()
    assert data_missing["available"] is False
    assert "unavailable" in data_missing["message"].lower()


def test_api_download_answer_pdf():
    """Test POST /chat/download-pdf endpoint."""
    payload = {
        "question": "What is Rule 158B?",
        "answer": "Rule 158B of Drugs and Cosmetics Rules defines regulatory requirements for ASU formulations.",
        "evidence_status": "sufficient",
        "confidence": "high",
        "citations": [
            {
                "source_filename": SAMPLE_DOC,
                "page": 1,
                "excerpt": "Rule 158B regulatory requirements",
            }
        ],
        "jurisdiction": "India",
        "language": "English",
        "disclaimer": "Guidance disclaimer text.",
    }
    response = client.post("/chat/download-pdf", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")


def test_api_traversal_attack_blocked_at_endpoint():
    """Test directory traversal attack is blocked on API endpoint with HTTP 400."""
    response = client.get("/documents/%2E%2E%5Csecrets.pdf/view")
    assert response.status_code == 400
    assert "Invalid document filename" in response.json()["detail"]
