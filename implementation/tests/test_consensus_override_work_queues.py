import importlib.util
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
SCRIPT = V2 / "build_consensus_override_work_queues.py"

sys.path.insert(0, str(V2))
spec = importlib.util.spec_from_file_location("build_consensus_override_work_queues", SCRIPT)
queues = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(queues)


class ConsensusOverrideWorkQueuesTests(unittest.TestCase):
    def test_taxonomy_queue_includes_policy_cases_but_not_source_conflicts(self):
        rows = [
            {
                "fdc_id": "1",
                "action_type": "policy_decision",
                "issue_family": "baking_decoration_or_topping_routed_as_candy",
                "title": "SPRINKLES",
            },
            {
                "fdc_id": "2",
                "action_type": "policy_fix_candidate",
                "issue_family": "salad_topping_routed_as_finished_salad",
                "title": "SALAD TOPPING",
            },
            {
                "fdc_id": "3",
                "action_type": "source_conflict_review",
                "issue_family": "candy_bfc_routed_outside_snack_candy",
                "title": "CHOCOLATE BAR",
            },
        ]

        taxonomy = queues.build_taxonomy_todo(rows)
        conflicts = queues.build_source_conflict_todo(rows)

        self.assertEqual(["1", "2"], sorted(row["fdc_id"] for row in taxonomy))
        self.assertEqual("shared", next(row["owner"] for row in taxonomy if row["fdc_id"] == "1"))
        self.assertEqual("claude", next(row["owner"] for row in taxonomy if row["fdc_id"] == "2"))
        self.assertEqual(["3"], [row["fdc_id"] for row in conflicts])

    def test_reference_todo_keeps_current_and_proposed_fields_separate(self):
        rows = [{
            "fdc_id": "10",
            "issue_family": "plant_milk_has_dairy_milk_reference",
            "severity": "high",
            "confidence": "high",
            "suspect_reference_fields": "sr28",
            "sr28_code": "1077",
            "sr28_desc": "Milk, whole",
            "title": "UNSWEETENED ALMOND MILK",
        }]

        todo = queues.build_reference_todo(rows)

        self.assertEqual("todo", todo[0]["status"])
        self.assertEqual("codex", todo[0]["owner"])
        self.assertEqual("1077", todo[0]["current_sr28_code"])
        self.assertEqual("Milk, whole", todo[0]["current_sr28_desc"])
        self.assertEqual("", todo[0]["proposed_sr28_code"])


if __name__ == "__main__":
    unittest.main()
