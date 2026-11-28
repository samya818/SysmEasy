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

from sysmeasy.contracts.llm_provider import detect_env_llm_provider
from sysmeasy.elicitation.nl_parser import (
    _isolate_specification_section,
    _slugify_part_name,
    _to_float,
    parse_cdc_to_input1,
)
from sysmeasy.generation.llm_repair import complete_sysml_satisfaction, repair_sysml_syntax
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
    repair_attempts: int = 1
    semantic_completed: bool = False


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


def _domain_to_port_def(domain: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9]", "", str(domain or "Signal")).capitalize()
    return f"{clean}Port" if not clean.endswith("Port") else clean


def _extract_states_for_sysml(conops: str, spec_text: str) -> tuple[list[str], list[str]]:
    """Extract operational modes/states and transition guards from spec text when present."""
    text = f"{conops} {spec_text}".lower()
    candidates = [
        ("Veille", ["veille", "arrêt", "arret", "standby", "au sol"]),
        ("PreVol", ["pré-vol", "pre-vol", "initialisation", "démarrage", "demarrage", "boot"]),
        ("EnVol", ["en vol", "croisière", "nominal", "mission", "livraison", "projection", "travail", "marche"]),
        ("Evitement", ["évitement", "evitement", "obstacle", "lidar"]),
        ("RetourBase", ["retour", "base", "rtl"]),
        ("Urgence", ["urgence", "surchauffe", "défaut", "defaut", "perte", "panne"]),
    ]
    states = [name for name, kws in candidates if any(k in text for k in kws)]
    if len(states) < 2:
        return [], []
    guards = ["init_ok", "mission_active", "obstacle_ou_seuil", "retour_ou_fin", "anomalie_critique"]
    return states[:5], guards


def _render_livrable2_sysml(
    project_name: str,
    conops: str,
    requirements: list[dict[str, Any]],
    components: list[dict[str, Any]],
    connections: list[dict[str, str]] | None = None,
    physics_params: dict[str, Any] | None = None,
    spec_text: str = "",
) -> str:
    lines = [
        f"package '{project_name}' {{",
        "    private import ScalarValues::*;",
        "",
        f"    doc /* {conops.replace('*/', '')} */",
        "",
    ]

    # Declare port defs explicitly for every domain used by components
    domains = sorted({
        _domain_to_port_def(p.get("domain", "Signal"))
        for comp in components
        for p in comp.get("ports", [])
    })
    for pdef in domains:
        lines.append(f"    port def {pdef};")
    if domains:
        lines.append("")

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
            pdef = _domain_to_port_def(port.get("domain", "Signal"))
            lines.append(f"        {port['direction']} port {port['name']} : {pdef};")
        lines.append("    }")
    lines.append("")

    # Explicit battery/power parameters in SysML when provided (no hidden magic numbers)
    params = physics_params or {}
    if params.get("bus_voltage_v") and params.get("battery_capacity_ah"):
        lines.extend([
            "    part def PowerBudget {",
            f"        attribute bus_voltage_v : Real = {float(params['bus_voltage_v'])};",
            f"        attribute battery_capacity_ah : Real = {float(params['battery_capacity_ah'])};",
            f"        attribute dod : Real = {float(params.get('dod', 0.85))};",
            "    }",
            "",
        ])

    # State machine in SysML v2 when operational modes are present in the spec
    states, guards = _extract_states_for_sysml(conops, spec_text)
    if states:
        lines.append("    state def OperationalModes {")
        for st in states:
            lines.append(f"        state {st};")
        for i in range(len(states) - 1):
            g = guards[i % len(guards)]
            lines.append(f"        transition {states[i]}_to_{states[i+1]} first {states[i]} accept {g} then {states[i+1]};")
        lines.append("    }")
        lines.append("")

    # Root assembly with explicit `connect` links between matching out -> in ports
    root_name = _slugify_part_name(project_name) + "System"
    comp_by_name = {c["name"]: c for c in components}
    lines.append(f"    part def {root_name} {{")
    for comp in components:
        lines.append(f"        part {comp['name'].lower()} : {comp['name']};")

    for cn in (connections or []):
        src = comp_by_name.get(cn.get("from", ""))
        dst = comp_by_name.get(cn.get("to", ""))
        if not src or not dst or src["name"] == dst["name"]:
            continue
        dom = cn.get("domain", "")
        src_port = next((p["name"] for p in src.get("ports", []) if p.get("direction") == "out" and (not dom or p.get("domain") == dom)), None)
        dst_port = next((p["name"] for p in dst.get("ports", []) if p.get("direction") == "in" and (not dom or p.get("domain") == dom)), None)
        if src_port and dst_port:
            lines.append(f"        connect {src['name'].lower()}.{src_port} to {dst['name'].lower()}.{dst_port};")

    lines.append("    }")
    lines.append("")

    # Top-level system instance & satisfy links (no self-reference inside part def)
    lines.append(f"    part system : {root_name};")
    for req in requirements:
        lines.append(f"    satisfy '{req['id']}' by system;")
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

    # Agent 3: Render SysML v2 with explicit port defs, connect, state def, PowerBudget & satisfy links
    sysml_code = _render_livrable2_sysml(
        project_name,
        conops,
        requirements,
        components,
        connections=connections,
        physics_params=params,
        spec_text=spec_text,
    )

    # Agent 4: Deterministic syntax validation with active LLM repair loop (Choice 1 & 10)
    syntax_ok, syntax_errors = check_sysml_syntax(sysml_code)
    provider = detect_env_llm_provider(override_gemini_key=override_gemini_key)
    repair_attempts = 1
    if not syntax_ok and provider is not None:
        for attempt in range(2, 4):  # max 2 tentatives de réparation
            repair_attempts = attempt
            repaired = repair_sysml_syntax(sysml_code, syntax_errors, provider)
            ok_rep, err_rep = check_sysml_syntax(repaired)
            if ok_rep:
                sysml_code = repaired
                syntax_ok, syntax_errors = ok_rep, err_rep
                break
            elif attempt == 3:
                syntax_errors.append(
                    "Arrêt lucide Orchestrateur : persistance d'anomalies de syntaxe après 2 essais de réparation LLM."
                )

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

    # Agent 6: Satisfy recall >= 95% + Boucle sémantique vers Agent 3 (Choix 10, p. 12)
    root_name = _slugify_part_name(project_name) + "System"
    recall_pct = _compute_satisfy_recall(sysml_code, requirements)
    semantic_completed = False
    if recall_pct < 95.0 and requirements:
        missing_req_ids = [
            r["id"]
            for r in requirements
            if f"satisfy '{r['id']}'" not in sysml_code
            and f"satisfy {r['id']}" not in sysml_code
        ]
        if missing_req_ids:
            sysml_code = complete_sysml_satisfaction(sysml_code, missing_req_ids, root_name)
            semantic_completed = True
            # Re-vérification syntaxique et sémantique obligatoire (Choix 10, p. 12)
            syntax_ok, syntax_errors = check_sysml_syntax(sysml_code)
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
        repair_attempts=repair_attempts,
        semantic_completed=semantic_completed,
    )
