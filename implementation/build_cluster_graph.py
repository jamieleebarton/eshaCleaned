from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path

import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler

import cluster_spine_common as common


def balanced_sample(assignments: pd.DataFrame, max_clusters: int) -> pd.DataFrame:
    if max_clusters <= 0 or len(assignments) <= max_clusters:
        return assignments.copy()
    hard = assignments[assignments["graph_severity"] == "hard"]
    unassigned = assignments[assignments["assignment_status"] != "assigned"]
    ok = assignments[assignments["graph_severity"] == "ok"]
    hard_n = min(len(hard), max_clusters // 3)
    unassigned_n = min(len(unassigned), max_clusters // 3)
    ok_n = max_clusters - hard_n - unassigned_n
    parts = []
    if hard_n:
        parts.append(hard.sample(hard_n, random_state=17))
    if unassigned_n:
        parts.append(unassigned.sample(unassigned_n, random_state=23))
    if ok_n:
        parts.append(ok.sample(min(len(ok), ok_n), random_state=31))
    return pd.concat(parts, ignore_index=True).drop_duplicates("cluster_id")


def embed(nodes: pd.DataFrame) -> pd.DataFrame:
    if len(nodes) < 3:
        out = nodes.copy()
        out["x"] = range(len(out))
        out["y"] = 0.0
        out["z"] = 0.0
        return out
    vectorizer = TfidfVectorizer(max_features=16000, min_df=1, ngram_range=(1, 2))
    matrix = vectorizer.fit_transform(nodes["text"].astype(str))
    if matrix.shape[1] < 3:
        coords = [[float(i), 0.0, 0.0] for i in range(len(nodes))]
    else:
        coords = TruncatedSVD(n_components=3, random_state=13).fit_transform(matrix)
        coords = StandardScaler().fit_transform(coords)
    out = nodes.copy()
    out["x"] = [float(c[0]) for c in coords]
    out["y"] = [float(c[1]) for c in coords]
    out["z"] = [float(c[2]) for c in coords]
    return out


def add_edge_lengths(edges: pd.DataFrame, nodes: pd.DataFrame) -> pd.DataFrame:
    coords = nodes.set_index("node_id")[["x", "y", "z"]].to_dict("index")
    lengths = []
    for _, row in edges.iterrows():
        a = coords.get(row["source"])
        b = coords.get(row["target"])
        if not a or not b:
            lengths.append(0.0)
            continue
        lengths.append(math.sqrt((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2 + (a["z"] - b["z"]) ** 2))
    out = edges.copy()
    out["edge_length"] = [round(v, 4) for v in lengths]
    return out


def write_html(nodes: pd.DataFrame, edges: pd.DataFrame, summary: dict[str, object], path: Path) -> None:
    node_records = nodes[["node_id", "node_type", "label", "severity", "text", "x", "y", "z"]].to_dict("records")
    edge_records = edges[["source", "target", "severity", "label", "edge_length"]].to_dict("records")
    summary_json = json.dumps(summary, indent=2, sort_keys=True)
    html_text = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Cluster Taxonomy Conflict Map</title>
  <style>
    body {{ margin: 24px; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif; color: #1f2933; }}
    canvas {{ width: 100%; height: 420px; border: 1px solid #d8dee9; background: #fbfaf5; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, minmax(280px, 1fr)); gap: 16px; }}
    pre {{ background: #f4f6f8; padding: 12px; overflow: auto; }}
  </style>
</head>
<body>
  <h1>Cluster Taxonomy Conflict Map</h1>
  <p>Each blue dot is a product evidence cluster. Each black square is an ESHA code. Red/orange edges are cluster-level conflicts or unassigned candidates.</p>
  <div class="grid"><canvas id="xy" width="640" height="420"></canvas><canvas id="xz" width="640" height="420"></canvas><canvas id="yz" width="640" height="420"></canvas></div>
  <h2>Summary</h2><pre>{html.escape(summary_json)}</pre>
<script>
const nodes = {json.dumps(node_records)};
const edges = {json.dumps(edge_records)};
const byId = new Map(nodes.map(n => [n.node_id, n]));
function color(s) {{ return s === 'hard' ? '#dc2626' : s === 'soft' ? '#f59e0b' : '#b8bec8'; }}
function draw(id, a, b) {{
  const c = document.getElementById(id), ctx = c.getContext('2d'), w = c.width, h = c.height, pad = 28;
  const xs = nodes.map(n => n[a]), ys = nodes.map(n => n[b]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const sx = v => pad + (v - minX) / Math.max(maxX - minX, 1e-9) * (w - 2 * pad);
  const sy = v => h - pad - (v - minY) / Math.max(maxY - minY, 1e-9) * (h - 2 * pad);
  ctx.clearRect(0,0,w,h);
  ctx.globalAlpha = 0.18;
  for (const e of edges) {{
    const s = byId.get(e.source), t = byId.get(e.target); if (!s || !t) continue;
    ctx.strokeStyle = color(e.severity); ctx.beginPath(); ctx.moveTo(sx(s[a]), sy(s[b])); ctx.lineTo(sx(t[a]), sy(t[b])); ctx.stroke();
  }}
  ctx.globalAlpha = 0.85;
  for (const n of nodes) {{
    ctx.fillStyle = n.node_type === 'esha' ? '#111827' : color(n.severity);
    const x = sx(n[a]), y = sy(n[b]);
    if (n.node_type === 'esha') ctx.fillRect(x - 3, y - 3, 6, 6); else {{ ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fill(); }}
  }}
}}
draw('xy','x','y'); draw('xz','x','z'); draw('yz','y','z');
</script>
</body>
</html>
"""
    path.write_text(html_text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assignments", type=Path, default=common.CLUSTER_ASSIGNMENTS_CSV)
    parser.add_argument("--validation", type=Path, default=common.CLUSTER_VALIDATION_CSV)
    parser.add_argument("--max-clusters", type=int, default=15000)
    args = parser.parse_args()

    assignments = pd.read_csv(args.assignments, dtype=str, keep_default_na=False, low_memory=False)
    validation = pd.read_csv(args.validation, dtype=str, keep_default_na=False, low_memory=False) if args.validation.exists() else pd.DataFrame()
    hard_clusters = set(validation.get("cluster_id", pd.Series(dtype=str)).astype(str)) if not validation.empty and "cluster_id" in validation else set()
    assignments["graph_severity"] = assignments.apply(
        lambda r: "hard" if str(r.get("cluster_id")) in hard_clusters else "ok" if r.get("assignment_status") == "assigned" else "soft",
        axis=1,
    )
    sample = balanced_sample(assignments, args.max_clusters)
    nodes: list[dict[str, object]] = []
    esha_nodes: dict[str, dict[str, object]] = {}
    edges: list[dict[str, object]] = []
    for _, row in sample.iterrows():
        cid = str(row["cluster_id"])
        cluster_node = f"cluster:{cid}"
        cluster_text = " ".join(
            str(row.get(c, ""))
            for c in (
                "dominant_product_description", "dominant_category", "category_lane",
                "product_form", "title_identity_terms", "ingredient_core_terms",
                "subtype_keys",
            )
        )
        nodes.append(
            {
                "node_id": cluster_node,
                "node_type": "cluster",
                "label": str(row.get("dominant_product_description") or cid),
                "severity": row["graph_severity"],
                "text": cluster_text,
            }
        )
        if str(row.get("assignment_status")) == "assigned":
            code = str(row.get("assigned_esha_code"))
            esha_node = f"esha:{code}"
            esha_nodes[esha_node] = {
                "node_id": esha_node,
                "node_type": "esha",
                "label": str(row.get("assigned_esha_description") or code),
                "severity": "esha",
                "text": f"{row.get('assigned_esha_head','')} {row.get('assigned_esha_description','')} {row.get('assigned_esha_family','')}",
            }
            edges.append(
                {
                    "source": cluster_node,
                    "target": esha_node,
                    "severity": row["graph_severity"],
                    "label": str(row.get("assignment_reason") or ""),
                }
            )
    node_df = embed(pd.DataFrame(nodes + list(esha_nodes.values())))
    edge_df = add_edge_lengths(pd.DataFrame(edges), node_df) if edges else pd.DataFrame()
    node_df.to_csv(common.CLUSTER_GRAPH_NODES_CSV, index=False)
    edge_df.to_csv(common.CLUSTER_GRAPH_EDGES_CSV, index=False)
    summary = {
        "nodes": str(common.CLUSTER_GRAPH_NODES_CSV),
        "edges": str(common.CLUSTER_GRAPH_EDGES_CSV),
        "html": str(common.CLUSTER_GRAPH_HTML),
        "sample_clusters": int(len(sample)),
        "hard_clusters_in_sample": int((sample["graph_severity"] == "hard").sum()),
        "soft_clusters_in_sample": int((sample["graph_severity"] == "soft").sum()),
        "ok_clusters_in_sample": int((sample["graph_severity"] == "ok").sum()),
    }
    write_html(node_df, edge_df, summary, common.CLUSTER_GRAPH_HTML)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
