"""Shared dataclasses + enums for the calculator.

Guardrails baked in:
- #4: Resolution requires BOTH nutrition_state and shopping_state.
- #10: single import location for every type.
- #18: no imports from resolver.py / layered_resolver.py here — keep types pure.
- #20: alternatives[] always present (may be empty).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class NutritionState(Enum):
    EXACT_USDA_ANCHOR = "exact_usda_anchor"
    REVIEWED_LOCAL_LABEL_ANCHOR = "reviewed_local_label_anchor"
    REVIEWED_PROXY = "reviewed_proxy"
    NUTRITION_UNKNOWN = "nutrition_unknown"
    NON_FOOD = "non_food"


class ShoppingState(Enum):
    SHOPPING_CANDIDATES_STRONG = "shopping_candidates_strong"
    SHOPPING_CANDIDATES_WEAK = "shopping_candidates_weak"
    SHOPPING_GAP = "shopping_gap"
    NON_FOOD = "non_food"


class TrustLayer(Enum):
    L1_CANONICAL = "L1_canonical"
    L2_CANONICAL_ALIAS = "L2_canonical_alias"
    L3_CANONICAL_STRIPPED = "L3_canonical_stripped"
    L4_REVIEWED_PROXY = "L4_reviewed_proxy"
    L5_SR28_FALLBACK = "L5_sr28_fallback"
    L6_EXTERNAL_CATALOG = "L6_external_catalog"
    L7_CONCEPT_ALIAS = "L7_concept_alias"
    L8_NUTRITION_UNKNOWN = "L8_nutrition_unknown"


@dataclass
class NutritionEstimate:
    kcal: float
    protein_g: float
    fat_g: float
    carbs_g: float


@dataclass
class ProductCandidate:
    gtin_upc: str
    description: str
    brand_name: str
    branded_food_category: str
    source: str  # A_fndds_crosswalk | B_category_map | C_normalizer | D_cleaned_overlay


@dataclass
class Resolution:
    canonical_name: str
    sr28_fdc_id: str
    fndds_code: str
    pseudo_code: str
    nutrition_state: NutritionState
    shopping_state: ShoppingState
    trust_layer: TrustLayer
    grams: float | None
    alternatives: list[str]
    path: list[str]
    nutrition: NutritionEstimate | None = None
    products: list[ProductCandidate] = field(default_factory=list)
    notes: str = ""
    shopping_canonical: str = ""
    # Shopping-side SR28/FNDDS codes. Distinct from the nutrition sr28_fdc_id/
    # fndds_code fields because an auto-batched proxy may legitimately supply
    # nutrition via its proxy code but MUST NOT drive shopping through that
    # code (the proxy's SR28 points at an unrelated food). Callers that join
    # products by code must use these fields, not the nutrition fields.
    shopping_sr28_fdc_id: str = ""
    shopping_fndds_code: str = ""
    # Esha is the granular food ID (39,691 distinct codes vs SR28's ~7,800).
    # When set, nutrition comes from esha_nutrition.csv (Tier A label median
    # preferred, Tier B SR28/FNDDS proxy fallback). Shopping joins products
    # by esha_code — products are tagged with their own EshaCode at build
    # time, so two foods that share an SR28 proxy (e.g. chipotle mayo and
    # mayonnaise proxy to mayo's SR28) still shop as distinct products.
    esha_code: str = ""
    # Hestia Taxonomy Code (HTC) + Retail Leaf Path (RLP), loaded from the
    # compact api/data/hestia_taxonomy_lookup.db artifact.
    canonical_path: str = ""
    retail_leaf_path: str = ""
    canonical_label: str = ""
    product_identity_fixed: str = ""
    htc_code: str = ""
    htc_sku_code: str = ""
    htc_group: str = ""
    htc_family: str = ""
    htc_food: str = ""
    htc_form: str = ""
    htc_processing: str = ""
    htc_ptype: str = ""
    htc_check: str = ""
    htc_confidence: float | None = None
    htc_source: str = ""
    taxonomy_source: str = ""
