from __future__ import annotations

import sys
import unittest
from pathlib import Path


IMPLEMENTATION_ROOT = Path(__file__).resolve().parents[1]
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

from rft_concept import (  # noqa: E402
    _IDENTITY_TOKENS,
    build_concept_index,
    build_token_to_concepts,
    concept_tokens_from_text,
    route,
)
from rft_scale_concept import apply_category_route_hints  # noqa: E402


class RFTConceptRouterRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.concepts = build_concept_index()
        cls.token_idx = build_token_to_concepts(cls.concepts)

    def _route(self, surface: str) -> dict:
        return route(surface, self.concepts, self.token_idx)

    def test_split_apple_sauce_routes_to_cinnamon_applesauce(self) -> None:
        res = self._route("CINNAMON APPLE SAUCE")
        esha = (res.get("backtracked") or {}).get("esha") or {}

        self.assertEqual(res["verdict"], "EXACT")
        self.assertEqual(res["concept"].concept_id, frozenset({"applesauce", "cinnamon"}))
        self.assertEqual(esha.get("code"), "46799")
        self.assertEqual(esha.get("desc"), "applesauce, cinnamon")

    def test_redundant_apple_and_packaging_do_not_weaken_applesauce(self) -> None:
        res = self._route("APPLE CINNAMON APPLE SAUCE CUPS")
        esha = (res.get("backtracked") or {}).get("esha") or {}

        self.assertEqual(res["verdict"], "EXACT")
        self.assertEqual(res["concept"].concept_id, frozenset({"applesauce", "cinnamon"}))
        self.assertEqual(esha.get("code"), "46799")

    def test_cinnamon_typo_normalizes_for_applesauce(self) -> None:
        res = self._route("CINNANON APPLE SAUCE")
        esha = (res.get("backtracked") or {}).get("esha") or {}

        self.assertEqual(res["verdict"], "EXACT")
        self.assertEqual(esha.get("code"), "46799")

    def test_single_token_plant_milk_expands_to_source_and_milk(self) -> None:
        self.assertEqual(
            concept_tokens_from_text("Silk Oatmilk"),
            frozenset({"oat-milk"}),
        )

    def test_piece_stem_are_facets_not_identity_anchors(self) -> None:
        res = self._route("MUSHROOM PIECES & STEMS")
        esha = (res.get("backtracked") or {}).get("esha") or {}

        self.assertNotIn("piece", _IDENTITY_TOKENS)
        self.assertNotIn("stem", _IDENTITY_TOKENS)
        self.assertEqual(res["verdict"], "STRONG")
        self.assertEqual(esha.get("code"), "6276")
        self.assertEqual(esha.get("desc"), "mushrooms, pieces stems, canned")

    def test_canned_category_hint_recovers_exact_mushroom_piece_leaf(self) -> None:
        surface, hints = apply_category_route_hints(
            "MUSHROOM PIECES & STEMS",
            "Canned Vegetables",
        )
        res = self._route(surface)
        esha = (res.get("backtracked") or {}).get("esha") or {}

        self.assertEqual(hints, ["canned"])
        self.assertEqual(res["verdict"], "EXACT")
        self.assertEqual(esha.get("code"), "6276")

    def test_no_salt_added_does_not_force_salted_mushroom_leaf(self) -> None:
        res = self._route("NO SALT ADDED MUSHROOM PIECES & STEMS CANNED")
        esha = (res.get("backtracked") or {}).get("esha") or {}

        self.assertEqual(res["verdict"], "EXACT")
        self.assertEqual(esha.get("code"), "6276")
        self.assertNotIn("salt", res["concept"].concept_id)


if __name__ == "__main__":
    unittest.main()
