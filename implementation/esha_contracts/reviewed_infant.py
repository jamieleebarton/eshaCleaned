from __future__ import annotations

from .contract_base import (
    ContractFn,
    ContractSpec,
    MatchDecision,
    ProductFacts,
    accept,
    match_spec,
    reject,
)

INFANT_CATEGORIES = ("baby", "infant", "powdered drinks")

SOY_EXCLUDES = ("milk", "dairy", "lactose", "whey", "casein")
STANDARD_EXCLUDES = ("soy", "isomil", "prosobee")

def make_brand_form_contract(
    esha_code: str,
    esha_description: str,
    brand_terms: tuple[str, ...],
    form_terms: tuple[str, ...],
    variant_terms: tuple[str, ...] = (),
    exclude_terms: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*INFANT_CATEGORIES):
            if not product.has_any(*brand_terms):
                return reject(f"{esha_code} category mismatch")
        if not product.has_any(*brand_terms):
            return reject(f"{esha_code} missing brand")
        spec = ContractSpec(
            esha_code=esha_code,
            esha_description=esha_description,
            allowed_categories=(),
            search_terms=brand_terms + form_terms + variant_terms,
            required_terms=form_terms + variant_terms,
            exclude_terms=exclude_terms,
        )
        return match_spec(product, spec)
    return contract


def make_generic_contract(
    esha_code: str,
    esha_description: str,
    form_terms: tuple[str, ...],
    variant_terms: tuple[str, ...] = (),
    exclude_terms: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*INFANT_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any("formula", "infant"):
            return reject(f"{esha_code} missing formula/infant cue")
        spec = ContractSpec(
            esha_code=esha_code,
            esha_description=esha_description,
            allowed_categories=(),
            search_terms=form_terms + variant_terms,
            required_terms=form_terms + variant_terms,
            exclude_terms=exclude_terms,
        )
        return match_spec(product, spec)
    return contract


def make_specialty_contract(
    esha_code: str,
    esha_description: str,
    product_terms: tuple[str, ...],
    form_terms: tuple[str, ...],
    variant_terms: tuple[str, ...] = (),
    exclude_terms: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*INFANT_CATEGORIES):
            if not product.has_any(*product_terms):
                return reject(f"{esha_code} category mismatch")
        if not product.has_any(*product_terms):
            return reject(f"{esha_code} missing product name")
        spec = ContractSpec(
            esha_code=esha_code,
            esha_description=esha_description,
            allowed_categories=(),
            search_terms=product_terms + form_terms + variant_terms,
            required_terms=form_terms + variant_terms,
            exclude_terms=exclude_terms,
        )
        return match_spec(product, spec)
    return contract

# make_brand_form_contract entries
def match_esha_18778(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("18778", 'Infant Formula, soy, Good Start, with DHA & ARA, ready to feed', ('good', 'start'), ('ready', 'feed'), (), ('casein', 'dairy', 'essentials', 'gentle', 'milk', 'nourish', 'protect', 'soy', 'supreme', 'whey'))(product)

def match_esha_18779(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("18779", 'Infant Formula, soy, Good Start, with ARA & DHA, powder', ('good', 'start'), ('powder',), (), ('casein', 'dairy', 'essentials', 'gentle', 'milk', 'nourish', 'protect', 'soy', 'supreme', 'whey'))(product)

def match_esha_18783(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("18783", 'Infant Formula, Good Start Gentle Plus, with iron, ready to feed', ('good', 'start'), ('ready', 'feed'), ('gentle', 'plus'), ('essentials', 'isomil', 'nourish', 'prosobee', 'protect', 'soy', 'supreme'))(product)

def match_esha_18784(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("18784", 'Infant Formula, Good Start Gentle Plus, with iron, prepared from concentrate', ('good', 'start'), ('concentrated',), ('gentle', 'plus'), ('essentials', 'isomil', 'nourish', 'prosobee', 'protect', 'soy', 'supreme'))(product)

def match_esha_18788(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("18788", 'Infant Formula, soy, Good Start, with DHA & ARA, concentrate', ('good', 'start'), ('concentrated',), (), ('casein', 'dairy', 'essentials', 'gentle', 'milk', 'nourish', 'protect', 'soy', 'supreme', 'whey'))(product)

def match_esha_14701(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("14701", 'Infant Formula, Good Start Supreme, powder', ('good', 'start'), ('powder',), ('supreme',), ('essentials', 'gentle', 'isomil', 'nourish', 'prosobee', 'protect', 'soy'))(product)

def match_esha_14702(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("14702", 'Infant Formula, Good Start Supreme NaturalCultures powder scoop', ('good', 'start'), ('powder',), ('supreme',), ('essentials', 'gentle', 'isomil', 'nourish', 'prosobee', 'protect', 'soy'))(product)

def match_esha_14703(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("14703", 'Infant Formula, soy, Good Start Supeme, powder', ('good', 'start'), ('powder',), (), ('casein', 'dairy', 'essentials', 'gentle', 'milk', 'nourish', 'protect', 'soy', 'supreme', 'whey'))(product)

def match_esha_14704(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("14704", 'Infant Formula, Good Start 2 Supreme, powder', ('good', 'start'), ('powder',), ('supreme',), ('essentials', 'gentle', 'isomil', 'nourish', 'prosobee', 'protect', 'soy'))(product)

def match_esha_14705(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("14705", 'Infant Formula, soy, Good Start 2 Supreme, powder', ('good', 'start'), ('powder',), ('supreme',), ('casein', 'dairy', 'essentials', 'gentle', 'milk', 'nourish', 'protect', 'soy', 'whey'))(product)

def match_esha_14706(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("14706", 'Infant Formula, NAN, powder', ('nan',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_15362(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("15362", 'Infant Formula, Enfamil AR LIPIL, powder', ('enfamil',), ('powder',), ('lipil',), ('enfacare', 'enfagrow', 'gentlease', 'isomil', 'lacto', 'lactofree', 'next', 'nutramigen', 'portagen', 'pregestimil', 'prosobee', 'soy', 'step'))(product)

def match_esha_15363(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("15363", 'Infant Formula, Enfamil AR LIPIL, ready to use', ('enfamil',), ('ready', 'feed'), ('lipil',), ('enfacare', 'enfagrow', 'gentlease', 'isomil', 'lacto', 'lactofree', 'next', 'nutramigen', 'portagen', 'pregestimil', 'prosobee', 'soy', 'step'))(product)

def match_esha_15368(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("15368", 'Infant Formula, Similac Advance, with iron, powder', ('similac',), ('powder',), ('advance',), ('alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_15369(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("15369", 'Infant Formula, Similac Advance, with iron, concentrate', ('similac',), ('concentrated',), ('advance',), ('alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_16953(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("16953", 'Infant Formula, Similac Advance, with iron, ready to feed', ('similac',), ('ready', 'feed'), ('advance',), ('alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_16955(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("16955", 'Infant Formula, Enfamil Lactofree, with iron, powder', ('enfamil',), ('powder',), ('lactofree',), ('enfacare', 'enfagrow', 'gentlease', 'isomil', 'next', 'nutramigen', 'portagen', 'pregestimil', 'prosobee', 'soy', 'step'))(product)

def match_esha_16957(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("16957", 'Infant Formula, Enfamil, with iron, powder', ('enfamil',), ('powder',), (), ('enfacare', 'enfagrow', 'gentlease', 'isomil', 'lacto', 'lactofree', 'lipil', 'next', 'nutramigen', 'portagen', 'pregestimil', 'prosobee', 'soy', 'step'))(product)

def match_esha_16962(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("16962", 'Infant Formula, Enfamil, low iron, powder', ('enfamil',), ('powder',), (), ('enfacare', 'enfagrow', 'gentlease', 'isomil', 'lacto', 'lactofree', 'lipil', 'next', 'nutramigen', 'portagen', 'pregestimil', 'prosobee', 'soy', 'step'))(product)

def match_esha_16963(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("16963", 'Infant Formula, Enfamil, low iron, ready to feed', ('enfamil',), ('ready', 'feed'), (), ('enfacare', 'enfagrow', 'gentlease', 'isomil', 'lacto', 'lactofree', 'lipil', 'next', 'nutramigen', 'portagen', 'pregestimil', 'prosobee', 'soy', 'step'))(product)

def match_esha_16965(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("16965", 'Infant Formula, Enfamil, with iron, ready to feed', ('enfamil',), ('ready', 'feed'), (), ('enfacare', 'enfagrow', 'gentlease', 'isomil', 'lacto', 'lactofree', 'lipil', 'next', 'nutramigen', 'portagen', 'pregestimil', 'prosobee', 'soy', 'step'))(product)

def match_esha_17953(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("17953", 'Infant Formula, Bright Beginnings, gentle, prepared from dry', ('bright', 'beginnings'), ('powder',), ('gentle',), ('isomil', 'prosobee', 'soy', 'ultra'))(product)

def match_esha_17954(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("17954", 'Infant Formula, Bright Beginnings, prepared from dry, org', ('bright', 'beginnings'), ('powder',), (), ('gentle', 'isomil', 'prosobee', 'soy', 'ultra'))(product)

def match_esha_17955(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("17955", 'Infant Formula, soy, Bright Beginnings, prepared from dry', ('bright', 'beginnings'), ('powder',), (), ('casein', 'dairy', 'gentle', 'milk', 'ultra', 'whey'))(product)

def match_esha_17956(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("17956", 'Infant Formula, Bright Beginnings 2, prepared from dry', ('bright', 'beginnings'), ('powder',), ('2',), ('gentle', 'isomil', 'prosobee', 'soy', 'ultra'))(product)

def match_esha_17957(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("17957", 'Infant Formula, Bright Beginnings 2, with prebiotics, prepared', ('bright', 'beginnings'), ('prepared',), ('2',), ('gentle', 'isomil', 'prosobee', 'soy', 'ultra'))(product)

def match_esha_17958(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("17958", 'Infant Formula, Bright Beginnings, prepared from dry', ('bright', 'beginnings'), ('powder',), (), ('gentle', 'isomil', 'prosobee', 'soy', 'ultra'))(product)

def match_esha_17961(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("17961", 'Infant Formula, Bright Beginnings, gentle, powder', ('bright', 'beginnings'), ('powder',), ('gentle',), ('isomil', 'prosobee', 'soy', 'ultra'))(product)

def match_esha_17962(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("17962", 'Infant Formula, Bright Beginnings, powder, org', ('bright', 'beginnings'), ('powder',), (), ('gentle', 'isomil', 'prosobee', 'soy', 'ultra'))(product)

def match_esha_17963(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("17963", 'Infant Formula, soy, Bright Beginnings, powder', ('bright', 'beginnings'), ('powder',), (), ('casein', 'dairy', 'gentle', 'milk', 'ultra', 'whey'))(product)

def match_esha_17964(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("17964", 'Infant Formula, Bright Beginnings 2, powder', ('bright', 'beginnings'), ('powder',), ('2',), ('gentle', 'isomil', 'prosobee', 'soy', 'ultra'))(product)

def match_esha_17965(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("17965", 'Infant Formula, Bright Beginnings, powder', ('bright', 'beginnings'), ('powder',), (), ('gentle', 'isomil', 'prosobee', 'soy', 'ultra'))(product)

def match_esha_21505(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("21505", 'Infant Formula, Good Start Gentle Plus, powder', ('good', 'start'), ('powder',), ('gentle', 'plus'), ('essentials', 'isomil', 'nourish', 'prosobee', 'protect', 'soy', 'supreme'))(product)

def match_esha_21506(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("21506", 'Infant Formula, Good Start Protect Plus, powder', ('good', 'start'), ('powder',), ('protect', 'plus'), ('essentials', 'gentle', 'isomil', 'nourish', 'prosobee', 'soy', 'supreme'))(product)

def match_esha_21507(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("21507", 'Infant Formula, Good Start Nourish Plus, powder', ('good', 'start'), ('powder',), ('nourish', 'plus'), ('essentials', 'gentle', 'isomil', 'prosobee', 'protect', 'soy', 'supreme'))(product)

def match_esha_21508(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("21508", 'Infant Formula, Good Start Gentle Plus, ready to feed', ('good', 'start'), ('ready', 'feed'), ('gentle', 'plus'), ('essentials', 'isomil', 'nourish', 'prosobee', 'protect', 'soy', 'supreme'))(product)

def match_esha_21509(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("21509", 'Infant Formula, Good Start Soy Plus, powder', ('good', 'start'), ('powder',), ('soy', 'plus'), ('casein', 'dairy', 'essentials', 'gentle', 'milk', 'nourish', 'protect', 'supreme', 'whey'))(product)

def match_esha_21510(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("21510", 'Infant Formula, Good Start Soy Plus, ready to feed', ('good', 'start'), ('ready', 'feed'), ('soy', 'plus'), ('casein', 'dairy', 'essentials', 'gentle', 'milk', 'nourish', 'protect', 'supreme', 'whey'))(product)

def match_esha_21511(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("21511", 'Infant Formula, Good Start Gentle Plus 2, powder', ('good', 'start'), ('powder',), ('gentle', 'plus'), ('essentials', 'isomil', 'nourish', 'prosobee', 'protect', 'soy', 'supreme'))(product)

def match_esha_21512(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("21512", 'Infant Formula, Good Start Protect Plus 2, powder', ('good', 'start'), ('powder',), ('protect', 'plus'), ('essentials', 'gentle', 'isomil', 'nourish', 'prosobee', 'soy', 'supreme'))(product)

def match_esha_21513(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("21513", 'Infant Formula, Good Start Soy Plus 2, powder', ('good', 'start'), ('powder',), ('soy', 'plus'), ('casein', 'dairy', 'essentials', 'gentle', 'milk', 'nourish', 'protect', 'supreme', 'whey'))(product)

def match_esha_29369(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29369", 'Infant Formula, Similac Expert Care Alimentum, prepared from pwd', ('similac',), ('powder',), ('alimentum',), ('advance', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29370(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29370", 'Infant Formula, Similac Expert Care Alimentum, powder', ('similac',), ('powder',), ('alimentum',), ('advance', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29371(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29371", 'Infant Formula, Similac Organic, powder', ('similac',), ('powder',), ('organic',), ('advance', 'alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29372(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29372", 'Infant Formula, soy, Similac Go & Grow, prepared from pwd', ('similac',), ('powder',), ('go', 'grow'), ('advance', 'alimentum', 'care', 'casein', 'comfort', 'dairy', 'isomil', 'milk', 'neosure', 'organic', 'sensitive', 'special', 'spit', 'total', 'whey'))(product)

def match_esha_29373(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29373", 'Infant Formula, Similac Sensitive for Spit-Up, ready to feed', ('similac',), ('ready', 'feed'), ('sensitive', 'spit'), ('advance', 'alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'soy', 'special', 'total'))(product)

def match_esha_29374(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29374", 'Infant Formula, soy, Similac Isomil, prepared from pwd', ('similac',), ('powder',), ('isomil',), ('advance', 'alimentum', 'care', 'casein', 'comfort', 'dairy', 'go', 'grow', 'milk', 'neosure', 'organic', 'sensitive', 'special', 'spit', 'total', 'whey'))(product)

def match_esha_29375(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29375", 'Infant Formula, soy, Similac Isomil, powder', ('similac',), ('powder',), ('isomil',), ('advance', 'alimentum', 'care', 'casein', 'comfort', 'dairy', 'go', 'grow', 'milk', 'neosure', 'organic', 'sensitive', 'special', 'spit', 'total', 'whey'))(product)

def match_esha_29376(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29376", 'Infant Formula, Similac NeoSure, ready to feed', ('similac',), ('ready', 'feed'), ('neosure',), ('advance', 'alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29377(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29377", 'Infant Formula, Similac NeoSure, ready to feed, SD', ('similac',), ('ready', 'feed'), ('neosure',), ('advance', 'alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29378(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29378", 'Infant Formula, Similac PM 60/40, powder', ('similac',), ('powder',), ('pm',), ('advance', 'alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29379(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29379", 'Infant Formula, Similac PM 60/40, prepared from pwd', ('similac',), ('powder',), ('pm',), ('advance', 'alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29380(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29380", 'Infant Formula, Similac Go & Grow, prepared from pwd', ('similac',), ('powder',), ('go', 'grow'), ('advance', 'alimentum', 'care', 'comfort', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29381(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29381", 'Infant Formula, Similac Expert Care Alimentum, ready to feed', ('similac',), ('ready', 'feed'), ('alimentum',), ('advance', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29382(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29382", 'Infant Formula, Similac Organic, prepared from pwd', ('similac',), ('powder',), ('organic',), ('advance', 'alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29383(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29383", 'Infant Formula, Similac Go & Grow, powder', ('similac',), ('powder',), ('go', 'grow'), ('advance', 'alimentum', 'care', 'comfort', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29384(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29384", 'Infant Formula, soy, Similac Go & Grow, powder', ('similac',), ('powder',), ('go', 'grow'), ('advance', 'alimentum', 'care', 'casein', 'comfort', 'dairy', 'isomil', 'milk', 'neosure', 'organic', 'sensitive', 'special', 'spit', 'total', 'whey'))(product)

def match_esha_29385(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29385", 'Infant Formula, Similac Sensitive for Spit-Up, powder', ('similac',), ('powder',), ('sensitive', 'spit'), ('advance', 'alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'soy', 'special', 'total'))(product)

def match_esha_29386(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29386", 'Infant Formula, Similac Sensitive for Spit-Up, prepared from pwd', ('similac',), ('powder',), ('sensitive', 'spit'), ('advance', 'alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'soy', 'special', 'total'))(product)

def match_esha_29387(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29387", 'Infant Formula, Similac Special Care 20, low iron, ready to feed, SD', ('similac',), ('ready', 'feed'), ('special', 'care'), ('advance', 'alimentum', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'spit', 'total'))(product)

def match_esha_29388(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29388", 'Infant Formula, Similac Special Care 24, high protein, ready to feed, SD', ('similac',), ('ready', 'feed'), ('special', 'care'), ('advance', 'alimentum', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'spit', 'total'))(product)

def match_esha_29389(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29389", 'Infant Formula, Similac Special Care 30, with iron, ready to feed', ('similac',), ('ready', 'feed'), ('special', 'care'), ('advance', 'alimentum', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'spit', 'total'))(product)

def match_esha_29390(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29390", 'Infant Formula, Similac Special Care 30, with iron, ready to feed, SD', ('similac',), ('ready', 'feed'), ('special', 'care'), ('advance', 'alimentum', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'spit', 'total'))(product)

def match_esha_29391(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29391", 'Infant Formula, Similac Organic, ready to feed', ('similac',), ('ready', 'feed'), ('organic',), ('advance', 'alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29392(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29392", 'Infant Formula, Similac Organic, ready to feed, SD', ('similac',), ('ready', 'feed'), ('organic',), ('advance', 'alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29393(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29393", 'Infant Formula, soy, Similac Isomil, ready to feed', ('similac',), ('ready', 'feed'), ('isomil',), ('advance', 'alimentum', 'care', 'casein', 'comfort', 'dairy', 'go', 'grow', 'milk', 'neosure', 'organic', 'sensitive', 'special', 'spit', 'total', 'whey'))(product)

def match_esha_29394(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29394", 'Infant Formula, soy, Similac Isomil, ready to feed, SD', ('similac',), ('ready', 'feed'), ('isomil',), ('advance', 'alimentum', 'care', 'casein', 'comfort', 'dairy', 'go', 'grow', 'milk', 'neosure', 'organic', 'sensitive', 'special', 'spit', 'total', 'whey'))(product)

def match_esha_29395(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29395", 'Infant Formula, soy, Similac Isomil On-The-Go, ready to feed', ('similac',), ('ready', 'feed'), ('isomil',), ('advance', 'alimentum', 'care', 'casein', 'comfort', 'dairy', 'go', 'grow', 'milk', 'neosure', 'organic', 'sensitive', 'special', 'spit', 'total', 'whey'))(product)

def match_esha_29396(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29396", 'Infant Formula, soy, Similac Isomil, concentrate', ('similac',), ('concentrated',), ('isomil',), ('advance', 'alimentum', 'care', 'casein', 'comfort', 'dairy', 'go', 'grow', 'milk', 'neosure', 'organic', 'sensitive', 'special', 'spit', 'total', 'whey'))(product)

def match_esha_29397(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29397", 'Infant Formula, soy, Similac Isomil, prepared from concentrate', ('similac',), ('concentrated',), ('isomil',), ('advance', 'alimentum', 'care', 'casein', 'comfort', 'dairy', 'go', 'grow', 'milk', 'neosure', 'organic', 'sensitive', 'special', 'spit', 'total', 'whey'))(product)

def match_esha_29398(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29398", 'Infant Formula, Similac NeoSure, prepared from pwd', ('similac',), ('powder',), ('neosure',), ('advance', 'alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29399(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29399", 'Infant Formula, Similac NeoSure, powder', ('similac',), ('powder',), ('neosure',), ('advance', 'alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29400(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29400", 'Infant Formula, Similac Advance, ready to feed', ('similac',), ('ready', 'feed'), ('advance',), ('alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29401(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29401", 'Infant Formula, Similac Expert Care Alimentum, ready to feed, SD', ('similac',), ('ready', 'feed'), ('alimentum',), ('advance', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29463(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29463", 'Infant Formula, Similac Advance, concentrate', ('similac',), ('concentrated',), ('advance',), ('alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29464(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29464", 'Infant Formula, Similac Advance, prepared from concentrate', ('similac',), ('concentrated',), ('advance',), ('alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29465(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29465", 'Infant Formula, Similac Special Care 24, with iron, ready to feed', ('similac',), ('ready', 'feed'), ('special', 'care'), ('advance', 'alimentum', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'spit', 'total'))(product)

def match_esha_29466(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29466", 'Infant Formula, Similac Special Care 24, with iron, ready to feed, SD', ('similac',), ('ready', 'feed'), ('special', 'care'), ('advance', 'alimentum', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'spit', 'total'))(product)

def match_esha_29467(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29467", 'Infant Formula, Similac Advance, powder', ('similac',), ('powder',), ('advance',), ('alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29468(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29468", 'Infant Formula, Similac Advance, prepared from pwd', ('similac',), ('powder',), ('advance',), ('alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29469(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29469", 'Infant Formula, Similac Sensitive, ready to feed', ('similac',), ('ready', 'feed'), ('sensitive',), ('advance', 'alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29470(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29470", 'Infant Formula, Similac Sensitive, ready to feed, SD', ('similac',), ('ready', 'feed'), ('sensitive',), ('advance', 'alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29471(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29471", 'Infant Formula, Similac Sensitive, prepared from concentrate', ('similac',), ('concentrated',), ('sensitive',), ('advance', 'alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29472(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29472", 'Infant Formula, Similac Sensitive, concentrate', ('similac',), ('concentrated',), ('sensitive',), ('advance', 'alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29473(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29473", 'Infant Formula, Similac Sensitive, prepared from pwd', ('similac',), ('powder',), ('sensitive',), ('advance', 'alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_29474(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("29474", 'Infant Formula, Similac Sensitive, powder', ('similac',), ('powder',), ('sensitive',), ('advance', 'alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_37780(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("37780", 'Infant Formula, Enfamil Gentlease, powder', ('enfamil',), ('powder',), ('gentlease',), ('enfacare', 'enfagrow', 'isomil', 'lacto', 'lactofree', 'lipil', 'next', 'nutramigen', 'portagen', 'pregestimil', 'prosobee', 'soy', 'step'))(product)

def match_esha_37942(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("37942", 'Infant Formula, Enfamil, Gentlease, powder', ('enfamil',), ('powder',), ('gentlease',), ('enfacare', 'enfagrow', 'isomil', 'lacto', 'lactofree', 'lipil', 'next', 'nutramigen', 'portagen', 'pregestimil', 'prosobee', 'soy', 'step'))(product)

def match_esha_60135(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("60135", 'Infant Formula, Similac, low iron, ready to feed', ('similac',), ('ready', 'feed'), (), ('advance', 'alimentum', 'care', 'comfort', 'diarrhea', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_60173(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("60173", 'Infant Formula, Similac, with iron, ready to feed', ('similac',), ('ready', 'feed'), (), ('advance', 'alimentum', 'care', 'comfort', 'diarrhea', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_60302(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("60302", 'Infant Formula, soy, Ultra Bright Beginnings, ready to feed', ('bright', 'beginnings'), ('ready', 'feed'), ('ultra',), ('casein', 'dairy', 'gentle', 'milk', 'whey'))(product)

def match_esha_60311(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("60311", 'Infant Formula, Similac Special Care 20, with iron, ready to feed, SD', ('similac',), ('ready', 'feed'), ('special', 'care'), ('advance', 'alimentum', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'spit', 'total'))(product)

def match_esha_60312(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("60312", 'Infant Formula, Similac Special Care 24, low iron, ready to feed, SD', ('similac',), ('ready', 'feed'), ('special', 'care'), ('advance', 'alimentum', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'spit', 'total'))(product)

def match_esha_60314(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("60314", 'Infant Formula, Ultra Bright Beginnings, ready to feed', ('bright', 'beginnings'), ('ready', 'feed'), ('ultra',), ('gentle', 'isomil', 'prosobee', 'soy'))(product)

def match_esha_60455(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("60455", 'Infant Formula, Natural Care Advance, with ARA & DHA, ready to feed', ('natural', 'care'), ('ready', 'feed'), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62301(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("62301", 'Infant Formula, Similac Expert Care for Diarrhea, ready to feed', ('similac',), ('ready', 'feed'), ('diarrhea',), ('advance', 'alimentum', 'care', 'comfort', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_62351(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("62351", 'Infant Formula, Good Start Supreme, with iron, ready to feed', ('good', 'start'), ('ready', 'feed'), ('supreme',), ('essentials', 'gentle', 'isomil', 'nourish', 'prosobee', 'protect', 'soy'))(product)

def match_esha_62354(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("62354", 'Infant Formula, Enfamil Lactofree, with iron, ready to feed', ('enfamil',), ('ready', 'feed'), ('lactofree',), ('enfacare', 'enfagrow', 'gentlease', 'isomil', 'next', 'nutramigen', 'portagen', 'pregestimil', 'prosobee', 'soy', 'step'))(product)

def match_esha_62356(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("62356", 'Infant Formula, Good Start 2 Essentials, with iron, ready to feed', ('good', 'start'), ('ready', 'feed'), ('essentials',), ('gentle', 'isomil', 'nourish', 'prosobee', 'protect', 'soy', 'supreme'))(product)

def match_esha_62358(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("62358", 'Infant Formula, soy, Good Start Essentials, with iron, ready to feed', ('good', 'start'), ('ready', 'feed'), ('essentials',), ('casein', 'dairy', 'gentle', 'milk', 'nourish', 'protect', 'soy', 'supreme', 'whey'))(product)

def match_esha_62600(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("62600", 'Infant Formula, Good Start Supreme with iron, concentrate', ('good', 'start'), ('concentrated',), ('supreme',), ('essentials', 'gentle', 'isomil', 'nourish', 'prosobee', 'protect', 'soy'))(product)

def match_esha_62601(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("62601", 'Infant Formula, Good Start Supreme with iron, powder, scoop', ('good', 'start'), ('powder',), ('supreme',), ('essentials', 'gentle', 'isomil', 'nourish', 'prosobee', 'protect', 'soy'))(product)

def match_esha_62617(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("62617", 'Infant Formula, Similac, with iron, concentrate', ('similac',), ('concentrated',), (), ('advance', 'alimentum', 'care', 'comfort', 'diarrhea', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_62618(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("62618", 'Infant Formula, Similac, with iron, powder', ('similac',), ('powder',), (), ('advance', 'alimentum', 'care', 'comfort', 'diarrhea', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_62619(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("62619", 'Infant Formula, Similac, low iron, concentrate', ('similac',), ('concentrated',), (), ('advance', 'alimentum', 'care', 'comfort', 'diarrhea', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_62620(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("62620", 'Infant Formula, Similac, low iron, powder', ('similac',), ('powder',), (), ('advance', 'alimentum', 'care', 'comfort', 'diarrhea', 'go', 'grow', 'isomil', 'neosure', 'organic', 'prosobee', 'sensitive', 'soy', 'special', 'spit', 'total'))(product)

def match_esha_62623(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("62623", 'Infant Formula, Ultra Bright Beginnings, concentrate', ('bright', 'beginnings'), ('concentrated',), ('ultra',), ('gentle', 'isomil', 'prosobee', 'soy'))(product)

def match_esha_62624(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("62624", 'Infant Formula, Ultra Bright Beginnings, powder', ('bright', 'beginnings'), ('powder',), ('ultra',), ('gentle', 'isomil', 'prosobee', 'soy'))(product)

def match_esha_62628(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("62628", 'Infant Formula, soy, Ultra Bright Beginnings, powder, scoop', ('bright', 'beginnings'), ('powder',), ('ultra',), ('casein', 'dairy', 'gentle', 'milk', 'whey'))(product)

def match_esha_62629(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("62629", 'Infant Formula, Good Start 2 Essentials with iron, concentrate', ('good', 'start'), ('concentrated',), ('essentials',), ('gentle', 'isomil', 'nourish', 'prosobee', 'protect', 'soy', 'supreme'))(product)

def match_esha_62630(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("62630", 'Infant Formula, Good Start 2 Essentials with iron, powder, scoop', ('good', 'start'), ('powder',), ('essentials',), ('gentle', 'isomil', 'nourish', 'prosobee', 'protect', 'soy', 'supreme'))(product)

def match_esha_62633(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("62633", 'Infant Formula, soy, Good Start Essentials, with iron, concentrate', ('good', 'start'), ('concentrated',), ('essentials',), ('casein', 'dairy', 'gentle', 'milk', 'nourish', 'protect', 'soy', 'supreme', 'whey'))(product)

def match_esha_62634(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("62634", 'Infant Formula, soy, Good Start Essentials, with iron, powder scp', ('good', 'start'), ('powder',), ('essentials',), ('casein', 'dairy', 'gentle', 'milk', 'nourish', 'protect', 'soy', 'supreme', 'whey'))(product)

def match_esha_63435(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("63435", 'Infant Formula, Enfamil LIPIL, with iron, ARA & DHA, powder', ('enfamil',), ('powder',), ('lipil',), ('enfacare', 'enfagrow', 'gentlease', 'isomil', 'lacto', 'lactofree', 'next', 'nutramigen', 'portagen', 'pregestimil', 'prosobee', 'soy', 'step'))(product)

def match_esha_63436(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("63436", 'Infant Formula, Enfamil LIPIL, with iron, ready to feed', ('enfamil',), ('ready', 'feed'), ('lipil',), ('enfacare', 'enfagrow', 'gentlease', 'isomil', 'lacto', 'lactofree', 'next', 'nutramigen', 'portagen', 'pregestimil', 'prosobee', 'soy', 'step'))(product)

def match_esha_63437(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("63437", 'Infant Formula, Enfamil LIPIL, low iron, with ARA & DHA, powder', ('enfamil',), ('powder',), ('lipil',), ('enfacare', 'enfagrow', 'gentlease', 'isomil', 'lacto', 'lactofree', 'next', 'nutramigen', 'portagen', 'pregestimil', 'prosobee', 'soy', 'step'))(product)

def match_esha_63438(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("63438", 'Infant Formula, Enfamil LactoFree LIPIL, with iron, powder', ('enfamil',), ('powder',), ('lactofree',), ('enfacare', 'enfagrow', 'gentlease', 'isomil', 'next', 'nutramigen', 'portagen', 'pregestimil', 'prosobee', 'soy', 'step'))(product)

def match_esha_63439(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("63439", 'Infant Formula, Enfamil LactoFree LIPIL, with iron, concentrate', ('enfamil',), ('concentrated',), ('lactofree',), ('enfacare', 'enfagrow', 'gentlease', 'isomil', 'next', 'nutramigen', 'portagen', 'pregestimil', 'prosobee', 'soy', 'step'))(product)

def match_esha_63440(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("63440", 'Infant Formula, Enfamil LIPIL, ready to feed', ('enfamil',), ('ready', 'feed'), ('lipil',), ('enfacare', 'enfagrow', 'gentlease', 'isomil', 'lacto', 'lactofree', 'next', 'nutramigen', 'portagen', 'pregestimil', 'prosobee', 'soy', 'step'))(product)

def match_esha_63627(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("63627", 'Infant Formula, soy, Ultra Bright Beginnings, concentrate', ('bright', 'beginnings'), ('concentrated',), ('ultra',), ('casein', 'dairy', 'gentle', 'milk', 'whey'))(product)

def match_esha_63660(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("63660", 'Infant Formula, Enfamil LIPIL, with iron ARA DHA, concentrate', ('enfamil',), ('concentrated',), ('lipil',), ('enfacare', 'enfagrow', 'gentlease', 'isomil', 'lacto', 'lactofree', 'next', 'nutramigen', 'portagen', 'pregestimil', 'prosobee', 'soy', 'step'))(product)

def match_esha_63661(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("63661", 'Infant Formula, Enfamil LIPIL, low iron, concentrate', ('enfamil',), ('concentrated',), ('lipil',), ('enfacare', 'enfagrow', 'gentlease', 'isomil', 'lacto', 'lactofree', 'next', 'nutramigen', 'portagen', 'pregestimil', 'prosobee', 'soy', 'step'))(product)

def match_esha_63662(product: ProductFacts) -> MatchDecision:
    return make_brand_form_contract("63662", 'Infant Formula, Enfamil LIPIL, low iron, ready to feed', ('enfamil',), ('ready', 'feed'), ('lipil',), ('enfacare', 'enfagrow', 'gentlease', 'isomil', 'lacto', 'lactofree', 'next', 'nutramigen', 'portagen', 'pregestimil', 'prosobee', 'soy', 'step'))(product)

# make_generic_contract entries
def match_esha_04431(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("4431", 'Infant Formula, Sensitive, lactose free, with ARA & DHA, ready to feed', ('ready', 'feed'), ('sensitive',), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_18785(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("18785", 'Infant Formula, Gentlease LIPIL, with iron, prepared from pwd', ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_15356(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("15356", 'Infant Formula, Store Brand, ready to feed', ('ready', 'feed'), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_15357(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("15357", 'Infant Formula, Store Brand, concentrate', ('concentrated',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_15358(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("15358", 'Infant Formula, Store Brand, powder', ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_15359(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("15359", 'Infant Formula, soy, Store Brand, ready to feed', ('ready', 'feed'), (), ('casein', 'dairy', 'milk', 'whey'))(product)

def match_esha_15360(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("15360", 'Infant Formula, soy, Store Brand, concentrate', ('concentrated',), (), ('casein', 'dairy', 'milk', 'whey'))(product)

def match_esha_15361(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("15361", 'Infant Formula, soy, Store Brand, powder', ('powder',), (), ('casein', 'dairy', 'milk', 'whey'))(product)

def match_esha_15364(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("15364", 'Infant Formula, EnfaCare LIPIL, ready to use', ('ready', 'feed'), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_15365(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("15365", 'Infant Formula, NeoSure Advance, with ARA & DHA, ready to feed', ('ready', 'feed'), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_15366(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("15366", 'Infant Formula, Sensitive, lactose free, with ARA & DHA, concentrate', ('concentrated',), ('sensitive',), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_15367(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("15367", 'Infant Formula, Sensitive, lactose free, with ARA & DHA, powder', ('powder',), ('sensitive',), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_15370(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("15370", 'Infant Formula, Isomil Advance, with iron, concentrate', ('concentrated',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_15371(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("15371", 'Infant Formula, Isomil Advance, with iron, ready to feed', ('ready', 'feed'), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_15372(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("15372", 'Infant Formula, Isomil Advance, with iron, powder', ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_16956(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("16956", 'Infant Formula, soy, ProSobee, with iron, powder', ('powder',), (), ('casein', 'dairy', 'milk', 'whey'))(product)

def match_esha_16959(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("16959", 'Infant Formula, soy, ProSobee Next Step, powder', ('powder',), (), ('casein', 'dairy', 'milk', 'whey'))(product)

def match_esha_16960(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("16960", 'Infant Formula, soy, ProSobee Next Step, prepared from pwd', ('powder',), (), ('casein', 'dairy', 'milk', 'whey'))(product)

def match_esha_16966(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("16966", 'Infant Formula, soy, ProSobee, with iron, liquid concentrate', ('concentrated',), (), ('casein', 'dairy', 'milk', 'whey'))(product)

def match_esha_17941(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("17941", 'Infant Formula, Store Brand, gentle, prepared from pwd', ('powder',), ('gentle',), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_17942(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("17942", 'Infant Formula, Store Brand, lactose free, prepared from pwd', ('powder',), ('lactose', 'free'), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_17943(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("17943", 'Infant Formula, Store Brand, prepared from pwd, org', ('powder',), ('organic',), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_17944(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("17944", 'Infant Formula, Store Brand, stage 2, prepared from pwd', ('powder',), ('stage',), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_17945(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("17945", 'Infant Formula, Store Brand, sensitivity, prepared from pwd', ('powder',), ('sensitivity',), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_17946(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("17946", 'Infant Formula, soy, Store Brand, prepared from pwd, org', ('powder',), ('organic',), ('casein', 'dairy', 'milk', 'whey'))(product)

def match_esha_17947(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("17947", 'Infant Formula, Store Brand, gentle, powder', ('powder',), ('gentle',), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_17948(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("17948", 'Infant Formula, Store Brand, lactose free, powder', ('powder',), ('lactose', 'free'), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_17949(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("17949", 'Infant Formula, Store Brand, powder, org', ('powder',), ('organic',), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_17950(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("17950", 'Infant Formula, Store Brand, stage 2, powder', ('powder',), ('stage',), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_17951(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("17951", 'Infant Formula, Store Brand, sensitivity, powder', ('powder',), ('sensitivity',), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_17952(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("17952", 'Infant Formula, soy, Store Brand, powder, org', ('powder',), ('organic',), ('casein', 'dairy', 'milk', 'whey'))(product)

def match_esha_28418(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("28418", 'Infant Formula, Alimentum Advance, with iron ARA & DHA, powder', ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_37940(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("37940", 'Infant Formula, Enfagrow Premium, powder', ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_37941(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("37941", 'Infant Formula, Enfagrow Premium, ready to feed', ('ready', 'feed'), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_39796(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("39796", 'Infant Formula, Nutramigen, with iron, powder', ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_39797(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("39797", 'Infant Formula, Next Step LIPIL, prepared from pwd', ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_39798(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("39798", 'Infant Formula, Nutramigen, with iron, prepared from pwd', ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_39800(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("39800", 'Infant Formula, Pregestimil, with iron, 20 calorie/ounce, ready to use', ('ready', 'feed'), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_39801(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("39801", 'Infant Formula, Pregestimil, with iron, 24 calorie/ounce, ready to use', ('ready', 'feed'), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_60133(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("60133", 'Infant Formula, Premature, with iron, 20cal/ounce, ready to use', ('ready', 'feed'), ('premature',), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_60134(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("60134", 'Infant Formula, Premature, with iron, 24cal/ounce, ready to use', ('ready', 'feed'), ('premature',), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_60136(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("60136", 'Infant Formula, Special Care Advance 24, with iron ARA DHA, ready to feed', ('ready', 'feed'), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_60297(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("60297", 'Infant Formula, Premature, 20cal/ounce, ready to use', ('ready', 'feed'), ('premature',), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_60298(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("60298", 'Infant Formula, Premature, 24cal/ounce, ready to use', ('ready', 'feed'), ('premature',), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_60299(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("60299", 'Infant Formula, soy, Isomil, with iron, ready to feed', ('ready', 'feed'), (), ('casein', 'dairy', 'milk', 'whey'))(product)

def match_esha_60303(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("60303", 'Infant Formula, Nutramigen, with iron, ready to feed', ('ready', 'feed'), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_60304(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("60304", 'Infant Formula, Pregestimil, with iron, prepared from pwd', ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_60305(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("60305", 'Infant Formula, soy, ProSobee, with iron, ready to feed', ('ready', 'feed'), (), ('casein', 'dairy', 'milk', 'whey'))(product)

def match_esha_62072(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("62072", 'Infant Formula, Alimentum, with iron, ready to feed', ('ready', 'feed'), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62125(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("62125", 'Infant Formula, Portagen, with iron, prepared from pwd', ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62176(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("62176", 'Infant Formula, NeoSure Advance, with ARA & DHA, powder', ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62353(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("62353", 'Infant Formula, EnfaCare LIPIL, with iron ARA DHA, powder', ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62585(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("62585", 'Infant Formula, Next Step LIPIL, powder', ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62607(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("62607", 'Infant Formula, Nutramigen, with iron, powder, scoop', ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62608(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("62608", 'Infant Formula, Nutramigen, with iron, liquid concentrate', ('concentrated',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62609(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("62609", 'Infant Formula, Portagen, with iron, powder, scoop', ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62610(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("62610", 'Infant Formula, Pregestimil, with iron, powder, scoop', ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62613(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("62613", 'Infant Formula, PM 60/40, low iron, powder', ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62614(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("62614", 'Infant Formula, soy, Isomil, with iron, concentrate', ('concentrated',), (), ('casein', 'dairy', 'milk', 'whey'))(product)

def match_esha_62615(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("62615", 'Infant Formula, soy, Isomil, with iron, powder', ('powder',), (), ('casein', 'dairy', 'milk', 'whey'))(product)

def match_esha_63441(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("63441", 'Infant Formula, Nutramigen LIPIL, with iron, powder', ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_63442(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("63442", 'Infant Formula, Nutramigen LIPIL, with iron, concentrate', ('concentrated',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_63443(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("63443", 'Infant Formula, soy, ProSobee Next Step LIPIL, with ARA DHA powder', ('powder',), (), ('casein', 'dairy', 'milk', 'whey'))(product)

def match_esha_63622(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("63622", 'Infant Formula, soy, ProSobee LIPIL, with iron, ready to use', ('ready', 'feed'), (), ('casein', 'dairy', 'milk', 'whey'))(product)

def match_esha_63623(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("63623", 'Infant Formula, soy, ProSobee Next Step LIPIL, ready to feed', ('ready', 'feed'), (), ('casein', 'dairy', 'milk', 'whey'))(product)

def match_esha_63624(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("63624", 'Infant Formula, soy, ProSobee LIPIL, with iron, powder, scoop', ('powder',), (), ('casein', 'dairy', 'milk', 'whey'))(product)

def match_esha_63625(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("63625", 'Infant Formula, soy, ProSobee LIPIL, with iron ARA DHA, concentrate', ('concentrated',), (), ('casein', 'dairy', 'milk', 'whey'))(product)

def match_esha_63626(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("63626", 'Infant Formula, Nutramigen LIPIL, with iron, ready to feed', ('ready', 'feed'), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_63664(product: ProductFacts) -> MatchDecision:
    return make_generic_contract("63664", 'Infant Formula, Alimentum Advance, with ARA & DHA, ready to feed', ('ready', 'feed'), (), ('isomil', 'prosobee', 'soy'))(product)

# make_specialty_contract entries
def match_esha_04430(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("4430", 'Infant Formula, Calcilo XD, powder', ('calcilo',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_29434(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("29434", 'Infant Formula, EleCare, vanilla, 20 calorie/fl ounce, prepared', ('elecare',), ('prepared',), ('vanilla',), ('isomil', 'prosobee', 'soy', 'unflavored'))(product)

def match_esha_29435(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("29435", 'Infant Formula, EleCare, vanilla, 30 calorie/fl ounce, prepared', ('elecare',), ('prepared',), ('vanilla',), ('isomil', 'prosobee', 'soy', 'unflavored'))(product)

def match_esha_29437(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("29437", 'Infant Formula, Cyclinex-1, powder', ('cyclinex',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_29439(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("29439", 'Infant Formula, EleCare, unflavored, powder', ('elecare',), ('powder',), ('unflavored',), ('isomil', 'prosobee', 'soy', 'vanilla'))(product)

def match_esha_29440(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("29440", 'Infant Formula, EleCare, vanilla, powder', ('elecare',), ('powder',), ('vanilla',), ('isomil', 'prosobee', 'soy', 'unflavored'))(product)

def match_esha_29441(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("29441", 'Infant Formula, Glutarex-1, powder', ('glutarex',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_29444(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("29444", 'Infant Formula, Hominex-1, powder', ('hominex',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_29446(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("29446", 'Infant Formula, I-Valex-1, powder', ('i-valex',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_29449(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("29449", 'Infant Formula, Ketonex-1, powder', ('ketonex',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_29451(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("29451", 'Infant Formula, Phenex-1, powder', ('phenex',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_29455(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("29455", 'Infant Formula, Pro-Phree, powder', ('pro-phree',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_29456(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("29456", 'Infant Formula, Propimex-1, powder', ('propimex',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_29459(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("29459", 'Infant Formula, Tyrex-1, powder', ('tyrex',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_39802(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("39802", 'Infant Formula, TYROS 1, powder', ('tyros',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_39804(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("39804", 'Infant Formula, PFD 1, powder', ('pfd',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_39810(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("39810", 'Infant Formula, HCY 1, powder', ('hcy',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_39812(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("39812", 'Infant Formula, OA 1, powder', ('oa',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_39815(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("39815", 'Infant Formula, WND 1, powder', ('wnd',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_60131(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("60131", 'Infant Formula, Product 3232A, with o added carb, powder', ('product', '3232a'), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62069(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("62069", 'Infant Formula, BCAD 1, powder, scoop', ('bcad',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62128(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("62128", 'Infant Formula, Phenyl-Free 1, powder', ('phenyl-free',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62364(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("62364", 'Infant Formula, Xphe Analog, powder scp', ('xphe',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62367(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("62367", 'Infant Formula, MSUD Analog, powder scp', ('msud',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62370(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("62370", 'Infant Formula, XPhe Xtyr Analog, powder scp', ('xphe',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62372(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("62372", 'Infant Formula, XPTM Analog, powder scp', ('xptm',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62373(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("62373", 'Infant Formula, Xmet Analog, powder scp', ('xmet',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62376(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("62376", 'Infant Formula, XMTVI Analog, powder scp', ('xmtvi',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62378(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("62378", 'Infant Formula, XLys XTrp Analog, powder scp', ('xlys',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62381(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("62381", 'Infant Formula, Xleu Analog, powder scp', ('xleu',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_62536(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("62536", 'Infant Formula, Neocate, powder', ('neocate',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

def match_esha_63375(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("63375", 'Infant Formula, EleCare, unflavored, 20 calorie/fl ounce, prepared', ('elecare',), ('prepared',), ('unflavored',), ('isomil', 'prosobee', 'soy', 'vanilla'))(product)

def match_esha_63376(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("63376", 'Infant Formula, EleCare, unflavored, 30 calorie/fl ounce, prepared', ('elecare',), ('prepared',), ('unflavored',), ('isomil', 'prosobee', 'soy', 'vanilla'))(product)

def match_esha_63761(product: ProductFacts) -> MatchDecision:
    return make_specialty_contract("63761", 'Infant Formula, Neocate, DHA & ARA, powder, scp', ('neocate',), ('powder',), (), ('isomil', 'prosobee', 'soy'))(product)

CONTRACTS: dict[str, ContractFn] = {
    "4430": match_esha_04430,
    "4431": match_esha_04431,
    "18778": match_esha_18778,
    "18779": match_esha_18779,
    "18783": match_esha_18783,
    "18784": match_esha_18784,
    "18785": match_esha_18785,
    "18788": match_esha_18788,
    "14701": match_esha_14701,
    "14702": match_esha_14702,
    "14703": match_esha_14703,
    "14704": match_esha_14704,
    "14705": match_esha_14705,
    "14706": match_esha_14706,
    "15356": match_esha_15356,
    "15357": match_esha_15357,
    "15358": match_esha_15358,
    "15359": match_esha_15359,
    "15360": match_esha_15360,
    "15361": match_esha_15361,
    "15362": match_esha_15362,
    "15363": match_esha_15363,
    "15364": match_esha_15364,
    "15365": match_esha_15365,
    "15366": match_esha_15366,
    "15367": match_esha_15367,
    "15368": match_esha_15368,
    "15369": match_esha_15369,
    "15370": match_esha_15370,
    "15371": match_esha_15371,
    "15372": match_esha_15372,
    "16953": match_esha_16953,
    "16955": match_esha_16955,
    "16956": match_esha_16956,
    "16957": match_esha_16957,
    "16959": match_esha_16959,
    "16960": match_esha_16960,
    "16962": match_esha_16962,
    "16963": match_esha_16963,
    "16965": match_esha_16965,
    "16966": match_esha_16966,
    "17941": match_esha_17941,
    "17942": match_esha_17942,
    "17943": match_esha_17943,
    "17944": match_esha_17944,
    "17945": match_esha_17945,
    "17946": match_esha_17946,
    "17947": match_esha_17947,
    "17948": match_esha_17948,
    "17949": match_esha_17949,
    "17950": match_esha_17950,
    "17951": match_esha_17951,
    "17952": match_esha_17952,
    "17953": match_esha_17953,
    "17954": match_esha_17954,
    "17955": match_esha_17955,
    "17956": match_esha_17956,
    "17957": match_esha_17957,
    "17958": match_esha_17958,
    "17961": match_esha_17961,
    "17962": match_esha_17962,
    "17963": match_esha_17963,
    "17964": match_esha_17964,
    "17965": match_esha_17965,
    "21505": match_esha_21505,
    "21506": match_esha_21506,
    "21507": match_esha_21507,
    "21508": match_esha_21508,
    "21509": match_esha_21509,
    "21510": match_esha_21510,
    "21511": match_esha_21511,
    "21512": match_esha_21512,
    "21513": match_esha_21513,
    "28418": match_esha_28418,
    "29369": match_esha_29369,
    "29370": match_esha_29370,
    "29371": match_esha_29371,
    "29372": match_esha_29372,
    "29373": match_esha_29373,
    "29374": match_esha_29374,
    "29375": match_esha_29375,
    "29376": match_esha_29376,
    "29377": match_esha_29377,
    "29378": match_esha_29378,
    "29379": match_esha_29379,
    "29380": match_esha_29380,
    "29381": match_esha_29381,
    "29382": match_esha_29382,
    "29383": match_esha_29383,
    "29384": match_esha_29384,
    "29385": match_esha_29385,
    "29386": match_esha_29386,
    "29387": match_esha_29387,
    "29388": match_esha_29388,
    "29389": match_esha_29389,
    "29390": match_esha_29390,
    "29391": match_esha_29391,
    "29392": match_esha_29392,
    "29393": match_esha_29393,
    "29394": match_esha_29394,
    "29395": match_esha_29395,
    "29396": match_esha_29396,
    "29397": match_esha_29397,
    "29398": match_esha_29398,
    "29399": match_esha_29399,
    "29400": match_esha_29400,
    "29401": match_esha_29401,
    "29434": match_esha_29434,
    "29435": match_esha_29435,
    "29437": match_esha_29437,
    "29439": match_esha_29439,
    "29440": match_esha_29440,
    "29441": match_esha_29441,
    "29444": match_esha_29444,
    "29446": match_esha_29446,
    "29449": match_esha_29449,
    "29451": match_esha_29451,
    "29455": match_esha_29455,
    "29456": match_esha_29456,
    "29459": match_esha_29459,
    "29463": match_esha_29463,
    "29464": match_esha_29464,
    "29465": match_esha_29465,
    "29466": match_esha_29466,
    "29467": match_esha_29467,
    "29468": match_esha_29468,
    "29469": match_esha_29469,
    "29470": match_esha_29470,
    "29471": match_esha_29471,
    "29472": match_esha_29472,
    "29473": match_esha_29473,
    "29474": match_esha_29474,
    "37780": match_esha_37780,
    "37940": match_esha_37940,
    "37941": match_esha_37941,
    "37942": match_esha_37942,
    "39796": match_esha_39796,
    "39797": match_esha_39797,
    "39798": match_esha_39798,
    "39800": match_esha_39800,
    "39801": match_esha_39801,
    "39802": match_esha_39802,
    "39804": match_esha_39804,
    "39810": match_esha_39810,
    "39812": match_esha_39812,
    "39815": match_esha_39815,
    "60131": match_esha_60131,
    "60133": match_esha_60133,
    "60134": match_esha_60134,
    "60135": match_esha_60135,
    "60136": match_esha_60136,
    "60173": match_esha_60173,
    "60297": match_esha_60297,
    "60298": match_esha_60298,
    "60299": match_esha_60299,
    "60302": match_esha_60302,
    "60303": match_esha_60303,
    "60304": match_esha_60304,
    "60305": match_esha_60305,
    "60311": match_esha_60311,
    "60312": match_esha_60312,
    "60314": match_esha_60314,
    "60455": match_esha_60455,
    "62069": match_esha_62069,
    "62072": match_esha_62072,
    "62125": match_esha_62125,
    "62128": match_esha_62128,
    "62176": match_esha_62176,
    "62301": match_esha_62301,
    "62351": match_esha_62351,
    "62353": match_esha_62353,
    "62354": match_esha_62354,
    "62356": match_esha_62356,
    "62358": match_esha_62358,
    "62364": match_esha_62364,
    "62367": match_esha_62367,
    "62370": match_esha_62370,
    "62372": match_esha_62372,
    "62373": match_esha_62373,
    "62376": match_esha_62376,
    "62378": match_esha_62378,
    "62381": match_esha_62381,
    "62536": match_esha_62536,
    "62585": match_esha_62585,
    "62600": match_esha_62600,
    "62601": match_esha_62601,
    "62607": match_esha_62607,
    "62608": match_esha_62608,
    "62609": match_esha_62609,
    "62610": match_esha_62610,
    "62613": match_esha_62613,
    "62614": match_esha_62614,
    "62615": match_esha_62615,
    "62617": match_esha_62617,
    "62618": match_esha_62618,
    "62619": match_esha_62619,
    "62620": match_esha_62620,
    "62623": match_esha_62623,
    "62624": match_esha_62624,
    "62628": match_esha_62628,
    "62629": match_esha_62629,
    "62630": match_esha_62630,
    "62633": match_esha_62633,
    "62634": match_esha_62634,
    "63375": match_esha_63375,
    "63376": match_esha_63376,
    "63435": match_esha_63435,
    "63436": match_esha_63436,
    "63437": match_esha_63437,
    "63438": match_esha_63438,
    "63439": match_esha_63439,
    "63440": match_esha_63440,
    "63441": match_esha_63441,
    "63442": match_esha_63442,
    "63443": match_esha_63443,
    "63622": match_esha_63622,
    "63623": match_esha_63623,
    "63624": match_esha_63624,
    "63625": match_esha_63625,
    "63626": match_esha_63626,
    "63627": match_esha_63627,
    "63660": match_esha_63660,
    "63661": match_esha_63661,
    "63662": match_esha_63662,
    "63664": match_esha_63664,
    "63761": match_esha_63761,
}
