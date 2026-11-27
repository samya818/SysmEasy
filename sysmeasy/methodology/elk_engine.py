"""Eclipse Layout Kernel (elkjs) bridge for collision-free SysML v2 diagram layouts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as patches
import matplotlib.pyplot as plt

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LAYOUT_SCRIPT = _PROJECT_ROOT / "elk_layout" / "layout.js"
_ELK_MODULE = _PROJECT_ROOT / "elk_layout" / "node_modules" / "elkjs"


def is_elk_available() -> bool:
    """Return True if Node.js and elkjs are present on this machine."""
    return bool(shutil.which("node") and _LAYOUT_SCRIPT.is_file() and _ELK_MODULE.exists())


def run_elk_layout(graph: dict[str, Any], timeout_s: float = 10.0) -> dict[str, Any] | None:
    """Execute elkjs layout via Node.js and return the laid-out graph, or None on unavailability."""
    if not is_elk_available():
        return None
    try:
        proc = subprocess.run(
            ["node", str(_LAYOUT_SCRIPT)],
            input=json.dumps(graph),
            text=True,
            capture_output=True,
            timeout=timeout_s,
            encoding="utf-8",
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        return json.loads(proc.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None


def _draw_orthogonal_edge(
    ax: plt.Axes,
    pts: list[tuple[float, float]],
    color: str,
    dashed: bool = True,
    lw: float = 1.35,
) -> None:
    """Draw an orthogonal ELK polyline with a clean arrowhead on the final segment."""
    if len(pts) < 2:
        return
    ls = "--" if dashed else "-"
    if len(pts) > 2:
        xs = [p[0] for p in pts[:-1]] + [pts[-2][0]]
        ys = [p[1] for p in pts[:-1]] + [pts[-2][1]]
        ax.plot(xs, ys, color=color, lw=lw, ls=ls, alpha=0.88, zorder=2, solid_capstyle="round")
    ax.annotate(
        "",
        xy=pts[-1],
        xytext=pts[-2],
        arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, ls=ls, alpha=0.92, shrinkA=0, shrinkB=0, mutation_scale=11),
        zorder=2,
    )


def _edge_points_from_section(section: dict[str, Any], total_h: float, offset_x: float, offset_y: float) -> list[tuple[float, float]]:
    """Convert ELK top-down edge section points into matplotlib bottom-up coordinates."""
    raw_pts = [section["startPoint"], *section.get("bendPoints", []), section["endPoint"]]
    return [(offset_x + p["x"], total_h - (offset_y + p["y"])) for p in raw_pts]


def render_ibd_with_elk(
    project_name: str,
    summary_txt: str,
    has_warnings: bool,
    comps: list[dict[str, Any]],
    conns: list[dict[str, Any]],
    output_path: str,
) -> bool:
    """Render an Internal Block Diagram using ELK layered orthogonal routing. Returns False if ELK is unavailable."""
    use_legend = len(conns) > 4
    comp_map = {c["name"]: c for c in comps}
    elk_nodes: list[dict[str, Any]] = []

    for c in comps:
        cname = c["name"]
        label = textwrap.fill(c.get("label", cname), width=24)
        n_lines = label.count("\n") + 1
        ports_meta = c.get("ports", [])
        elk_ports: list[dict[str, Any]] = []
        used_port_ids: set[str] = set()

        for p_idx, p in enumerate(ports_meta):
            pid = f"{cname}::{p['name']}"
            if pid in used_port_ids:
                pid = f"{pid}_{p_idx}"
            used_port_ids.add(pid)
            direction = p.get("direction", "in")
            side = "EAST" if direction == "out" else ("WEST" if direction == "in" else "SOUTH")
            elk_ports.append({
                "id": pid,
                "width": 10,
                "height": 10,
                "layoutOptions": {"elk.port.side": side},
                "meta": {"name": p["name"], "direction": direction, "domain": p.get("domain", "data")},
            })

        in_cnt = sum(1 for ep in elk_ports if ep["layoutOptions"]["elk.port.side"] == "WEST")
        out_cnt = sum(1 for ep in elk_ports if ep["layoutOptions"]["elk.port.side"] == "EAST")
        node_h = max(84, 52 + n_lines * 16, 26 + max(in_cnt, out_cnt) * 22)
        elk_nodes.append({
            "id": cname,
            "width": 225,
            "height": node_h,
            "ports": elk_ports,
            "layoutOptions": {
                "elk.portConstraints": "FIXED_SIDE",
                "elk.nodeLabels.placement": "INSIDE V_CENTER H_CENTER",
            },
            "meta": {
                "label": label,
                "category": c.get("category", "part"),
                "mass_kg": c.get("mass_kg", 0.0),
                "power_w": c.get("power_w", 0.0),
            },
        })

    def _pick_port(comp_name: str, side: str, domain: str) -> str:
        node = next((n for n in elk_nodes if n["id"] == comp_name), None)
        if not node:
            return comp_name
        for ep in node["ports"]:
            if ep["layoutOptions"]["elk.port.side"] == side and ep["meta"]["domain"] == domain:
                return ep["id"]
        for ep in node["ports"]:
            if ep["layoutOptions"]["elk.port.side"] == side:
                return ep["id"]
        # Create a clean synthetic port if the component didn't declare one on that side
        pid = f"{comp_name}::{side.lower()}_{len(node['ports'])}"
        node["ports"].append({
            "id": pid,
            "width": 10,
            "height": 10,
            "layoutOptions": {"elk.port.side": side},
            "meta": {"name": domain, "direction": "out" if side == "EAST" else "in", "domain": domain},
        })
        return pid

    elk_edges: list[dict[str, Any]] = []
    legend_items: list[str] = []
    flow_idx = 0
    for cn in conns:
        src, dst = cn.get("from", ""), cn.get("to", "")
        if src not in comp_map or dst not in comp_map or src == dst:
            continue
        flow_idx += 1
        domain = cn.get("domain", "data")
        lbl = cn.get("label") or ("data" if domain == "data" else "power")
        badge = f"F{flow_idx}" if use_legend else lbl[:22]
        if use_legend:
            legend_items.append(f"F{flow_idx}: {lbl}")
        src_port = _pick_port(src, "EAST", domain)
        dst_port = _pick_port(dst, "WEST", domain)
        elk_edges.append({
            "id": f"e{flow_idx}",
            "sources": [src_port],
            "targets": [dst_port],
            "labels": [{"text": badge, "width": max(26, len(badge) * 7.2 + 8), "height": 16}],
            "meta": {"domain": domain, "badge": badge},
        })

    graph = {
        "id": "ibd_root",
        "layoutOptions": {
            "elk.algorithm": "layered",
            "elk.direction": "RIGHT",
            "elk.edgeRouting": "ORTHOGONAL",
            "elk.spacing.nodeNode": "42",
            "elk.layered.spacing.nodeNodeBetweenLayers": "68",
            "elk.layered.spacing.edgeNodeBetweenLayers": "28",
            "elk.spacing.edgeEdge": "16",
            "elk.spacing.edgeNode": "22",
            "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
            "elk.padding": "[top=24,left=24,bottom=24,right=24]",
        },
        "children": elk_nodes,
        "edges": elk_edges,
    }

    layouted = run_elk_layout(graph)
    if not layouted:
        return False

    gw = max(float(layouted.get("width", 800)), 640.0)
    gh = max(float(layouted.get("height", 400)), 280.0)
    header_h = 54.0
    legend_rows = ((len(legend_items) + 2) // 3) if legend_items else 0
    legend_h = (24.0 * legend_rows + 32.0) if legend_items else 0.0
    total_w = gw + 40.0
    total_h = header_h + gh + legend_h + 32.0

    fig_w = max(10.0, min(16.0, total_w / 82.0))
    fig_h = fig_w * (total_h / total_w)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=180)
    ax.set_xlim(0, total_w)
    ax.set_ylim(0, total_h)
    ax.axis("off")

    # Outer SysML frame
    frame = patches.FancyBboxPatch(
        (8, 8), total_w - 16, total_h - 16,
        boxstyle="round,pad=4", fc="#F8FAFC", ec="#1E3A8A", lw=1.6, zorder=0,
    )
    ax.add_patch(frame)
    ax.text(24, total_h - 28, f"ibd [part def] {project_name}", fontsize=10.5, fontweight="bold", color="#1E3A8A", va="center", zorder=5)
    ax.text(
        total_w - 24, total_h - 28, summary_txt, ha="right", va="center", fontsize=8.2, fontweight="bold",
        color="#059669" if not has_warnings else "#D97706", zorder=5,
    )

    offset_x, offset_y = 20.0, header_h
    meta_by_id = {n["id"]: n["meta"] for n in elk_nodes}
    ports_meta_by_id = {ep["id"]: ep["meta"] for n in elk_nodes for ep in n["ports"]}

    # Draw edges first (behind nodes, above frame)
    for edge in layouted.get("edges", []):
        domain = edge.get("meta", {}).get("domain", "data")
        color = "#2563EB" if domain == "data" else ("#059669" if domain == "mechanical" else "#D97706")
        for sec in edge.get("sections", []):
            pts = _edge_points_from_section(sec, total_h, offset_x, offset_y)
            _draw_orthogonal_edge(ax, pts, color, dashed=(domain == "data"))
        for lbl in edge.get("labels", []):
            lx = offset_x + float(lbl.get("x", 0)) + float(lbl.get("width", 26)) / 2
            ly = total_h - (offset_y + float(lbl.get("y", 0)) + float(lbl.get("height", 16)) / 2)
            ax.text(
                lx, ly, lbl["text"], ha="center", va="center", fontsize=6.8, fontweight="bold",
                color=color, bbox=dict(fc="#FFFFFF", ec=color, lw=0.7, pad=1.4, alpha=0.97), zorder=6,
            )

    # Draw component blocks & SysML port squares
    for node in layouted.get("children", []):
        nx = offset_x + float(node["x"])
        nw = float(node["width"])
        nh = float(node["height"])
        ny = total_h - (offset_y + float(node["y"]) + nh)
        meta = meta_by_id.get(node["id"], {})

        box = patches.FancyBboxPatch(
            (nx, ny), nw, nh, boxstyle="round,pad=2", fc="#FFFFFF", ec="#2563EB", lw=1.4, zorder=3,
        )
        ax.add_patch(box)
        ax.text(
            nx + nw / 2, ny + nh - 13, f"«{meta.get('category', 'part')}»",
            ha="center", va="center", fontsize=6.5, style="italic", color="#64748B", zorder=4,
        )
        ax.text(
            nx + nw / 2, ny + nh * 0.54, meta.get("label", node["id"]),
            ha="center", va="center", fontsize=8.0, fontweight="bold", color="#0F172A", zorder=4,
        )
        ax.text(
            nx + nw / 2, ny + 15, f"{meta.get('mass_kg', 0.0)} kg | {meta.get('power_w', 0.0)} W",
            ha="center", va="center", fontsize=7.2, color="#475569", zorder=4,
        )

        for port in node.get("ports", []):
            px = nx + float(port.get("x", 0))
            pw = float(port.get("width", 10))
            ph = float(port.get("height", 10))
            py = total_h - (offset_y + float(node["y"]) + float(port.get("y", 0)) + ph)
            pmeta = ports_meta_by_id.get(port["id"], {})
            pcol = "#2563EB" if pmeta.get("domain") == "data" else "#D97706"
            pbox = patches.Rectangle((px, py), pw, ph, fc="#EFF6FF", ec=pcol, lw=1.1, zorder=5)
            ax.add_patch(pbox)

    # Full 3-column flow legend at the bottom
    if legend_items:
        leg_y0 = 18.0
        leg_box = patches.FancyBboxPatch(
            (20, leg_y0), total_w - 40, legend_h - 4, boxstyle="round,pad=3",
            fc="#FFFFFF", ec="#CBD5E1", lw=0.9, zorder=2,
        )
        ax.add_patch(leg_box)
        col_w = (total_w - 64) / 3.0
        for i, item in enumerate(legend_items):
            r_idx, c_idx = divmod(i, 3)
            lx = 32 + c_idx * col_w
            ly = (leg_y0 + legend_h - 20) - r_idx * 22.0
            ax.text(lx, ly, item[:38], ha="left", va="center", fontsize=7.0, color="#334155", zorder=4)

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return True


def render_stm_with_elk(
    project_name: str,
    states: list[str],
    guards: list[str],
    output_path: str,
) -> bool:
    """Render a State Machine Diagram using ELK layered routing. Returns False if ELK is unavailable."""
    elk_nodes: list[dict[str, Any]] = [
        {"id": "__init__", "width": 22, "height": 22, "meta": {"init": True}},
    ]
    for i, st in enumerate(states):
        wrapped = textwrap.fill(st, width=18)
        elk_nodes.append({
            "id": f"st_{i}",
            "width": 165,
            "height": max(64, 34 + (wrapped.count("\n") + 1) * 16),
            "meta": {"label": wrapped, "idx": i},
        })

    elk_edges: list[dict[str, Any]] = [
        {"id": "e_init", "sources": ["__init__"], "targets": ["st_0"], "labels": []},
    ]
    for i in range(len(states) - 1):
        g = textwrap.fill(guards[i % len(guards)], width=18)
        elk_edges.append({
            "id": f"e_{i}",
            "sources": [f"st_{i}"],
            "targets": [f"st_{i + 1}"],
            "labels": [{"text": g, "width": 120, "height": 28}],
        })
    if len(states) >= 2:
        elk_edges.append({
            "id": "e_reset",
            "sources": [f"st_{len(states) - 1}"],
            "targets": ["st_0"],
            "labels": [{"text": "Réarmement / Nouveau cycle", "width": 150, "height": 18}],
            "meta": {"reset": True},
        })

    graph = {
        "id": "stm_root",
        "layoutOptions": {
            "elk.algorithm": "layered",
            "elk.direction": "RIGHT",
            "elk.edgeRouting": "ORTHOGONAL",
            "elk.layered.cycleBreaking.strategy": "MODEL_ORDER",
            "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
            "elk.layered.edgeLabels.sideSelection": "ALWAYS_UP",
            "elk.spacing.nodeNode": "44",
            "elk.layered.spacing.nodeNodeBetweenLayers": "68",
            "elk.spacing.edgeNode": "26",
            "elk.spacing.edgeLabel": "10",
            "elk.padding": "[top=30,left=24,bottom=34,right=24]",
        },
        "children": elk_nodes,
        "edges": elk_edges,
    }
    layouted = run_elk_layout(graph)
    if not layouted:
        return False

    gw = max(float(layouted.get("width", 700)), 520.0)
    gh = max(float(layouted.get("height", 260)), 200.0)
    header_h = 46.0
    total_w = gw + 40.0
    total_h = header_h + gh + 24.0

    fig_w = max(9.5, min(14.5, total_w / 76.0))
    fig, ax = plt.subplots(figsize=(fig_w, fig_w * (total_h / total_w)), dpi=180)
    ax.set_xlim(0, total_w)
    ax.set_ylim(0, total_h)
    ax.axis("off")

    frame = patches.FancyBboxPatch((8, 8), total_w - 16, total_h - 16, boxstyle="round,pad=4", fc="#F8FAFC", ec="#1E3A8A", lw=1.6, zorder=0)
    ax.add_patch(frame)
    ax.text(24, total_h - 26, f"stm [State Machine] Modes — {project_name}", fontsize=10.5, fontweight="bold", color="#1E3A8A", va="center", zorder=5)

    offset_x, offset_y = 20.0, header_h
    meta_by_id = {n["id"]: n["meta"] for n in elk_nodes}
    edge_meta = {e["id"]: e.get("meta", {}) for e in elk_edges}
    palette = [("#EFF6FF", "#2563EB"), ("#ECFDF5", "#059669"), ("#FEF3C7", "#D97706"), ("#FEF2F2", "#DC2626")]

    for edge in layouted.get("edges", []):
        is_reset = edge_meta.get(edge["id"], {}).get("reset", False)
        color = "#64748B" if is_reset else "#334155"
        for sec in edge.get("sections", []):
            pts = _edge_points_from_section(sec, total_h, offset_x, offset_y)
            _draw_orthogonal_edge(ax, pts, color, dashed=is_reset, lw=1.2 if is_reset else 1.5)
        for lbl in edge.get("labels", []):
            lx = offset_x + float(lbl.get("x", 0)) + float(lbl.get("width", 100)) / 2
            ly = total_h - (offset_y + float(lbl.get("y", 0)) + float(lbl.get("height", 18)) / 2)
            ax.text(
                lx, ly, lbl["text"], ha="center", va="center", fontsize=6.9, style="italic",
                color=color, bbox=dict(fc="#F8FAFC", ec="#E2E8F0", lw=0.6, pad=1.5), zorder=6,
            )

    for node in layouted.get("children", []):
        nx = offset_x + float(node["x"])
        nw = float(node["width"])
        nh = float(node["height"])
        ny = total_h - (offset_y + float(node["y"]) + nh)
        meta = meta_by_id.get(node["id"], {})
        if meta.get("init"):
            ax.add_patch(patches.Circle((nx + nw / 2, ny + nh / 2), 9, fc="#0F172A", ec="#0F172A", zorder=4))
        else:
            fc, ec = palette[meta.get("idx", 0) % len(palette)]
            box = patches.FancyBboxPatch((nx, ny), nw, nh, boxstyle="round,pad=4", fc=fc, ec=ec, lw=1.6, zorder=3)
            ax.add_patch(box)
            ax.text(nx + nw / 2, ny + nh / 2, meta["label"], ha="center", va="center", fontsize=8.2, fontweight="bold", color="#0F172A", zorder=4)

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return True
