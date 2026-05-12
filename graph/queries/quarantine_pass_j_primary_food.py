"""Pass J: primary-food-token mismatch quarantine + re-mapping.

For each (Product, ESHA) pair currently in v3, extract the *primary food noun*
from each description. If they disagree, the assignment is structurally wrong
even if scores are high.

Examples this catches:
    LARGE APRICOTS    -> primary=apricot   ESHA=Apple, fresh    primary=apple    DISAGREE
    DOUBLE CHOC APPLE -> primary=chocolate ESHA=Adam's Apple    primary=apple    DISAGREE
    ROASTED PEPPER HUMMUS -> primary=hummus ESHA=Cracker        primary=cracker  DISAGREE

Examples this leaves alone (correctly):
    MCINTOSH APPLES   -> primary=apple     ESHA=Apple, medium   primary=apple    AGREE

Priority order for picking the primary food token from a multi-noun description:
    1. DESSERT_HEADS (chocolate, candy, cookie, cake) — confections dominate
    2. SEAFOOD / MEAT / POULTRY                       — animal proteins are usually primary
    3. LEGUMES / NUTS_SEEDS                           — bean/nut products
    4. VEGETABLES
    5. FRUITS
    6. GRAINS

When mismatch is found, search ALL ESHA codes for one whose primary matches the
product's primary, then pick the highest-scoring (entropy-weighted token overlap).

Writes:
    implementation/output/product_to_best_esha_full_map.v4.csv
    graph/quarantine/primary_food_mismatches.csv
    graph/quarantine/baseline_after_pass_j.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
V3_CSV = ROOT / "implementation" / "output" / "product_to_best_esha_full_map.v3.csv"
V4_CSV = ROOT / "implementation" / "output" / "product_to_best_esha_full_map.v4.csv"
ESHA_CSV = ROOT / "esha_cleaned.csv"
TOKEN_ENTROPY_CSV = ROOT / "data" / "token_entropy.csv"
OUT_DIR = ROOT / "graph" / "quarantine"
OUT_MISMATCHES = OUT_DIR / "primary_food_mismatches.csv"
OUT_BASELINE = OUT_DIR / "baseline_after_pass_j.json"

sys.path.insert(0, str(ROOT / "implementation"))
from match_esha_to_products import (  # noqa: E402
    FRUITS, VEGETABLES, MEATS, POULTRY, SEAFOOD, LEGUMES, NUTS_SEEDS,
    GRAINS, DESSERT_HEADS, tokens_for,
)


# Confection/pastry tokens missing from DESSERT_HEADS that need to count as
# DESSERT primary food. Without these, "Pop-Tarts Caramel Apple", "Apple Babka",
# "Caramel Apple Werther's", "Gummi Apple Rings", etc. fall through to FRUIT
# primary because none of {tart, caramel, babka, gummi, ...} are in DESSERT_HEADS.
EXTRA_CONFECTION_TOKENS = {
    # confections
    "caramel", "caramels", "fudge", "toffee", "nougat",
    "gummy", "gummi", "gummies", "jelly", "jellybean", "jellybeans",
    "marshmallow", "marshmallows", "marzipan", "praline", "pralines",
    "icing", "frosting", "glaze", "glazed", "candied", "syrup",
    # pastries / baked sweets
    "tart", "tarts", "babka", "strudel", "danish", "turnover", "turnovers",
    "scone", "scones", "popover", "waffle", "waffles", "fritter", "fritters",
    "eclair", "macaron", "macaroon", "macarons", "macaroons", "kringle",
    "cobbler", "crumble", "crisp", "crisps",  # apple crisp etc.
    "shortcake", "trifle",
}
# Treat snack-style PCs as savory/sweet snacks regardless of fruit token in name.
DESSERT_FOODS = (DESSERT_HEADS | EXTRA_CONFECTION_TOKENS) - {"snack", "dessert", "meal", "dish", "bar", "mix"}

# Priority-ordered domains. Earlier domain wins when multiple food tokens present.
DOMAIN_ORDER: list[tuple[str, set[str]]] = [
    ("DESSERT", DESSERT_FOODS),
    ("SEAFOOD", SEAFOOD),
    ("POULTRY", POULTRY),
    ("MEAT", MEATS),
    ("LEGUME", LEGUMES),
    ("NUT_SEED", NUTS_SEEDS),
    ("VEGETABLE", VEGETABLES),
    ("FRUIT", FRUITS),
    ("GRAIN", GRAINS),
]


def primary_food(tokens: list[str]) -> tuple[str | None, str | None]:
    """Return (token, domain) of the primary food noun, by priority order.

    Within a domain, picks the earliest occurrence in the token list.
    """
    if not tokens:
        return None, None
    token_seq = list(tokens)
    for domain, members in DOMAIN_ORDER:
        for tok in token_seq:
            if tok in members:
                return tok, domain
    return None, None


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("loading v3 CSV", flush=True)
    v3 = pd.read_csv(V3_CSV, dtype=str, keep_default_na=False, low_memory=False)
    n = len(v3)
    print(f"  rows: {n:,}", flush=True)

    print("loading ESHA database", flush=True)
    esha = pd.read_csv(ESHA_CSV, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    esha = esha.rename(columns={"EshaCode": "code", "Description": "description"})
    esha = esha[["code", "description"]].copy()
    esha["code"] = esha["code"].astype(str).str.strip()
    esha["description"] = esha["description"].astype(str).str.strip()
    esha = esha[esha["code"].str.match(r"^\d+$")]
    print(f"  esha codes: {len(esha):,}", flush=True)

    print("tokenizing + extracting primary food per ESHA code", flush=True)
    esha["_tokens"] = esha["description"].apply(tokens_for)
    esha[["_primary", "_domain"]] = esha["_tokens"].apply(lambda t: pd.Series(primary_food(t)))
    print(f"  ESHAs with primary food: {esha['_primary'].notna().sum():,}", flush=True)

    print("loading token entropy", flush=True)
    if TOKEN_ENTROPY_CSV.exists():
        ent = pd.read_csv(TOKEN_ENTROPY_CSV, dtype={"token": str})
        max_e = max(float(ent["entropy"].max() or 1.0), 1e-6)
        token_weight = {row.token: 1.0 - (float(row.entropy or 0.0) / max_e) for row in ent.itertuples()}
    else:
        token_weight = {}

    print("tokenizing + extracting primary food per Product (v3)", flush=True)
    v3["_p_tokens"] = v3["product_description"].apply(tokens_for)
    v3[["_p_primary", "_p_domain"]] = v3["_p_tokens"].apply(lambda t: pd.Series(primary_food(t)))

    print("tokenizing + extracting primary food per Product's currently-assigned ESHA description", flush=True)
    v3["_e_tokens"] = v3["best_esha_description"].apply(tokens_for)
    v3[["_e_primary", "_e_domain"]] = v3["_e_tokens"].apply(lambda t: pd.Series(primary_food(t)))

    has_p = v3["_p_primary"].notna()
    has_e = v3["_e_primary"].notna()
    has_both = has_p & has_e
    print(f"  rows with product primary food:  {has_p.sum():,}", flush=True)
    print(f"  rows with ESHA primary food:     {has_e.sum():,}", flush=True)
    print(f"  rows with BOTH:                  {has_both.sum():,}", flush=True)

    mismatch = has_both & (v3["_p_primary"] != v3["_e_primary"])
    print(f"  primary-food-mismatch rows:      {mismatch.sum():,}", flush=True)

    # Index ESHA codes by primary food for fast lookup
    print("indexing ESHA codes by primary food", flush=True)
    esha_by_primary: dict[str, list[tuple[str, str, set]]] = {}
    for _, r in esha.iterrows():
        primary = r["_primary"]
        if not primary:
            continue
        esha_by_primary.setdefault(primary, []).append((r["code"], r["description"], set(r["_tokens"])))

    print(f"  distinct primary food tokens in ESHA: {len(esha_by_primary):,}", flush=True)

    # Pass K: import shared subtype + filler helpers from matcher
    from match_esha_to_products import subtype_compatible as _subtype_compat, GENERIC_FILLER_TOKENS as _FILLER  # noqa: E402

    def best_replacement(p_tokens: list[str], p_primary: str, target_family: str | None = None) -> tuple[str | None, str | None, float]:
        candidates = esha_by_primary.get(p_primary, [])
        if not candidates:
            return None, None, 0.0
        ptoks = set(p_tokens)
        best_score = -1.0
        best_code = None
        best_desc = None
        for code, desc, ctoks in candidates:
            # Pass K.3 — subtype gate (only when target family is known/derivable)
            if target_family and not _subtype_compat(ptoks, ctoks, target_family):
                continue
            shared = ptoks & ctoks
            if not shared:
                continue
            matched_score = sum(token_weight.get(t, 0.5) for t in shared)
            extra = (ctoks - ptoks) - _FILLER
            overspec = 0.35 * sum(token_weight.get(t, 0.5) for t in extra)
            overspec = min(overspec, 0.6 * matched_score)
            s = matched_score - overspec
            if s > best_score:
                best_score = s
                best_code = code
                best_desc = desc
        return best_code, best_desc, max(best_score, 0.0)

    print("computing replacement ESHA codes for mismatches", flush=True)
    sub = v3[mismatch].copy()
    repl = sub.apply(
        lambda r: best_replacement(r["_p_tokens"], r["_p_primary"]),
        axis=1,
        result_type="expand",
    )
    repl.columns = ["new_code", "new_description", "new_score"]
    sub = pd.concat([sub.reset_index(drop=True), repl.reset_index(drop=True)], axis=1)
    found = sub["new_code"].notna()
    print(f"  found replacement: {found.sum():,}", flush=True)
    print(f"  no replacement candidate: {(~found).sum():,}", flush=True)

    # Filter to actual changes (skip if replacement happens to be same as current)
    sub["is_change"] = sub["new_code"] != sub["best_esha_code"]
    apply_set = sub[found & sub["is_change"]].copy()
    print(f"  rows to actually change: {len(apply_set):,}", flush=True)

    print("applying to v4 CSV", flush=True)
    v4 = v3.drop(columns=[c for c in v3.columns if c.startswith("_")]).copy()
    v4_indexed = v4.set_index("gtin_upc")
    apply_indexed = apply_set.set_index("gtin_upc")

    diff_rows = []
    for gtin in v4_indexed.index.intersection(apply_indexed.index):
        prop = apply_indexed.loc[gtin]
        if isinstance(prop, pd.DataFrame):
            prop = prop.iloc[0]
        old_code = v4_indexed.at[gtin, "best_esha_code"]
        old_desc = v4_indexed.at[gtin, "best_esha_description"]
        old_family = v4_indexed.at[gtin, "best_esha_family"]
        new_code = str(prop["new_code"]).split(".")[0]
        new_desc = str(prop["new_description"])
        v4_indexed.at[gtin, "best_esha_code"] = new_code
        v4_indexed.at[gtin, "best_esha_description"] = new_desc
        # Family stays the same — primary food is sub-family discrimination
        v4_indexed.at[gtin, "assignment_source"] = "healed_v0.2_j_primary_food"
        diff_rows.append({
            "gtin_upc": gtin,
            "product_description": v4_indexed.at[gtin, "product_description"],
            "product_primary": str(prop["_p_primary"]),
            "old_esha_code": old_code,
            "old_esha_description": old_desc,
            "old_esha_primary": str(prop["_e_primary"]),
            "new_esha_code": new_code,
            "new_esha_description": new_desc,
        })

    diff_df = pd.DataFrame(diff_rows)
    diff_df.to_csv(OUT_MISMATCHES, index=False)
    print(f"  diff rows: {len(diff_df):,}  -> {OUT_MISMATCHES.relative_to(ROOT)}", flush=True)

    v4 = v4_indexed.reset_index()[v3.drop(columns=[c for c in v3.columns if c.startswith("_")]).columns.tolist()]
    v4.to_csv(V4_CSV, index=False)
    print(f"  wrote {V4_CSV.relative_to(ROOT)}", flush=True)

    summary = {
        "v3_total":                int(n),
        "rows_with_both_primaries": int(has_both.sum()),
        "primary_food_mismatches":  int(mismatch.sum()),
        "replacements_found":       int(found.sum()),
        "replacements_applied":     int(len(diff_df)),
        "v4_assignments": int((v4["best_esha_code"].astype(str).str.strip() != "").sum()),
    }
    OUT_BASELINE.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
