"""RFC 8785 (JCS) canonical sealing and verification for INPUT 1 contracts."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

import jcs


class ContractSealError(RuntimeError):
    """Raised when an INPUT 1 sealed envelope fails integrity verification."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"[{code}] {message}")


def canonical_sha256(content: Mapping[str, Any]) -> str:
    """Compute the RFC 8785 JCS canonical SHA-256 digest of a content dictionary."""
    payload = {k: v for k, v in content.items() if k != "canonical_sha256"}
    return hashlib.sha256(jcs.canonicalize(payload)).hexdigest()


def verify_sealed_input1(envelope: Mapping[str, Any]) -> str:
    """Verify content_only JCS SHA-256 on a sealed INPUT 1 envelope (raises E-07)."""
    if "content" not in envelope or "canonical_sha256" not in envelope:
        raise ContractSealError("E-07", "Missing 'content' or 'canonical_sha256' in INPUT 1")
    expected = canonical_sha256(envelope["content"])
    actual = str(envelope["canonical_sha256"])
    if expected != actual:
        raise ContractSealError(
            "E-07",
            f"INPUT1_HASH_MISMATCH: expected {expected}, got {actual}",
        )
    return actual
