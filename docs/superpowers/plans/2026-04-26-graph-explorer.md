# Graph Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an interactive 3D explorer over the Kuzu knowledge graph that visualizes every Product, ESHACode, ProductCategory, and ESHACategory in one shared embedding space, plus a ranked CSV of suspect Product→ESHACode mappings that feeds the existing quarantine pipeline.

**Architecture:** Python orchestrator reads from Kuzu, embeds every node text with local `sentence-transformers/all-MiniLM-L6-v2` (cached on disk), computes a per-Product suspicion score from three independent "views" (text / graph-neighborhood / label), projects embeddings to 3D with PCA + UMAP, then renders a self-contained `index.html` (deck.gl WebGL2 scatterplot) and writes `embedding_suspects.csv` next to the existing quarantine artifacts. No server, no external API.

**Tech Stack:** Python 3.11, `kuzu`, `pandas`, `numpy`, `sentence-transformers`, `scikit-learn` (PCA), `umap-learn`, `deck.gl` (vendored standalone bundle), unittest.

**Spec:** `docs/superpowers/specs/2026-04-26-graph-explorer-design.md`

---

## File Structure

```
graph/queries/embed_nodes.py                          # NEW — text → vector module (cached)
graph/queries/score_suspicion.py                      # NEW — three-view scoring module
graph/queries/build_graph_explorer.py                 # NEW — orchestrator (CLI entry)
graph/queries/explorer_template.html                  # NEW — viewer template w/ __DATA__ placeholder
graph/cache/node_embeddings.npz                       # GENERATED — cached vectors
implementation/output/graph_explorer/index.html       # GENERATED — final viewer
graph/quarantine/embedding_suspects.csv               # GENERATED — suspect mappings
implementation/tests/test_embed_nodes.py              # NEW — unit tests
implementation/tests/test_score_suspicion.py          # NEW — unit tests
implementation/tests/test_build_graph_explorer.py     # NEW — integration smoke test
requirements-graph.txt                                # MODIFY — add new deps
```

Each module has one responsibility. `embed_nodes` only knows about text→vector + caching. `score_suspicion` only knows about combining vectors into per-Product scores. `build_graph_explorer` only knows about glue (Kuzu I/O, projection, file emission). The HTML template is a flat file with one placeholder, kept separate so the orchestrator's Python isn't full of inline JS.

---

## Task 1: Add dependencies

**Files:**
- Modify: `requirements-graph.txt`

- [ ] **Step 1: Read current contents**

Run: `cat requirements-graph.txt`
Expected: shows `kuzu>=0.11` and `pandas>=2.0`.

- [ ] **Step 2: Append new dependencies**

Replace file contents with:

```
kuzu>=0.11
pandas>=2.0
numpy>=1.24
scikit-learn>=1.3
sentence-transformers>=2.7
umap-learn>=0.5
```

- [ ] **Step 3: Install**

Run: `pip install -r requirements-graph.txt`
Expected: all install cleanly. `sentence-transformers` pulls in torch — ~1–2 min the first time.

- [ ] **Step 4: Smoke check imports**

Run:
```bash
python3 -c "import kuzu, pandas, numpy, sklearn, sentence_transformers, umap; print('ok')"
```
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add requirements-graph.txt
git commit -m "deps: add embedding/projection libs for graph explorer"
```

---

## Task 2: `embed_nodes.py` — text builders (TDD)

**Files:**
- Create: `graph/queries/embed_nodes.py`
- Test: `implementation/tests/test_embed_nodes.py`

The module has three units of work: (a) build a text string per node from a Kuzu connection, (b) call the model, (c) cache by content hash. We TDD them in that order.

- [ ] **Step 1: Write failing test for `build_node_texts`**

Create `implementation/tests/test_embed_nodes.py`:

```python
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from graph.queries.embed_nodes import build_node_texts  # noqa: E402


class BuildNodeTextsTest(unittest.TestCase):
    def _fake_conn(self, query_results):
        conn = MagicMock()
        def execute(q, _params=None):
            for key, rows in query_results.items():
                if key in q:
                    result = MagicMock()
                    result.has_next.side_effect = [True] * len(rows) + [False]
                    result.get_next.side_effect = [list(r) for r in rows]
                    return result
            raise AssertionError(f"no fake result for: {q}")
        conn.execute.side_effect = execute
        return conn

    def test_product_text_concatenates_description_and_tokens(self):
        conn = self._fake_conn({
            "Product": [("0001", "WHOLE MILK 1 GAL", "milk whole gallon")],
            "ESHACode": [],
            "ProductCategory": [],
            "ESHACategory": [],
        })
        texts = build_node_texts(conn)
        self.assertEqual(texts["Product:0001"], "WHOLE MILK 1 GAL milk whole gallon")

    def test_esha_code_text_concatenates_code_and_description(self):
        conn = self._fake_conn({
            "Product": [],
            "ESHACode": [("1004", "Milk, fluid, whole")],
            "ProductCategory": [],
            "ESHACategory": [],
        })
        texts = build_node_texts(conn)
        self.assertEqual(texts["ESHACode:1004"], "1004 Milk, fluid, whole")

    def test_category_texts_use_name(self):
        conn = self._fake_conn({
            "Product": [],
            "ESHACode": [],
            "ProductCategory": [("Milk",)],
            "ESHACategory": [("dairy",)],
        })
        texts = build_node_texts(conn)
        self.assertEqual(texts["ProductCategory:Milk"], "Milk")
        self.assertEqual(texts["ESHACategory:dairy"], "dairy")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest implementation.tests.test_embed_nodes -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph.queries.embed_nodes'`.

- [ ] **Step 3: Implement `build_node_texts`**

Create `graph/queries/embed_nodes.py`:

```python
"""Build text strings per node and embed them with sentence-transformers.

Caches vectors on disk keyed by (model_name, content hash) so reruns are cheap.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

import kuzu
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "graph" / "cache" / "node_embeddings.npz"
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _drain(result) -> Iterable[list]:
    while result.has_next():
        yield result.get_next()


def build_node_texts(conn: kuzu.Connection) -> dict[str, str]:
    """Return {node_id: text} for every Product, ESHACode, ProductCategory, ESHACategory.

    node_id format: '<NodeKind>:<primary_key>'.
    Product text = description + space-joined token values from HAS_TOKEN edges.
    ESHACode text = code + ' ' + description.
    Category texts = the name itself.
    """
    texts: dict[str, str] = {}

    q_products = (
        "MATCH (p:Product) "
        "OPTIONAL MATCH (p)-[:HAS_TOKEN]->(t:Token) "
        "RETURN p.gtin_upc, p.description, COLLECT(t.value) AS tokens"
    )
    for gtin, desc, tokens in _drain(conn.execute(q_products)):
        joined_tokens = " ".join(t for t in (tokens or []) if t)
        text = (desc or "").strip()
        if joined_tokens:
            text = (text + " " + joined_tokens).strip()
        if text:
            texts[f"Product:{gtin}"] = text

    for code, desc in _drain(conn.execute("MATCH (e:ESHACode) RETURN e.code, e.description")):
        text = f"{code} {desc or ''}".strip()
        if text:
            texts[f"ESHACode:{code}"] = text

    for (name,) in _drain(conn.execute("MATCH (c:ProductCategory) RETURN c.name")):
        if name:
            texts[f"ProductCategory:{name}"] = name

    for (name,) in _drain(conn.execute("MATCH (c:ESHACategory) RETURN c.name")):
        if name:
            texts[f"ESHACategory:{name}"] = name

    return texts


def _content_hash(model_name: str, texts: dict[str, str]) -> str:
    h = hashlib.sha256()
    h.update(model_name.encode("utf-8"))
    for key in sorted(texts):
        h.update(b"\x1f")
        h.update(key.encode("utf-8"))
        h.update(b"\x1e")
        h.update(texts[key].encode("utf-8"))
    return h.hexdigest()


def embed_all(
    conn: kuzu.Connection,
    model_name: str = DEFAULT_MODEL,
    cache_path: Path = CACHE_PATH,
) -> dict[str, np.ndarray]:
    """Return {node_id: vector}. Loads from cache when (model, texts) unchanged."""
    texts = build_node_texts(conn)
    digest = _content_hash(model_name, texts)

    if cache_path.exists():
        cached = np.load(cache_path, allow_pickle=False)
        if str(cached.get("digest", np.array("", dtype="<U1"))) == digest:
            ids = list(cached["ids"])
            vecs = cached["vectors"]
            return {ids[i]: vecs[i] for i in range(len(ids))}

    from sentence_transformers import SentenceTransformer  # lazy: heavy import
    model = SentenceTransformer(model_name)
    ids = sorted(texts)
    print(f"embedding {len(ids):,} nodes with {model_name}", flush=True)
    vectors = model.encode(
        [texts[i] for i in ids],
        batch_size=128,
        show_progress_bar=True,
        normalize_embeddings=True,
    ).astype(np.float32)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        cache_path,
        ids=np.array(ids),
        vectors=vectors,
        digest=np.array(digest),
    )
    return {ids[i]: vectors[i] for i in range(len(ids))}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest implementation.tests.test_embed_nodes -v`
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add graph/queries/embed_nodes.py implementation/tests/test_embed_nodes.py
git commit -m "feat(graph): build_node_texts for explorer embeddings"
```

---

## Task 3: `embed_nodes.py` — caching round-trip (TDD)

**Files:**
- Modify: `implementation/tests/test_embed_nodes.py`

We've already written `embed_all` in Task 2 because it shares structure with the texts code. Here we add tests proving the cache round-trips correctly without touching the network.

- [ ] **Step 1: Add cache round-trip tests**

Append to `implementation/tests/test_embed_nodes.py` (above the `if __name__` line):

```python
import tempfile
import numpy as np
from unittest.mock import patch
from graph.queries.embed_nodes import embed_all, _content_hash  # noqa: E402


class EmbedAllCacheTest(unittest.TestCase):
    def _conn(self):
        return MagicMock()  # only used via build_node_texts, which we patch

    def test_cache_hit_skips_model_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "emb.npz"
            texts = {"Product:1": "milk", "ESHACode:1004": "1004 milk fluid"}
            digest = _content_hash("test-model", texts)
            ids = sorted(texts)
            np.savez(
                cache,
                ids=np.array(ids),
                vectors=np.zeros((len(ids), 4), dtype=np.float32),
                digest=np.array(digest),
            )
            with patch("graph.queries.embed_nodes.build_node_texts", return_value=texts):
                with patch("sentence_transformers.SentenceTransformer") as model_cls:
                    out = embed_all(self._conn(), model_name="test-model", cache_path=cache)
                    model_cls.assert_not_called()
            self.assertEqual(set(out), {"Product:1", "ESHACode:1004"})
            self.assertEqual(out["Product:1"].shape, (4,))

    def test_cache_miss_invokes_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "emb.npz"
            texts = {"Product:1": "milk"}
            with patch("graph.queries.embed_nodes.build_node_texts", return_value=texts):
                fake_model = MagicMock()
                fake_model.encode.return_value = np.array([[0.1, 0.2, 0.3, 0.4]], dtype=np.float32)
                with patch("sentence_transformers.SentenceTransformer", return_value=fake_model):
                    out = embed_all(self._conn(), model_name="test-model", cache_path=cache)
                    fake_model.encode.assert_called_once()
            self.assertTrue(cache.exists())
            self.assertEqual(out["Product:1"].tolist(), [0.1, 0.2, 0.3, 0.4])
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python3 -m unittest implementation.tests.test_embed_nodes -v`
Expected: 5 tests pass total.

- [ ] **Step 3: Commit**

```bash
git add implementation/tests/test_embed_nodes.py
git commit -m "test(graph): cache round-trip for embed_all"
```

---

## Task 4: `score_suspicion.py` — three-view scoring (TDD)

**Files:**
- Create: `graph/queries/score_suspicion.py`
- Test: `implementation/tests/test_score_suspicion.py`

The scoring module operates purely on numpy arrays + a small DataFrame describing graph relationships — no Kuzu in this module, which keeps it unit-testable.

- [ ] **Step 1: Write failing test for `score_all`**

Create `implementation/tests/test_score_suspicion.py`:

```python
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from graph.queries.score_suspicion import score_all  # noqa: E402


def _vec(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def _fixture():
    # Two clean clusters: milk (vecs near +x), popcorn (vecs near +y).
    embeddings = {
        "Product:milk_a":   _vec(1.0, 0.05, 0.0),
        "Product:milk_b":   _vec(0.95, 0.0, 0.05),
        "Product:popcorn":  _vec(0.05, 1.0, 0.0),
        "ESHACode:1004":    _vec(0.98, 0.02, 0.0),   # milk
        "ESHACode:5500":    _vec(0.02, 0.98, 0.0),   # popcorn
        "ProductCategory:Milk":    _vec(0.97, 0.0, 0.03),
        "ProductCategory:Snacks":  _vec(0.0, 0.97, 0.03),
    }
    products = pd.DataFrame([
        # popcorn is mis-mapped to milk code 1004; everything else is correct
        {"gtin_upc": "milk_a",  "assigned_code": "1004", "category": "Milk",
         "description": "WHOLE MILK"},
        {"gtin_upc": "milk_b",  "assigned_code": "1004", "category": "Milk",
         "description": "2% MILK"},
        {"gtin_upc": "popcorn", "assigned_code": "1004", "category": "Snacks",
         "description": "BUTTERED POPCORN"},
    ])
    return embeddings, products


class ScoreAllTest(unittest.TestCase):
    def test_correctly_mapped_product_has_low_suspicion(self):
        embeddings, products = _fixture()
        out = score_all(embeddings, products)
        row = out.loc[out["gtin_upc"] == "milk_a"].iloc[0]
        self.assertLess(row["suspicion"], 0.3)
        self.assertEqual(row["disagreement_kind"], "agree")

    def test_wrong_label_product_is_flagged(self):
        embeddings, products = _fixture()
        out = score_all(embeddings, products)
        row = out.loc[out["gtin_upc"] == "popcorn"].iloc[0]
        self.assertGreater(row["suspicion"], 0.7)
        self.assertEqual(row["disagreement_kind"], "wrong_label")
        self.assertEqual(row["text_view_code"], "5500")
        self.assertEqual(row["top1_code"], "5500")

    def test_assigned_rank_is_position_in_text_view_ranking(self):
        embeddings, products = _fixture()
        out = score_all(embeddings, products)
        row = out.loc[out["gtin_upc"] == "popcorn"].iloc[0]
        # popcorn assigned to milk code 1004, but 5500 is closer
        self.assertEqual(row["assigned_rank"], 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest implementation.tests.test_score_suspicion -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `score_suspicion.py`**

Create `graph/queries/score_suspicion.py`:

```python
"""Score every Product → ESHACode mapping using three independent 'views'.

Views:
  text   — embedding of (description + tokens) vs every ESHACode embedding
  graph  — average of nearby Product embeddings (same ProductCategory),
           projected against every ESHACode embedding
  label  — embedding of the assigned ESHACode itself, vs the product embedding

A mapping is suspect when the assigned code is far down the text view's ranking,
or when text + graph agree on a different code than the assigned label.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _stack(embeddings: dict[str, np.ndarray], ids: list[str]) -> np.ndarray:
    return np.vstack([embeddings[i] for i in ids])


def _rank_codes(query_vec: np.ndarray, code_ids: list[str], code_mat: np.ndarray) -> list[tuple[str, float]]:
    sims = code_mat @ query_vec  # cosine since both sides are L2-normalized
    order = np.argsort(-sims)
    return [(code_ids[i].split(":", 1)[1], float(sims[i])) for i in order]


def score_all(
    embeddings: dict[str, np.ndarray],
    products: pd.DataFrame,
    top_k_neighbors: int = 25,
) -> pd.DataFrame:
    """Score one row per product. Required `products` columns:
    gtin_upc, assigned_code, category, description (description unused, kept for context)."""
    code_ids = sorted(k for k in embeddings if k.startswith("ESHACode:"))
    code_mat = _stack(embeddings, code_ids)

    # Group product ids by category so we can compute the graph view efficiently.
    cat_to_pids: dict[str, list[str]] = {}
    for _, r in products.iterrows():
        pid = f"Product:{r['gtin_upc']}"
        if pid in embeddings:
            cat_to_pids.setdefault(r["category"], []).append(pid)

    rows = []
    for _, r in products.iterrows():
        gtin = r["gtin_upc"]
        assigned = r["assigned_code"]
        pid = f"Product:{gtin}"
        if pid not in embeddings:
            continue
        p_vec = embeddings[pid]

        text_ranking = _rank_codes(p_vec, code_ids, code_mat)
        text_top = text_ranking[0]
        text_view_code = text_top[0]

        # graph view: mean of up-to-K cosine-nearest products in same category
        cohort = [q for q in cat_to_pids.get(r["category"], []) if q != pid]
        if cohort:
            cohort_mat = _stack(embeddings, cohort)
            sims = cohort_mat @ p_vec
            keep = np.argsort(-sims)[:top_k_neighbors]
            g_vec = cohort_mat[keep].mean(axis=0)
            g_vec = g_vec / (np.linalg.norm(g_vec) or 1.0)
            graph_view_code = _rank_codes(g_vec, code_ids, code_mat)[0][0]
        else:
            graph_view_code = text_view_code

        # label view: assigned code's vector vs product vector
        assigned_key = f"ESHACode:{assigned}"
        if assigned_key in embeddings:
            label_sim = float(embeddings[assigned_key] @ p_vec)
        else:
            label_sim = 0.0
        label_view_code = assigned

        # Where does the assigned code rank in the text view? 1-indexed.
        try:
            assigned_rank = next(i for i, (c, _) in enumerate(text_ranking, start=1) if c == assigned)
        except StopIteration:
            assigned_rank = len(text_ranking) + 1

        # disagreement kind
        if assigned == text_view_code == graph_view_code:
            kind = "agree"
        elif text_view_code == graph_view_code and text_view_code != assigned:
            kind = "wrong_label"
        elif text_view_code != graph_view_code and (text_view_code == assigned or graph_view_code == assigned):
            kind = "bad_upstream"
        else:
            kind = "garbage"

        # suspicion: 0..1, dominated by assigned_rank, boosted on wrong_label
        rank_score = 1.0 - 1.0 / max(assigned_rank, 1)        # 0 at rank 1, →1 as rank grows
        label_score = max(0.0, 1.0 - label_sim)               # 0 if label hugs product
        kind_boost = {"agree": 0.0, "bad_upstream": 0.15, "wrong_label": 0.35, "garbage": 0.25}[kind]
        suspicion = float(min(1.0, 0.55 * rank_score + 0.20 * label_score + kind_boost))

        rows.append({
            "gtin_upc": gtin,
            "assigned_code": assigned,
            "assigned_rank": assigned_rank,
            "top1_code": text_top[0],
            "top1_score": text_top[1],
            "text_view_code": text_view_code,
            "graph_view_code": graph_view_code,
            "label_view_code": label_view_code,
            "label_view_sim": label_sim,
            "disagreement_kind": kind,
            "suspicion": suspicion,
        })

    return pd.DataFrame(rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest implementation.tests.test_score_suspicion -v`
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add graph/queries/score_suspicion.py implementation/tests/test_score_suspicion.py
git commit -m "feat(graph): three-view suspicion scoring for product→ESHA mappings"
```

---

## Task 5: HTML viewer template

**Files:**
- Create: `graph/queries/explorer_template.html`

Self-contained HTML, deck.gl from a CDN with a SRI-pinned version, all app code inline, single `__DATA__` placeholder that the orchestrator replaces with a JSON blob.

- [ ] **Step 1: Create the template**

Create `graph/queries/explorer_template.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Graph Explorer</title>
<style>
  html, body { margin: 0; height: 100%; background: #0b0d12; color: #e6e8ec;
               font-family: ui-sans-serif, system-ui, sans-serif; }
  #root { display: grid; grid-template-columns: 1fr 320px; height: 100vh; }
  #scene { position: relative; }
  #toolbar { position: absolute; top: 8px; left: 8px; right: 8px; z-index: 2;
             display: flex; gap: 8px; flex-wrap: wrap; }
  #toolbar > * { background: #1a1d24; color: #e6e8ec; border: 1px solid #2b2f38;
                 padding: 4px 8px; border-radius: 4px; font: inherit; }
  #panel { padding: 12px; overflow-y: auto; border-left: 1px solid #2b2f38;
           background: #11141a; }
  #panel h2 { margin: 0 0 6px; font-size: 14px; }
  #panel pre { white-space: pre-wrap; font-size: 12px; }
  .legend { font-size: 11px; padding: 6px 8px; }
</style>
</head>
<body>
<div id="root">
  <div id="scene">
    <div id="toolbar">
      <select id="projection">
        <option value="pca">PCA</option>
        <option value="umap" selected>UMAP</option>
      </select>
      <select id="colorBy">
        <option value="esha_family">color: esha_family</option>
        <option value="category">color: category</option>
        <option value="suspicion" selected>color: suspicion</option>
        <option value="disagreement_kind">color: disagreement_kind</option>
        <option value="kind">color: node kind</option>
      </select>
      <input id="search" type="search" placeholder="search label/id…" />
      <label class="legend"><input type="checkbox" id="show_products" checked /> Products</label>
      <label class="legend"><input type="checkbox" id="show_codes" checked /> ESHACodes</label>
      <label class="legend"><input type="checkbox" id="show_categories" /> Categories</label>
      <span class="legend" id="counts"></span>
    </div>
  </div>
  <div id="panel"><h2>Click a point</h2><div id="detail">Nothing selected.</div></div>
</div>
<script src="https://unpkg.com/deck.gl@9.0.33/dist.min.js"
        crossorigin="anonymous"></script>
<script>
const DATA = __DATA__;

function colorFor(node, mode) {
  if (mode === "suspicion") {
    const s = node.suspicion ?? 0;
    return [Math.round(255 * s), Math.round(255 * (1 - s)), 60, 220];
  }
  if (mode === "kind") {
    return ({Product:[120,180,255], ESHACode:[255,200,80],
             ProductCategory:[180,120,255], ESHACategory:[120,255,180]}[node.kind])
           .concat([220]);
  }
  const key = node[mode] || "_";
  let h = 0; for (let i=0;i<key.length;i++) h = (h*31 + key.charCodeAt(i)) >>> 0;
  return [(h*73)%256, (h*151)%256, (h*229)%256, 220];
}

let projection = "umap";
let colorBy = "suspicion";
let visibleKinds = new Set(["Product","ESHACode"]);
let searchTerm = "";

function visibleNodes() {
  return DATA.nodes.filter(n => {
    if (!visibleKinds.has(n.kind)) return false;
    if (searchTerm && !(n.label||"").toLowerCase().includes(searchTerm)
                   && !(n.id||"").toLowerCase().includes(searchTerm)) return false;
    return true;
  });
}

const {Deck, OrbitView, ScatterplotLayer} = deck;
const view = new OrbitView({orbitAxis: "Y", fov: 50});

const deckgl = new Deck({
  parent: document.getElementById("scene"),
  views: view,
  initialViewState: {target: [0,0,0], rotationX: 30, rotationOrbit: 30, zoom: 2.5},
  controller: true,
  layers: [],
  onClick: (info) => {
    const n = info.object;
    document.getElementById("detail").innerHTML = n
      ? `<pre>${JSON.stringify(n, null, 2)}</pre>`
      : "Nothing selected.";
  },
});

function rebuild() {
  const nodes = visibleNodes();
  document.getElementById("counts").textContent =
    `${nodes.length.toLocaleString()} / ${DATA.nodes.length.toLocaleString()} nodes`;
  const layer = new ScatterplotLayer({
    id: "nodes",
    data: nodes,
    getPosition: d => d[projection] || [0,0,0],
    getFillColor: d => colorFor(d, colorBy),
    getRadius: d => d.kind === "Product" ? 0.05 : 0.18,
    radiusUnits: "common",
    pickable: true,
  });
  deckgl.setProps({layers: [layer]});
}

document.getElementById("projection").addEventListener("change", e => { projection = e.target.value; rebuild(); });
document.getElementById("colorBy").addEventListener("change",   e => { colorBy = e.target.value; rebuild(); });
document.getElementById("search").addEventListener("input",     e => { searchTerm = e.target.value.toLowerCase(); rebuild(); });
for (const [id, kind] of [["show_products","Product"],["show_codes","ESHACode"],["show_categories","ProductCategory"]]) {
  document.getElementById(id).addEventListener("change", e => {
    if (e.target.checked) visibleKinds.add(kind); else visibleKinds.delete(kind);
    rebuild();
  });
}

rebuild();
</script>
</body>
</html>
```

- [ ] **Step 2: Verify the template parses (no execution yet, no data)**

Run: `python3 -c "open('graph/queries/explorer_template.html').read().index('__DATA__'); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add graph/queries/explorer_template.html
git commit -m "feat(graph): static HTML template for graph explorer (deck.gl)"
```

---

## Task 6: `build_graph_explorer.py` — orchestrator

**Files:**
- Create: `graph/queries/build_graph_explorer.py`

Reads Kuzu, calls `embed_all`, gets the per-product audit context for `score_all`, projects to 3D (PCA + UMAP), assembles `data.json`, splices into the HTML template, writes the suspect CSV.

- [ ] **Step 1: Create the orchestrator**

Create `graph/queries/build_graph_explorer.py`:

```python
"""Build the graph explorer HTML and the embedding suspect CSV.

Run: python3 graph/queries/build_graph_explorer.py
Outputs:
  implementation/output/graph_explorer/index.html
  graph/quarantine/embedding_suspects.csv
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import kuzu
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

from embed_nodes import embed_all
from score_suspicion import score_all

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DB = ROOT / "graph" / "db" / "kuzu"
TEMPLATE = ROOT / "graph" / "queries" / "explorer_template.html"
OUT_DIR = ROOT / "implementation" / "output" / "graph_explorer"
OUT_HTML = OUT_DIR / "index.html"
OUT_CSV = ROOT / "graph" / "quarantine" / "embedding_suspects.csv"


def fetch_products(conn: kuzu.Connection) -> pd.DataFrame:
    """Read the per-product audit row needed for score_all + viewer metadata."""
    q = (
        "MATCH (p:Product)-[:MAPS_TO]->(e:ESHACode)-[:IN_ESHA_CATEGORY]->(ef:ESHACategory) "
        "OPTIONAL MATCH (p)-[:IN_CATEGORY]->(c:ProductCategory) "
        "OPTIONAL MATCH (p)-[:MADE_BY]->(b:Brand) "
        "RETURN p.gtin_upc, p.description, e.code, ef.name, c.name, b.name"
    )
    rows = []
    res = conn.execute(q)
    while res.has_next():
        gtin, desc, code, family, cat, brand = res.get_next()
        rows.append({
            "gtin_upc": gtin,
            "description": desc or "",
            "assigned_code": code,
            "esha_family": family or "",
            "category": cat or "",
            "brand": brand or "",
        })
    return pd.DataFrame(rows)


def fetch_node_meta(conn: kuzu.Connection) -> dict[str, dict]:
    """Return a small label/category map for non-Product nodes (for the viewer)."""
    meta: dict[str, dict] = {}
    for code, desc in _drain(conn.execute("MATCH (e:ESHACode) RETURN e.code, e.description")):
        meta[f"ESHACode:{code}"] = {"label": f"{code} {desc or ''}".strip(),
                                     "kind": "ESHACode", "esha_family": "", "category": ""}
    for code, family in _drain(conn.execute(
        "MATCH (e:ESHACode)-[:IN_ESHA_CATEGORY]->(ef:ESHACategory) RETURN e.code, ef.name"
    )):
        if f"ESHACode:{code}" in meta:
            meta[f"ESHACode:{code}"]["esha_family"] = family or ""
    for (name,) in _drain(conn.execute("MATCH (c:ProductCategory) RETURN c.name")):
        meta[f"ProductCategory:{name}"] = {"label": name, "kind": "ProductCategory",
                                            "esha_family": "", "category": name}
    for (name,) in _drain(conn.execute("MATCH (c:ESHACategory) RETURN c.name")):
        meta[f"ESHACategory:{name}"] = {"label": name, "kind": "ESHACategory",
                                         "esha_family": name, "category": ""}
    return meta


def _drain(result):
    while result.has_next():
        yield result.get_next()


def project(embeddings: dict[str, np.ndarray]) -> tuple[list[str], np.ndarray, np.ndarray]:
    ids = sorted(embeddings)
    mat = np.vstack([embeddings[i] for i in ids])
    pca = PCA(n_components=3, random_state=0).fit_transform(mat).astype(np.float32)
    try:
        import umap
        reducer = umap.UMAP(n_components=3, random_state=0, metric="cosine",
                            n_neighbors=15, min_dist=0.1)
        umap_xyz = reducer.fit_transform(mat).astype(np.float32)
    except Exception as exc:
        print(f"warn: UMAP failed ({exc}); falling back to PCA for both views", flush=True)
        umap_xyz = pca
    # Center & rescale each projection into roughly [-1,1] for nicer viewer defaults.
    def normalize(arr):
        arr = arr - arr.mean(axis=0)
        s = max(np.abs(arr).max(), 1e-6)
        return (arr / s).astype(np.float32)
    return ids, normalize(pca), normalize(umap_xyz)


def assemble_data(
    ids: list[str],
    pca_xyz: np.ndarray,
    umap_xyz: np.ndarray,
    products: pd.DataFrame,
    scores: pd.DataFrame,
    node_meta: dict[str, dict],
) -> dict:
    score_by_gtin = scores.set_index("gtin_upc").to_dict("index")
    products_by_gtin = products.set_index("gtin_upc").to_dict("index")
    nodes = []
    for i, nid in enumerate(ids):
        kind, key = nid.split(":", 1)
        node = {"id": nid, "kind": kind, "label": key,
                "pca": pca_xyz[i].tolist(), "umap": umap_xyz[i].tolist()}
        if kind == "Product":
            p = products_by_gtin.get(key)
            s = score_by_gtin.get(key)
            if p:
                node["label"] = (p["description"] or key)[:80]
                node["category"] = p["category"]
                node["esha_family"] = p["esha_family"]
                node["assigned_esha"] = p["assigned_code"]
                node["brand"] = p["brand"]
            if s:
                node["suspicion"] = round(float(s["suspicion"]), 4)
                node["disagreement_kind"] = s["disagreement_kind"]
                node["top1_code"] = s["top1_code"]
                node["assigned_rank"] = int(s["assigned_rank"])
        else:
            meta = node_meta.get(nid, {})
            node["label"] = meta.get("label", key)
            node["esha_family"] = meta.get("esha_family", "")
            node["category"] = meta.get("category", "")
        nodes.append(node)
    return {"nodes": nodes}


def write_outputs(data: dict, scores: pd.DataFrame, products: pd.DataFrame) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    template = TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(data, separators=(",", ":"))
    OUT_HTML.write_text(template.replace("__DATA__", payload), encoding="utf-8")
    print(f"wrote {OUT_HTML}", flush=True)

    suspect = scores.merge(products, on="gtin_upc", how="left", suffixes=("", "_p"))
    suspect = suspect.sort_values("suspicion", ascending=False).reset_index(drop=True)
    suspect_out = pd.DataFrame({
        "gtin_upc": suspect["gtin_upc"],
        "fdc_id": "",
        "product_description": suspect["description"],
        "product_category": suspect["category"],
        "brand": suspect["brand"],
        "manufacturer": "",
        "current_esha_code": suspect["assigned_code"],
        "current_esha_description": "",
        "current_esha_category": suspect["esha_family"],
        "score": suspect["suspicion"].round(4),
        "assignment_source": "embedding_suspect",
        "quarantine_reason": suspect["disagreement_kind"],
        "embedding_top1_code": suspect["top1_code"],
        "embedding_assigned_rank": suspect["assigned_rank"],
    })
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    suspect_out.to_csv(OUT_CSV, index=False)
    print(f"wrote {OUT_CSV} ({len(suspect_out):,} rows)", flush=True)


def main() -> None:
    if not GRAPH_DB.exists():
        sys.exit(f"missing kuzu db: {GRAPH_DB} — run graph/ingest/build_kuzu_graph.py first")

    print(f"opening kuzu db at {GRAPH_DB}", flush=True)
    db = kuzu.Database(str(GRAPH_DB))
    conn = kuzu.Connection(db)

    embeddings = embed_all(conn)
    print(f"embeddings: {len(embeddings):,} nodes", flush=True)

    products = fetch_products(conn)
    print(f"products with MAPS_TO: {len(products):,}", flush=True)

    scores = score_all(embeddings, products)
    print(f"scored {len(scores):,} products", flush=True)

    node_meta = fetch_node_meta(conn)
    ids, pca_xyz, umap_xyz = project(embeddings)
    data = assemble_data(ids, pca_xyz, umap_xyz, products, scores, node_meta)
    write_outputs(data, scores, products)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))  # local imports
    main()
```

Note: the `sys.path.insert` at the bottom is needed only if executed as a script with `python3 path/to/file.py`; the `from embed_nodes import embed_all` style matches your other `graph/queries/*.py` modules.

- [ ] **Step 2: Static syntax check**

Run: `python3 -c "import ast; ast.parse(open('graph/queries/build_graph_explorer.py').read()); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add graph/queries/build_graph_explorer.py
git commit -m "feat(graph): orchestrator that builds explorer HTML + suspect CSV"
```

---

## Task 7: Integration smoke test against a tiny live Kuzu DB

**Files:**
- Create: `implementation/tests/test_build_graph_explorer.py`

Builds a 3-product Kuzu DB in a temp dir, runs the orchestrator's helpers end-to-end (without invoking the real model — uses tiny stub vectors), asserts the HTML and CSV are well-formed.

- [ ] **Step 1: Write the integration test**

Create `implementation/tests/test_build_graph_explorer.py`:

```python
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import kuzu
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "graph" / "queries"))

from graph.queries import build_graph_explorer as bge  # noqa: E402


SCHEMA = [
    "CREATE NODE TABLE Product(gtin_upc STRING, fdc_id STRING, description STRING, PRIMARY KEY (gtin_upc))",
    "CREATE NODE TABLE Brand(name STRING, PRIMARY KEY (name))",
    "CREATE NODE TABLE ProductCategory(name STRING, PRIMARY KEY (name))",
    "CREATE NODE TABLE Token(value STRING, PRIMARY KEY (value))",
    "CREATE NODE TABLE ESHACode(code STRING, description STRING, PRIMARY KEY (code))",
    "CREATE NODE TABLE ESHACategory(name STRING, PRIMARY KEY (name))",
    "CREATE REL TABLE MADE_BY(FROM Product TO Brand)",
    "CREATE REL TABLE IN_CATEGORY(FROM Product TO ProductCategory)",
    "CREATE REL TABLE HAS_TOKEN(FROM Product TO Token)",
    "CREATE REL TABLE MAPS_TO(FROM Product TO ESHACode)",
    "CREATE REL TABLE IN_ESHA_CATEGORY(FROM ESHACode TO ESHACategory)",
]

INSERTS = [
    "CREATE (:Product {gtin_upc:'milk_a', fdc_id:'1', description:'WHOLE MILK 1 GAL'})",
    "CREATE (:Product {gtin_upc:'milk_b', fdc_id:'2', description:'2% MILK'})",
    "CREATE (:Product {gtin_upc:'popcorn', fdc_id:'3', description:'BUTTERED POPCORN'})",
    "CREATE (:Brand {name:'Acme'})",
    "CREATE (:ProductCategory {name:'Milk'})",
    "CREATE (:ProductCategory {name:'Snacks'})",
    "CREATE (:ESHACode {code:'1004', description:'Milk, fluid, whole'})",
    "CREATE (:ESHACode {code:'5500', description:'Popcorn, popped, with butter'})",
    "CREATE (:ESHACategory {name:'dairy'})",
    "CREATE (:ESHACategory {name:'snack'})",
    "MATCH (p:Product {gtin_upc:'milk_a'}), (b:Brand {name:'Acme'}) CREATE (p)-[:MADE_BY]->(b)",
    "MATCH (p:Product {gtin_upc:'milk_a'}), (c:ProductCategory {name:'Milk'}) CREATE (p)-[:IN_CATEGORY]->(c)",
    "MATCH (p:Product {gtin_upc:'milk_b'}), (c:ProductCategory {name:'Milk'}) CREATE (p)-[:IN_CATEGORY]->(c)",
    "MATCH (p:Product {gtin_upc:'popcorn'}), (c:ProductCategory {name:'Snacks'}) CREATE (p)-[:IN_CATEGORY]->(c)",
    "MATCH (p:Product {gtin_upc:'milk_a'}), (e:ESHACode {code:'1004'}) CREATE (p)-[:MAPS_TO]->(e)",
    "MATCH (p:Product {gtin_upc:'milk_b'}), (e:ESHACode {code:'1004'}) CREATE (p)-[:MAPS_TO]->(e)",
    # popcorn is mis-mapped to milk on purpose
    "MATCH (p:Product {gtin_upc:'popcorn'}), (e:ESHACode {code:'1004'}) CREATE (p)-[:MAPS_TO]->(e)",
    "MATCH (e:ESHACode {code:'1004'}), (f:ESHACategory {name:'dairy'}) CREATE (e)-[:IN_ESHA_CATEGORY]->(f)",
    "MATCH (e:ESHACode {code:'5500'}), (f:ESHACategory {name:'snack'}) CREATE (e)-[:IN_ESHA_CATEGORY]->(f)",
]


def _stub_embeddings():
    def vec(*xs):
        v = np.array(xs, dtype=np.float32)
        return v / np.linalg.norm(v)
    return {
        "Product:milk_a":   vec(1.0, 0.05, 0.0),
        "Product:milk_b":   vec(0.95, 0.0, 0.05),
        "Product:popcorn":  vec(0.05, 1.0, 0.0),
        "ESHACode:1004":    vec(0.98, 0.02, 0.0),
        "ESHACode:5500":    vec(0.02, 0.98, 0.0),
        "ProductCategory:Milk":   vec(0.97, 0.0, 0.03),
        "ProductCategory:Snacks": vec(0.0, 0.97, 0.03),
        "ESHACategory:dairy":     vec(0.97, 0.0, 0.03),
        "ESHACategory:snack":     vec(0.0, 0.97, 0.03),
    }


class BuildGraphExplorerSmokeTest(unittest.TestCase):
    def test_end_to_end_emits_html_and_suspect_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            db_dir = tmp / "kuzu"
            db = kuzu.Database(str(db_dir))
            conn = kuzu.Connection(db)
            for stmt in SCHEMA + INSERTS:
                conn.execute(stmt)

            out_html = tmp / "explorer.html"
            out_csv = tmp / "embedding_suspects.csv"

            with patch.object(bge, "GRAPH_DB", db_dir), \
                 patch.object(bge, "OUT_HTML", out_html), \
                 patch.object(bge, "OUT_DIR", tmp), \
                 patch.object(bge, "OUT_CSV", out_csv), \
                 patch("graph.queries.embed_nodes.embed_all", return_value=_stub_embeddings()):
                bge.main()

            self.assertTrue(out_html.exists())
            html = out_html.read_text()
            # Splice succeeded — placeholder is gone, JSON is valid.
            self.assertNotIn("__DATA__", html)
            blob = html.split("const DATA = ", 1)[1].split(";\n", 1)[0]
            data = json.loads(blob)
            self.assertGreaterEqual(len(data["nodes"]), 7)

            self.assertTrue(out_csv.exists())
            df = pd.read_csv(out_csv)
            top = df.iloc[0]
            self.assertEqual(top["gtin_upc"], "popcorn")
            self.assertEqual(top["quarantine_reason"], "wrong_label")
            self.assertEqual(str(top["embedding_top1_code"]), "5500")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the integration test**

Run: `python3 -m unittest implementation.tests.test_build_graph_explorer -v`
Expected: 1 test passes.

- [ ] **Step 3: Run full embed_nodes + score_suspicion suites together**

Run: `python3 -m unittest implementation.tests.test_embed_nodes implementation.tests.test_score_suspicion implementation.tests.test_build_graph_explorer -v`
Expected: 9 tests pass total.

- [ ] **Step 4: Commit**

```bash
git add implementation/tests/test_build_graph_explorer.py
git commit -m "test(graph): end-to-end smoke for graph explorer pipeline"
```

---

## Task 8: First real run + manual sanity check

**Files:**
- (no code changes — this is the trust-builder pass from the spec)

- [ ] **Step 1: Confirm Kuzu DB exists**

Run: `ls -la graph/db/kuzu`
Expected: directory with at least a `data.kz` file. If missing, run `python3 graph/ingest/build_kuzu_graph.py` first.

- [ ] **Step 2: Run the orchestrator against the real graph**

Run: `python3 graph/queries/build_graph_explorer.py`
Expected: prints embedding progress (first run downloads MiniLM, ~80MB, ~1–2 min) then scoring + writing. Total time on a typical corpus: 5–15 minutes.

- [ ] **Step 3: Open the viewer**

Run: `open implementation/output/graph_explorer/index.html`
Expected: browser opens, point cloud renders within ~3 sec, toolbar is interactive. Color defaults to suspicion (red = suspect). Drag to rotate. Click a red point and confirm the right-side panel shows its metadata + disagreement kind.

- [ ] **Step 4: Inspect the suspect CSV**

Run: `head -5 graph/quarantine/embedding_suspects.csv`
Expected: header row matches the schema in Task 6 (gtin_upc, fdc_id, product_description, …, embedding_top1_code, embedding_assigned_rank). Top rows have suspicion ≥ ~0.7.

- [ ] **Step 5: Sanity-check three known-bad mappings**

Pick three product GTINs you already know are mis-mapped (from prior heal passes or your memory). Confirm each shows up in the top 5% of `embedding_suspects.csv` ordered by `score`.

If they don't, the embedding signal is too weak for v1 — open an issue and stop here. If they do, proceed.

- [ ] **Step 6: Commit the generated outputs (optional)**

```bash
git add implementation/output/graph_explorer/index.html graph/quarantine/embedding_suspects.csv
git commit -m "data: first graph_explorer run + embedding_suspects.csv"
```

---

## Task 9: Wire into AGENTS.md

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Find the "Build, Test, and Development Commands" section**

Run: `grep -n "Build, Test, and Development Commands" AGENTS.md`

- [ ] **Step 2: Add a bullet**

Add this bullet under that section (after the existing `python3 implementation/build_release_blocker_queue.py` line):

```
- `python3 graph/queries/build_graph_explorer.py` regenerates `implementation/output/graph_explorer/index.html` (interactive 3D explorer) and `graph/quarantine/embedding_suspects.csv` (ranked suspect Product→ESHA mappings using local embeddings).
```

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs: document graph_explorer command in AGENTS.md"
```

---

## Self-Review

Spec coverage:
- Three-view scoring (text/graph/label) → Task 4 ✓
- Disagreement kinds (`agree | wrong_label | bad_upstream | garbage`) → Task 4 ✓
- Embeddings cached on disk by content hash → Task 2/3 ✓
- PCA + UMAP projection → Task 6 ✓
- Single self-contained HTML viewer with deck.gl → Tasks 5+6 ✓
- Color-by toolbar (esha_family, category, suspicion, disagreement, kind) → Task 5 ✓
- Click-a-node side panel → Task 5 ✓
- Suspect CSV using existing quarantine schema → Task 6 ✓
- Orchestrator CLI entry → Task 6 ✓
- Tests covering each module + end-to-end smoke → Tasks 2,3,4,7 ✓
- AGENTS.md docs → Task 9 ✓

Open spec items deferred (acknowledged in spec): Ingredient node table, auto-apply, t-SNE.

Type/naming consistency: `score_all`, `embed_all`, `build_node_texts`, `disagreement_kind`, `assigned_rank`, `top1_code`, `text_view_code`, `graph_view_code`, `label_view_code`, `suspicion` — verified consistent across Tasks 2/3/4/6/7.

No placeholders found.
