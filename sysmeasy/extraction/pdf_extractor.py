"""Deterministic PDF span extractor using PyMuPDF (Agent 1).

Extracts text spans with 0-indexed page numbers and PostScript 1/72 pt
bounding boxes, enforcing rotation == 0 (E-02) and non-encrypted PDFs (E-10).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Union

import pymupdf


class ExtractionError(RuntimeError):
    """Base error raised during PDF ingestion with an architectural error code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"[{code}] {message}")


@dataclass(frozen=True)
class RawSpan:
    """Single extracted text block with spatial coordinates."""

    page_idx: int
    bbox: tuple[float, float, float, float]
    text: str


def normalize_span_text(text: str) -> str:
    """Apply NFKC normalization, strip soft hyphens, and de-hyphenate line wraps."""
    cleaned = text.replace("\u00ad", "")
    cleaned = unicodedata.normalize("NFKC", cleaned)
    # Join words split across a line break with a trailing hyphen.
    cleaned = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def extract_pdf_spans(pdf_source: Union[str, Path, bytes]) -> list[RawSpan]:
    """Extract normalized text spans from a PDF file path or raw bytes."""
    if isinstance(pdf_source, bytes):
        doc = pymupdf.open(stream=pdf_source, filetype="pdf")
    else:
        path = Path(pdf_source)
        if not path.is_file():
            raise ExtractionError("E-01", f"PDF file not found: {path}")
        doc = pymupdf.open(path)

    try:
        if doc.is_encrypted:
            raise ExtractionError("E-10", "PDF is encrypted or password-protected")

        spans: list[RawSpan] = []
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            if page.rotation != 0:
                raise ExtractionError(
                    "E-02",
                    f"Page {page_idx} has non-zero rotation ({page.rotation} deg)",
                )

            blocks = page.get_text("blocks")
            for block in blocks:
                # block format: (x0, y0, x1, y1, text, block_no, block_type)
                if len(block) < 7 or block[6] != 0:
                    continue
                norm = normalize_span_text(str(block[4]))
                if not norm:
                    continue
                bbox = (
                    round(float(block[0]), 2),
                    round(float(block[1]), 2),
                    round(float(block[2]), 2),
                    round(float(block[3]), 2),
                )
                spans.append(RawSpan(page_idx=page_idx, bbox=bbox, text=norm))

        return spans
    finally:
        doc.close()
