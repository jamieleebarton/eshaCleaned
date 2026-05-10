from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLANNER = ROOT / "planner"
if str(PLANNER) not in sys.path:
    sys.path.insert(0, str(PLANNER))

from hestia.scoring_config import ScoringConfig
from hestia.sparse_cascade import (
    _protein_targeting_overrides,
    _with_constructor_protein_target,
)


class ProteinTargetingConfigTests(unittest.TestCase):
    def test_moderate_protein_target_stays_soft_for_thrifty(self) -> None:
        config = ScoringConfig.thrifty(protein_pct=18.0)

        overrides = _protein_targeting_overrides(config)

        self.assertNotIn("enable_protein_prefilter", overrides)
        self.assertTrue(overrides["enable_protein_density_bonus"])
        self.assertGreater(overrides["protein_density_value"], config.protein_density_value)
        self.assertGreater(overrides["macro_deviation_weight"], config.macro_deviation_weight)

    def test_twenty_percent_stays_soft_for_budget_tiers(self) -> None:
        for factory in (
            ScoringConfig.thrifty,
            ScoringConfig.low_cost,
            ScoringConfig.moderate,
            ScoringConfig.liberal,
        ):
            with self.subTest(factory=factory.__name__):
                overrides = _protein_targeting_overrides(factory(protein_pct=20.0))
                self.assertNotIn("enable_protein_prefilter", overrides)

    def test_prefilter_boundary_is_twenty_five_percent(self) -> None:
        self.assertNotIn(
            "enable_protein_prefilter",
            _protein_targeting_overrides(ScoringConfig.thrifty(protein_pct=24.9)),
        )
        self.assertTrue(
            _protein_targeting_overrides(
                ScoringConfig.thrifty(protein_pct=25.0)
            )["enable_protein_prefilter"]
        )

    def test_high_protein_target_enables_hard_prefilter(self) -> None:
        config = ScoringConfig.thrifty(protein_pct=25.0)

        overrides = _protein_targeting_overrides(config)

        self.assertTrue(overrides["enable_protein_prefilter"])
        self.assertEqual(overrides["protein_filter_margin"], 6.0)

    def test_budget_tier_is_source_mix_not_macro_target(self) -> None:
        self.assertIsNone(ScoringConfig.thrifty(protein_pct=20.0).protein_target_distribution)
        self.assertIsNotNone(ScoringConfig.low_cost(protein_pct=20.0).protein_target_distribution)
        self.assertIsNotNone(ScoringConfig.moderate(protein_pct=20.0).protein_target_distribution)
        self.assertIsNotNone(ScoringConfig.liberal(protein_pct=20.0).protein_target_distribution)

    def test_constructor_protein_target_matches_config_path(self) -> None:
        config = _with_constructor_protein_target(
            ScoringConfig.thrifty(),
            protein_pct_target=20.0,
        )

        self.assertEqual(config.protein_pct_target, 20.0)
        self.assertNotIn("enable_protein_prefilter", _protein_targeting_overrides(config))

    def test_explicit_config_target_wins_over_constructor_default(self) -> None:
        config = _with_constructor_protein_target(
            ScoringConfig.thrifty(protein_pct=18.0),
            protein_pct_target=20.0,
        )

        self.assertEqual(config.protein_pct_target, 18.0)


if __name__ == "__main__":
    unittest.main()
