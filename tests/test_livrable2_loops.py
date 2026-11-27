"""Tests for Livrable 2 core loops: syntax repair, semantic completion, and orchestrator memory."""

import pytest
from sysmeasy.contracts.llm_provider import LLMResponse
from sysmeasy.generation.llm_repair import (
    clean_sysml_fences,
    complete_sysml_satisfaction,
    make_llm_repair_fn,
    repair_sysml_syntax,
)
from sysmeasy.orchestrator.orchestrator import OrchestratorMemory, run_verification_pipeline
from sysmeasy.validation.antlr_compiler import check_sysml_syntax
from sysmeasy.livrable2_pipeline import run_livrable2_pipeline, _compute_satisfy_recall


class MockLLMProvider:
    """Mock provider simulating LLM responses for test deterministic runs."""

    def __init__(self, reply: str = ""):
        self.reply = reply
        self.call_history: list[dict[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str, *, temperature: float = 0.0) -> LLMResponse:
        self.call_history.append({"system": system_prompt, "user": user_prompt})
        return LLMResponse(content=self.reply, model="mock-model")


def test_clean_sysml_fences():
    fenced = "```sysml\npackage Test {}\n```"
    assert clean_sysml_fences(fenced) == "package Test {}"


def test_complete_sysml_satisfaction_loop():
    """Verify Agent 6 -> Agent 3 semantic loop (Livrable 2 Choice 10, p. 12)."""
    initial_sysml = """package 'DroneSystem' {
    part def DroneAssembly {
        part camera : Camera;
        satisfy 'REQ-01' by DroneAssembly;
    }
}
"""
    missing_reqs = ["REQ-02", "REQ-03"]
    completed = complete_sysml_satisfaction(initial_sysml, missing_reqs, "DroneAssembly")

    assert "satisfy 'REQ-02' by DroneAssembly;" in completed
    assert "satisfy 'REQ-03' by DroneAssembly;" in completed
    # Verify ANTLR syntax still passes on the completed model
    ok, errors = check_sysml_syntax(completed)
    assert ok, f"Syntax error after satisfaction completion: {errors}"


def test_repair_sysml_syntax_loop():
    """Verify Agent 4 -> Agent 3 syntax repair loop (Livrable 2 Choice 1, p. 7)."""
    broken_code = """package 'Rover' {
    part def Chassis {
        attribute mass_kg : Real = 5.0
    }
"""  # Missing closing brace and semicolon
    ok, diagnostics = check_sysml_syntax(broken_code)
    assert not ok
    assert len(diagnostics) > 0

    fixed_code = """package 'Rover' {
    part def Chassis {
        attribute mass_kg : Real = 5.0;
    }
}
"""
    mock_provider = MockLLMProvider(reply=f"```sysml\n{fixed_code}\n```")
    repaired = repair_sysml_syntax(
        broken_code,
        diagnostics,
        mock_provider,
        rules_memo=["R-01: Fermer les accolades."],
    )

    ok_rep, errors_rep = check_sysml_syntax(repaired)
    assert ok_rep
    assert len(errors_rep) == 0
    assert "Fermer les accolades" in mock_provider.call_history[0]["system"]


def test_orchestrator_two_level_memory():
    """Verify Orchestrator two-level memory (Livrable 2 Choice 8, p. 11 & p. 19)."""
    mem = OrchestratorMemory()
    assert len(mem.durable_rules) >= 3
    mem.record_case_alert("Alerte-Cas-Masse", "Masse 26kg > limite 25kg")
    assert len(mem.case_alerts) == 1
    assert "[Alerte-Cas-Masse]" in mem.case_alerts[0]
    mem.clear_case_alerts()
    assert len(mem.case_alerts) == 0
    assert len(mem.durable_rules) >= 3  # Durable rules stay intact


def test_livrable2_pipeline_auto_satisfaction():
    """Verify that livrable2_pipeline achieves satisfy recall on raw prompt."""
    prompt = (
        'Système de Robot "AgriBot".\n'
        "- REQ-01 : Masse maximale <= 15 kg.\n"
        "- REQ-02 : Consommation <= 200 W.\n"
        "- Capteur LIDAR : masse 1.2 kg, puissance 20 W.\n"
    )
    res = run_livrable2_pipeline(prompt)
    assert res.syntax_ok is True
    assert res.satisfy_recall_pct >= 95.0
    assert res.passed is True
    assert len(res.ebom) >= 1
