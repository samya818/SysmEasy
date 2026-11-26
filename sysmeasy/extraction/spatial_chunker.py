"""Spatial chunker enforcing <= 200-word sentence chunks and NFKC invariants."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Sequence

from sysmeasy.extraction.pdf_extractor import RawSpan


@dataclass(frozen=True)
class SpatialChunk:
    """Traceable text chunk linked to its source page and bounding box."""

    span_id: str
    page_idx: int
    bbox: tuple[float, float, float, float]
    exact_quote: str
    word_count: int


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk_spans(
    spans: Sequence[RawSpan],
    *,
    max_words: int = 200,
) -> list[SpatialChunk]:
    """Group or split raw spans into chunks of at most max_words words."""
    if max_words <= 0:
        raise ValueError("max_words must be positive")

    chunks: list[SpatialChunk] = []
    idx = 1

    for span in spans:
        assert unicodedata.is_normalized("NFKC", span.text), "Span text must be NFKC-normalized"
        words = span.text.split()
        if len(words) <= max_words:
            chunks.append(
                SpatialChunk(
                    span_id=f"SP-{idx:02d}",
                    page_idx=span.page_idx,
                    bbox=span.bbox,
                    exact_quote=span.text,
                    word_count=len(words),
                )
            )
            idx += 1
            continue

        current_sentences: list[str] = []
        current_words = 0

        for sentence in _split_sentences(span.text):
            s_words = sentence.split()
            if len(s_words) > max_words:
                # Hard-wrap an oversized single sentence to respect max_words.
                if current_sentences:
                    quote = " ".join(current_sentences)
                    chunks.append(
                        SpatialChunk(
                            span_id=f"SP-{idx:02d}",
                            page_idx=span.page_idx,
                            bbox=span.bbox,
                            exact_quote=quote,
                            word_count=current_words,
                        )
                    )
                    idx += 1
                    current_sentences = []
                    current_words = 0

                for start in range(0, len(s_words), max_words):
                    part = " ".join(s_words[start : start + max_words])
                    chunks.append(
                        SpatialChunk(
                            span_id=f"SP-{idx:02d}",
                            page_idx=span.page_idx,
                            bbox=span.bbox,
                            exact_quote=part,
                            word_count=len(part.split()),
                        )
                    )
                    idx += 1
                continue

            if current_words + len(s_words) > max_words and current_sentences:
                quote = " ".join(current_sentences)
                chunks.append(
                    SpatialChunk(
                        span_id=f"SP-{idx:02d}",
                        page_idx=span.page_idx,
                        bbox=span.bbox,
                        exact_quote=quote,
                        word_count=current_words,
                    )
                )
                idx += 1
                current_sentences = [sentence]
                current_words = len(s_words)
            else:
                current_sentences.append(sentence)
                current_words += len(s_words)

        if current_sentences:
            quote = " ".join(current_sentences)
            chunks.append(
                SpatialChunk(
                    span_id=f"SP-{idx:02d}",
                    page_idx=span.page_idx,
                    bbox=span.bbox,
                    exact_quote=quote,
                    word_count=current_words,
                )
            )
            idx += 1

    return chunks
