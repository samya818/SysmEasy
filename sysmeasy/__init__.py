"""SysmEasy — AI pipeline for SysML v2 model generation and verification.

Package structure
-----------------
extraction   : A1 — PDF to structured specification dict (PyMuPDF)
elicitation  : A2 — NL requirement elicitation and COTS lookup
generation   : A3 — SysML v2 code generation (Jinja2 + LLM repair)
validation   : A4 — Syntactic validation (ANTLR4)
verification : M5 physics calculator + A6a Z3 formal oracle
review       : A6b ISO 29148 cognitive review
orchestrator : A7 pipeline runner and RFC 8785 audit chain
contracts    : Pydantic schemas for INPUT 1 and INPUT 2
"""

__version__ = "2.5.0"
