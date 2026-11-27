"""Dynamic matplotlib diagram renderer for SysML views selected by DiagramPlan."""

from __future__ import annotations

import os
import re
import textwrap
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as patches
import matplotlib.pyplot as plt

from sysmeasy.livrable2_pipeline import Livrable2Result
from sysmeasy.methodology.diagram_selector import DiagramPlan, DiagramSpec


def _render_context_bdd(result: Livrable2Result, output_path: str) -> None:
    """Niveau 0: Black-box system context with external interfaces & top requirements."""
    fig, ax = plt.subplots(figsize=(10, 5.2), dpi=180)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.2)
    ax.axis("off")

    frame = patches.FancyBboxPatch((0.2, 0.2), 9.6, 4.8, boxstyle="round,pad=0.08", fc="#F8FAFC", ec="#1E3A8A", lw=1.5)
    ax.add_patch(frame)
    ax.text(0.45, 4.72, f"bdd [System Context] {result.project_name}", fontsize=10.5, fontweight="bold", color="#1E3A8A")

    # Central System of Interest (SoI)
    soi = patches.FancyBboxPatch((3.4, 1.75), 3.2, 1.85, boxstyle="round,pad=0.08", fc="#DBEAFE", ec="#1D4ED8", lw=2.0)
    ax.add_patch(soi)
    ax.text(5.0, 2.95, result.project_name[:28], ha="center", va="center", fontsize=11, fontweight="bold", color="#1E3A8A")
    ax.text(5.0, 2.52, f"{len(result.components)} sous-systèmes | {len(result.requirements)} exigences", ha="center", va="center", fontsize=8, color="#1E40AF")
    ax.text(5.0, 2.12, result.conops[:48] + ("…" if len(result.conops) > 48 else ""), ha="center", va="center", fontsize=7.2, style="italic", color="#334155")

    # External actors / environment boxes
    actors = [
        ("Opérateur / Utilisateur", 0.55, 3.0, "#FEF3C7", "#D97706"),
        ("Source d'Énergie", 0.55, 1.15, "#ECFDF5", "#059669"),
        ("Environnement Terrain", 7.15, 3.0, "#F1F5F9", "#475569"),
        ("Exigences Clés", 7.15, 1.15, "#EFF6FF", "#3B82F6"),
    ]
    for label, x, y, fc, ec in actors:
        box = patches.FancyBboxPatch((x, y), 2.3, 0.95, boxstyle="round,pad=0.06", fc=fc, ec=ec, lw=1.2)
        ax.add_patch(box)
        ax.text(x + 1.15, y + 0.58, label, ha="center", va="center", fontsize=8.2, fontweight="bold", color="#0F172A")
        if label == "Exigences Clés" and result.requirements:
            if len(result.requirements) <= 5:
                req_preview = ", ".join(r["id"] for r in result.requirements)
            else:
                req_preview = f"{result.requirements[0]['id']} .. {result.requirements[-1]['id']}"
            ax.text(x + 1.15, y + 0.25, req_preview, ha="center", va="center", fontsize=7.0, color="#1E40AF")
        # Arrow toward/from SoI
        start_x = x + 2.3 if x < 5.0 else x
        end_x = 3.4 if x < 5.0 else 6.6
        ax.annotate("", xy=(end_x, 2.65), xytext=(start_x, y + 0.48),
                    arrowprops=dict(arrowstyle="<->", color=ec, lw=1.2, alpha=0.85))

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _render_ibd(result: Livrable2Result, output_path: str) -> None:
    """Niveau 1: Internal Block Diagram with components, mass/power, ports and complete flow legend."""
    comps = result.components[:9]
    cols = 3
    rows = max(1, (len(comps) + cols - 1) // cols)
    conns = [cn for cn in result.connections if cn.get("from") and cn.get("to") and cn["from"] != cn["to"]]
    use_legend = len(conns) > 4

    legend_rows = ((len(conns) + 2) // 3) if use_legend else 0
    legend_h = (0.28 * legend_rows + 0.40) if use_legend else 0.0
    fig_h = 2.4 + rows * 1.80 + legend_h
    fig, ax = plt.subplots(figsize=(11.4, fig_h), dpi=180)
    ax.set_xlim(0, 11.4)
    ax.set_ylim(0, fig_h)
    ax.axis("off")

    frame = patches.FancyBboxPatch((0.2, 0.2), 11.0, fig_h - 0.4, boxstyle="round,pad=0.08", fc="#F8FAFC", ec="#1E3A8A", lw=1.5, zorder=0)
    ax.add_patch(frame)
    ax.text(0.45, fig_h - 0.48, f"ibd [part def] {result.project_name}", fontsize=10.5, fontweight="bold", color="#1E3A8A", zorder=4)

    summary_txt = f"Masse : {result.total_mass_kg:.1f} kg | Puissance : {result.total_power_w:.0f} W"
    if result.autonomy_min is not None:
        summary_txt += f" | Autonomie : {result.autonomy_min:.0f} min"
    ax.text(10.95, fig_h - 0.48, summary_txt, ha="right", fontsize=8.3, fontweight="bold",
            color="#059669" if not result.soft_warnings else "#D97706", zorder=4)

    box_w, box_h = 3.10, 1.38
    positions: dict[str, tuple[float, float]] = {}
    top_y = fig_h - 0.85 - box_h
    for idx, comp in enumerate(comps):
        row, col = divmod(idx, cols)
        x = 0.58 + col * 3.55
        y = top_y - row * 1.82
        positions[comp["name"]] = (x, y)
        box = patches.FancyBboxPatch((x, y), box_w, box_h, boxstyle="round,pad=0.05", fc="#FFFFFF", ec="#3B82F6", lw=1.3, zorder=3)
        ax.add_patch(box)

        label = textwrap.fill(comp.get("label", comp["name"]), width=26)
        ax.text(x + box_w / 2, y + 1.04, label, ha="center", va="center", fontsize=7.8, fontweight="bold", color="#0F172A", zorder=4)
        ax.text(x + box_w / 2, y + 0.62, f"{comp['mass_kg']} kg | {comp['power_w']} W", ha="center", va="center", fontsize=7.3, color="#475569", zorder=4)

        ports = comp.get("ports", [])
        if ports:
            strip = patches.FancyBboxPatch((x + 0.08, y + 0.08), box_w - 0.16, 0.34, boxstyle="round,pad=0.02", fc="#EFF6FF", ec="#BFDBFE", lw=0.7, zorder=3)
            ax.add_patch(strip)
            port_lbl = " | ".join(f"{p['direction']}:{p['name'][:10]}" for p in ports[:2])
            ax.text(x + box_w / 2, y + 0.25, f"[{port_lbl}]", ha="center", va="center", fontsize=6.4, color="#1D4ED8", zorder=4)

    def _draw_arrow(src_name: str, dst_name: str, color: str, badge: str, frac: float = 0.5) -> None:
        sx, sy = positions[src_name]
        tx, ty = positions[dst_name]
        dy = abs(sy - ty)
        if dy < 0.2:
            if abs(sx - tx) > 3.8:
                start_pt = (sx + box_w / 2, sy)
                end_pt = (tx + box_w / 2, ty)
                ax.annotate("", xy=end_pt, xytext=start_pt,
                            arrowprops=dict(arrowstyle="->", color=color, lw=1.2, ls="--", alpha=0.85,
                                            connectionstyle="arc3,rad=0.26"), zorder=1)
                mid_x = start_pt[0] + (end_pt[0] - start_pt[0]) * frac
                mid_y = sy - 0.32
            else:
                start_pt = (sx + box_w, sy + box_h * 0.5) if sx < tx else (sx, sy + box_h * 0.5)
                end_pt = (tx, ty + box_h * 0.5) if sx < tx else (tx + box_w, ty + box_h * 0.5)
                ax.annotate("", xy=end_pt, xytext=start_pt,
                            arrowprops=dict(arrowstyle="->", color=color, lw=1.2, ls="--", alpha=0.85), zorder=1)
                mid_x = start_pt[0] + (end_pt[0] - start_pt[0]) * frac
                mid_y = start_pt[1] + 0.14
        else:
            start_pt = (sx + box_w / 2, sy) if sy > ty else (sx + box_w / 2, sy + box_h)
            end_pt = (tx + box_w / 2, ty + box_h) if sy > ty else (tx + box_w / 2, ty)
            rad = 0.28 if dy > 2.2 else 0.08
            ax.annotate("", xy=end_pt, xytext=start_pt,
                        arrowprops=dict(arrowstyle="->", color=color, lw=1.2, ls="--", alpha=0.85,
                                        connectionstyle=f"arc3,rad={rad}"), zorder=1)
            mid_x = start_pt[0] + (end_pt[0] - start_pt[0]) * frac
            mid_y = start_pt[1] + (end_pt[1] - start_pt[1]) * frac

        if badge:
            ax.text(mid_x, mid_y, badge, ha="center", va="center", fontsize=6.4, fontweight="bold",
                    color=color, bbox=dict(fc="#FFFFFF", ec=color, lw=0.6, pad=1.1, alpha=0.96), zorder=5)

    legend_items: list[str] = []
    if conns:
        for idx, cn in enumerate(conns, start=1):
            if cn["from"] in positions and cn["to"] in positions:
                is_data = cn.get("domain") == "data"
                lbl = cn.get("label") or ("data" if is_data else "power")
                badge = f"F{idx}" if use_legend else lbl
                if use_legend:
                    legend_items.append(f"F{idx}: {lbl}")
                _draw_arrow(cn["from"], cn["to"], "#2563EB" if is_data else "#D97706", badge, frac=0.36 if idx % 2 else 0.64)
    else:
        sources = [c for c in comps if any(p.get("direction") == "out" for p in c.get("ports", []))]
        sinks = [c for c in comps if any(p.get("direction") == "in" for p in c.get("ports", []))]
        if sources and sinks:
            for sink in sinks:
                if sources[0]["name"] != sink["name"]:
                    _draw_arrow(sources[0]["name"], sink["name"], "#D97706", "power")

    if legend_items:
        leg_box = patches.FancyBboxPatch((0.45, 0.35), 10.5, legend_h - 0.15, boxstyle="round,pad=0.04",
                                         fc="#FFFFFF", ec="#CBD5E1", lw=0.8, zorder=2)
        ax.add_patch(leg_box)
        for i, item in enumerate(legend_items):
            r_idx, c_idx = divmod(i, 3)
            lx = 0.65 + c_idx * 3.48
            ly = (0.35 + legend_h - 0.32) - r_idx * 0.26
            ax.text(lx, ly, item[:34], ha="left", va="center", fontsize=6.8, color="#334155", zorder=4)

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _extract_states(result: Livrable2Result, raw_prompt: str) -> list[str]:
    text = f"{result.conops} {raw_prompt}".lower()
    candidates = [
        ("Veille / Arrêt", ["veille", "arrêt", "arret", "standby"]),
        ("Démarrage / Init", ["démarrage", "demarrage", "initialisation", "boot"]),
        ("Fonctionnement Nominal", ["nominal", "projection", "travail", "marche", "charge", "croisière"]),
        ("Mode Éco / Régulation", ["éco", "eco", "régul", "regul", "thermique"]),
        ("Sécurité / Urgence", ["urgence", "surchauffe", "défaut", "defaut", "coupure", "100%"]),
    ]
    states = [name for name, kws in candidates if any(k in text for k in kws)]
    if len(states) < 3:
        states = ["Initialisation", "Mode Nominal", "Mode Dégradé / Arrêt"]
    return states[:4]


def _render_stm(result: Livrable2Result, raw_prompt: str, output_path: str, spec: DiagramSpec | None = None) -> None:
    """Niveau 2: State Machine Diagram showing operational modes & wrapped transitions."""
    states = list(spec.states) if spec and len(spec.states) >= 2 else _extract_states(result, raw_prompt)
    guards = list(spec.transitions) if spec and spec.transitions else ["init_ok", "seuil / défaut", "urgence"]
    fig, ax = plt.subplots(figsize=(11.5, 5.0), dpi=180)
    ax.set_xlim(0, 11.5)
    ax.set_ylim(0, 5.0)
    ax.axis("off")

    frame = patches.FancyBboxPatch((0.2, 0.2), 11.1, 4.6, boxstyle="round,pad=0.08", fc="#F8FAFC", ec="#1E3A8A", lw=1.5)
    ax.add_patch(frame)
    ax.text(0.45, 4.48, f"stm [State Machine] Modes — {result.project_name}", fontsize=10.5, fontweight="bold", color="#1E3A8A")

    ax.add_patch(patches.Circle((0.75, 2.5), 0.14, fc="#0F172A", ec="#0F172A"))
    n = len(states)
    w = min(1.85, 6.2 / max(n, 1))
    step_x = (9.6 - 1.35) / max(n, 1)
    xs = [1.35 + i * step_x for i in range(n)]

    ax.annotate("", xy=(xs[0], 2.5), xytext=(0.90, 2.5), arrowprops=dict(arrowstyle="->", color="#0F172A", lw=1.5))

    palette = [("#EFF6FF", "#2563EB"), ("#ECFDF5", "#059669"), ("#FEF3C7", "#D97706"), ("#FEF2F2", "#DC2626")]
    for i, st in enumerate(states):
        fc, ec = palette[i % len(palette)]
        box = patches.FancyBboxPatch((xs[i], 1.9), w, 1.2, boxstyle="round,pad=0.08", fc=fc, ec=ec, lw=1.6, zorder=3)
        ax.add_patch(box)
        ax.text(xs[i] + w / 2, 2.5, textwrap.fill(st, width=16), ha="center", va="center",
                fontsize=8.2, fontweight="bold", color="#0F172A", zorder=4)
        if i < n - 1:
            ax.annotate("", xy=(xs[i + 1], 2.5), xytext=(xs[i] + w, 2.5),
                        arrowprops=dict(arrowstyle="->", color="#334155", lw=1.5), zorder=2)
            mid_x = (xs[i] + w + xs[i + 1]) / 2
            guard_lbl = textwrap.fill(guards[i % len(guards)], width=16)
            ax.text(mid_x, 3.22, guard_lbl, ha="center", va="bottom", fontsize=6.6, style="italic",
                    color="#334155", bbox=dict(fc="#F8FAFC", ec="none", pad=0.8), zorder=5)

    if n >= 2:
        ax.annotate("", xy=(xs[0] + w / 2, 1.88), xytext=(xs[-1] + w / 2, 1.88),
                    arrowprops=dict(arrowstyle="->", color="#64748B", lw=1.1, ls="--", connectionstyle="arc3,rad=-0.24"), zorder=2)
        ax.text(5.75, 0.92, "Réarmement / Nouveau cycle", ha="center", fontsize=7.8, style="italic", color="#64748B")

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _render_act(result: Livrable2Result, output_path: str) -> None:
    """Niveau 2: Activity Diagram showing sequential functional flow."""
    fig, ax = plt.subplots(figsize=(10, 4.6), dpi=180)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.6)
    ax.axis("off")

    frame = patches.FancyBboxPatch((0.2, 0.2), 9.6, 4.2, boxstyle="round,pad=0.08", fc="#F8FAFC", ec="#1E3A8A", lw=1.5)
    ax.add_patch(frame)
    ax.text(0.45, 4.1, f"act [Activity] Flux Fonctionnel — {result.project_name}", fontsize=10.5, fontweight="bold", color="#1E3A8A")

    steps = [r["name"][:22] for r in result.requirements[:4]]
    if len(steps) < 3:
        steps = ["Acquérir entrées", "Traiter & Réguler", "Exécuter mission", "Contrôler sécurité"]

    n = len(steps)
    xs = [1.2 + i * (7.8 / n) for i in range(n)]
    w = min(1.8, 6.4 / n)
    ax.add_patch(patches.Circle((0.7, 2.3), 0.13, fc="#0F172A"))
    ax.annotate("", xy=(xs[0], 2.3), xytext=(0.85, 2.3), arrowprops=dict(arrowstyle="->", color="#0F172A", lw=1.4))

    for i, step in enumerate(steps):
        box = patches.FancyBboxPatch((xs[i], 1.75), w, 1.1, boxstyle="round,pad=0.08", fc="#EFF6FF", ec="#2563EB", lw=1.5)
        ax.add_patch(box)
        ax.text(xs[i] + w / 2, 2.3, step, ha="center", va="center", fontsize=8.2, fontweight="bold", color="#0F172A")
        if i < n - 1:
            ax.annotate("", xy=(xs[i + 1], 2.3), xytext=(xs[i] + w, 2.3),
                        arrowprops=dict(arrowstyle="->", color="#2563EB", lw=1.5))

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _render_par(result: Livrable2Result, output_path: str) -> None:
    """Niveau 2: Parametric / Budget breakdown chart (Mass & Power per component)."""
    comps = [c for c in result.components if c["mass_kg"] > 0 or c["power_w"] > 0][:8]
    if not comps:
        comps = result.components[:6]

    labels = [textwrap.fill(c.get("label", c["name"]), width=22) for c in comps]
    masses = [float(c.get("mass_kg", 0.0)) for c in comps]
    powers = [float(c.get("power_w", 0.0)) for c in comps]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.4), dpi=180)
    fig.patch.set_facecolor("#F8FAFC")

    if sum(masses) == 0.0 and result.total_mass_kg > 0:
        mass_labels = [f"{result.project_name}\n(budget système)"]
        mass_vals = [result.total_mass_kg]
    else:
        mass_labels, mass_vals = labels, masses

    ax1.barh(mass_labels, mass_vals, color="#3B82F6")
    ax1.set_title(f"Répartition Masse (Total : {result.total_mass_kg:.1f} kg)", fontsize=9.5, fontweight="bold", color="#1E3A8A")
    ax1.set_xlabel("kg", fontsize=8)
    ax1.tick_params(labelsize=7.5)
    ax1.invert_yaxis()

    ax2.barh(labels, powers, color="#F59E0B")
    ax2.set_title(f"Répartition Puissance (Total : {result.total_power_w:.0f} W)", fontsize=9.5, fontweight="bold", color="#1E3A8A")
    ax2.set_xlabel("W", fontsize=8)
    ax2.tick_params(labelsize=7.5)
    ax2.invert_yaxis()

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def render_selected_diagrams(
    result: Livrable2Result,
    plan: DiagramPlan,
    output_dir: str,
    raw_prompt: str = "",
) -> list[dict[str, Any]]:
    """Render all diagrams chosen by DiagramPlan and return metadata + image URLs."""
    os.makedirs(output_dir, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", result.project_name.lower()).strip("_") or "custom"

    rendered: list[dict[str, Any]] = []
    for spec in plan.diagrams:
        fname = f"dyn_{slug}_{spec.type}.png"
        fpath = os.path.join(output_dir, fname)

        if spec.type in ("context_bdd", "uc"):
            _render_context_bdd(result, fpath)
        elif spec.type == "ibd":
            _render_ibd(result, fpath)
        elif spec.type == "stm":
            _render_stm(result, raw_prompt, fpath, spec=spec)
        elif spec.type == "act":
            _render_act(result, fpath)
        elif spec.type == "par":
            _render_par(result, fpath)
        else:
            _render_ibd(result, fpath)

        rendered.append({
            "type": spec.type,
            "title": spec.title,
            "comment": spec.comment,
            "img_url": f"/images/{fname}",
            "img_path": fpath,
        })
    return rendered
