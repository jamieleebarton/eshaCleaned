#!/usr/bin/env python3
"""Generate FDC path-alignment outputs.

Scans every row across the three downstream corpora (Walmart/Kroger,
SR28/FNDDS, recipe ingredients), finds every `canonical_path` that is
NOT in the FDC universe, and emits three artifacts:

  1. recipe_pricing/expand_fdc_rewrites.csv          — auto rewrite rules
  2. recipe_pricing/expand_fdc_rewrites_review.csv   — manual triage queue
  3. retail_mapper/v2/synthetic_taxonomy_anchors.csv — new FDC leaves to add

Path resolution strategy (in order):

  A. Non-food top-level prefix   →  route to the matching `Non-Food > <X>` sentinel
                                    (8 sentinel anchors added to FDC).
  B. Spirits / liqueur prefix    →  route to one of the 16 new `Beverage > Spirits > X`
                                    leaves (added to FDC).
  C. parent_strip                →  drop the leaf if the parent is already in FDC.
  D. leaf_match_unique           →  the leaf segment appears as the leaf of exactly
                                    one FDC path → snap to that.
  E. leaf_weighted_jaccard       →  best FDC path by Jaccard with a leaf-overlap bonus,
                                    score ≥ 0.66 = auto, 0.40-0.66 = review.
  F. propose_new_leaf            →  high-volume out-of-FDC path with no good match;
                                    surfaced for the user to confirm a new FDC leaf.
  G. manual_review               →  everything else.

Every auto rule's `new_path` is verified to exist in the FDC universe (FDC original
+ Non-Food sentinels + Spirits leaves added by this run).
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
OUT_AUTO = ROOT / "recipe_pricing" / "expand_fdc_rewrites.csv"
OUT_REVIEW = ROOT / "recipe_pricing" / "expand_fdc_rewrites_review.csv"
OUT_ANCHORS = ROOT / "retail_mapper" / "v2" / "synthetic_taxonomy_anchors.csv"

# Read from before-fdc-align snapshots when present so the generator is
# idempotent: rerunning after cleanup must not lose the propose_new_leaf
# anchors. Falls back to live files if snapshots are missing.
def _snap_or_live(p: Path) -> Path:
    snap = p.with_suffix(".before-fdc-align.csv")
    return snap if snap.exists() else p

CORPORA = [
    (_snap_or_live(ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_v2.csv"),
     "title", "walmart_kroger"),
    (_snap_or_live(ROOT / "recipe_pricing" / "output" / "sr28_fndds_taxonomy_v2.csv"),
     "title", "sr28_fndds"),
    (_snap_or_live(ROOT / "recipe_mapper" / "v1" / "output" / "ingredient_full_audit.csv"),
     "item", "ingredients"),
]

# --- Non-food routing ---------------------------------------------------------

# Map: out-of-FDC top-level prefix → Non-Food sentinel sub-leaf.
NON_FOOD_PREFIX_TO_SENTINEL = {
    "Non-Food":                  "Non-Food > Other",
    "Nonfood":                   "Non-Food > Other",
    "Other":                     "Non-Food > Other",
    "Pet":                       "Non-Food > Pet",
    "Pet Care":                  "Non-Food > Pet",
    "Pet Food":                  "Non-Food > Pet",
    "Personal Care":             "Non-Food > Personal Care",
    "Bath & Body":               "Non-Food > Personal Care",
    "Oral Care":                 "Non-Food > Personal Care",
    "Hair Care":                 "Non-Food > Personal Care",
    "Skin Care":                 "Non-Food > Personal Care",
    "Beauty":                    "Non-Food > Beauty",
    "Beauty & Personal Care":    "Non-Food > Beauty",
    "Health & Beauty":           "Non-Food > Beauty",
    "Cosmetics":                 "Non-Food > Beauty",
    "Household":                 "Non-Food > Household",
    "Home":                      "Non-Food > Household",
    "Home & Garden":             "Non-Food > Household",
    "Cleaning":                  "Non-Food > Household",
    "Cleaning Supplies":         "Non-Food > Household",
    "Laundry":                   "Non-Food > Household",
    "Health & Wellness":         "Non-Food > Health & Wellness",
    "Wellness":                  "Non-Food > Health & Wellness",
    "Vitamins & Supplements":    "Non-Food > Health & Wellness",
    "Sports & Wellness":         "Non-Food > Health & Wellness",
    "Sports":                    "Non-Food > Health & Wellness",
    "Sports Nutrition":          "Non-Food > Health & Wellness",
    "Kitchen":                   "Non-Food > Kitchen & Dining",
    "Kitchen & Dining":          "Non-Food > Kitchen & Dining",
    "Dining":                    "Non-Food > Kitchen & Dining",
    "Cookware":                  "Non-Food > Kitchen & Dining",
    "Baking & Cooking Supplies": "Non-Food > Kitchen & Dining",
    "Baking Supplies":           "Non-Food > Kitchen & Dining",
    "Office":                    "Non-Food > Office",
    "Office Supplies":           "Non-Food > Office",
    "Stationery":                "Non-Food > Office",
    "School Supplies":           "Non-Food > Office",
    "Automotive":                "Non-Food > Other",
    "Lawn & Garden":             "Non-Food > Other",
    "Garden":                    "Non-Food > Other",
    "Floral":                    "Non-Food > Other",
    "Hardware":                  "Non-Food > Other",
    "Tools":                     "Non-Food > Other",
    "Toys":                      "Non-Food > Other",
    "Electronics":               "Non-Food > Other",
    "Clothing":                  "Non-Food > Other",
    "Apparel":                   "Non-Food > Other",
}

# All distinct sentinel paths (used to seed FDC + the auto rules).
NON_FOOD_SENTINELS = sorted(set(NON_FOOD_PREFIX_TO_SENTINEL.values()))

# --- Spirits & Liqueur routing ------------------------------------------------

# New FDC leaves under Beverage > Spirits, plus their `product_identity_fixed`
# (used for the synthetic anchor row's identity column).
WINE_LEAVES = [
    ("Beverage > Wine > Red",            "Red Wine"),
    ("Beverage > Wine > White",          "White Wine"),
    ("Beverage > Wine > Rosé",           "Rosé Wine"),
    ("Beverage > Wine > Dessert Wine",   "Dessert Wine"),
    ("Beverage > Wine > Cooking Wine",   "Cooking Wine"),
]

SPIRITS_LEAVES = [
    ("Beverage > Spirits > Vodka",        "Vodka"),
    ("Beverage > Spirits > Rum",          "Rum"),
    ("Beverage > Spirits > Gin",          "Gin"),
    ("Beverage > Spirits > Whiskey",      "Whiskey"),
    ("Beverage > Spirits > Bourbon",      "Bourbon"),
    ("Beverage > Spirits > Scotch",       "Scotch"),
    ("Beverage > Spirits > Tequila",      "Tequila"),
    ("Beverage > Spirits > Mezcal",       "Mezcal"),
    ("Beverage > Spirits > Brandy",       "Brandy"),
    ("Beverage > Spirits > Cognac",       "Cognac"),
    ("Beverage > Spirits > Liqueur",      "Liqueur"),
    ("Beverage > Spirits > Cream Liqueur", "Cream Liqueur"),
    ("Beverage > Spirits > Schnapps",     "Schnapps"),
    ("Beverage > Spirits > Vermouth",     "Vermouth"),
    ("Beverage > Spirits > Bitters",      "Bitters"),
    ("Beverage > Spirits > Aperitif",     "Aperitif"),
]

# Keyword → spirits FDC path. Order matters: most-specific first.
SPIRITS_KEYWORD_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(cream\s*liqueur|baileys|kahlua\s*cream|amarula)\b", re.I), "Beverage > Spirits > Cream Liqueur"),
    (re.compile(r"\bvodka\b", re.I),    "Beverage > Spirits > Vodka"),
    (re.compile(r"\b(gin)\b", re.I),     "Beverage > Spirits > Gin"),
    (re.compile(r"\b(bourbon)\b", re.I), "Beverage > Spirits > Bourbon"),
    (re.compile(r"\b(scotch)\b", re.I),  "Beverage > Spirits > Scotch"),
    (re.compile(r"\b(whiskey|whisky|rye)\b", re.I), "Beverage > Spirits > Whiskey"),
    (re.compile(r"\b(tequila)\b", re.I), "Beverage > Spirits > Tequila"),
    (re.compile(r"\b(mezcal|mescal)\b", re.I), "Beverage > Spirits > Mezcal"),
    (re.compile(r"\b(rum)\b", re.I),     "Beverage > Spirits > Rum"),
    (re.compile(r"\b(cognac|armagnac)\b", re.I), "Beverage > Spirits > Cognac"),
    (re.compile(r"\b(brandy|grappa|pisco|kirsch|kirschwasser)\b", re.I), "Beverage > Spirits > Brandy"),
    (re.compile(r"\b(schnapps)\b", re.I), "Beverage > Spirits > Schnapps"),
    (re.compile(r"\b(vermouth)\b", re.I), "Beverage > Spirits > Vermouth"),
    (re.compile(r"\b(bitters)\b", re.I),  "Beverage > Spirits > Bitters"),
    (re.compile(r"\b(aperitif|aperol|campari|pernod|absinthe|sambuca|ouzo)\b", re.I), "Beverage > Spirits > Aperitif"),
    (re.compile(r"\b(liqueur|liquor|cordial)\b", re.I), "Beverage > Spirits > Liqueur"),
]

# --- Tunables -----------------------------------------------------------------

JACCARD_AUTO = 0.80      # higher bar after switching to content-only tokens
JACCARD_REVIEW = 0.40
NEW_LEAF_MIN_ROWS = 5


def parent_path(p: str) -> str:
    parts = [s.strip() for s in p.split(" > ") if s.strip()]
    return " > ".join(parts[:-1]) if len(parts) > 1 else ""


def leaf_of(p: str) -> str:
    parts = [s.strip() for s in p.split(" > ") if s.strip()]
    return parts[-1] if parts else ""


# Words that describe form/cut/preparation, not identity. Two different species
# both having "Fillets" in the leaf is not evidence they're the same food.
FORM_TOKENS = {
    "fillets", "fillet", "steaks", "steak", "legs", "leg", "chunks",
    "pieces", "slices", "slice", "halves", "half", "whole", "ground",
    "mince", "minced", "diced", "chopped", "shredded", "cubed", "crushed",
    "powder", "powdered", "dried", "fresh", "frozen", "raw", "cooked",
    "roasted", "baked", "fried", "boiled", "smoked", "tail", "tails",
    "claws", "meat", "rack", "ribs", "strips", "strip",
}

STOP_TOKENS = {
    "the", "a", "an", "of", "and", "with", "in", "on", "for", "or", "to",
}


def tokens_of(p: str) -> set[str]:
    return {t.strip().lower() for t in re.split(r"[\s>&]+", p) if t.strip()}


def content_tokens(text: str) -> set[str]:
    """Identity-bearing words from a string — excludes form/cut/stop tokens."""
    raw = {t.strip().lower() for t in re.split(r"[\s>&]+", text) if t.strip()}
    return {t for t in raw if t not in FORM_TOKENS and t not in STOP_TOKENS}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def score_candidate(out_path: str, fdc_path: str) -> float:
    """Content-token Jaccard. Form tokens (fillets/steaks/legs) are stripped first
    so two different species don't match just because they share form."""
    return jaccard(content_tokens(out_path), content_tokens(fdc_path))


def main() -> int:
    # 1. Load FDC universe
    fdc_paths: set[str] = set()
    fdc_leaf_to_paths: defaultdict[str, list[str]] = defaultdict(list)
    with AUDIT.open() as f:
        for row in csv.DictReader(f):
            cp = (row.get("canonical_path") or "").strip()
            if not cp or cp in fdc_paths:
                continue
            fdc_paths.add(cp)
            fdc_leaf_to_paths[leaf_of(cp).lower()].append(cp)
    print(f"FDC universe: {len(fdc_paths):,} paths", file=sys.stderr)

    # Augment universe with synthetic anchors that THIS run will add to FDC.
    augmented = set(fdc_paths)
    augmented.update(NON_FOOD_SENTINELS)
    augmented.update(p for p, _ in SPIRITS_LEAVES)
    augmented.update(p for p, _ in WINE_LEAVES)
    fdc_leaf_to_paths_aug = defaultdict(list, fdc_leaf_to_paths)
    for p in NON_FOOD_SENTINELS + [s[0] for s in SPIRITS_LEAVES] + [w[0] for w in WINE_LEAVES]:
        fdc_leaf_to_paths_aug[leaf_of(p).lower()].append(p)

    # 2. Stream the corpora
    out_of_fdc: defaultdict[str, dict] = defaultdict(
        lambda: {"row_count": 0, "samples": [], "sources": Counter()}
    )
    total_rows = 0
    for p, item_field, label in CORPORA:
        if not p.exists():
            print(f"  skip missing corpus: {p}", file=sys.stderr)
            continue
        n = 0
        with p.open() as f:
            for row in csv.DictReader(f):
                total_rows += 1
                n += 1
                cp = (row.get("canonical_path") or "").strip()
                if not cp or cp in augmented:
                    continue
                rec = out_of_fdc[cp]
                rec["row_count"] += 1
                rec["sources"][label] += 1
                if len(rec["samples"]) < 5:
                    item = (row.get(item_field) or "").strip()
                    if item and item not in rec["samples"]:
                        rec["samples"].append(item)
        print(f"  scanned {label}: {n:,} rows", file=sys.stderr)
    print(f"total rows scanned: {total_rows:,}", file=sys.stderr)
    print(f"distinct out-of-augmented-FDC paths: {len(out_of_fdc):,}", file=sys.stderr)

    fdc_paths_list = list(augmented)

    # Build a vocabulary of content tokens across all FDC leaves — used to
    # detect "true gap" leaves where the LLM's identity-word never appears
    # anywhere in FDC.
    fdc_leaf_content_vocab: set[str] = set()
    for fp in fdc_paths_list:
        fdc_leaf_content_vocab.update(content_tokens(leaf_of(fp)))

    # 3. Resolve each path
    auto_rows: list[dict] = []
    review_rows: list[dict] = []

    for cp, rec in sorted(out_of_fdc.items(), key=lambda kv: -kv[1]["row_count"]):
        cp_top = cp.split(" > ")[0].strip()
        cp_leaf = leaf_of(cp).lower()
        cp_parent = parent_path(cp)
        sample_blob = " | ".join(rec["samples"])

        proposal: str | None = None
        source: str | None = None
        score = 0.0

        # A. Non-food prefix routing
        if cp_top in NON_FOOD_PREFIX_TO_SENTINEL:
            proposal = NON_FOOD_PREFIX_TO_SENTINEL[cp_top]
            source = "non_food_prefix"
            score = 1.0

        # B. Spirits / liqueur keyword routing
        if proposal is None:
            for pat, target in SPIRITS_KEYWORD_RULES:
                if pat.search(cp) or pat.search(sample_blob):
                    proposal = target
                    source = "spirits_keyword"
                    score = 1.0
                    break

        # C. parent_strip
        if proposal is None and cp_parent and cp_parent in augmented:
            proposal = cp_parent
            source = "parent_strip"
            score = 1.0

        # D. leaf_match_unique
        if proposal is None:
            cands = [c for c in fdc_leaf_to_paths_aug.get(cp_leaf, []) if c != cp]
            if len(cands) == 1:
                proposal = cands[0]
                source = "leaf_match_unique"
                score = 0.95

        # E. content-token Jaccard against entire FDC universe
        if proposal is None:
            best, best_sc = None, -1.0
            for fp in fdc_paths_list:
                sc = score_candidate(cp, fp)
                if sc > best_sc:
                    best, best_sc = fp, sc
            proposal, source, score = best, "content_jaccard", best_sc

        # Vocabulary-gap signal: LLM's leaf names a thing whose identity word
        # never appears anywhere in FDC's leaf vocabulary. Strong "new leaf" signal.
        leaf_content = content_tokens(leaf_of(cp))
        is_vocab_gap = bool(leaf_content) and not (leaf_content & fdc_leaf_content_vocab)

        out_row = {
            "old_path": cp,
            "new_path": proposal or "",
            "source": source,
            "confidence": f"{score:.3f}",
            "row_count": rec["row_count"],
            "sources": ",".join(f"{k}={v}" for k, v in rec["sources"].most_common()),
            "samples": sample_blob,
        }

        # Classify
        if source in ("non_food_prefix", "spirits_keyword", "parent_strip", "leaf_match_unique"):
            out_row["status"] = "auto"
            auto_rows.append(out_row)
        elif source == "content_jaccard" and score >= JACCARD_AUTO and proposal in augmented and not is_vocab_gap:
            out_row["status"] = "auto"
            auto_rows.append(out_row)
        else:
            if is_vocab_gap and rec["row_count"] >= NEW_LEAF_MIN_ROWS:
                out_row["status"] = "propose_new_leaf"
            elif rec["row_count"] >= NEW_LEAF_MIN_ROWS and score < JACCARD_REVIEW:
                out_row["status"] = "propose_new_leaf"
            elif score >= JACCARD_REVIEW:
                out_row["status"] = "review_low_confidence_match"
            else:
                out_row["status"] = "review_no_match"
            review_rows.append(out_row)

    # 4. Validate auto targets
    bad = [r for r in auto_rows if r["new_path"] not in augmented]
    if bad:
        print(f"ERROR: {len(bad)} auto rules have non-augmented-FDC targets", file=sys.stderr)
        for r in bad[:10]:
            print(f"  {r['old_path']} → {r['new_path']}", file=sys.stderr)
        return 2

    # 5. Write outputs

    # 5a. Auto rules
    fieldnames = [
        "old_path", "new_path", "source", "confidence",
        "row_count", "sources", "samples", "status",
    ]
    OUT_AUTO.parent.mkdir(parents=True, exist_ok=True)
    with OUT_AUTO.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(auto_rows)

    # 5b. Review queue (with a `decision` column for the user)
    # Sort: status first (propose_new_leaf, review_low_confidence_match, review_no_match),
    # then by row_count desc within each status. High-impact rows surface at the top.
    status_rank = {"propose_new_leaf": 0, "review_low_confidence_match": 1, "review_no_match": 2}
    review_sorted = sorted(
        review_rows,
        key=lambda r: (status_rank.get(r["status"], 99), -int(r["row_count"])),
    )
    with OUT_REVIEW.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames + ["decision"])
        w.writeheader()
        for r in review_sorted:
            r2 = dict(r)
            # Pre-fill propose_new_leaf rows with a suggested new path = the LLM's path itself
            if r["status"] == "propose_new_leaf":
                r2["decision"] = f"add_as_new_fdc_leaf:{r['old_path']}"
            else:
                r2["decision"] = ""
            w.writerow(r2)

    # 5c. Synthetic taxonomy anchors — Non-Food sentinels + Spirits leaves
    # + every `propose_new_leaf` row (auto-accepted as new FDC leaves).
    with OUT_ANCHORS.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "fdc_id", "title", "branded_food_category",
            "canonical_path", "canonical_label", "product_identity_fixed",
            "consensus_source", "note",
        ])
        for sentinel in NON_FOOD_SENTINELS:
            slug = sentinel.split(" > ")[-1].lower().replace(" & ", "_").replace(" ", "_")
            ident = sentinel.split(" > ")[-1]
            w.writerow([
                f"SYNTH:nonfood_{slug}",
                f"{sentinel} (taxonomy anchor)",
                "",
                sentinel, ident, ident,
                "synthetic_taxonomy_anchor",
                "Non-food sentinel — products under this path do not join FDC retail.",
            ])
        for path, identity in SPIRITS_LEAVES:
            slug = identity.lower().replace(" ", "_")
            w.writerow([
                f"SYNTH:spirits_{slug}",
                f"{path} (taxonomy anchor)",
                "",
                path, identity, identity,
                "synthetic_taxonomy_anchor",
                "Distilled spirits / liqueur — new retail leaf.",
            ])
        for path, identity in WINE_LEAVES:
            slug = identity.lower().replace(" ", "_")
            w.writerow([
                f"SYNTH:wine_{slug}",
                f"{path} (taxonomy anchor)",
                "",
                path, identity, identity,
                "synthetic_taxonomy_anchor",
                "Wine subtype — new retail leaf.",
            ])
        # Auto-accept each propose_new_leaf as a new FDC leaf at the LLM's path.
        seen_new_leaves: set[str] = set()
        for r in review_rows:
            if r["status"] != "propose_new_leaf":
                continue
            new_path = r["old_path"]
            if new_path in seen_new_leaves:
                continue
            seen_new_leaves.add(new_path)
            ident = leaf_of(new_path)
            slug = re.sub(r"[^a-z0-9]+", "_", ident.lower()).strip("_")
            w.writerow([
                f"SYNTH:gap_{slug}",
                f"{new_path} (taxonomy anchor)",
                "",
                new_path, ident, ident,
                "synthetic_taxonomy_anchor",
                f"Vocabulary gap auto-accepted ({r['row_count']} corpus rows).",
            ])

    # 6. Summary
    by_source = Counter(r["source"] for r in auto_rows)
    by_status = Counter(r["status"] for r in review_rows)
    auto_rows_total = sum(r["row_count"] for r in auto_rows)
    review_rows_total = sum(r["row_count"] for r in review_rows)
    print()
    print(f"AUTO RULES: {len(auto_rows):,} unique paths → {OUT_AUTO}")
    print(f"  covers {auto_rows_total:,} corpus rows")
    for src, n in by_source.most_common():
        print(f"  {src:<26} {n:>5,}")
    print()
    print(f"REVIEW QUEUE: {len(review_rows):,} unique paths → {OUT_REVIEW}")
    print(f"  covers {review_rows_total:,} corpus rows")
    for st, n in by_status.most_common():
        print(f"  {st:<26} {n:>5,}")
    print()
    print(f"SYNTHETIC ANCHORS: {len(NON_FOOD_SENTINELS) + len(SPIRITS_LEAVES)} new FDC leaves → {OUT_ANCHORS}")
    print(f"  Non-Food sentinels: {len(NON_FOOD_SENTINELS)}")
    print(f"  Spirits leaves:     {len(SPIRITS_LEAVES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
