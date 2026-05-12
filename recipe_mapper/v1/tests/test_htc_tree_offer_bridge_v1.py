#!/usr/bin/env python3
"""Regression tests for the HTC/tree-first offer bridge."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_htc_tree_offer_bridge_v1 import ProductOffer, build_index, pick_offer, product_matches_recipe  # noqa: E402
from htc_tree_core_v1 import decode_htc, htc_from_tree_identity, identity_tokens  # noqa: E402


def recipe(
    item: str,
    *,
    group: str,
    family: str = "0",
    pid: str,
    canonical: str,
    modifier: str = "",
    htc_code: str = "",
) -> dict[str, str]:
    return {
        "ingredient_item": item,
        "recipe_count": "10",
        "htc_code": htc_code or f"{group}{family}000000",
        "htc_group": group,
        "htc_family": family,
        "identity_code": "",
        "tree_product_identity": pid,
        "tree_canonical_path": canonical,
        "tree_modifier": modifier,
    }


def offer(
    name: str,
    *,
    group: str,
    family: str = "0",
    pid: str,
    canonical: str,
    modifier: str = "",
    source: str = "walmart",
    cents: int = 399,
    grams: float = 100.0,
    tree_authority: str = "test_tree",
    htc_code: str = "",
) -> ProductOffer:
    return ProductOffer(
        source=source,
        rowid=name,
        upc=name,
        name=name,
        brand="",
        grams=grams,
        cents=cents,
        cpg=cents / grams,
        category_path=canonical,
        category_path_walmart=canonical,
        tree_product_identity=pid,
        tree_canonical_path=canonical,
        tree_modifier=modifier,
        taxonomy_status="approved_taxonomy",
        htc_code=htc_code or f"{group}{family}000000",
        htc_group=group,
        htc_family=family,
        htc_form="0",
        htc_processing="0",
        htc_ptype="0",
        tree_authority=tree_authority,
        title_terms_set=frozenset(identity_tokens(name)),
    )


class HtcTreeOfferBridgeV1Tests(unittest.TestCase):
    def assertMatch(self, row: dict[str, str], product: ProductOffer) -> None:
        ok, score, reason = product_matches_recipe(row, product)
        self.assertTrue(ok, (score, reason, product))

    def assertRejects(self, row: dict[str, str], product: ProductOffer) -> str:
        ok, _score, reason = product_matches_recipe(row, product)
        self.assertFalse(ok, (reason, product))
        return reason

    def test_garlic_rejects_garlic_flavored_potatoes(self) -> None:
        row = recipe(
            "garlic",
            group="6",
            pid="Garlic",
            canonical="Produce > Vegetables > Garlic",
        )
        potato = offer(
            "The Little Potato Company Garlic Parsley Potatoes, 1 lb Tray",
            group="6",
            pid="Potatoes",
            canonical="Produce > Vegetables > Potatoes",
            modifier="Garlic Parsley",
        )
        garlic = offer(
            "Fresh Whole Garlic",
            group="6",
            pid="Garlic",
            canonical="Produce > Vegetables > Garlic",
        )

        self.assertEqual("tree_identity_conflict", self.assertRejects(row, potato))
        self.assertMatch(row, garlic)

    def test_ground_cinnamon_rejects_cereal_and_accepts_spice(self) -> None:
        row = recipe(
            "ground cinnamon",
            group="E",
            family="2",
            pid="Cinnamon",
            canonical="Pantry > Spices & Seasonings > Cinnamon",
        )
        cereal = offer(
            "General Mills Apple Cinnamon Large Size Cheerios",
            group="E",
            family="2",
            pid="Cereal",
            canonical="Pantry > Cereal",
        )
        spice = offer(
            "Great Value Ground Cinnamon, 2.37 oz",
            group="E",
            family="2",
            pid="Cinnamon",
            canonical="Pantry > Spices & Seasonings > Cinnamon",
        )

        self.assertEqual("ground_form_mismatch", self.assertRejects(row, cereal))
        self.assertMatch(row, spice)

    def test_plain_banana_rejects_snacks_and_accepts_produce(self) -> None:
        row = recipe(
            "banana",
            group="7",
            pid="Bananas",
            canonical="Produce > Fruit > Bananas",
        )
        snack = offer(
            "Calbee Harvest Snaps Kids Crispy Bananas",
            group="7",
            pid="Bananas",
            canonical="Snack > Fruit Snacks > Bananas",
        )
        produce = offer(
            "Fresh Banana",
            group="7",
            pid="Bananas",
            canonical="Produce > Fruit > Bananas",
        )

        self.assertEqual("plain_produce_composite", self.assertRejects(row, snack))
        self.assertMatch(row, produce)

    def test_plain_eggs_reject_hard_boiled_and_accept_shell_eggs(self) -> None:
        row = recipe(
            "eggs",
            group="5",
            pid="Eggs",
            canonical="Dairy > Eggs",
        )
        hard_boiled = offer(
            "Great Value Cage-Free Hard Boiled Eggs",
            group="5",
            pid="Eggs",
            canonical="Dairy > Eggs",
        )
        pickled = offer(
            "Old South Pickled Eggs, Whole, Mild, Shelf Stable Jar",
            group="5",
            pid="Eggs",
            canonical="Dairy > Eggs",
        )
        scramble_mix = offer(
            "Eggylicious Egg Scramble Mix Made with Whole Eggs",
            group="5",
            pid="Eggs",
            canonical="Dairy > Eggs",
        )
        egg_bites = offer(
            "Jimmy Dean Sausage Three Cheese Egg Bites",
            group="5",
            pid="Egg Bites",
            canonical="Dairy > Eggs > Egg Bites",
        )
        shell_eggs = offer(
            "Great Value Large White Eggs, 18 Count",
            group="5",
            pid="Eggs",
            canonical="Dairy > Eggs",
            tree_authority="white_shell_egg_correction",
        )

        self.assertEqual("egg_process_mismatch", self.assertRejects(row, hard_boiled))
        self.assertEqual("egg_process_mismatch", self.assertRejects(row, pickled))
        self.assertEqual("egg_process_mismatch", self.assertRejects(row, scramble_mix))
        self.assertEqual("egg_product_form_mismatch", self.assertRejects(row, egg_bites))
        self.assertMatch(row, shell_eggs)

    def test_plain_tomatoes_accept_fresh_roma_bag_not_plants(self) -> None:
        row = recipe(
            "tomatoes",
            group="6",
            family="7",
            pid="Tomatoes",
            canonical="Produce > Vegetables > Tomatoes",
        )
        roma = offer(
            "Fresh Roma Tomato, 2 lb Bag",
            group="6",
            family="7",
            pid="Tomatoes",
            canonical="Produce > Vegetables > Tomatoes",
        )
        plant = offer(
            "Bonnie Plants Sun Sugar Yellow Cherry Tomato Live Plants",
            group="6",
            family="7",
            pid="Tomatoes",
            canonical="Patio > Garden > Live Plants > Tomato Plants",
        )

        self.assertMatch(row, roma)
        self.assertEqual("plain_produce_nonfresh_path", self.assertRejects(row, plant))

    def test_ghee_uses_oil_tree_not_plain_butter(self) -> None:
        row = recipe(
            "ghee",
            group="B",
            pid="Ghee",
            canonical="Pantry > Oil > Ghee",
        )
        ghee = offer(
            "Simple Truth Organic Ghee Butter",
            group="B",
            pid="Ghee",
            canonical="Pantry > Oil > Ghee",
        )
        butter = offer(
            "Kroger Unsalted Butter",
            group="1",
            family="4",
            pid="Butter",
            canonical="Dairy > Butter",
        )

        self.assertMatch(row, ghee)
        self.assertEqual("htc_mismatch", self.assertRejects(row, butter))

    def test_ground_mace_accepts_mace_spice_tree(self) -> None:
        row = recipe(
            "ground mace",
            group="E",
            family="2",
            pid="Spice Blend",
            canonical="Pantry > Spices & Seasonings > Spice Blend",
            modifier="Mace",
        )
        mace = offer(
            "McCormick Ground Mace, 0.9 oz",
            group="E",
            family="2",
            pid="Spice Blend",
            canonical="Pantry > Spices & Seasonings > Spice Blend",
            modifier="Mace",
        )

        self.assertMatch(row, mace)

    def test_generic_spice_blend_recipe_can_match_specific_spice_leaf(self) -> None:
        row = recipe(
            "cumin seeds",
            group="E",
            family="6",
            pid="Spice Blend",
            canonical="Pantry > Spices & Seasonings > Spice Blend",
            modifier="Cumin",
        )
        cumin_seed = offer(
            "El Guapo No Artificial Flavors Whole Cumin, 0.75 oz Bag",
            group="E",
            family="4",
            pid="Cumin Seed",
            canonical="Pantry > Spices & Seasonings > Cumin Seed",
        )
        cinnamon = offer(
            "Great Value Ground Cinnamon, 2 oz",
            group="E",
            family="2",
            pid="Cinnamon",
            canonical="Pantry > Spices & Seasonings > Cinnamon",
        )

        self.assertMatch(row, cumin_seed)
        self.assertEqual("htc_mismatch", self.assertRejects(row, cinnamon))

    def test_spice_identity_rejects_tea_products(self) -> None:
        row = recipe(
            "cardamom seeds",
            group="E",
            family="2",
            pid="Spice Blend",
            canonical="Pantry > Spices & Seasonings > Spice Blend",
            modifier="Cardamom",
        )
        tea = offer(
            "Yogi Cozy Cardamom Caffeine Free Immune Sleep Supplement Herbal Tea",
            group="E",
            family="2",
            pid="Spice Blend",
            canonical="Pantry > Spices & Seasonings > Spice Blend",
            modifier="Cardamom",
        )

        self.assertEqual("spice_beverage_product", self.assertRejects(row, tea))

    def test_plain_butter_rejects_flavor_text_and_accepts_butter(self) -> None:
        row = recipe(
            "butter",
            group="1",
            family="4",
            pid="Butter",
            canonical="Dairy > Butter",
        )
        syrup = offer(
            "Kroger Butter Flavored Pancake Syrup",
            group="1",
            family="4",
            pid="Butter",
            canonical="Dairy > Butter",
        )
        spreadable = offer(
            "Kroger Butter with Olive Oil & Sea Salt Spreadable Tub",
            group="1",
            family="4",
            pid="Butter",
            canonical="Dairy > Butter",
        )
        butter_pecan = offer(
            "Edy's/Dreyer's Butter Pecan, 1.5 Qt",
            group="1",
            family="4",
            pid="Butter",
            canonical="Dairy > Butter",
        )
        croissant_loaf = offer(
            "Private Selection All Butter Croissant Loaf",
            group="1",
            family="4",
            pid="Butter",
            canonical="Dairy > Butter",
        )
        butter = offer(
            "Kroger Unsalted Butter Sticks",
            group="1",
            family="4",
            pid="Butter",
            canonical="Dairy > Butter",
        )

        self.assertEqual("butter_flavor_text", self.assertRejects(row, syrup))
        self.assertEqual("butter_flavor_text", self.assertRejects(row, spreadable))
        self.assertEqual("butter_flavor_text", self.assertRejects(row, butter_pecan))
        self.assertEqual("butter_flavor_text", self.assertRejects(row, croissant_loaf))
        self.assertMatch(row, butter)

    def test_fresh_chili_peppers_reject_jarred_and_accept_fresh_varieties(self) -> None:
        row = recipe(
            "green chili peppers",
            group="6",
            pid="Chili Peppers",
            canonical="Produce > Vegetables > Chili Peppers",
        )
        jarred = offer(
            "Mezzetta Fresno Chili Peppers, 16 fl oz Jar",
            group="6",
            pid="Chili Peppers",
            canonical="Produce > Vegetables > Chili Peppers",
        )
        canned_packaged = offer(
            "Mezzetta Fresno Chili Peppers",
            group="6",
            pid="Chili Peppers",
            canonical="Produce > Vegetables > Chili Peppers",
        )
        serrano = offer(
            "Fresh Green Serrano Peppers",
            group="6",
            pid="Serrano Peppers",
            canonical="Produce > Vegetables > Serrano Peppers",
        )

        self.assertEqual("plain_produce_composite", self.assertRejects(row, jarred))
        canned_packaged = ProductOffer(
            **{**canned_packaged.__dict__, "category_path": "Canned & Packaged"}
        )
        self.assertEqual("plain_produce_composite", self.assertRejects(row, canned_packaged))
        self.assertMatch(row, serrano)

    def test_boneless_skinless_chicken_breasts_are_allowed_identity_terms(self) -> None:
        row = recipe(
            "boneless skinless chicken breasts",
            group="3",
            pid="Chicken Breasts",
            canonical="Meat & Seafood > Poultry > Chicken Breasts",
        )
        chicken = offer(
            "Great Value Boneless Skinless Chicken Breasts",
            group="3",
            pid="Chicken Breasts",
            canonical="Meat & Seafood > Poultry > Chicken Breasts",
        )

        self.assertMatch(row, chicken)

    def test_vanilla_extract_parent_is_allowed_when_title_has_identity(self) -> None:
        row = recipe(
            "vanilla",
            group="E",
            family="5",
            pid="Vanilla Extract",
            canonical="Pantry > Baking Extracts > Vanilla Extract",
        )
        extract = offer(
            "Kroger Pure Vanilla Extract",
            group="E",
            family="5",
            pid="Extract",
            canonical="Pantry > Baking Extracts",
        )

        self.assertMatch(row, extract)

    def test_specific_seed_spice_terms_must_match(self) -> None:
        row = recipe(
            "cardamom seeds",
            group="E",
            family="2",
            pid="Seeds",
            canonical="Pantry > Spices & Seasonings > Seeds",
        )
        cinnamon_seeds = offer(
            "DAVID Cinnamon Seeds Snacks",
            group="E",
            family="2",
            pid="Seeds",
            canonical="Pantry > Spices & Seasonings > Seeds",
        )
        cardamom = offer(
            "Swad Cardamom Seeds",
            group="E",
            family="2",
            pid="Seeds",
            canonical="Pantry > Spices & Seasonings > Seeds",
        )
        self.assertEqual("specific_term_missing", self.assertRejects(row, cinnamon_seeds))
        self.assertMatch(row, cardamom)

        coriander_row = recipe(
            "coriander seeds",
            group="E",
            family="2",
            pid="Seeds",
            canonical="Pantry > Spices & Seasonings > Seeds",
        )
        curry_powder = offer(
            "VAHDAM Curry Powder Spice Blend with Coriander",
            group="E",
            family="2",
            pid="Seeds",
            canonical="Pantry > Spices & Seasonings > Seeds",
        )
        ground_cardamom = offer(
            "Badia Spices Organic Ground Cardamom",
            group="E",
            family="2",
            pid="Seeds",
            canonical="Pantry > Spices & Seasonings > Seeds",
        )
        self.assertEqual("seed_form_mismatch", self.assertRejects(coriander_row, curry_powder))
        self.assertEqual("seed_form_mismatch", self.assertRejects(row, ground_cardamom))

        coriander_spice_blend_row = recipe(
            "coriander seeds",
            group="E",
            family="4",
            pid="Spice Blend",
            canonical="Pantry > Spices & Seasonings > Spice Blend",
            modifier="Coriander Seed",
        )
        whole_coriander = offer(
            "McCormick Whole Coriander Seed, 1.25 oz",
            group="E",
            family="4",
            pid="Coriander Seed",
            canonical="Pantry > Spices & Seasonings > Coriander Seed",
        )
        ground_coriander_seed = offer(
            "Private Selection Ground Coriander Seed Shaker",
            group="E",
            family="4",
            pid="Coriander Seed",
            canonical="Pantry > Spices & Seasonings > Coriander Seed",
        )
        self.assertMatch(coriander_spice_blend_row, whole_coriander)
        self.assertEqual("seed_form_mismatch", self.assertRejects(coriander_spice_blend_row, ground_coriander_seed))

        index = build_index([
            curry_powder,
            whole_coriander,
            offer(
                "Generic Italian Seasoning",
                group="E",
                family="4",
                pid="Spice Blend",
                canonical="Pantry > Spices & Seasonings > Spice Blend",
            ),
        ])
        picked, _score, status, _detail = pick_offer(coriander_spice_blend_row, index, "all")
        self.assertEqual("safe_priced", status)
        self.assertEqual("Coriander Seed", picked.tree_product_identity if picked else "")

    def test_component_noise_rejects_cereal_and_sazon(self) -> None:
        almonds = recipe(
            "almonds",
            group="A",
            pid="Almonds",
            canonical="Snack > Nuts > Almonds",
        )
        cereal = offer(
            "Post Honey Bunches of Oats with Almonds",
            group="A",
            pid="Almonds",
            canonical="Snack > Nuts > Almonds",
        )
        cilantro = recipe(
            "cilantro",
            group="E",
            family="3",
            pid="Cilantro",
            canonical="Produce > Fresh Herbs > Cilantro",
        )
        sazon = offer(
            "GOYA Sazon with Cilantro & Tomato",
            group="E",
            family="3",
            pid="Cilantro",
            canonical="Produce > Fresh Herbs > Cilantro",
        )

        self.assertEqual("composite_noise", self.assertRejects(almonds, cereal))
        self.assertEqual("composite_noise", self.assertRejects(cilantro, sazon))

    def test_lemon_zest_does_not_match_lemonade(self) -> None:
        row = recipe(
            "lemon zest",
            group="7",
            pid="Lemon Zest",
            canonical="Produce > Fruit > Lemon Zest",
        )
        lemonade = offer(
            "Tropicana Classic Lemonade Made With Real Lemons",
            group="7",
            pid="Lemonade",
            canonical="Produce > Fruit > Lemonade",
        )

        self.assertEqual("zest_mismatch", self.assertRejects(row, lemonade))

    def test_title_token_candidates_cover_tree_variants(self) -> None:
        cornstarch = recipe(
            "cornstarch",
            group="8",
            family="7",
            pid="Cornstarch",
            canonical="Pantry > Flour > Cornstarch",
        )
        corn_starch = offer(
            "Great Value Corn Starch, 16 oz",
            group="8",
            family="7",
            pid="Corn Starch",
            canonical="Pantry > Flour > Corn Starch",
        )
        tomato_paste = recipe(
            "tomato paste",
            group="6",
            family="7",
            pid="Tomato Paste",
            canonical="Pantry > Canned Vegetables > Tomato Paste",
        )
        canned_paste = offer(
            "Great Value Tomato Paste, 6 oz",
            group="6",
            family="7",
            pid="Tomato Paste",
            canonical="Pantry > Canned Vegetables > Tomato Paste",
        )
        breadcrumbs = recipe(
            "breadcrumbs",
            group="8",
            family="0",
            pid="Breadcrumbs",
            canonical="Pantry > Baking Mixes > Breadcrumbs",
        )
        bread_crumbs = offer(
            "Great Value Plain Bread Crumbs, 15 oz",
            group="8",
            family="0",
            pid="Bread",
            canonical="Bakery > Bread",
        )

        self.assertMatch(cornstarch, corn_starch)
        self.assertMatch(tomato_paste, canned_paste)
        self.assertMatch(breadcrumbs, bread_crumbs)

    def test_unresolved_spice_recipe_can_match_specific_spice_title(self) -> None:
        row = recipe(
            "ground cloves",
            group="E",
            family="2",
            pid="",
            canonical="",
        )
        cloves = offer(
            "Great Value Ground Cloves, 2 oz",
            group="E",
            family="2",
            pid="Spice Blend",
            canonical="Pantry > Spices & Seasonings > Spice Blend",
        )

        self.assertMatch(row, cloves)

    def test_title_recall_does_not_accept_wrong_forms(self) -> None:
        scallions = recipe(
            "scallions",
            group="6",
            family="5",
            pid="Green Onions",
            canonical="Produce > Vegetables > Green Onions",
        )
        chips = offer(
            "Mikesell's Green Onion Potato Chips",
            group="6",
            family="5",
            pid="Green Onions",
            canonical="Produce > Vegetables > Green Onions",
        )
        fresh_green_onions = offer(
            "Fresh Organic Whole Green Onions Vegetable",
            group="6",
            family="5",
            pid="Green Onions",
            canonical="Produce > Vegetables > Green Onions",
        )
        ground_coriander = recipe(
            "ground coriander",
            group="E",
            family="4",
            pid="Spice Blend",
            canonical="Pantry > Spices & Seasonings > Spice Blend",
            modifier="Ground Coriander",
        )
        curry_powder = offer(
            "VAHDAM Curry Powder Spice Blend with Coriander",
            group="E",
            family="4",
            pid="Spice Blend",
            canonical="Pantry > Spices & Seasonings > Spice Blend",
        )
        coriander_powder = offer(
            "Ground Coriander Powder",
            group="E",
            family="4",
            pid="Spice Blend",
            canonical="Pantry > Spices & Seasonings > Spice Blend",
        )
        fresh_ginger = recipe(
            "fresh ginger",
            group="E",
            family="4",
            pid="Ginger",
            canonical="Pantry > Spices & Seasonings > Ginger",
        )
        ginger_drink = offer(
            "Bolthouse Farms Immunity Pineapple Kale Ginger Boost",
            group="E",
            family="4",
            pid="Ginger",
            canonical="Pantry > Spices & Seasonings > Ginger",
        )
        ginger_root = offer(
            "Organic Fresh Ginger Root",
            group="E",
            family="4",
            pid="Ginger",
            canonical="Produce > Vegetables > Ginger",
        )

        self.assertEqual("plain_produce_composite", self.assertRejects(scallions, chips))
        self.assertMatch(scallions, fresh_green_onions)
        onion_tree_green_onions = offer(
            "Fresh Organic Whole Green Onions Vegetable",
            group="6",
            family="5",
            pid="Onions",
            canonical="Produce > Vegetables > Onions",
        )
        canned_onion_tomatoes = offer(
            "Del Monte Diced Tomatoes with Green Peppers & Onions, 14.5 oz Can",
            group="6",
            family="5",
            pid="Onions",
            canonical="Produce > Vegetables > Onions",
        )
        self.assertMatch(scallions, onion_tree_green_onions)
        self.assertEqual("plain_produce_composite", self.assertRejects(scallions, canned_onion_tomatoes))
        self.assertEqual("ground_form_mismatch", self.assertRejects(ground_coriander, curry_powder))
        self.assertMatch(ground_coriander, coriander_powder)
        direct_ground_coriander = offer(
            "Private Selection Ground Coriander Seed Shaker",
            group="E",
            family="4",
            pid="Coriander Seed",
            canonical="Pantry > Spices & Seasonings > Coriander Seed",
        )
        self.assertMatch(ground_coriander, direct_ground_coriander)
        self.assertEqual("fresh_spice_form_mismatch", self.assertRejects(fresh_ginger, ginger_drink))
        self.assertMatch(fresh_ginger, ginger_root)

    def test_heavy_cream_accepts_whipping_cream_not_substitute(self) -> None:
        row = recipe(
            "heavy cream",
            group="1",
            family="3",
            pid="Heavy Cream",
            canonical="Dairy > Cream > Heavy Cream",
        )
        heavy_whipping = offer(
            "Kroger Heavy Whipping Cream Pint",
            group="1",
            family="3",
            pid="Heavy Whipping Cream",
            canonical="Dairy > Cream > Heavy Whipping Cream",
        )
        dairy_free = offer(
            "Country Crock Homestyle Dairy Free Heavy Whipping Cream",
            group="1",
            family="3",
            pid="Heavy Whipping Cream",
            canonical="Dairy > Cream > Heavy Whipping Cream",
        )

        self.assertMatch(row, heavy_whipping)
        self.assertEqual("cream_substitute", self.assertRejects(row, dairy_free))

    def test_dried_fruit_stays_in_fruit_group_not_snack_group(self) -> None:
        raisins_htc = htc_from_tree_identity("Snack > Dried Fruit > Raisins", "Raisins")
        self.assertEqual(("7", "4"), (raisins_htc.group, raisins_htc.family))

        row = recipe(
            "raisins",
            group="7",
            family="4",
            pid="Raisins",
            canonical="Snack > Dried Fruit > Raisins",
        )
        plain_raisins = offer(
            "Sun-Maid California Sun-Dried Raisins",
            group="7",
            family="4",
            pid="Raisins",
            canonical="Snack > Dried Fruit > Raisins",
        )
        yogurt_raisins = offer(
            "Great Value Yogurt Covered Raisins",
            group="7",
            family="4",
            pid="Raisins",
            canonical="Snack > Dried Fruit > Raisins",
        )

        self.assertMatch(row, plain_raisins)
        self.assertEqual("composite_noise", self.assertRejects(row, yogurt_raisins))

    def test_sparkling_water_uses_flavor_slot_and_exact_code_preference(self) -> None:
        lime_htc = htc_from_tree_identity("Beverage > Sparkling Water", "Sparkling Water", "Lime")
        key_lime_htc = htc_from_tree_identity("Beverage > Sparkling Water", "Sparkling Water", "Key Lime")
        lemon_lime_htc = htc_from_tree_identity("Beverage > Sparkling Water", "Sparkling Water", "Lemon Lime")

        self.assertEqual("D208000$", lime_htc.code)
        self.assertEqual("D221000D", key_lime_htc.code)
        self.assertEqual("D20M000E", lemon_lime_htc.code)
        self.assertEqual(("D208000$", "D", "2", "08"), (
            decode_htc("~D208000$").code,
            decode_htc("~D208000$").group,
            decode_htc("~D208000$").family,
            decode_htc("~D208000$").food,
        ))

        row = recipe(
            "lime seltzer water",
            group="D",
            family="2",
            pid="Sparkling Water",
            canonical="Beverage > Sparkling Water",
            modifier="Lime",
            htc_code=lime_htc.code,
        )
        cheap_key_lime = offer(
            "Clear American Key Lime Sparkling Water, 33.8 fl oz",
            group="D",
            family="2",
            pid="Sparkling Water",
            canonical="Beverage > Sparkling Water",
            modifier="Key Lime",
            cents=84,
            grams=999.584,
            htc_code=key_lime_htc.code,
        )
        exact_lime = offer(
            "Polar Zero Calorie Lime Sparkling Seltzer Water, 12 fl oz, 8 Pack Cans",
            group="D",
            family="2",
            pid="Sparkling Water",
            canonical="Beverage > Sparkling Water",
            modifier="Lime",
            cents=328,
            grams=354.882,
            htc_code=lime_htc.code,
        )

        product, _score, status, detail = pick_offer(row, build_index([cheap_key_lime, exact_lime]), "walmart")
        self.assertEqual("safe_priced", status)
        self.assertEqual(exact_lime.name, product.name if product else "")
        self.assertIn("exact_htc", detail)

    def test_plain_mint_accepts_fresh_herb_not_candy(self) -> None:
        row = recipe(
            "mint",
            group="E",
            family="3",
            pid="Mints",
            canonical="Pantry > Spices & Seasonings > Mints",
        )
        fresh_mint = offer(
            "Fresh Organic Mint, 0.5 oz Clamshell",
            group="E",
            family="3",
            pid="Mint",
            canonical="Produce > Herbs > Mint",
        )
        candy_mints = offer(
            "Tic Tac Freshmints Mints 4ct",
            group="J",
            family="0",
            pid="Mints",
            canonical="Snack > Candy > Mints",
        )

        self.assertMatch(row, fresh_mint)
        self.assertEqual("htc_mismatch", self.assertRejects(row, candy_mints))


if __name__ == "__main__":
    unittest.main()
