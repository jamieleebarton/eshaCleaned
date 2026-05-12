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

import build_ingredient_fingerprint_clusters as ingredient_clusters


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"
DEFAULT_MAP_CSV = OUT_DIR / "product_to_best_esha_full_map.csv"
OUT_ASSIGNMENTS = OUT_DIR / "taxonomy_conflict_assignments.csv"
OUT_NODES = OUT_DIR / "taxonomy_conflict_nodes.csv"
OUT_EDGES = OUT_DIR / "taxonomy_conflict_edges.csv"
OUT_HTML = OUT_DIR / "taxonomy_conflict_map.html"
OUT_SUMMARY = OUT_DIR / "taxonomy_conflict_summary.json"


def esha_head(description: str) -> str:
    return str(description or "").split(",", 1)[0].strip()


def classify_assignments(features: pd.DataFrame, anchors: dict[str, ingredient_clusters.EshaAnchor]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    assigned = features[features["best_esha_code"].astype(str).str.strip() != ""]
    for _, product in assigned.iterrows():
        code = str(product.get("best_esha_code") or "").split(".")[0]
        anchor = anchors.get(code)
        ok, reason = ingredient_clusters.candidate_gate(product, anchor)
        evidence = set(product["_title_tokens"]) | set(product["_ingredient_tokens"])
        structural_reason = ingredient_clusters.form_mismatch_reason(product, anchor, evidence) if anchor else None
        display_reason = structural_reason or reason
        hard = ingredient_clusters.hard_quarantine(product, anchor, reason)
        severity = "ok" if ok else "hard" if hard else "soft"
        rows.append(
            {
                "gtin_upc": product["gtin_upc"],
                "fdc_id": product["fdc_id"],
                "product_description": product["product_description"],
                "branded_food_category": product["branded_food_category"],
                "brand_owner": product["brand_owner"],
                "brand_name": product["brand_name"],
                "esha_code": code,
                "esha_description": product.get("best_esha_description", ""),
                "esha_head": esha_head(product.get("best_esha_description", "")),
                "esha_family": product.get("best_esha_family", ""),
                "assignment_source": product.get("assignment_source", ""),
                "score": product.get("score", ""),
                "product_family": product["_product_family"],
                "primary_food": product["_primary"],
                "state_lane": product["_state_lane"],
                "ingredient_key": product["_ingredient_key"],
                "candidate_ok": bool(ok),
                "severity": severity,
                "conflict_reason": display_reason,
                "structural_reason": structural_reason or "",
            }
        )
    return pd.DataFrame(rows)


def balanced_assignment_sample(assignments: pd.DataFrame, max_products: int) -> pd.DataFrame:
    if max_products <= 0 or len(assignments) <= max_products:
        return assignments.copy()

    hard = assignments[assignments["severity"] == "hard"]
    soft = assignments[assignments["severity"] == "soft"]
    ok = assignments[assignments["severity"] == "ok"]

    hard_n = min(len(hard), max_products // 2)
    soft_n = min(len(soft), max_products // 3)
    ok_n = max_products - hard_n - soft_n
    if ok_n < 0:
        ok_n = 0

    parts = []
    if hard_n:
        parts.append(hard.sample(hard_n, random_state=17))
    if soft_n:
        parts.append(soft.sample(soft_n, random_state=23))
    if ok_n:
        parts.append(ok.sample(min(len(ok), ok_n), random_state=31))
    out = pd.concat(parts, ignore_index=True) if parts else assignments.head(max_products).copy()
    return out.drop_duplicates("gtin_upc", keep="first")


def build_nodes_and_edges(sample: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    product_nodes: list[dict[str, object]] = []
    esha_nodes: dict[str, dict[str, object]] = {}
    edges: list[dict[str, object]] = []

    for _, row in sample.iterrows():
        product_id = f"p:{row['gtin_upc']}"
        esha_id = f"e:{row['esha_code']}"
        product_text = " ".join(
            [
                str(row["product_description"]),
                str(row["branded_food_category"]),
                str(row["product_family"]),
                str(row["primary_food"]),
                str(row["state_lane"]),
                str(row["ingredient_key"]),
            ]
        )
        esha_text = " ".join(
            [
                str(row["esha_head"]),
                str(row["esha_description"]),
                str(row["esha_family"]),
            ]
        )
        product_nodes.append(
            {
                "node_id": product_id,
                "node_type": "product",
                "label": row["product_description"],
                "family": row["product_family"],
                "text": product_text,
                "gtin_upc": row["gtin_upc"],
                "fdc_id": row["fdc_id"],
                "esha_code": row["esha_code"],
                "severity": row["severity"],
                "conflict_reason": row["conflict_reason"],
            }
        )
        esha_nodes[esha_id] = {
            "node_id": esha_id,
            "node_type": "esha",
            "label": row["esha_description"],
            "family": row["esha_family"],
            "text": esha_text,
            "gtin_upc": "",
            "fdc_id": "",
            "esha_code": row["esha_code"],
            "severity": "esha",
            "conflict_reason": "",
        }
        edges.append(
            {
                "source": product_id,
                "target": esha_id,
                "gtin_upc": row["gtin_upc"],
                "fdc_id": row["fdc_id"],
                "product_description": row["product_description"],
                "branded_food_category": row["branded_food_category"],
                "esha_code": row["esha_code"],
                "esha_description": row["esha_description"],
                "esha_head": row["esha_head"],
                "severity": row["severity"],
                "conflict_reason": row["conflict_reason"],
                "assignment_source": row["assignment_source"],
            }
        )

    nodes = pd.DataFrame(product_nodes + list(esha_nodes.values()))
    edge_df = pd.DataFrame(edges)
    return nodes, edge_df


def embed_nodes(nodes: pd.DataFrame) -> pd.DataFrame:
    if nodes.empty:
        nodes["x"] = []
        nodes["y"] = []
        nodes["z"] = []
        return nodes
    vectorizer = TfidfVectorizer(max_features=12000, min_df=2, ngram_range=(1, 2))
    matrix = vectorizer.fit_transform(nodes["text"].astype(str))
    if matrix.shape[1] < 3 or len(nodes) < 3:
        coords = [[float(i), 0.0, 0.0] for i in range(len(nodes))]
    else:
        svd = TruncatedSVD(n_components=3, random_state=13)
        coords = svd.fit_transform(matrix)
        coords = StandardScaler().fit_transform(coords)
    out = nodes.copy()
    out["x"] = [float(c[0]) for c in coords]
    out["y"] = [float(c[1]) for c in coords]
    out["z"] = [float(c[2]) for c in coords]
    return out


def add_edge_lengths(edges: pd.DataFrame, nodes: pd.DataFrame) -> pd.DataFrame:
    coords = nodes.set_index("node_id")[["x", "y", "z"]].to_dict("index")
    lengths: list[float] = []
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


def html_payload(nodes: pd.DataFrame, edges: pd.DataFrame, summary: dict[str, object]) -> str:
    node_cols = ["node_id", "node_type", "label", "family", "severity", "conflict_reason", "x", "y", "z"]
    edge_cols = ["source", "target", "severity", "conflict_reason", "product_description", "esha_description", "edge_length"]
    node_records = nodes[node_cols].to_dict("records")
    edge_records = edges.sort_values(["severity", "edge_length"], ascending=[True, False])[edge_cols].to_dict("records")
    top_reasons = Counter(edges.loc[edges["severity"] != "ok", "conflict_reason"].astype(str)).most_common(20)
    top_rows = "\n".join(f"<tr><td>{html.escape(k)}</td><td>{v:,}</td></tr>" for k, v in top_reasons)
    summary_json = json.dumps(summary, indent=2, sort_keys=True)
    nodes_json = json.dumps(node_records)
    edges_json = json.dumps(edge_records)
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Taxonomy Conflict Map</title>
  <style>
    body {{ margin: 24px; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif; color: #1f2933; }}
    h1 {{ margin: 0 0 8px; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, minmax(280px, 1fr)); gap: 16px; }}
    canvas {{ width: 100%; height: 420px; border: 1px solid #d8dee9; background: #fbfaf5; }}
    .legend span {{ display: inline-block; margin-right: 16px; }}
    table {{ border-collapse: collapse; margin-top: 16px; }}
    td, th {{ border-bottom: 1px solid #e5e7eb; padding: 6px 10px; text-align: left; }}
    pre {{ background: #f4f6f8; padding: 12px; overflow: auto; }}
  </style>
</head>
<body>
  <h1>Taxonomy Conflict Map</h1>
  <p>Products and ESHA codes are embedded into the same TF-IDF/SVD space. Assignment edges connect products to their chosen ESHA code. Long red/orange edges are likely taxonomy breaks.</p>
  <div class="legend">
    <span style="color:#9ca3af">gray = passing assignment</span>
    <span style="color:#f59e0b">orange = soft conflict</span>
    <span style="color:#dc2626">red = hard conflict</span>
    <span style="color:#2563eb">blue dot = product</span>
    <span style="color:#111827">black square = ESHA code</span>
  </div>
  <div class="grid">
    <div><h3>XY</h3><canvas id="xy" width="640" height="420"></canvas></div>
    <div><h3>XZ</h3><canvas id="xz" width="640" height="420"></canvas></div>
    <div><h3>YZ</h3><canvas id="yz" width="640" height="420"></canvas></div>
  </div>
  <h2>Top Conflict Reasons</h2>
  <table><tr><th>Reason</th><th>Edges</th></tr>{top_rows}</table>
  <h2>Summary</h2>
  <pre>{html.escape(summary_json)}</pre>
  <script>
const nodes = {nodes_json};
const edges = {edges_json};
const byId = new Map(nodes.map(n => [n.node_id, n]));
function color(severity) {{
  if (severity === 'hard') return '#dc2626';
  if (severity === 'soft') return '#f59e0b';
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
    ctx.beginPath();
    ctx.moveTo(sx(s[a]), sy(s[b]));
    ctx.lineTo(sx(t[a]), sy(t[b]));
    ctx.stroke();
  }}
  ctx.globalAlpha = 0.85;
  for (const n of nodes) {{
    const x = sx(n[a]), y = sy(n[b]);
    if (n.node_type === 'esha') {{
      ctx.fillStyle = '#111827';
      ctx.fillRect(x - 2, y - 2, 4, 4);
    }} else {{
      ctx.fillStyle = n.severity === 'hard' ? '#dc2626' : n.severity === 'soft' ? '#f59e0b' : '#2563eb';
      ctx.beginPath();
      ctx.arc(x, y, 2.2, 0, Math.PI * 2);
      ctx.fill();
    }}
  }}
}}
draw('xy', 'x', 'y');
draw('xz', 'x', 'z');
draw('yz', 'y', 'z');
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-map", type=Path, default=DEFAULT_MAP_CSV)
    parser.add_argument("--max-products", type=int, default=15000)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("loading products", flush=True)
    products = ingredient_clusters.load_products()
    print(f"  products: {len(products):,}", flush=True)
    print(f"loading map: {args.current_map}", flush=True)
    current = ingredient_clusters.load_current_map(args.current_map)
    print(f"  map rows: {len(current):,}", flush=True)
    print("loading ESHA anchors", flush=True)
    anchors = ingredient_clusters.load_esha_anchors()
    print(f"  anchors: {len(anchors):,}", flush=True)
    print("building product features", flush=True)
    features = ingredient_clusters.build_product_features(products, current)
    print("classifying assignments", flush=True)
    assignments = classify_assignments(features, anchors)
    assignments.to_csv(OUT_ASSIGNMENTS, index=False)
    print(f"  wrote {OUT_ASSIGNMENTS.relative_to(ROOT)} ({len(assignments):,} rows)", flush=True)

    sample = balanced_assignment_sample(assignments, args.max_products)
    print(f"building graph sample: {len(sample):,} products", flush=True)
    nodes, edges = build_nodes_and_edges(sample)
    nodes = embed_nodes(nodes)
    edges = add_edge_lengths(edges, nodes)
    nodes.to_csv(OUT_NODES, index=False)
    edges.to_csv(OUT_EDGES, index=False)

    summary = {
        "current_map": str(args.current_map),
        "assigned_rows_classified": int(len(assignments)),
        "sampled_products": int(len(sample)),
        "sampled_nodes": int(len(nodes)),
        "sampled_edges": int(len(edges)),
        "severity_counts": assignments["severity"].value_counts().to_dict(),
        "top_conflict_reasons": assignments.loc[assignments["severity"] != "ok", "conflict_reason"].value_counts().head(30).to_dict(),
        "top_hard_heads": assignments.loc[assignments["severity"] == "hard", "esha_head"].value_counts().head(30).to_dict(),
        "top_hard_codes": assignments.loc[assignments["severity"] == "hard", "esha_code"].value_counts().head(30).to_dict(),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    OUT_HTML.write_text(html_payload(nodes, edges, summary), encoding="utf-8")
    print(f"  wrote {OUT_NODES.relative_to(ROOT)}", flush=True)
    print(f"  wrote {OUT_EDGES.relative_to(ROOT)}", flush=True)
    print(f"  wrote {OUT_HTML.relative_to(ROOT)}", flush=True)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
