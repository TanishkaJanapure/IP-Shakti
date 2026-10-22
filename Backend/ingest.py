
from pathlib import Path
import json
import csv

from pypdf import PdfReader
from docx import Document

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "data" / "legal_docs"
OUTPUT_DIR = BASE_DIR / "data" / "processed"

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def extract_pdf(path):
    reader = PdfReader(str(path))
    pages = []

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append({
                "page": page_number,
                "text": text.strip()
            })

    return pages


def extract_docx(path):
    doc = Document(str(path))
    paragraphs = [
        p.text.strip()
        for p in doc.paragraphs
        if p.text.strip()
    ]

    # Word paragraphs are extracted, but original page numbers
    # cannot reliably be inferred from a DOCX file.
    text = "\n".join(paragraphs)
    return [{"page": None, "text": text}] if text else []


def extract_txt(path):
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return [{"page": None, "text": text}] if text else []


def extract_document(path):
    extension = path.suffix.lower()

    if extension == ".pdf":
        return extract_pdf(path)
    if extension == ".docx":
        return extract_docx(path)
    if extension == ".txt":
        return extract_txt(path)

    return []


def main():
    if not DOCS_DIR.exists():
        print(f"Document folder not found: {DOCS_DIR}")
        print("Create data/legal_docs and copy your files into it.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    documents = []
    report = []

    files = sorted(
        p for p in DOCS_DIR.rglob("*")
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    print(f"Supported files found: {len(files)}")

    for path in files:
        try:
            pages = extract_document(path)
            full_text = "\n\n".join(
                item["text"] for item in pages
            )

            record = {
                "document_id": path.relative_to(DOCS_DIR).as_posix(),
                "filename": path.name,
                "file_type": path.suffix.lower(),
                "pages": pages,
                "character_count": len(full_text),
                "status": (
                    "extracted" if full_text.strip()
                    else "needs_ocr_or_review"
                ),
            }
            documents.append(record)

            report.append({
                "filename": path.name,
                "file_type": path.suffix.lower(),
                "character_count": len(full_text),
                "status": record["status"],
            })

            print(
                f"[{record['status']}] {path.name}: "
                f"{len(full_text)} characters"
            )

        except Exception as error:
            report.append({
                "filename": path.name,
                "file_type": path.suffix.lower(),
                "character_count": 0,
                "status": f"error: {error}",
            })
            print(f"[ERROR] {path.name}: {error}")

    json_path = OUTPUT_DIR / "documents.json"
    with json_path.open("w", encoding="utf-8") as file:
        json.dump(documents, file, ensure_ascii=False, indent=2)

    csv_path = OUTPUT_DIR / "ingestion_report.csv"
    with csv_path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "filename", "file_type",
                "character_count", "status"
            ],
        )
        writer.writeheader()
        writer.writerows(report)

    print("\nIngestion complete.")
    print(f"Extracted records: {len(documents)}")
    print(f"JSON output: {json_path}")
    print(f"Report: {csv_path}")
    print("Review the report before building the RAG index.")


if __name__ == "__main__":
    main()
