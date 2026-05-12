import sys
import unittest
from pathlib import Path


ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
V2 = ROOT / "retail_mapper" / "v2"
if str(V2) not in sys.path:
    sys.path.insert(0, str(V2))

import merge_semantic_taxonomy_into_enriched as merger  # noqa: E402


class MergeSemanticTaxonomyIntoEnrichedTests(unittest.TestCase):
    def test_merge_preserves_original_confidence_and_adds_semantic_confidence(self) -> None:
        rows = [
            {
                "fdc_id": "2500391",
                "title": "UNSWEETENED CHOCOLATE ALMONDMILK",
                "confidence": "0.61",
                "llm_evidence_block": "evidence",
            }
        ]
        base_fields = ["fdc_id", "title", "confidence", "llm_evidence_block"]
        semantic_index = {
            "2500391": {
                "product_identity": "Almond Milk",
                "canonical_path": "Beverage > Plant Milk > Almond Milk",
                "canonical_label": "Almond Milk (Chocolate, Unsweetened)",
                "confidence": "0.95",
                "claims": "unsweetened",
                "flavor": "chocolate",
            }
        }
        assignment_index = {"2500391": {"node_id": "product_identity:almond-milk"}}

        merged, stats = merger.merge_rows(rows, base_fields, semantic_index, assignment_index)

        self.assertEqual(stats["rows_written"], 1)
        self.assertEqual(stats["semantic_matched"], 1)
        self.assertEqual(merged[0]["confidence"], "0.61")
        self.assertEqual(merged[0]["semantic_confidence"], "0.95")
        self.assertEqual(merged[0]["semantic_product_identity"], "Almond Milk")
        self.assertEqual(merged[0]["semantic_claims"], "unsweetened")
        self.assertEqual(merged[0]["semantic_node_id"], "product_identity:almond-milk")

    def test_output_fields_replace_existing_semantic_columns_on_rerun(self) -> None:
        fields = [
            "fdc_id",
            "title",
            "semantic_product_identity",
            "semantic_node_id",
            "confidence",
        ]

        merged_fields = merger.output_fields(fields)

        self.assertEqual(merged_fields[:3], ["fdc_id", "title", "confidence"])
        self.assertEqual(merged_fields.count("semantic_product_identity"), 1)
        self.assertEqual(merged_fields.count("semantic_node_id"), 1)
        self.assertTrue(merged_fields[-len(merger.SEMANTIC_OUTPUT_FIELDS) :] == merger.SEMANTIC_OUTPUT_FIELDS)


if __name__ == "__main__":
    unittest.main()
