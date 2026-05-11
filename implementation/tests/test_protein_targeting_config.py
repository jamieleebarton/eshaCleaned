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

    def test_baseline_fifteen_percent_stays_soft_for_thrifty(self) -> None:
        overrides = _protein_targeting_overrides(ScoringConfig.thrifty(protein_pct=15.0))

        self.assertNotIn("enable_protein_prefilter", overrides)
        self.assertTrue(overrides["enable_protein_density_bonus"])
        self.assertGreater(overrides["protein_density_value"], 0)

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

    def test_normal_tiers_do_not_auto_enable_hard_prefilter_at_p35(self) -> None:
        for factory in (
            ScoringConfig.thrifty,
            ScoringConfig.low_cost,
            ScoringConfig.moderate,
            ScoringConfig.liberal,
        ):
            with self.subTest(factory=factory.__name__):
                overrides = _protein_targeting_overrides(factory(protein_pct=35.0))
                self.assertNotIn("enable_protein_prefilter", overrides)
                self.assertNotIn("protein_filter_margin", overrides)

    def test_prefilter_boundary_is_not_auto_enabled_for_normal_tiers(self) -> None:
        self.assertNotIn(
            "enable_protein_prefilter",
            _protein_targeting_overrides(ScoringConfig.thrifty(protein_pct=24.9)),
        )
        self.assertNotIn(
            "enable_protein_prefilter",
            _protein_targeting_overrides(ScoringConfig.thrifty(protein_pct=25.0)),
        )

    def test_high_protein_mode_keeps_hard_prefilter(self) -> None:
        config = ScoringConfig.high_protein(target_pct=35.0)

        overrides = _protein_targeting_overrides(config)

        self.assertTrue(config.enable_protein_prefilter)
        self.assertNotIn("enable_protein_prefilter", overrides)
        self.assertEqual(overrides["protein_filter_margin"], 8.0)

    def test_thrifty_preserves_budget_produce_nudges(self) -> None:
        config = ScoringConfig.thrifty(protein_pct=35.0)

        self.assertTrue(config.enable_produce_bonus)
        self.assertEqual(config.produce_value_lunch, 0.002)
        self.assertEqual(config.produce_value_dinner, 0.005)

    def test_budget_tier_is_source_mix_not_macro_target(self) -> None:
        self.assertIsNone(ScoringConfig.thrifty(protein_pct=20.0).protein_target_distribution)
        self.assertIsNotNone(ScoringConfig.thrifty(protein_pct=35.0).protein_target_distribution)
        self.assertIsNotNone(ScoringConfig.low_cost(protein_pct=20.0).protein_target_distribution)
        self.assertIsNotNone(ScoringConfig.moderate(protein_pct=20.0).protein_target_distribution)
        self.assertIsNotNone(ScoringConfig.liberal(protein_pct=20.0).protein_target_distribution)

    def test_high_protein_thrifty_uses_budget_source_mix(self) -> None:
        config = ScoringConfig.thrifty(protein_pct=35.0)

        self.assertEqual(
            config.protein_target_distribution,
            [0.03, 0.22, 0.25, 0.02, 0.34, 0.14],
        )
        self.assertGreater(
            config.protein_target_distribution[4] + config.protein_target_distribution[5],
            config.protein_target_distribution[0] + config.protein_target_distribution[3],
        )
        self.assertGreater(
            config.protein_target_distribution[1] + config.protein_target_distribution[2],
            config.protein_target_distribution[0] + config.protein_target_distribution[3],
        )

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
