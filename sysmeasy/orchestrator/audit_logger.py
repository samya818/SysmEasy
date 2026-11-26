"""Linear hash-chain audit logger and verifier (Agent 7)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping


class AuditChainError(RuntimeError):
    """Raised when the linear audit hash chain is broken (E-12)."""

    def __init__(self, message: str) -> None:
        self.code = "E-12"
        super().__init__(f"[E-12] {message}")


@dataclass
class AuditLogger:
    """Builds and verifies a linear SHA-256 chain over pipeline steps."""

    steps: list[dict[str, Any]] = field(default_factory=list)
    _prev_hash: str = "0" * 64

    def record(self, agent: str, payload_summary: str) -> dict[str, Any]:
        """Append a sealed audit step and return the step record."""
        step_order = len(self.steps) + 1
        raw = f"{self._prev_hash}||{step_order}||{agent}||{payload_summary}"
        entry_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        entry = {
            "step_order": step_order,
            "agent": agent,
            "payload_summary": payload_summary,
            "prev_hash": self._prev_hash,
            "entry_hash": entry_hash,
        }
        self.steps.append(entry)
        self._prev_hash = entry_hash
        return entry

    def to_trace(self, contract_id: str) -> dict[str, Any]:
        """Export the complete trace dictionary."""
        return {
            "contract_id": contract_id,
            "steps": list(self.steps),
            "trace_sha256": self._prev_hash,
        }

    @staticmethod
    def verify_trace(trace: Mapping[str, Any]) -> str:
        """Verify every link in a trace dict and return trace_sha256 (raises E-12)."""
        prev = "0" * 64
        for step in trace.get("steps", []):
            if step.get("prev_hash") != prev:
                raise AuditChainError(f"Chain break at step {step.get('step_order')}")
            raw = f"{prev}||{step['step_order']}||{step['agent']}||{step['payload_summary']}"
            expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            if step.get("entry_hash") != expected:
                raise AuditChainError(f"Altered hash at step {step.get('step_order')}")
            prev = expected

        if trace.get("trace_sha256") != prev:
            raise AuditChainError("Final trace_sha256 does not match last entry_hash")
        return prev
