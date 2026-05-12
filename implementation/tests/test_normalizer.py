"""Regression pack for the canonical-item normalizer.

Every compositional bug we've hit must be pinned here. The bar: the
normalizer never silently produces a head-noun error. If it can't resolve,
it returns None.
"""
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from normalizer import Normalizer, _normalize_text, _singularize


class NormalizerTextUtilsTests(unittest.TestCase):
    def test_normalize_lowercases(self):
        self.assertEqual('peanut butter', _normalize_text('Peanut Butter'))

    def test_normalize_collapses_whitespace(self):
        self.assertEqual('peanut butter', _normalize_text('  Peanut   Butter  '))

    def test_normalize_hyphens_to_spaces(self):
        self.assertEqual('all purpose flour', _normalize_text('all-purpose flour'))

    def test_normalize_strips_punct(self):
        self.assertEqual('salt', _normalize_text('salt,'))

    def test_singularize_regular(self):
        self.assertEqual('peanut', _singularize('peanuts'))

    def test_singularize_ies(self):
        self.assertEqual('berry', _singularize('berries'))

    def test_singularize_xes(self):
        self.assertEqual('box', _singularize('boxes'))

    def test_singularize_too_short_returns_none(self):
        self.assertIsNone(_singularize('is'))


class NormalizerCompositionalTests(unittest.TestCase):
    """The no-head-noun-errors regression pack."""
    @classmethod
    def setUpClass(cls):
        cls.norm = Normalizer()

    def assertNotResolvesTo(self, text, forbidden, msg=None):
        """Normalizer must NOT map `text` to `forbidden`."""
        r = self.norm.normalize(text)
        self.assertNotEqual(forbidden, r.canonical,
            msg or f'{text!r} silently resolved to {forbidden!r} via {r.path}')

    def test_peanut_butter_not_butter(self):
        self.assertNotResolvesTo('crunchy peanut butter', 'butter')
        self.assertNotResolvesTo('smooth peanut butter', 'butter')
        self.assertNotResolvesTo('natural peanut butter', 'butter')

    def test_butter_peas_not_butter(self):
        self.assertNotResolvesTo('butter peas', 'butter')

    def test_coffee_beans_not_kidney_beans(self):
        self.assertNotResolvesTo('coffee beans', 'beans')
        # If coffee beans isn't a canonical key, should be None, not 'beans'
        r = self.norm.normalize('coffee beans')
        if r.canonical is not None:
            self.assertIn('coffee', r.canonical,
                f'coffee beans resolved to {r.canonical!r}; must contain coffee')

    def test_instant_coffee_roast_not_beef_roast(self):
        r = self.norm.normalize('instant coffee, original roast')
        if r.canonical is not None:
            self.assertIn('coffee', r.canonical,
                f'instant coffee roast resolved to {r.canonical!r}')
            self.assertNotIn('beef', r.canonical)

    def test_bagel_chips_not_bagel(self):
        r = self.norm.normalize('bagel chips')
        if r.canonical is not None:
            # bagel chips could be a canonical key; if it maps to plain bagel
            # that would be a compositional error
            self.assertIn('chip', r.canonical,
                f'bagel chips resolved to {r.canonical!r}; must contain "chip"')

    def test_caesar_salad_dressing_not_salad(self):
        self.assertNotResolvesTo('caesar salad dressing', 'salad')
        self.assertNotResolvesTo('caesar salad dressing', 'caesar salad')

    def test_milk_chocolate_not_milk(self):
        # Explicit project ban documented in registries.py
        self.assertNotResolvesTo('milk chocolate', 'milk')
        self.assertNotResolvesTo('milk chocolate chips', 'milk')

    def test_oil_to_brush_not_bread(self):
        r = self.norm.normalize('oil, to brush the bread')
        if r.canonical is not None:
            self.assertNotIn('bread', r.canonical,
                f'oil to brush bread resolved to {r.canonical!r}')

    def test_artichoke_hearts_in_oil_not_oil(self):
        r = self.norm.normalize('artichoke hearts in oil')
        if r.canonical is not None:
            self.assertIn('artichoke', r.canonical,
                f'artichoke hearts in oil resolved to {r.canonical!r}')

    def test_tuna_in_water_not_water(self):
        r = self.norm.normalize('canned light tuna in water')
        if r.canonical is not None:
            self.assertIn('tuna', r.canonical,
                f'tuna in water resolved to {r.canonical!r}')

    def test_sardines_in_olive_oil_not_oil(self):
        r = self.norm.normalize('sardines in olive oil')
        if r.canonical is not None:
            self.assertIn('sardine', r.canonical,
                f'sardines in olive oil resolved to {r.canonical!r}')

    def test_bread_baking_soda_not_bread(self):
        r = self.norm.normalize('bread baking soda')
        if r.canonical is not None:
            self.assertIn('baking soda', r.canonical,
                f'bread baking soda resolved to {r.canonical!r}')

    def test_corn_oil_butter_not_butter(self):
        # Recipe line: "corn oil butter" — likely "corn oil" or a butter-oil blend
        # Must not drop to just "butter"
        self.assertNotResolvesTo('corn oil butter', 'butter')

    def test_garlic_in_oil_not_oil(self):
        r = self.norm.normalize('garlic in oil')
        if r.canonical is not None:
            self.assertIn('garlic', r.canonical,
                f'garlic in oil resolved to {r.canonical!r}')


class NormalizerHappyPathTests(unittest.TestCase):
    """These are things the normalizer SHOULD resolve correctly."""
    @classmethod
    def setUpClass(cls):
        cls.norm = Normalizer()

    def test_salt_exact(self):
        r = self.norm.normalize('salt')
        self.assertEqual('salt', r.canonical)
        self.assertIn(r.confidence, ('exact','alias'))

    def test_butter_exact(self):
        r = self.norm.normalize('butter')
        self.assertEqual('butter', r.canonical)

    def test_garlic_exact(self):
        r = self.norm.normalize('garlic')
        self.assertEqual('garlic', r.canonical)

    def test_butter_unsalted_resolves_to_butter_variant(self):
        r = self.norm.normalize('butter, unsalted')
        # Either 'butter' (stripped) or 'unsalted butter'/'butter unsalted' is acceptable;
        # the nutrition is different so if a compound canonical exists, prefer it.
        self.assertIsNotNone(r.canonical)
        self.assertIn('butter', r.canonical)

    def test_fresh_mozzarella_strips_to_mozzarella(self):
        r = self.norm.normalize('fresh mozzarella cheese')
        if r.canonical is not None:
            self.assertIn('mozzarella', r.canonical)

    def test_unknown_returns_none(self):
        # Nonsense compound — should fail closed, not guess
        r = self.norm.normalize('ziblorkian qqzooblofruit')
        self.assertIsNone(r.canonical)


if __name__ == '__main__':
    unittest.main()
