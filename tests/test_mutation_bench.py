"""Tests for the mutation engine: calibration MS=100% and HO MS>=75%."""

import json
from pathlib import Path

from sysmeasy.generation.modeling_agent import render_sysml_from_input1
from sysmeasy.verification.formal_oracle import evaluate_formal_oracle
from sysmeasy.verification.mutation_engine import ALL_MUTANTS, CALIBRATION_MUTANTS, HOLD_OUT_MUTANTS


def _load_rover_v10() -> dict:
    root = Path(__file__).resolve().parent.parent
    return json.loads((root / "examples" / "rover_v1.0.input1.json").read_text(encoding="utf-8"))


def _is_killed(payload: dict, sysml_mutant: str) -> bool:
    """A mutant is killed if the formal oracle issues a FAIL on the mutated code."""
    result = evaluate_formal_oracle(payload, sysml_mutant, battery_capacity_ah=28.0)
    return result.verdict == "FAIL"


def test_calibration_ms100():
    """All 15 calibration mutants must be killed (MS_15 = 100%)."""
    payload = _load_rover_v10()
    baseline = render_sysml_from_input1(payload)

    killed = []
    survived = []
    for mutant in CALIBRATION_MUTANTS:
        mutated = mutant.apply(baseline)
        if _is_killed(payload, mutated):
            killed.append(mutant.mutant_id)
        else:
            survived.append(mutant.mutant_id)

    ms = len(killed) / len(CALIBRATION_MUTANTS) * 100
    print(f"Calibration MS: {ms:.1f}%  killed={killed}  survived={survived}")
    assert survived == [], f"Survived calibration mutants: {survived}"
    assert ms == 100.0


def test_hold_out_ms_above_75():
    """At least 75% of hold-out mutants must be killed (MS_HO15 >= 75%)."""
    payload = _load_rover_v10()
    baseline = render_sysml_from_input1(payload)

    killed = []
    survived = []
    for mutant in HOLD_OUT_MUTANTS:
        mutated = mutant.apply(baseline)
        if _is_killed(payload, mutated):
            killed.append(mutant.mutant_id)
        else:
            survived.append(mutant.mutant_id)

    ms = len(killed) / len(HOLD_OUT_MUTANTS) * 100
    print(f"Hold-out MS: {ms:.1f}%  killed={killed}  survived={survived}")
    assert ms >= 75.0, f"Hold-out MS too low: {ms:.1f}% — survived: {survived}"


def test_healthy_model_not_flagged():
    """A syntactically and semantically valid model must not be killed (zero false positives)."""
    payload = _load_rover_v10()
    baseline = render_sysml_from_input1(payload)
    result = evaluate_formal_oracle(payload, baseline, battery_capacity_ah=28.0)
    assert result.verdict == "PASS", f"False positive on healthy model: {result.violations}"
