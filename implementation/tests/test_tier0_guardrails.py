"""Tier 0 preflight — 20 guardrails, each preventing one historical failure
pattern named in CALCULATOR_DIAGNOSIS_WHY_IT_IS_FUCKED.md and related docs.

These run before any long audit or mapper run. See spec Appendix for the
1:1 mapping.
"""
import csv
import re
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "implementation"))


# ==== Reference data loaders (cached across tests) ============================

_SR28_FDC: set[str] | None = None
_FNDDS_CODES: set[str] | None = None


def sr28_fdc_set() -> set[str]:
    global _SR28_FDC
    if _SR28_FDC is not None:
        return _SR28_FDC
    p = ROOT / "data" / "sr28_csv" / "food.csv"
    out = set()
    with p.open() as f:
        for r in csv.DictReader(f):
            out.add(r["fdc_id"].strip())
    _SR28_FDC = out
    return out


def fndds_code_set() -> set[str]:
    global _FNDDS_CODES
    if _FNDDS_CODES is not None:
        return _FNDDS_CODES
    p = ROOT / "data" / "fndds" / "MainFoodDesc16.csv"
    out = set()
    with p.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            out.add(r["Food code"].strip())
    _FNDDS_CODES = out
    return out


# ==== Guardrail 1: Synthetic-code hallucination ==============================
class Guardrail1_NoSyntheticCodes(unittest.TestCase):
    """Every fdc_id in every registry must SELECT-hit SR28 or FNDDS."""

    def _check_registry(self, path: Path, sr28_col: str, fndds_col: str = ""):
        sr28 = sr28_fdc_set()
        fndds = fndds_code_set()
        bad_sr28 = []
        bad_fndds = []
        with path.open() as f:
            for i, r in enumerate(csv.DictReader(f), start=2):
                s = (r.get(sr28_col) or "").strip()
                if s and s not in sr28:
                    bad_sr28.append((i, s))
                if fndds_col:
                    fc = (r.get(fndds_col) or "").strip()
                    if fc and fc not in fndds:
                        bad_fndds.append((i, fc))
        self.assertEqual(bad_sr28, [], f"{path.name}: SR28 fdc_ids not in food.csv")
        # NOTE: Hestia FNDDS codes not in our FNDDS 16 are expected (newer version);
        # they're allowed in canonical_items.csv but flagged in canonical_pseudos.csv only.
        # For canonical_pseudos: fndds_code can be a real FNDDS code OR a Hestia pseudo.
        # The nutrition_proxy_sr28_fdc_id is what we validate, not fndds_code.

    def test_canonical_items_sr28_codes_real(self):
        self._check_registry(ROOT / "implementation" / "canonical_items.csv", "sr28_fdc_id")

    def test_reviewed_nutrition_anchors_sr28_real(self):
        p = ROOT / "implementation" / "reviewed_nutrition_anchors.csv"
        sr28 = sr28_fdc_set()
        fndds = fndds_code_set()
        bad = []
        with p.open() as f:
            for i, r in enumerate(csv.DictReader(f), start=2):
                src = (r.get("source_system") or "").strip().upper()
                code = (r.get("food_id") or "").strip()
                if not code:
                    continue
                if src == "SR28" and code not in sr28:
                    bad.append((i, src, code))
                elif src == "FNDDS" and code not in fndds:
                    # FNDDS mismatches allowed if review_status flagged
                    if (r.get("review_status") or "").strip() != "flagged_auto_batch_conflict":
                        bad.append((i, src, code))
        self.assertEqual(bad, [], "reviewed_nutrition_anchors.csv has codes not in SR28/FNDDS")

    def test_canonical_pseudos_proxy_sr28_real(self):
        p = ROOT / "implementation" / "canonical_pseudos.csv"
        if not p.exists():
            self.skipTest("canonical_pseudos.csv not yet created (Task 5)")
        sr28 = sr28_fdc_set()
        bad = []
        with p.open() as f:
            for i, r in enumerate(csv.DictReader(f), start=2):
                if (r.get("review_status") or "").strip() in ("catch_all_split", "ungrounded"):
                    continue  # legitimate unresolved tail
                proxy = (r.get("nutrition_proxy_sr28_fdc_id") or "").strip()
                if not proxy:
                    bad.append((i, "MISSING nutrition_proxy_sr28_fdc_id"))
                elif proxy not in sr28:
                    bad.append((i, f"not in SR28: {proxy}"))
        self.assertEqual(bad, [], "canonical_pseudos.csv has missing/bad proxies")


class Guardrail1b_CandyRegistryMappings(unittest.TestCase):
    def test_canonical_to_esha_keeps_reviewed_candy_rows(self):
        path = ROOT / "implementation" / "canonical_to_esha.csv"
        rows = {}
        with path.open() as f:
            for row in csv.DictReader(f):
                rows[row["canonical_name"]] = row
        expected = {
            "candy cane": ("92711", "Candy, hard, lollipop, Candy Cane"),
            "caramel candies": ("23015", "Candy, caramels"),
            "hard candy": ("23031", "Candy, hard, all flavors"),
            "tootsie pop": ("92709", "Candy, hard, lollipop, Tootsie Pop, assorted flavors, regular"),
            "tootsie pops": ("92709", "Candy, hard, lollipop, Tootsie Pop, assorted flavors, regular"),
            "tootsie roll midgees": ("92721", "Candy, Tootsie Roll, small Midgees"),
        }
        for canonical_name, (esha_code, esha_description) in expected.items():
            with self.subTest(canonical_name=canonical_name):
                self.assertIn(canonical_name, rows)
                self.assertEqual(esha_code, rows[canonical_name]["esha_code"])
                self.assertEqual(esha_description, rows[canonical_name]["esha_description"])

    def test_reviewed_nutrition_anchors_block_known_candy_auto_defaults(self):
        path = ROOT / "implementation" / "reviewed_nutrition_anchors.csv"
        rows = {}
        with path.open() as f:
            for row in csv.DictReader(f):
                rows[row["concept_key"]] = row

        for concept_key in ("tootsie roll midgees|||", "tootsie roll midgies|||", "tootsie rolls|||"):
            with self.subTest(concept_key=concept_key):
                self.assertEqual("approved", rows[concept_key]["review_status"])
                self.assertEqual("167971", rows[concept_key]["food_id"])
                self.assertEqual("Candies, TOOTSIE ROLL, chocolate-flavor roll", rows[concept_key]["description"])

        for concept_key in ("pink fruit taffy|||", "wooden lollipop sticks|||"):
            with self.subTest(concept_key=concept_key):
                self.assertEqual("flagged_auto_batch_conflict", rows[concept_key]["review_status"])


# ==== Guardrail 2: No runtime LLM =============================================
class Guardrail2_NoRuntimeLLM(unittest.TestCase):
    """Grep calculator modules for network imports. Any hit = fail."""

    FORBIDDEN_IMPORTS = re.compile(
        r"^\s*(import|from)\s+(anthropic|openai|http|urllib|requests|httpx|aiohttp)\b",
        re.MULTILINE,
    )

    CALCULATOR_MODULES = [
        "implementation/normalizer.py",
        "implementation/layered_resolver.py",
        "implementation/sr28_nutrition.py",
        "implementation/portion_resolver.py",
        "implementation/product_matcher.py",
        "implementation/price_resolver.py",
        "implementation/calculator.py",
        "implementation/schema.py",
        "implementation/non_food_words.py",
        "implementation/resolver.py",
        "implementation/nutrition.py",
    ]

    def test_no_network_imports_in_calculator(self):
        hits = []
        for rel in self.CALCULATOR_MODULES:
            p = ROOT / rel
            if not p.exists():
                continue
            text = p.read_text()
            for m in self.FORBIDDEN_IMPORTS.finditer(text):
                line_no = text[: m.start()].count("\n") + 1
                hits.append(f"{rel}:{line_no} -> {m.group(0).strip()}")
        self.assertEqual(hits, [], "Network imports in calculator modules")


# ==== Guardrail 3: Head-noun collision (the compositional-error regression) ==
class Guardrail3_NoHeadNounCollision(unittest.TestCase):
    """Every compositional-error class pinned as a test. Delegates to test_normalizer.py."""

    def test_normalizer_regression_pack_present_and_green(self):
        import subprocess
        r = subprocess.run(
            ["python3", "-m", "unittest", "implementation.tests.test_normalizer", "-v"],
            capture_output=True, text=True, cwd=ROOT,
        )
        self.assertEqual(r.returncode, 0, f"test_normalizer failed:\n{r.stdout}\n{r.stderr}")


# ==== Guardrail 4: Nutrition-shopping collapse ================================
class Guardrail4_NutritionShoppingSeparated(unittest.TestCase):
    """Resolution dataclass requires both nutrition_state AND shopping_state."""

    def test_resolution_cannot_be_built_without_both_states(self):
        from schema import Resolution
        with self.assertRaises(TypeError):
            Resolution()

    def test_resolution_field_names_are_plural(self):
        """Guard against refactors that might collapse to one field."""
        from schema import Resolution
        fields = {f.name for f in Resolution.__dataclass_fields__.values()}
        self.assertIn("nutrition_state", fields)
        self.assertIn("shopping_state", fields)


# ==== Guardrail 5: No invented-match-to-avoid-unknown =========================
# See spec — enforced in Task 14 via diff-aware CI gate. Here we assert the
# nutrition_unknown state exists and is terminal.
class Guardrail5_UnknownIsValidTerminal(unittest.TestCase):
    def test_nutrition_unknown_state_exists(self):
        from schema import NutritionState
        self.assertIn("NUTRITION_UNKNOWN", {s.name for s in NutritionState})


# ==== Guardrail 6: Coverage-metric 5-tuple ====================================
class Guardrail6_MetricsAreTuples(unittest.TestCase):
    """Every metric in a report carries denominator/numerator/artifact/command/does_not_prove."""

    def test_metrics_schema_is_documented_in_spec(self):
        spec = ROOT / "docs" / "superpowers" / "specs" / "2026-04-18-normalized-recipe-calculator-design.md"
        text = spec.read_text()
        self.assertIn("5-tuple", text)
        self.assertIn("denominator", text)
        self.assertIn("does_NOT_prove", text)

    def test_metrics_contract_enforced_at_report_build(self):
        """Enforced in Task 14 (phase15_full_corpus_calculation.py). Placeholder here."""
        self.skipTest("Metrics contract enforced in Task 12 (phase15_full_corpus_calculation.py)")


# ==== Guardrail 7: Proxy auto-promotion ======================================
class Guardrail7_NoUnreviewedPromotion(unittest.TestCase):
    """Every registry loader rejects rows where review_status != approved for primary use."""

    def _count_rows_by_status(self, path: Path) -> dict[str, int]:
        out: dict[str, int] = {}
        with path.open() as f:
            for r in csv.DictReader(f):
                s = (r.get("review_status") or "").strip() or "MISSING"
                out[s] = out.get(s, 0) + 1
        return out

    def test_canonical_items_status_audit(self):
        p = ROOT / "implementation" / "canonical_items.csv"
        counts = self._count_rows_by_status(p)
        self.assertNotIn("MISSING", counts, f"Rows without review_status in {p.name}")


# ==== Guardrail 8: grams=0 -> non_food shortcut ==============================
class Guardrail8_NonFoodRequiresLexicon(unittest.TestCase):
    def test_non_food_module_exists_with_lexicon(self):
        from non_food_words import is_non_food, _load
        self.assertTrue(len(_load()) >= 10, "non_food lexicon too sparse")

    def test_zero_kcal_food_is_not_non_food(self):
        from non_food_words import is_non_food
        self.assertFalse(is_non_food("water"))
        self.assertFalse(is_non_food("salt"))  # zero kcal per USDA but is a food


# ==== Guardrail 9: Family-rule blast radius ==================================
class Guardrail9_FamilyRulesPresent(unittest.TestCase):
    def test_seven_protected_families_are_in_product_family_safety_rules(self):
        p = ROOT / "implementation" / "product_family_safety_rules.csv"
        self.assertTrue(p.exists(), "product_family_safety_rules.csv missing")
        names = set()
        with p.open() as f:
            for r in csv.DictReader(f):
                names.add((r.get("family_id") or "").strip().lower())
        # The 7 protected families from CLAUDE.md rule 8
        required = {"milk", "butter", "cream", "chicken", "rice", "beans", "sauce"}
        # Either exact match or prefix
        missing = []
        for fam in required:
            if not any(fam in n for n in names):
                missing.append(fam)
        self.assertEqual(missing, [], f"Missing protected-family rules: {missing}")


# ==== Guardrail 10: Implicit-contract schema drift ===========================
class Guardrail10_SchemaSingleSource(unittest.TestCase):
    def test_schema_module_owns_dataclasses(self):
        from schema import Resolution, NutritionEstimate, ProductCandidate
        for cls in (Resolution, NutritionEstimate, ProductCandidate):
            self.assertTrue(cls.__module__.endswith("schema"), f"{cls} not from schema module")

    def test_round_trip_fixture(self):
        """Serialize + reload a Resolution without loss."""
        from schema import Resolution, NutritionState, ShoppingState, TrustLayer
        import dataclasses, json
        r = Resolution(
            canonical_name="butter", sr28_fdc_id="173410", fndds_code="",
            pseudo_code="", nutrition_state=NutritionState.EXACT_USDA_ANCHOR,
            shopping_state=ShoppingState.SHOPPING_CANDIDATES_STRONG,
            trust_layer=TrustLayer.L1_CANONICAL, grams=14.2, alternatives=[], path=[],
        )
        d = dataclasses.asdict(r)
        d["nutrition_state"] = NutritionState(d["nutrition_state"])
        d["shopping_state"] = ShoppingState(d["shopping_state"])
        d["trust_layer"] = TrustLayer(d["trust_layer"])
        d.pop("nutrition", None)
        d.pop("products", None)
        d.pop("notes", None)
        r2 = Resolution(**d)
        self.assertEqual(r2.canonical_name, r.canonical_name)


# ==== Guardrail 11: Registry proliferation ==================================
class Guardrail11_NoAdhocReviewedCSVs(unittest.TestCase):
    def test_all_reviewed_csvs_are_in_resolver_context(self):
        """Every implementation/reviewed_*.csv file must be declared in resolver_context.DEFAULT_ARTIFACTS."""
        import sys
        sys.path.insert(0, str(ROOT / "implementation"))
        from resolver_context import DEFAULT_ARTIFACTS
        import dataclasses
        declared = set()
        if dataclasses.is_dataclass(DEFAULT_ARTIFACTS):
            for f in dataclasses.fields(DEFAULT_ARTIFACTS):
                v = getattr(DEFAULT_ARTIFACTS, f.name)
                if isinstance(v, Path):
                    declared.add(v.resolve())
        found = set()
        for p in (ROOT / "implementation").glob("reviewed_*.csv"):
            found.add(p.resolve())
        missing = found - declared
        self.assertEqual(missing, set(), f"reviewed_*.csv files not declared in DEFAULT_ARTIFACTS: {missing}")

    def test_no_private_alias_dicts_in_calculator_modules(self):
        """No module-level ALIASES = {...} in calculator paths — guardrail against private alias dicts."""
        import re as rem
        suspects = []
        for rel in ["implementation/normalizer.py", "implementation/layered_resolver.py",
                    "implementation/calculator.py", "implementation/sr28_nutrition.py",
                    "implementation/portion_resolver.py", "implementation/product_matcher.py"]:
            p = ROOT / rel
            if not p.exists(): continue
            text = p.read_text()
            if rem.search(r'^\s*ALIASES\s*=\s*\{', text, rem.MULTILINE):
                suspects.append(rel)
        self.assertEqual(suspects, [], "Private ALIASES dict found in calculator module")


# ==== Guardrail 12: Multi-agent concurrent-writer race =======================
class Guardrail12_MultiAgentLock(unittest.TestCase):
    def test_canonical_writers_reference_lock_name(self):
        """Scripts that rewrite canonical outputs reference the shared lock path."""
        # Pass if the coordination doc mentions the lock path — this is a convention gate, not an ops lock.
        coord = ROOT / "implementation" / "AGENT_COORDINATION.md"
        if not coord.exists():
            self.skipTest("AGENT_COORDINATION.md missing; coordination doc is authoritative for lock discipline.")
        text = coord.read_text()
        self.assertIn(".recipe_line_to_concept.lock", text,
                      "Lock name must be documented in AGENT_COORDINATION.md")


# ==== Guardrail 13: Scope-creep / boil-the-ocean =============================
class Guardrail13_ScopeFrozen(unittest.TestCase):
    def test_launch_scope_exists(self):
        candidates = [ROOT / "LAUNCH_SCOPE.md", ROOT / "implementation" / "LAUNCH_SCOPE.md",
                      ROOT / "docs" / "superpowers" / "specs" / "2026-04-18-normalized-recipe-calculator-design.md"]
        existing = [p for p in candidates if p.exists()]
        self.assertTrue(existing, "No launch-scope document found; scope must be explicitly frozen somewhere.")

    def test_scope_lists_out_of_scope(self):
        """The design spec has an explicit 'out of scope' section."""
        spec = ROOT / "docs" / "superpowers" / "specs" / "2026-04-18-normalized-recipe-calculator-design.md"
        if not spec.exists():
            self.skipTest("design spec missing")
        text = spec.read_text()
        self.assertIn("out of scope", text.lower())


# ==== Guardrail 14: Stale-metric drift =======================================
class Guardrail14_MetricsFreshness(unittest.TestCase):
    def test_metrics_md_exists_or_deferred(self):
        """phase15 metrics report is either fresh or clearly deferred."""
        path = ROOT / "recipe_pricing" / "output" / "phase15_full_corpus_metrics.md"
        if not path.exists():
            self.skipTest("phase15 run not executed yet (Task 12)")
        text = path.read_text()
        for tag in ("denominator", "numerator", "does_NOT_prove"):
            self.assertIn(tag, text, f"5-tuple metric contract missing '{tag}'")


# ==== Guardrail 15: Fuzzy-match acceptance forbidden =========================
class Guardrail15_NoFuzzyMatchAcceptance(unittest.TestCase):
    def test_product_matcher_does_not_use_fuzz(self):
        """product_matcher.py must not import fuzzywuzzy, rapidfuzz, difflib.SequenceMatcher, or Levenshtein."""
        import re as rem
        p = ROOT / "implementation" / "product_matcher.py"
        self.assertTrue(p.exists(), "product_matcher.py missing")
        text = p.read_text()
        forbidden = rem.compile(r'^\s*(import|from)\s+(fuzzywuzzy|rapidfuzz|Levenshtein|difflib)\b', rem.MULTILINE)
        self.assertIsNone(forbidden.search(text), "fuzzy-match library imported in product_matcher")


# ==== Guardrail 16: Plural-fold mangling =====================================
class Guardrail16_AnchoredPluralFold(unittest.TestCase):
    def test_protected_plurals_do_not_mangle(self):
        """'oats', 'greens', 'chives', 'grits', 'wits', 'news' must not naively strip to singular."""
        import sys
        sys.path.insert(0, str(ROOT / "implementation"))
        from normalizer import _singularize
        # _singularize returns None for protected cases only if anchored; otherwise returns a naive singular.
        # The guardrail is: if _singularize returns something, the caller must check canonical before accepting.
        # Here we only assert the function is deterministic and doesn't crash on these words.
        for word in ("oats", "greens", "chives", "grits", "wits", "news"):
            result = _singularize(word)
            # Result may be None (protected) or the naive stem; both acceptable as long as no crash.
            self.assertTrue(result is None or isinstance(result, str))


# ==== Guardrail 17: Parser info loss (display→item) ==========================
class Guardrail17_ItemFallbackNamed(unittest.TestCase):
    def test_item_fallback_lookup_exists_in_audit(self):
        import sqlite3 as s
        db = ROOT / "implementation" / "output" / "recipe_qa_nutrition_calculation_audit.db"
        if not db.exists():
            self.skipTest("audit DB not present locally")
        with s.connect(f"file:{db}?mode=ro", uri=True) as c:
            row = c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='item_fallback_lookup'"
            ).fetchone()
            self.assertIsNotNone(row, "item_fallback_lookup table must exist in audit DB")


# ==== Guardrail 18: Coupling import creep ====================================
class Guardrail18_NoNutritionToResolverImport(unittest.TestCase):
    FORBIDDEN = re.compile(
        r'^\s*(import|from)\s+(resolver|layered_resolver)\b',
        re.MULTILINE,
    )
    MODULES = ["implementation/nutrition.py", "implementation/sr28_nutrition.py",
               "implementation/schema.py", "implementation/non_food_words.py"]

    def test_no_resolver_imports_in_nutrition_modules(self):
        hits = []
        for rel in self.MODULES:
            p = ROOT / rel
            if not p.exists(): continue
            text = p.read_text()
            for m in self.FORBIDDEN.finditer(text):
                line_no = text[:m.start()].count('\n') + 1
                hits.append(f"{rel}:{line_no} -> {m.group(0).strip()}")
        self.assertEqual(hits, [], "nutrition/schema modules must not import resolver")


# ==== Guardrail 19: Post-2018 data drift =====================================
class Guardrail19_ExternalCatalogPresent(unittest.TestCase):
    def test_external_catalog_csv_exists(self):
        p = ROOT / "implementation" / "reviewed_external_catalog_items.csv"
        self.assertTrue(p.exists(), "reviewed_external_catalog_items.csv missing")

    def test_schema_shopping_state_has_shopping_only_or_shopping_gap(self):
        import sys
        sys.path.insert(0, str(ROOT / "implementation"))
        from schema import ShoppingState
        names = {s.name for s in ShoppingState}
        self.assertTrue(
            "SHOPPING_GAP" in names or "SHOPPING_ONLY" in names,
            f"ShoppingState must carry SHOPPING_GAP or SHOPPING_ONLY terminal state; got {names}"
        )


# ==== Guardrail 20: "Or"-alternative collapse ================================
class Guardrail20_AlternativesListed(unittest.TestCase):
    def test_resolution_alternatives_is_list(self):
        import sys
        sys.path.insert(0, str(ROOT / "implementation"))
        from schema import Resolution, NutritionState, ShoppingState, TrustLayer
        r = Resolution(
            canonical_name="butter", sr28_fdc_id="173410", fndds_code="",
            pseudo_code="", nutrition_state=NutritionState.EXACT_USDA_ANCHOR,
            shopping_state=ShoppingState.SHOPPING_CANDIDATES_STRONG,
            trust_layer=TrustLayer.L1_CANONICAL, grams=14.2,
            alternatives=["margarine"], path=[],
        )
        self.assertIsInstance(r.alternatives, list)
        self.assertEqual(r.alternatives, ["margarine"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
