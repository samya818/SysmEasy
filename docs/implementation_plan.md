# Plan d'Implémentation & Organisation Git — SysmEasy V2

**Projet d'Ingénierie Système de 4e année (IATD) — ENSAM Meknès**  
**Dépôt cible :** `https://github.com/samya818/SysmEasy`  
**Échéance P0 :** Soutenance intermédiaire du 11 décembre 2026  

---

## 1. Principes Directeurs : Un Dépôt Sobre et Crédible

L'objectif de ce plan est de restructurer le dossier de travail actuel en un dépôt Git propre, modulaire et vérifiable, reflétant une démarche rigoureuse d'élèves-ingénieures :

1. **Séparation stricte code / brouillons / datasets :** Aucun fichier temporaire (`bruillon*`, `test_layout.png`, `preview_architecture.png`, `extracted_bruillon_2.txt`), aucune archive `.zip`, aucun corpus brut (`SysMBench_Dataset/`, `articles/`) et aucun PDF lourd compilé ne doivent polluer l'historique Git.
2. **Code sobre et testable :**
   * Pas de journaux ou `print` décoratifs, pas de commentaires qui paraphrasent l'instruction suivante.
   * Pas de valeurs métier codées en dur (tous les paramètres viennent d'`INPUT 1` ou de fichiers de configuration).
   * Typage explicite (`typing`, `Protocol`, `dataclass`) et fonctions courtes à responsabilité unique.
3. **Historique Git réaliste et atomique :**
   * Travail par branches courtes (`chore/*`, `feat/*`, `docs/*`) mergées dans `dev`, puis dans `main` une fois les tests verts.
   * Messages au format *Conventional Commits* courts et factuels (ex. `fix(physics): include 15W lidar load in rover budget`, `test(jcs): verify RFC 8785 canonical hash`), sans emojis ni descriptions fleuves.

---

## 2. Arborescence Cible du Dépôt

Cette arborescence aligne le code réel sur le diagramme de paquetages `PKG-01` de la spécification :

```text
SysmEasy/
├── .gitignore
├── pyproject.toml                  # Dépendances figées (jcs, z3-solver, antlr4, pymupdf, fastapi)
├── README.md                       # Présentation sobre : objectif, installation, commandes de test
├── docs/
│   ├── architecture_sysml_v2_master.md
│   └── schema/
│       ├── INPUT1_content.schema.json
│       └── INPUT1_sealed.schema.json
├── sysmeasy/                       # Package Python principal
│   ├── __init__.py
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── pdf_extractor.py        # Agent 1 : extraction PyMuPDF + vérification page.rotation == 0
│   │   └── spatial_chunker.py      # Découpage <= 200 mots + assertion NFKC
│   ├── core/
│   │   ├── __init__.py
│   │   ├── llm_provider.py         # Interface Protocol LLMProvider (Anthropic, OpenAI, vLLM)
│   │   ├── rag_orchestrator.py     # Dual-RAG ChromaDB (CDC + Méthode, all-MiniLM-L6-v2)
│   │   ├── investigation_agent.py  # Agent 2 : Guichet unique + scellement RFC 8785 (jcs)
│   │   ├── modeling_agent.py       # Agent 3 : Gabarits Jinja2 + réparation (reset / patch)
│   │   └── orchestrator.py         # Agent 7 : Machine à états, table de vérité, codes E-01..E-06
│   ├── verification/
│   │   ├── __init__.py
│   │   ├── antlr_compiler.py       # Agent 4 : Parseur KerML ANTLR4 réel
│   │   ├── physics_calculator.py   # Module 5 : Python + Z3 (bilans masse, puissance, autonomie)
│   │   ├── formal_oracle.py        # Agent 6a : Table de symboles, M1-M6, chaîne causale M5
│   │   ├── cognitive_oracle.py     # Agent 6b : Digest AST + classification ISO/IEC/IEEE 29148
│   │   └── mutation_engine.py      # Banc de mutation (15 calibration + 15 hold-out)
│   ├── reporting/
│   │   ├── __init__.py
│   │   ├── audit_logger.py         # Chaîne de hachage linéaire (audit_trace.json)
│   │   ├── report_generator.py     # Génération rapport PDF ReportLab
│   │   └── plm_exporter.py         # Export SysML v2 REST + mapping OSLC RM
│   └── web/
│       ├── __init__.py
│       ├── server.py               # API FastAPI (migrée depuis interface_agentic_sysml)
│       └── static/                 # Interface HTML/JS/CSS épurée
├── templates/                      # Gabarits Jinja2 (.sysml.j2)
├── examples/
│   ├── rover_v1.0.input1.json      # Scellé RFC 8785 (1c8d8832...)
│   ├── rover_v1.1.input1.json      # Avenant chaîné (9157a8d3...)
│   ├── rover_v1.0.sysml            # Modèle KerML validé
│   └── rover_audit_trace.json      # Trace linéaire vérifiable (051f71f5...)
├── experiments/
│   ├── scenario_selection.md       # 25 éval + 5 validation aveugle SysMBench
│   └── run_4way_benchmark.py       # Script d'évaluation Configs A/B/C/D
├── scripts/
│   └── verify_audit_chain.py       # Vérificateur autonome de la chaîne d'audit
└── tests/
    ├── test_rfc8785_conformance.py
    ├── test_input1_hash.py
    ├── test_span_integrity.py
    ├── test_antlr_compiler.py
    ├── test_physics_sensitivity.py
    ├── test_physics_vs_llm.py
    ├── test_matrix_m5_causal_chain.py
    ├── test_double_oracle_independence.py
    └── test_reproducibility.py
```

---

## 3. Configuration `.gitignore` Recommandée

À placer à la racine avant le premier commit de restructuration :

```gitignore
# Environnements et caches Python
__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/
*.egg-info/
dist/
build/

# Secrets et variables locales
.env
.env.*

# Données lourdes, corpus et brouillons locaux
SysMBench_Dataset/
articles/
des references pour le rag/
livrable_2_latex/
*.pdf
*.zip
*.png
*.jpg
chch.txt
extracted_bruillon_2.txt
make_preview.py
generate_clean_diagram.py

# Bases vectorielles et sorties générées à chaud
chroma_db/
results/*.json
!examples/*.json
```

---

## 4. Stratégie de Branches Git

Le workflow suit un modèle à deux branches permanentes (`main`, `dev`) et des branches thématiques courtes :

```text
main (stable, tag v2.5-soutenance)
  ▲
  └── dev (intégration continue)
        ├── chore/repo-structure
        ├── feat/contracts-jcs
        ├── feat/ingestion-spatial
        ├── feat/physics-z3
        ├── feat/kerml-compiler
        ├── feat/oracle-m1-m6
        ├── feat/audit-orchestrator
        ├── feat/web-and-reporting
        ├── feat/mutation-bench
        └── docs/architecture-spec
```

### Commandes de base pour chaque branche :
```bash
git checkout dev
git pull origin dev
git checkout -b feat/<nom-branche>
# ... développement + tests ...
pytest tests/
git add <fichiers_cibles>
git commit -m "type(scope): description courte"
git checkout dev
git merge --no-ff feat/<nom-branche>
git branch -d feat/<nom-branche>
```

---

## 5. Plan d'Implémentation Détaillé par Branche (10 Étapes)

### Étape 1 — `chore/repo-structure` (Priorité P0)
* **Objectif :** Poser les bases propres du dépôt sans casser l'existant.
* **Fichiers :** `.gitignore`, `pyproject.toml`, `README.md`, création des dossiers `sysmeasy/*`, `templates/`, `docs/schema/`.
* **Commits suggérés :**
  * `chore: initialize package layout and gitignore`
  * `build: pin core dependencies in pyproject.toml`
  * `docs: write concise project README with test instructions`
* **Critère de merge :** `pip install -e .` réussit et `git status` n'affiche aucun fichier temporaire.

### Étape 2 — `feat/contracts-jcs` (Priorité P0 — Déjà amorcée)
* **Objectif :** Figer les schémas JSON `INPUT 1` et le hachage strict RFC 8785 (`jcs`).
* **Fichiers :** `docs/schema/INPUT1_content.schema.json`, `docs/schema/INPUT1_sealed.schema.json`, `examples/rover_v1.0.input1.json`, `examples/rover_v1.1.input1.json`, `tests/test_rfc8785_conformance.py`, `tests/test_input1_hash.py`.
* **Commits suggérés :**
  * `feat(contracts): add INPUT 1 content and sealed JSON schemas`
  * `test(jcs): add RFC 8785 conformance and rover hash chain tests`
* **Critère de merge :** `pytest tests/test_rfc8785_conformance.py tests/test_input1_hash.py` passe à 100 %.

### Étape 3 — `feat/ingestion-spatial` (Priorité P0)
* **Objectif :** Implémenter l'Agent 1 déterministe avec `PyMuPDF`, contrôle de rotation et normalisation NFKC.
* **Fichiers :** `sysmeasy/ingestion/pdf_extractor.py`, `sysmeasy/ingestion/spatial_chunker.py`, `tests/test_span_integrity.py`.
* **Commits suggérés :**
  * `feat(ingestion): extract text spans with 0-indexed page_idx and bbox`
  * `feat(ingestion): enforce 200-word sentence chunking and NFKC validation`
  * `test(ingestion): cover hyphenation, ligatures and soft hyphens`
* **Critère de merge :** Les citations avec césures/ligatures et les pages tournées (`E-02`) sont correctement gérées.

### Étape 4 — `feat/physics-z3` (Priorité P0 — Déjà amorcée)
* **Objectif :** Implémenter le Module Déterministe 5 (Python + Z3) avec bilan 340 W et émission de `SOFT_WARNING`.
* **Fichiers :** `sysmeasy/verification/physics_calculator.py`, `tests/test_physics_sensitivity.py`, `tests/test_physics_vs_llm.py`.
* **Commits suggérés :**
  * `feat(physics): implement deterministic mass, power and autonomy solver`
  * `test(physics): verify 340W rover budget, DoD sensitivity and LLM drift catch`
* **Critère de merge :** `test_physics_sensitivity.py` et `test_physics_vs_llm.py` passent.

### Étape 5 — `feat/kerml-compiler` (Priorité P0)
* **Objectif :** Connecter le parseur ANTLR4 KerML réel (Agent 4) et la génération par gabarits Jinja2 (Agent 3).
* **Fichiers :** `sysmeasy/verification/antlr_compiler.py`, `sysmeasy/core/modeling_agent.py`, `templates/rover_system.sysml.j2`, `examples/rover_v1.0.sysml`, `tests/test_antlr_compiler.py`.
* **Commits suggérés :**
  * `feat(compiler): integrate ANTLR4 KerML parser for local syntax checks`
  * `feat(modeling): add Jinja2 generator and hybrid repair loop`
  * `test(compiler): validate rover v1.0 KerML model and syntax error detection`
* **Critère de merge :** `examples/rover_v1.0.sysml` compile sans erreur et les fautes syntaxiques injectées sont rejetées.

### Étape 6 — `feat/oracle-m1-m6` (Priorité P0)
* **Objectif :** Séparer opérationnellement l'Agent 6a (formel local : symboles, M1-M5 avec chaîne causale, M6 Z3) et l'Agent 6b (cognitif ISO 29148 via `LLMProvider`).
* **Fichiers :** `sysmeasy/core/llm_provider.py`, `sysmeasy/verification/formal_oracle.py`, `sysmeasy/verification/cognitive_oracle.py`, `tests/test_matrix_m5_causal_chain.py`, `tests/test_double_oracle_independence.py`.
* **Commits suggérés :**
  * `feat(llm): define LLMProvider protocol and provider adapters`
  * `feat(oracle): implement formal matrices M1-M6 with M5 causal chain`
  * `feat(oracle): add isolated ISO 29148 semantic classifier`
* **Critère de merge :** `MUT-17` est rejeté par `test_matrix_m5_causal_chain.py` et l'isolation réseau de 6a est testée.

### Étape 7 — `feat/audit-orchestrator` (Priorité P0)
* **Objectif :** Implémenter l'Agent 7 (machine à états, table de vérité booléenne, codes `E-01`..`E-06`), la chaîne linéaire d'audit et le delta d'évolution v1.0 $\rightarrow$ v1.1.
* **Fichiers :** `sysmeasy/core/investigation_agent.py`, `sysmeasy/core/orchestrator.py`, `sysmeasy/reporting/audit_logger.py`, `scripts/verify_audit_chain.py`, `examples/rover_audit_trace.json`, `tests/test_reproducibility.py`.
* **Commits suggérés :**
  * `feat(core): add Agent 2 single-window handler and re-sealing flow`
  * `feat(audit): implement linear hash chain logger and CLI verifier`
  * `feat(core): wire Agent 7 orchestrator, truth table and error routing`
* **Critère de merge :** `python scripts/verify_audit_chain.py` et `pytest tests/test_reproducibility.py` passent.

### Étape 8 — `feat/web-and-reporting` (Priorité P0 / P1)
* **Objectif :** Migrer proprement l'existant de `interface_agentic_sysml/` vers `sysmeasy/web/` et `sysmeasy/reporting/` en supprimant tout code factice hérité de la V1.
* **Fichiers :** `sysmeasy/web/server.py`, `sysmeasy/web/static/`, `sysmeasy/reporting/report_generator.py`, `sysmeasy/reporting/plm_exporter.py`.
* **Commits suggérés :**
  * `refactor(web): migrate FastAPI server and static UI into sysmeasy.web`
  * `feat(reporting): connect PDF synthesis report to real audit trace`
  * `feat(plm): add SysML v2 REST payload and OSLC RM mapper`
* **Critère de merge :** L'API démarre (`uvicorn sysmeasy.web.server:app`) et les endpoints de génération/export répondent sans valeurs codées en dur.

### Étape 9 — `feat/mutation-bench` (Priorité P0 CLI / P1 CI & RAG)
* **Objectif :** Finaliser le banc de mutation (15 calibration + 15 hold-out), le Dual-RAG (`rag_orchestrator.py`) et le script de benchmark SysMBench (30 scénarios).
* **Fichiers :** `sysmeasy/verification/mutation_engine.py`, `sysmeasy/core/rag_orchestrator.py`, `experiments/scenario_selection.md`, `experiments/run_4way_benchmark.py`.
* **Commits suggérés :**
  * `feat(rag): implement Dual-RAG orchestrator with ChromaDB metadata filters`
  * `feat(mutation): add 15 calibration and 15 hold-out mutation suite`
  * `exp(bench): add 4-way SysMBench evaluation runner`
* **Critère de merge :** $MS_{15} = 100\,\%$ et $MS_{\text{HO15}} \ge 75\,\%$ avec 0 faux positif sur modèles sains.

### Étape 10 — `docs/architecture-spec` & Release Soutenance
* **Objectif :** Publier la documentation consolidée dans `docs/`, merger `dev` dans `main`, et poser un tag propre pour la soutenance du 11/12/2026.
* **Actions :**
  * Copier `architecture_sysml_v2_master.md` dans `docs/architecture_sysml_v2_master.md`.
  * Vérifier que toute la suite `pytest` passe sur `main`.
  * Créer le tag : `git tag -a v2.5-soutenance -m "Architecture and P0 core for 11/12 defense"`.
  * Attacher `architecture_sysml_v2_master.pdf` en pièce jointe de la **GitHub Release** `v2.5-soutenance` (sans le commiter dans Git).

---

## 6. Checklist Finale Avant `git push`

- [ ] Aucun fichier PDF, `.zip`, `.png` de debug ou brouillon suivi par Git (`git ls-files`).
- [ ] Aucune clé API (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) présente dans le code ou l'historique.
- [ ] Tous les tests unitaires (`tests/*.py`) et `scripts/verify_audit_chain.py` passent en une seule commande `pytest`.
- [ ] Le `README.md` est sobre, exact, et ne contient que des commandes et chemins réellement présents dans le dépôt.
- [ ] L'historique `git log --oneline --graph` montre une progression logique par branches, sans commit monolithique suspect.
