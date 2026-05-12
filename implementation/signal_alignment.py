"""Pass L — multi-signal alignment scorer.

For any (product, candidate ESHA family) pair, count how many of 4 independent
signals agree on the family:

  Signal 1: Title-implied family       (detect_family on product description)
  Signal 2: PC-implied family          (dominant family in this branded_food_category)
  Signal 3: Brand×PC-implied family    (dominant family in this brand+PC cell)
  Signal 4: Ingredient-implied family  (dominant from product's ingredients)

Returns (agree_count, available_count). A safe assignment requires agree_count
to meet a minimum proportion of available_count.

The alignment dominants are learned ONLY from CONSERVATIVE trusted rows:
  assignment_source == "fallback_category_family" AND score >= 12

This excludes anything healed (so we don't amplify our own errors) and uses
only the matcher's most-confident output as the learning source.

WWEIA is intentionally NOT included — it's LLM-tagged and we already
established it amplifies bias when used as a structural signal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import pandas as pd


PC_MIN_SUPPORT = 50
BRAND_PC_MIN_SUPPORT = 15
INGREDIENT_MIN_SUPPORT = 50

# Which families count as "compatible siblings" so a single mismatch between
# them doesn't drop the alignment count. Snack-domain families overlap a lot.
SIBLING_FAMILIES = [
    {"dessert_snack", "grain"},      # cookies/granola bars span both
    {"dessert_snack", "condiment"},  # pie fillings, chocolate sauces
    {"vegetable", "soup"},           # canned vegetables vs vegetable soup
    {"meat", "prepared_food"},       # deli meat vs deli sandwich
    {"fruit", "condiment"},          # jams, preserves
]


def _families_compatible(a: str, b: str) -> bool:
    if a == b:
        return True
    for group in SIBLING_FAMILIES:
        if a in group and b in group:
            return True
    return False


@dataclass
class AlignmentDominants:
    """Per-cell dominant family lookup tables."""
    pc_dom: dict[str, str] = field(default_factory=dict)
    pc_share: dict[str, float] = field(default_factory=dict)
    brand_pc_dom: dict[tuple[str, str], str] = field(default_factory=dict)
    brand_pc_share: dict[tuple[str, str], float] = field(default_factory=dict)
    ingredient_dom_per_gtin: dict[str, str] = field(default_factory=dict)
    ingredient_share_per_gtin: dict[str, float] = field(default_factory=dict)


def _dominant(group_cols: list[str], src: pd.DataFrame, min_support: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    g = src.dropna(subset=group_cols).copy()
    cells = g.groupby(group_cols + ["family"]).size().reset_index(name="n")
    totals = cells.groupby(group_cols)["n"].sum().rename("total").reset_index()
    cells = cells.merge(totals, on=group_cols)
    dom = cells.sort_values(group_cols + ["n"], ascending=[True] * len(group_cols) + [False]).drop_duplicates(group_cols, keep="first")
    dom = dom[dom["total"] >= min_support].copy()
    dom["share"] = dom["n"] / dom["total"]
    return dom, cells


def learn_dominants(trusted: pd.DataFrame) -> AlignmentDominants:
    """Learn alignment dominants from trusted rows.

    `trusted` must have columns:
      gtin_upc, branded_food_category, brand, family
    where `brand` is preferably brand_name with brand_owner fallback.
    """
    out = AlignmentDominants()

    # PC -> family
    pc_dom_df, _ = _dominant(["branded_food_category"], trusted, PC_MIN_SUPPORT)
    out.pc_dom = dict(zip(pc_dom_df["branded_food_category"], pc_dom_df["family"]))
    out.pc_share = dict(zip(pc_dom_df["branded_food_category"], pc_dom_df["share"]))

    # (brand, PC) -> family
    bp_dom_df, _ = _dominant(["brand", "branded_food_category"], trusted, BRAND_PC_MIN_SUPPORT)
    for _, row in bp_dom_df.iterrows():
        out.brand_pc_dom[(row["brand"], row["branded_food_category"])] = row["family"]
        out.brand_pc_share[(row["brand"], row["branded_food_category"])] = row["share"]

    return out


def compute_ingredient_signals(
    ingredient_pairs: pd.DataFrame,  # columns: gtin_upc, ingredient
    trusted: pd.DataFrame,
    out: AlignmentDominants,
) -> None:
    """Mutates `out`: fills `ingredient_dom_per_gtin` and `ingredient_share_per_gtin`.

    For each Ingredient, learn its dominant family from trusted rows that
    contain that ingredient. Then for each Product, aggregate across its
    ingredients (weighted by ingredient share) to get the product-level
    ingredient-implied family.
    """
    trusted_basic = trusted[["gtin_upc", "family"]]
    ing_trusted = ingredient_pairs.merge(trusted_basic, on="gtin_upc", how="inner")
    ing_dom_df, _ = _dominant(["ingredient"], ing_trusted, INGREDIENT_MIN_SUPPORT)
    if ing_dom_df.empty:
        return
    ing_lookup = dict(zip(ing_dom_df["ingredient"], zip(ing_dom_df["family"], ing_dom_df["share"])))

    # For each product, aggregate ingredient votes
    has_dom = ingredient_pairs[ingredient_pairs["ingredient"].isin(ing_lookup)].copy()
    has_dom["dominant_family"] = has_dom["ingredient"].map(lambda i: ing_lookup[i][0])
    has_dom["share"] = has_dom["ingredient"].map(lambda i: ing_lookup[i][1])
    votes = has_dom.groupby(["gtin_upc", "dominant_family"])["share"].sum().reset_index().rename(columns={"share": "vote_weight"})
    totals = votes.groupby("gtin_upc")["vote_weight"].sum().rename("total_vote").reset_index()
    votes = votes.merge(totals, on="gtin_upc")
    sig = votes.sort_values(["gtin_upc", "vote_weight"], ascending=[True, False]).drop_duplicates("gtin_upc", keep="first")
    sig["share"] = sig["vote_weight"] / sig["total_vote"].clip(lower=1e-6)
    for _, row in sig.iterrows():
        out.ingredient_dom_per_gtin[row["gtin_upc"]] = row["dominant_family"]
        out.ingredient_share_per_gtin[row["gtin_upc"]] = float(row["share"])


@dataclass
class AlignmentResult:
    agree_count: int
    available_count: int
    signal_families: dict[str, str]  # signal_name -> expected_family

    @property
    def passes_strict(self) -> bool:
        # Require at least 2 signals available AND >= 50% of available agree
        if self.available_count < 2:
            return True  # fall back gracefully — can't enforce without enough signal
        # If 4 available -> need 3
        if self.available_count == 4:
            return self.agree_count >= 3
        # Otherwise majority
        return self.agree_count * 2 >= self.available_count + (1 if self.available_count % 2 == 0 else 0)


def compute_alignment(
    *,
    title_family: str | None,
    branded_food_category: str | None,
    brand: str | None,
    gtin_upc: str | None,
    candidate_family: str,
    dominants: AlignmentDominants,
) -> AlignmentResult:
    """For a single product attribute set + candidate ESHA family, return agreement count."""
    signals: dict[str, str] = {}

    if title_family:
        signals["title"] = title_family

    if branded_food_category:
        pc_fam = dominants.pc_dom.get(branded_food_category)
        if pc_fam:
            signals["pc"] = pc_fam

    if brand and branded_food_category:
        bp_fam = dominants.brand_pc_dom.get((brand, branded_food_category))
        if bp_fam:
            signals["brand_pc"] = bp_fam

    if gtin_upc:
        ing_fam = dominants.ingredient_dom_per_gtin.get(gtin_upc)
        if ing_fam:
            signals["ingredient"] = ing_fam

    available = len(signals)
    agree = sum(1 for f in signals.values() if _families_compatible(f, candidate_family))
    return AlignmentResult(agree_count=agree, available_count=available, signal_families=signals)


def alignment_passes(
    *,
    title_family: str | None,
    branded_food_category: str | None,
    brand: str | None,
    gtin_upc: str | None,
    candidate_family: str,
    dominants: AlignmentDominants,
    min_agree_when_4: int = 3,
    min_agree_when_3: int = 2,
    min_agree_when_2: int = 2,
    ingredient_veto: bool = True,
) -> bool:
    """Hard-gate: returns True if alignment meets minimum thresholds.

    INGREDIENT VETO (default ON): if the ingredient signal is available,
    the candidate family MUST be compatible with the ingredient-implied
    family. Ingredients are the closest thing to ground truth — they're
    regulated label data — so a contradiction with ingredients overrides
    any number of agreeing brand/PC/title signals.
    """
    # Ingredient veto: if available and incompatible, reject regardless of others
    if ingredient_veto and gtin_upc:
        ing_fam = dominants.ingredient_dom_per_gtin.get(gtin_upc)
        ing_share = dominants.ingredient_share_per_gtin.get(gtin_upc, 0.0)
        # Only veto when ingredient signal is strong (>= 0.6 share)
        if ing_fam and ing_share >= 0.6 and not _families_compatible(ing_fam, candidate_family):
            return False

    r = compute_alignment(
        title_family=title_family,
        branded_food_category=branded_food_category,
        brand=brand,
        gtin_upc=gtin_upc,
        candidate_family=candidate_family,
        dominants=dominants,
    )
    if r.available_count < 2:
        return True  # cannot enforce — fall back to other scoring
    if r.available_count == 4:
        return r.agree_count >= min_agree_when_4
    if r.available_count == 3:
        return r.agree_count >= min_agree_when_3
    return r.agree_count >= min_agree_when_2


def best_target_family(
    voted_family: str | None,
    *,
    title_family: str | None,
    branded_food_category: str | None,
    brand: str | None,
    gtin_upc: str | None,
    dominants: AlignmentDominants,
) -> str | None:
    """Return voted_family if it passes ingredient veto, else override.

    When ingredient signal is strong (>= 0.6) and disagrees with voted_family,
    we override to the ingredient-implied family. Ingredients are ground truth.
    """
    if not voted_family or not dominants:
        return voted_family
    if alignment_passes(
        title_family=title_family,
        branded_food_category=branded_food_category,
        brand=brand,
        gtin_upc=gtin_upc,
        candidate_family=voted_family,
        dominants=dominants,
        ingredient_veto=True,
    ):
        return voted_family
    # Veto fired or alignment failed — switch to ingredient-implied family if strong
    if gtin_upc:
        ing = dominants.ingredient_dom_per_gtin.get(gtin_upc)
        ing_share = dominants.ingredient_share_per_gtin.get(gtin_upc, 0.0)
        if ing and ing_share >= 0.5:
            return ing
    return voted_family


def load_alignment_dominants_from_cache(cache_path) -> AlignmentDominants | None:
    """Load dominants written by Pass L. Returns None if cache missing."""
    import json as _json
    from pathlib import Path as _Path
    p = _Path(cache_path)
    if not p.exists():
        return None
    j = _json.loads(p.read_text())
    return AlignmentDominants(
        pc_dom=j.get("pc_dom", {}),
        brand_pc_dom={tuple(k.split("|||", 1)): v for k, v in j.get("brand_pc_dom", {}).items()},
        ingredient_dom_per_gtin=j.get("ingredient_dom_per_gtin", {}),
        ingredient_share_per_gtin=j.get("ingredient_share_per_gtin", {}),
    )


def aligned_families(
    *,
    title_family: str | None,
    branded_food_category: str | None,
    brand: str | None,
    gtin_upc: str | None,
    dominants: AlignmentDominants,
    min_agree: int = 2,
    ingredient_veto: bool = True,
) -> list[str]:
    """Return the list of families that pass alignment for this product.

    With INGREDIENT VETO on, the ingredient-implied family is the dominant
    candidate — if available with strong share, ONLY families compatible
    with it are returned.
    """
    # If ingredients are strong, they alone determine valid families
    if ingredient_veto and gtin_upc:
        ing_fam = dominants.ingredient_dom_per_gtin.get(gtin_upc)
        ing_share = dominants.ingredient_share_per_gtin.get(gtin_upc, 0.0)
        if ing_fam and ing_share >= 0.6:
            # Only return families compatible with the ingredient signal
            candidates = {ing_fam}
            # Also include sibling-compatible families
            for fam in [title_family,
                        dominants.pc_dom.get(branded_food_category) if branded_food_category else None,
                        dominants.brand_pc_dom.get((brand, branded_food_category)) if brand and branded_food_category else None]:
                if fam and _families_compatible(fam, ing_fam):
                    candidates.add(fam)
            return list(candidates)

    # Otherwise, vote across available signals
    candidates = set()
    if title_family:
        candidates.add(title_family)
    if branded_food_category:
        f = dominants.pc_dom.get(branded_food_category)
        if f:
            candidates.add(f)
    if brand and branded_food_category:
        f = dominants.brand_pc_dom.get((brand, branded_food_category))
        if f:
            candidates.add(f)
    if gtin_upc:
        f = dominants.ingredient_dom_per_gtin.get(gtin_upc)
        if f:
            candidates.add(f)

    out: list[str] = []
    for fam in candidates:
        if alignment_passes(
            title_family=title_family,
            branded_food_category=branded_food_category,
            brand=brand,
            gtin_upc=gtin_upc,
            candidate_family=fam,
            dominants=dominants,
            min_agree_when_4=min_agree,
            min_agree_when_3=min_agree,
            min_agree_when_2=min_agree,
            ingredient_veto=False,  # already checked above
        ):
            out.append(fam)
    return out
