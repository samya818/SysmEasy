"""Deterministic physics and budget calculator (Module 5).

Computes total mass, power consumption, and continuous autonomy from
an INPUT 1 component list, and checks constraint satisfiability with Z3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import z3


@dataclass(frozen=True)
class PhysicsReport:
    """Result of deterministic physics and Z3 constraint evaluation."""

    total_mass_kg: float
    total_power_w: float
    usable_energy_wh: float
    autonomy_min: float
    mass_margin_kg: float
    autonomy_margin_min: float
    z3_satisfiable: bool
    status: str
    warnings: tuple[str, ...] = field(default_factory=tuple)


def compute_total_mass(components: Sequence[Mapping[str, Any]]) -> float:
    """Return the sum of component masses in kilograms."""
    return round(sum(float(c.get("mass_kg", 0.0)) for c in components), 4)


def compute_total_power(components: Sequence[Mapping[str, Any]]) -> float:
    """Return the sum of nominal component power draws in watts."""
    return round(sum(float(c.get("power_w", 0.0)) for c in components), 4)


def compute_autonomy_minutes(
    capacity_nominal_wh: float,
    power_load_w: float,
    dod: float = 0.85,
) -> float:
    """Compute continuous autonomy in minutes given nominal capacity, load, and DoD."""
    if capacity_nominal_wh <= 0.0:
        raise ValueError("capacity_nominal_wh must be positive")
    if power_load_w <= 0.0:
        raise ValueError("power_load_w must be positive")
    if not 0.0 < dod <= 1.0:
        raise ValueError("dod must be in (0, 1]")
    usable_wh = capacity_nominal_wh * dod
    return (usable_wh / power_load_w) * 60.0


def check_z3_feasibility(
    total_mass_kg: float,
    max_mass_kg: float,
    autonomy_min: float,
    min_autonomy_min: float,
) -> bool:
    """Verify mass and autonomy inequalities using Z3 real arithmetic."""
    solver = z3.Solver()
    mass = z3.Real("total_mass_kg")
    autonomy = z3.Real("autonomy_min")

    solver.add(mass == z3.RealVal(str(round(total_mass_kg, 6))))
    solver.add(autonomy == z3.RealVal(str(round(autonomy_min, 6))))
    solver.add(mass <= z3.RealVal(str(max_mass_kg)))
    solver.add(autonomy >= z3.RealVal(str(min_autonomy_min)))

    return solver.check() == z3.sat


def evaluate_system_budgets(
    components: Sequence[Mapping[str, Any]],
    *,
    bus_voltage_v: float,
    battery_capacity_ah: float,
    dod: float = 0.85,
    max_mass_kg: float = 25.0,
    min_autonomy_min: float = 90.0,
) -> PhysicsReport:
    """Evaluate mass, power, autonomy budgets and emit SOFT_WARNING on violations."""
    total_mass = compute_total_mass(components)
    total_power = compute_total_power(components)
    nominal_wh = bus_voltage_v * battery_capacity_ah
    usable_wh = nominal_wh * dod
    autonomy = compute_autonomy_minutes(nominal_wh, total_power, dod)

    mass_margin = round(max_mass_kg - total_mass, 4)
    autonomy_margin = round(autonomy - min_autonomy_min, 4)

    warnings: list[str] = []
    if mass_margin < 0.0:
        warnings.append(
            f"Mass budget exceeded: {total_mass:.2f} kg > {max_mass_kg:.2f} kg"
        )
    if autonomy_margin < 0.0:
        warnings.append(
            f"Autonomy below target: {autonomy:.1f} min < {min_autonomy_min:.1f} min"
        )

    sat = check_z3_feasibility(total_mass, max_mass_kg, autonomy, min_autonomy_min)
    status = "OK" if (sat and not warnings) else "SOFT_WARNING"

    return PhysicsReport(
        total_mass_kg=total_mass,
        total_power_w=total_power,
        usable_energy_wh=round(usable_wh, 4),
        autonomy_min=round(autonomy, 4),
        mass_margin_kg=mass_margin,
        autonomy_margin_min=autonomy_margin,
        z3_satisfiable=sat,
        status=status,
        warnings=tuple(warnings),
    )
