"""PlantUML diagram renderer for SysML views selected by DiagramPlan.

Generates clean PlantUML source from Livrable2Result and renders PNGs via
Kroki (https://kroki.io/plantuml/png) with automatic fallback to the public
PlantUML server — zero matplotlib, zero ELK/Node.js, 100% Vercel-compatible.
"""

from __future__ import annotations

import logging
import os
import re
import urllib.error
import urllib.request
import zlib
from typing import Any

from sysmeasy.livrable2_pipeline import Livrable2Result
from sysmeasy.methodology.diagram_selector import DiagramPlan, DiagramSpec

logger = logging.getLogger(__name__)

_KROKI_URL = "https://kroki.io/plantuml/png"
_PLANTUML_URL = "https://www.plantuml.com/plantuml/png"
_PLANTUML_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"

# Minimal 1x1 transparent PNG used only if both remote PlantUML servers are unreachable offline.
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


def _safe(text: str, max_len: int = 48) -> str:
    """Sanitize text for PlantUML labels so brackets/quotes never break syntax."""
    cleaned = re.sub(r'[\r\n"\[\]{}<>]+', " ", str(text or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) > max_len:
        return cleaned[: max_len - 1].rstrip() + "…"
    return cleaned or "System"


def _alias(name: str, fallback: str = "node") -> str:
    """Return a safe PlantUML identifier."""
    slug = re.sub(r"[^A-Za-z0-9_]", "_", str(name or ""))
    if not slug or slug[0].isdigit():
        slug = f"{fallback}_{slug}"
    return slug


def _encode_plantuml(source: str) -> str:
    """Encode PlantUML text using standard deflate + 6-bit PlantUML alphabet."""
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
    """Generate PlantUML source code for the requested SysML view."""
    proj = _safe(result.project_name, 36)

    if diagram_type in ("context_bdd", "uc"):
        lines = [
            "@startuml",
            f'title bdd [System Context] {proj}',
            _THEME_HEADER,
            "left to right direction",
            'actor "Operateur / Utilisateur" as op',
            'rectangle "Source Energie" as pwr <<environment>>',
            f'rectangle "{proj}\\n({len(result.components)} blocs | {len(result.requirements)} exigences)" as soi <<system>> #DBEAFE',
            'rectangle "Environnement Terrain" as env <<environment>>',
            f'rectangle "Exigences Cles ({len(result.requirements)})" as reqs <<requirement>> #EFF6FF',
            "op <--> soi : Commandes / Retours",
            "pwr --> soi : Alimentation",
            "soi <--> env : Interactions physiques",
            "soi ..> reqs : satisfy",
        ]
        if result.conops:
            lines.append(f'note bottom of soi : {_safe(result.conops, 90)}')
        lines.append("@enduml")
        return "\n".join(lines)

    if diagram_type == "stm":
        states = list(spec.states) if spec and len(spec.states) >= 2 else _extract_states(result, raw_prompt)
        guards = list(spec.transitions) if spec and spec.transitions else ["init_ok", "seuil / defaut", "urgence"]
        lines = ["@startuml", f"title stm [State Machine] Modes - {proj}", _THEME_HEADER]
        aliases = [_alias(f"S{i}_{s}", "S") for i, s in enumerate(states)]
        for al, st in zip(aliases, states):
            lines.append(f'state "{_safe(st, 28)}" as {al}')
        lines.append(f"[*] --> {aliases[0]}")
        for i in range(len(aliases) - 1):
            guard = _safe(guards[i % len(guards)], 28)
            lines.append(f"{aliases[i]} --> {aliases[i + 1]} : {guard}")
        if len(aliases) >= 2:
            lines.append(f"{aliases[-1]} --> {aliases[0]} : Rearmement / Cycle")
        lines.append("@enduml")
        return "\n".join(lines)

    if diagram_type == "act":
        steps = [_safe(r["name"], 32) for r in result.requirements[:4]]
        if len(steps) < 3:
            steps = ["Acquerir entrees", "Traiter et Reguler", "Executer mission", "Controler securite"]
        lines = ["@startuml", f"title act [Activity] Flux Fonctionnel - {proj}", _THEME_HEADER, "start"]
        for step in steps:
            lines.append(f":{step};")
        lines.extend(["stop", "@enduml"])
        return "\n".join(lines)

    if diagram_type == "par":
        comps = [c for c in result.components if c["mass_kg"] > 0 or c["power_w"] > 0][:10] or result.components[:6]
        lines = [
            "@startuml",
            f"title par [Parametric] Budgets Systeme - {proj}",
            _THEME_HEADER,
            f'package "Bilan Global" {{',
            f'  object "Budgets {proj}" as total {{',
            f"    Masse totale = {result.total_mass_kg:.2f} kg",
            f"    Puissance totale = {result.total_power_w:.1f} W",
        ]
        if result.autonomy_min is not None:
            lines.append(f"    Autonomie = {result.autonomy_min:.0f} min")
        lines.append("  }")
        lines.append("}")
        for idx, c in enumerate(comps):
            al = _alias(c["name"], f"C{idx}")
            lbl = _safe(c.get("label", c["name"]), 28)
            lines.append(f'object "{lbl}" as {al} {{')
            lines.append(f"  mass_kg = {c['mass_kg']}")
            lines.append(f"  power_w = {c['power_w']}")
            lines.append("}")
            lines.append(f"{al} ..> total : contribue")
        lines.append("@enduml")
        return "\n".join(lines)

    # Default / IBD: Internal Block Diagram
    comps = result.components[:14]
    conns = [cn for cn in result.connections if cn.get("from") and cn.get("to") and cn["from"] != cn["to"]]
    summary = f"Masse : {result.total_mass_kg:.1f} kg | Puissance : {result.total_power_w:.0f} W"
    if result.autonomy_min is not None:
        summary += f" | Autonomie : {result.autonomy_min:.0f} min"

    lines = [
        "@startuml",
        f"title ibd [part def] {proj}\\n{summary}",
        _THEME_HEADER,
        "left to right direction",
        f'package "{proj}" {{',
    ]
    comp_aliases: dict[str, str] = {}
    for idx, c in enumerate(comps):
        cname = c["name"]
        al = _alias(cname, f"B{idx}")
        comp_aliases[cname] = al
        lbl = _safe(c.get("label", cname), 28)
        cat = _safe(c.get("category", "part"), 14)
        ports_txt = ", ".join(f"{p['direction']}:{_safe(p['name'], 12)}" for p in c.get("ports", [])[:2])
        body = f"{lbl}\\n{c['mass_kg']} kg | {c['power_w']} W"
        if ports_txt:
            body += f"\\n[{ports_txt}]"
        lines.append(f'  rectangle "{body}" as {al} <<{cat}>>')
    lines.append("}")

    if conns:
        for cn in conns:
            src_al = comp_aliases.get(cn["from"])
            dst_al = comp_aliases.get(cn["to"])
            if src_al and dst_al:
                lbl = _safe(cn.get("label") or cn.get("domain") or "flux", 24)
                lines.append(f"{src_al} --> {dst_al} : {lbl}")
    else:
        sources = [c for c in comps if any(p.get("direction") == "out" for p in c.get("ports", []))]
        sinks = [c for c in comps if any(p.get("direction") == "in" for p in c.get("ports", []))]
        if sources and sinks:
            src_al = comp_aliases.get(sources[0]["name"])
            for sink in sinks:
                dst_al = comp_aliases.get(sink["name"])
                if src_al and dst_al and src_al != dst_al:
                    lines.append(f"{src_al} --> {dst_al} : power")

    lines.append("@enduml")
    return "\n".join(lines)


def _extract_states(result: Livrable2Result, raw_prompt: str) -> list[str]:
    text = f"{result.conops} {raw_prompt}".lower()
    candidates = [
        ("Veille / Arret", ["veille", "arrêt", "arret", "standby"]),
        ("Demarrage / Init", ["démarrage", "demarrage", "initialisation", "boot"]),
        ("Fonctionnement Nominal", ["nominal", "projection", "travail", "marche", "charge", "croisière"]),
        ("Mode Eco / Regulation", ["éco", "eco", "régul", "regul", "thermique"]),
        ("Securite / Urgence", ["urgence", "surchauffe", "défaut", "defaut", "coupure", "100%"]),
    ]
    states = [name for name, kws in candidates if any(k in text for k in kws)]
    if len(states) < 3:
        states = ["Initialisation", "Mode Nominal", "Mode Degrade / Arret"]
    return states[:4]


def render_plantuml_to_png(puml_source: str, output_path: str, timeout_s: float = 15.0) -> bool:
    """Render PlantUML source to PNG via Kroki (primary) or PlantUML server (fallback)."""
    headers = {"Content-Type": "text/plain; charset=utf-8", "User-Agent": "SysmEasy/2.5"}

    # 1. Primary: Kroki POST /plantuml/png
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

    # 2. Fallback: public PlantUML GET /plantuml/png/<encoded>
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

    # 3. Offline safety: write minimal valid PNG so callers/PDF never crash without internet
    with open(output_path, "wb") as f:
        f.write(_FALLBACK_1X1_PNG)
    return False


def render_selected_diagrams(
    result: Livrable2Result,
    plan: DiagramPlan,
    output_dir: str,
    raw_prompt: str = "",
) -> list[dict[str, Any]]:
    """Render all diagrams chosen by DiagramPlan via PlantUML and return metadata + image URLs."""
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
        })
    return rendered
