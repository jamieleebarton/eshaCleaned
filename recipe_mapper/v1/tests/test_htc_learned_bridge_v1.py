#!/usr/bin/env python3
"""Regression tests for the corpus-learned HTC bridge."""
from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from htc_learned_bridge_v1 import (  # noqa: E402
    ConceptEvidence,
    IngredientProfile,
    ProductRecord,
    _choose_product_tree_fields,
    _fresh_herb_product_tree_fields,
    concept_index,
    contract_reject_reason,
    generate_candidates,
    learn_contract,
    pick_product_for_contract,
    product_index,
    token_set,
)


def concept(
    pid: str,
    canonical: str,
    *,
    title: str = "",
    modifier: str = "",
    htc: tuple[str, ...] = (),
    refs: str = "",
) -> ConceptEvidence:
    ev = ConceptEvidence(pid=pid, canonical=canonical, modifier=modifier, count=100, sample_title=title)
    for prefix in htc:
        ev.htc_prefix_counts[prefix] += 10
    for blob, counter in (
        (pid, ev.identity_tokens),
        (modifier, ev.identity_tokens),
        (canonical, ev.identity_tokens),
        (canonical, ev.path_tokens),
        (title, ev.title_tokens),
        (refs, ev.reference_tokens),
    ):
        counter.update(token_set(blob))
    ev.confidence_sum = 95.0
    ev.confidence_n = 100
    return ev


def product(
    name: str,
    *,
    pid: str,
    canonical: str,
    htc_code: str,
    category: str = "Home Page/Food",
    cents: int = 399,
    grams: float = 100.0,
    modifier: str = "",
    upc: str = "",
    source: str = "",
    evidence_score: float = 90.0,
) -> ProductRecord:
    return ProductRecord(
        rowid=name,
        source=source,
        upc=upc,
        name=name,
        grams=grams,
        cents=cents,
        category_path=category,
        category_path_walmart=category,
        htc_code=htc_code,
        proposed_pid=pid,
        proposed_canonical=canonical,
        proposed_modifier=modifier,
        taxonomy_status="approved_taxonomy",
        evidence_score=evidence_score,
    )


class HtcLearnedBridgeV1Tests(unittest.TestCase):
    def test_ground_cloves_contract_is_learned_from_positive_and_negative_evidence(self) -> None:
        index = concept_index([
            concept(
                "Cloves",
                "Pantry > Spices & Seasonings > Cloves",
                title="Great Value Ground Cloves",
                htc=("E2",),
                refs="Spices cloves ground",
            ),
            concept(
                "Garlic",
                "Produce > Vegetables > Garlic",
                title="Fresh Garlic Cloves",
                htc=("60",),
                refs="Garlic raw cloves",
            ),
            concept("Cookies", "Bakery > Cookies", title="Clove Cookies", htc=("80",)),
            concept("Candy", "Snack > Candy", title="Clove Candy", htc=("80",)),
        ])
        profile = IngredientProfile(item="ground cloves", recipe_count=100, htc_code="E200002B", sr28_desc="Spices, cloves, ground")

        candidates = generate_candidates(profile, index)
        contract = learn_contract(profile, candidates, index)

        self.assertEqual("ready", contract.status, contract)
        self.assertEqual("Cloves", contract.concept_pid)
        self.assertIn("clove", contract.required_terms)
        self.assertIn("garlic", contract.forbidden_terms)
        self.assertIn("cookie", contract.forbidden_terms)
        self.assertIn("candy", contract.forbidden_terms)
        self.assertIn("Pantry > Spices & Seasonings", contract.allowed_paths)

        real = product(
            "Great Value Ground Cloves, 2 oz",
            pid="Cloves",
            canonical="Pantry > Spices & Seasonings > Cloves",
            htc_code="E200002B",
            category="Home Page/Food/Pantry/Spices & Seasonings",
        )
        garlic = product(
            "Fresh Garlic Cloves",
            pid="Garlic",
            canonical="Produce > Vegetables > Garlic",
            htc_code="6000000A",
            category="Home Page/Food/Produce/Fresh Vegetables/Garlic",
        )
        self.assertEqual("", contract_reject_reason(contract, real))
        self.assertIn(
            contract_reject_reason(contract, garlic),
            {"primary_identity_conflict:Garlic", "forbidden_term:garlic", "path_conflict", "htc_conflict:60"},
        )

    def test_almond_creamer_rejects_by_learned_path_and_component_context(self) -> None:
        index = concept_index([
            concept("Almonds", "Snack > Nuts > Almonds", title="Raw Whole Almonds", htc=("A0",), refs="Nuts almonds"),
            concept(
                "Half and Half",
                "Dairy > Cream > Half and Half",
                title="nutpods Half and Half made with Almonds and Coconuts",
                htc=("10",),
                refs="Creamer half and half almond coconut",
            ),
        ])
        profile = IngredientProfile(item="almonds", recipe_count=50, htc_code="A0000001", sr28_desc="Nuts, almonds")
        contract = learn_contract(profile, generate_candidates(profile, index), index)
        creamer = product(
            "nutpods Non Dairy Half & Half Alternative made with Almonds and Coconuts",
            pid="Half and Half",
            canonical="Dairy > Cream > Half and Half",
            htc_code="1000000D",
            category="Home Page/Food/Dairy/Creamer",
        )

        self.assertEqual("ready", contract.status, contract)
        self.assertIn("almond", contract.required_terms)
        self.assertIn(
            contract_reject_reason(contract, creamer),
            {"primary_identity_conflict:Half and Half", "path_conflict", "forbidden_term:coconut", "forbidden_term:creamer"},
        )

    def test_butter_pecan_ice_cream_is_not_an_offer_for_butter(self) -> None:
        index = concept_index([
            concept("Butter", "Dairy > Butter", title="Unsalted Sweet Cream Butter", htc=("10",), refs="Butter"),
            concept("Ice Cream", "Frozen > Ice Cream", title="Butter Pecan Ice Cream", htc=("13",), refs="Ice cream"),
        ])
        profile = IngredientProfile(item="butter", recipe_count=60, htc_code="1000000D", sr28_desc="Butter, without salt")
        contract = learn_contract(profile, generate_candidates(profile, index), index)
        products = product_index([
            product("Edy's Butter Pecan Ice Cream", pid="Ice Cream", canonical="Frozen > Ice Cream", htc_code="1300000A"),
            product("Great Value Unsalted Butter", pid="Butter", canonical="Dairy > Butter", htc_code="1000000D", cents=499),
        ])

        match = pick_product_for_contract(contract, products)

        self.assertEqual("accepted_offer", match.status, match)
        self.assertIsNotNone(match.product)
        self.assertEqual("Great Value Unsalted Butter", match.product.name)

    def test_tree_primary_identity_beats_flavor_tokens(self) -> None:
        index = concept_index([
            concept("Garlic", "Produce > Vegetables > Garlic", title="Garlic Chopped", htc=("60",), refs="Garlic raw"),
            concept("Potatoes", "Produce > Vegetables > Potatoes", title="Garlic Parsley Fresh Creamer Potatoes", htc=("71",), refs="Potatoes fresh"),
        ])
        profile = IngredientProfile(item="garlic", recipe_count=100, htc_code="6000000A", sr28_desc="Garlic, raw")
        contract = learn_contract(profile, generate_candidates(profile, index), index)
        potato = product(
            "The Little Potato Company Garlic Parsley Potatoes, 1 lb Tray",
            pid="Potatoes",
            canonical="Produce > Vegetables > Potatoes",
            htc_code="71000100",
            category="Home Page/Food/Fresh Produce/Fresh Vegetables/Potatoes",
            modifier="Garlic Parsley",
        )
        garlic = product(
            "Dorot Gardens Crushed Garlic Cubes",
            pid="Garlic",
            canonical="Frozen > Vegetables > Garlic",
            htc_code="6000000A",
            category="Home Page/Food/Frozen/Frozen Vegetables",
        )

        self.assertEqual("ready", contract.status, contract)
        self.assertEqual("primary_identity_conflict:Potatoes", contract_reject_reason(contract, potato))
        self.assertEqual("", contract_reject_reason(contract, garlic))

    def test_fresh_mint_rejects_candy_and_mouthwash_noise(self) -> None:
        index = concept_index([
            concept("Mint", "Produce > Fresh Herbs > Mint", title="Fresh Mint 0.5 oz Clamshell", htc=("60",), refs="Peppermint fresh"),
            concept("Mints", "Snack > Candy > Mints", title="Sweet Mint Candy", htc=("80",), refs="Candy mints"),
            concept("Mouthwash", "Personal Care > Oral Care > Mouthwash", title="Fresh Mint Mouthwash", htc=("N0",), refs="Mouthwash"),
        ])
        profile = IngredientProfile(item="fresh mint", recipe_count=20, htc_code="6000000A", sr28_desc="Peppermint, fresh")
        contract = learn_contract(profile, generate_candidates(profile, index), index)
        products = product_index([
            product("Sweet Mint Candy", pid="Mints", canonical="Snack > Candy > Mints", htc_code="8000000A"),
            product(
                "Fresh Mint Mouthwash",
                pid="Mouthwash",
                canonical="Personal Care > Oral Care > Mouthwash",
                htc_code="N000000A",
                category="Home Page/Personal Care/Oral Care",
            ),
            product("Fresh Mint, 0.5 oz Clamshell", pid="Mint", canonical="Produce > Fresh Herbs > Mint", htc_code="6000000A"),
        ])

        match = pick_product_for_contract(contract, products)

        self.assertEqual("ready", contract.status, contract)
        self.assertIn("mint", contract.required_terms)
        self.assertIn(
            contract_reject_reason(
                contract,
                product("Wrigley's Doublemint Mint Gum", pid="Mints", canonical="Snack > Candy > Mints", htc_code="8000000A"),
            ),
            {"primary_identity_conflict:Mints", "path_conflict", "form_conflict:candy", "form_conflict:gum", "forbidden_term:candy"},
        )
        self.assertEqual("accepted_offer", match.status, match)
        self.assertIsNotNone(match.product)
        self.assertEqual("Fresh Mint, 0.5 oz Clamshell", match.product.name)

    def test_plain_mint_profile_prefers_fresh_herb_over_candy(self) -> None:
        index = concept_index([
            concept("Mint", "Produce > Fresh Herbs > Mint", title="Fresh Mint 0.5 oz Clamshell", htc=("60",), refs="Peppermint leaves fresh"),
            concept("Mints", "Snack > Candy > Mints", title="Doublemint Mint Gum", htc=("80",), refs="Candy mints"),
        ])
        profile = IngredientProfile(item="mint", recipe_count=20, htc_code="6000000A", sr28_desc="Peppermint, fresh")
        contract = learn_contract(profile, generate_candidates(profile, index), index)

        self.assertEqual("ready", contract.status, contract)
        self.assertEqual("Mint", contract.concept_pid)
        self.assertIn("Produce > Fresh Herbs", contract.allowed_paths)

    def test_plain_mint_uses_fresh_leaf_fallback_when_corpus_only_has_candy(self) -> None:
        index = concept_index([
            concept("Mints", "Snack > Candy > Mints", title="Doublemint Mint Gum", htc=("80",), refs="Candy mints"),
        ])
        profile = IngredientProfile(item="mint", recipe_count=20, htc_code="6000000A", sr28_desc="Peppermint, fresh")
        contract = learn_contract(profile, generate_candidates(profile, index), index)

        self.assertEqual("ready", contract.status, contract)
        self.assertEqual("Mint", contract.concept_pid)
        self.assertIn("fresh_leaf_fallback:non_herb_consensus_winner", contract.evidence)
        self.assertIn("Produce > Fresh Herbs", contract.allowed_paths)

    def test_plain_mint_falls_back_from_spice_mint_and_accepts_retail_produce(self) -> None:
        index = concept_index([
            concept("Mints", "Pantry > Spices & Seasonings > Mints", title="Mint", htc=("E3",), refs="Mint"),
        ])
        profile = IngredientProfile(item="mint", recipe_count=20, htc_code="E300000X", sr28_desc="Peppermint, fresh")
        contract = learn_contract(profile, generate_candidates(profile, index), index)
        products = product_index([
            product(
                "Wrigley's Doublemint Mint Gum Chewing Gum Mega Pack",
                pid="Gum",
                canonical="Snack > Gum",
                htc_code="J000000D",
                category="Candy",
                modifier="Wint O Green Mint",
                evidence_score=90.0,
            ),
            product(
                "Simple Truth Organic Mint",
                pid="Mints",
                canonical="Pantry > Spices & Seasonings > Mints",
                htc_code="E300000X",
                category="Natural & Organic Produce",
                evidence_score=40.0,
            ),
        ])

        match = pick_product_for_contract(contract, products)

        self.assertEqual("ready", contract.status, contract)
        self.assertEqual("Mint", contract.concept_pid)
        self.assertEqual("accepted_offer", match.status, match)
        self.assertIsNotNone(match.product)
        self.assertEqual("Simple Truth Organic Mint", match.product.name)

    def test_bad_sr28_anchor_goes_to_review_instead_of_pricing_wrong_surface(self) -> None:
        index = concept_index([
            concept(
                "Coriander Seed",
                "Pantry > Spices & Seasonings > Coriander Seed",
                title="Whole Coriander Seed",
                htc=("E4",),
                refs="Spices coriander seed",
            ),
        ])
        profile = IngredientProfile(item="ground mace", recipe_count=10, htc_code="E200002B", sr28_desc="Spices, coriander seed")
        contract = learn_contract(profile, generate_candidates(profile, index), index)

        self.assertEqual("needs_llm_contract_review", contract.status, contract)
        self.assertEqual("surface_reference_conflict", contract.review_reason)

    def test_family_conflicts_reject_lookalike_staples(self) -> None:
        index = concept_index([
            concept("Salt", "Pantry > Spices & Seasonings > Salt", title="Table Salt", htc=("E0",), refs="Salt table"),
            concept("White Flour", "Pantry > Flour > White Flour", title="All-Purpose Flour", htc=("87",), refs="Wheat flour white"),
            concept("Almond Flour", "Pantry > Flour > Almond Flour", title="Superfine Blanched Almond Flour", htc=("87",)),
            concept("Sugar", "Pantry > Sweeteners > Sugar", title="Granulated Sugar", htc=("C0",), refs="Sugar granulated"),
            concept("Sugar Substitute", "Pantry > Sweeteners > Sugar Substitute", title="Stevia Sugar Substitute", htc=("C0",)),
            concept("Vegetable Oil", "Pantry > Oil > Vegetable Oil", title="Vegetable Oil", htc=("B0",), refs="Soybean oil"),
            concept("Cooking Spray", "Pantry > Oil > Cooking Spray", title="Duck Fat Cooking Oil Spray", htc=("B0",)),
            concept("Baking Powder", "Pantry > Baking Extracts > Baking Powder", title="Baking Powder", htc=("E5",), refs="Baking powder"),
            concept("Baking Mix", "Pantry > Baking Mixes > Cornbread Mix", title="Honey Cornbread Mix", htc=("80",)),
            concept("Eggs", "Dairy > Eggs", title="Large White Eggs", htc=("50",), refs="Egg whole raw"),
            concept("Egg Whites", "Dairy > Egg Whites", title="Liquid Egg Whites", htc=("50",), refs="Egg white raw"),
        ])

        salt_profile = IngredientProfile(item="salt", recipe_count=10, htc_code="E0000006", sr28_desc="Salt, table")
        salt_contract = learn_contract(salt_profile, generate_candidates(salt_profile, index), index)
        self.assertEqual(
            "absent_claim:salt",
            contract_reject_reason(
                salt_contract,
                product("Salt Free Everything But the Salt Seasoning Blend", pid="Salt", canonical="Pantry > Spices & Seasonings > Salt", htc_code="E0000006"),
            ),
        )

        flour_contract = learn_contract(
            IngredientProfile(item="all-purpose flour", recipe_count=10, htc_code="87000006", sr28_desc="Wheat flour, white, all-purpose"),
            generate_candidates(IngredientProfile(item="all-purpose flour", recipe_count=10, htc_code="87000006", sr28_desc="Wheat flour, white, all-purpose"), index),
            index,
        )
        self.assertIn(
            contract_reject_reason(
                flour_contract,
                product("Superfine Blanched Almond Flour", pid="Almond Flour", canonical="Pantry > Flour > Almond Flour", htc_code="87000006"),
            ),
            {"forbidden_term:almond", "primary_identity_conflict:Almond Flour"},
        )

        sugar_profile = IngredientProfile(item="sugar", recipe_count=10, htc_code="C000000N", sr28_desc="Sugars, granulated")
        sugar_contract = learn_contract(sugar_profile, generate_candidates(sugar_profile, index), index)
        self.assertIn(
            contract_reject_reason(
                sugar_contract,
                product("Granulated Stevia Sugar Substitute", pid="Sugar Substitute", canonical="Pantry > Sweeteners > Sugar Substitute", htc_code="C000000N"),
            ),
            {"forbidden_term:stevia", "primary_identity_conflict:Sugar Substitute"},
        )

        oil_profile = IngredientProfile(item="vegetable oil", recipe_count=10, htc_code="B000600C", sr28_desc="Oil, soybean")
        oil_contract = learn_contract(oil_profile, generate_candidates(oil_profile, index), index)
        self.assertIn(
            contract_reject_reason(
                oil_contract,
                product("Duck Fat Cooking Oil Spray", pid="Cooking Spray", canonical="Pantry > Oil > Cooking Spray", htc_code="B000600C"),
            ),
            {
                "forbidden_term:cooking",
                "primary_identity_conflict:Cooking Spray",
            },
        )

        powder_profile = IngredientProfile(item="baking powder", recipe_count=10, htc_code="E800500*", sr28_desc="Leavening agents, baking powder")
        powder_contract = learn_contract(powder_profile, generate_candidates(powder_profile, index), index)
        self.assertIn("powder", powder_contract.required_terms)
        self.assertIn(
            contract_reject_reason(
                powder_contract,
                product("Honey Cornbread Mix", pid="Baking Mix", canonical="Pantry > Baking Mixes > Cornbread Mix", htc_code="8000000A"),
            ),
            {
                "missing_required:baking",
                "missing_required:powder",
                "primary_identity_conflict:Baking Mix",
                "path_conflict",
            },
        )

        egg_profile = IngredientProfile(item="egg", recipe_count=10, htc_code="5000000A", sr28_desc="Egg, whole, raw")
        egg_contract = learn_contract(egg_profile, generate_candidates(egg_profile, index), index)
        self.assertNotIn("white", egg_contract.forbidden_terms)
        self.assertEqual(
            "",
            contract_reject_reason(
                egg_contract,
                product("Large White Eggs", pid="Eggs", canonical="Dairy > Eggs", htc_code="5000000A"),
            ),
        )

        soda_index = concept_index([
            concept(
                "Baking Soda",
                "Pantry > Baking Additives & Extracts > Baking Soda",
                title="Pure Baking Soda",
                htc=("E5",),
                refs="Leavening agents baking soda",
            ),
        ])
        soda_profile = IngredientProfile(item="baking soda", recipe_count=10, htc_code="D0006000", sr28_desc="Leavening agents, baking soda")
        soda_contract = learn_contract(soda_profile, generate_candidates(soda_profile, soda_index), soda_index)
        self.assertEqual(
            "",
            contract_reject_reason(
                soda_contract,
                product(
                    "Kroger Pure Baking Soda",
                    pid="Baking Soda",
                    canonical="Pantry > Baking Additives & Extracts > Baking Soda",
                    htc_code="D0006000",
                ),
            ),
        )

    def test_tree_composite_identity_beats_component_identity_override(self) -> None:
        self.assertEqual(
            ("Salad Kit", "Produce > Salad Kits", "Sunflower Bacon Crunch Sweet Onion"),
            _choose_product_tree_fields(
                title="Private Selection Sweet Onion and Gruyere Chopped Salad Kit",
                existing_pid="Salad Kit",
                existing_canonical="Produce > Salad Kits",
                existing_modifier="Sunflower Bacon Crunch Sweet Onion",
                existing_bridge_status="title_match",
                proposed_pid="Onions",
                proposed_canonical="Produce > Vegetables > Onions",
                proposed_modifier="",
            ),
        )

    def test_tree_keeps_buttermilk_identity_over_plain_milk_substring(self) -> None:
        self.assertEqual(
            ("Buttermilk", "Dairy > Buttermilk", "Cultured Whole Milk"),
            _choose_product_tree_fields(
                title="Kroger Cultured Whole Milk Buttermilk Half Gallon",
                existing_pid="Buttermilk",
                existing_canonical="Dairy > Buttermilk",
                existing_modifier="Cultured Whole Milk",
                existing_bridge_status="title_match",
                proposed_pid="Milk",
                proposed_canonical="Dairy > Milk",
                proposed_modifier="",
            ),
        )

    def test_product_tree_overrides_fresh_herb_retail_category_noise(self) -> None:
        self.assertEqual(
            ("Mint", "Produce > Fresh Herbs > Mint", ""),
            _fresh_herb_product_tree_fields(
                title="Simple Truth Organic Mint",
                category_path="Natural & Organic Produce",
                category_path_walmart="",
            ),
        )
        self.assertIsNone(
            _fresh_herb_product_tree_fields(
                title="Private Selection Pure Peppermint Extract",
                category_path="Baking Goods",
                category_path_walmart="",
            )
        )

    def test_plain_yogurt_rejects_flavored_yogurt_drink(self) -> None:
        index = concept_index([
            concept("Yogurt", "Dairy > Yogurt", title="Plain Yogurt", htc=("11",), refs="Yogurt plain"),
        ])
        profile = IngredientProfile(item="plain yogurt", recipe_count=10, htc_code="1100000A", sr28_desc="Yogurt, plain")
        contract = learn_contract(profile, generate_candidates(profile, index), index)

        self.assertEqual(
            "form_conflict:drink",
            contract_reject_reason(
                contract,
                product(
                    "Chobani Low-Fat Greek Yogurt Drink Strawberry Banana",
                    pid="Yogurt",
                    canonical="Dairy > Yogurt",
                    htc_code="1100000A",
                    modifier="Greek Strawberry Banana",
                ),
            ),
        )

    def test_vanilla_contract_accepts_vanilla_extract_identity(self) -> None:
        index = concept_index([
            concept(
                "Extract",
                "Pantry > Baking Extracts",
                modifier="Vanilla",
                title="Vanilla Extract",
                htc=("E5",),
                refs="Vanilla extract",
            ),
        ])
        profile = IngredientProfile(item="vanilla", recipe_count=10, htc_code="E500000A", sr28_desc="Vanilla extract")
        contract = learn_contract(profile, generate_candidates(profile, index), index)

        self.assertEqual("ready", contract.status, contract)
        self.assertEqual(
            "",
            contract_reject_reason(
                contract,
                product(
                    "Kroger Clear Imitation Vanilla Extract",
                    pid="Vanilla Extract",
                    canonical="Pantry > Baking Extracts > Vanilla Extract",
                    htc_code="E500000A",
                    modifier="Clear",
                ),
            ),
        )

    def test_plain_bananas_prefer_fresh_plu_over_frozen_sliced(self) -> None:
        index = concept_index([
            concept("Bananas", "Produce > Fruit > Bananas", title="Fresh Bananas", htc=("60",), refs="Bananas raw"),
        ])
        profile = IngredientProfile(item="bananas", recipe_count=10, htc_code="6000000A", sr28_desc="Bananas, raw")
        contract = learn_contract(profile, generate_candidates(profile, index), index)
        products = product_index([
            product(
                "Great Value Sliced Bananas, 16 oz Bag",
                pid="Bananas",
                canonical="Frozen > Frozen Fruit > Bananas",
                htc_code="6000000A",
                modifier="Sliced",
                evidence_score=95.0,
            ),
            product(
                "Fresh Bunch of Bananas - 5-7 Bananas",
                pid="Bananas",
                canonical="Produce > Fruit > Bananas",
                htc_code="6000000A",
                upc="0000000004011",
                evidence_score=45.0,
            ),
        ])

        match = pick_product_for_contract(contract, products)

        self.assertEqual("accepted_offer", match.status, match)
        self.assertIsNotNone(match.product)
        self.assertEqual("Fresh Bunch of Bananas - 5-7 Bananas", match.product.name)

    def test_plain_banana_does_not_fall_back_to_frozen_sliced(self) -> None:
        index = concept_index([
            concept("Bananas", "Produce > Fruit > Bananas", title="Fresh Bananas", htc=("60",), refs="Bananas raw"),
        ])
        profile = IngredientProfile(item="bananas", recipe_count=10, htc_code="7100000Q", sr28_desc="Bananas, raw")
        contract = learn_contract(profile, generate_candidates(profile, index), index)
        products = product_index([
            product(
                "Great Value Sliced Bananas, 16 oz Bag",
                pid="Bananas",
                canonical="Frozen > Frozen Fruit > Bananas",
                htc_code="6000000A",
                modifier="Sliced",
                evidence_score=95.0,
            ),
        ])

        match = pick_product_for_contract(contract, products)

        self.assertEqual("needs_product_api_query", match.status, match)

    def test_fresh_herb_does_not_accept_dressing_context(self) -> None:
        index = concept_index([
            concept("Cilantro", "Produce > Fresh Herbs > Cilantro", title="Cilantro", htc=("E3",), refs="Cilantro fresh"),
        ])
        profile = IngredientProfile(item="cilantro", recipe_count=10, htc_code="E300000X", sr28_desc="Coriander leaves, raw")
        contract = learn_contract(profile, generate_candidates(profile, index), index)
        products = product_index([
            product(
                "Bolthouse Farms Dressing, Cilantro Avocado Creamy Yogurt Dressing",
                pid="Cilantro",
                canonical="Produce > Fresh Herbs > Cilantro",
                htc_code="E300000X",
                category="Home Page/Food/Fresh Produce/Packaged Salads, Dressings & Dips/Fresh Dressings",
                evidence_score=120.0,
            ),
        ])

        match = pick_product_for_contract(contract, products)

        self.assertEqual("needs_product_api_query", match.status, match)

    def test_plain_onions_reject_pantry_chopped_onion_bottle(self) -> None:
        index = concept_index([
            concept("Onions", "Produce > Vegetables > Onions", title="Sweet Onions", htc=("65",), refs="Onions raw"),
        ])
        profile = IngredientProfile(item="onions", recipe_count=10, htc_code="6500000J", sr28_desc="Onions, raw")
        contract = learn_contract(profile, generate_candidates(profile, index), index)
        products = product_index([
            product(
                "Lawry's Casero Kosher Chopped Onion, 5.6 oz Bottle",
                pid="Onions",
                canonical="Produce > Vegetables > Onions",
                htc_code="6500000J",
                category="Home Page/Food/Pantry/Pantry meal essentials",
                evidence_score=120.0,
            ),
            product(
                "Sweet Onion 3 lb Bag",
                pid="Onions",
                canonical="Produce > Vegetables > Onions",
                htc_code="6500000J",
                category="Produce",
                evidence_score=60.0,
            ),
        ])

        match = pick_product_for_contract(contract, products)

        self.assertEqual("accepted_offer", match.status, match)
        self.assertIsNotNone(match.product)
        self.assertEqual("Sweet Onion 3 lb Bag", match.product.name)

    def test_plain_raisins_reject_salted_cocoa_variant(self) -> None:
        index = concept_index([
            concept("Raisins", "Snack > Dried Fruit > Raisins", title="California Raisins", htc=("74",), refs="Raisins"),
        ])
        profile = IngredientProfile(item="raisins", recipe_count=10, htc_code="7400400=", sr28_desc="Raisins")
        contract = learn_contract(profile, generate_candidates(profile, index), index)
        products = product_index([
            product(
                "Kellogg's Raisin Bran Blueberry",
                pid="Raisins",
                canonical="Snack > Dried Fruit > Raisins",
                htc_code="7400400=",
                evidence_score=130.0,
            ),
            product(
                "Sun-Maid Farmstand Reserve Sea Salt Cocoa Carmel Raisins",
                pid="Raisins",
                canonical="Snack > Dried Fruit > Raisins",
                htc_code="7400400=",
                evidence_score=120.0,
            ),
            product(
                "Sun-Maid California Golden Raisins",
                pid="Raisins",
                canonical="Snack > Dried Fruit > Raisins",
                htc_code="7400400=",
                modifier="Golden",
                evidence_score=60.0,
            ),
        ])

        match = pick_product_for_contract(contract, products)

        self.assertEqual("accepted_offer", match.status, match)
        self.assertIsNotNone(match.product)
        self.assertEqual("Sun-Maid California Golden Raisins", match.product.name)

    def test_plain_cashews_reject_pineapple_habanero_variant(self) -> None:
        index = concept_index([
            concept("Cashews", "Snack > Nuts > Cashews", title="Raw Cashews", htc=("A0",), refs="Cashews"),
        ])
        profile = IngredientProfile(item="cashews", recipe_count=10, htc_code="A000030N", sr28_desc="Nuts, cashew nuts, raw")
        contract = learn_contract(profile, generate_candidates(profile, index), index)
        products = product_index([
            product(
                "Private Selection Kettle Roasted Pineapple Habanero Cashews",
                pid="Cashews",
                canonical="Snack > Nuts > Cashews",
                htc_code="A000030N",
                evidence_score=120.0,
            ),
            product(
                "Great Value Organic Raw Whole Cashews",
                pid="Cashews",
                canonical="Snack > Nuts > Cashews",
                htc_code="A000030N",
                evidence_score=60.0,
            ),
        ])

        match = pick_product_for_contract(contract, products)

        self.assertEqual("accepted_offer", match.status, match)
        self.assertIsNotNone(match.product)
        self.assertEqual("Great Value Organic Raw Whole Cashews", match.product.name)

    def test_vegetable_oil_rejects_avocado_olive_oil_blend(self) -> None:
        index = concept_index([
            concept("Vegetable Oil", "Pantry > Oil > Vegetable Oil", title="Vegetable Oil", htc=("B0",), refs="Soybean oil"),
        ])
        profile = IngredientProfile(item="vegetable oil", recipe_count=10, htc_code="B000600C", sr28_desc="Oil, soybean")
        contract = learn_contract(profile, generate_candidates(profile, index), index)
        products = product_index([
            product(
                "Tantillo Avocado Extra Virgin Olive Oil Squeeze Bottle",
                pid="Oil",
                canonical="Pantry > Oil",
                htc_code="B000600C",
                modifier="Avocado Olive",
                evidence_score=120.0,
            ),
            product(
                "Crisco Pure Vegetable Oil, Cooking Oil, 40 fl oz",
                pid="Vegetable Oil",
                canonical="Pantry > Oil > Vegetable Oil",
                htc_code="B000600C",
                modifier="Soybean",
                evidence_score=60.0,
            ),
        ])

        match = pick_product_for_contract(contract, products)

        self.assertEqual("accepted_offer", match.status, match)
        self.assertIsNotNone(match.product)
        self.assertEqual("Crisco Pure Vegetable Oil, Cooking Oil, 40 fl oz", match.product.name)

    def test_absent_allergen_list_rejects_no_milk_product(self) -> None:
        index = concept_index([
            concept("Milk", "Dairy > Milk", title="Reduced Fat Milk", htc=("10",), refs="Milk fluid"),
        ])
        profile = IngredientProfile(item="milk", recipe_count=10, htc_code="1000600D", sr28_desc="Milk, reduced fat")
        contract = learn_contract(profile, generate_candidates(profile, index), index)

        self.assertEqual(
            "absent_claim:milk",
            contract_reject_reason(
                contract,
                product(
                    "Penne Rigate Pasta - No Egg, Milk, or Soy - Contains Wheat",
                    pid="Milk",
                    canonical="Dairy > Milk",
                    htc_code="1000600D",
                ),
            ),
        )

    def test_green_chile_spelling_matches_green_chili_peppers(self) -> None:
        index = concept_index([
            concept("Chili", "Pantry > Chili", title="Green Chili Peppers", htc=("90",), refs="Peppers hot green chili"),
        ])
        profile = IngredientProfile(item="green chili peppers", recipe_count=10, htc_code="9000000S", sr28_desc="Peppers, hot chili, green")
        contract = learn_contract(profile, generate_candidates(profile, index), index)

        self.assertEqual(
            "",
            contract_reject_reason(
                contract,
                product(
                    "Kroger Diced Green Chile Peppers",
                    pid="Chile Peppers",
                    canonical="Pantry > Spices & Seasonings > Chile Peppers",
                    htc_code="9000000S",
                ),
            ),
        )
        self.assertEqual(
            "",
            contract_reject_reason(
                contract,
                product(
                    "Great Value Canned Medium Diced Green Chiles",
                    pid="Green Chiles",
                    canonical="Pantry > Canned Vegetables > Green Chiles",
                    htc_code="9000000S",
                ),
            ),
        )

    def test_ghee_does_not_forbid_its_clarified_butter_reference(self) -> None:
        index = concept_index([
            concept("Ghee", "Pantry > Oil > Ghee", title="Ghee", htc=("B0",), refs="Ghee clarified butter"),
            concept("Butter", "Dairy > Butter", title="Butter", htc=("10",), refs="Butter"),
        ])
        profile = IngredientProfile(item="ghee", recipe_count=10, htc_code="B000000A", sr28_desc="Ghee, clarified butter")
        contract = learn_contract(profile, generate_candidates(profile, index), index)

        self.assertNotIn("butter", contract.forbidden_terms)
        self.assertEqual(
            "",
            contract_reject_reason(
                contract,
                product(
                    "Beneficial Blends Ghee Clarified Butter",
                    pid="Ghee",
                    canonical="Dairy > Butter > Ghee",
                    htc_code="B000000A",
                ),
            ),
        )


if __name__ == "__main__":
    unittest.main()
