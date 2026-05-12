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
