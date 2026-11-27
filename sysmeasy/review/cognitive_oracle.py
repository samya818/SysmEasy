"""Isolated cognitive ISO/IEC/IEEE 29148 reviewer (Agent 6b)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Optional

from sysmeasy.contracts.llm_provider import LLMProvider

CognitiveVerdictType = Literal["CONFORME", "NON_CONFORME", "AMBIGU"]
_ALLOWED_VERDICTS = {"CONFORME", "NON_CONFORME", "AMBIGU"}


@dataclass(frozen=True)
class CognitiveVerdict:
    """Structured ISO 29148 semantic assessment from Agent 6b."""

    verdict: CognitiveVerdictType
    rationale: str
    error_code: Optional[str] = None


_SYSTEM_PROMPT = (
    "You are an ISO/IEC/IEEE 29148 requirements reviewer. "
    "Return strictly a JSON object with keys 'verdict' "
    "(one of CONFORME, NON_CONFORME, AMBIGU) and 'rationale'."
)


def evaluate_cognitive_oracle(
    provider: LLMProvider,
    input1_payload: Mapping[str, Any],
    sysml_digest: str,
) -> CognitiveVerdict:
    """Classify semantic ISO 29148 conformance; force AMBIGU on E-09 malformed output."""
    content = input1_payload.get("content", input1_payload)
    reqs = [
        {"id": r["id"], "name": r["name"], "target": r["target"]}
        for r in content.get("requirements", [])
    ]
    user_prompt = json.dumps({"requirements": reqs, "sysml_digest": sysml_digest}, ensure_ascii=False)

    response = provider.complete(_SYSTEM_PROMPT, user_prompt, temperature=0.0)
    try:
        parsed = json.loads(response.content)
        verdict = parsed.get("verdict")
        rationale = str(parsed.get("rationale", "")).strip()
        if verdict not in _ALLOWED_VERDICTS:
            raise ValueError(f"Invalid verdict token: {verdict!r}")
        return CognitiveVerdict(verdict=verdict, rationale=rationale or "No rationale provided")
    except Exception as exc:
        # E-09: malformed LLM output never crashes the pipeline; force AMBIGU for human triage.
        return CognitiveVerdict(
            verdict="AMBIGU",
            rationale=f"Malformed LLM output coerced to AMBIGU ({exc})",
            error_code="E-09",
        )
