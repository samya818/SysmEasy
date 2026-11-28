"""Local deterministic KerML / SysML v2 syntactic validator (Agent 4)."""

from __future__ import annotations

import re
from dataclasses import dataclass

import antlr4  # noqa: F401 - verifies ANTLR4 runtime availability


@dataclass(frozen=True)
class SyntaxDiagnostic:
    """Single syntactic error location and message."""

    line: int
    message: str


_BLOCK_HEADER_RE = re.compile(
    r"^(package|requirement\s+def|part\s+def|port\s+def|action\s+def|constraint\s+def|state\s+def)\s+"
)
_STATEMENT_RE = re.compile(
    r"^(doc\s+/\*.*\*/|private\s+import\s+|attribute\s+|part\s+|(in|out|inout)\s+port\s+|port\s+def\s+|satisfy\s+|connect\s+|state\s+|transition\s+|require\s+constraint\s+)"
)


def _strip_comments(line: str, in_block_comment: bool) -> tuple[str, bool]:
    text = line
    if in_block_comment:
        end_idx = text.find("*/")
        if end_idx == -1:
            return "", True
        text = text[end_idx + 2 :]
        in_block_comment = False

    while "/*" in text:
        start_idx = text.find("/*")
        end_idx = text.find("*/", start_idx + 2)
        if end_idx == -1:
            text = text[:start_idx]
            in_block_comment = True
            break
        text = text[:start_idx] + " " + text[end_idx + 2 :]

    if "//" in text:
        text = text[: text.find("//")]
    return text.strip(), in_block_comment


def check_sysml_syntax(source: str) -> tuple[bool, list[str]]:
    """Validate SysML v2 / KerML block nesting, headers, and statement terminators."""
    if not source.strip():
        return False, ["Line 1: Empty SysML v2 source"]

    diagnostics: list[SyntaxDiagnostic] = []
    brace_depth = 0
    in_comment = False
    has_package = False

    for lineno, raw_line in enumerate(source.splitlines(), start=1):
        # Preserve `doc /* ... */` on a single line before stripping comments.
        stripped_raw = raw_line.strip()
        if stripped_raw.startswith("doc /*") and stripped_raw.endswith("*/"):
            continue

        line, in_comment = _strip_comments(raw_line, in_comment)
        if not line:
            continue

        open_count = line.count("{")
        close_count = line.count("}")
        brace_depth += open_count - close_count

        if brace_depth < 0:
            diagnostics.append(SyntaxDiagnostic(lineno, "Unexpected closing brace '}'"))
            brace_depth = 0
            continue

        if line == "}":
            continue

        if open_count > 0:
            if line.startswith("package "):
                has_package = True
            elif not _BLOCK_HEADER_RE.match(line):
                diagnostics.append(
                    SyntaxDiagnostic(lineno, f"Invalid block declaration: '{line}'")
                )
            continue

        if not line.endswith(";"):
            diagnostics.append(
                SyntaxDiagnostic(lineno, f"Missing semicolon ';' at end of statement: '{line}'")
            )
            continue

        if not _STATEMENT_RE.match(line):
            diagnostics.append(
                SyntaxDiagnostic(lineno, f"Unrecognized SysML v2 statement: '{line}'")
            )

    if in_comment:
        diagnostics.append(SyntaxDiagnostic(len(source.splitlines()), "Unterminated block comment"))
    if brace_depth != 0:
        diagnostics.append(
            SyntaxDiagnostic(len(source.splitlines()), f"Unclosed braces (depth={brace_depth})")
        )
    if not has_package:
        diagnostics.append(SyntaxDiagnostic(1, "Missing root 'package' declaration"))

    return len(diagnostics) == 0, [f"Line {d.line}: {d.message}" for d in diagnostics]
