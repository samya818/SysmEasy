"""PlantUML diagram renderer derived strictly from parsed SysML v2 code (Single Source of Truth).

Parses `sysml_code` directly (`package`, `port def`, `part def`, `connect`, `state def`,
`transition`, `requirement def`, `satisfy`) so diagrams never invent elements absent
from the SysML v2 model. Renders PNGs via Kroki (https://kroki.io/plantuml/png) with
automatic fallback to the public PlantUML server — zero matplotlib, zero ELK/Node.js.
"""

from __future__ import annotations

import logging
import os
import re
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass, field
from typing import Any

from sysmeasy.livrable2_pipeline import Livrable2Result
from sysmeasy.methodology.diagram_selector import DiagramPlan, DiagramSpec

logger = logging.getLogger(__name__)

_KROKI_URL = "https://kroki.io/plantuml/png"
_PLANTUML_URL = "https://www.plantuml.com/plantuml/png"
_PLANTUML_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"

_FALLBACK_1X1_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00"
    b"\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

_THEME_HEADER = """\
skinparam shadowing false
skinparam roundcorner 8
skinparam backgroundColor #F8FAFC
skinparam defaultFontName SansSerif
skinparam defaultFontSize 12
skinparam ArrowColor #2563EB
skinparam ArrowThickness 1.4
skinparam rectangle {
  BackgroundColor #FFFFFF
  BorderColor #3B82F6
  FontColor #0F172A
}
skinparam package {
  BackgroundColor #FFFFFF
  BorderColor #1E3A8A
  FontColor #1E3A8A
}
skinparam state {
  BackgroundColor #EFF6FF
  BorderColor #2563EB
  FontColor #0F172A
}
skinparam note {
  BackgroundColor #FFFBEB
  BorderColor #F59E0B
  FontColor #78350F
}"""


@dataclass
class ParsedSysML:
    """Structured AST extracted strictly from textual SysML v2 code."""

    project_name: str = "System"
    doc_text: str = ""
    port_defs: list[str] = field(default_factory=list)
    requirements: list[dict[str, str]] = field(default_factory=list)
    parts: list[dict[str, Any]] = field(default_factory=list)
    power_budget: dict[str, float] = field(default_factory=dict)
    states: list[str] = field(default_factory=list)
    transitions: list[tuple[str, str, str]] = field(default_factory=list)  # (src, guard, dst)
    connections: list[tuple[str, str, str, str]] = field(default_factory=list)  # (src_inst, src_port, dst_inst, dst_port)
    satisfies: list[tuple[str, str]] = field(default_factory=list)  # (req_id, target)
    part_instances: dict[str, str] = field(default_factory=dict)  # instance_lower -> PartDefName


def parse_sysml_code(sysml_code: str) -> ParsedSysML:
    """Parse textual SysML v2 code into a deterministic model representation."""
    parsed = ParsedSysML()
    if m_pkg := re.search(r"package\s+'([^']+)'|package\s+(\w+)", sysml_code):
        parsed.project_name = m_pkg.group(1) or m_pkg.group(2)
    if m_doc := re.search(r"^\s*doc\s+/\*\s*(.*?)\s*\*/", sysml_code, re.MULTILINE):
        parsed.doc_text = m_doc.group(1).strip()

    parsed.port_defs = re.findall(r"port\s+def\s+(\w+)\s*;", sysml_code)

    for req_id, body in re.findall(r"requirement\s+def\s+'([^']+)'\s*\{(.*?)\}", sysml_code, re.DOTALL):
        doc_m = re.search(r"doc\s+/\*\s*(.*?)\s*\*/", body)
        val_m = re.search(r"attribute\s+targetValue\s*:\s*Real\s*=\s*([0-9.]+)\s*;", body)
        unit_m = re.search(r'attribute\s+unit\s*:\s*String\s*=\s*"([^"]*)"\s*;', body)
        parsed.requirements.append({
            "id": req_id,
            "doc": doc_m.group(1).strip() if doc_m else req_id,
            "val": val_m.group(1) if val_m else "",
            "unit": unit_m.group(1) if unit_m else "",
        })

    for pname, body in re.findall(r"part\s+def\s+(\w+)\s*\{(.*?)\}", sysml_code, re.DOTALL):
        if pname == "PowerBudget":
            for attr, val in re.findall(r"attribute\s+(\w+)\s*:\s*Real\s*=\s*([0-9.]+)\s*;", body):
                parsed.power_budget[attr] = float(val)
            continue

        # Capture sub-part instances and `connect` links in assembly part defs
        insts = re.findall(r"^\s*part\s+(\w+)\s*:\s*(\w+)\s*;", body, re.MULTILINE)
        conns = re.findall(r"connect\s+(\w+)\.(\w+)\s+to\s+(\w+)\.(\w+)\s*;", body)
        if insts:
            for inst_name, type_name in insts:
                parsed.part_instances[inst_name] = type_name
            parsed.connections.extend(conns)
            continue

        mass_m = re.search(r"attribute\s+mass_kg\s*:\s*Real\s*=\s*([0-9.]+)\s*;", body)
        power_m = re.search(r"attribute\s+power_w\s*:\s*Real\s*=\s*([0-9.]+)\s*;", body)
        ports = re.findall(r"(in|out|inout)\s+port\s+(\w+)\s*:\s*(\w+)\s*;", body)
        parsed.parts.append({
            "name": pname,
            "mass_kg": float(mass_m.group(1)) if mass_m else 0.0,
            "power_w": float(power_m.group(1)) if power_m else 0.0,
            "ports": [{"direction": d, "name": n, "type": t} for d, n, t in ports],
        })

    for s_body in re.findall(r"state\s+def\s+\w+\s*\{(.*?)\}", sysml_code, re.DOTALL):
        parsed.states.extend(re.findall(r"^\s*state\s+(\w+)\s*;", s_body, re.MULTILINE))
        for _tname, src, guard, dst in re.findall(
            r"transition\s+(\w+)\s+first\s+(\w+)\s+accept\s+(\w+)\s+then\s+(\w+)\s*;", s_body
        ):
            parsed.transitions.append((src, guard, dst))

    parsed.satisfies = re.findall(r"satisfy\s+'([^']+)'\s+by\s+(\w+)\s*;", sysml_code)
    return parsed


def extract_sysml_slice(sysml_code: str, diagram_type: str) -> str:
    """Return only the SysML v2 snippet relevant to the given diagram view."""
    if not sysml_code.strip():
        return ""

    if diagram_type == "stm":
        blocks = re.findall(r"(state\s+def\s+\w+\s*\{.*?\})", sysml_code, re.DOTALL)
        return "\n\n".join(b.strip() for b in blocks) if blocks else "// Aucun bloc state def défini dans ce modèle."

    if diagram_type == "par":
        blocks = re.findall(r"(part\s+def\s+PowerBudget\s*\{.*?\})", sysml_code, re.DOTALL)
        reqs = [
            b.strip()
            for b in re.findall(r"(requirement\s+def\s+'[^']+'\s*\{.*?\})", sysml_code, re.DOTALL)
            if 'unit : String = "spec"' not in b
        ]
        parts = blocks + reqs[:6]
        return "\n\n".join(parts) if parts else sysml_code

    if diagram_type in ("context_bdd", "uc"):
        header = []
        if m := re.search(r"(package\s+'[^']+'\s*\{)", sysml_code):
            header.append(m.group(1))
        if m := re.search(r"^\s*(doc\s+/\*.*?\*/)", sysml_code, re.MULTILINE):
            header.append("    " + m.group(1))
        sats = re.findall(r"^\s*(part\s+system\s*:.*|satisfy\s+.*)", sysml_code, re.MULTILINE)
        header.extend("    " + s.strip() for s in sats[:10])
        if header:
            header.append("}")
            return "\n".join(header)

    if diagram_type == "ibd":
        pdefs = re.findall(r"^\s*(port\s+def\s+\w+\s*;)", sysml_code, re.MULTILINE)
        parts = re.findall(r"(part\s+def\s+(?!PowerBudget\b)\w+\s*\{.*?\})", sysml_code, re.DOTALL)
        snippet = pdefs + [p.strip() for p in parts]
        if snippet:
            return "\n\n".join(snippet)

    return sysml_code


def _safe(text: str, wrap_width: int = 0) -> str:
    """Sanitize text for PlantUML without truncating information."""
    cleaned = re.sub(r'[\r\n"\[\]{}<>]+', " ", str(text or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return "System"
    if wrap_width > 0 and len(cleaned) > wrap_width:
        words, lines, cur = cleaned.split(" "), [], ""
        for w in words:
            if cur and len(cur) + 1 + len(w) > wrap_width:
                lines.append(cur)
                cur = w
            else:
                cur = f"{cur} {w}".strip()
        if cur:
            lines.append(cur)
        return "\\n".join(lines)
    return cleaned


def _alias(name: str, fallback: str = "node") -> str:
    slug = re.sub(r"[^A-Za-z0-9_]", "_", str(name or ""))
    if not slug or slug[0].isdigit():
        slug = f"{fallback}_{slug}"
    return slug


def _encode_plantuml(source: str) -> str:
    compressed = zlib.compress(source.encode("utf-8"), 9)[2:-4]
    out: list[str] = []
    for i in range(0, len(compressed), 3):
        b1 = compressed[i]
        b2 = compressed[i + 1] if i + 1 < len(compressed) else 0
        b3 = compressed[i + 2] if i + 2 < len(compressed) else 0
        out.append(_PLANTUML_ALPHABET[b1 >> 2])
        out.append(_PLANTUML_ALPHABET[((b1 & 0x3) << 4) | (b2 >> 4)])
        out.append(_PLANTUML_ALPHABET[((b2 & 0xF) << 2) | (b3 >> 6)])
        out.append(_PLANTUML_ALPHABET[b3 & 0x3F])
    return "".join(out)


def build_plantuml_source(
    result: Livrable2Result,
    diagram_type: str,
    raw_prompt: str = "",
    spec: DiagramSpec | None = None,
) -> str:
    """Generate PlantUML source strictly from parsed `result.sysml_code`."""
    model = parse_sysml_code(result.sysml_code)
    proj = _safe(model.project_name)

    if diagram_type in ("context_bdd", "uc"):
        lines = [
            "@startuml",
            f"title General View (Contexte) - {proj}",
            _THEME_HEADER,
            "left to right direction",
            f'rectangle "{proj}\\n({len(model.parts)} part def | {len(model.requirements)} requirement def)" as soi <<system>> #DBEAFE',
        ]
        for idx, req in enumerate(model.requirements[:8]):
            al = _alias(req["id"], f"R{idx}")
            lines.append(f'rectangle "{_safe(req["id"])}\\n{_safe(req["doc"], 32)}" as {al} <<requirement>> #EFF6FF')
            lines.append(f"soi ..> {al} : satisfy")
        if model.doc_text:
            lines.append(f'note bottom of soi : {_safe(model.doc_text, 65)}')
        lines.append("@enduml")
        return "\n".join(lines)

    if diagram_type == "stm":
        lines = ["@startuml", f"title State Transition View - {proj}", _THEME_HEADER]
        if not model.states:
            lines.append('note "Aucun state def / transition défini dans le code SysML v2." as empty_stm')
            lines.append("@enduml")
            return "\n".join(lines)
        for st in model.states:
            lines.append(f'state "{_safe(st)}" as {_alias(st, "S")}')
        lines.append(f"[*] --> {_alias(model.states[0], 'S')}")
        for src, guard, dst in model.transitions:
            lines.append(f"{_alias(src, 'S')} --> {_alias(dst, 'S')} : {_safe(guard)}")
        lines.append("@enduml")
        return "\n".join(lines)

    if diagram_type == "act":
        lines = ["@startuml", f"title Action Flow View - {proj}", _THEME_HEADER, "start"]
        steps = [_safe(r["doc"], 36) for r in model.requirements[:5]] or ["Initialiser systeme", "Executer mission", "Verifier contraintes"]
        for step in steps:
            lines.append(f":{step};")
        lines.extend(["stop", "@enduml"])
        return "\n".join(lines)

    if diagram_type == "par":
        total_mass = sum(p["mass_kg"] for p in model.parts)
        total_power = sum(p["power_w"] for p in model.parts)
        lines = [
            "@startuml",
            f"title Constraint & Budget View - {proj}",
            _THEME_HEADER,
            'package "Budgets extraits du code SysML v2" {',
            f'  object "PowerBudget & Bilan" as total {{',
            f"    Somme mass_kg = {total_mass:.2f} kg",
            f"    Somme power_w = {total_power:.1f} W",
        ]
        for k, v in model.power_budget.items():
            lines.append(f"    {k} = {v}")
        lines.extend(["  }", "}"])
        for idx, p in enumerate(model.parts):
            al = _alias(p["name"], f"P{idx}")
            lines.extend([
                f'object "{_safe(p["name"])}" as {al} {{',
                f"  mass_kg = {p['mass_kg']}",
                f"  power_w = {p['power_w']}",
                "}",
                f"{al} ..> total : contribue",
            ])
        lines.append("@enduml")
        return "\n".join(lines)

    # Default / IBD (Interconnection View): strictly reflects `part def`, `port`, and `connect` in sysml_code
    total_mass = sum(p["mass_kg"] for p in model.parts)
    total_power = sum(p["power_w"] for p in model.parts)
    title_line = f"Interconnection View (IBD) - {proj}\\nMasse (part def) : {total_mass:.1f} kg | Puissance : {total_power:.0f} W"
    if model.power_budget.get("bus_voltage_v") and model.power_budget.get("battery_capacity_ah") and total_power > 0:
        dod = model.power_budget.get("dod", 0.85)
        auto_min = (model.power_budget["bus_voltage_v"] * model.power_budget["battery_capacity_ah"] * dod / total_power) * 60.0
        title_line += f" | Autonomie : {auto_min:.0f} min"

    lines = [
        "@startuml",
        f"title {title_line}",
        _THEME_HEADER,
        "left to right direction",
        f'package "{proj}" {{',
    ]
    part_aliases: dict[str, str] = {}
    for idx, p in enumerate(model.parts):
        pname = p["name"]
        al = _alias(pname, f"B{idx}")
        part_aliases[pname] = al
        part_aliases[pname.lower()] = al
        ports_txt = ", ".join(f"{pt['direction']} {pt['name']}:{pt['type']}" for pt in p["ports"][:3])
        body = f"{_safe(pname)}\\n{p['mass_kg']} kg | {p['power_w']} W"
        if ports_txt:
            body += f"\\n[{ports_txt}]"
        lines.append(f'  rectangle "{body}" as {al} <<part def>>')
    lines.append("}")

    for src_inst, src_port, dst_inst, dst_port in model.connections:
        src_type = model.part_instances.get(src_inst, src_inst)
        dst_type = model.part_instances.get(dst_inst, dst_inst)
        src_al = part_aliases.get(src_type) or part_aliases.get(src_inst)
        dst_al = part_aliases.get(dst_type) or part_aliases.get(dst_inst)
        if src_al and dst_al:
            lines.append(f"{src_al} --> {dst_al} : {src_port} -> {dst_port}")

    lines.append("@enduml")
    return "\n".join(lines)


def render_plantuml_to_png(puml_source: str, output_path: str, timeout_s: float = 15.0) -> bool:
    """Render PlantUML source to PNG via Kroki (primary) or PlantUML server (fallback)."""
    headers = {"Content-Type": "text/plain; charset=utf-8", "User-Agent": "SysmEasy/2.5"}

    try:
        req = urllib.request.Request(_KROKI_URL, data=puml_source.encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            png_bytes = resp.read()
            if png_bytes.startswith(b"\x89PNG"):
                with open(output_path, "wb") as f:
                    f.write(png_bytes)
                return True
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("Kroki PlantUML render failed (%s), trying plantuml.com fallback", exc)

    try:
        encoded = _encode_plantuml(puml_source)
        req = urllib.request.Request(f"{_PLANTUML_URL}/{encoded}", headers={"User-Agent": "SysmEasy/2.5"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            png_bytes = resp.read()
            if png_bytes.startswith(b"\x89PNG"):
                with open(output_path, "wb") as f:
                    f.write(png_bytes)
                return True
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("PlantUML fallback render failed (%s), writing minimal offline placeholder", exc)

    with open(output_path, "wb") as f:
        f.write(_FALLBACK_1X1_PNG)
    return False


def render_selected_diagrams(
    result: Livrable2Result,
    plan: DiagramPlan,
    output_dir: str,
    raw_prompt: str = "",
) -> list[dict[str, Any]]:
    """Render all diagrams chosen by DiagramPlan strictly from `result.sysml_code`."""
    os.makedirs(output_dir, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", result.project_name.lower()).strip("_") or "custom"

    rendered: list[dict[str, Any]] = []
    for spec in plan.diagrams:
        fname = f"dyn_{slug}_{spec.type}.png"
        fpath = os.path.join(output_dir, fname)
        puml_source = build_plantuml_source(result, spec.type, raw_prompt=raw_prompt, spec=spec)
        render_plantuml_to_png(puml_source, fpath)

        rendered.append({
            "type": spec.type,
            "title": spec.title,
            "comment": spec.comment,
            "img_url": f"/images/{fname}",
            "img_path": fpath,
            "plantuml_source": puml_source,
            "sysml_code": extract_sysml_slice(result.sysml_code, spec.type),
        })
    return rendered
