"""
Générateur de Rapport Exécutif PDF — Style V1 Minimaliste
Projet : SysmEasy — ENSAM Meknès (S. Loukili & K. El Khaniri)
"""

import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("T", parent=base["Heading1"], fontSize=17, leading=21, textColor=colors.HexColor("#1E3A8A"), fontName="Helvetica-Bold"),
        "sub": ParagraphStyle("S", parent=base["Normal"], fontSize=9.5, leading=13, textColor=colors.HexColor("#475569"), fontName="Helvetica-Oblique"),
        "h2": ParagraphStyle("H2", parent=base["Heading2"], fontSize=12.5, leading=16, textColor=colors.HexColor("#0F172A"), fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=6),
        "body": ParagraphStyle("B", parent=base["Normal"], fontSize=9.5, leading=13.5, textColor=colors.HexColor("#334155"), fontName="Helvetica"),
        "bold": ParagraphStyle("BB", parent=base["Normal"], fontSize=9.5, leading=13.5, textColor=colors.HexColor("#0F172A"), fontName="Helvetica-Bold"),
        "note": ParagraphStyle("N", parent=base["Normal"], fontSize=9, leading=13, textColor=colors.HexColor("#1E3A8A"), fontName="Helvetica"),
        "warn": ParagraphStyle("W", parent=base["Normal"], fontSize=9, leading=13, textColor=colors.HexColor("#92400E"), fontName="Helvetica"),
    }


def _resolve_img_path(diag: dict) -> str | None:
    p = diag.get("img_path", "")
    if p and os.path.isfile(p):
        return p
    rel = str(diag.get("img_url", "")).lstrip("/")
    cand = os.path.join(STATIC_DIR, "generated", os.path.basename(rel))
    return cand if os.path.isfile(cand) else None


def generate_dynamic_pdf_report(canonical: dict, output_path: str, doc_name: str = None) -> str:
    """Génère un rapport de synthèse minimaliste dans le style V1."""
    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    st = _styles()
    story = []

    raw_title = str(canonical.get("title", "Système")).split("—")[0].strip()
    conops = str(canonical.get("conops", "")).strip()
    metier = canonical.get("metier", {})
    alerts = metier.get("alerts", [])
    diagrams = canonical.get("diagrams", [])
    ebom = canonical.get("ebom", [])
    v2 = canonical.get("v2_pipeline", {})
    phys = v2.get("physics", {})

    # Fallback if diagrams list is absent
    if not diagrams and canonical.get("diagram_img"):
        diagrams = [{
            "title": "Architecture & Échanges",
            "comment": f"Vue interne des composants extraits pour {raw_title}.",
            "img_url": canonical["diagram_img"],
        }]

    # 1. En-tête ENSAM
    hdr = Table([[
        Paragraph("<b>ENSAM MEKNÈS</b> — Département GIA-DTSI", ParagraphStyle("HL", fontSize=9, textColor=colors.HexColor("#2563EB"))),
        Paragraph(f"Date : {datetime.now().strftime('%d/%m/%Y à %H:%M')}", ParagraphStyle("HR", fontSize=9, textColor=colors.HexColor("#64748B"), alignment=2)),
    ]], colWidths=[300, 220])
    hdr.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    story += [
        hdr,
        Spacer(1, 6),
        HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563EB"), spaceAfter=12),
        Paragraph(f"RAPPORT DE SYNTHÈSE : {raw_title.upper()}", st["title"]),
        Spacer(1, 4),
        Paragraph(f"Source : <i>{doc_name.strip() if doc_name and doc_name.strip() else raw_title}</i>", st["sub"]),
        Spacer(1, 12),
    ]

    # 2. Badges statut (style V1)
    n_alerts = len(alerts)
    status_txt = "ARCHITECTURE CONFORME" if n_alerts == 0 else "POINTS À CONFIRMER"
    alert_lbl = f"{n_alerts} POINT D'ARBITRAGE IDENTIFIÉ" if n_alerts == 1 else f"{n_alerts} POINTS D'ARBITRAGE IDENTIFIÉS"
    badge_tbl = Table([[
        Paragraph(f"<b>STATUT :</b> {status_txt}", ParagraphStyle("B1", fontSize=9.5, textColor=colors.HexColor("#065F46"), fontName="Helvetica-Bold")),
        Paragraph(f"<b>ARBITRAGES :</b> {alert_lbl}", ParagraphStyle("B2", fontSize=9.5, textColor=colors.HexColor("#92400E"), fontName="Helvetica-Bold")),
    ]], colWidths=[260, 260])
    badge_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#ECFDF5")),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#FFFBEB")),
        ("BOX", (0, 0), (0, 0), 1, colors.HexColor("#A7F3D0")),
        ("BOX", (1, 0), (1, 0), 1, colors.HexColor("#FDE68A")),
        ("PADDING", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    story += [badge_tbl, Spacer(1, 10)]

    if conops:
        story += [Paragraph(conops, st["body"]), Spacer(1, 10)]

    # 3. Vues / Graphes d'architecture sélectionnés (hors bilans budgets non pertinents pour l'employé)
    filtered_diagrams = [
        d for d in diagrams
        if d.get("type") != "par" and not any(w in str(d.get("title", "")).lower() for w in ("budget", "évaluation des budgets", "evaluation des budgets"))
    ]
    for idx, diag in enumerate(filtered_diagrams, start=1):
        if idx > 1:
            story.append(PageBreak())
        story.append(Paragraph(f"{idx}. {diag.get('title', f'Vue {idx}')}", st["h2"]))
        img_path = _resolve_img_path(diag)
        if img_path:
            story.append(RLImage(img_path, width=510, height=265, kind="proportional"))
            story.append(Spacer(1, 8))
        if diag.get("comment"):
            story.append(Paragraph(diag["comment"], st["note"]))
            story.append(Spacer(1, 8))

    # 4. Points d'Arbitrage & Recommandations (les tables brutes eBOM et Exigences sont retirées du rapport employé)
    story.append(PageBreak())
    sec_num = len(filtered_diagrams) + 1

    story.append(Paragraph(f"{sec_num}. Points d'Arbitrage & Recommandations", st["h2"]))
    if alerts:
        act_rows = [[Paragraph("<b>Sujet</b>", st["bold"]), Paragraph("<b>Recommandation</b>", st["bold"])]]
        for al in alerts:
            act_rows.append([
                Paragraph(str(al.get("title", "Point à préciser")), st["body"]),
                Paragraph(str(al.get("text", "")), st["warn"]),
            ])
        t_act = Table(act_rows, colWidths=[170, 350])
        t_act.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("PADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t_act)
    else:
        story.append(Paragraph("Aucune ambiguïté critique détectée dans le cahier des charges.", st["body"]))

    story += [
        Spacer(1, 20),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceAfter=8),
        Table([[
            Paragraph("<b>SysmEasy</b> — ENSAM Meknès", st["body"]),
            Paragraph("<b>Supervision :</b> Mme I. El-Hassani & M. D. Motte", st["body"]),
            Paragraph("<b>Projet 4A :</b> S. Loukili & K. El Khaniri", st["body"]),
        ]], colWidths=[160, 190, 170]),
    ]

    doc.build(story)
    return output_path


def generate_executive_pdf_report(model_key: str, output_path: str, doc_name: str = None):
    """Fallback minimaliste pour les clés de démonstration statiques."""
    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    st = _styles()
    story = [
        Paragraph(f"RAPPORT DE SYNTHÈSE : {model_key.upper()}", st["title"]),
        Spacer(1, 8),
        Paragraph("Soumettez un cahier des charges dans l'interface pour générer un rapport personnalisé.", st["body"]),
    ]
    doc.build(story)
    return output_path
