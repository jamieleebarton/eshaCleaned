import unittest

from implementation.build_recipe_normalization_nebius_calculation import build_rows


def ingredient(
    *,
    line_index,
    display,
    machine_name,
    source_grams,
    raw_policy,
    raw_status="BLOCKED",
    role="consumed",
    matchability_status="MATCH_READY",
    blockers=None,
    quantity_extra=None,
    culinary_use=None,
):
    quantity = {"source_grams": source_grams}
    if quantity_extra:
        quantity.update(quantity_extra)
    return {
        "line_index": line_index,
        "original_display": display,
        "original_item": machine_name,
        "rewritten_ingredient": display,
        "normalized": {
            "machine_name": machine_name,
            "product_identity": machine_name,
            "culinary_use": culinary_use,
        },
        "matchability": {"status": matchability_status, "match_blockers": []},
        "role": role,
        "quantity": quantity,
        "consumption": {
            "consumption_policy": raw_policy,
            "calculation_status": raw_status,
            "consumed_grams": None,
            "blockers": blockers or ["blocked"],
        },
        "calculation_choice": {"selected_ingredient": machine_name, "requires_user_selection": False},
    }


class RecipeNormalizationNebiusCalculationTests(unittest.TestCase):
    def _by_line(self, recipe):
        line_rows, summary_rows = build_rows([recipe])
        return {row["line_index"]: row for row in line_rows}, summary_rows[0]

    def test_yield_bone_in_pork(self):
        recipe = {
            "recipe_id": 11737,
            "title": "Hillbilly Bean Soup",
            "ingredients": [
                ingredient(
                    line_index=2,
                    display="1 ham bone (with meat scraps)",
                    machine_name="ham bone with meat",
                    source_grams=300,
                    raw_policy="yield_policy_required",
                ),
            ],
        }
        rows, summary = self._by_line(recipe)
        self.assertEqual("75", rows["2"]["calculated_grams"])
        self.assertEqual("bone_in_pork_yield_25pct_applied", rows["2"]["policy_applied"])
        self.assertEqual("yes", summary["calculatable"])

    def test_yield_bone_in_poultry(self):
        recipe = {
            "recipe_id": 71,
            "title": "Classic Chicken and Dumplings",
            "ingredients": [
                ingredient(
                    line_index=0,
                    display="4 lbs bone-in chicken pieces (thighs and drumsticks)",
                    machine_name="chicken pieces",
                    source_grams=1814,
                    raw_policy="yield_policy_required",
                ),
            ],
        }
        rows, summary = self._by_line(recipe)
        self.assertEqual("1269.8", rows["0"]["calculated_grams"])
        self.assertEqual("bone_in_poultry_yield_70pct_applied", rows["0"]["policy_applied"])
        self.assertEqual("yes", summary["calculatable"])

    def test_retention_bay_leaf(self):
        recipe = {
            "recipe_id": 11737,
            "title": "Hillbilly Bean Soup",
            "ingredients": [
                ingredient(
                    line_index=3,
                    display="1 bay leaf",
                    machine_name="bay leaf",
                    source_grams=0.5,
                    raw_policy="retention_policy_required",
                ),
            ],
        }
        rows, summary = self._by_line(recipe)
        self.assertEqual("0", rows["3"]["calculated_grams"])
        self.assertEqual("removed_aromatic_zero_consumption_applied", rows["3"]["policy_applied"])

    def test_uptake_saute_default(self):
        recipe = {
            "recipe_id": 39,
            "title": "Chicken Biryani",
            "ingredients": [
                ingredient(
                    line_index=18,
                    display="2 tablespoons vegetable oil",
                    machine_name="vegetable oil",
                    source_grams=27,
                    raw_policy="uptake_policy_required",
                    role="process_medium",
                ),
                ingredient(
                    line_index=19,
                    display="1 tablespoon ghee",
                    machine_name="ghee",
                    source_grams=14,
                    raw_policy="uptake_policy_required",
                    role="process_medium",
                ),
            ],
        }
        rows, summary = self._by_line(recipe)
        self.assertEqual("6.75", rows["18"]["calculated_grams"])
        self.assertEqual("uptake_policy_default_25pct_applied", rows["18"]["policy_applied"])
        self.assertEqual("3.5", rows["19"]["calculated_grams"])
        self.assertEqual("yes", summary["calculatable"])

    def test_sodium_absorption_default(self):
        recipe = {
            "recipe_id": 39,
            "title": "Chicken Biryani",
            "ingredients": [
                ingredient(
                    line_index=17,
                    display="Salt, to taste",
                    machine_name="salt",
                    source_grams=2,
                    raw_policy="sodium_absorption_policy_required",
                    role="process_cooking_water",
                ),
            ],
        }
        rows, summary = self._by_line(recipe)
        self.assertEqual("0.2", rows["17"]["calculated_grams"])
        self.assertEqual("sodium_absorption_default_10pct_applied", rows["17"]["policy_applied"])

    def test_selected_option_first_alt_with_yield(self):
        recipe = {
            "recipe_id": 19546,
            "title": "Calico Bean Soup",
            "ingredients": [
                ingredient(
                    line_index=1,
                    display="1 lb ham bone or ham hock or 1 lb ground beef",
                    machine_name="ham bone",
                    source_grams=454,
                    raw_policy="selected_option_required",
                    role="alternative_group",
                ),
            ],
        }
        rows, summary = self._by_line(recipe)
        self.assertEqual("113.5", rows["1"]["calculated_grams"])
        self.assertIn("bone_in_pork_yield_25pct_applied", rows["1"]["policy_applied"])
        self.assertEqual("yes", summary["calculatable"])

    def test_selected_option_protein_alt(self):
        recipe = {
            "recipe_id": 24789,
            "title": "Stuffed Burgers",
            "ingredients": [
                ingredient(
                    line_index=0,
                    display="1 1/2 lbs lean ground beef OR ground chicken OR ground turkey",
                    machine_name="ground beef",
                    source_grams=680,
                    raw_policy="selected_option_required",
                    role="alternative_group",
                ),
            ],
        }
        rows, summary = self._by_line(recipe)
        self.assertEqual("680", rows["0"]["calculated_grams"])
        self.assertEqual("selected_option_first_alternative_applied", rows["0"]["policy_applied"])

    def test_selected_option_milk_or_sour_cream(self):
        recipe = {
            "recipe_id": 4627,
            "title": "Chicken Tortilla Soup",
            "ingredients": [
                ingredient(
                    line_index=13,
                    display="1 cup milk OR 1 cup sour cream",
                    machine_name="milk",
                    source_grams=240,
                    raw_policy="selected_option_required",
                    role="alternative_group",
                ),
            ],
        }
        rows, summary = self._by_line(recipe)
        self.assertEqual("240", rows["13"]["calculated_grams"])

    def test_ambiguous_identity_fallback(self):
        recipe = {
            "recipe_id": "synthetic_recipe_edge_cases_001",
            "title": "Synthetic Edge Cases",
            "ingredients": [
                {
                    "line_index": 1,
                    "original_display": "1 cup 100% bran",
                    "original_item": "100% bran",
                    "rewritten_ingredient": "1 cup 100% bran",
                    "normalized": {"machine_name": "100% bran", "product_identity": "100% bran"},
                    "matchability": {
                        "status": "BLOCKED",
                        "match_blockers": ["Ambiguous product identity"],
                    },
                    "role": "consumed",
                    "quantity": {"source_grams": 60},
                    "consumption": {
                        "consumption_policy": "all_input",
                        "calculation_status": "BLOCKED",
                        "consumed_grams": None,
                        "blockers": ["Ambiguous product identity"],
                    },
                    "calculation_choice": {
                        "selected_ingredient": "100% bran",
                        "requires_user_selection": False,
                    },
                },
            ],
        }
        rows, summary = self._by_line(recipe)
        self.assertEqual("60", rows["1"]["calculated_grams"])
        self.assertEqual(
            "identity_ambiguous_source_grams_default_applied",
            rows["1"]["policy_applied"],
        )
        self.assertEqual("yes", summary["calculatable"])

    def test_range_midpoint(self):
        recipe = {
            "recipe_id": 11737,
            "title": "Hillbilly Bean Soup",
            "ingredients": [
                ingredient(
                    line_index=33,
                    display="1 to 3 teaspoons Worcestershire sauce",
                    machine_name="Worcestershire sauce",
                    source_grams=15,
                    raw_policy="all_input",
                    quantity_extra={"range_low": 1, "range_high": 3, "unit": "teaspoon"},
                ),
            ],
        }
        rows, summary = self._by_line(recipe)
        self.assertEqual("10", rows["33"]["calculated_grams"])
        self.assertEqual("range_midpoint_default_applied", rows["33"]["policy_applied"])


if __name__ == "__main__":
    unittest.main()
