# SysmEasy

AI-driven pipeline for generating and evolving SysML v2 models from natural-language specifications.

**ENSAM Meknès — IATD 4th year — 2026**  
*Samya Loukili & Kenza El Khaniri*

---

## Overview

SysmEasy transforms a structured natural-language specification (INPUT 1) into a formally verified SysML v2 model through an eight-stage pipeline:

1. **A1** — PDF extraction (PyMuPDF)
2. **A2** — Requirement elicitation and COTS lookup
3. **A3** — SysML v2 code generation (Jinja2 + LLM repair)
4. **A4** — Syntactic validation (ANTLR4 grammar)
5. **M5** — Physics and mass budget calculation (Python + Z3)
6. **A6a** — Formal oracle (Z3 SMT)
7. **A6b** — Cognitive review (ISO 29148 conformance via LLM)
8. **A7** — Orchestrator and audit chain (RFC 8785 / JCS)

Decision records (DEC-01, DEC-02) and all intermediate outputs are sealed with JCS-canonical SHA-256 hashes, forming a linear Merkle audit chain.

---

## Repository layout

```
sysmeasy/
├── sysmeasy/
│   ├── extraction/       # A1 — PDF and text ingestion
│   ├── elicitation/      # A2 — NL requirement → INPUT 1 contract (JCS RFC 8785)
│   ├── generation/       # A3 — SysML v2 modeling & active LLM repair loop
│   ├── validation/       # A4 — Fast ANTLR4 syntax checker (< 50ms)
│   ├── verification/     # A5 — Consultative physics balance (mass, power, autonomy)
│   ├── review/           # A6 — Semantic satisfaction recall (>=95%) & cognitive review
│   ├── orchestrator/     # A7 — Two-level memory & lucid stopping orchestrator
│   ├── methodology/      # MagicGrid, HarmonySE, ARCADIA diagram selector & ELK layout
│   └── contracts/        # Pydantic schemas, JCS seal & fast LLM providers
├── examples/             # Reference payloads & specifications
├── tests/                # Automated test suite (52+ passing unit & integration tests)
├── static/               # Web application assets
├── templates/            # SysML v2 Jinja2 reference templates
├── server.py             # FastAPI web application server
└── pyproject.toml
```

---

## Quick start

```bash
# Install in editable mode (Python 3.11+)
pip install -e ".[dev]"

# Optional (recommended): install ELK (elkjs) for collision-free SysML diagram layouts (Node.js 18+)
npm install --prefix elk_layout

# Run the full test suite
pytest tests/ -v

# Verify audit chain integrity
python scripts/verify_audit_chain.py

# Start the web interface
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

### Gemini API Key Configuration

Each user must provide their own Gemini API key (`.env` is excluded from Git):
- **Via the web UI**: open `http://127.0.0.1:8000`, click the **Clé API Gemini** button in the right sidebar, paste your key, and save.
- **Via `.env`**: create a `.env` file at the project root containing `GEMINI_API_KEY=your_key_here`.

---

## Tests

| Test file | What it covers |
|---|---|
| `test_rfc8785_conformance.py` | JCS canonical serialization against RFC 8785 Appendix vectors |
| `test_input1_hash.py` | INPUT 1 v1.0 and v1.1 deterministic hash values |
| `test_physics_sensitivity.py` | 340 W budget, DoD sweep, autonomy ≥ 90 min |
| `test_physics_vs_llm.py` | M5 catches arithmetic errors the LLM would propagate |
| `test_matrix_m5_causal_chain.py` | MUT-17 formal rejection by Z3 causal chain |
| `test_reproducibility.py` | Deterministic re-hash and v1.0→v1.1 chain integrity |

All tests must pass before any merge to `main`.

---

## Reference hashes (INPUT 1 — Rover use case)

| Artifact | JCS SHA-256 |
|---|---|
| `rover_v1.0.input1.json` | `1c8d8832059300e063a676c9b8b9475fca923d1ccee7527ec368f051afc43871` |
| `rover_v1.1.input1.json` | `9157a8d34a07a958fd822f97b25254beeb1aaa69ac529792bbcf68cf557cb22c` |
| `rover_audit_trace.json` | trace\_sha256 `051f71f567bab710ededdd6efda5974e8273b689c1413905f13c7f1ae29a4296` |

These values are asserted in the test suite and must not change.
