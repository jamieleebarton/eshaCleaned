from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Sequence

from .signature import CanonicalSignature, MatchTrace
from .vocabularies import Vocabularies
from .normalizer import normalize
from .brand_stripper import strip_brand
from .attribute_extractor import extract_attributes
from .lexical_matcher import LexicalMatcher
from .embedding_matcher import EmbeddingMatcher
from .disambiguator import CanonicalCandidate, disambiguate
from .composite_router import is_composite, route_composite

LEXICAL_THRESHOLD = 0.55
TOP_K_LEXICAL = 5
TOP_K_EMBED_POOL = 50


@dataclass(frozen=True)
class ProductRow:
    description: str
    brand_name: Optional[str] = None
    brand_owner: Optional[str] = None
    branded_food_category: Optional[str] = None


CanonicalCorpusRow = tuple[str, str, Optional[str], Optional[str], Optional[str], Optional[str]]


@dataclass
class CanonicalSignaturePipeline:
    vocab: Vocabularies
    category_to_anchor: dict[str, str]
    canonical_index: dict[str, CanonicalCandidate]
    lexical: LexicalMatcher
    embedder: Optional[EmbeddingMatcher]

    @classmethod
    def build(
        cls,
        canonical_rows: Sequence[CanonicalCorpusRow],
        vocab: Vocabularies,
        category_to_anchor: dict[str, str],
        *,
        with_embeddings: bool = False,
    ) -> "CanonicalSignaturePipeline":
        idx: dict[str, CanonicalCandidate] = {}
        corpus: list[tuple[str, str]] = []
        for cid, text, form, state, flavor, style in canonical_rows:
            idx[cid] = CanonicalCandidate(id=cid, form=form, state=state,
                                          flavor=flavor, style=style)
            corpus.append((cid, text))
        lex = LexicalMatcher.fit(corpus)
        emb = EmbeddingMatcher.fit(corpus) if with_embeddings else None
        return cls(vocab=vocab, category_to_anchor=category_to_anchor,
                   canonical_index=idx, lexical=lex, embedder=emb)

    def process(self, row: ProductRow) -> tuple[CanonicalSignature, MatchTrace, Optional[str]]:
        norm = normalize(row.description)
        residual_after_brand, brand = strip_brand(
            norm, brand_name=row.brand_name, brand_owner=row.brand_owner,
            brand_vocabulary=self.vocab.brand_vocabulary,
        )
        ext = extract_attributes(
            residual_after_brand,
            fluff=self.vocab.fluff_tokens | self.vocab.noise_tokens,
            flavors=self.vocab.flavor_vocabulary,
            forms=self.vocab.form_vocabulary,
            states=self.vocab.state_vocabulary,
            styles=self.vocab.style_vocabulary,
            packaging=self.vocab.packaging_vocabulary,
        )
        # Override extractor's naive rightmost-token head with the rightmost
        # token that's actually a known canonical head — falls back to extractor's
        # value if no residual token is in the canonical vocab.
        ext = self._refine_head_noun(ext)

        composite_flag = is_composite(norm)

        if composite_flag:
            routing = route_composite(
                row.description,
                branded_food_category=row.branded_food_category,
                category_to_anchor=self.category_to_anchor,
            )
            sig = CanonicalSignature(
                head_noun=ext.head_noun, modifiers=frozenset(),
                form=ext.form, state=ext.state, flavor=ext.flavor, style=ext.style,
                composite=True,
                secondary_ingredients=routing.detected_secondary,
            )
            trace = MatchTrace(
                match_layer=routing.layer,
                stripped_brand=brand,
                stripped_fluff=ext.fluff_stripped,
                extracted_attributes=self._attr_dict(ext),
                residual=ext.residual,
                top_candidates=((routing.anchor_id, 1.0),) if routing.anchor_id else (),
                match_confidence=1.0 if routing.anchor_id else 0.0,
                match_reason=("category lookup hit" if routing.anchor_id
                              else "composite, no category mapping"),
            )
            return sig, trace, routing.anchor_id

        lex_results = self.lexical.match(ext.residual, k=TOP_K_LEXICAL)
        if not lex_results:
            sig = CanonicalSignature(
                head_noun=ext.head_noun, modifiers=frozenset(),
                form=ext.form, state=ext.state, flavor=ext.flavor, style=ext.style,
            )
            trace = MatchTrace(
                match_layer="unmatched",
                stripped_brand=brand,
                stripped_fluff=ext.fluff_stripped,
                extracted_attributes=self._attr_dict(ext),
                residual=ext.residual,
                top_candidates=(),
                match_confidence=0.0,
                match_reason="empty residual or no lexical hits",
            )
            return sig, trace, None

        layer = "L4_lexical"
        if lex_results[0][1] < LEXICAL_THRESHOLD and self.embedder is not None:
            pool = [c for c, _ in self.lexical.match(ext.residual, k=TOP_K_EMBED_POOL)]
            embed_results = self.embedder.rerank(ext.residual, pool, k=TOP_K_LEXICAL)
            if embed_results:
                lex_results = embed_results
                layer = "L5_embedding"

        annotated = [(self.canonical_index[cid], score) for cid, score in lex_results
                     if cid in self.canonical_index]
        if not annotated:
            return self._unmatched(ext, brand)

        winner = disambiguate(
            annotated,
            product_form=ext.form, product_state=ext.state,
            product_flavor=ext.flavor, product_style=ext.style,
        )
        winner_score = next(s for c, s in lex_results if c == winner.id)
        if layer == "L4_lexical" and len(lex_results) > 1:
            layer = "L6_disambiguated" if winner.id != lex_results[0][0] else "L4_lexical"

        sig = CanonicalSignature(
            head_noun=ext.head_noun,
            modifiers=frozenset(filter(None, (ext.flavor, ext.form, ext.state, ext.style))),
            form=ext.form, state=ext.state, flavor=ext.flavor, style=ext.style,
            composite=False,
        )
        trace = MatchTrace(
            match_layer=layer,
            stripped_brand=brand,
            stripped_fluff=ext.fluff_stripped,
            extracted_attributes=self._attr_dict(ext),
            residual=ext.residual,
            top_candidates=tuple(lex_results[:3]),
            match_confidence=winner_score,
            match_reason=f"{layer}: {winner.id} won by attribute overlap and lexical score",
        )
        return sig, trace, winner.id

    def _attr_dict(self, ext) -> dict:
        return {"form": ext.form, "state": ext.state, "flavor": ext.flavor,
                "style": ext.style, "packaging": ext.packaging}

    def _refine_head_noun(self, ext):
        """Pick rightmost residual token that's a known canonical head; fall back
        to extractor's rightmost-token choice. Prevents leftover noise like product
        codes or runaway modifiers from winning the head_noun slot."""
        from .attribute_extractor import ExtractionResult
        if not ext.residual or not self.vocab.canonical_head_tokens:
            return ext
        tokens = ext.residual.split()
        for tok in reversed(tokens):
            if tok in self.vocab.canonical_head_tokens:
                if tok == ext.head_noun:
                    return ext
                return ExtractionResult(
                    residual=ext.residual, head_noun=tok,
                    fluff_stripped=ext.fluff_stripped,
                    form=ext.form, state=ext.state, flavor=ext.flavor,
                    style=ext.style, packaging=ext.packaging,
                )
        return ext

    def _unmatched(self, ext, brand) -> tuple[CanonicalSignature, MatchTrace, None]:
        sig = CanonicalSignature(
            head_noun=ext.head_noun, modifiers=frozenset(),
            form=ext.form, state=ext.state, flavor=ext.flavor, style=ext.style,
        )
        trace = MatchTrace(
            match_layer="unmatched",
            stripped_brand=brand,
            stripped_fluff=ext.fluff_stripped,
            extracted_attributes=self._attr_dict(ext),
            residual=ext.residual,
            top_candidates=(),
            match_confidence=0.0,
            match_reason="no candidate survived disambiguation",
        )
        return sig, trace, None
