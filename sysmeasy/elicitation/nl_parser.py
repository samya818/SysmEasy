"""Structured natural-language specification parser (Agent 2 elicitation).

Extracts requirements (REQ-xx), components (mass_kg, power_w), bus voltage,
battery capacity, and ambiguities from a raw engineering prompt into a
JCS-sealed INPUT 1 contract.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from sysmeasy.contracts.jcs_seal import canonical_sha256
from sysmeasy.contracts.llm_provider import LLMProvider, detect_env_llm_provider

_REQ_LINE_RE = re.compile(
    r"[-*•]?\s*(REQ-\d+)\s*[:\-–]\s*(.+?)\s*(?:$|(?=\n))",
    re.MULTILINE,
)
_COMP_LINE_RE = re.compile(
    r"^\s*[-*•]\s*([^:\n]+?)\s*:\s*([^\n]+)$",
    re.MULTILINE,
)
_MASS_RE = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*kg\b", re.IGNORECASE)
_POWER_RE = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*W\b")
_VOLT_RE = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*V\b")
_AH_RE = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*Ah\b", re.IGNORECASE)
_MAH_RE = re.compile(r"([0-9]+(?:[\s\u00a0][0-9]+)*(?:[.,][0-9]+)?)\s*mAh\b", re.IGNORECASE)
_WH_RE = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*Wh\b", re.IGNORECASE)
_DOD_RE = re.compile(r"(?:décharge|dod)[^\d]{0,20}([0-9]+(?:[.,][0-9]+)?)\s*%", re.IGNORECASE)
_HOURS_RE = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*(?:h|heures?)\b", re.IGNORECASE)
_MIN_RE = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*min(?:utes?)?\b", re.IGNORECASE)
_SPEED_RE = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*m/s\b", re.IGNORECASE)
_DB_RE = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*dB\b", re.IGNORECASE)
_LM_RE = re.compile(r"([0-9]+(?:[\s\u00a0][0-9]+)*)\s*(?:lumens?|lm)\b", re.IGNORECASE)
_SEC_RE = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*(?:s|secondes?)\b", re.IGNORECASE)


class CDCUnreadableError(ValueError):
    """Raised when the input document/specification cannot be parsed into readable text (IN-05)."""
    pass


def validate_cdc_payload(raw_text: str, file_name: str = "") -> None:
    """Fail-fast gate: verify that the input text contains readable specification content.

    Blocks processing on binary streams, corrupt extractions, or unreadable inputs (IN-05).
    """
    cleaned = raw_text.strip()
    if not cleaned:
        raise CDCUnreadableError("Le cahier des charges fourni est vide.")

    # Check for raw binary indicators (e.g. unextracted PDF binary stream or replacement characters)
    if cleaned.startswith("%PDF-") or "\x00" in cleaned:
        raise CDCUnreadableError(
            "IN-05 BLOQUÉ : Le fichier transmis est un flux binaire brut non extrait. "
            "Une extraction textuelle ou OCR préalable est requise."
        )

    # Check for placeholder messages indicating extraction failure
    lower = cleaned.lower()
    if "document binaire" in lower or "document compressé" in lower or "fichier non lisible" in lower:
        raise CDCUnreadableError(
            "IN-05 BLOQUÉ : Le document source est illisible ou compressé sans texte extractible. "
            "Le pipeline refuse d'extrapoler sur une source invalide."
        )

    # Statistical check: must contain at least 20 printable alphabetical characters
    alpha_chars = sum(1 for c in cleaned if c.isalpha())
    if alpha_chars < 20:
        raise CDCUnreadableError(
            "IN-05 BLOQUÉ : Contenu textuel insuffisant pour établir un modèle d'ingénierie "
            f"({alpha_chars} caractères alphabétiques détectés, minimum 20 requis)."
        )


def _isolate_specification_section(prompt: str) -> str:
    """Strip role/task instructions and isolate the product specification block."""
    text = prompt.replace("\r\n", "\n").replace("\r", "\n")

    # Prefer explicit XML-like tags if provided.
    if "<requirements_spec>" in text and "</requirements_spec>" in text:
        return text.split("<requirements_spec>", 1)[1].split("</requirements_spec>", 1)[0].strip()

    # Slice from the specification header anywhere in the text (handles inline/flattened pastes).
    spec_start = re.search(
        r"(?i)(?:#{1,3}\s*(?:SITUATION|Cahier des charges|Spécifications?)\b|Cahier des charges\s*[—:\-])",
        text,
    )
    if spec_start:
        text = text[spec_start.start() :]

    # Stop before task/output instructions if present.
    task_start = re.search(r"(?im)(?:^|\s)#{1,3}\s*(?:TÂCHES|TACHES|TASKS)\b", text)
    if task_start:
        text = text[: task_start.start()]

    # Restore line breaks before inline markdown bullets (` - **Section** : ...`).
    text = re.sub(r"\s+-\s+(?=\*\*[^*]+\*\*\s*:)", "\n- ", text)
    return text.strip()


def _to_float(val: str) -> float:
    return float(val.replace(",", "."))


def _slugify_part_name(label: str) -> str:
    ascii_label = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode("ascii")
    clean = re.sub(r"[^A-Za-z0-9]+", " ", ascii_label).strip()
    words = [w.capitalize() for w in clean.split() if w]
    name = "".join(words) or "SubsystemPart"
    if name[0].isdigit():
        name = "Part" + name
    return name


def is_structured_cdc(prompt: str) -> bool:
    """Return True for any multi-clause engineering specification (not just short V1 demo keywords)."""
    spec_text = _isolate_specification_section(prompt)
    if _REQ_LINE_RE.search(spec_text):
        return True
    if _MASS_RE.search(spec_text) and (_POWER_RE.search(spec_text) or _VOLT_RE.search(spec_text)):
        return True
    if len(_COMP_LINE_RE.findall(spec_text)) >= 2:
        return True
    return len(spec_text) > 200


_EXTRACTION_SYSTEM_PROMPT = """Tu es un ingénieur MBSE. Extrais la structure d'un cahier des charges en JSON strict.
Règles critiques :
1. N'inclus JAMAIS les rubriques éditoriales ou contraintes globales (ex: Objectif, Mission, Contraintes, Environnement) dans "components".
2. Les limites globales du système (ex: MTOW <= 2.8 kg, autonomie >= 35 min) vont dans "requirements", PAS comme masse d'un composant.
3. Une plage de valeurs (ex: "0 °C à 45 °C") doit rester UNE SEULE exigence ("numerical_val": 0.0, "unit": "spec", "target": "0 °C à 45 °C"), ne jamais la couper en deux.
4. Un code normatif ou de classification (ex: "IP54", "IP67", "ISO ...") N'EST PAS une grandeur numérique : mets "numerical_val": 0.0, "unit": "spec", "target": "Protection IP54".
5. Chaque élément de "components" doit être un vrai sous-système matériel ou logiciel avec ses propres ports ("power_out"|"power_in"|"data_out"|"data_in").
6. Remplis "connections" avec les flux explicites entre composants ({"from": "NomCompA", "to": "NomCompB", "domain": "electrical|data|mechanical", "label": "flux"}).
7. "conops" doit être un texte libre de 2 à 4 phrases décrivant : la mission du système, son environnement opérationnel, les conditions d'usage et les contraintes de contexte qui ne peuvent pas être réduites à un chiffre (ex : terrain, climat, utilisateur cible). Ce champ est OBLIGATOIRE et alimente les balises doc du code SysML v2.
8. "operational_context" est un résumé libre (1-3 phrases) des contraintes qualitatives irréductibles à un JSON : matériaux imposés, fournisseurs préférés, normes de certification, conditions environnementales particulières, contraintes réglementaires.

Format JSON attendu :
{
  "project_name": "...",
  "conops": "2-4 phrases : mission, environnement, conditions d'usage, contraintes contextuelles non chiffrables",
  "operational_context": "1-3 phrases : contraintes qualitatives irréductibles (matériaux, fournisseurs, normes, réglementation)",
  "physics_params": {"bus_voltage_v": 24.0, "battery_capacity_ah": 20.0, "dod": 0.85},
  "requirements": [{"id": "REQ-01", "name": "...", "target": "...", "numerical_val": 0.0, "unit": "...", "comparator": "<=|>=|=="}],
  "components": [{"label": "...", "category": "part|actuator|sensor|controller", "mass_kg": 0.0, "power_w": 0.0, "ports": [{"name": "power_in", "direction": "in", "domain": "electrical", "unit": "V"}]}],
  "connections": [{"from": "...", "to": "...", "domain": "electrical", "label": "Énergie"}],
  "ambiguities": ["..."]
}"""


def _is_non_component_clause(clean_label: str, specs: str) -> bool:
    """Detect editorial sections or system-level constraints that must not become `part` blocks."""
    lbl = clean_label.lower().strip()
    sp = specs.lower()
    if any(lbl == h or lbl.startswith(h + " ") for h in (
        "objectif", "mission", "contexte", "contraintes", "environnement",
        "normes", "sécurité", "securite", "généralités", "generalites", "périmètre", "perimetre",
    )):
        return True
    if any(k in sp for k in ("mtow", "masse totale", "masse maximale", "masse en ordre de marche")) and not _POWER_RE.search(specs):
        return True
    return False


def _infer_ports_and_category(label: str, specs: str) -> tuple[str, list[dict[str, str]]]:
    txt = f"{label} {specs}".lower()
    ports: list[dict[str, str]] = []
    if any(k in txt for k in ["batterie", "battery", "pack", "alimentation", "énergie", "energie", "lipo", "lifepo4"]):
        ports.append({"name": "power_out", "direction": "out", "domain": "electrical", "unit": "V"})
    if any(k in txt for k in ["calculateur", "jetson", "ecu", "controller", "contrôle", "controle", "connectivité", "navigation", "communication", "télémétrie"]):
        ports.append({"name": "power_in", "direction": "in", "domain": "electrical", "unit": "V"})
        ports.append({"name": "data_in", "direction": "in", "domain": "data", "unit": "Mbps"})
        return "controller", ports
    if any(k in txt for k in ["lidar", "caméra", "camera", "sensor", "capteur", "optique", "charge utile", "gnss", "gps"]):
        ports.append({"name": "power_in", "direction": "in", "domain": "electrical", "unit": "V"})
        ports.append({"name": "data_out", "direction": "out", "domain": "data", "unit": "Mbps"})
        return "sensor", ports
    if any(k in txt for k in ["moteur", "pompe", "motor", "pump", "propulsion", "actionneur", "actuator"]):
        ports.append({"name": "power_in", "direction": "in", "domain": "electrical", "unit": "V"})
        return "actuator", ports
    return "part", ports


def _infer_connections(components: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Build directional IBD flows from matching out -> in ports across components."""
    conns: list[dict[str, str]] = []
    for domain, lbl in (("electrical", "Énergie"), ("data", "Données")):
        sources = [c for c in components if any(p.get("direction") == "out" and p.get("domain") == domain for p in c.get("ports", []))]
        sinks = [c for c in components if any(p.get("direction") == "in" and p.get("domain") == domain for p in c.get("ports", []))]
        if sources and sinks:
            src = sources[0]["name"]
            for sink in sinks:
                if sink["name"] != src:
                    conns.append({"from": src, "to": sink["name"], "domain": domain, "label": lbl})
    return conns


def _try_llm_extraction(prompt: str, provider: LLMProvider | None, *, strict_llm: bool = False) -> dict[str, Any] | None:
    active = provider or detect_env_llm_provider()
    if active is None:
        if strict_llm:
            raise RuntimeError("Aucune clé API LLM configurée (GEMINI_API_KEY / OPENAI_API_KEY / GROQ_API_KEY).")
        return None
    try:
        resp = active.complete(_EXTRACTION_SYSTEM_PROMPT, prompt[:4000], temperature=0.0)
        m = re.search(r"\{.*\}", resp.content, re.DOTALL)
        if not m:
            if strict_llm:
                raise RuntimeError("Le LLM n'a pas renvoyé de JSON valide pour l'extraction.")
            return None
        data = json.loads(m.group(0))
        if not isinstance(data.get("components"), list) or not isinstance(data.get("requirements"), list):
            if strict_llm:
                raise RuntimeError("JSON LLM incomplet (components/requirements manquants).")
            return None
        return data
    except Exception as exc:
        if strict_llm:
            raise RuntimeError(f"Erreur d'appel LLM : {exc}") from exc
        return None


def _detect_incose_vague_terms(text: str, requirements: list[dict[str, Any]]) -> list[str]:
    """Detect non-measurable terms prohibited by the INCOSE Guide for Writing Requirements (Livrable 2, p. 16)."""
    incose_alerts: list[str] = []
    vague_lexicon = [
        ("adapté", "adaptée"),
        ("raisonnable", "vitesse raisonnable"),
        ("optimal", "optimale"),
        ("suffisant", "suffisante"),
        ("bonne autonomie", "autonomie adéquate"),
        ("rapide", "temps rapide"),
        ("léger", "légère"),
        ("robuste", "conception robuste"),
        ("facile", "utilisation facile"),
        ("environ", "sensiblement égal"),
    ]
    for r in requirements:
        target_str = str(r.get("target") or r.get("name") or "").lower()
        num_val = float(r.get("numerical_val") or 0.0)
        if num_val == 0.0 or r.get("unit") == "spec":
            for term_family in vague_lexicon:
                for variant in term_family:
                    if re.search(r"\b" + re.escape(variant) + r"\b", target_str):
                        incose_alerts.append(
                            f"Règle INCOSE R-VAG : Le terme non mesurable '{variant}' a été détecté dans {r.get('id', 'l exigence')}. "
                            "Préciser une grandeur numérique cible avec unité de mesure."
                        )
                        break

    if not incose_alerts:
        prompt_lower = text.lower()
        for term_family in vague_lexicon[:4]:
            primary = term_family[0]
            if re.search(r"\b" + re.escape(primary) + r"\b", prompt_lower):
                incose_alerts.append(
                    f"Règle INCOSE R-VAG : Le terme '{primary}' présent dans l'expression du besoin est imprécis. "
                    "Préciser un seuil d'acceptation chiffré."
                )
    return incose_alerts[:4]


def _extract_rag_pointers(prompt: str) -> list[str]:
    """Identify secondary sections or annexes for targeted RAG retrieval without black holes (Livrable 2, p. 15)."""
    pointers: list[str] = []
    patterns = [
        (r"(?:annexe|appendice)\s+([A-Z0-9]+[^\n.:]{0,40})", "Annexe source"),
        (r"(?:protocole|procédure)\s+(?:d['’]essais?|[^\n.:]{3,35})", "Protocole d'essais"),
        (r"(?:norme|standard)\s+(?:iso|ieee|en|nf|ce)\s*([0-9\-]+)", "Référence normative"),
    ]
    for pattern, label in patterns:
        for match in re.finditer(pattern, prompt, re.IGNORECASE):
            matched_text = match.group(0).strip()
            if matched_text and len(matched_text) < 60:
                pointers.append(f"[{label}] {matched_text} (balisé pour consultation ciblée)")
    return pointers[:4]


def _extract_hybrid_text(prompt: str, resolved_name: str) -> tuple[str, str]:
    """Extract natural-language ConOps and qualitative operational context (Livrable 2, Choix 4).

    Preserves non-numeric context (environment, mission, qualitative constraints) that cannot
    be reduced to a rigid JSON table, so Agent 3 can populate SysML v2 `doc /* ... */` tags.
    """
    qualitative_kw = (
        "mission", "objectif", "contexte", "environnement", "désert", "poussière",
        "température", "chaleur", "froid", "pluie", "étanche", "norme", "iso",
        "fournisseur", "client", "terrain", "extérieur", "intérieur", "sécurité",
        "doit ", "opérer", "fonctionner",
    )
    prose_sentences: list[str] = []
    qualitative_sentences: list[str] = []
    for raw_line in prompt.splitlines():
        line = raw_line.strip().lstrip("-*•").strip()
        if not line or len(line) < 15:
            continue
        if re.match(r"^REQ-\d+\s*[:\-–]", line, re.IGNORECASE):
            continue
        # Skip pure component spec bullets (e.g. "Moteur : 2.5 kg, 120 W") unless they carry qualitative context
        has_qual = any(k in line.lower() for k in qualitative_kw)
        is_pure_comp = bool(_COMP_LINE_RE.match(raw_line)) and (_MASS_RE.search(line) or _POWER_RE.search(line))
        if is_pure_comp and not has_qual:
            continue
        prose_sentences.append(line)
        if has_qual:
            qualitative_sentences.append(line)

    conops = " ".join(prose_sentences[:3]).strip()
    if not conops:
        conops = f"Système {resolved_name} formalisé d'après le besoin exprimé."
    operational_context = " ".join(qualitative_sentences[:3]).strip()
    return conops[:500], operational_context[:500]


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None or val == "":
        return default
    try:
        return float(str(val).replace(",", "."))
    except (ValueError, TypeError):
        return default


def parse_cdc_to_input1(
    prompt: str,
    *,
    project_name: str | None = None,
    provider: LLMProvider | None = None,
    strict_llm: bool = False,
    override_gemini_key: str | None = None,
) -> dict[str, Any]:
    """Parse a raw engineering specification into a JCS-sealed INPUT 1 payload."""
    if override_gemini_key and provider is None:
        from sysmeasy.contracts.llm_provider import detect_env_llm_provider
        provider = detect_env_llm_provider(override_gemini_key=override_gemini_key)
    validate_cdc_payload(prompt)
    prompt = _isolate_specification_section(prompt)
    title_match = re.search(r'(?:Robot|Système|Projet|Projecteur|DataShow|Drone|Spécification)[^"\n]*?"([^"]+)"', prompt, re.IGNORECASE)
    if not title_match:
        title_match = re.search(r'"([^"]{2,40})"', prompt)
    resolved_name = project_name or (title_match.group(1).strip() if title_match else "CustomSystem")

    llm_data = _try_llm_extraction(prompt, provider, strict_llm=strict_llm)
    if llm_data is not None:
        resolved_name = project_name or str(llm_data.get("project_name") or resolved_name)
        comps = []
        for c in llm_data["components"]:
            lbl = str(c.get("label") or c.get("name") or "Subsystem")
            comps.append({
                "name": _slugify_part_name(lbl),
                "label": lbl,
                "category": str(c.get("category") or "part"),
                "mass_kg": _safe_float(c.get("mass_kg"), 0.0),
                "power_w": _safe_float(c.get("power_w"), 0.0),
                "ports": list(c.get("ports") or []),
            })
        reqs = [
            {
                "id": str(r.get("id") or f"REQ-{i:02d}"),
                "name": str(r.get("name") or "")[:60],
                "target": str(r.get("target") or "")[:180],
                "numerical_val": _safe_float(r.get("numerical_val"), 0.0),
                "unit": str(r.get("unit") or "spec"),
                "comparator": str(r.get("comparator") or "=="),
                "origin": "document",
                "span": None,
            }
            for i, r in enumerate(llm_data["requirements"], start=1)
        ]
        conns = [
            {
                "from": _slugify_part_name(str(cn.get("from") or "")),
                "to": _slugify_part_name(str(cn.get("to") or "")),
                "domain": str(cn.get("domain") or "electrical"),
                "label": str(cn.get("label") or ""),
            }
            for cn in (llm_data.get("connections") or [])
        ] or _infer_connections(comps)
        params = llm_data.get("physics_params") or {}
        incose_ambs = _detect_incose_vague_terms(prompt, reqs)
        rag_ptrs = _extract_rag_pointers(prompt)
        content = {
            "contract_id": f"CTR-{_slugify_part_name(resolved_name).upper()[:8]}-2026",
            "project_name": resolved_name,
            "conops": str(llm_data.get("conops") or ""),
            "operational_context": str(llm_data.get("operational_context") or ""),
            "version": "1.0",
            "parent_sha256": None,
            "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "physics_params": {
                "bus_voltage_v": _safe_float(params.get("bus_voltage_v"), 24.0),
                "battery_capacity_ah": _safe_float(params.get("battery_capacity_ah"), 20.0),
                "dod": _safe_float(params.get("dod"), 0.85),
            },
            "requirements": reqs,
            "components": comps,
            "connections": conns,
            "ambiguities": [str(a) for a in llm_data.get("ambiguities", [])] + incose_ambs,
            "rag_pointers": rag_ptrs,
        }
        return {
            "hash_scope": "content_only",
            "canonical_algorithm": "RFC8785_JCS",
            "content": content,
            "canonical_sha256": canonical_sha256(content),
        }

    requirements: list[dict[str, Any]] = []
    for req_id, desc in _REQ_LINE_RE.findall(prompt):
        num_val = 0.0
        unit = "unit"
        comp = "=="

        if m := _HOURS_RE.search(desc):
            num_val = round(_to_float(m.group(1)) * 60.0, 2)
            unit = "min"
            comp = ">=" if any(k in desc.lower() for k in ["min", "au moins", ">=", "≥"]) else "=="
        elif m := _MIN_RE.search(desc):
            num_val = _to_float(m.group(1))
            unit = "min"
            comp = ">=" if any(k in desc.lower() for k in ["min", ">=", "≥"]) else "=="
        elif m := _MASS_RE.search(desc):
            num_val = _to_float(m.group(1))
            unit = "kg"
            comp = "<=" if any(k in desc.lower() for k in ["max", "<=", "≤"]) else "=="
        elif m := _VOLT_RE.search(desc):
            num_val = _to_float(m.group(1))
            unit = "V"
            comp = "=="
        elif m := _SPEED_RE.search(desc):
            num_val = _to_float(m.group(1))
            unit = "m/s"
            comp = "=="

        requirements.append({
            "id": req_id,
            "name": desc.split("(")[0].strip()[:60],
            "target": desc.strip(),
            "numerical_val": num_val,
            "unit": unit,
            "comparator": comp,
            "origin": "document",
            "span": None,
        })

    bus_voltage_v = 24.0
    if mv := _VOLT_RE.search(prompt):
        bus_voltage_v = _to_float(mv.group(1))

    battery_ah = 20.0
    if mah := _AH_RE.search(prompt):
        battery_ah = _to_float(mah.group(1))
    elif mmah := _MAH_RE.search(prompt):
        battery_ah = round(float(re.sub(r"[\s\u00a0]+", "", mmah.group(1)).replace(",", ".")) / 1000.0, 3)
    elif mwh := _WH_RE.search(prompt):
        battery_ah = round(_to_float(mwh.group(1)) / max(bus_voltage_v, 1.0), 3)

    dod = 0.85
    if mdod := _DOD_RE.search(prompt):
        dod = round(_to_float(mdod.group(1)) / 100.0, 4)

    components: list[dict[str, Any]] = []
    for raw_label, specs in _COMP_LINE_RE.findall(prompt):
        clean_label = raw_label.replace("**", "").strip()
        if clean_label.upper().startswith("REQ-"):
            continue
        mass_matches = _MASS_RE.findall(specs)
        power_matches = _POWER_RE.findall(specs)
        is_editorial_or_limit = _is_non_component_clause(clean_label, specs)

        if not is_editorial_or_limit and not mass_matches and not power_matches and len(_REQ_LINE_RE.findall(prompt)) > 0:
            continue

        # Prefer trailing cumulative value (after '=' if present, e.g., "4 x 1.2 kg = 4.8 kg").
        mass_kg = _to_float(mass_matches[-1]) if mass_matches else 0.0
        power_w = _to_float(power_matches[-1]) if power_matches else 0.0

        if len(_REQ_LINE_RE.findall(prompt)) == 0:
            # Record every bulleted CDC section as a requirement with extracted numerical bounds.
            if mass_kg > 0:
                req_val, req_unit = mass_kg, "kg"
                req_comp = "<=" if any(k in specs.lower() for k in ["inférieur", "inferieur", "max", "mtow", "<=", "≤"]) else "=="
            elif power_w > 0:
                req_val, req_unit, req_comp = power_w, "W", "=="
            elif m_lm := _LM_RE.search(specs):
                req_val = float(re.sub(r"\s+", "", m_lm.group(1)))
                req_unit, req_comp = "lm", ">="
            elif m_db := _DB_RE.search(specs):
                req_val, req_unit, req_comp = _to_float(m_db.group(1)), "dB", "<="
            elif m_sec := _SEC_RE.search(specs):
                req_val, req_unit, req_comp = _to_float(m_sec.group(1)), "s", "<="
            else:
                req_val, req_unit, req_comp = 0.0, "spec", "=="

            requirements.append({
                "id": f"REQ-{len(requirements) + 1:02d}",
                "name": clean_label[:60],
                "target": specs.strip()[:180],
                "numerical_val": req_val,
                "unit": req_unit,
                "comparator": req_comp,
                "origin": "document",
                "span": None,
            })

            if req_unit != "min" and "autonomie" in specs.lower():
                if m_min := _MIN_RE.search(specs):
                    requirements.append({
                        "id": f"REQ-{len(requirements) + 1:02d}",
                        "name": f"{clean_label[:48]} (autonomie)",
                        "target": specs.strip()[:180],
                        "numerical_val": _to_float(m_min.group(1)),
                        "unit": "min",
                        "comparator": ">=",
                        "origin": "document",
                        "span": None,
                    })

        if is_editorial_or_limit:
            continue

        category, ports = _infer_ports_and_category(clean_label, specs)

        # Avoid creating a bogus active component with 0 W in M5 by typing it as "part" if power_w == 0.
        if power_w == 0.0 and category in {"actuator", "controller", "sensor"}:
            category = "part"

        components.append({
            "name": _slugify_part_name(clean_label),
            "label": clean_label,
            "category": category,
            "mass_kg": mass_kg,
            "power_w": power_w,
            "ports": ports,
        })

    # Fallback for prose-only specifications with no bulleted "Label : specs" lines
    if not components:
        components.append({
            "name": _slugify_part_name(resolved_name),
            "label": resolved_name,
            "category": "part",
            "mass_kg": 0.0,
            "power_w": 0.0,
            "ports": [],
        })
    if not requirements:
        clauses = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", prompt) if len(s.strip()) > 20]
        for idx, clause in enumerate(clauses[:6], start=1):
            requirements.append({
                "id": f"REQ-{idx:02d}",
                "name": clause[:60],
                "target": clause[:180],
                "numerical_val": 0.0,
                "unit": "spec",
                "comparator": "==",
                "origin": "document",
                "span": None,
            })

    is_ac_mains = any(k in prompt.lower() for k in ["secteur", "v ac", "50/60 hz", "100–240", "100-240"])
    ambiguities: list[str] = []
    if is_ac_mains:
        if sum(c["power_w"] for c in components) <= 15.0:
            ambiguities.append("Puissance électrique nominale globale (W) de la lampe/source non chiffrée pour le dimensionnement thermique.")
    else:
        if "câblage" in prompt.lower() and not any(
            c["power_w"] > 0 for c in components if "cabl" in c["name"].lower()
        ):
            ambiguities.append("Rendement de conversion / pertes câble non spécifiés (supposé 100 %).")
        if not _DOD_RE.search(prompt):
            ambiguities.append("Profondeur de décharge (DoD) absente : valeur par défaut 85 % appliquée.")
    if not any("réservoir" in c.get("label", "").lower() and "plein" in prompt.lower() for c in components):
        if "réservoir" in prompt.lower():
            ambiguities.append("Masse du réservoir donnée à vide uniquement : masse de liquide/charge utile manquante.")

    ambiguities += _detect_incose_vague_terms(prompt, requirements)
    rag_ptrs = _extract_rag_pointers(prompt)

    conops_text, op_context_text = _extract_hybrid_text(prompt, resolved_name)

    content = {
        "contract_id": f"CTR-{_slugify_part_name(resolved_name).upper()[:8]}-2026",
        "project_name": resolved_name,
        "conops": conops_text,
        "operational_context": op_context_text,
        "version": "1.0",
        "parent_sha256": None,
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "physics_params": {
            "bus_voltage_v": bus_voltage_v,
            "battery_capacity_ah": battery_ah,
            "dod": dod,
        },
        "requirements": requirements,
        "components": components,
        "connections": _infer_connections(components),
        "ambiguities": ambiguities,
        "rag_pointers": rag_ptrs,
    }
    return {
        "hash_scope": "content_only",
        "canonical_algorithm": "RFC8785_JCS",
        "content": content,
        "canonical_sha256": canonical_sha256(content),
    }
