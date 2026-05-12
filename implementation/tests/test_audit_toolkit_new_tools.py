import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "implementation"))

from esha_audit_toolkit import compare_nutrient_fingerprint  # noqa: E402


class CompareNutrientFingerprintTest(unittest.TestCase):
    def test_returns_profile_per_code(self):
        out = compare_nutrient_fingerprint([1, 8000])
        self.assertEqual(len(out["profiles"]), 2)
        codes = {p["esha_code"] for p in out["profiles"]}
        self.assertEqual(codes, {1, 8000})
        for p in out["profiles"]:
            for key in ("kcal_per_100g", "protein_per_100g", "fat_per_100g", "carbs_per_100g"):
                self.assertIn(key, p)

    def test_distance_is_large_for_dissimilar_foods(self):
        out = compare_nutrient_fingerprint([1, 8000])  # milk vs butter
        dist = out["pairwise_euclid"][0]["distance"]
        self.assertGreater(dist, 50.0)

    def test_distance_is_small_for_similar_foods(self):
        # two milk codes should be close (actual whole vs 2% distance ~10.6)
        out = compare_nutrient_fingerprint([1, 2])  # whole vs 2% milk
        dist = out["pairwise_euclid"][0]["distance"]
        self.assertLess(dist, 15.0)

    def test_missing_code_returned_with_null_profile(self):
        out = compare_nutrient_fingerprint([1, 99999999])
        codes = {p["esha_code"]: p for p in out["profiles"]}
        self.assertIsNone(codes[99999999]["kcal_per_100g"])


from esha_audit_toolkit import recipe_context  # noqa: E402


class RecipeContextTest(unittest.TestCase):
    def test_returns_title_and_siblings(self):
        # 403484 is the White Chocolate Cheesecake recipe in CLAUDE.md
        out = recipe_context(403484)
        self.assertTrue(out["ok"])
        self.assertIn("clean_title", out)
        self.assertIsInstance(out["ingredients"], list)
        self.assertGreater(len(out["ingredients"]), 0)
        for ing in out["ingredients"]:
            self.assertIn("display", ing)
            self.assertIn("item", ing)

    def test_returns_ok_false_for_missing_recipe(self):
        out = recipe_context(99999999999)
        self.assertFalse(out["ok"])


from esha_audit_toolkit import prior_decisions  # noqa: E402


class PriorDecisionsTest(unittest.TestCase):
    def test_known_canonical_returns_entries(self):
        out = prior_decisions("butter")
        self.assertIn("approved_normalization_rules", out)
        self.assertIn("canonical_items", out)
        self.assertIn("canonical_to_esha", out)
        self.assertIn("reviewed_nutrition_anchors", out)
        hits = sum(1 for v in out.values() if isinstance(v, list) and v)
        self.assertGreater(hits, 0)

    def test_unknown_canonical_returns_empty_lists(self):
        out = prior_decisions("zzzzzz_not_a_real_ingredient_xyz")
        for v in out.values():
            if isinstance(v, list):
                self.assertEqual(v, [])


import subprocess
import time
import urllib.parse
import urllib.request


class AuditApiEndpointsTest(unittest.TestCase):
    server_proc = None
    port = 18765  # non-default to avoid colliding with a dev server

    @classmethod
    def setUpClass(cls):
        cls.server_proc = subprocess.Popen(
            [sys.executable, "implementation/esha_audit_api.py", "--port", str(cls.port)],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(40):
            if cls.server_proc.poll() is not None:
                out, err = cls.server_proc.communicate()
                detail = f"{out}\n{err}"
                if "PermissionError" in detail or "Operation not permitted" in detail:
                    raise unittest.SkipTest("sandbox disallows binding a local HTTP server")
                raise RuntimeError(f"audit api exited early:\n{detail}")
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{cls.port}/health", timeout=1
                ) as r:
                    if r.status == 200:
                        return
            except Exception as exc:
                if "Operation not permitted" in str(exc):
                    cls.server_proc.terminate()
                    try:
                        cls.server_proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        cls.server_proc.kill()
                    raise unittest.SkipTest("sandbox disallows loopback HTTP probes")
                time.sleep(0.25)
        cls.server_proc.terminate()
        raise RuntimeError("audit api did not start")

    @classmethod
    def tearDownClass(cls):
        if cls.server_proc:
            cls.server_proc.terminate()
            try:
                cls.server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.server_proc.kill()

    def _get(self, path: str, params: dict) -> dict:
        import json as _json
        qs = urllib.parse.urlencode(params)
        with urllib.request.urlopen(
            f"http://127.0.0.1:{self.port}{path}?{qs}", timeout=5
        ) as r:
            return _json.loads(r.read())

    def test_nutrient_compare_endpoint(self):
        out = self._get("/nutrient-compare", {"codes": "1,8000"})
        self.assertEqual(len(out["profiles"]), 2)
        self.assertGreater(out["pairwise_euclid"][0]["distance"], 50.0)

    def test_recipe_context_endpoint(self):
        out = self._get("/recipe-context", {"recipe_id": 403484})
        self.assertTrue(out["ok"])
        self.assertIn("ingredients", out)

    def test_prior_decisions_endpoint(self):
        out = self._get("/prior-decisions", {"normalized_item": "butter"})
        self.assertEqual(out["normalized_item"], "butter")
        self.assertIn("canonical_items", out)


if __name__ == "__main__":
    unittest.main()
