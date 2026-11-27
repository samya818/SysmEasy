"""Tests for Agent 3 Jinja2 generation and Agent 4 SysML v2 syntax checker."""

import json
from pathlib import Path

import pytest

from sysmeasy.generation.modeling_agent import (
    ModelingError,
    generate_with_repair,
    render_sysml_from_input1,
)
from sysmeasy.validation.antlr_compiler import check_sysml_syntax


def _load_rover_v10() -> dict:
    root = Path(__file__).resolve().parent.parent
    return json.loads((root / "examples" / "rover_v1.0.input1.json").read_text(encoding="utf-8"))


def test_render_and_compile_rover_v10():
    payload = _load_rover_v10()
    sysml_code, attempts = generate_with_repair(payload, check_sysml_syntax)
    assert attempts == 1
    assert "package 'Rover Tout-Terrain'" in sysml_code
    assert "part def LidarSensor" in sysml_code
    assert "attribute power_w : Real = 15.0;" in sysml_code

    ok, errors = check_sysml_syntax(sysml_code)
    assert ok is True
    assert errors == []


def test_compiler_rejects_injected_syntax_errors():
    payload = _load_rover_v10()
    valid_code = render_sysml_from_input1(payload)

    broken_semicolon = valid_code.replace("attribute power_w : Real = 15.0;", "attribute power_w : Real = 15.0")
    ok, errors = check_sysml_syntax(broken_semicolon)
    assert ok is False
    assert any("semicolon" in err.lower() for err in errors)

    broken_brace = valid_code[:-2]
    ok2, errors2 = check_sysml_syntax(broken_brace)
    assert ok2 is False
    assert any("unclosed braces" in err.lower() for err in errors2)


def test_repair_loop_recovers_from_syntax_fault():
    payload = _load_rover_v10()

    def broken_validator(code: str) -> tuple[bool, list[str]]:
        if "REPAIRED" not in code:
            return False, ["Line 1: simulated error"]
        return check_sysml_syntax(code.replace("// REPAIRED\n", ""))

    def repair(code: str, _diags: list[str]) -> str:
        return "// REPAIRED\n" + code

    fixed_code, attempts = generate_with_repair(payload, broken_validator, repair_fn=repair)
    assert attempts == 2
    assert fixed_code.startswith("// REPAIRED\n")


def test_missing_template_raises_e11():
    payload = _load_rover_v10()
    with pytest.raises(ModelingError) as exc_info:
        render_sysml_from_input1(payload, template_name="nonexistent.sysml.j2")
    assert exc_info.value.code == "E-11"
