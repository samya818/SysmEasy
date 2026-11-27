"""End-to-end tests for Agent 7 orchestrator, JCS sealing, and audit chain."""

import copy
import json
from pathlib import Path

import pytest

from sysmeasy.contracts.jcs_seal import ContractSealError, verify_sealed_input1
from sysmeasy.contracts.llm_provider import LLMResponse
from sysmeasy.orchestrator.audit_logger import AuditChainError, AuditLogger
from sysmeasy.orchestrator.orchestrator import run_verification_pipeline


class _StubProvider:
    def __init__(self, raw_output: str) -> None:
        self._raw = raw_output

    def complete(self, system_prompt: str, user_prompt: str, *, temperature: float = 0.0) -> LLMResponse:
        return LLMResponse(content=self._raw, model="stub-model")


def _load_rover_v10() -> dict:
    root = Path(__file__).resolve().parent.parent
    return json.loads((root / "examples" / "rover_v1.0.input1.json").read_text(encoding="utf-8"))


def test_end_to_end_pipeline_certifies_rover_v10():
    payload = _load_rover_v10()
    provider = _StubProvider('{"verdict": "CONFORME", "rationale": "Clear and testable."}')
    outcome = run_verification_pipeline(payload, provider, battery_capacity_ah=28.0)

    assert outcome.status == "CERTIFIED"
    assert outcome.formal.verdict == "PASS"
    assert AuditLogger.verify_trace(outcome.audit_trace) == outcome.audit_trace["trace_sha256"]


def test_formal_fail_overrides_cognitive_conforme():
    payload = _load_rover_v10()
    provider = _StubProvider('{"verdict": "CONFORME", "rationale": "Looks good."}')
    # 20 Ah pack fails M6 (72.0 min < 90 min) even though LLM says CONFORME.
    outcome = run_verification_pipeline(payload, provider, battery_capacity_ah=20.0)
    assert outcome.status == "REJECTED_FORMAL"


def test_e09_and_human_timeout_yield_blocked_on_human():
    payload = _load_rover_v10()
    bad_provider = _StubProvider("INVALID_JSON")
    outcome = run_verification_pipeline(
        payload, bad_provider, battery_capacity_ah=28.0, human_timed_out=True
    )
    assert outcome.cognitive.error_code == "E-09"
    assert outcome.status == "BLOCKED_ON_HUMAN"


def test_tampered_input1_raises_e07():
    payload = copy.deepcopy(_load_rover_v10())
    payload["content"]["components"][0]["mass_kg"] = 999.0
    with pytest.raises(ContractSealError) as exc_info:
        verify_sealed_input1(payload)
    assert exc_info.value.code == "E-07"


def test_tampered_audit_trace_raises_e12():
    payload = _load_rover_v10()
    provider = _StubProvider('{"verdict": "CONFORME", "rationale": "OK"}')
    outcome = run_verification_pipeline(payload, provider)
    trace = copy.deepcopy(outcome.audit_trace)
    trace["steps"][1]["payload_summary"] = "tampered"
    with pytest.raises(AuditChainError) as exc_info:
        AuditLogger.verify_trace(trace)
    assert exc_info.value.code == "E-12"
