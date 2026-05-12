import csv
import sys
import tempfile
import unittest
from pathlib import Path


IMPLEMENTATION_ROOT = Path(__file__).resolve().parents[1]
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

from audit_cart_identity_safety import (  # noqa: E402
    expected_bell_pepper,
    expected_chili_powder,
    expected_ham,
    expected_onion,
    expected_seasoning,
    expected_snack_chip,
    expected_sour_cream,
    expected_spice_or_herb,
    expected_yogurt,
    family_for_concept,
    normalization_findings,
    product_contract_findings,
    target_preserves_expected,
)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class CartIdentitySafetyTests(unittest.TestCase):
    def test_onion_variants_preserve_shopping_identity(self) -> None:
        self.assertEqual(expected_onion("large maui onion"), ("sweet onion|||", "sweet onion"))
        self.assertEqual(expected_onion("white onion diced"), ("white onion||white|", "white onion"))
        self.assertIsNone(expected_onion("green onion white and green parts"))
        self.assertIsNone(expected_onion("^green\\s+onions?,?\\s+white\\s+and\\s+green\\s+parts$"))
        self.assertIsNone(expected_onion("crispy fried onion rings"))
        self.assertIsNone(expected_onion("frozen hash brown potatoes with onions and peppers"))
        self.assertIsNone(expected_onion("frzn peas & pearl onions"))
        self.assertEqual(expected_onion("small white pearl onion"), ("pearl onion|||", "pearl onion"))
        self.assertIsNone(family_for_concept("onion dip|||"))
        self.assertIsNone(family_for_concept("cream cheese with chives and onions|||"))
        self.assertIsNone(family_for_concept("onion mix|||"))

    def test_ham_detector_does_not_match_substrings(self) -> None:
        self.assertIsNone(expected_ham("graham cracker crust"))
        self.assertIsNone(family_for_concept("champagne|||"))
        self.assertEqual(expected_ham("sliced ham"), ("sliced ham|||", "sliced ham"))
        self.assertEqual(expected_ham("thin sliced smoked ham"), ("sliced ham|||", "sliced ham"))
        self.assertEqual(expected_ham("few slices cured ham"), ("sliced ham|||", "sliced ham"))
        self.assertEqual(expected_ham("spiral-sliced fully cooked bone-in ham"), ("bone-in smoked ham|||", "bone-in smoked ham"))
        self.assertEqual(expected_ham("smoked ham hock"), ("ham hock|||", "ham hock"))
        self.assertEqual(expected_ham("large smoked ham steak"), ("ham steak|||", "ham steak"))
        self.assertEqual(expected_ham("cubed fully cooked ham"), ("diced ham|||", "diced ham"))
        self.assertEqual(expected_ham("smoked ham bone"), ("ham bone|||", "ham bone"))
        self.assertEqual(expected_ham("turkey ham"), ("turkey ham|||", "turkey ham"))
        self.assertEqual(expected_ham("boneless smoked ham"), ("smoked ham|||", "smoked ham"))
        self.assertIsNone(expected_ham("picnic ham"))
        self.assertIsNone(family_for_concept("ham stock|||"))

    def test_chili_powder_alternative_is_not_auto_flagged(self) -> None:
        self.assertIsNone(expected_chili_powder("chili powder or cayenne pepper"))
        self.assertIsNone(expected_chili_powder("salt, pepper, chili powder and cumin"))
        self.assertIsNone(expected_chili_powder("chili powder-seasoned pinto beans"))
        self.assertEqual(expected_chili_powder("new mexico chili powder"), ("new mexico chili powder|||", "chili powder"))

    def test_yogurt_detector_preserves_state_without_negation_traps(self) -> None:
        self.assertEqual(expected_yogurt("nonfat vanilla yogurt"), ("nonfat vanilla yogurt|||", "nonfat vanilla yogurt"))
        self.assertEqual(expected_yogurt("plain low fat greek yogurt"), ("plain low-fat greek yogurt|||", "plain low-fat greek yogurt"))
        self.assertEqual(expected_yogurt("plain 2% greek yogurt"), ("plain low-fat greek yogurt|||", "plain low-fat greek yogurt"))
        self.assertEqual(expected_yogurt("nonfat peach yogurt"), ("nonfat peach yogurt|||", "nonfat peach yogurt"))
        self.assertEqual(expected_yogurt("plain yogurt (not nonfat)"), ("plain yogurt|||", "plain yogurt"))
        self.assertEqual(expected_yogurt("plain greek yogurt (not vanilla)"), ("plain greek yogurt|||", "plain greek yogurt"))
        self.assertIsNone(expected_yogurt("vanilla-flavored soy yogurt"))
        self.assertIsNone(expected_yogurt("low-fat sour cream, mixed with yogurt"))
        self.assertIsNone(expected_yogurt("yogurt cheese"))
        self.assertIsNone(family_for_concept("yogurt cheese|||"))
        self.assertIsNone(family_for_concept("yogurt covered raisin|||"))

    def test_sour_cream_detector_preserves_required_fat_state_only(self) -> None:
        self.assertEqual(expected_sour_cream("non-fat sour cream"), ("sour cream|fat-free||", "fat-free sour cream"))
        self.assertEqual(expected_sour_cream("reduced-fat sour cream"), ("sour cream|low-fat||", "low-fat sour cream"))
        self.assertIsNone(expected_sour_cream("sour cream (not fat free)"))
        self.assertIsNone(expected_sour_cream("sour cream (can use low fat)"))
        self.assertIsNone(expected_sour_cream("low-fat buttermilk (or sour cream)"))
        self.assertIsNone(expected_sour_cream("sour cream (fat free works well)"))
        self.assertIsNone(expected_sour_cream("large tub sour cream (nonfat is available)"))
        self.assertIsNone(family_for_concept("sour cream with chive|||"))
        self.assertIsNone(family_for_concept("yogurt or sour cream|||"))

    def test_seasoning_detector_skips_component_contexts(self) -> None:
        self.assertIsNone(expected_seasoning("ground beef, cooked with taco seasoning"))
        self.assertIsNone(expected_seasoning("chili powder, can use taco seasoning"))
        self.assertIsNone(expected_seasoning("pckt taco seasoning/ranch dressing"))
        self.assertEqual(expected_seasoning("taco seasoning, dry mix"), ("taco seasoning mix|||", "taco seasoning mix"))
        self.assertEqual(
            expected_seasoning("mccormick montreal steak seasoning"),
            ("montreal steak seasoning|||", "montreal steak seasoning"),
        )

    def test_snack_chip_detector_preserves_chip_family(self) -> None:
        self.assertEqual(expected_snack_chip("ridged potato chips"), ("potato chips|||", "potato chips"))
        self.assertEqual(expected_snack_chip("plain potato chips"), ("potato chips|plain||", "plain potato chips"))
        self.assertEqual(expected_snack_chip("tortilla chips crushed"), ("tortilla chips|||", "tortilla chips"))
        self.assertIsNone(expected_snack_chip("chocolate chips"))
        self.assertIsNone(expected_snack_chip("wood chips for smoking"))

    def test_spice_and_herb_detector_preserves_form(self) -> None:
        self.assertEqual(expected_spice_or_herb("ground cloves"), ("ground cloves|||", "ground cloves"))
        self.assertEqual(expected_spice_or_herb("ground cumin"), ("ground cumin|||", "ground cumin"))
        self.assertEqual(expected_spice_or_herb("fresh thyme"), ("thyme|||fresh", "fresh thyme"))
        self.assertEqual(expected_spice_or_herb("dried basil"), ("dried basil|||", "dried basil"))
        self.assertIsNone(expected_spice_or_herb("ginger ale"))
        self.assertIsNone(expected_spice_or_herb("tomatoes with basil"))
        self.assertIsNone(expected_spice_or_herb("dill relish"))
        self.assertIsNone(expected_spice_or_herb("coarse-grained dijon mustard"))
        self.assertIsNone(expected_spice_or_herb("salt, pepper, and paprika"))

    def test_bell_pepper_detector_skips_chile_and_tomato_context(self) -> None:
        self.assertIsNone(expected_bell_pepper("dried red pepper"))
        self.assertIsNone(expected_bell_pepper("tomatoes with green chile peppers"))
        self.assertIsNone(expected_bell_pepper("red pepper hummus"))
        self.assertIsNone(expected_bell_pepper("frozen broccoli, red peppers, onions and mushrooms"))
        self.assertIsNone(family_for_concept("hot red pepper|||"))
        self.assertIsNone(family_for_concept("red pepper jelly|||"))
        self.assertEqual(expected_bell_pepper("medium green pepper"), ("green bell pepper|||", "green bell pepper"))

    def test_target_preservation_accepts_exact_or_expected_family(self) -> None:
        self.assertTrue(target_preserves_expected("white onion||white|", "white onion||white|", "white onion"))
        self.assertTrue(target_preserves_expected("yellow onion|||", "yellow onion|||", "yellow onion"))
        self.assertFalse(target_preserves_expected("onion|||", "yellow onion|||", "yellow onion"))

    def test_normalization_findings_flag_variant_collapse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.csv"
            write_csv(
                path,
                [
                    "rule_id",
                    "rule_type",
                    "match_type",
                    "input_surface",
                    "canonical_concept_key",
                    "canonical_name",
                    "status",
                    "notes",
                ],
                [
                    {
                        "rule_id": "bad_yellow_onion",
                        "rule_type": "alias",
                        "match_type": "exact",
                        "input_surface": "large yellow onion",
                        "canonical_concept_key": "onion|||",
                        "canonical_name": "onion",
                        "status": "approved",
                        "notes": "42 occ",
                    },
                    {
                        "rule_id": "good_yellow_onion",
                        "rule_type": "alias",
                        "match_type": "exact",
                        "input_surface": "yellow onion",
                        "canonical_concept_key": "yellow onion|||",
                        "canonical_name": "yellow onion",
                        "status": "approved",
                        "notes": "100 occ",
                    },
                ],
            )

            findings = normalization_findings(path)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].row_id, "bad_yellow_onion")
        self.assertEqual(findings[0].expected_target, "yellow onion|||")

    def test_product_contract_findings_flag_wrong_category(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contracts.csv"
            write_csv(
                path,
                [
                    "contract_id",
                    "concept_keys",
                    "allowed_categories",
                    "required_any",
                    "forbidden_any",
                    "positive_examples",
                    "negative_examples",
                    "policy",
                    "notes",
                ],
                [
                    {
                        "contract_id": "bad_yogurt",
                        "concept_keys": '["fat free greek yogurt|||"]',
                        "allowed_categories": '["Cheese"]',
                        "required_any": "[]",
                        "forbidden_any": "[]",
                        "positive_examples": "[]",
                        "negative_examples": "[]",
                        "policy": "direct_buy",
                        "notes": "",
                    },
                    {
                        "contract_id": "good_yogurt",
                        "concept_keys": '["plain greek yogurt|||"]',
                        "allowed_categories": '["Yogurt"]',
                        "required_any": "[]",
                        "forbidden_any": "[]",
                        "positive_examples": "[]",
                        "negative_examples": "[]",
                        "policy": "direct_buy",
                        "notes": "",
                    },
                ],
            )

            findings = product_contract_findings(path)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].row_id, "bad_yogurt")
        self.assertEqual(findings[0].issue, "allowed_category_mismatch")


if __name__ == "__main__":
    unittest.main()
