"""Pipeline orchestrator, truth table, two-level memory, and error routing (Agent 7).

Implements the Livrable 2 design choices:
- Choice 8 (p. 11, 18-19): Two-level memory (durable rules vs temporary case alerts) & lucid stopping criteria.
- Choice 1 & 10 (p. 7, 12, 17): Fast ANTLR4 syntax repair loop with LLM callback.
- Choice 10 & Role Agent 6b (p. 18): Full-model cognitive review (ISO 29148) without truncation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from sysmeasy.contracts.jcs_seal import verify_sealed_input1
from sysmeasy.contracts.llm_provider import LLMProvider
from sysmeasy.generation.llm_repair import make_llm_repair_fn
from sysmeasy.generation.modeling_agent import generate_with_repair
from sysmeasy.orchestrator.audit_logger import AuditLogger
from sysmeasy.review.cognitive_oracle import CognitiveVerdict, evaluate_cognitive_oracle
from sysmeasy.validation.antlr_compiler import check_sysml_syntax
from sysmeasy.verification.formal_oracle import FormalVerdict, evaluate_formal_oracle

FinalPipelineStatus = Literal[
    "CERTIFIED",
    "REJECTED_FORMAL",
    "REJECTED_SEMANTIC",
    "ESCALATED_HUMAN",
    "BLOCKED_ON_HUMAN",
]


@dataclass
class OrchestratorMemory:
    """Two-level memory system as designed in Livrable 2 (Choice 8, p. 11 & p. 19)."""

    durable_rules: list[str] = field(default_factory=lambda: [
        "R-01: Fermer chaque bloc part def et requirement def avec une accolade fermante.",
        "R-02: Les flux doivent relier un port out vers un port in de domaine compatible.",
        "R-03: Chaque exigence de l'INPUT 1 doit être tracée par une relation satisfy formelle.",
    ])
    case_alerts: list[str] = field(default_factory=list)

    def record_case_alert(self, label: str, message: str) -> None:
        """Store a temporary case-specific alert (e.g., [Alerte-Cas-REQ-04])."""
        self.case_alerts.append(f"[{label}] {message}")

    def clear_case_alerts(self) -> None:
        """Clear short-term memory after cycle completion to avoid context bloat."""
        self.case_alerts.clear()


@dataclass(frozen=True)
class PipelineOutcome:
    """Final output of an end-to-end SysmEasy verification run."""

    status: FinalPipelineStatus
    sysml_code: str
    formal: FormalVerdict
    cognitive: CognitiveVerdict
    audit_trace: dict[str, Any]
    memory_trace: dict[str, Any] = field(default_factory=dict)


def resolve_truth_table(
    formal: FormalVerdict,
    cognitive: CognitiveVerdict,
    *,
    human_timed_out: bool = False,
) -> FinalPipelineStatus:
    """Resolve final status giving absolute priority to formal verification."""
    if formal.verdict == "FAIL":
        return "REJECTED_FORMAL"
    if cognitive.verdict == "CONFORME":
        return "CERTIFIED"
    if cognitive.verdict == "NON_CONFORME":
        return "REJECTED_SEMANTIC"
    # AMBIGU (including E-09 coerced outputs)
    return "BLOCKED_ON_HUMAN" if human_timed_out else "ESCALATED_HUMAN"


def run_verification_pipeline(
    sealed_input1: Mapping[str, Any],
    provider: LLMProvider,
    *,
    bus_voltage_v: float = 24.0,
    battery_capacity_ah: float = 28.0,
    dod: float = 0.85,
    max_mass_kg: float = 25.0,
    min_autonomy_min: float = 90.0,
    human_timed_out: bool = False,
    memory: OrchestratorMemory | None = None,
) -> PipelineOutcome:
    """Execute A7 orchestration from sealed INPUT 1 through A3, A4, A6a, A6b, and audit."""
    logger = AuditLogger()
    mem = memory or OrchestratorMemory()

    input1_hash = verify_sealed_input1(sealed_input1)
    contract_id = str(sealed_input1["content"]["contract_id"])
    logger.record("A2_SEAL", f"input1_sha256={input1_hash}")

    # Agent 3 + Agent 4: Model generation with active LLM repair loop (Choice 1 & 10)
    repair_fn = make_llm_repair_fn(provider, rules_memo=mem.durable_rules)
    sysml_code, attempts = generate_with_repair(
        sealed_input1,
        check_sysml_syntax,
        repair_fn=repair_fn,
        max_attempts=3,
    )
    logger.record("A3_A4_MODEL", f"attempts={attempts}, lines={len(sysml_code.splitlines())}")

    # Agent 5 & 6a: Formal oracle
    formal = evaluate_formal_oracle(
        sealed_input1,
        sysml_code,
        bus_voltage_v=bus_voltage_v,
        battery_capacity_ah=battery_capacity_ah,
        dod=dod,
        max_mass_kg=max_mass_kg,
        min_autonomy_min=min_autonomy_min,
    )
    logger.record("A6a_FORMAL", f"verdict={formal.verdict}, matrices={formal.matrix_results}")

    # Agent 6b: Cognitive review on the FULL model (Point 3: never truncated to 300 chars)
    cognitive = evaluate_cognitive_oracle(provider, sealed_input1, sysml_digest=sysml_code)
    logger.record("A6b_COGNITIVE", f"verdict={cognitive.verdict}, err={cognitive.error_code}")

    final_status = resolve_truth_table(formal, cognitive, human_timed_out=human_timed_out)
    logger.record("A7_ORCHESTRATOR", f"final_status={final_status}")

    outcome = PipelineOutcome(
        status=final_status,
        sysml_code=sysml_code,
        formal=formal,
        cognitive=cognitive,
        audit_trace=logger.to_trace(contract_id),
        memory_trace={
            "durable_rules_count": len(mem.durable_rules),
            "case_alerts": list(mem.case_alerts),
        },
    )
    mem.clear_case_alerts()
    return outcome
