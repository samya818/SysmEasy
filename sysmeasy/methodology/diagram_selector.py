"""LLM-driven SysML diagram selector grounded in M. Motte's MBSE methodologies.

Encodes the diagram selection principles from:
  - MagicGrid (Aleksandraviciene & Morkevicius, 2021):
      * Problem Domain (Black-box): System Context (ibd/bdd), Use Cases (uc), Scenarios (act)
      * Solution Domain: Structure (ibd), Behavior (stm for modes/states, act for flows), Parameters (par)
  - HarmonySE (Hoffmann, IBM Rhapsody Deskbook):
      * Requirements -> Functional Analysis (act/sd/stm) -> Architecture Design (bdd/ibd)
  - ARCADIA (Roques, Capella):
      * Operational / System / Logical / Physical layers & functional/energy exchanges
  - Guo et al. (CECNet 2022) & Elaasar et al. (MBSE Survey 2025):
      * Choose 2 to 4 complementary, readable views suited to stakeholders.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from sysmeasy.contracts.llm_provider import LLMProvider, detect_env_llm_provider
from sysmeasy.livrable2_pipeline import Livrable2Result

VALID_DIAGRAM_TYPES = ("context_bdd", "uc", "ibd", "stm", "act", "par")

MOTTE_METHODOLOGY_PROMPT = """Tu es un architecte MBSE expert en MagicGrid, HarmonySE et ARCADIA (4 piliers SysML : Requirements, Structure, Behavior, Parameters).
À partir d'un cahier des charges résumé, choisis **3 diagrammes complémentaires par défaut** (2 si CDC simple/partiel, 4 max uniquement si budgets chiffrés ET modes sont tous deux critiques, jamais plus de 4, sans redondance) :

Règle clé (Guo et al., 2022) :
- Problem Domain (analyse amont) -> `act` pour les flux fonctionnels sans modes.
- Solution Domain (conception système/sous-système) -> `stm` pour les modes/transitions + `ibd` pour les ports et flux physiques.

Applique ces 4 profils de décision :
- **Cas A — Système électromécanique / énergie / multi-composants** -> 3 vues (4 si `stm` + `par` critiques) : `context_bdd` (Niveau 0 boîte noire) + `ibd` (ports typés `out->in`, W, kg) + `par` (si budgets masse/puissance/autonomie) ou `act` (si boucle de contrôle).
- **Cas B — Système commandé par modes / états / boucle d'asservissement** -> 3 vues : `context_bdd` (ou `uc`) + `ibd` (capteurs/contrôleur/actionneurs) + `stm` (états/modes et seuils/conditions de transition).
- **Cas C — Système orienté connectivité, interfaces & contraintes produit** (type ARCADIA) -> 3 vues : `uc` (ou `context_bdd`) + `ibd` (interfaces vidéo/signal/puissance/thermique) + `stm` (ou `act` si séquence sans modes).
- **Cas D — Demande simple / partielle sans comportement dynamique** -> 2 vues suffisent : `context_bdd` + `ibd`.

Règles de contenu :
1. "context_bdd" : vue Niveau 0 boîte noire (acteurs/environnement + exigences clés).
2. "ibd" : indispensable dès >= 2 sous-systèmes ou ports/flux.
3. "stm" : fournis "states" (3 à 4 états propres au système), "transitions" (déclencheurs concis uniquement, sans répéter "-> ÉtatCible") et "layout_direction" ("DOWN" si >= 4 états ou longs libellés pour tenir lisiblement sur A4, sinon "RIGHT").
4. "act" : enchaînement d'actions sans modes explicites.
5. "par" : uniquement si le CDC impose des budgets numériques critiques (masse, puissance, autonomie).
6. "uc" : seulement si plusieurs acteurs humains/externes interagissent avec des services distincts.

Réponds UNIQUEMENT en JSON valide sans jargon technique :
{
  "methodology": "MagicGrid" | "HarmonySE" | "ARCADIA",
  "diagrams": [
    {
      "type": "context_bdd|uc|ibd|stm|act|par",
      "title": "Titre court en français",
      "comment": "1 phrase simple et claire expliquant ce que montre ce schéma.",
      "layout_direction": "RIGHT" | "DOWN",
      "states": ["optionnel pour stm: État 1", "État 2", "État 3"],
      "transitions": ["optionnel pour stm: déclencheur 1", "déclencheur 2"]
    }
  ]
}"""


@dataclass(frozen=True)
class DiagramSpec:
    """Single selected diagram specification."""

    type: str
    title: str
    comment: str
    states: list[str] = field(default_factory=list)
    transitions: list[str] = field(default_factory=list)
    layout_direction: str = "RIGHT"
    aspect_ratio: float = 2.0


@dataclass(frozen=True)
class DiagramPlan:
    """Selected methodology and ordered list of diagrams (2 to 4)."""

    methodology: str
    diagrams: list[DiagramSpec]


def _build_spec_summary(result: Livrable2Result, raw_prompt: str) -> str:
    reqs = "; ".join(f"{r['id']}: {r['target']} ({r['comparator']} {r['numerical_val']} {r['unit']})" for r in result.requirements[:10])
    comps = ", ".join(f"{c.get('label', c['name'])} ({c['mass_kg']}kg, {c['power_w']}W)" for c in result.components[:10])
    return (
        f"Projet: {result.project_name}\n"
        f"Mission: {result.conops}\n"
        f"Exigences ({len(result.requirements)}): {reqs}\n"
        f"Composants ({len(result.components)}): {comps}\n"
        f"Bilan physique: masse={result.total_mass_kg}kg, puissance={result.total_power_w}W, autonomie={result.autonomy_min}min\n"
        f"Extrait CDC: {raw_prompt[:600]}"
    )


def _parse_llm_plan(raw_json: str) -> DiagramPlan | None:
    match = re.search(r"\{.*\}", raw_json, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

    methodology = str(data.get("methodology", "MagicGrid"))
    items = data.get("diagrams", [])
    specs: list[DiagramSpec] = []
    seen: set[str] = set()
    for item in items:
        dtype = str(item.get("type", "")).strip()
        if dtype in VALID_DIAGRAM_TYPES and dtype not in seen:
            seen.add(dtype)
            raw_dir = str(item.get("layout_direction", "RIGHT")).strip().upper()
            layout_dir = raw_dir if raw_dir in ("RIGHT", "DOWN") else "RIGHT"
            specs.append(DiagramSpec(
                type=dtype,
                title=str(item.get("title", dtype)).strip()[:90],
                comment=str(item.get("comment", "")).strip()[:260],
                states=[str(s).strip()[:32] for s in (item.get("states") or [])[:4]],
                transitions=[str(t).strip()[:48] for t in (item.get("transitions") or [])[:4]],
                layout_direction=layout_dir,
            ))
    if len(specs) < 2:
        return None
    return DiagramPlan(methodology=methodology, diagrams=specs[:4])


def _heuristic_motte_plan(result: Livrable2Result, raw_prompt: str) -> DiagramPlan:
    """Deterministic fallback applying the exact Motte (MagicGrid/HarmonySE) rules."""
    text = f"{result.conops} {raw_prompt}".lower()
    has_modes = any(k in text for k in [
        "mode", "état", "etat", "veille", "démarrage", "demarrage", "arrêt", "arret",
        "surchauffe", "urgence", "charge", "until", "boucle", "température", "temperature", "seuil",
    ])
    has_actions = any(k in text for k in [
        "étape", "etape", "scénario", "scenario", "séquence", "sequence", "flux",
        "pulvérisation", "pulverisation", "désherbage", "desherbage", "projeter", "desservir",
    ])
    has_budgets = (
        result.total_mass_kg > 0
        or result.total_power_w > 0
        or result.autonomy_min is not None
        or any(r["unit"] in ("kg", "min", "W") for r in result.requirements)
    )
    has_multi_components = len(result.components) >= 2

    diagrams: list[DiagramSpec] = [
        DiagramSpec(
            type="context_bdd",
            title=f"Vue d'ensemble — {result.project_name}",
            comment=f"Situe {result.project_name} dans son environnement opérationnel avec ses interfaces externes et exigences principales.",
        )
    ]

    if has_multi_components:
        diagrams.append(DiagramSpec(
            type="ibd",
            title="Architecture interne et échanges",
            comment=f"Présente les {len(result.components)} sous-systèmes identifiés et les flux physiques ou de commande qui les relient.",
        ))

    if has_modes:
        diagrams.append(DiagramSpec(
            type="stm",
            title="Modes de fonctionnement et transitions",
            comment="Décrit les états opérationnels du système et les conditions de passage d'un mode à l'autre.",
        ))
    elif has_actions:
        diagrams.append(DiagramSpec(
            type="act",
            title="Déroulement fonctionnel",
            comment="Illustre l'enchaînement des fonctions principales assurées par le système.",
        ))

    if has_budgets and len(diagrams) < 4:
        diagrams.append(DiagramSpec(
            type="par",
            title="Bilan des budgets (masse et énergie)",
            comment=f"Synthétise la répartition de la masse ({result.total_mass_kg:.1f} kg) et de l'énergie ({result.total_power_w:.0f} W) par rapport aux limites.",
        ))

    # Ensure at least 2 diagrams
    if len(diagrams) < 2:
        diagrams.append(DiagramSpec(
            type="ibd",
            title="Structure et composants",
            comment=f"Détaille les composants principaux extraits pour {result.project_name}.",
        ))

    methodology = "HarmonySE" if has_modes and not has_budgets else "MagicGrid"
    return DiagramPlan(methodology=methodology, diagrams=diagrams[:4])


def select_diagrams(
    result: Livrable2Result,
    raw_prompt: str = "",
    provider: LLMProvider | None = None,
    *,
    strict_llm: bool = False,
) -> DiagramPlan:
    """Ask the LLM (or Motte-rule fallback if strict_llm=False) which 2-4 diagrams to render."""
    active_provider = provider or detect_env_llm_provider()
    if active_provider is None:
        if strict_llm:
            raise RuntimeError("Aucune clé API LLM configurée pour le choix des diagrammes.")
        return _heuristic_motte_plan(result, raw_prompt)
    try:
        summary = _build_spec_summary(result, raw_prompt)
        resp = active_provider.complete(MOTTE_METHODOLOGY_PROMPT, summary, temperature=0.0)
        plan = _parse_llm_plan(resp.content)
        if plan is not None:
            return plan
        if strict_llm:
            raise RuntimeError("Le LLM n'a pas renvoyé un plan de diagrammes valide.")
    except Exception as exc:
        if strict_llm:
            raise RuntimeError(f"Erreur LLM (sélection de diagrammes) : {exc}") from exc
    return _heuristic_motte_plan(result, raw_prompt)
