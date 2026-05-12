from __future__ import annotations

import argparse
import html
import json
import math
from collections import Counter
from pathlib import Path

import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler

import self_heal_common as sh


OUT_ASSIGNMENTS = sh.SELF_HEAL_DIR / "self_heal_conflict_assignments.csv"
OUT_NODES = sh.SELF_HEAL_DIR / "self_heal_conflict_nodes.csv"
OUT_EDGES = sh.SELF_HEAL_DIR / "self_heal_conflict_edges.csv"
OUT_HTML = sh.SELF_HEAL_DIR / "self_heal_conflict_map.html"
OUT_SUMMARY = sh.SELF_HEAL_DIR / "self_heal_conflict_summary.json"


def classify(current: pd.DataFrame, facts: pd.DataFrame) -> pd.DataFrame:
    fact_by_fdc = sh.product_fact_map(facts)
    rows = []
    for _, row in current.iterrows():
        fdc_id = str(row.get("fdc_id") or "")
        fact = fact_by_fdc.get(fdc_id)
        code = str(row.get("best_esha_code") or "").split(".")[0].strip()
        desc = str(row.get("best_esha_description") or "")
        head = str(row.get("best_esha_head") or sh.esha_head(desc))
        target_heads = str(fact.get("target_heads") if fact is not None else "")
        if not code:
            severity = "missing"
            reason = str(row.get("self_heal_reason") or "missing_leaf")
        elif fact is None:
            severity = "hard"
            reason = "missing_product_facts"
        elif not sh.head_compatible(target_heads.split("|"), head):
            severity = "hard"
            reason = f"head_mismatch:{head}->allowed:{target_heads}"
        elif str(row.get("self_heal_status") or "") == "missing_leaf":
            severity = "missing"
            reason = str(row.get("self_heal_reason") or "missing_leaf")
        else:
            severity = "ok"
            reason = str(row.get("self_heal_reason") or "compatible")
        rows.append(
            {
                "gtin_upc": row.get("gtin_upc", ""),
                "fdc_id": fdc_id,
                "product_description": row.get("product_description", ""),
                "branded_food_category": row.get("branded_food_category", ""),
                "esha_code": code,
                "esha_description": desc,
                "esha_head": head,
                "assignment_source": row.get("assignment_source", ""),
                "self_heal_status": row.get("self_heal_status", ""),
                "category_lane": fact.get("category_lane", "") if fact is not None else "",
                "product_form": fact.get("product_form", "") if fact is not None else "",
                "product_role": fact.get("product_role", "") if fact is not None else "",
                "identity_terms": fact.get("identity_terms", "") if fact is not None else "",
                "target_heads": target_heads,
                "severity": severity,
                "conflict_reason": reason,
                "node_text": " ".join(
                    [
                        str(row.get("product_description", "")),
                        str(row.get("branded_food_category", "")),
                        str(fact.get("category_lane", "") if fact is not None else ""),
                        str(fact.get("product_form", "") if fact is not None else ""),
                        str(fact.get("identity_terms", "") if fact is not None else ""),
                    ]
                ),
            }
        )
    return pd.DataFrame(rows)


def balanced_sample(assignments: pd.DataFrame, max_products: int) -> pd.DataFrame:
    if max_products <= 0 or len(assignments) <= max_products:
        return assignments.copy()
    parts = []
    for severity, share in (("hard", 0.45), ("missing", 0.20), ("ok", 0.35)):
        subset = assignments[assignments["severity"] == severity]
        n = min(len(subset), int(max_products * share))
        if n:
            parts.append(subset.sample(n, random_state=17 + len(parts)))
    out = pd.concat(parts, ignore_index=True) if parts else assignments.head(max_products).copy()
    if len(out) < max_products:
        rest = assignments.drop(out.index, errors="ignore")
        out = pd.concat([out, rest.head(max_products - len(out))], ignore_index=True)
    return out.drop_duplicates("fdc_id", keep="first").head(max_products)


def nodes_edges(sample: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    nodes = []
    edges = []
    esha_seen = set()
    for _, row in sample.iterrows():
        product_id = f"p:{row['fdc_id']}"
        nodes.append(
            {
                "node_id": product_id,
                "node_type": "product",
                "label": row["product_description"],
                "family": row["category_lane"],
                "severity": row["severity"],
                "conflict_reason": row["conflict_reason"],
                "text": row["node_text"],
            }
        )
        code = str(row.get("esha_code") or "")
        if not code:
            continue
        esha_id = f"e:{code}"
        if esha_id not in esha_seen:
            esha_seen.add(esha_id)
            nodes.append(
                {
                    "node_id": esha_id,
                    "node_type": "esha",
                    "label": row["esha_description"],
                    "family": row["esha_head"],
                    "severity": "esha",
                    "conflict_reason": "",
                    "text": f"{row['esha_head']} {row['esha_description']}",
                }
            )
        edges.append(
            {
                "source": product_id,
                "target": esha_id,
                "severity": row["severity"],
                "conflict_reason": row["conflict_reason"],
                "product_description": row["product_description"],
                "esha_description": row["esha_description"],
                "assignment_source": row["assignment_source"],
            }
        )
    return pd.DataFrame(nodes), pd.DataFrame(edges)


def embed(nodes: pd.DataFrame) -> pd.DataFrame:
    if nodes.empty:
        return nodes.assign(x=[], y=[], z=[])
    vectorizer = TfidfVectorizer(max_features=12000, min_df=2, ngram_range=(1, 2))
    matrix = vectorizer.fit_transform(nodes["text"].astype(str))
    if matrix.shape[1] < 3 or len(nodes) < 3:
        coords = [[float(i), 0.0, 0.0] for i in range(len(nodes))]
    else:
        coords = StandardScaler().fit_transform(TruncatedSVD(n_components=3, random_state=19).fit_transform(matrix))
    out = nodes.copy()
    out["x"] = [float(c[0]) for c in coords]
    out["y"] = [float(c[1]) for c in coords]
    out["z"] = [float(c[2]) for c in coords]
    return out


def add_edge_lengths(edges: pd.DataFrame, nodes: pd.DataFrame) -> pd.DataFrame:
    if edges.empty:
        return edges.assign(edge_length=[])
    coords = nodes.set_index("node_id")[["x", "y", "z"]].to_dict("index")
    lengths = []
    for _, row in edges.iterrows():
        a = coords.get(row["source"])
        b = coords.get(row["target"])
        if not a or not b:
            lengths.append(0.0)
        else:
            lengths.append(math.sqrt((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2 + (a["z"] - b["z"]) ** 2))
    out = edges.copy()
    out["edge_length"] = [round(v, 4) for v in lengths]
    return out


def html_payload(nodes: pd.DataFrame, edges: pd.DataFrame, summary: dict[str, object]) -> str:
    node_cols = ["node_id", "node_type", "label", "family", "severity", "conflict_reason", "x", "y", "z"]
    edge_cols = ["source", "target", "severity", "conflict_reason", "product_description", "esha_description", "edge_length"]
    nodes_json = json.dumps(nodes[node_cols].to_dict("records"))
    edges_json = json.dumps(edges[edge_cols].to_dict("records"))
    top_rows = "\n".join(
        f"<tr><td>{html.escape(str(k))}</td><td>{v:,}</td></tr>"
        for k, v in Counter(edges.loc[edges["severity"] != "ok", "conflict_reason"].astype(str)).most_common(25)
    )
    summary_json = html.escape(json.dumps(summary, indent=2, sort_keys=True))
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Self-Heal Conflict Map</title>
  <style>
    body {{ margin: 24px; font-family: ui-sans-serif, system-ui, sans-serif; color: #1f2933; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, minmax(280px, 1fr)); gap: 16px; }}
    canvas {{ width: 100%; height: 420px; border: 1px solid #d8dee9; background: #fbfaf5; }}
    td, th {{ border-bottom: 1px solid #e5e7eb; padding: 6px 10px; text-align: left; }}
    pre {{ background: #f4f6f8; padding: 12px; overflow: auto; }}
  </style>
</head>
<body>
  <h1>Self-Heal Conflict Map</h1>
  <p>Red edges are hard category/head incompatibilities. Orange/missing rows are abstentions. Gray edges are compatible assignments.</p>
  <div class="grid">
    <div><h3>XY</h3><canvas id="xy" width="640" height="420"></canvas></div>
    <div><h3>XZ</h3><canvas id="xz" width="640" height="420"></canvas></div>
    <div><h3>YZ</h3><canvas id="yz" width="640" height="420"></canvas></div>
  </div>
  <h2>Top Conflict Reasons</h2>
  <table><tr><th>Reason</th><th>Edges</th></tr>{top_rows}</table>
  <h2>Summary</h2><pre>{summary_json}</pre>
  <script>
const nodes = {nodes_json};
const edges = {edges_json};
const byId = new Map(nodes.map(n => [n.node_id, n]));
function color(severity) {{
  if (severity === 'hard') return '#dc2626';
  if (severity === 'missing') return '#f59e0b';
  return '#b8bec8';
}}
function draw(canvasId, a, b) {{
  const c = document.getElementById(canvasId);
  const ctx = c.getContext('2d');
  const w = c.width, h = c.height, pad = 28;
  const valsA = nodes.map(n => n[a]);
  const valsB = nodes.map(n => n[b]);
  const minA = Math.min(...valsA), maxA = Math.max(...valsA);
  const minB = Math.min(...valsB), maxB = Math.max(...valsB);
  const sx = v => pad + (v - minA) / Math.max(maxA - minA, 1e-9) * (w - pad * 2);
  const sy = v => h - pad - (v - minB) / Math.max(maxB - minB, 1e-9) * (h - pad * 2);
  ctx.clearRect(0, 0, w, h);
  ctx.globalAlpha = 0.14;
  for (const e of edges) {{
    const s = byId.get(e.source), t = byId.get(e.target);
    if (!s || !t) continue;
    ctx.strokeStyle = color(e.severity);
    ctx.beginPath(); ctx.moveTo(sx(s[a]), sy(s[b])); ctx.lineTo(sx(t[a]), sy(t[b])); ctx.stroke();
  }}
  ctx.globalAlpha = 0.85;
  for (const n of nodes) {{
    const x = sx(n[a]), y = sy(n[b]);
    ctx.fillStyle = n.node_type === 'esha' ? '#111827' : color(n.severity);
    if (n.node_type === 'esha') ctx.fillRect(x - 2, y - 2, 4, 4);
    else {{ ctx.beginPath(); ctx.arc(x, y, 2.2, 0, Math.PI * 2); ctx.fill(); }}
  }}
}}
draw('xy', 'x', 'y'); draw('xz', 'x', 'z'); draw('yz', 'y', 'z');
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-map", type=Path, default=sh.VSELF_CSV)
    parser.add_argument("--product-facts", type=Path, default=sh.SELF_HEAL_DIR / "product_facts.csv")
    parser.add_argument("--max-products", type=int, default=15000)
    args = parser.parse_args()

    sh.SELF_HEAL_DIR.mkdir(parents=True, exist_ok=True)
    current = pd.read_csv(args.current_map, dtype=str, keep_default_na=False, low_memory=False)
    facts = pd.read_csv(args.product_facts, dtype=str, keep_default_na=False, low_memory=False)
    assignments = classify(current, facts)
    assignments.to_csv(OUT_ASSIGNMENTS, index=False)
    sample = balanced_sample(assignments, args.max_products)
    nodes, edges = nodes_edges(sample)
    nodes = embed(nodes)
    edges = add_edge_lengths(edges, nodes)
    nodes.to_csv(OUT_NODES, index=False)
    edges.to_csv(OUT_EDGES, index=False)
    summary = {
        "current_map": str(args.current_map),
        "assignments": int(len(assignments)),
        "sampled_products": int(len(sample)),
        "sampled_edges": int(len(edges)),
        "severity_counts": assignments["severity"].value_counts().to_dict(),
        "top_conflict_reasons": assignments.loc[assignments["severity"] != "ok", "conflict_reason"].value_counts().head(50).to_dict(),
        "top_hard_heads": assignments.loc[assignments["severity"] == "hard", "esha_head"].value_counts().head(50).to_dict(),
    }
    sh.summarize_json(OUT_SUMMARY, summary)
    OUT_HTML.write_text(html_payload(nodes, edges, summary), encoding="utf-8")
    print(f"wrote {OUT_HTML} ({len(sample):,} sampled products)", flush=True)


if __name__ == "__main__":
    main()
