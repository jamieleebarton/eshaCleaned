from __future__ import annotations

import csv
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


IMPLEMENTATION_ROOT = Path(__file__).resolve().parents[1]
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

import provenance_graph as graph  # noqa: E402


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class ProvenanceGraphTests(unittest.TestCase):
    def test_build_and_trace_minimal_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            implementation = root / "implementation"
            output = implementation / "output"
            lookup_db = output / "product_esha_lookup.db"

            write_csv(
                root / "canonical_surface_normalized_with_product_proxies.csv",
                [
                    "canonical_surface",
                    "canonical_normalized",
                    "canonical_shopping_item",
                    "record_type",
                    "sr28_code",
                    "fndds_code",
                    "esha_code",
                    "esha_description",
                    "nutrition_match_state",
                    "product_proxy_match_state",
                    "esha_match_type",
                ],
                [
                    {
                        "canonical_surface": "ap flour",
                        "canonical_normalized": "all purpose flour",
                        "canonical_shopping_item": "all purpose flour",
                        "record_type": "ingredient",
                        "sr28_code": "100",
                        "fndds_code": "",
                        "esha_code": "45984",
                        "esha_description": "Flour, white, all-purpose",
                        "nutrition_match_state": "sr28_match",
                        "product_proxy_match_state": "contract_passed",
                        "esha_match_type": "reviewed_top2500",
                    }
                ],
            )
            write_csv(
                implementation / "canonical_to_esha.csv",
                ["canonical_name", "esha_code", "esha_description"],
                [{"canonical_name": "all purpose flour", "esha_code": "45984", "esha_description": "Flour, white, all-purpose"}],
            )
            write_csv(
                root / "esha_cleaned_canonical.csv",
                ["EshaCode", "Description", "canonical_shopping_item"],
                [{"EshaCode": "45984", "Description": "Flour, white, all-purpose", "canonical_shopping_item": "all purpose flour"}],
            )
            pack_path = output / "esha_code_query_packs" / "grain" / "045984_flour.md"
            pack_path.parent.mkdir(parents=True, exist_ok=True)
            pack_path.write_text("# pack\n", encoding="utf-8")
            write_csv(
                output / "esha_code_query_pack_index.csv",
                ["esha_code", "description", "family", "query", "pack_path", "total_product_matches"],
                [
                    {
                        "esha_code": "45984",
                        "description": "Flour, white, all-purpose",
                        "family": "grain",
                        "query": "flour",
                        "pack_path": str(pack_path),
                        "total_product_matches": "10",
                    }
                ],
            )
            write_csv(
                output / "top2500_cleanup_progress.csv",
                ["rank", "normalized_item", "occurrence_count", "issue_class", "check_status", "issue_priority", "esha_code", "esha_description"],
                [
                    {
                        "rank": "1",
                        "normalized_item": "ap flour",
                        "occurrence_count": "100",
                        "issue_class": "ok",
                        "check_status": "done",
                        "issue_priority": "OK",
                        "esha_code": "45984",
                        "esha_description": "Flour, white, all-purpose",
                    }
                ],
            )
            output.mkdir(parents=True, exist_ok=True)
            con = sqlite3.connect(lookup_db)
            try:
                con.execute(
                    """
                    CREATE TABLE product_esha_code_rollup (
                        gtin_upc TEXT,
                        product_description TEXT,
                        brand_name TEXT,
                        branded_food_category TEXT,
                        esha_code_count TEXT,
                        esha_codes TEXT,
                        primary_esha_code TEXT,
                        collision_status TEXT
                    )
                    """
                )
                con.execute(
                    """
                    INSERT INTO product_esha_code_rollup
                    VALUES ('0001', 'Generic AP Flour', 'Acme', 'Flour', '1', '45984', '45984', '')
                    """
                )
                con.commit()
            finally:
                con.close()

            with patch.object(graph, "ROOT", root), \
                patch.object(graph, "IMPLEMENTATION_ROOT", implementation), \
                patch.object(graph, "OUTPUT_ROOT", output), \
                patch.object(graph, "CANONICAL_SURFACE", root / "canonical_surface_normalized_with_product_proxies.csv"), \
                patch.object(graph, "PACK_INDEX", output / "esha_code_query_pack_index.csv"), \
                patch.object(graph, "TOP2500_PROGRESS", output / "top2500_cleanup_progress.csv"), \
                patch.object(graph, "LOOKUP_DB", lookup_db), \
                patch.object(graph, "CANONICAL_TO_ESHA", implementation / "canonical_to_esha.csv"), \
                patch.object(graph, "ESHA_CANONICAL", root / "esha_cleaned_canonical.csv"), \
                patch.object(graph, "REVIEWED_CONTRACT_SPECS", output / "reviewed_specs.json"), \
                patch.object(graph, "_load_reviewed_contract_codes", return_value={"45984"}):
                db_path = output / "provenance_graph.db"
                counts = graph.build_graph(db_path)
                self.assertGreaterEqual(counts.node_count, 6)
                traced = graph.trace_entity("esha_code", "45984", db_path=db_path)
                self.assertTrue(traced["ok"])
                self.assertEqual(traced["node"]["node_id"], "esha:45984")
                outgoing = {(row["edge_type"], row["dst_kind"]) for row in traced["outgoing_edges"]}
                self.assertIn(("has_pack", "pack"), outgoing)
                self.assertIn(("reviewed_by_contract", "reviewed_contract"), outgoing)
                self.assertTrue(any(dep["artifact_path"].endswith("045984_flour.md") for dep in traced["rebuild_dependencies"]))


if __name__ == "__main__":
    unittest.main()
