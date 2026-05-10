import unittest
from dataclasses import replace

from planner.hestia.scoring_config import ScoringConfig
from planner.mode_config import build_scoring_config


class PlannerModeConfigTests(unittest.TestCase):
    def build(self, mode: str, protein_pct: float = 35.0):
        return build_scoring_config(
            ScoringConfig,
            replace,
            mode=mode,
            protein_pct=protein_pct,
            daily_cal=2000.0,
            leftover_pct=0.75,
        )

    def test_balanced_matches_production_without_diversity_boost(self) -> None:
        config = self.build("balanced")

        self.assertEqual(config.protein_pct_target, 35.0)
        self.assertEqual(config.daily_cal_target, 2000.0)
        self.assertEqual(config.leftover_pct_target, 0.75)
        self.assertFalse(config.enable_protein_diversity_boost)
        self.assertEqual(config.beef_boost, 0.0)
        self.assertEqual(config.fish_boost, 0.0)
        self.assertIsNone(config.protein_target_distribution)

    def test_budget_matches_production_without_diversity_boost(self) -> None:
        config = self.build("budget")

        self.assertFalse(config.enable_protein_diversity_boost)
        self.assertEqual(config.beef_boost, 0.0)
        self.assertEqual(config.fish_boost, 0.0)

    def test_tier_modes_keep_source_mix_separate_from_macro_target(self) -> None:
        thrifty = self.build("thrifty")
        low_cost = self.build("low_cost")
        liberal = self.build("liberal")

        self.assertEqual(thrifty.protein_pct_target, 35.0)
        self.assertEqual(low_cost.protein_pct_target, 35.0)
        self.assertEqual(liberal.protein_pct_target, 35.0)
        self.assertEqual(thrifty.protein_target_distribution, [0.03, 0.22, 0.25, 0.02, 0.34, 0.14])
        self.assertEqual(low_cost.protein_target_distribution, [0.03, 0.18, 0.30, 0.04, 0.35, 0.10])
        self.assertEqual(liberal.protein_target_distribution, [0.22, 0.12, 0.18, 0.22, 0.18, 0.08])


if __name__ == "__main__":
    unittest.main()
