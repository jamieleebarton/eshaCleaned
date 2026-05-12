from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recipe_pricing.fix_size_display_grams import choose_expected_grams


def _load_plan_audit_module():
    path = ROOT / "planner" / "scripts" / "audit_plan_reasonableness.py"
    spec = importlib.util.spec_from_file_location("audit_plan_reasonableness", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AUDIT = _load_plan_audit_module()


class PackageSizeAuditTests(unittest.TestCase):
    def test_ct_slash_weight_is_total_net_weight(self) -> None:
        expected_g, source = choose_expected_grams(
            "Kroger 100% Whole Wheat Bagels",
            "6 ct / 20 oz",
        )

        self.assertEqual(source, "size_display_pack")
        self.assertAlmostEqual(expected_g or 0.0, 566.99, places=2)

    def test_container_pack_slash_weight_is_total_pack_weight(self) -> None:
        expected_g, source = choose_expected_grams(
            "Juice Boxes",
            "8 pk / 6.75 fl oz",
        )

        self.assertEqual(source, "size_display_pack")
        self.assertAlmostEqual(expected_g or 0.0, 1596.969, places=3)

    def test_prepared_yield_does_not_override_net_package_weight(self) -> None:
        expected_g, source = choose_expected_grams(
            "Great Value Instant Nonfat Dry Milk, 3.2 oz Pouches, "
            "3 Count, Makes 3 Quarts Total, 12 Servings",
            "9.6 oz (272g)",
        )

        self.assertEqual(source, "size_display")
        self.assertAlmostEqual(expected_g or 0.0, 272.1552, places=3)

    def test_random_weight_produce_is_audit_info_not_failure(self) -> None:
        flags = AUDIT.package_flags(
            "Produce > Vegetables > Jalapenos|6622100V",
            {
                "name": "Fresh Jalapeno Peppers",
                "grams": 68.0,
                "cents": 27,
                "display": "1 lb",
            },
        )
        details = AUDIT.package_flag_details(
            "Produce > Vegetables > Jalapenos|6622100V",
            {
                "name": "Fresh Jalapeno Peppers",
                "grams": 68.0,
                "cents": 27,
                "display": "1 lb",
            },
        )

        self.assertNotIn("package_grams_under_declared_size", flags)
        self.assertIn("random_weight_average_unit", [d["flag"] for d in details])

    def test_gravy_packet_overinflated_grams_still_fails(self) -> None:
        flags = AUDIT.package_flags(
            "Pantry > Spices & Seasonings > Seasoning|E6020309",
            {
                "name": "Simply Organic Roasted Chicken Gravy Seasoning Mix, .85 oz Packet",
                "grams": 2409.7,
                "cents": 167,
                "display": "1 oz",
            },
        )

        self.assertIn("package_grams_over_declared_size", flags)

    def test_small_spice_package_is_not_high_cpg_failure(self) -> None:
        flags = AUDIT.package_flags(
            "Pantry > Spices & Seasonings > Basil|E302400V",
            {
                "name": "Gourmet Garden Lightly Dried Basil",
                "grams": 9.1,
                "cents": 399,
                "display": "0.42 oz",
            },
        )

        self.assertNotIn("very_high_cpg", flags)


if __name__ == "__main__":
    unittest.main()
