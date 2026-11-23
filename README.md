# SysmEasy 🚀

### Plateforme d'Assistance à l'Ingénierie Système & Modélisation SysML v2

> **Projet métier — ENSAM de Meknès**  
> **Département :** Génie Industriel & Productique (GIA / DTSI)  
> **Auteures :** Samya Loukili & Kenza El Khaniri  
> **Supervision :** Mme Ibtissam El-Hassani & M. Damien Motte  

---

## 📌 Présentation du Projet

La transition vers l'ingénierie système basée sur les modèles (**MBSE — Model-Based Systems Engineering**) et l'adoption du standard **OMG SysML v2** constituent un enjeu majeur pour l'industrie moderne. Toutefois, un fossé important persiste entre :
1. **Les cahiers des charges textuels industriels** (souvent denses, ambigus ou incomplets).
2. **Les exigences de formalisation rigoureuse** requises par les compilateurs SysML v2 et les plateformes PLM.
3. **Les besoins opérationnels des équipes métier non spécialistes** (qualité, industrialisation, achats, gestion de projet) qui doivent comprendre, auditer et valider les modèles sans se perdre dans la syntaxe formelle.

**SysmEasy** est une plateforme web conçue pour automatiser l'analyse sémantique des spécifications textuelles, générer des modèles SysML v2 formellement valides, et fournir une interface de revue ergonomique adaptée à la fois aux ingénieurs système et aux collaborateurs de terrain.

---

## 🌟 Fonctionnalités Principales

### 1. Vue Double-Persona (Métier vs Expert)
* **Mode Métier (Simple) :** Traduit chaque règle, flux et bloc en français clair. L'employé accède à une fiche produit simplifiée, aux citations exactes du cahier des charges (`Page X, §Y`), et à une identification visuelle immédiate des **zones floues** et points d'arbitrage.
* **Mode Expert (SysML v2 & Invariants) :** Donne accès au code source SysML v2 complet (syntaxe normalisée OMG KerML), au journal d'exécution ANTLR, aux graphes de connaissances (KG), et à l'état de validation des 5 Invariants formels.

### 2. Moteur Déterministe des 5 Invariants Universels
Chaque architecture générée est soumise à une vérification mathématique rigoureuse :
* **INV-01 (Compatibilité des Domaines Physiques) :** $M_{\text{domaine}}(u, v) = 1$ (ex: électrique, mécanique, hydraulique, signal).
* **INV-02 (Directionnalité des Ports) :** $T_{\text{dir}}(\text{out} \to \text{in})$ garantit l'orientation correcte des liaisons.
* **INV-03 (Conformité des Item Flows & Unités SI) :** Validation dimensionnelle selon les standards internationaux.
* **INV-04 (Clôture Temporelle des Boucles) :** Présence obligatoire de conditions d'arrêt explicites dans les `loop actions`.
* **INV-05 (Clôture Topologique des Blocs) :** Détection des composants isolés et validation de leur statut (`INTENTIONALLY_STANDALONE` vs omission).

### 3. Revue Collaborative & Gestion des Arbitrages
* Validation en 1 clic (*« C'est exact »*, *« Modifier »*, *« Transférer aux Zones Floues »*).
* Distinction explicite entre ce qui provient du texte d'origine et ce qui relève d'une recommandation d'ingénierie (ex. plage thermique recommandée selon norme ISO).
* Suivi de l'avancement en temps réel avec barre de progression et filtres dynamiques.

### 4. Interopérabilité PLM Réaliste (Sandbox Standalone)
* Prise en charge des standards d'échange ouverts (**OMG Systems Modeling API & Services 1.0**, OSLC 3.0, JSON-LD).
* Export de packages formels prêts pour l'intégration dans **Dassault Systèmes 3DEXPERIENCE**, **PTC Windchill** ou **Siemens Teamcenter**.

### 5. Générateur de Rapports Exécutifs PDF
* Génération de synthèses professionnelles de 4 pages calibrées (Page de garde, Vue Système Niv. 0, Blocs IBD Niv. 1, Déroulement Niv. 2, Plan d'Actions & Arbitrages pour réunion).

---

## 🛠️ Architecture Technique

* **Backend :** Python 3.10+ / FastAPI (REST API asynchrone, validation Pydantic).
* **Moteur MBSE :** Moteur d'invariants formels déterministe (0-token, temps d'exécution < 1 ms).
* **Génération Graphique & PDF :** Matplotlib (diagrammes vectoriels normalisés), ReportLab (composition de documents A4).
* **Frontend :** Interface Single-Page réactive, Tailwind CSS, Lucide Icons, KaTeX pour le rendu des formules formelles.

---

## 📂 Structure du Répertoire

```text
SysmEasy/
├── server.py                   # Serveur d'API FastAPI et orchestration
├── mbse_universal_engine.py    # Moteur de vérification formelle (5 Invariants)
├── report_generator.py         # Moteur de génération des rapports PDF de synthèse
├── requirements.txt            # Dépendances Python
├── launch_interface.bat        # Script de démarrage rapide sous Windows
├── README.md                   # Documentation du projet
│
└── static/                     # Assets statiques et interface web
    ├── index.html              # Interface utilisateur (Double-Persona)
    ├── battery_ibd_rendered.png
    ├── diagram_action_flow.png
    ├── diagram_charging_system_overview.png
    ├── diagram_system_overview.png
    ├── sysml_ibd_official_rendered.png
    └── generated/              # Fichiers générés dynamiquement (JSON / PDF)
```

---

## 🚀 Installation & Démarrage

### 1. Cloner le dépôt
```bash
git clone https://github.com/samya818/SysmEasy.git
cd SysmEasy
```

### 2. Créer et activer un environnement virtuel
```bash
python -m venv venv
# Sous Windows :
venv\Scripts\activate
# Sous Linux / macOS :
source venv/bin/activate
```

### 3. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 4. Lancer la plateforme
```bash
python server.py
```
*Ou directement en double-cliquant sur `launch_interface.bat` sous Windows.*

L'interface est accessible à l'adresse : **[http://localhost:8000](http://localhost:8000)**.

---

## 🎓 Cadre Académique & Mentions

Ce projet s'inscrit dans le cadre du **Projet Métier ** pour l'obtention du Diplôme d'Ingénieur d'État à l'**École Nationale Supérieure d'Arts et Métiers (ENSAM) de Meknès**.

Nous tenons à exprimer notre profonde gratitude envers nos encadrants, **Mme Ibtissam El-Hassani** et **M. Damien Motte**, pour leur accompagnement scientifique, leurs conseils avisés et leur soutien tout au long de la réalisation de ce travail.
