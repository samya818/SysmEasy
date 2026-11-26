"""Jinja2 SysML v2 model generator and hybrid repair loop (Agent 3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError


class ModelingError(RuntimeError):
    """Error raised during SysML v2 template rendering or repair."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"[{code}] {message}")


DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


def render_sysml_from_input1(
    input1_payload: Mapping[str, Any],
    *,
    template_name: str = "rover_system.sysml.j2",
    template_dir: Optional[Path] = None,
) -> str:
    """Render a SysML v2 textual model from a sealed INPUT 1 envelope or content dict."""
    content = input1_payload.get("content", input1_payload)
    tpl_dir = template_dir or DEFAULT_TEMPLATE_DIR

    if not (tpl_dir / template_name).is_file():
        raise ModelingError("E-11", f"Template not found: {tpl_dir / template_name}")

    env = Environment(
        loader=FileSystemLoader(str(tpl_dir)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    try:
        template = env.get_template(template_name)
        return template.render(content=content).strip() + "\n"
    except TemplateError as exc:
        raise ModelingError("E-11", f"Template rendering failed: {exc}") from exc


def generate_with_repair(
    input1_payload: Mapping[str, Any],
    validator_fn: Callable[[str], tuple[bool, list[str]]],
    repair_fn: Optional[Callable[[str, list[str]], str]] = None,
    *,
    max_attempts: int = 3,
    template_name: str = "rover_system.sysml.j2",
) -> tuple[str, int]:
    """Generate SysML v2 code and optionally invoke a repair callback on syntax errors."""
    code = render_sysml_from_input1(input1_payload, template_name=template_name)
    for attempt in range(1, max_attempts + 1):
        ok, diagnostics = validator_fn(code)
        if ok:
            return code, attempt
        if repair_fn is None or attempt == max_attempts:
            raise ModelingError("E-03", "; ".join(diagnostics))
        code = repair_fn(code, diagnostics)
    raise ModelingError("E-03", "Unreachable repair state")
