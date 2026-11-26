"""Tests for double-oracle independence (Agent 6a formal vs Agent 6b cognitive)."""

import json
from pathlib import Path

from sysmeasy.contracts.llm_provider import LLMResponse
from sysmeasy.generation.modeling_agent import render_sysml_from_input1
from sysmeasy.review.cognitive_oracle import evaluate_cognitive_oracle
from sysmeasy.verification.formal_oracle import evaluate_formal_oracle


class _StubProvider:
    def __init__(self, raw_output: str) -> None:
        self._raw = raw_output

    def complete(self, system_prompt: str, user_prompt: str, *, temperature: float = 0.0) -> LLMResponse:
        return LLMResponse(content=self._raw, model="stub-model")


def _load_rover_v10() -> dict:
    root = Path(__file__).resolve().parent.parent
    return json.loads((root / "examples" / "rover_v1.0.input1.json").read_text(encoding="utf-8"))


def test_formal_oracle_passes_valid_rover_v10():
    payload = _load_rover_v10()
    sysml = render_sysml_from_input1(payload)
    res = evaluate_formal_oracle(payload, sysml, battery_capacity_ah=28.0)
    assert res.passed is True
    assert res.verdict == "PASS"
    assert all(res.matrix_results.values())


def test_formal_oracle_catches_attribute_drift_and_budget_violation():
    payload = _load_rover_v10()
    sysml = render_sysml_from_input1(payload).replace(
        "attribute power_w : Real = 15.0;", "attribute power_w : Real = 0.0;"
    )
    res = evaluate_formal_oracle(payload, sysml, battery_capacity_ah=20.0)
    assert res.passed is False
    assert res.verdict == "FAIL"
    assert res.matrix_results["M4"] is False
    assert res.matrix_results["M6"] is False


def test_cognitive_oracle_handles_valid_and_malformed_e09():
    payload = _load_rover_v10()

    ok_provider = _StubProvider('{"verdict": "CONFORME", "rationale": "All ISO 29148 criteria met."}')
    verdict_ok = evaluate_cognitive_oracle(ok_provider, payload, "digest")
    assert verdict_ok.verdict == "CONFORME"
    assert verdict_ok.error_code is None

    bad_provider = _StubProvider("not valid json at all")
    verdict_bad = evaluate_cognitive_oracle(bad_provider, payload, "digest")
    assert verdict_bad.verdict == "AMBIGU"
    assert verdict_bad.error_code == "E-09"
