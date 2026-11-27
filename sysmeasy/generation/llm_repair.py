"""LLM-driven SysML v2 repair loop and semantic completion (Agent 3 & Agent 4 & Agent 6).

Implements the Livrable 2 design choices:
- Choice 1 & Role Agent 3/4: Fast ANTLR4 syntax repair loop (< 50ms parser feedback)
- TTool-AI (p. 6): Clean context reset on repair to prevent error-cascading
- Choice 10 (p. 12): Semantic satisfaction completion cycle with proof by REQ-ID
- Choice 8 (p. 11): Lucid stop after max 2 attempts to avoid infinite loops
"""

from __future__ import annotations

import re
from typing import Callable, Mapping, Any
from sysmeasy.contracts.llm_provider import LLMProvider


def clean_sysml_fences(content: str) -> str:
    """Strip markdown code fences and extraneous text returned by LLMs."""
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def repair_sysml_syntax(
    code: str,
    diagnostics: list[str],
    provider: LLMProvider,
    *,
    rules_memo: list[str] | None = None,
) -> str:
    """Repair SysML v2 syntax using an isolated clean-context prompt (TTool-AI reset)."""
    memo_text = ""
    if rules_memo:
        memo_text = "\nRègles de modélisation durables (Mémoire Orchestrateur) :\n" + "\n".join(f"- {r}" for r in rules_memo)

    system_prompt = (
        "Tu es l'Agent 3 (Architecte SysML v2). Ta tâche est de corriger les erreurs de syntaxe SysML v2 "
        "signalées par le compilateur ANTLR (Agent 4). Ne modifie pas la sémantique ni les noms de blocs.\n"
        "Règles strictes :\n"
        "1. Respecte la grammaire OMG SysML v2 (accolades appariées, points-virgules en fin d'attributs/satisfy).\n"
        "2. Conserve les 'part def', 'requirement def', 'port' in/out et 'satisfy'.\n"
        "3. Réponds UNIQUEMENT avec le code SysML v2 brut, sans explications, sans balises markdown."
        f"{memo_text}"
    )

    diagnostics_formatted = "\n".join(f"- {d}" for d in diagnostics[:8])
    user_prompt = (
        f"Voici le code SysML v2 comportant des erreurs de syntaxe :\n\n"
        f"```sysml\n{code}\n```\n\n"
        f"Diagnostics d'erreurs retournés par ANTLR4 :\n"
        f"{diagnostics_formatted}\n\n"
        f"Corrige le code pour qu'il soit syntaxiquement valide."
    )

    resp = provider.complete(system_prompt, user_prompt, temperature=0.0)
    repaired = clean_sysml_fences(resp.content)
    if len(repaired) < 50 or "package" not in repaired:
        return code
    return repaired


def make_llm_repair_fn(
    provider: LLMProvider,
    *,
    rules_memo: list[str] | None = None,
) -> Callable[[str, list[str]], str]:
    """Create a repair callback compatible with generate_with_repair."""
    def _repair(code: str, diagnostics: list[str]) -> str:
        return repair_sysml_syntax(code, diagnostics, provider, rules_memo=rules_memo)
    return _repair


def complete_sysml_satisfaction(
    sysml_code: str,
    missing_req_ids: list[str],
    root_name: str,
) -> str:
    """Deterministically inject missing satisfy links into the root assembly block (Choice 10, p. 12)."""
    if not missing_req_ids:
        return sysml_code

    new_satisfy_lines = [f"        satisfy '{req_id}' by {root_name};" for req_id in missing_req_ids]
    insert_block = "\n".join(new_satisfy_lines)

    root_pattern = re.compile(rf"(part\s+def\s+{re.escape(root_name)}\s*\{{[^}}]*?)(\s*\}})", re.DOTALL)
    match = root_pattern.search(sysml_code)
    if match:
        body = match.group(1).rstrip()
        closing = match.group(2)
        replacement = f"{body}\n{insert_block}\n    {closing.strip()}"
        return sysml_code[:match.start()] + replacement + sysml_code[match.end():]

    last_brace_idx = sysml_code.rfind("}")
    if last_brace_idx != -1:
        prefix = sysml_code[:last_brace_idx].rstrip()
        return f"{prefix}\n    // Complétion sémantique Agent 6 -> Agent 3 (Livrable 2)\n{insert_block}\n}}\n"

    return sysml_code
