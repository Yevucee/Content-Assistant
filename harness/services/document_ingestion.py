"""Extract plain text from common document types (practical, not exhaustive)."""

from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)


class DocumentExtractError(ValueError):
    pass


def extract_text_from_bytes(filename: str, data: bytes) -> str:
    """
    Best-effort text extraction from filename extension.
    Raises DocumentExtractError if nothing usable is produced.
    """
    name = (filename or "upload").lower()
    if not data:
        raise DocumentExtractError("Empty file.")

    if name.endswith(".txt") or name.endswith(".md") or name.endswith(".markdown"):
        return _decode_utf8(data)

    if name.endswith(".pdf"):
        return _extract_pdf(data)

    if name.endswith(".docx"):
        return _extract_docx(data)

    # Plain try as UTF-8 for unknown types
    try:
        t = _decode_utf8(data)
        if len(t.strip()) > 50:
            return t
    except UnicodeDecodeError:
        pass

    raise DocumentExtractError(
        f"Unsupported or unreadable file type for {filename!r}. "
        "Use .txt, .md, .pdf, or .docx, or paste text instead."
    )


def _decode_utf8(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        from io import BytesIO
    except ImportError as e:  # pragma: no cover
        raise DocumentExtractError("PDF support requires pypdf (install dependencies).") from e

    reader = PdfReader(BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            t = ""
        if t.strip():
            parts.append(t.strip())
    text = "\n\n".join(parts).strip()
    if not text:
        raise DocumentExtractError("No extractable text from PDF (may be scanned). Paste text instead.")
    return text


def _extract_docx(data: bytes) -> str:
    try:
        from docx import Document
        from io import BytesIO
    except ImportError as e:  # pragma: no cover
        raise DocumentExtractError("Word support requires python-docx.") from e

    doc = Document(BytesIO(data))
    paras = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    text = "\n\n".join(paras).strip()
    if not text:
        raise DocumentExtractError("No paragraphs found in .docx.")
    return text


def combine_pasted_and_extracted(pasted: str | None, extracted: str | None) -> str:
    a = (pasted or "").strip()
    b = (extracted or "").strip()
    if a and b:
        return f"{a}\n\n---\n\n{b}" if a != b else a
    return a or b
