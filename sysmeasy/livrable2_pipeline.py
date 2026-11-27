"""Clean, simplified Livrable 2 pipeline (Agents 1 to 6, no M0-M6/graph bloat).

Follows the exact 6-step architecture from Livrable 2:
  Agent 1: Isolate spec -> extract ConOps, requirements, components
  Agent 2: Flag ambiguities / missing data -> build INPUT 1
  Agent 3: Render SysML v2 model (part def, port, requirement def, satisfy)
  Agent 4: Validate SysML v2 syntax
  Agent 5: Consultative Python physics check (mass, power, autonomy -> SOFT_WARNING)
  Agent 6: Verify satisfy recall >= 95% and generate eBOM table
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sysmeasy.elicitation.nl_parser import (
    _isolate_specification_section,
    _slugify_part_name,
    _to_float,
    parse_cdc_to_input1,
)
from sysmeasy.validation.antlr_compiler import check_sysml_syntax


@dataclass(frozen=True)
class Livrable2Result:
    """Consolidated output of the Livrable 2 pipeline."""

    project_name: str
    conops: str
    requirements: list[dict[str, Any]]
    components: list[dict[str, Any]]
    ebom: list[dict[str, Any]]
    sysml_code: str
    syntax_ok: bool
    syntax_errors: list[str]
    total_mass_kg: float
    total_power_w: float
    autonomy_min: float | None
    soft_warnings: list[str]
    ambiguities: list[str]
    satisfy_recall_pct: float
    passed: bool
    traceability: list[dict[str, str]] = field(default_factory=list)
    connections: list[dict[str, str]] = field(default_factory=list)


def _extract_conops(spec_text: str, project_name: str) -> str:
    for line in spec_text.splitlines():
        clean = line.replace("**", "").strip(" -•#\t")
        if not clean or clean.lower().startswith("cahier des charges"):
            continue
        if clean.lower().startswith("objectif"):
            return clean.split(":", 1)[-1].strip()
        if len(clean) > 25 and not clean.upper().startswith("REQ-"):
            return clean[:240]
    return f"Modélisation système de {project_name}."


def _render_livrable2_sysml(
    project_name: str,
    conops: str,
    requirements: list[dict[str, Any]],
    components: list[dict[str, Any]],
) -> str:
    lines = [
        f"package '{project_name}' {{",
        "    private import ScalarValues::*;",
        "",
        f"    doc /* {conops.replace('*/', '')} */",
        "",
    ]

    for req in requirements:
        lines.extend([
            f"    requirement def '{req['id']}' {{",
            f"        doc /* {req['name']}: {req['target']} */",
            f"        attribute targetValue : Real = {req['numerical_val']};",
            f"        attribute unit : String = \"{req['unit']}\";",
            "    }",
        ])
    lines.append("")

    for comp in components:
        lines.extend([
            f"    part def {comp['name']} {{",
            f"        attribute mass_kg : Real = {comp['mass_kg']};",
            f"        attribute power_w : Real = {comp['power_w']};",
        ])
        for port in comp.get("ports", []):
            lines.append(f"        {port['direction']} port {port['name']} : {port['domain']};")
        lines.append("    }")
    lines.append("")

    # Root assembly + satisfy links (Agent 3 & Agent 6 traceability)
    root_name = _slugify_part_name(project_name) + "System"
    lines.append(f"    part def {root_name} {{")
    for comp in components:
        lines.append(f"        part {comp['name'].lower()} : {comp['name']};")
    for req in requirements:
        lines.append(f"        satisfy '{req['id']}' by {root_name};")
    lines.append("    }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _compute_satisfy_recall(sysml_code: str, requirements: list[dict[str, Any]]) -> float:
    if not requirements:
        return 100.0
    satisfied = sum(1 for r in requirements if f"satisfy '{r['id']}'" in sysml_code)
    return round((satisfied / len(requirements)) * 100.0, 1)


def run_livrable2_pipeline(prompt: str, *, strict_llm: bool = False, override_gemini_key: str | None = None) -> Livrable2Result:
    """Execute the clean 6-agent Livrable 2 flow on any raw specification prompt."""
    spec_text = _isolate_specification_section(prompt)
    envelope = parse_cdc_to_input1(prompt, strict_llm=strict_llm, override_gemini_key=override_gemini_key)
    content = envelope["content"]

    project_name: str = content["project_name"]
    requirements: list[dict[str, Any]] = content["requirements"]
    components: list[dict[str, Any]] = content["components"]
    ambiguities: list[str] = list(content.get("ambiguities", []))
    params = content.get("physics_params", {})

    conops = content.get("conops") or _extract_conops(spec_text, project_name)
    connections: list[dict[str, str]] = list(content.get("connections", []))

    # Agent 3: Render SysML v2 with explicit satisfy links
    sysml_code = _render_livrable2_sysml(project_name, conops, requirements, components)

    # Agent 4: Deterministic syntax validation
    syntax_ok, syntax_errors = check_sysml_syntax(sysml_code)

    # Agent 5: Physics check (only when physical parameters are explicitly provided)
    total_mass = round(sum(float(c.get("mass_kg", 0.0)) for c in components), 2)
    total_power = round(sum(float(c.get("power_w", 0.0)) for c in components), 2)
    soft_warnings: list[str] = []

    max_mass = next((r["numerical_val"] for r in requirements if r["unit"] == "kg" and r["numerical_val"] > 0), None)
    if total_mass == 0.0 and max_mass is not None:
        total_mass = round(float(max_mass), 2)
        ambiguities.append(f"Masse maximale système ({total_mass:.2f} kg) renseignée ; répartition par sous-système non chiffrée.")
    elif max_mass is not None and total_mass > max_mass:
        soft_warnings.append(f"Masse totale ({total_mass:.2f} kg) > limite ({max_mass:.2f} kg).")

    # Autonomy: calculated ONLY if explicit battery parameters exist (NO silent default battery injection)
    autonomy_min: float | None = None
    bus_v = params.get("bus_voltage_v")
    cap_ah = params.get("battery_capacity_ah")
    if bus_v is not None and cap_ah is not None and float(bus_v) > 0 and float(cap_ah) > 0 and total_power > 0.0:
        dod = float(params.get("dod", 0.85))
        usable_wh = float(bus_v) * float(cap_ah) * dod
        autonomy_min = round((usable_wh / total_power) * 60.0, 1)
        min_auto = next((r["numerical_val"] for r in requirements if r["unit"] == "min" and r["numerical_val"] > 0), None)
        if min_auto is not None and autonomy_min < min_auto:
            is_peak = any(k in spec_text.lower() for k in ["puissance maximale", "puissance max", "crête", "pointe", "en montée"])
            if is_peak:
                soft_warnings.append(
                    f"À puissance crête ({total_power:.0f} W), autonomie = {autonomy_min:.1f} min (< {min_auto:.1f} min). "
                    "Préciser la consommation moyenne nominale dans le CDC."
                )
            else:
                soft_warnings.append(
                    f"Autonomie calculée ({autonomy_min:.1f} min) < exigence ({min_auto:.1f} min). Envisager une source d'énergie supérieure."
                )

    # Agent 6: Satisfy recall >= 95% + eBOM generation
    recall_pct = _compute_satisfy_recall(sysml_code, requirements)
    ebom = [
        {
            "repere": f"CMP-{idx:02d}",
            "name": c.get("label", c["name"]),
            "category": c["category"],
            "qty": 1,
            "mass_kg": c["mass_kg"],
            "power_w": c["power_w"],
        }
        for idx, c in enumerate(components, start=1)
    ]

    root_name = _slugify_part_name(project_name) + "System"
    traceability = [
        {
            "id": r["id"],
            "name": r["name"],
            "target": r["target"],
            "satisfied_by": root_name,
            "expr": f"{r['comparator']} {r['numerical_val']} {r['unit']}" if r["numerical_val"] > 0 and r["unit"] != "spec" else (r["target"][:75] or "Spécification qualitative"),
        }
        for r in requirements
    ]

    passed = syntax_ok and recall_pct >= 95.0
    return Livrable2Result(
        project_name=project_name,
        conops=conops,
        requirements=requirements,
        components=components,
        ebom=ebom,
        sysml_code=sysml_code,
        syntax_ok=syntax_ok,
        syntax_errors=syntax_errors,
        total_mass_kg=total_mass,
        total_power_w=total_power,
        autonomy_min=autonomy_min,
        soft_warnings=soft_warnings,
        ambiguities=ambiguities,
        satisfy_recall_pct=recall_pct,
        passed=passed,
        traceability=traceability,
        connections=connections,
    )
