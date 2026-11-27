"""Local deterministic formal oracle (Agent 6a — Matrices M1 to M6).

Runs completely offline with zero LLM or network calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from sysmeasy.verification.physics_calculator import evaluate_system_budgets


@dataclass(frozen=True)
class FormalVerdict:
    """Output of Agent 6a formal verification."""

    passed: bool
    verdict: Literal["PASS", "FAIL"]
    matrix_results: dict[str, bool]
    violations: tuple[str, ...] = field(default_factory=tuple)


_PART_DEF_RE = re.compile(r"part\s+def\s+(\w+)\s*\{(.*?)\}", re.DOTALL)
_REQ_DEF_RE = re.compile(r"requirement\s+def\s+'([^']+)'\s*\{(.*?)\}", re.DOTALL)
_ATTR_REAL_RE = re.compile(r"attribute\s+(\w+)\s*:\s*Real\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*;")
_ATTR_STR_RE = re.compile(r'attribute\s+(\w+)\s*:\s*String\s*=\s*"([^"]*)"\s*;')
_PORT_RE = re.compile(r"(in|out|inout)\s+port\s+(\w+)\s*:\s*(\w+)\s*;")
_PKG_RE = re.compile(r"^\s*package\s+", re.MULTILINE)


def _parse_symbol_table(sysml_source: str) -> tuple[dict[str, dict[str, Any]], set[str]]:
    parts: dict[str, dict[str, Any]] = {}
    seen_names: list[str] = []
    for name, body in _PART_DEF_RE.findall(sysml_source):
        seen_names.append(name)
        attrs_real = {k: float(v) for k, v in _ATTR_REAL_RE.findall(body)}
        attrs_str = {k: v for k, v in _ATTR_STR_RE.findall(body)}
        ports = {(p_dir, p_name, p_dom) for p_dir, p_name, p_dom in _PORT_RE.findall(body)}
        parts[name] = {"attrs": attrs_real, "str_attrs": attrs_str, "ports": ports}

    # Detect duplicated part def names (MUT-11 class)
    duplicates = {n for n in seen_names if seen_names.count(n) > 1}

    req_names: list[str] = [req_id for req_id, _ in _REQ_DEF_RE.findall(sysml_source)]
    reqs = set(req_names)
    duplicate_reqs = {n for n in req_names if req_names.count(n) > 1}
    has_package = bool(_PKG_RE.search(sysml_source))
    return parts, reqs, duplicates | duplicate_reqs, has_package


def evaluate_formal_oracle(
    input1_payload: Mapping[str, Any],
    sysml_source: str,
    *,
    bus_voltage_v: float = 24.0,
    battery_capacity_ah: float = 28.0,
    dod: float = 0.85,
    max_mass_kg: float = 25.0,
    min_autonomy_min: float = 90.0,
) -> FormalVerdict:
    """Execute matrices M1-M6 against INPUT 1 and the generated SysML v2 source."""
    content = input1_payload.get("content", input1_payload)
    parts, reqs, duplicates, has_package = _parse_symbol_table(sysml_source)
    violations: list[str] = []

    # M0: Root package declaration and no duplicate definitions
    m0_ok = True
    if not has_package:
        m0_ok = False
        violations.append("M0: Missing root 'package' declaration")
    if duplicates:
        m0_ok = False
        violations.append(f"M0: Duplicate part def names: {sorted(duplicates)}")

    # M1: Component coverage
    m1_ok = True
    for comp in content.get("components", []):
        if comp["name"] not in parts:
            m1_ok = False
            violations.append(f"M1: Missing part def '{comp['name']}'")

    # M2: Requirement coverage
    m2_ok = True
    for req in content.get("requirements", []):
        if req["id"] not in reqs:
            m2_ok = False
            violations.append(f"M2: Missing requirement def '{req['id']}'")

    # M3: Port & domain consistency
    m3_ok = True
    for comp in content.get("components", []):
        parsed = parts.get(comp["name"])
        if not parsed:
            m3_ok = False
            continue
        expected_ports = {
            (p["direction"], p["name"], p["domain"]) for p in comp.get("ports", [])
        }
        if expected_ports != parsed["ports"]:
            m3_ok = False
            violations.append(f"M3: Port mismatch on '{comp['name']}'")

    # M4: Attribute numerical parity + category non-empty
    m4_ok = True
    for comp in content.get("components", []):
        parsed = parts.get(comp["name"])
        if not parsed:
            m4_ok = False
            continue
        attrs = parsed["attrs"]
        str_attrs = parsed.get("str_attrs", {})
        if abs(attrs.get("mass_kg", -1.0) - float(comp["mass_kg"])) > 1e-4:
            m4_ok = False
            violations.append(f"M4: mass_kg drift on '{comp['name']}'")
        if abs(attrs.get("power_w", -1.0) - float(comp["power_w"])) > 1e-4:
            m4_ok = False
            violations.append(f"M4: power_w drift on '{comp['name']}'")
        if str_attrs.get("category", "MISSING") == "":
            m4_ok = False
            violations.append(f"M4: Empty category string on '{comp['name']}'")
        if str_attrs.get("category", comp["category"]) != comp["category"]:
            m4_ok = False
            violations.append(f"M4: category mismatch on '{comp['name']}'")

    # M5: Causal chain (every non-zero power consumer must carry power_w and feed budget)
    m5_ok = m4_ok
    for comp in content.get("components", []):
        if comp.get("category") in {"actuator", "controller", "sensor"}:
            if float(comp.get("power_w", 0.0)) <= 0.0:
                m5_ok = False
                violations.append(f"M5: Active component '{comp['name']}' reports <= 0 W")

    # M6: Budget satisfiability (mass <= max AND autonomy >= min)
    # Agent 5 est purement consultatif : un échec ici émet un Soft Warning
    # sans bloquer le pipeline (Livrable 2 §6).
    physics = evaluate_system_budgets(
        content.get("components", []),
        bus_voltage_v=bus_voltage_v,
        battery_capacity_ah=battery_capacity_ah,
        dod=dod,
        max_mass_kg=max_mass_kg,
        min_autonomy_min=min_autonomy_min,
    )
    m6_ok = physics.budget_feasible
    if not m6_ok:
        violations.extend(f"M6: {w}" for w in physics.warnings)

    matrix_results = {
        "M0": m0_ok,
        "M1": m1_ok,
        "M2": m2_ok,
        "M3": m3_ok,
        "M4": m4_ok,
        "M5": m5_ok,
        "M6": m6_ok,
    }
    passed = all(matrix_results.values())
    return FormalVerdict(
        passed=passed,
        verdict="PASS" if passed else "FAIL",
        matrix_results=matrix_results,
        violations=tuple(violations),
    )
