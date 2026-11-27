"""Unit tests for sysmeasy.verification.physics_calculator (Module 5)."""

import json
from pathlib import Path

from sysmeasy.verification.physics_calculator import (
    compute_autonomy_minutes,
    evaluate_system_budgets,
)


def _load_rover_components(filename: str) -> list[dict]:
    root = Path(__file__).resolve().parent.parent
    data = json.loads((root / "examples" / filename).read_text(encoding="utf-8"))
    return data["content"]["components"]


def test_rover_v10_20ah_triggers_soft_warning():
    components = _load_rover_components("rover_v1.0.input1.json")
    report = evaluate_system_budgets(
        components,
        bus_voltage_v=24.0,
        battery_capacity_ah=20.0,
        dod=0.85,
        max_mass_kg=25.0,
        min_autonomy_min=90.0,
    )
    assert report.total_power_w == 340.0
    assert report.usable_energy_wh == 408.0
    assert round(report.autonomy_min, 1) == 72.0
    assert report.budget_feasible is False
    assert report.status == "SOFT_WARNING"
    assert len(report.warnings) == 1


def test_rover_v10_28ah_satisfies_all_budgets():
    components = _load_rover_components("rover_v1.0.input1.json")
    report = evaluate_system_budgets(
        components,
        bus_voltage_v=24.0,
        battery_capacity_ah=28.0,
        dod=0.85,
        max_mass_kg=25.0,
        min_autonomy_min=90.0,
    )
    assert report.total_mass_kg == 22.80
    assert report.total_power_w == 340.0
    assert round(report.autonomy_min, 1) == 100.8
    assert report.mass_margin_kg == 2.20
    assert report.budget_feasible is True
    assert report.status == "OK"
    assert report.warnings == ()


def test_rover_v11_28ah_mass_reduction():
    components = _load_rover_components("rover_v1.1.input1.json")
    report = evaluate_system_budgets(
        components,
        bus_voltage_v=24.0,
        battery_capacity_ah=28.0,
        dod=0.85,
        max_mass_kg=22.0,
        min_autonomy_min=90.0,
    )
    assert report.total_mass_kg == 21.20
    assert report.mass_margin_kg == 0.80
    assert report.budget_feasible is True
    assert report.status == "OK"


def test_autonomy_validation_errors():
    import pytest

    with pytest.raises(ValueError):
        compute_autonomy_minutes(0.0, 340.0, 0.85)
    with pytest.raises(ValueError):
        compute_autonomy_minutes(672.0, 0.0, 0.85)
    with pytest.raises(ValueError):
        compute_autonomy_minutes(672.0, 340.0, 1.5)
