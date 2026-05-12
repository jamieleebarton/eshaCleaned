# implementation/tests/test_signature_dataclasses.py
import unittest
from implementation.canonical_signature.signature import CanonicalSignature, MatchTrace


class SignatureDataclassTests(unittest.TestCase):
    def test_signature_equality_is_structural(self):
        a = CanonicalSignature(head_noun="applesauce", modifiers=frozenset({"cinnamon"}))
        b = CanonicalSignature(head_noun="applesauce", modifiers=frozenset({"cinnamon"}))
        self.assertEqual(a, b)

    def test_signature_is_hashable(self):
        s = CanonicalSignature(head_noun="apple", modifiers=frozenset())
        {s}  # must not raise

    def test_signature_default_fields_are_none(self):
        s = CanonicalSignature(head_noun="apple", modifiers=frozenset())
        self.assertIsNone(s.form)
        self.assertIsNone(s.state)
        self.assertIsNone(s.flavor)
        self.assertIsNone(s.style)
        self.assertFalse(s.composite)
        self.assertEqual(s.secondary_ingredients, ())

    def test_match_trace_carries_all_provenance_fields(self):
        t = MatchTrace(
            match_layer="L4_lexical",
            stripped_brand="NATURE'S PLACE",
            stripped_fluff=("organic", "fresh"),
            extracted_attributes={"form": "sliced"},
            residual="apples",
            top_candidates=(("apple_raw", 0.91), ("apple_cooked", 0.42)),
            match_confidence=0.91,
            match_reason="char-ngram exact head match",
        )
        self.assertEqual(t.match_layer, "L4_lexical")
        self.assertEqual(t.match_confidence, 0.91)
