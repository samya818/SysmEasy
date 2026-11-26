"""Tests for Agent 1 spatial PDF extraction and NFKC chunking."""

import unicodedata

import pymupdf
import pytest

from sysmeasy.extraction.pdf_extractor import (
    ExtractionError,
    RawSpan,
    extract_pdf_spans,
    normalize_span_text,
)
from sysmeasy.extraction.spatial_chunker import chunk_spans


def _build_pdf_bytes(text: str, *, rotation: int = 0) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 100), text)
    if rotation:
        page.set_rotation(rotation)
    data = doc.tobytes()
    doc.close()
    return data


def test_nfkc_ligatures_and_soft_hyphens():
    raw = "La con\ufb01guration e\ufb00ectue une véri-\nfication sys\u00adtème."
    norm = normalize_span_text(raw)
    assert unicodedata.is_normalized("NFKC", norm)
    assert "\u00ad" not in norm
    assert "configuration" in norm
    assert "effectue" in norm
    assert "vérification" in norm
    assert "système." in norm


def test_pdf_extraction_zero_indexed_page_and_bbox():
    pdf_bytes = _build_pdf_bytes("Autonomie minimale de 90 minutes.")
    spans = extract_pdf_spans(pdf_bytes)
    assert len(spans) == 1
    assert spans[0].page_idx == 0
    x0, y0, x1, y1 = spans[0].bbox
    assert x0 >= 40.0 and x1 > x0 and y1 > y0
    assert "90 minutes" in spans[0].text


def test_rotated_page_raises_e02():
    pdf_bytes = _build_pdf_bytes("Rotated page", rotation=90)
    with pytest.raises(ExtractionError) as exc_info:
        extract_pdf_spans(pdf_bytes)
    assert exc_info.value.code == "E-02"


def test_chunk_spans_respects_200_word_limit():
    sentences = [f"Phrase numéro {i} avec dix mots pour tester le découpage." for i in range(45)]
    long_text = " ".join(sentences)
    span = RawSpan(page_idx=0, bbox=(50.0, 50.0, 500.0, 400.0), text=long_text)
    chunks = chunk_spans([span], max_words=200)
    assert len(chunks) >= 2
    assert all(c.word_count <= 200 for c in chunks)
    assert chunks[0].span_id == "SP-01"
    assert chunks[1].span_id == "SP-02"
