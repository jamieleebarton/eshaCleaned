from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import match_esha_to_products as matcher


@dataclass(frozen=True)
class ProductFacts:
    description: str
    category: str
    description_norm: str
    category_norm: str
    description_tokens: frozenset[str]
    category_tokens: frozenset[str]
    ingredients: str = ""
    ingredients_norm: str = ""
    ingredients_tokens: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_row(cls, row: matcher.ProductRow) -> "ProductFacts":
        return cls.from_components(row.description, row.category, row.ingredients)

    @classmethod
    def from_components(cls, description: str, category: str, ingredients: str = "") -> "ProductFacts":
        description_norm = matcher.normalize_text(description)
        category_norm = matcher.normalize_text(category)
        ingredients_norm = matcher.normalize_text(ingredients)
        return cls(
            description=description,
            category=category,
            description_norm=description_norm,
            category_norm=category_norm,
            description_tokens=frozenset(matcher.tokens_for(description)),
            category_tokens=frozenset(matcher.tokens_for(category)),
            ingredients=ingredients,
            ingredients_norm=ingredients_norm,
            ingredients_tokens=frozenset(matcher.tokens_for(ingredients)),
        )

    def has_any(self, *terms: str) -> bool:
        return any(term in self.description_tokens for term in terms)

    def has_all(self, *terms: str) -> bool:
        return all(term in self.description_tokens for term in terms)

    def has_phrase(self, phrase: str) -> bool:
        return matcher.has_phrase(self.description_norm, phrase)

    def ingredients_have_any(self, *terms: str) -> bool:
        return any(term in self.ingredients_tokens for term in terms)

    def ingredients_have_phrase(self, phrase: str) -> bool:
        return matcher.has_phrase(self.ingredients_norm, phrase)

    def category_has_any(self, *terms: str) -> bool:
        return any(term in self.category_tokens or matcher.has_phrase(self.category_norm, term) for term in terms)


@dataclass(frozen=True)
class MatchDecision:
    status: str
    reason: str


@dataclass(frozen=True)
class ContractSpec:
    esha_code: str
    esha_description: str
    allowed_categories: tuple[str, ...]
    search_terms: tuple[str, ...]
    required_terms: tuple[str, ...]
    exclude_terms: tuple[str, ...]
    exclude_phrases: tuple[str, ...] = ()
    required_phrases: tuple[str, ...] = ()


ContractFn = Callable[[ProductFacts], MatchDecision]


def accept(reason: str) -> MatchDecision:
    return MatchDecision("accept", reason)


def reject(reason: str) -> MatchDecision:
    return MatchDecision("reject", reason)


def todo(reason: str) -> MatchDecision:
    return MatchDecision("todo", reason)


def match_spec(product: ProductFacts, spec: ContractSpec) -> MatchDecision:
    if spec.allowed_categories and not product.category_has_any(*spec.allowed_categories):
        return reject(f"{spec.esha_code} category mismatch")
    missing = [term for term in spec.required_terms if term not in product.description_tokens]
    if missing:
        return reject(f"{spec.esha_code} missing required term(s): " + "|".join(missing))
    missing_phrases = [phrase for phrase in spec.required_phrases if not product.has_phrase(phrase)]
    if missing_phrases:
        return reject(f"{spec.esha_code} missing required phrase(s): " + "|".join(missing_phrases))
    excluded = [term for term in spec.exclude_terms if term in product.description_tokens]
    if excluded:
        return reject(f"{spec.esha_code} excluded term(s): " + "|".join(excluded))
    excluded_phrases = [phrase for phrase in spec.exclude_phrases if product.has_phrase(phrase)]
    if excluded_phrases:
        return reject(f"{spec.esha_code} excluded phrase(s): " + "|".join(excluded_phrases))
    return accept(f"{spec.esha_code} reviewed contract accepted")
