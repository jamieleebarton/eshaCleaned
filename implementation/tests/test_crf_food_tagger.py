"""Unit tests for crf_food_tagger."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from implementation.crf_food_tagger import (
    KNOWN_PREP_WORDS,
    KNOWN_UNITS,
    build_food_vocab_from_concepts,
    concept_base_tokens,
    extract_all_food_spans,
    extract_food_span,
    label_surface_bio,
    predict_labels,
    sequence_features,
    token_features,
    tokenize,
    train_crf,
)


class TestTokenize(unittest.TestCase):
    def test_simple_whitespace(self):
        self.assertEqual(tokenize("chicken breast"), ["chicken", "breast"])

    def test_lowercases(self):
        self.assertEqual(tokenize("Chicken Breast"), ["chicken", "breast"])

    def test_separates_commas_as_tokens(self):
        self.assertEqual(
            tokenize("frozen peas, skip blanching"),
            ["frozen", "peas", ",", "skip", "blanching"],
        )

    def test_preserves_hyphenated_words(self):
        self.assertEqual(tokenize("low-fat milk"), ["low-fat", "milk"])

    def test_preserves_apostrophes(self):
        self.assertEqual(tokenize("m&m's"), ["m", "&", "m's"])

    def test_handles_parens(self):
        self.assertEqual(
            tokenize("chocolate (chopped)"),
            ["chocolate", "(", "chopped", ")"],
        )

    def test_handles_digits(self):
        self.assertEqual(tokenize("1 cup salt"), ["1", "cup", "salt"])

    def test_empty_string(self):
        self.assertEqual(tokenize(""), [])


class TestConceptBaseTokens(unittest.TestCase):
    def test_simple_concept(self):
        self.assertEqual(concept_base_tokens("chicken breast|||"), ["chicken", "breast"])

    def test_concept_with_variant(self):
        self.assertEqual(
            concept_base_tokens("chicken breast|||boneless"), ["chicken", "breast"]
        )

    def test_single_word(self):
        self.assertEqual(concept_base_tokens("salt|||"), ["salt"])

    def test_empty_concept(self):
        self.assertEqual(concept_base_tokens(""), [])

    def test_lowercases(self):
        self.assertEqual(concept_base_tokens("Olive Oil|||"), ["olive", "oil"])


class TestLabelSurfaceBIO(unittest.TestCase):
    def test_contiguous_match(self):
        labels = label_surface_bio(
            ["boneless", "skinless", "chicken", "breast", "halves"],
            ["chicken", "breast"],
        )
        self.assertEqual(labels, ["O", "O", "B-FOOD", "I-FOOD", "O"])

    def test_single_token_food(self):
        labels = label_surface_bio(["kosher", "salt"], ["salt"])
        self.assertEqual(labels, ["O", "B-FOOD"])

    def test_contiguous_match_at_start(self):
        labels = label_surface_bio(
            ["olive", "oil", "extra", "virgin"],
            ["olive", "oil"],
        )
        self.assertEqual(labels, ["B-FOOD", "I-FOOD", "O", "O"])

    def test_no_match_all_O(self):
        labels = label_surface_bio(["completely", "unrelated"], ["chicken"])
        self.assertEqual(labels, ["O", "O"])

    def test_empty_concept_all_O(self):
        labels = label_surface_bio(["some", "tokens"], [])
        self.assertEqual(labels, ["O", "O"])

    def test_empty_surface(self):
        self.assertEqual(label_surface_bio([], ["chicken"]), [])

    def test_fallback_to_subsequence_when_no_contiguous(self):
        labels = label_surface_bio(
            ["chicken", "boneless", "breast"],
            ["chicken", "breast"],
        )
        self.assertEqual(labels, ["B-FOOD", "O", "I-FOOD"])


class TestTokenFeatures(unittest.TestCase):
    def test_basic_features_present(self):
        feats = token_features(
            ["chicken", "breast"], 0, food_vocab={"chicken", "breast"}
        )
        self.assertEqual(feats["word"], "chicken")
        self.assertEqual(feats["suffix3"], "ken")
        self.assertEqual(feats["is_food_vocab"], "1")
        self.assertEqual(feats["BOS"], "1")

    def test_next_token_features(self):
        feats = token_features(
            ["chicken", "breast"], 0, food_vocab={"chicken", "breast"}
        )
        self.assertEqual(feats["+1:word"], "breast")
        self.assertEqual(feats["+1:is_food_vocab"], "1")

    def test_eos_marker(self):
        feats = token_features(
            ["chicken", "breast"], 1, food_vocab={"chicken"}
        )
        self.assertEqual(feats["EOS"], "1")

    def test_unit_detection(self):
        feats = token_features(["cup", "salt"], 0, food_vocab={"salt"})
        self.assertEqual(feats["is_unit"], "1")

    def test_prep_detection(self):
        feats = token_features(["chopped", "onion"], 0, food_vocab={"onion"})
        self.assertEqual(feats["is_prep"], "1")

    def test_digit_shape(self):
        feats = token_features(["1", "cup"], 0, food_vocab=set())
        self.assertEqual(feats["is_digit"], "1")

    def test_punct_shape(self):
        feats = token_features(
            ["salt", ",", "pepper"], 1, food_vocab={"salt", "pepper"}
        )
        self.assertEqual(feats["is_punct"], "1")


class TestSequenceFeatures(unittest.TestCase):
    def test_returns_one_feature_dict_per_token(self):
        seq = sequence_features(["chicken", "breast"], food_vocab={"chicken"})
        self.assertEqual(len(seq), 2)
        self.assertIsInstance(seq[0], dict)


class TestExtractFoodSpan(unittest.TestCase):
    def test_contiguous_span(self):
        tokens = ["boneless", "skinless", "chicken", "breast", "halves"]
        labels = ["O", "O", "B-FOOD", "I-FOOD", "O"]
        self.assertEqual(extract_food_span(tokens, labels), "chicken breast")

    def test_single_token(self):
        tokens = ["kosher", "salt"]
        labels = ["O", "B-FOOD"]
        self.assertEqual(extract_food_span(tokens, labels), "salt")

    def test_no_food(self):
        tokens = ["for", "serving"]
        labels = ["O", "O"]
        self.assertEqual(extract_food_span(tokens, labels), "")

    def test_multiple_spans_returns_longest(self):
        tokens = ["chicken", "or", "ground", "beef"]
        labels = ["B-FOOD", "O", "B-FOOD", "I-FOOD"]
        self.assertEqual(extract_food_span(tokens, labels), "ground beef")

    def test_returns_empty_for_empty_inputs(self):
        self.assertEqual(extract_food_span([], []), "")


class TestExtractAllFoodSpans(unittest.TestCase):
    def test_alternative(self):
        tokens = ["chicken", "or", "beef"]
        labels = ["B-FOOD", "O", "B-FOOD"]
        self.assertEqual(extract_all_food_spans(tokens, labels), ["chicken", "beef"])

    def test_single_span(self):
        tokens = ["ground", "beef"]
        labels = ["B-FOOD", "I-FOOD"]
        self.assertEqual(extract_all_food_spans(tokens, labels), ["ground beef"])

    def test_no_spans(self):
        self.assertEqual(extract_all_food_spans(["a", "b"], ["O", "O"]), [])


class TestBuildFoodVocab(unittest.TestCase):
    def test_extracts_unique_tokens_from_concept_list(self):
        concepts = [
            "chicken breast|||",
            "olive oil|||",
            "salt|||",
            "chicken breast|||boneless",
        ]
        vocab = build_food_vocab_from_concepts(concepts)
        self.assertEqual(vocab, {"chicken", "breast", "olive", "oil", "salt"})

    def test_lowercases(self):
        concepts = ["Chicken Breast|||"]
        vocab = build_food_vocab_from_concepts(concepts)
        self.assertEqual(vocab, {"chicken", "breast"})

    def test_skips_empty_concepts(self):
        vocab = build_food_vocab_from_concepts(["", "salt|||"])
        self.assertEqual(vocab, {"salt"})


class TestTrainAndPredict(unittest.TestCase):
    def test_train_and_predict_roundtrip(self):
        food_vocab = {"chicken", "breast", "salt", "butter"}
        training_pairs = [
            (["boneless", "chicken", "breast"], ["O", "B-FOOD", "I-FOOD"]),
            (["kosher", "salt"], ["O", "B-FOOD"]),
            (["chopped", "chicken", "breast"], ["O", "B-FOOD", "I-FOOD"]),
            (["unsalted", "butter"], ["O", "B-FOOD"]),
            (["fresh", "salt"], ["O", "B-FOOD"]),
            (["skinless", "chicken", "breast"], ["O", "B-FOOD", "I-FOOD"]),
        ] * 20

        with tempfile.TemporaryDirectory() as tmp:
            model_path = Path(tmp) / "model.crfsuite"
            train_crf(training_pairs, model_path, food_vocab=food_vocab, max_iter=30)
            self.assertTrue(model_path.exists())

            labels = predict_labels(
                ["sliced", "chicken", "breast"],
                model_path,
                food_vocab=food_vocab,
            )
            self.assertEqual(len(labels), 3)
            self.assertEqual(labels[1], "B-FOOD")
            self.assertEqual(labels[2], "I-FOOD")


if __name__ == "__main__":
    unittest.main()
