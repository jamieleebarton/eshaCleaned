import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from schema import Resolution, NutritionEstimate, ProductCandidate, NutritionState, ShoppingState, TrustLayer


class SchemaContractTests(unittest.TestCase):
    def test_resolution_requires_both_trust_states(self):
        """Guardrail #4: nutrition_state and shopping_state are both required, never collapsed."""
        with self.assertRaises(TypeError):
            Resolution()  # must fail — missing required fields

    def test_resolution_round_trip(self):
        """Guardrail #10: dataclass round-trip fixture."""
        r = Resolution(
            canonical_name="butter",
            sr28_fdc_id="173410",
            fndds_code="81100500",
            pseudo_code="",
            nutrition_state=NutritionState.EXACT_USDA_ANCHOR,
            shopping_state=ShoppingState.SHOPPING_CANDIDATES_STRONG,
            trust_layer=TrustLayer.L1_CANONICAL,
            grams=14.2,
            alternatives=[],
            path=["L1/item='butter' -> 'butter'"],
        )
        self.assertEqual(r.sr28_fdc_id, "173410")
        self.assertEqual(r.nutrition_state, NutritionState.EXACT_USDA_ANCHOR)

    def test_nutrition_state_is_enum_with_terminal_values(self):
        """Every state from CLAUDE.md must exist."""
        names = {s.name for s in NutritionState}
        self.assertIn("EXACT_USDA_ANCHOR", names)
        self.assertIn("REVIEWED_LOCAL_LABEL_ANCHOR", names)
        self.assertIn("REVIEWED_PROXY", names)
        self.assertIn("NUTRITION_UNKNOWN", names)
        self.assertIn("NON_FOOD", names)

    def test_shopping_state_is_enum_with_terminal_values(self):
        names = {s.name for s in ShoppingState}
        self.assertIn("SHOPPING_CANDIDATES_STRONG", names)
        self.assertIn("SHOPPING_CANDIDATES_WEAK", names)
        self.assertIn("SHOPPING_GAP", names)
        self.assertIn("NON_FOOD", names)

    def test_alternatives_list_required_field(self):
        """Guardrail #20: OR-alternatives never hidden."""
        r = Resolution(
            canonical_name="butter",
            sr28_fdc_id="173410", fndds_code="", pseudo_code="",
            nutrition_state=NutritionState.EXACT_USDA_ANCHOR,
            shopping_state=ShoppingState.SHOPPING_CANDIDATES_STRONG,
            trust_layer=TrustLayer.L1_CANONICAL,
            grams=14.2,
            alternatives=["margarine"],
            path=[],
        )
        self.assertEqual(r.alternatives, ["margarine"])


if __name__ == "__main__":
    unittest.main()
