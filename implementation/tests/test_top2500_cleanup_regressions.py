import sys
import tempfile
import unittest
from pathlib import Path


IMPLEMENTATION_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = IMPLEMENTATION_ROOT.parent
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))
PRICE_SCRIPTS = REPO_ROOT / "recipe_pricing" / "scripts"
if str(PRICE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PRICE_SCRIPTS))

from build_top2500_cleanup_checklist import build_checklist, write_csv  # noqa: E402
from build_canonical_surface_esha_cleanup_queue import classify as classify_cleanup_row  # noqa: E402
from build_top2500_cleanup_queue import build_queue  # noqa: E402
from build_top_ingredient_coverage_audit import issue_for  # noqa: E402
from esha_contracts import ProductFacts, evaluate_facts  # noqa: E402
from esha_cart_price_probe import surface_candidates  # noqa: E402
from surface_lab_calculator import calculate_lab  # noqa: E402


class SurfaceLabTop2500RegressionTests(unittest.TestCase):
    def test_granulated_sugar_stays_granulated_not_beet(self) -> None:
        lab = calculate_lab(display="granulated sugar", item="granulated sugar", grams=100)
        self.assertEqual(lab.esha_code, "25006")
        self.assertEqual(lab.esha_description, "Sugar, white, granulated")

    def test_beet_sugar_stays_beet_specific(self) -> None:
        lab = calculate_lab(display="beet sugar", item="beet sugar", grams=100)
        self.assertEqual(lab.esha_code, "39201")
        self.assertEqual(lab.esha_description, "Sugar, beet, fruit")

    def test_mustard_seed_routes_to_spice_cards(self) -> None:
        ground = calculate_lab(display="Spices, mustard seed, ground", item="Spices, mustard seed, ground", grams=100)
        yellow = calculate_lab(
            display="Spices, mustard seed, yellow, ground",
            item="Spices, mustard seed, yellow, ground",
            grams=100,
        )
        self.assertEqual(ground.esha_code, "26514")
        self.assertEqual(ground.esha_description, "Spice, mustard seed, ground")
        self.assertEqual(yellow.esha_code, "26110")
        self.assertEqual(yellow.esha_description, "Spice, mustard seed, yellow, ground")

    def test_common_head_aliases_resolve_to_safe_base_cards(self) -> None:
        flour = calculate_lab(
            display="Wheat flour, white, all-purpose, enriched, bleached",
            item="Wheat flour, white, all-purpose, enriched, bleached",
            grams=100,
        )
        pepper = calculate_lab(display="Spices, pepper, black", item="Spices, pepper, black", grams=100)
        yeast = calculate_lab(
            display="Leavening agents, yeast, baker's, active dry",
            item="Leavening agents, yeast, baker's, active dry",
            grams=100,
        )
        pancake_mix = calculate_lab(
            display="Baking mixes, pancakes, dry mix, complete",
            item="Baking mixes, pancakes, dry mix, complete",
            grams=100,
        )
        self.assertEqual(flour.canonical_name, "all purpose flour")
        self.assertEqual(flour.esha_code, "45984")
        self.assertEqual(pepper.canonical_name, "black pepper")
        self.assertEqual(pepper.esha_code, "90212")
        self.assertEqual(yeast.canonical_name, "active dry yeast")
        self.assertEqual(yeast.esha_code, "28000")
        self.assertEqual(pancake_mix.canonical_name, "pancake mix")
        self.assertEqual(pancake_mix.esha_code, "16700")

    def test_known_wrong_esha_assignments_are_cleared(self) -> None:
        whipped = calculate_lab(display="whipped dessert topping", item="whipped dessert topping", grams=100)
        menthe = calculate_lab(display="creme de menthe", item="creme de menthe", grams=100)
        cacao = calculate_lab(display="creme de cacao", item="creme de cacao", grams=100)
        pasta = calculate_lab(display="pasta", item="pasta", grams=100)
        self.assertEqual(whipped.esha_code, "")
        self.assertTrue(any("surface_esha_clear" in step for step in whipped.path))
        self.assertEqual(menthe.esha_code, "")
        self.assertTrue(any("surface_esha_clear" in step for step in menthe.path))
        self.assertEqual(cacao.esha_code, "")
        self.assertTrue(any("surface_esha_clear" in step for step in cacao.path))
        self.assertEqual(pasta.esha_code, "")
        self.assertTrue(any("surface_esha_clear" in step for step in pasta.path))

    def test_first_p1_cleanup_batch_behaves_honestly(self) -> None:
        macaroni = calculate_lab(display="macaroni", item="macaroni", grams=100)
        cinnamon_sugar = calculate_lab(display="cinnamon sugar", item="cinnamon sugar", grams=100)
        thickened_cream = calculate_lab(display="thickened cream", item="thickened cream", grams=100)
        stock = calculate_lab(display="stock", item="stock", grams=100)

        self.assertEqual(macaroni.esha_code, "38061")
        self.assertEqual(macaroni.esha_description, "Pasta, macaroni, enriched, dry")
        self.assertEqual(macaroni.nutrition_source, "esha_tier_a_label_median")

        self.assertEqual(cinnamon_sugar.esha_code, "")
        self.assertEqual(cinnamon_sugar.canonical_name, "cinnamon sugar")
        self.assertEqual(cinnamon_sugar.shopping_state, "shopping_candidates_strong")

        self.assertEqual(thickened_cream.shopping_canonical, "heavy cream")
        self.assertEqual(thickened_cream.esha_code, "502")
        self.assertEqual(thickened_cream.shopping_state, "shopping_candidates_strong")

        self.assertEqual(stock.esha_code, "")
        self.assertEqual(stock.nutrition_state, "nutrition_unknown")
        self.assertEqual(stock.shopping_state, "shopping_gap")

    def test_balsamic_vinaigrette_uses_real_esha_dressing_card(self) -> None:
        lab = calculate_lab(display="balsamic vinaigrette", item="balsamic vinaigrette", grams=100)

        self.assertEqual(lab.canonical_name, "balsamic vinaigrette")
        self.assertEqual(lab.esha_code, "18324")
        self.assertEqual(lab.esha_description, "Salad Dressing, vinaigrette, balsamic")
        self.assertEqual(lab.nutrition_source, "esha_tier_a_label_median")
        self.assertEqual(lab.shopping_state, "shopping_candidates_strong")

    def test_second_p1_cleanup_batch_routes_real_cards(self) -> None:
        red_lentils = calculate_lab(display="red lentils", item="red lentils", grams=100)
        ramen = calculate_lab(display="ramen noodles", item="ramen noodles", grams=100)
        chicken_ramen = calculate_lab(
            display="chicken-flavored ramen noodles",
            item="chicken-flavored ramen noodles",
            grams=100,
        )
        andouille = calculate_lab(display="andouille sausage", item="andouille sausage", grams=100)
        spiced_rum = calculate_lab(display="spiced rum", item="spiced rum", grams=100)

        self.assertEqual(red_lentils.esha_code, "7378")
        self.assertEqual(red_lentils.esha_description, "Beans, lentils, red, dried")

        self.assertEqual(ramen.esha_code, "92163")
        self.assertEqual(ramen.esha_description, "Soup, ramen noodle, any flavor, dry")

        self.assertEqual(chicken_ramen.canonical_name, "chicken flavored ramen noodles")
        self.assertEqual(chicken_ramen.esha_code, "28169")
        self.assertEqual(chicken_ramen.esha_description, "Soup, ramen noodle, chicken flavor, dry")

        self.assertEqual(andouille.esha_code, "58511")
        self.assertEqual(andouille.esha_description, "Sausage, pork, Cajun andouille")

        self.assertEqual(spiced_rum.esha_code, "22593")
        self.assertEqual(spiced_rum.esha_description, "Alcohol, rum, 80 proof")
        self.assertEqual(spiced_rum.shopping_state, "shopping_gap")

    def test_exact_label_head_items_pick_up_real_esha_cards(self) -> None:
        half = calculate_lab(display="half-and-half", item="half-and-half", grams=100)
        gingerroot = calculate_lab(display="gingerroot", item="gingerroot", grams=100)
        buns = calculate_lab(display="hamburger buns", item="hamburger buns", grams=100)
        pepperoni = calculate_lab(display="pepperoni", item="pepperoni", grams=100)
        tamari = calculate_lab(display="tamari", item="tamari", grams=100)

        self.assertEqual(half.canonical_name, "half and half")
        self.assertEqual(half.esha_code, "500")
        self.assertEqual(half.shopping_state, "shopping_candidates_strong")

        self.assertEqual(gingerroot.shopping_canonical, "ginger root")
        self.assertEqual(gingerroot.esha_code, "90442")

        self.assertEqual(buns.esha_code, "42508")
        self.assertEqual(buns.esha_description, "Roll, hamburger")

        self.assertEqual(pepperoni.esha_code, "13021")
        self.assertEqual(pepperoni.shopping_state, "shopping_candidates_strong")

        self.assertEqual(tamari.esha_code, "26705")
        self.assertEqual(tamari.shopping_state, "shopping_candidates_strong")

    def test_exact_label_alcohol_and_spice_batch_pick_up_real_esha_cards(self) -> None:
        fresh_ginger = calculate_lab(display="fresh gingerroot", item="fresh gingerroot", grams=100)
        mirin = calculate_lab(display="mirin", item="mirin", grams=100)
        sake = calculate_lab(display="sake", item="sake", grams=100)
        provence = calculate_lab(display="herbes de provence", item="herbes de provence", grams=100)

        self.assertEqual(fresh_ginger.shopping_canonical, "ginger root")
        self.assertEqual(fresh_ginger.esha_code, "90442")

        self.assertEqual(mirin.esha_code, "22591")
        self.assertEqual(mirin.esha_description, "Wine, mirin, INTL")

        self.assertEqual(sake.esha_code, "22676")
        self.assertEqual(sake.nutrition_source, "sr28_direct")

        self.assertEqual(provence.esha_code, "36409")
        self.assertEqual(provence.esha_description, "Herb Blend, herbes de Provence")

    def test_reviewed_no_exact_esha_target_apples_stay_explicit(self) -> None:
        baking = calculate_lab(display="baking apples", item="baking apples", grams=100)
        red_delicious = calculate_lab(display="red delicious apples", item="red delicious apples", grams=100)

        self.assertEqual(baking.esha_code, "")
        self.assertEqual(baking.canonical_name, "granny smith apple")
        self.assertIn(baking.shopping_state, {"shopping_candidates_strong", "shopping_candidates_weak"})

        self.assertEqual(red_delicious.esha_code, "")
        self.assertEqual(red_delicious.canonical_name, "red delicious apple")
        self.assertIn(red_delicious.shopping_state, {"shopping_candidates_strong", "shopping_candidates_weak"})

    def test_generic_sugar_and_flour_use_reviewed_head_contracts(self) -> None:
        sugar = calculate_lab(display="sugar", item="sugar", grams=100)
        flour = calculate_lab(display="flour", item="flour", grams=100)

        self.assertEqual(sugar.canonical_name, "granulated sugar")
        self.assertEqual(sugar.esha_code, "25006")
        self.assertEqual(sugar.shopping_state, "shopping_candidates_strong")

        self.assertEqual(flour.canonical_name, "all purpose flour")
        self.assertEqual(flour.esha_code, "45984")
        self.assertEqual(flour.shopping_state, "shopping_candidates_strong")

    def test_reviewed_head_pack_contracts_filter_common_pantry_items(self) -> None:
        water = calculate_lab(display="water", item="water", grams=100)
        milk = calculate_lab(display="milk", item="milk", grams=100)
        salt = calculate_lab(display="salt", item="salt", grams=100)
        butter = calculate_lab(display="butter", item="butter", grams=100)
        soy_sauce = calculate_lab(display="soy sauce", item="soy sauce", grams=100)
        baking_powder = calculate_lab(display="baking powder", item="baking powder", grams=100)
        baking_soda = calculate_lab(display="baking soda", item="baking soda", grams=100)
        lemon_juice = calculate_lab(display="lemon juice", item="lemon juice", grams=100)

        self.assertIn(water.shopping_state, {"shopping_candidates_strong", "shopping_candidates_weak"})
        self.assertTrue(water.products)
        self.assertTrue(all("sparkling" not in product.description.lower() for product in water.products[:5]))

        self.assertIn(milk.shopping_state, {"shopping_candidates_strong", "shopping_candidates_weak"})
        self.assertTrue(all("almond" not in product.description.lower() for product in milk.products[:5]))
        self.assertTrue(all("chocolate" not in product.description.lower() for product in milk.products[:5]))

        self.assertIn(salt.shopping_state, {"shopping_candidates_strong", "shopping_candidates_weak"})
        self.assertTrue(all("seasoned" not in product.description.lower() for product in salt.products[:5]))
        self.assertTrue(all("substitute" not in product.description.lower() for product in salt.products[:5]))
        self.assertTrue(all("canning" not in product.description.lower() for product in salt.products[:10]))
        self.assertTrue(all("pickling" not in product.description.lower() for product in salt.products[:10]))

        self.assertIn(butter.shopping_state, {"shopping_candidates_strong", "shopping_candidates_weak"})
        self.assertTrue(all("peanut" not in product.description.lower() for product in butter.products[:5]))
        self.assertTrue(all("almond" not in product.description.lower() for product in butter.products[:5]))

        self.assertIn(soy_sauce.shopping_state, {"shopping_candidates_strong", "shopping_candidates_weak"})
        self.assertTrue(all("soy" in product.description.lower() for product in soy_sauce.products[:5]))
        self.assertTrue(all("sauce" in product.description.lower() for product in soy_sauce.products[:5]))
        self.assertTrue(all("paste" not in product.description.lower() for product in soy_sauce.products[:5]))
        self.assertTrue(all("tamari" not in product.description.lower() for product in soy_sauce.products[:5]))

        self.assertIn(baking_powder.shopping_state, {"shopping_candidates_strong", "shopping_candidates_weak"})
        self.assertTrue(all("baking powder" in product.description.lower() for product in baking_powder.products[:5]))

        self.assertIn(baking_soda.shopping_state, {"shopping_candidates_strong", "shopping_candidates_weak"})
        self.assertTrue(all("baking soda" in product.description.lower() for product in baking_soda.products[:5]))

        self.assertIn(lemon_juice.shopping_state, {"shopping_candidates_strong", "shopping_candidates_weak"})
        self.assertTrue(all("lemon juice" in product.description.lower() for product in lemon_juice.products[:5]))

    def test_canning_and_pickling_salt_use_salt_nutrition_but_not_plain_salt_esha(self) -> None:
        for text in ("canning salt", "pickling salt", "canning and pickling salt"):
            lab = calculate_lab(display=text, item=text, grams=100)
            self.assertEqual(lab.esha_code, "")
            self.assertEqual(lab.sr28_fdc_id, "173468")
            self.assertEqual(lab.fndds_code, "")
            self.assertEqual(lab.nutrition_source, "sr28_direct")
            self.assertTrue(lab.products)
            self.assertTrue(any("canning" in product.description.lower() or "pickling" in product.description.lower() for product in lab.products[:3]))

    def test_milk_subtypes_keep_their_fat_level_cards(self) -> None:
        expected = {
            "milk": "1",
            "whole milk": "1",
            "skim milk": "6",
            "nonfat milk": "6",
            "low-fat milk": "4",
            "reduced-fat milk": "2",
        }
        for surface, code in expected.items():
            with self.subTest(surface=surface):
                lab = calculate_lab(display=surface, item=surface, grams=100)
                self.assertEqual(lab.esha_code, code)
                self.assertTrue(all("chocolate" not in product.description.lower() for product in lab.products[:5]))
                self.assertTrue(all("almond" not in product.description.lower() for product in lab.products[:5]))

    def test_named_oils_do_not_route_to_generic_vegetable_oil(self) -> None:
        expected = {
            "oil": "90965",
            "vegetable oil": "90965",
            "peanut oil": "44896",
            "sesame oil": "8771",
            "toasted sesame oil": "49279",
        }
        for surface, code in expected.items():
            with self.subTest(surface=surface):
                lab = calculate_lab(display=surface, item=surface, grams=100)
                self.assertEqual(lab.esha_code, code)
                self.assertTrue(all("beancurd" not in product.description.lower() for product in lab.products[:5]))
                self.assertTrue(all("butter" not in product.description.lower() for product in lab.products[:5]))

    def test_cocoa_powder_is_not_hot_cocoa_mix(self) -> None:
        expected = {
            "cocoa powder": "23712",
            "unsweetened cocoa powder": "23712",
            "dutch-process cocoa powder": "28210",
        }
        for surface, code in expected.items():
            with self.subTest(surface=surface):
                lab = calculate_lab(display=surface, item=surface, grams=100)
                self.assertEqual(lab.esha_code, code)
                self.assertNotEqual(lab.esha_code, "12")
                self.assertTrue(all("hot cocoa" not in product.description.lower() for product in lab.products[:5]))
                self.assertTrue(all("protein" not in product.description.lower() for product in lab.products[:5]))
                self.assertTrue(all("truffle" not in product.description.lower() for product in lab.products[:5]))

    def test_batch8_surfaces_route_to_reviewed_cards(self) -> None:
        expected = {
            "apple": "3001",
            "apples": "3001",
            "blueberries": "3381",
            "cherry tomatoes": "90530",
            "breadcrumbs": "42439",
            "italian seasoned breadcrumbs": "42358",
            "seasoned breadcrumbs": "42144",
            "peanut butter": "25778",
            "cream of mushroom soup": "50477",
            "pineapple juice": "3990",
            "seasoning salt": "91928",
            "fresh mint": "26630",
            "hot pepper sauce": "53470",
            "cooking spray": "35301",
        }
        for surface, code in expected.items():
            with self.subTest(surface=surface):
                lab = calculate_lab(display=surface, item=surface, grams=100)
                self.assertEqual(lab.esha_code, code)

    def test_batch8_shopping_candidates_reject_known_noise(self) -> None:
        apples = calculate_lab(display="apple", item="apple", grams=100)
        self.assertTrue(all("cider" not in product.description.lower() for product in apples.products[:5]))
        self.assertTrue(all("caramel" not in product.description.lower() for product in apples.products[:5]))

        breadcrumbs = calculate_lab(display="breadcrumbs", item="breadcrumbs", grams=100)
        self.assertTrue(all("shrimp" not in product.description.lower() for product in breadcrumbs.products[:5]))
        self.assertTrue(all("fish" not in product.description.lower() for product in breadcrumbs.products[:5]))

        mint = calculate_lab(display="fresh mint", item="fresh mint", grams=100)
        self.assertEqual(mint.shopping_state, "shopping_gap")
        self.assertTrue(all("gum" in product.reason or "jelly" in product.reason for product in mint.rejected_products[:3]))

        hot_sauce = calculate_lab(display="hot pepper sauce", item="hot pepper sauce", grams=100)
        self.assertTrue(any("hot sauce" in product.description.lower() for product in hot_sauce.products[:3]))

    def test_batch9_surfaces_route_to_reviewed_cards(self) -> None:
        expected = {
            "nuts": "4591",
            "chopped nuts": "4591",
            "bittersweet chocolate": "4356",
            "chili sauce": "434",
            "yellow cake mix": "46089",
            "kalamata olives": "6499",
            "golden raisins": "3934",
            "roma tomatoes": "6492",
            "self-rising flour": "38033",
            "tomato juice": "3996",
            "tomato puree": "5476",
            "sunflower seeds": "4545",
            "yellow cornmeal": "38004",
            "miniature marshmallows": "23008",
            "penne pasta": "92830",
            "crabmeat": "26830",
            "white chocolate": "90659",
            "white chocolate chips": "23447",
        }
        for surface, code in expected.items():
            with self.subTest(surface=surface):
                lab = calculate_lab(display=surface, item=surface, grams=100)
                self.assertEqual(lab.esha_code, code)

    def test_batch9_shopping_candidates_reject_known_noise(self) -> None:
        tomato_juice = calculate_lab(display="tomato juice", item="tomato juice", grams=100)
        self.assertTrue(all("diced" not in product.description.lower() for product in tomato_juice.products[:5]))

        tomato_puree = calculate_lab(display="tomato puree", item="tomato puree", grams=100)
        self.assertTrue(all("diced" not in product.description.lower() for product in tomato_puree.products[:5]))
        self.assertTrue(all("chopped" not in product.description.lower() for product in tomato_puree.products[:5]))

        penne = calculate_lab(display="penne pasta", item="penne pasta", grams=100)
        self.assertTrue(all("alfredo" not in product.description.lower() for product in penne.products[:5]))
        self.assertTrue(all("gluten free" not in product.description.lower() for product in penne.products[:5]))

        white_chocolate_chips = calculate_lab(display="white chocolate chips", item="white chocolate chips", grams=100)
        self.assertTrue(all("pudding" not in product.description.lower() for product in white_chocolate_chips.products[:5]))

        flour = evaluate_facts(
            "38033",
            ProductFacts.from_components("SELF-RISING FLOUR", "Flours & Corn Meal", "Wheat flour, salt, baking soda"),
        )
        self.assertIsNotNone(flour)
        self.assertEqual(flour.status, "accept")

        cornmeal = evaluate_facts(
            "38033",
            ProductFacts.from_components("SELF-RISING CORNMEAL", "Flours & Corn Meal", "Corn meal, flour, leavening"),
        )
        self.assertIsNotNone(cornmeal)
        self.assertEqual(cornmeal.status, "reject")

        mix = evaluate_facts(
            "38033",
            ProductFacts.from_components(
                "Pillsbury Hotel & Restaurant Self Rising All Purpose Flour",
                "Grains/Flour",
                "Wheat flour, sugar, corn meal, soybean oil, eggs, nonfat milk, whey",
            ),
        )
        self.assertIsNotNone(mix)
        self.assertEqual(mix.status, "reject")

    def test_crawfish_tail_card_accepts_tailmeat_and_rejects_whole_or_prepared(self) -> None:
        tailmeat = evaluate_facts(
            "24190",
            ProductFacts.from_components(
                "CRAWFISH TAIL MEAT",
                "Frozen Fish & Seafood",
                "Crawfish Tail Meat",
            ),
        )
        self.assertIsNotNone(tailmeat)
        self.assertEqual(tailmeat.status, "accept")

        whole = evaluate_facts(
            "24190",
            ProductFacts.from_components(
                '16/22 WHL BOILED CRAWFISH',
                "Fish Unprepared/Unprocessed",
                "Crawfish Tail Meat, Salt, Chinese Red Pepper",
            ),
        )
        self.assertIsNotNone(whole)
        self.assertEqual(whole.status, "reject")

        dip = evaluate_facts(
            "24190",
            ProductFacts.from_components(
                "CRAWFISH DIP, CRAWFISH",
                "Dips & Salsa",
                "Crawfish Tailmeat, Mayonnaise, Cream Cheese",
            ),
        )
        self.assertIsNotNone(dip)
        self.assertEqual(dip.status, "reject")

    def test_chipotle_mayo_accepts_label_variants_but_rejects_adjacent_dressings(self) -> None:
        accepted = (
            "CHIPOTLE MAYO, CHIPOTLE",
            "MAYO DRESSING WITH CHIPOTLE, CHIPOTLE",
            "CHIPOTLE MAYONNAISE, CHIPOTLE",
            "CHIPOTLE LIME MAYO MAYONNAISE, CHIPOTLE LIME MAYO",
            "CHIPOTLE MAYO SANDWICH SPREAD, CHIPOTLE",
        )
        for description in accepted:
            with self.subTest(description=description):
                decision = evaluate_facts(
                    "22937",
                    ProductFacts.from_components(
                        description,
                        "Salad Dressing & Mayonnaise",
                        "Soybean oil, egg yolks, vinegar, salt, chipotle pepper",
                    ),
                )
                self.assertIsNotNone(decision)
                self.assertEqual(decision.status, "accept")

        rejected = (
            "CHIPOTLE CAESAR DRESSING, CHIPOTLE CAESAR",
            "CHIPOTLE RANCH DRESSING, CHIPOTLE RANCH",
            "CHIPOTLE LIME DRESSING, CHIPOTLE LIME",
        )
        for description in rejected:
            with self.subTest(description=description):
                decision = evaluate_facts(
                    "22937",
                    ProductFacts.from_components(
                        description,
                        "Salad Dressing & Mayonnaise",
                        "Soybean oil, water, vinegar, spices, chipotle pepper",
                    ),
                )
                self.assertIsNotNone(decision)
                self.assertEqual(decision.status, "reject")

    def test_batch10_surfaces_route_to_reviewed_cards(self) -> None:
        expected = {
            "peanuts": "4696",
            "pumpkin": "6298",
            "cayenne": "82043",
            "lasagna noodles": "91211",
            "firm tofu": "12888",
            "splenda granular": "31180",
            "ripe bananas": "51329",
            "cornflour": "30000",
            "bourbon": "22671",
            "sauerkraut": "36986",
            "soymilk": "20033",
            "cranberry juice": "4986",
            "hazelnuts": "4513",
            "cream of celery soup": "50473",
            "cashews": "63195",
            "salad oil": "90965",
            "ranch dressing": "8555",
            "cherry pie filling": "48015",
            "tahini": "4686",
            "miracle whip": "8479",
            "kahlua": "22519",
            "sunflower oil": "8233",
            "quick oats": "92017",
        }
        for surface, code in expected.items():
            with self.subTest(surface=surface):
                lab = calculate_lab(display=surface, item=surface, grams=100)
                self.assertEqual(lab.esha_code, code)
        red = calculate_lab(display="red food coloring", item="red food coloring", grams=100)
        puff = calculate_lab(display="puff pastry", item="puff pastry", grams=100)
        self.assertEqual(red.esha_code, "")
        self.assertEqual(red.nutrition_state, "nutrition_unknown")
        self.assertEqual(puff.esha_code, "")
        self.assertEqual(puff.nutrition_source, "sr28_direct")

    def test_batch10_shopping_candidates_reject_known_noise(self) -> None:
        cayenne = calculate_lab(display="cayenne", item="cayenne", grams=100)
        self.assertTrue(all("lemonade" not in product.description.lower() for product in cayenne.products[:5]))
        self.assertTrue(all("hummus" not in product.description.lower() for product in cayenne.products[:5]))

        bourbon = calculate_lab(display="bourbon", item="bourbon", grams=100)
        self.assertTrue(all("cookie" not in product.description.lower() for product in bourbon.products[:5]))

        hazelnut = calculate_lab(display="hazelnuts", item="hazelnuts", grams=100)
        self.assertTrue(all("coffee" not in product.description.lower() for product in hazelnut.products[:5]))
        self.assertTrue(all("chocolate" not in product.description.lower() for product in hazelnut.products[:5]))

        tahini = calculate_lab(display="tahini", item="tahini", grams=100)
        self.assertTrue(all("hummus" not in product.description.lower() for product in tahini.products[:5]))
        self.assertTrue(all("dressing" not in product.description.lower() for product in tahini.products[:5]))

        sunflower_oil = calculate_lab(display="sunflower oil", item="sunflower oil", grams=100)
        self.assertTrue(all("tuna" not in product.description.lower() for product in sunflower_oil.products[:5]))
        self.assertTrue(all("olive" not in product.description.lower() for product in sunflower_oil.products[:5]))

    def test_batch11_surfaces_route_to_reviewed_cards(self) -> None:
        expected = {
            "orzo pasta": "38328",
            "bisquick baking mix": "16533",
            "mini marshmallows": "23008",
            "marshmallows": "23007",
            "ritz crackers": "70963",
            "coconut oil": "8037",
            "pita bread": "42007",
            "frozen whipped topping": "54387",
            "coriander powder": "26571",
            "refrigerated crescent dinner rolls": "16638",
            "cumin powder": "26503",
            "ranch dressing mix": "41429",
            "graham cracker crust": "48475",
            "baguette": "19170",
            "watercress": "5222",
            "mini chocolate chips": "23183",
            "lump crabmeat": "19153",
            "sea scallops": "19029",
            "golden syrup": "90065",
            "tart apples": "3001",
            "white cake mix": "46081",
            "black-eyed peas": "90018",
            "colby-monterey jack cheese": "1282",
            "mixed salad greens": "48561",
            "wonton wrappers": "12879",
            "fettuccine": "91182",
            "ground flax seeds": "29575",
        }
        for surface, code in expected.items():
            with self.subTest(surface=surface):
                lab = calculate_lab(display=surface, item=surface, grams=100)
                self.assertEqual(lab.esha_code, code)

        for surface in ("triple sec", "grand marnier"):
            with self.subTest(surface=surface):
                lab = calculate_lab(display=surface, item=surface, grams=100)
                self.assertEqual(lab.esha_code, "")
                self.assertEqual(lab.fndds_code, "93201000")

        sugar_substitute = calculate_lab(display="sugar substitute", item="sugar substitute", grams=100)
        self.assertEqual(sugar_substitute.esha_code, "")
        self.assertEqual(sugar_substitute.fndds_code, "91200000")

    def test_batch11_shopping_candidates_reject_known_noise(self) -> None:
        sugar_substitute = calculate_lab(display="sugar substitute", item="sugar substitute", grams=100)
        self.assertTrue(all("coffee" not in product.description.lower() for product in sugar_substitute.products[:5]))
        self.assertTrue(all("salt substitute" not in product.description.lower() for product in sugar_substitute.products[:5]))

        tart_apple = calculate_lab(display="tart apples", item="tart apples", grams=100)
        self.assertTrue(all("juice" not in product.description.lower() for product in tart_apple.products[:5]))
        self.assertTrue(all("oatmeal" not in product.description.lower() for product in tart_apple.products[:5]))
        self.assertTrue(all("fudge" not in product.description.lower() for product in tart_apple.products[:5]))

        coconut_oil = calculate_lab(display="coconut oil", item="coconut oil", grams=100)
        self.assertTrue(all("spray" not in product.description.lower() for product in coconut_oil.products[:5]))
        self.assertTrue(all("butter" not in product.description.lower() for product in coconut_oil.products[:5]))

        ranch_mix = calculate_lab(display="ranch dressing mix", item="ranch dressing mix", grams=100)
        self.assertTrue(all("dip" not in product.description.lower() for product in ranch_mix.products[:5]))
        self.assertTrue(all("bottled" not in product.description.lower() for product in ranch_mix.products[:5]))

        scallops = calculate_lab(display="sea scallops", item="sea scallops", grams=100)
        self.assertTrue(all("scalloped potato" not in product.description.lower() for product in scallops.products[:5]))
        self.assertTrue(all("bacon" not in product.description.lower() for product in scallops.products[:5]))

        orange_liqueur = calculate_lab(display="triple sec", item="triple sec", grams=100)
        self.assertEqual(orange_liqueur.shopping_state, "shopping_gap")

    def test_batch12_surfaces_route_to_reviewed_cards(self) -> None:
        expected = {
            "guacamole": "13485",
            "diced tomatoes and green chilies": "42757",
            "sweet chili sauce": "434",
            "sultanas": "3934",
            "turkey breast": "51131",
            "raw turkey breast": "51131",
            "pecorino romano cheese": "1262",
            "coffee": "24339",
            "milk chocolate": "41521",
            "bicarbonate of soda": "28003",
            "bow tie pasta": "91200",
            "pumpkin seeds": "4522",
            "rotini pasta": "91193",
            "pizza dough": "46509",
            "clam juice": "19021",
            "xanthan gum": "38799",
            "kiwi": "3858",
            "watermelon": "27373",
            "salted peanuts": "49270",
            "phyllo dough": "45528",
            "fine dry breadcrumbs": "42004",
            "caramels": "23015",
            "semisweet chocolate morsels": "23442",
            "marsala wine": "35204",
            "gin": "22514",
            "rigatoni pasta": "38589",
            "pecan pieces": "4577",
            "chopped pecans": "4577",
            "instant espresso powder": "20013",
            "devil's food cake mix": "46494",
        }
        for surface, code in expected.items():
            with self.subTest(surface=surface):
                lab = calculate_lab(display=surface, item=surface, grams=100)
                self.assertEqual(lab.esha_code, code)

        for surface, fndds_code in {
            "cointreau liqueur": "93201000",
            "artificial sweetener": "91200000",
        }.items():
            with self.subTest(surface=surface):
                lab = calculate_lab(display=surface, item=surface, grams=100)
                self.assertEqual(lab.esha_code, "")
                self.assertEqual(lab.fndds_code, fndds_code)

    def test_batch12_contracts_reject_known_noise(self) -> None:
        def decision(code: str, description: str, category: str, ingredients: str = "") -> str:
            result = evaluate_facts(code, ProductFacts.from_components(description, category, ingredients))
            self.assertIsNotNone(result)
            return result.status

        self.assertEqual(decision("13485", "GUACAMOLE TORTILLA CHIPS", "Chips, Pretzels & Snacks"), "reject")
        self.assertEqual(decision("42757", "GREEN CHILE TOMATO SALSA", "Dips & Salsa"), "reject")
        self.assertEqual(decision("51131", "SLICED TURKEY BREAST LUNCHMEAT", "Lunchmeat"), "reject")
        self.assertEqual(decision("1262", "ROMANO CHEESE DRESSING", "Salad Dressing & Mayonnaise"), "reject")
        self.assertEqual(decision("24339", "COFFEE CREAMER", "Milk Additives"), "reject")
        self.assertEqual(decision("41521", "CHOCOLATE MILK", "Milk"), "reject")
        self.assertEqual(decision("4522", "PUMPKIN SEED TRAIL MIX", "Popcorn, Peanuts, Seeds & Related Snacks"), "reject")
        self.assertEqual(decision("46509", "PIZZA DOUGH KIT WITH SAUCE", "Crusts & Dough"), "reject")
        self.assertEqual(decision("19021", "CLAM TOMATO JUICE COCKTAIL", "Fruit & Vegetable Juice, Nectars & Fruit Drinks"), "reject")
        self.assertEqual(decision("42004", "SEASONED BREADCRUMB STUFFING", "Baking"), "reject")
        self.assertEqual(decision("23015", "CARAMEL SAUCE", "Syrups & Molasses"), "reject")
        self.assertEqual(decision("23442", "SEMI-SWEET CHOCOLATE CHIP COOKIES", "Cookies & Biscuits"), "reject")
        self.assertEqual(decision("46494", "DEVIL'S FOOD FROSTING", "Frosting & Icing"), "reject")

    def test_batch12_contracts_accept_known_good_retail_rows(self) -> None:
        def decision(code: str, description: str, category: str, ingredients: str = "") -> str:
            result = evaluate_facts(code, ProductFacts.from_components(description, category, ingredients))
            self.assertIsNotNone(result)
            return result.status

        self.assertEqual(decision("13485", "GUACAMOLE", "Dips & Salsa"), "accept")
        self.assertEqual(decision("42757", "DICED TOMATOES WITH GREEN CHILIES", "Canned Vegetables"), "accept")
        self.assertEqual(decision("51131", "TURKEY BREAST", "Turkey"), "accept")
        self.assertEqual(decision("1262", "PECORINO ROMANO CHEESE", "Cheese"), "accept")
        self.assertEqual(decision("24339", "GROUND COFFEE", "Coffee"), "accept")
        self.assertEqual(decision("41521", "MILK CHOCOLATE", "Chocolate"), "accept")
        self.assertEqual(decision("28003", "BAKING SODA", "Baking"), "accept")
        self.assertEqual(decision("91200", "BOW TIE PASTA", "Pasta by Shape & Type"), "accept")
        self.assertEqual(decision("4522", "PUMPKIN SEEDS", "Popcorn, Peanuts, Seeds & Related Snacks"), "accept")
        self.assertEqual(decision("91193", "ROTINI PASTA", "Pasta by Shape & Type"), "accept")
        self.assertEqual(decision("46509", "PIZZA DOUGH", "Crusts & Dough"), "accept")
        self.assertEqual(decision("19021", "CLAM JUICE", "Canned Seafood"), "accept")
        self.assertEqual(decision("38799", "XANTHAN GUM", "Baking"), "accept")
        self.assertEqual(decision("3858", "KIWIFRUIT", "Pre-Packaged Fruit & Vegetables"), "accept")
        self.assertEqual(decision("27373", "WATERMELON", "Pre-Packaged Fruit & Vegetables"), "accept")
        self.assertEqual(decision("49270", "SALTED PEANUTS", "Popcorn, Peanuts, Seeds & Related Snacks"), "accept")
        self.assertEqual(decision("45528", "PHYLLO DOUGH", "Frozen Bread & Dough"), "accept")
        self.assertEqual(decision("42004", "PLAIN BREADCRUMBS", "Baking"), "accept")
        self.assertEqual(decision("23015", "CARAMELS", "Candy"), "accept")
        self.assertEqual(decision("23442", "SEMI-SWEET CHOCOLATE MORSELS", "Baking Decorations & Dessert Toppings"), "accept")
        self.assertEqual(decision("35204", "MARSALA WINE", "Wine"), "accept")
        self.assertEqual(decision("22514", "GIN", "Liquor"), "accept")
        self.assertEqual(decision("38589", "RIGATONI PASTA", "Pasta by Shape & Type"), "accept")
        self.assertEqual(decision("4577", "PECAN PIECES", "Popcorn, Peanuts, Seeds & Related Snacks"), "accept")
        self.assertEqual(decision("20013", "INSTANT ESPRESSO POWDER", "Coffee"), "accept")
        self.assertEqual(decision("46494", "DEVIL'S FOOD CAKE MIX", "Cake, Cookie & Cupcake Mixes"), "accept")

    def test_batch13_surfaces_route_to_reviewed_cards(self) -> None:
        expected = {
            "bone-in chicken pieces": "15071",
            "low-fat plain yogurt": "11967",
            "bok choy": "37836",
            "crisco": "8278",
            "acorn squash": "5799",
            "mango chutney": "3838",
            "walnut pieces": "49277",
            "orange liqueur": "",
            "caramel ice cream topping": "23070",
            "imitation crabmeat": "19037",
            "extra firm tofu": "12893",
            "dry roasted peanuts": "4756",
            "grapeseed oil": "8047",
            "olives": "9539",
            "fettuccine pasta": "91182",
            "peppercorns": "26901",
            "tortillas": "51362",
            "baked beans": "27301",
            "whiskey": "22670",
            "dry vermouth": "35205",
            "espresso": "33295",
            "small shell pasta": "38396",
            "flax seed": "4770",
            "popped popcorn": "37597",
            "ziti pasta": "91198",
            "canadian bacon": "12008",
            "chili paste": "34574",
            "baileys irish cream": "",
            "chili-garlic sauce": "33128",
            "penne": "91197",
            "pomegranate juice": "4928",
            "coffee liqueur": "22519",
            "lawry's seasoned salt": "91928",
            "frozen hash browns": "5589",
            "safflower oil": "8772",
            "peach schnapps": "",
            "chocolate shavings": "4966",
            "grapefruit juice": "794",
            "oysters": "19026",
        }
        for surface, code in expected.items():
            with self.subTest(surface=surface):
                lab = calculate_lab(display=surface, item=surface, grams=100)
                self.assertEqual(lab.esha_code, code)

        self.assertEqual(calculate_lab(display="orange liqueur", item="orange liqueur", grams=100).fndds_code, "93201000")
        self.assertEqual(calculate_lab(display="baileys irish cream", item="baileys irish cream", grams=100).fndds_code, "93301450")
        self.assertEqual(calculate_lab(display="peach schnapps", item="peach schnapps", grams=100).fndds_code, "93201000")

    def test_batch13_contracts_reject_known_noise(self) -> None:
        def decision(code: str, description: str, category: str, ingredients: str = "") -> str:
            result = evaluate_facts(code, ProductFacts.from_components(description, category, ingredients))
            self.assertIsNotNone(result)
            return result.status

        self.assertEqual(decision("15071", "CHICKEN FAT", "Chicken"), "reject")
        self.assertEqual(decision("11967", "LOWFAT VANILLA YOGURT", "Yogurt"), "reject")
        self.assertEqual(decision("8278", "BUTTER FLAVORED COOKING SPRAY", "Shortening & Oil"), "reject")
        self.assertEqual(decision("23070", "CARAMEL CANDY", "Candy"), "reject")
        self.assertEqual(decision("19037", "CRAB CAKES", "Frozen Fish & Seafood"), "reject")
        self.assertEqual(decision("27301", "BLACK BEANS", "Canned & Bottled Beans"), "reject")
        self.assertEqual(decision("33295", "CHOCOLATE COVERED ESPRESSO BEANS", "Chocolate"), "reject")
        self.assertEqual(decision("34574", "CHILI SAUCE", "Ketchup, Mustard, BBQ & Cheese Sauce"), "reject")
        self.assertEqual(decision("33128", "CHILI GARLIC CHIPS", "Chips, Pretzels & Snacks"), "reject")
        self.assertEqual(decision("5589", "LOADED HASH BROWN CASSEROLE", "Frozen Prepared Sides"), "reject")
        self.assertEqual(decision("19026", "OYSTER CRACKERS", "Crackers & Biscotti"), "reject")

    def test_batch13_contracts_accept_known_good_retail_rows(self) -> None:
        def decision(code: str, description: str, category: str, ingredients: str = "") -> str:
            result = evaluate_facts(code, ProductFacts.from_components(description, category, ingredients))
            self.assertIsNotNone(result)
            return result.status

        self.assertEqual(decision("15071", "BONE-IN CHICKEN PIECES", "Chicken"), "accept")
        self.assertEqual(decision("11967", "PLAIN LOW FAT YOGURT", "Yogurt"), "accept")
        self.assertEqual(decision("37836", "BOK CHOY", "Pre-Packaged Fruit & Vegetables"), "accept")
        self.assertEqual(decision("8278", "CRISCO ALL VEGETABLE SHORTENING", "Shortening & Oil"), "accept")
        self.assertEqual(decision("5799", "ACORN SQUASH", "Pre-Packaged Fruit & Vegetables"), "accept")
        self.assertEqual(decision("3838", "MANGO CHUTNEY", "Oriental, Mexican & Ethnic Sauces"), "accept")
        self.assertEqual(decision("49277", "WALNUT PIECES", "Popcorn, Peanuts, Seeds & Related Snacks"), "accept")
        self.assertEqual(decision("23070", "CARAMEL TOPPING", "Syrups & Molasses"), "accept")
        self.assertEqual(decision("19037", "IMITATION CRABMEAT", "Fish & Seafood"), "accept")
        self.assertEqual(decision("12893", "EXTRA FIRM TOFU", "Plant Based Meat"), "accept")
        self.assertEqual(decision("4756", "DRY ROASTED PEANUTS", "Popcorn, Peanuts, Seeds & Related Snacks"), "accept")
        self.assertEqual(decision("8047", "GRAPESEED OIL", "Vegetable & Cooking Oils"), "accept")
        self.assertEqual(decision("9539", "GREEN OLIVES", "Pickles, Olives, Peppers & Relishes"), "accept")
        self.assertEqual(decision("51362", "FLOUR TORTILLAS", "Tortillas & Flat Breads"), "accept")
        self.assertEqual(decision("27301", "BAKED BEANS", "Canned & Bottled Beans"), "accept")
        self.assertEqual(decision("35205", "DRY VERMOUTH", "Wine"), "accept")
        self.assertEqual(decision("33295", "ESPRESSO", "Coffee"), "accept")
        self.assertEqual(decision("38396", "SMALL SHELLS PASTA", "Pasta by Shape & Type"), "accept")
        self.assertEqual(decision("4770", "FLAX SEEDS", "Popcorn, Peanuts, Seeds & Related Snacks"), "accept")
        self.assertEqual(decision("37597", "POPPED POPCORN", "Popcorn, Peanuts, Seeds & Related Snacks"), "accept")
        self.assertEqual(decision("12008", "CANADIAN BACON", "Bacon"), "accept")
        self.assertEqual(decision("33128", "CHILI GARLIC SAUCE", "Asian Sauces"), "accept")
        self.assertEqual(decision("4928", "POMEGRANATE JUICE", "Fruit & Vegetable Juice, Nectars & Fruit Drinks"), "accept")
        self.assertEqual(decision("5589", "FROZEN HASH BROWNS", "Frozen Vegetables"), "accept")
        self.assertEqual(decision("4966", "CHOCOLATE SHAVINGS", "Baking Decorations & Dessert Toppings"), "accept")
        self.assertEqual(decision("794", "GRAPEFRUIT JUICE", "Fruit & Vegetable Juice, Nectars & Fruit Drinks"), "accept")
        self.assertEqual(decision("19026", "RAW OYSTERS", "Fish & Seafood"), "accept")

    def test_batch14_surfaces_route_to_reviewed_cards(self) -> None:
        expected = {
            "white button mushrooms": "7351",
            "refrigerated biscuits": "16621",
            "dark beer": "34067",
            "ladyfingers": "15424",
            "thousand island dressing": "295",
            "mixed nuts": "4591",
            "prawns": "73123",
            "sriracha sauce": "53470",
            "walnut oil": "8085",
            "cooking apples": "3001",
            "kaiser rolls": "52470",
            "rice noodles": "33770",
            "arrowroot": "38801",
            "silken tofu": "12896",
            "farfalle pasta": "91201",
            "lemonade": "4794",
            "tapioca flour": "93175",
            "habanero chili": "37877",
            "sprite": "20032",
            "craisins": "3487",
            "hot dog bun": "15455",
            "jumbo pasta shells": "91214",
        }
        for surface, code in expected.items():
            with self.subTest(surface=surface):
                lab = calculate_lab(display=surface, item=surface, grams=100)
                self.assertEqual(lab.esha_code, code)

        fndds_expected = {
            "simple syrup": "91301100",
            "anchovy paste": "26101180",
            "blue curacao": "93201000",
            "tamarind paste": "62126000",
        }
        for surface, code in fndds_expected.items():
            with self.subTest(surface=surface):
                lab = calculate_lab(display=surface, item=surface, grams=100)
                self.assertEqual(lab.esha_code, "")
                self.assertEqual(lab.fndds_code, code)

    def test_batch14_contracts_reject_known_noise(self) -> None:
        def decision(code: str, description: str, category: str, ingredients: str = "") -> str:
            result = evaluate_facts(code, ProductFacts.from_components(description, category, ingredients))
            self.assertIsNotNone(result)
            return result.status

        self.assertEqual(decision("7351", "MUSHROOM GRAVY", "Gravy & Sauces"), "reject")
        self.assertEqual(decision("16621", "CHOCOLATE CHIP COOKIE DOUGH", "Refrigerated Dough"), "reject")
        self.assertEqual(decision("34067", "ROOT BEER", "Soda"), "reject")
        self.assertEqual(decision("15424", "LEMON COOKIES", "Cookies & Biscuits"), "reject")
        self.assertEqual(decision("295", "ITALIAN DRESSING", "Salad Dressing & Mayonnaise"), "reject")
        self.assertEqual(decision("73123", "PRAWN DUMPLINGS", "Frozen Dinners & Entrees"), "reject")
        self.assertEqual(decision("8085", "WALNUT OIL DRESSING", "Salad Dressing & Mayonnaise"), "reject")
        self.assertEqual(decision("52470", "KAISER ROLL SANDWICH", "Prepared Meals"), "reject")
        self.assertEqual(decision("33770", "PAD THAI RICE NOODLE MEAL", "Frozen Dinners & Entrees"), "reject")
        self.assertEqual(decision("38801", "ARROWROOT COOKIES", "Cookies & Biscuits"), "reject")
        self.assertEqual(decision("12896", "TOFU NOODLE SOUP", "Plant Based Meals"), "reject")
        self.assertEqual(decision("91201", "ELBOW MACARONI", "Pasta by Shape & Type"), "reject")
        self.assertEqual(decision("4794", "HARD LEMONADE", "Beer"), "reject")
        self.assertEqual(decision("93175", "TAPIOCA PEARLS", "Baking"), "reject")
        self.assertEqual(decision("37877", "HABANERO HOT SAUCE", "Ketchup, Mustard, BBQ & Cheese Sauce"), "reject")
        self.assertEqual(decision("20032", "SPRITE GUMMIES", "Candy"), "reject")
        self.assertEqual(decision("3487", "RAISINS", "Dried Fruit"), "reject")
        self.assertEqual(decision("15455", "HAMBURGER BUNS", "Breads & Buns"), "reject")
        self.assertEqual(decision("91214", "STUFFED SHELLS DINNER", "Frozen Dinners & Entrees"), "reject")

    def test_batch14_contracts_accept_known_good_retail_rows(self) -> None:
        def decision(code: str, description: str, category: str, ingredients: str = "") -> str:
            result = evaluate_facts(code, ProductFacts.from_components(description, category, ingredients))
            self.assertIsNotNone(result)
            return result.status

        self.assertEqual(decision("7351", "WHITE SLICED MUSHROOMS", "Pre-Packaged Fruit & Vegetables"), "accept")
        self.assertEqual(decision("16621", "PILLSBURY GRANDS BISCUITS", "Baking/Cooking Mixes/Supplies"), "accept")
        self.assertEqual(decision("34067", "DARK STOUT BEER", "Beer"), "accept")
        self.assertEqual(decision("15424", "LADYFINGERS", "Cookies & Biscuits"), "accept")
        self.assertEqual(decision("295", "THOUSAND ISLAND DRESSING", "Salad Dressing & Mayonnaise"), "accept")
        self.assertEqual(decision("73123", "RAW PRAWNS", "Frozen Fish & Seafood"), "accept")
        self.assertEqual(decision("8085", "WALNUT OIL", "Vegetable & Cooking Oils"), "accept")
        self.assertEqual(decision("52470", "KAISER ROLLS", "Breads & Buns"), "accept")
        self.assertEqual(decision("33770", "RICE STICKS RICE NOODLES", "All Noodles"), "accept")
        self.assertEqual(decision("38801", "ARROWROOT STARCH", "Baking"), "accept")
        self.assertEqual(decision("12896", "SILKEN TOFU", "Plant Based Meat"), "accept")
        self.assertEqual(decision("91201", "FARFALLE PASTA", "Pasta by Shape & Type"), "accept")
        self.assertEqual(decision("4794", "LEMONADE", "Fruit & Vegetable Juice, Nectars & Fruit Drinks"), "accept")
        self.assertEqual(decision("93175", "TAPIOCA FLOUR", "Flours & Corn Meal"), "accept")
        self.assertEqual(decision("37877", "HABANERO PEPPERS", "Pre-Packaged Fruit & Vegetables"), "accept")
        self.assertEqual(decision("20032", "SPRITE LEMON LIME SODA", "Soda"), "accept")
        self.assertEqual(decision("3487", "CRAISINS DRIED CRANBERRIES", "Dried Fruit"), "accept")
        self.assertEqual(decision("15455", "HOT DOG BUNS", "Breads & Buns"), "accept")
        self.assertEqual(decision("91214", "JUMBO SHELLS PASTA", "Pasta by Shape & Type"), "accept")

    def test_batch15_surfaces_route_to_reviewed_cards(self) -> None:
        expected = {
            "popped popcorn": "37597",
            "fresh baby spinach": "6863",
            "white kidney beans": "17741",
            "skirt steak": "38987",
            "french-style green beans": "6251",
            "beef roast": "27980",
            "juniper berries": "35078",
            "unbleached cane sugar": "49315",
            "beef flank steak": "58267",
            "pimento-stuffed green olives": "7846",
            "pitted green olives": "9539",
            "white peppercorns": "26037",
            "white sesame seeds": "4523",
            "candied red cherries": "48217",
            "ciabatta rolls": "23640",
            "yellow sweet onion": "9548",
            "refrigerated breadstick dough": "42257",
        }
        for surface, code in expected.items():
            with self.subTest(surface=surface):
                lab = calculate_lab(display=surface, item=surface, grams=100)
                self.assertEqual(lab.esha_code, code)

        beef_steak = calculate_lab(display="beef steak", item="beef steak", grams=100)
        self.assertEqual(beef_steak.esha_code, "")
        self.assertEqual(beef_steak.sr28_fdc_id, "169429")

    def test_batch15_contracts_reject_known_noise(self) -> None:
        def decision(code: str, description: str, category: str, ingredients: str = "") -> str:
            result = evaluate_facts(code, ProductFacts.from_components(description, category, ingredients))
            self.assertIsNotNone(result)
            return result.status

        self.assertEqual(decision("37597", "CARAMEL POPCORN", "Popcorn, Peanuts, Seeds & Related Snacks"), "reject")
        self.assertEqual(decision("6863", "SPINACH ARTICHOKE DIP", "Dips & Salsa"), "reject")
        self.assertEqual(decision("17741", "BLACK BEANS", "Canned & Bottled Beans"), "reject")
        self.assertEqual(decision("38987", "SKIRT STEAK DINNER", "Frozen Dinners & Entrees"), "reject")
        self.assertEqual(decision("6251", "GREEN BEAN CASSEROLE", "Frozen Vegetables"), "reject")
        self.assertEqual(decision("27980", "PORK ROAST", "Other Meats"), "reject")
        self.assertEqual(decision("35078", "JUNIPER KETCHUP", "Ketchup, Mustard, BBQ & Cheese Sauce"), "reject")
        self.assertEqual(decision("49315", "BROWN CANE SUGAR", "Granulated, Brown & Powdered Sugar"), "reject")
        self.assertEqual(decision("7846", "PIMENTO PEPPERS", "Canned Vegetables"), "reject")
        self.assertEqual(decision("26037", "WHITE PEPPER GRAVY", "Gravy & Sauces"), "reject")
        self.assertEqual(decision("23640", "CIABATTA SANDWICH", "Prepared Meals"), "reject")
        self.assertEqual(decision("58267", "FLANK STEAK BEEF JERKY", "Other Snacks"), "reject")
        self.assertEqual(decision("42257", "BREADSTICK CRACKERS", "Crackers & Biscotti"), "reject")
        self.assertEqual(decision("48217", "CHOCOLATE COVERED CHERRIES", "Candy"), "reject")

    def test_batch15_contracts_accept_known_good_retail_rows(self) -> None:
        def decision(code: str, description: str, category: str, ingredients: str = "") -> str:
            result = evaluate_facts(code, ProductFacts.from_components(description, category, ingredients))
            self.assertIsNotNone(result)
            return result.status

        self.assertEqual(decision("37597", "POPCORN", "Popcorn, Peanuts, Seeds & Related Snacks"), "accept")
        self.assertEqual(decision("6863", "BABY SPINACH", "Pre-Packaged Fruit & Vegetables"), "accept")
        self.assertEqual(decision("17741", "CANNELLINI WHITE KIDNEY BEANS", "Canned & Bottled Beans"), "accept")
        self.assertEqual(decision("38987", "BEEF SKIRT STEAK", "Other Meats"), "accept")
        self.assertEqual(decision("6251", "FRENCH STYLE GREEN BEANS", "Canned Vegetables"), "accept")
        self.assertEqual(decision("27980", "BEEF CHUCK ROAST", "Other Meats"), "accept")
        self.assertEqual(decision("35078", "JUNIPER BERRIES", "Herbs & Spices"), "accept")
        self.assertEqual(decision("49315", "RAW CANE SUGAR", "Granulated, Brown & Powdered Sugar"), "accept")
        self.assertEqual(decision("7846", "GREEN OLIVES STUFFED WITH PIMENTO", "Pickles, Olives, Peppers & Relishes"), "accept")
        self.assertEqual(decision("26037", "WHITE PEPPERCORNS", "Herbs & Spices"), "accept")
        self.assertEqual(decision("23640", "CIABATTA ROLLS", "Breads & Buns"), "accept")
        self.assertEqual(decision("58267", "BEEF FLANK STEAK", "Other Meats"), "accept")
        self.assertEqual(decision("42257", "PILLSBURY ORIGINAL BREADSTICKS", "Baking/Cooking Mixes/Supplies"), "accept")
        self.assertEqual(decision("48217", "MARASCHINO CHERRIES", "Baking Decorations & Dessert Toppings"), "accept")

    def test_reviewed_contracts_reject_observed_product_leaks(self) -> None:
        def decision(code: str, description: str, category: str, ingredients: str = "") -> str:
            result = evaluate_facts(code, ProductFacts.from_components(description, category, ingredients))
            self.assertIsNotNone(result)
            return result.status

        self.assertEqual(decision("49296", "GARLIC SEA SALT", "Seasoning Mixes, Salts, Marinades & Tenderizers"), "reject")
        self.assertEqual(decision("51329", "BANANA OATMEAL", "Pre-Packaged Fruit & Vegetables"), "reject")
        self.assertEqual(decision("51329", "MILD BANANA PEPPER RINGS", "Pre-Packaged Fruit & Vegetables"), "reject")
        self.assertEqual(decision("51329", "BANANA BLOSSOM IN BRINE", "Canned Fruit"), "reject")
        self.assertEqual(decision("53475", "MAPLE CIDER VINEGAR", "Other Cooking Sauces"), "reject")
        self.assertEqual(decision("3088", "CANDIED ORANGE PEELS IN SYRUP", "Pre-Packaged Fruit & Vegetables"), "reject")
        self.assertEqual(decision("53471", "TABASCO SCORPION SAUCE", "Ketchup, Mustard, BBQ & Cheese Sauce"), "reject")
        self.assertEqual(decision("53471", "TABASCO BUFFALO STYLE HOT SAUCE", "Ketchup, Mustard, BBQ & Cheese Sauce"), "reject")
        self.assertEqual(decision("4523", "SESAME & SUNFLOWER SEED CRUNCH", "Popcorn, Peanuts, Seeds & Related Snacks"), "reject")
        self.assertEqual(decision("3001", "CARAMEL APPLES WITH PEANUTS", "Pre-Packaged Fruit & Vegetables"), "reject")
        self.assertEqual(decision("3001", "APPLES & CREME PARFAIT", "Canned Fruit"), "reject")
        self.assertEqual(decision("3001", "APPLES & CHEDDAR SALAD", "Pre-Packaged Fruit & Vegetables"), "reject")
        self.assertEqual(decision("25570", "TORTILLA CHIPS SALSA VERDE", "Chips, Pretzels & Snacks"), "reject")
        self.assertEqual(decision("50477", "CREAM OF CHICKEN & MUSHROOM SOUP", "Canned Soup"), "reject")
        self.assertEqual(decision("91928", "GARLIC SEASONING SALT", "Seasoning Mixes, Salts, Marinades & Tenderizers"), "reject")
        self.assertEqual(decision("90530", "CHERRY TOMATO SALAD", "Pre-Packaged Fruit & Vegetables"), "reject")
        self.assertEqual(decision("3381", "DRIED BLUEBERRIES", "Dried Fruit"), "reject")
        self.assertEqual(decision("1793", "CHICKEN VEGETABLE BROTH", "Canned Soup"), "reject")
        self.assertEqual(decision("22501", "RED WINE VINEGAR", "Other Cooking Sauces"), "reject")
        self.assertEqual(decision("3990", "ORANGE PINEAPPLE JUICE", "Fruit & Vegetable Juice, Nectars & Fruit Drinks"), "reject")
        self.assertEqual(decision("26622", "CREAMY DILL DIP", "Dips & Salsa"), "reject")
        self.assertEqual(decision("508", "VANILLA ICE CREAM CAKE WITH WHIPPED TOPPING", "Ice Cream & Frozen Yogurt"), "reject")
        self.assertEqual(decision("26630", "SPEARMINT SUGAR FREE GUM ICE CUBES", "Chewing Gum & Mints"), "reject")
        self.assertEqual(decision("2004", "VANILLA ICE CREAM SANDWICH", "Ice Cream & Frozen Yogurt"), "reject")
        self.assertEqual(decision("52629", "POPCORN SHRIMP", "Frozen Fish & Seafood"), "reject")
        self.assertEqual(decision("6813", "EGGPLANT PICKLED", "Pickles, Olives, Peppers & Relishes"), "reject")
        self.assertEqual(decision("4511", "COCONUT WATER", "Coconut Water"), "reject")
        self.assertEqual(decision("41524", "CHOCOLATE MILK TASTING SQUARE", "Chocolate"), "reject")
        self.assertEqual(decision("34814", "COOKIE WITH SPLENDA", "Cookies & Biscuits"), "reject")
        self.assertEqual(decision("26901", "FETA BLACK PEPPERCORN CRUMBLES", "Cheese"), "reject")
        self.assertEqual(decision("7378", "RED LENTIL SOUP", "Other Soups"), "reject")
        self.assertEqual(decision("92163", "CHICKEN SHOYU RAMEN NOODLES", "Frozen Dinners & Entrees"), "reject")
        self.assertEqual(decision("28169", "BEEF FLAVOR RAMEN NOODLES", "All Noodles"), "reject")
        self.assertEqual(decision("58511", "CHICKEN ANDOUILLE SAUSAGE", "Sausages, Hotdogs & Brats"), "reject")
        self.assertEqual(decision("22593", "SPICED RUM PECANS", "Popcorn, Peanuts, Seeds & Related Snacks"), "reject")
        self.assertEqual(decision("25778", "PEANUT BUTTER POWDER", "Nut & Seed Butters"), "reject")
        self.assertEqual(decision("25778", "PEANUT BUTTER MINI CUPS", "Nut & Seed Butters"), "reject")
        self.assertEqual(decision("25778", "PEANUT BUTTER SPREAD", "Nut & Seed Butters", "Marshmallow Creme, Peanut Butter."), "reject")
        self.assertEqual(decision("4591", "CHOCOLATE MIXED NUTS FLAVOR SNACK BAR", "Chocolate"), "reject")
        self.assertEqual(decision("434", "HOT CHILI SAUCE", "Ketchup, Mustard, BBQ & Cheese Sauce"), "reject")
        self.assertEqual(decision("6499", "KALAMATA OLIVES HUMMUS", "Dips & Salsa"), "reject")
        self.assertEqual(decision("3996", "DICED TOMATOES IN TOMATO JUICE", "Tomatoes"), "reject")
        self.assertEqual(decision("5476", "DICED TOMATOES IN TOMATO PUREE", "Tomatoes"), "reject")
        self.assertEqual(decision("4545", "CHOCOLATE SUNFLOWER SEEDS", "Popcorn, Peanuts, Seeds & Related Snacks"), "reject")
        self.assertEqual(decision("92830", "CHICKEN ALFREDO WITH PENNE PASTA", "Other Deli"), "reject")
        self.assertEqual(decision("26830", "IMITATION CRABMEAT SURIMI", "Fish & Seafood"), "reject")
        self.assertEqual(decision("90659", "WHITE CHOCOLATE MACADAMIA COOKIE", "Cookies & Biscuits"), "reject")
        self.assertEqual(decision("23447", "WHITE CHOCOLATE VANILLA PUDDING WITH CHOCOLATE CHIPS", "Puddings & Custards"), "reject")
        self.assertEqual(decision("4696", "PEANUT BUTTER", "Nut & Seed Butters"), "reject")
        self.assertEqual(decision("82043", "CAYENNE LEMONADE", "Soda"), "reject")
        self.assertEqual(decision("91211", "LASAGNA SOUP WITH TURKEY SAUSAGE", "Other Soups"), "reject")
        self.assertEqual(decision("12888", "TOFU NOODLE SOUP", "Plant Based Meals"), "reject")
        self.assertEqual(decision("31180", "SORBET WITH SPLENDA", "Other Frozen Desserts"), "reject")
        self.assertEqual(decision("4986", "CRANBERRY APPLE JUICE", "Fruit & Vegetable Juice, Nectars & Fruit Drinks"), "reject")
        self.assertEqual(decision("4513", "HAZELNUT COFFEE CREAMER", "Milk Additives"), "reject")
        self.assertEqual(decision("50473", "CREAM OF MUSHROOM SOUP", "Canned Soup"), "reject")
        self.assertEqual(decision("63195", "CASHEW NUT CLUSTERS", "Popcorn, Peanuts, Seeds & Related Snacks"), "reject")
        self.assertEqual(decision("8555", "RANCH DRESSING DRY PACKET", "Salad Dressing & Mayonnaise"), "reject")
        self.assertEqual(decision("48015", "CHERRY LOW SUGAR PIE FILLING", "Pastry Shells & Fillings"), "reject")
        self.assertEqual(decision("4686", "HUMMUS TAHINI CHICKPEA DIP", "Dips & Salsa"), "reject")
        self.assertEqual(decision("22519", "KAHLUA CHOCOLATES", "Chocolate"), "reject")
        self.assertEqual(decision("8233", "TUNA IN SUNFLOWER OIL", "Canned Tuna"), "reject")
        self.assertEqual(decision("92017", "MAPLE INSTANT OATMEAL", "Cereal"), "reject")
        self.assertEqual(decision("38328", "ORZO RICE PILAF", "Pasta by Shape & Type"), "reject")
        self.assertEqual(decision("16533", "BISQUICK COMPLETE PANCAKE MIX", "Pancake, Waffle Mixes"), "reject")
        self.assertEqual(decision("23007", "MARSHMALLOW CREME", "Candy"), "reject")
        self.assertEqual(decision("70963", "RITZ PEANUT BUTTER SANDWICH CRACKERS", "Crackers & Biscotti"), "reject")
        self.assertEqual(decision("8037", "COCONUT OIL SPRAY", "Vegetable & Cooking Oils"), "reject")
        self.assertEqual(decision("41429", "RANCH DIP MIX", "Seasoning Mixes, Salts, Marinades & Tenderizers"), "reject")
        self.assertEqual(decision("48475", "GRAHAM CRACKER CHEESECAKE FILLING", "Pastry Shells & Fillings"), "reject")
        self.assertEqual(decision("19029", "SCALLOPED POTATOES", "Frozen Prepared Sides"), "reject")
        self.assertEqual(decision("90065", "MAPLE SYRUP", "Syrups & Molasses"), "reject")
        self.assertEqual(decision("12879", "WONTON SOUP", "Frozen Dinners & Entrees"), "reject")
        self.assertEqual(decision("1282", "COLBY & MONTEREY JACK MAC AND CHEESE", "Cheese"), "reject")

    def test_reviewed_contracts_accept_known_good_retail_rows(self) -> None:
        def decision(code: str, description: str, category: str, ingredients: str = "") -> str:
            result = evaluate_facts(code, ProductFacts.from_components(description, category, ingredients))
            self.assertIsNotNone(result)
            return result.status

        self.assertEqual(decision("22504", "WHITE COOKING WINE", "Other Cooking Sauces", "WINE, SALT."), "accept")
        self.assertEqual(
            decision(
                "25490",
                "LARGE FLOUR TORTILLA",
                "Mexican Dinner Mixes",
                "ENRICHED FLOUR (BLEACHED WHEAT FLOUR), WATER, VEGETABLE SHORTENING, SALT.",
            ),
            "accept",
        )
        self.assertEqual(
            decision(
                "25490",
                "ORGANIC WHITE TORTILLA",
                "Mexican Dinner Mixes",
                "ORGANIC UNBLEACHED WHEAT FLOUR, WATER, CANOLA OIL, SEA SALT.",
            ),
            "accept",
        )
        self.assertEqual(decision("51329", "BANANAS", "Pre-Packaged Fruit & Vegetables"), "accept")
        self.assertEqual(decision("3001", "GALA APPLES", "Pre-Packaged Fruit & Vegetables"), "accept")
        self.assertEqual(decision("25570", "MEDIUM SALSA", "Dips & Salsa"), "accept")
        self.assertEqual(decision("50477", "CREAM OF MUSHROOM CONDENSED SOUP", "Canned Soup"), "accept")
        self.assertEqual(decision("90374", "CREAM OF CHICKEN CONDENSED SOUP", "Canned Soup"), "accept")
        self.assertEqual(decision("91928", "SEASONING SALT", "Seasoning Mixes, Salts, Marinades & Tenderizers"), "accept")
        self.assertEqual(decision("90530", "CHERRY TOMATOES", "Pre-Packaged Fruit & Vegetables"), "accept")
        self.assertEqual(decision("5511", "CAPERS", "Pickles, Olives, Peppers & Relishes"), "accept")
        self.assertEqual(decision("3381", "FRESH BLUEBERRIES", "Pre-Packaged Fruit & Vegetables"), "accept")
        self.assertEqual(decision("4504", "ALMONDS", "Popcorn, Peanuts, Seeds & Related Snacks"), "accept")
        self.assertEqual(decision("49260", "SLICED ALMONDS", "Popcorn, Peanuts, Seeds & Related Snacks"), "accept")
        self.assertEqual(decision("1793", "VEGETABLE BROTH", "Canned Soup"), "accept")
        self.assertEqual(decision("22501", "RED COOKING WINE", "Other Cooking Sauces", "RED WINE, SALT."), "accept")
        self.assertEqual(decision("3990", "PINEAPPLE JUICE", "Fruit & Vegetable Juice, Nectars & Fruit Drinks"), "accept")
        self.assertEqual(decision("5104", "WHITE ONION", "Pre-Packaged Fruit & Vegetables"), "accept")
        self.assertEqual(decision("26622", "FRESH DILL", "Herbs & Spices"), "accept")
        self.assertEqual(decision("508", "ORIGINAL WHIPPED TOPPING", "Baking Decorations & Dessert Toppings"), "accept")
        self.assertEqual(decision("26630", "FRESH MINT", "Herbs & Spices"), "accept")
        self.assertEqual(decision("2004", "VANILLA ICE CREAM", "Ice Cream & Frozen Yogurt"), "accept")
        self.assertEqual(decision("48557", "DRIED CRANBERRIES", "Dried Fruit"), "accept")
        self.assertEqual(decision("52629", "RAW SHRIMP", "Frozen Fish & Seafood"), "accept")
        self.assertEqual(decision("26017", "CREAM OF TARTAR", "Baking"), "accept")
        self.assertEqual(decision("6813", "EGGPLANT", "Pre-Packaged Fruit & Vegetables"), "accept")
        self.assertEqual(decision("53474", "FISH SAUCE", "Condiments"), "accept")
        self.assertEqual(decision("4511", "SHREDDED COCONUT", "Baking"), "accept")
        self.assertEqual(decision("22604", "COOKING SHERRY", "Other Cooking Sauces"), "accept")
        self.assertEqual(decision("14984", "DICED GREEN CHILES", "Canned Vegetables"), "accept")
        self.assertEqual(decision("5001", "ASPARAGUS", "Pre-Packaged Fruit & Vegetables"), "accept")
        self.assertEqual(decision("41524", "SEMISWEET CHOCOLATE", "Baking Chocolate"), "accept")
        self.assertEqual(decision("38277", "BREAD FLOUR", "Flours & Corn Meal"), "accept")
        self.assertEqual(decision("13472", "CORN TORTILLAS", "Tortillas"), "accept")
        self.assertEqual(decision("5172", "PLUM TOMATOES", "Pre-Packaged Fruit & Vegetables"), "accept")
        self.assertEqual(decision("34814", "SPLENDA", "Sugars & Sweeteners"), "accept")
        self.assertEqual(decision("6298", "100% PURE PUMPKIN", "Canned Vegetables"), "accept")
        self.assertEqual(decision("24169", "UNSWEETENED CHOCOLATE", "Baking Chocolate"), "accept")
        self.assertEqual(decision("9114", "SPAGHETTI SAUCE", "Tomato-Based Pasta Sauce"), "accept")
        self.assertEqual(decision("26901", "BLACK PEPPERCORNS", "Herbs & Spices"), "accept")
        self.assertEqual(decision("7378", "RED LENTILS", "Vegetable and Lentil Mixes"), "accept")
        self.assertEqual(decision("92163", "RAMEN NOODLES", "All Noodles"), "accept")
        self.assertEqual(decision("28169", "CHICKEN FLAVOR RAMEN NOODLES", "All Noodles"), "accept")
        self.assertEqual(decision("58511", "ANDOUILLE SAUSAGE", "Sausages, Hotdogs & Brats"), "accept")
        self.assertEqual(decision("22593", "SPICED RUM", "Liquor"), "accept")
        self.assertEqual(decision("25778", "CREAMY PEANUT BUTTER", "Nut & Seed Butters", "Peanuts, Salt."), "accept")
        self.assertEqual(decision("4591", "MIXED NUTS PEANUTS ALMONDS CASHEWS PECANS", "Popcorn, Peanuts, Seeds & Related Snacks"), "accept")
        self.assertEqual(decision("4356", "BITTERSWEET CHOCOLATE", "Chocolate"), "accept")
        self.assertEqual(decision("434", "CHILI SAUCE", "Ketchup, Mustard, BBQ & Cheese Sauce"), "accept")
        self.assertEqual(decision("46089", "YELLOW CAKE MIX", "Cake, Cookie & Cupcake Mixes"), "accept")
        self.assertEqual(decision("6499", "PITTED KALAMATA OLIVES", "Pickles, Olives, Peppers & Relishes"), "accept")
        self.assertEqual(decision("3934", "GOLDEN RAISINS", "Wholesome Snacks"), "accept")
        self.assertEqual(decision("6492", "ROMA TOMATOES", "Pre-Packaged Fruit & Vegetables"), "accept")
        self.assertEqual(decision("3996", "TOMATO JUICE", "Fruit & Vegetable Juice, Nectars & Fruit Drinks"), "accept")
        self.assertEqual(decision("5476", "TOMATO PUREE", "Tomatoes"), "accept")
        self.assertEqual(decision("4545", "SUNFLOWER SEEDS", "Popcorn, Peanuts, Seeds & Related Snacks"), "accept")
        self.assertEqual(decision("38004", "YELLOW CORNMEAL", "Flours & Corn Meal"), "accept")
        self.assertEqual(decision("23008", "MINIATURE MARSHMALLOWS", "Candy"), "accept")
        self.assertEqual(decision("92830", "PENNE PASTA", "Pasta by Shape & Type"), "accept")
        self.assertEqual(decision("26830", "PASTEURIZED CRABMEAT", "Fish & Seafood"), "accept")
        self.assertEqual(decision("90659", "WHITE CHOCOLATE", "Chocolate"), "accept")
        self.assertEqual(decision("23447", "WHITE CHOCOLATE CHIPS", "Baking Decorations & Dessert Toppings"), "accept")
        self.assertEqual(decision("4696", "JUMBO PEANUTS", "Popcorn, Peanuts, Seeds & Related Snacks"), "accept")
        self.assertEqual(decision("82043", "GROUND CAYENNE PEPPER", "Herbs & Spices"), "accept")
        self.assertEqual(decision("91211", "LASAGNA NOODLES", "Pasta by Shape & Type"), "accept")
        self.assertEqual(decision("12888", "EXTRA FIRM TOFU", "Plant Based Meat"), "accept")
        self.assertEqual(decision("31180", "SPLENDA GRANULAR SWEETENER", "Sugars & Sweeteners"), "accept")
        self.assertEqual(decision("22671", "BOURBON", "Liquor"), "accept")
        self.assertEqual(decision("36986", "SAUERKRAUT", "Pickles, Olives, Peppers & Relishes"), "accept")
        self.assertEqual(decision("20033", "SOY MILK", "Plant Based Milk"), "accept")
        self.assertEqual(decision("4986", "CRANBERRY JUICE", "Fruit & Vegetable Juice, Nectars & Fruit Drinks"), "accept")
        self.assertEqual(decision("4513", "HAZELNUTS", "Popcorn, Peanuts, Seeds & Related Snacks"), "accept")
        self.assertEqual(decision("50473", "CREAM OF CELERY CONDENSED SOUP", "Canned Soup"), "accept")
        self.assertEqual(decision("63195", "RAW CASHEWS", "Popcorn, Peanuts, Seeds & Related Snacks"), "accept")
        self.assertEqual(decision("8555", "RANCH DRESSING", "Salad Dressing & Mayonnaise"), "accept")
        self.assertEqual(decision("48015", "CHERRY PIE FILLING", "Pastry Shells & Fillings"), "accept")
        self.assertEqual(decision("4686", "TAHINI", "Oriental, Mexican & Ethnic Sauces"), "accept")
        self.assertEqual(decision("8479", "MIRACLE WHIP", "Salad Dressing & Mayonnaise"), "accept")
        self.assertEqual(decision("22519", "COFFEE LIQUEUR", "Liquor"), "accept")
        self.assertEqual(decision("8233", "SUNFLOWER OIL", "Vegetable & Cooking Oils"), "accept")
        self.assertEqual(decision("92017", "QUICK ONE MINUTE OATMEAL", "Cereal"), "accept")
        self.assertEqual(decision("38328", "ORZO PASTA", "Pasta by Shape & Type"), "accept")
        self.assertEqual(decision("16533", "BISQUICK ORIGINAL PANCAKE & BAKING MIX", "Pancake, Waffle Mixes"), "accept")
        self.assertEqual(decision("23007", "MARSHMALLOWS", "Candy"), "accept")
        self.assertEqual(decision("70963", "RITZ CRACKERS", "Crackers & Biscotti"), "accept")
        self.assertEqual(decision("8037", "COCONUT OIL", "Vegetable & Cooking Oils"), "accept")
        self.assertEqual(decision("41429", "RANCH SALAD DRESSING MIX", "Seasoning Mixes, Salts, Marinades & Tenderizers"), "accept")
        self.assertEqual(decision("48475", "GRAHAM CRACKER PIE CRUST", "Pie Crusts"), "accept")
        self.assertEqual(decision("19029", "SEA SCALLOPS", "Frozen Fish & Seafood"), "accept")
        self.assertEqual(decision("90065", "GOLDEN CANE SYRUP", "Syrups & Molasses"), "accept")
        self.assertEqual(decision("12879", "WONTON WRAPPERS", "Crusts & Dough"), "accept")
        self.assertEqual(decision("1282", "COLBY JACK COLBY & MONTEREY JACK CHEESES", "Cheese"), "accept")


class CartProbeSurfaceCandidateTests(unittest.TestCase):
    def test_surface_candidate_rewrites_cover_known_head_failures(self) -> None:
        self.assertEqual(surface_candidates("Spices, mustard seed, ground", "")[0], "ground mustard")
        self.assertEqual(
            surface_candidates("Wheat flour, white, all-purpose, enriched, bleached", "")[0],
            "all purpose flour",
        )
        self.assertEqual(surface_candidates("Spices, pepper, black", "")[0], "black pepper")
        self.assertEqual(
            surface_candidates("Leavening agents, yeast, baker's, active dry", "")[0],
            "active dry yeast",
        )
        self.assertEqual(
            surface_candidates("Baking mixes, pancakes, dry mix, complete", "")[0],
            "pancake mix",
        )


class Top2500ChecklistBuilderTests(unittest.TestCase):
    def test_build_checklist_assigns_lanes_and_status(self) -> None:
        rows = [
            {
                "queue_rank": "1",
                "issue_priority": "P1",
                "normalized_item": "macaroni",
                "occurrence_count": "736",
                "esha_code": "",
                "esha_description": "",
                "issue_class": "canonical_gap",
                "recommended_action": "Find a reviewed target.",
                "audit_status": "todo",
                "audit_notes": "",
                "product_contract_status": "",
            },
            {
                "queue_rank": "2",
                "issue_priority": "P2",
                "normalized_item": "butter",
                "occurrence_count": "112921",
                "esha_code": "8000",
                "esha_description": "Butter, salted",
                "issue_class": "md_card_or_query_gap",
                "recommended_action": "Open the ESHA card and clean the query.",
                "audit_status": "todo",
                "audit_notes": "",
                "product_contract_status": "",
            },
        ]
        checklist = build_checklist(rows)
        self.assertEqual(checklist[0]["fix_lane"], "canonical_identity")
        self.assertEqual(checklist[0]["status"], "todo")
        self.assertEqual(checklist[1]["fix_lane"], "esha_card_query")
        self.assertEqual(checklist[1]["batch_id"], "P2-0001")

    def test_write_csv_emits_expected_columns(self) -> None:
        rows = [
            {
                "queue_rank": "1",
                "issue_priority": "P1",
                "normalized_item": "salt",
                "occurrence_count": "254404",
                "esha_code": "26098",
                "esha_description": "Monosodium glutamate",
                "issue_class": "md_card_or_query_gap",
                "recommended_action": "Review the card.",
                "fix_lane": "esha_card_query",
                "target_fix_file": "implementation/output/esha_code_query_packs/*",
                "regression_test": "implementation.tests.test_top2500_cleanup_regressions",
                "lab_probe_command": "python3 implementation/surface_lab_calculator.py --display \"salt\" --item \"salt\" --grams 100",
                "queue_rebuild_command": "python3 implementation/build_top_ingredient_coverage_audit.py",
                "proof_artifact": "implementation/output/top2500_cleanup_queue.csv",
                "status": "todo",
                "owner": "",
                "batch_id": "P1-0001",
                "verified_at": "",
                "notes": "",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "checklist.csv"
            write_csv(rows, out)
            text = out.read_text(encoding="utf-8")
        self.assertIn("normalized_item", text)
        self.assertIn("batch_id", text)


class Top2500AuditAndQueueTests(unittest.TestCase):
    def test_reviewed_terminal_bridge_states_are_not_p1(self) -> None:
        split_priority, split_class, _, _ = issue_for(
            {
                "bridge_status": "component_split",
                "bridge_source": "approved_split_match",
                "trust_level": "reviewed_rule",
                "product_contract_status": "",
                "canonical_row_status": "missing",
                "esha_code": "",
                "esha_match_type": "",
                "wrongness_batch": "",
                "cleanup_action": "",
                "esha_backing_status": "",
                "pack_candidate_clean_rows": "",
                "pack_cleanup_rows": "",
                "process_audit_flags": "",
            }
        )
        alt_priority, alt_class, _, _ = issue_for(
            {
                "bridge_status": "true_alternative_options",
                "bridge_source": "approved_alternative_match",
                "trust_level": "reviewed_rule",
                "product_contract_status": "",
                "canonical_row_status": "missing",
                "esha_code": "",
                "esha_match_type": "",
                "wrongness_batch": "",
                "cleanup_action": "",
                "esha_backing_status": "",
                "pack_candidate_clean_rows": "",
                "pack_cleanup_rows": "",
                "process_audit_flags": "",
            }
        )
        manual_priority, manual_class, _, _ = issue_for(
            {
                "bridge_status": "manual_food_required",
                "bridge_source": "approved_reject",
                "trust_level": "reviewed_rule",
                "product_contract_status": "",
                "canonical_row_status": "missing",
                "esha_code": "",
                "esha_match_type": "reviewed_no_esha_target:top2500_p1",
                "wrongness_batch": "",
                "cleanup_action": "",
                "esha_backing_status": "",
                "pack_candidate_clean_rows": "",
                "pack_cleanup_rows": "",
                "process_audit_flags": "",
            }
        )

        self.assertEqual((split_priority, split_class), ("P3", "explicit_component_split"))
        self.assertEqual((alt_priority, alt_class), ("P3", "explicit_alternative_options"))
        self.assertEqual((manual_priority, manual_class), ("P3", "explicit_manual_food_required"))

    def test_reviewed_external_catalog_assignments_are_not_actionable_queue_rows(self) -> None:
        priority, issue_class, flags, _ = issue_for(
            {
                "bridge_status": "concept_ready",
                "bridge_source": "approved_alias_match",
                "trust_level": "reviewed_rule",
                "product_contract_status": "external_catalog_covered",
                "canonical_row_status": "exact_surface",
                "esha_code": "26630",
                "esha_match_type": "reviewed_top2500_p2:fresh_mint",
                "wrongness_batch": "identity_with_product_evidence",
                "cleanup_action": "audit_row_esha_assignment",
                "esha_backing_status": "row_esha_cleanup_only",
                "pack_candidate_clean_rows": "0",
                "pack_cleanup_rows": "6",
                "process_audit_flags": "",
            }
        )
        self.assertEqual((priority, issue_class), ("P3", "external_catalog_covered"))
        self.assertIn("reviewed_external_catalog_shopping", flags)

    def test_queue_excludes_terminal_watchlist_rows(self) -> None:
        queue = build_queue(
            [
                {
                    "issue_priority": "P3",
                    "issue_class": "explicit_no_esha_target",
                    "rank": "1",
                    "normalized_item": "baking apples",
                    "occurrence_count": "193",
                },
                {
                    "issue_priority": "P3",
                    "issue_class": "external_catalog_covered",
                    "rank": "2",
                    "normalized_item": "red delicious apples",
                    "occurrence_count": "104",
                },
                {
                    "issue_priority": "P3",
                    "issue_class": "explicit_non_food_skip",
                    "rank": "3",
                    "normalized_item": "aluminum foil",
                    "occurrence_count": "97",
                },
                {
                    "issue_priority": "P2",
                    "issue_class": "md_card_or_query_gap",
                    "rank": "4",
                    "normalized_item": "butter",
                    "occurrence_count": "112921",
                },
            ]
        )
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["normalized_item"], "butter")

    def test_cleanup_queue_ignores_clean_reviewed_exact_text_conflict(self) -> None:
        action, reason, mechanism = classify_cleanup_row(
            {
                "esha_product_backing_status": "row_esha_has_clean_products",
                "audit_flags": "row_esha_differs_from_exact_esha_text",
                "product_probe_total": "0",
                "pack_candidate_clean_rows": "38",
                "pack_cleanup_rows": "0",
                "pack_total_product_matches": "38",
            }
        )
        self.assertEqual((action, reason, mechanism), ("", "", ""))


if __name__ == "__main__":
    unittest.main()
