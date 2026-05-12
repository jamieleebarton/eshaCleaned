import csv
import tempfile
import unittest
from pathlib import Path

from implementation.local_label_miner import (
    ParentConcept,
    build_parent_dict,
    extract_modifiers,
    find_nearest_parent,
    run_local_label_miner,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


class TestBuildParentDict(unittest.TestCase):
    def test_builds_parent_dict_from_sr28(self):
        parents = build_parent_dict(
            sr28_csv=FIXTURE_DIR / "sr28_sample.csv",
            fndds_csv=None,
            supplemental_csv=None,
            phase1_csv=None,
        )
        self.assertIn("ice cream", parents)
        self.assertEqual(parents["ice cream"].source, "SR28")
        self.assertTrue(parents["ice cream"].anchor_code)
        self.assertIn("paprika", parents)
        self.assertEqual(parents["paprika"].source, "SR28")
        self.assertIn("cinnamon", parents)

    def test_spice_prefix_stripped(self):
        parents = build_parent_dict(
            sr28_csv=FIXTURE_DIR / "sr28_sample.csv",
            fndds_csv=None,
            supplemental_csv=None,
            phase1_csv=None,
        )
        # Should have key 'paprika' (not 'spices'), because of spice prefix strip
        self.assertIn("paprika", parents)
        self.assertNotIn("spices", parents)


class TestFindNearestParent(unittest.TestCase):
    def setUp(self):
        self.parents = {
            "ice cream": ParentConcept(
                phrase="ice cream",
                source="SR28",
                anchor_code="167575",
                anchor_description="Ice creams, vanilla",
            ),
            "cream": ParentConcept(
                phrase="cream",
                source="SR28",
                anchor_code="9999",
                anchor_description="Cream, fluid",
            ),
            "paprika": ParentConcept(
                phrase="paprika",
                source="SR28",
                anchor_code="171323",
                anchor_description="Spices, paprika",
            ),
        }

    def test_finds_longest_suffix_parent(self):
        parent = find_nearest_parent(
            "mint chocolate chip ice cream", self.parents
        )
        self.assertIsNotNone(parent)
        self.assertEqual(parent.phrase, "ice cream")

    def test_prefers_longer_phrase_over_shorter(self):
        parent = find_nearest_parent("vanilla ice cream", self.parents)
        self.assertEqual(parent.phrase, "ice cream")

    def test_exact_match(self):
        parent = find_nearest_parent("paprika", self.parents)
        self.assertEqual(parent.phrase, "paprika")

    def test_no_match_returns_none(self):
        parent = find_nearest_parent("exotic mystery food", self.parents)
        self.assertIsNone(parent)


class TestExtractModifiers(unittest.TestCase):
    def test_removes_parent_tokens_from_base(self):
        mods = extract_modifiers(
            "mint chocolate chip ice cream", "ice cream"
        )
        self.assertEqual(mods, ["mint", "chocolate", "chip"])

    def test_modifiers_preserve_order(self):
        mods = extract_modifiers("smoked paprika", "paprika")
        self.assertEqual(mods, ["smoked"])

    def test_empty_when_base_equals_parent(self):
        mods = extract_modifiers("paprika", "paprika")
        self.assertEqual(mods, [])


class TestRunLocalLabelMiner(unittest.TestCase):
    def test_end_to_end_emits_paired_csvs(self):
        with tempfile.TemporaryDirectory() as td:
            outdir = Path(td)
            run_local_label_miner(
                misses_csv=FIXTURE_DIR / "misses_local_sample.csv",
                sr28_csv=FIXTURE_DIR / "sr28_sample.csv",
                fndds_csv=None,
                supplemental_csv=None,
                phase1_csv=None,
                out_dir=outdir,
                min_recipe_count=5,
            )
            concepts = list(
                csv.DictReader(open(outdir / "proposed_local_label_concepts.csv"))
            )
            rules = list(
                csv.DictReader(open(outdir / "proposed_local_label_rules.csv"))
            )
            contracts = list(
                csv.DictReader(open(outdir / "proposed_local_label_contracts.csv"))
            )
            unmatched = list(
                csv.DictReader(open(outdir / "local_label_unmatched.csv"))
            )

            # Expected proposals
            paprika_concepts = [
                c for c in concepts if c["parent_concept_phrase"] == "paprika"
            ]
            self.assertEqual(len(paprika_concepts), 1)
            self.assertIn("smoked", paprika_concepts[0]["distinguishing_modifiers"])
            self.assertEqual(paprika_concepts[0]["trust_state"], "reviewed_local_label_anchor")
            self.assertEqual(
                paprika_concepts[0]["nutrition_state"], "reviewed_local_label_anchor"
            )

            ice_cream_concepts = [
                c for c in concepts if c["parent_concept_phrase"] == "ice cream"
            ]
            # Mint choc chip + cookies and cream; "vanilla ice cream or whipped cream" skipped
            self.assertEqual(len(ice_cream_concepts), 2)
            mint = next(
                c for c in ice_cream_concepts if "mint" in c["distinguishing_modifiers"]
            )
            self.assertIn("chocolate", mint["distinguishing_modifiers"])
            self.assertIn("chip", mint["distinguishing_modifiers"])

            # Paired CSVs match concepts
            self.assertGreaterEqual(len(rules), 3)
            self.assertGreaterEqual(len(contracts), 3)

            # Unmatched: exotic mystery food (low recipe count is below threshold)
            unmatched_surfaces = [u["normalized_base_food"] for u in unmatched]
            self.assertIn("exotic mystery food", unmatched_surfaces)
            self.assertNotIn("low recipe count thing", unmatched_surfaces)

    def test_skips_alternatives(self):
        with tempfile.TemporaryDirectory() as td:
            outdir = Path(td)
            run_local_label_miner(
                misses_csv=FIXTURE_DIR / "misses_local_sample.csv",
                sr28_csv=FIXTURE_DIR / "sr28_sample.csv",
                fndds_csv=None,
                supplemental_csv=None,
                phase1_csv=None,
                out_dir=outdir,
                min_recipe_count=5,
            )
            concepts = list(
                csv.DictReader(open(outdir / "proposed_local_label_concepts.csv"))
            )
            # "vanilla ice cream or whipped cream" must NOT produce a proposal
            for c in concepts:
                self.assertNotIn(" or ", c["source_miss_surface"])

    def test_sibling_forbidden(self):
        with tempfile.TemporaryDirectory() as td:
            outdir = Path(td)
            run_local_label_miner(
                misses_csv=FIXTURE_DIR / "misses_local_sample.csv",
                sr28_csv=FIXTURE_DIR / "sr28_sample.csv",
                fndds_csv=None,
                supplemental_csv=None,
                phase1_csv=None,
                out_dir=outdir,
                min_recipe_count=5,
            )
            concepts = list(
                csv.DictReader(open(outdir / "proposed_local_label_concepts.csv"))
            )
            mint = next(
                c
                for c in concepts
                if c["parent_concept_phrase"] == "ice cream"
                and "mint" in c["distinguishing_modifiers"]
            )
            forbidden = mint["forbidden_tokens"]
            # Mint's forbidden = sibling (cookies and cream) modifiers
            self.assertIn("cookies", forbidden)
            self.assertIn("and", forbidden)
            self.assertIn("cream", forbidden)


class TestSeedParentIntegration(unittest.TestCase):
    def _write_seed_csv(self, rows: str) -> Path:
        tf = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
        tf.write(
            "phrase,family,anchor_system,anchor_code,anchor_description,notes\n"
        )
        tf.write(rows)
        tf.close()
        return Path(tf.name)

    def test_loads_seed_parents_from_csv(self):
        from implementation.local_label_miner import _load_seed_parents

        path = self._write_seed_csv(
            'garam masala,spice_blend,SR28,171329,"Spices, mixed",blend\n'
            'kosher salt,salt,SR28,173468,"Salt, table",flaked\n'
        )
        parents = _load_seed_parents(path)
        self.assertEqual(len(parents), 2)
        gm = next(p for p in parents if p.phrase == "garam masala")
        self.assertEqual(gm.source, "SEED")
        self.assertEqual(gm.anchor_code, "171329")
        self.assertEqual(gm.anchor_description, "Spices, mixed")

    def test_seed_parent_matches_unmatched_surface(self):
        parents = {
            "garam masala": ParentConcept(
                phrase="garam masala",
                source="SEED",
                anchor_code="171329",
                anchor_description="Spices, mixed",
            )
        }
        parent = find_nearest_parent("garam masala paste", parents)
        self.assertIsNotNone(parent)
        self.assertEqual(parent.phrase, "garam masala")
        mods = extract_modifiers("garam masala paste", parent.phrase)
        self.assertEqual(mods, ["paste"])

    def test_seed_parent_phrase_is_lowercased(self):
        from implementation.local_label_miner import _load_seed_parents

        path = self._write_seed_csv('Kosher Salt,salt,SR28,173468,"Salt, table",\n')
        parents = _load_seed_parents(path)
        self.assertEqual(parents[0].phrase, "kosher salt")

    def test_build_parent_dict_includes_seed(self):
        path = self._write_seed_csv(
            'garam masala,spice_blend,SR28,171329,"Spices, mixed",blend\n'
        )
        parents = build_parent_dict(
            sr28_csv=None,
            fndds_csv=None,
            supplemental_csv=None,
            phase1_csv=None,
            seed_parents_csv=path,
        )
        self.assertIn("garam masala", parents)
        self.assertEqual(parents["garam masala"].source, "SEED")

    def test_seed_defers_to_sr28(self):
        # SR28 fixture has 'paprika'; seed has 'paprika' too. SR28 must win.
        path = self._write_seed_csv(
            'paprika,spice_blend,SR28,999999,"Seed paprika",\n'
        )
        parents = build_parent_dict(
            sr28_csv=FIXTURE_DIR / "sr28_sample.csv",
            fndds_csv=None,
            supplemental_csv=None,
            phase1_csv=None,
            seed_parents_csv=path,
        )
        self.assertIn("paprika", parents)
        self.assertEqual(parents["paprika"].source, "SR28")

    def test_seed_beats_phase1(self):
        # Write a small phase1 CSV with same phrase as seed; seed must win.
        tf = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
        tf.write("base,raw_description\n")
        tf.write("garam masala,garam masala phase1\n")
        tf.close()
        phase1_path = Path(tf.name)

        seed_path = self._write_seed_csv(
            'garam masala,spice_blend,SR28,171329,"Spices, mixed",blend\n'
        )
        parents = build_parent_dict(
            sr28_csv=None,
            fndds_csv=None,
            supplemental_csv=None,
            phase1_csv=phase1_path,
            seed_parents_csv=seed_path,
        )
        self.assertEqual(parents["garam masala"].source, "SEED")


if __name__ == "__main__":
    unittest.main()
