"""
pdf_service.py - Secure PDF document access and answer report generation for IP-SAKTI Sahayak.

Features:
1. Secure access to source documents in data/legal_docs with strict path traversal prevention.
2. Dynamic answer report generation with question, answer, evidence status, citations,
   source filenames, page numbers, and legal disclaimer.
3. Safe availability checks returning user-friendly messages for missing files.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

BASE_DIR = Path(__file__).resolve().parent
LEGAL_DOCS_DIR = BASE_DIR / "data" / "legal_docs"


def get_secure_pdf_path(filename: str) -> Path:
    """
    Validate and return the resolved Path to a requested PDF document.
    Strictly prevents directory traversal and unauthorized path access.
    Raises HTTPException with friendly messages on error.
    """
    if not filename or not isinstance(filename, str):
        raise HTTPException(status_code=400, detail="Document filename is required.")

    # Prevent directory traversal characters and absolute path components
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=400,
            detail="Invalid document filename. Path traversal is not permitted.",
        )

    # Strictly enforce .pdf extension
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF legal documents are accessible.",
        )

    safe_name = Path(filename).name
    if not safe_name or safe_name != filename:
        raise HTTPException(
            status_code=400,
            detail="Invalid document filename format.",
        )

    LEGAL_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    target = (LEGAL_DOCS_DIR / safe_name).resolve()
    base_resolved = LEGAL_DOCS_DIR.resolve()

    try:
        target.relative_to(base_resolved)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail="Access to the requested document path is forbidden.",
        )

    if not target.exists() or not target.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"The requested source document '{filename}' is currently unavailable in the legal repository.",
        )

    return target


def is_pdf_available(filename: str) -> bool:
    """Safely check if a given PDF filename exists in the local repository."""
    try:
        path = get_secure_pdf_path(filename)
        return path.exists() and path.is_file()
    except Exception:
        return False


def generate_answer_report_pdf(
    question: str,
    answer: str,
    evidence_status: str,
    confidence: str,
    citations: list[dict[str, Any]],
    disclaimer: str,
    jurisdiction: str = "India",
    language: str = "English",
) -> bytes:
    """
    Generate a professional, downloadable PDF guidance report containing:
    - User's legal question
    - Grounded AI response
    - Evidence status and confidence level
    - All verified citations with real source filenames and page numbers
    - Legal disclaimer
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()

    # Color palette
    primary_color = colors.HexColor("#1A365D")   # Deep navy
    secondary_color = colors.HexColor("#2B6CB0") # Slate blue
    accent_green = colors.HexColor("#2F855A")    # Forest sage
    text_color = colors.HexColor("#2D3748")      # Dark charcoal
    muted_color = colors.HexColor("#718096")     # Slate grey
    bg_subtle = colors.HexColor("#F7FAFC")       # Off-white

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        textColor=primary_color,
        fontName="Helvetica-Bold",
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=muted_color,
        fontName="Helvetica",
        spaceAfter=12,
    )

    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=12,
        leading=16,
        textColor=secondary_color,
        fontName="Helvetica-Bold",
        spaceBefore=12,
        spaceAfter=6,
    )

    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=15,
        textColor=text_color,
        fontName="Helvetica",
    )

    question_style = ParagraphStyle(
        "QuestionText",
        parent=styles["Normal"],
        fontSize=10,
        leading=15,
        textColor=primary_color,
        fontName="Helvetica-Bold",
    )

    citation_style = ParagraphStyle(
        "CitationItem",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        textColor=text_color,
        fontName="Helvetica",
    )

    disclaimer_style = ParagraphStyle(
        "DisclaimerText",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#4A5568"),
        fontName="Helvetica-Oblique",
    )

    story = []

    # 1. Header Banner
    story.append(Paragraph("IP-SAKTI Sahayak", title_style))
    story.append(
        Paragraph(
            "Ayurveda Intellectual Property & Regulatory Guidance Report",
            subtitle_style,
        )
    )
    story.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceAfter=10))

    # 2. Metadata Table
    meta_data = [
        [
            Paragraph(f"<b>Jurisdiction:</b> {jurisdiction}", body_style),
            Paragraph(f"<b>Language:</b> {language}", body_style),
        ],
        [
            Paragraph(f"<b>Evidence Status:</b> {evidence_status.capitalize()}", body_style),
            Paragraph(f"<b>Confidence:</b> {confidence.capitalize()}", body_style),
        ],
        [
            Paragraph(
                f"<b>Generated:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
                body_style,
            ),
            Paragraph("<b>Verification:</b> Grounded in Curated Corpus", body_style),
        ],
    ]
    meta_table = Table(meta_data, colWidths=[260, 260])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg_subtle),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#EDF2F7")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 12))

    # 3. Question Section
    story.append(Paragraph("Question", section_heading))
    q_escaped = question.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    q_box = Table([[Paragraph(q_escaped, question_style)]], colWidths=[520])
    q_box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EBF8FF")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#BEE3F8")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.append(q_box)
    story.append(Spacer(1, 10))

    # 4. Answer Section
    story.append(Paragraph("AI Guidance Answer", section_heading))
    ans_escaped = (
        answer.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n\n", "<br/><br/>")
        .replace("\n", "<br/>")
    )
    story.append(Paragraph(ans_escaped, body_style))
    story.append(Spacer(1, 14))

    # 5. Citations Section
    if citations:
        story.append(Paragraph(f"Curated Sources & Citations ({len(citations)})", section_heading))
        cite_rows = []
        for i, cite in enumerate(citations, 1):
            source_file = cite.get("source_filename") or "Official Legal Text"
            page_val = cite.get("page")
            page_str = f"Page {page_val}" if page_val is not None else "Page reference not specified"
            excerpt = cite.get("excerpt") or ""

            escaped_file = source_file.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            escaped_excerpt = excerpt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

            cite_content = [
                Paragraph(f"<b>[{i}] {escaped_file}</b> — <i>{page_str}</i>", citation_style),
            ]
            if escaped_excerpt:
                cite_content.append(Spacer(1, 2))
                cite_content.append(
                    Paragraph(f'"{escaped_excerpt}"', citation_style)
                )

            cite_rows.append([cite_content])

        cite_table = Table(cite_rows, colWidths=[520])
        cite_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FAFAFA")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(cite_table)
        story.append(Spacer(1, 14))

    # 6. Legal Disclaimer Box
    story.append(
        KeepTogether(
            [
                HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E0"), spaceAfter=8),
                Paragraph(f"<b>Legal Disclaimer:</b> {disclaimer}", disclaimer_style),
                Spacer(1, 4),
                Paragraph(
                    "This report was automatically synthesized by IP-SAKTI Sahayak based on retrieved legal statutes. "
                    "For binding regulatory submissions or patent prosecution, consult an authorized patent agent or Ayurveda legal counsel.",
                    disclaimer_style,
                ),
            ]
        )
    )

    doc.build(story)
    return buf.getvalue()
