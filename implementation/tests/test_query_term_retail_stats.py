from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from implementation.analyze_query_term_retail_stats import (
    build_outputs,
    parse_markdown_table,
    parse_term_stats,
)


class QueryTermRetailStatsTests(unittest.TestCase):
    def test_parse_term_stats(self) -> None:
        parsed = parse_term_stats("aspartame:signal:35:9.46 | chocolate:broad:41369:2.41")
        self.assertEqual(parsed["aspartame"]["retail_count"], 35)
        self.assertEqual(parsed["chocolate"]["bucket"], "broad")

    def test_parse_markdown_table(self) -> None:
        lines = [
            "## Query Attempts",
            "",
            "| attempt | query | total_matches | error |",
            "| --- | --- | ---: | --- |",
            "| strict | `foo` | 0 |  |",
            "| drop_one_core_term:aspartame | `bar` | 7 |  |",
            "",
            "## Next",
        ]
        rows = parse_markdown_table(lines, "## Query Attempts")
        self.assertEqual(rows[0]["attempt"], "strict")
        self.assertEqual(rows[1]["total_matches"], "7")

    def test_build_outputs_finds_drop_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pack = root / "000151_test.md"
            pack.write_text(
                "\n".join(
                    [
                        "# ESHA 151: Test",
                        "",
                        "## Product Query Results",
                        "",
                        "- selected_query_attempt: drop_one_core_term:aspartame",
                        "- esha_required_terms_from_description: chocolate | aspartame",
                        "- weighted_query_term_stats: chocolate:broad:41369:2.41 | aspartame:signal:35:9.46",
                        "",
                        "## Query Attempts",
                        "",
                        "| attempt | query | total_matches | error |",
                        "| --- | --- | ---: | --- |",
                        "| strict | `strict` | 0 |  |",
                        "| drop_one_core_term:aspartame | `drop` | 7 |  |",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            term_rows, card_rows = build_outputs(
                [
                    {
                        "esha_code": "151",
                        "description": "Drink, chocolate, dairy, reduced calorie, with aspartame, prepared from dry with wtr",
                        "family": "beverage",
                        "pack_path": str(pack),
                    }
                ]
            )
            aspartame = next(row for row in term_rows if row["term"] == "aspartame")
            self.assertEqual(aspartame["drop_rescue_count"], 1)
            candidate = next(row for row in card_rows if row["term"] == "aspartame")
            self.assertEqual(candidate["candidate_action"], "demote_from_query")


if __name__ == "__main__":
    unittest.main()
