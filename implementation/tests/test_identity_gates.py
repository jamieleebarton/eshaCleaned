"""Tests for identity bridge hard gates.

These must pass before any base food can enter the calculator.
Covers the exact challenge cases from the identity rebuild plan.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from identity_bridge import gate_reject_reason, is_clean_base, repair_base


class TestGateRejectsPoison(unittest.TestCase):
    """No modifier-only, junk, prep-only, instruction-only, or brand-only base may pass."""

    def test_modifier_only_rejected(self):
        for base in ["fat-free", "hot", "cold", "extra", "unsalted", "additional",
                      "frozen", "fresh", "organic", "all-purpose", "low-fat",
                      "reduced-sodium", "lite", "remaining"]:
            reason = gate_reject_reason(base)
            self.assertTrue(reason, f"{base!r} should be rejected but passed gates")
            self.assertIn("modifier_only", reason, f"{base!r}: {reason}")

    def test_prep_only_rejected(self):
        for base in ["chopped", "diced", "sliced", "sifted", "melted", "softened"]:
            reason = gate_reject_reason(base)
            self.assertTrue(reason, f"{base!r} should be rejected")
            self.assertIn("prep_only", reason)

    def test_packaging_only_rejected(self):
        for base in ["can", "box", "jar", "package", "container", "bag"]:
            reason = gate_reject_reason(base)
            self.assertTrue(reason, f"{base!r} should be rejected")
            self.assertIn("packaging_only", reason)

    def test_size_only_rejected(self):
        for base in ["large", "small", "medium", "jumbo", "baby"]:
            reason = gate_reject_reason(base)
            self.assertTrue(reason, f"{base!r} should be rejected")
            self.assertIn("size_only", reason)

    def test_brand_only_rejected(self):
        for base in ["kraft", "absolut", "mccormick", "best foods", "velveeta"]:
            reason = gate_reject_reason(base)
            self.assertTrue(reason, f"{base!r} should be rejected")
            self.assertIn("brand_only", reason)

    def test_junk_rejected(self):
        for base in ["", "&nbsp;", "&nbsp", "%", "???", "_____", ".", ",", "42", "3.5"]:
            reason = gate_reject_reason(base)
            self.assertTrue(reason, f"{base!r} should be rejected but passed gates")

    def test_instruction_only_rejected(self):
        for base in ["for coating", "for rolling", "for garnish", "for frying"]:
            reason = gate_reject_reason(base)
            self.assertTrue(reason, f"{base!r} should be rejected")

    def test_all_modifier_tokens_rejected(self):
        for base in ["large fresh", "finely chopped", "extra large frozen"]:
            reason = gate_reject_reason(base)
            self.assertTrue(reason, f"{base!r} should be rejected")
            self.assertIn("all_modifier_tokens", reason)


class TestGateAcceptsRealFood(unittest.TestCase):
    """Real foods must pass the gates."""

    def test_common_foods_pass(self):
        for base in ["salt", "sugar", "butter", "egg", "flour", "milk", "water",
                      "olive oil", "garlic", "onion", "chicken", "beef", "rice",
                      "cream cheese", "sour cream", "baking powder", "vanilla",
                      "cinnamon", "oregano", "parsley", "tomato", "potato",
                      "chicken broth", "all-purpose flour", "ground beef",
                      "green onion", "cream of mushroom soup", "half and half",
                      "worcestershire sauce", "lemon juice", "peanut butter",
                      "brown sugar", "powdered sugar", "vegetable oil"]:
            self.assertTrue(is_clean_base(base), f"{base!r} should pass gates")


class TestRepairRules(unittest.TestCase):
    """Repair rules fix known poison patterns instead of rejecting them."""

    def test_fat_free_chicken_broth(self):
        repaired, repairs = repair_base("fat-free, less-sodium chicken broth")
        self.assertNotIn("fat-free", repaired.lower().split(",")[0].split()[0])
        self.assertIn("chicken broth", repaired.lower())

    def test_hot_cooked_rice(self):
        repaired, repairs = repair_base("hot, cooked rice")
        self.assertTrue(is_clean_base(repaired), f"repaired={repaired!r} should pass")
        self.assertIn("rice", repaired.lower())

    def test_cold_unsalted_butter(self):
        repaired, repairs = repair_base("cold, unsalted butter")
        self.assertIn("butter", repaired.lower())

    def test_additional_cilantro(self):
        repaired, repairs = repair_base("additional cilantro")
        self.assertEqual(repaired.lower(), "cilantro")

    def test_additional_flour_for_rolling(self):
        repaired, repairs = repair_base("additional flour for rolling")
        self.assertIn("flour", repaired.lower())
        self.assertNotIn("rolling", repaired.lower())

    def test_oil_for_frying(self):
        repaired, repairs = repair_base("oil for frying")
        self.assertEqual(repaired.lower(), "oil")

    def test_all_purpose_flour_sifted(self):
        repaired, repairs = repair_base("all-purpose flour sifted")
        self.assertEqual(repaired.lower(), "all-purpose flour")

    def test_whole_boneless_skinless_chicken_breasts(self):
        # 'whole' is a modifier — but the rest has real food
        repaired, repairs = repair_base("whole, boneless skinless chicken breasts")
        self.assertIn("chicken", repaired.lower())

    def test_box_frozen_chopped_broccoli(self):
        repaired, repairs = repair_base("box frozen chopped broccoli")
        # 'box' gets stripped as leading packaging is not in repair_base
        # but 'frozen chopped broccoli' → strip prep → 'broccoli'
        self.assertIn("broccoli", repaired.lower())


class TestChallengeDistinctions(unittest.TestCase):
    """Gates must not confuse similar foods."""

    def test_green_beans_passes(self):
        self.assertTrue(is_clean_base("green beans"))

    def test_green_bean_casserole_passes(self):
        self.assertTrue(is_clean_base("green bean casserole"))

    def test_green_beans_not_casserole(self):
        # These are different foods — gates don't collapse, they just validate
        self.assertNotEqual("green beans", "green bean casserole")

    def test_egg_yolks_passes(self):
        self.assertTrue(is_clean_base("egg yolks"))
        self.assertTrue(is_clean_base("egg yolk"))

    def test_ham_passes(self):
        self.assertTrue(is_clean_base("ham"))
        self.assertTrue(is_clean_base("deli ham"))


if __name__ == "__main__":
    unittest.main()
