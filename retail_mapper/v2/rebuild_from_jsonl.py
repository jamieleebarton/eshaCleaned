#!/usr/bin/env python3
"""Rebuild full_corpus_audit.csv from DeepSeek jsonl baseline + replay legitimate session fix logs.

Stages (matches plan):
  1. Parse full_corpus.live.jsonl line-by-line → dict keyed on fdc_id.
  2. Inner-join with current full_corpus_audit.csv to pull FNDDS/ESHA/SR28/title/ingredients data.
  3. Apply adjudication_decisions.jsonl borderline-case overrides.
  4. Replay session fix logs in chronological order (mtime). Skip destructive ones.
  5. Final BFC-family validation.
  6. Write new full_corpus_audit.csv.

Skips destructive logs:
  - fndds_consolidation_apply_log.csv
  - wreckage_recovery_log.csv
  - facet_path_build_log.csv (superseded)

Memory: streams the 892MB jsonl line-by-line; loads current 313MB CSV once.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from collections import Counter

V2 = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2")
JSONL = V2 / "full_corpus.live.jsonl"
ADJUDICATION = V2 / "adjudication_decisions.jsonl"
CURRENT_AUDIT = V2 / "full_corpus_audit.csv"
NEW_AUDIT = V2 / "full_corpus_audit.csv.rebuild"
DIFF_OUT = V2 / "recovery_diff.csv"

csv.field_size_limit(sys.maxsize)

# === Schema target (matches existing audit's 35 columns) ===
COLUMNS = [
    "fdc_id", "title", "branded_food_category", "retail_type",
    "category_path_original", "category_path_fixed", "path_fixer_applied",
    "product_identity_original", "product_identity_fixed", "fixer_applied",
    "canonical_path", "canonical_label",
    "variant", "flavor", "form_texture_cut", "processing_storage",
    "claims", "components_count", "components",
    "confidence", "mint_required", "review_flags", "rationale",
    "modifier", "retail_leaf_path",
    "fndds_code", "fndds_desc", "sr28_code", "sr28_desc",
    "esha_code", "esha_desc", "match_source", "match_score",
    "matched_key", "portions_json",
]

# === Logs to replay (chronological will be derived from mtime at runtime) ===
DESTRUCTIVE_LOGS = {
    "fndds_consolidation_apply_log.csv",
    "wreckage_recovery_log.csv",
    "facet_path_build_log.csv",  # superseded by facet_rebuild_v2_log.csv
}

REPLAYABLE_LOGS = [
    "consolidate_milk_log.csv",
    "consolidate_all_duplicates_log.csv",
    "fix_tea_paths_log.csv",
    "fix_nut_butters_log.csv",
    "fix_nut_butters_v2_log.csv",
    "fix_milk_percent_log.csv",
    "fix_mexican_blend_log.csv",
    "restructure_cheese_log.csv",
    "restructure_meat_seafood_log.csv",
    "apply_structural_duplicates_log.csv",
    "apply_synonyms_log.csv",
    "dedupe_adjacent_segments_log.csv",
    "strip_parent_echo_log.csv",
    "restore_flavors_log.csv",
    "restore_flavors_extended_log.csv",
    "fix_baking_mixes_log.csv",
    "cleanup_baking_mixes_log.csv",
    "comprehensive_cleanup_log.csv",
    "fix_bfc_families_log.csv",
    "comprehensive_bfc_align_log.csv",
    "facet_rebuild_v2_log.csv",
    "facet_enrich_shallow_log.csv",
    "insert_product_identity_log.csv",
    "comprehensive_milk_v2_log.csv",
    "fix_creamer_log.csv",
    "fix_tea_paths_log.csv",
]


def list_to_pipe(v) -> str:
    """List → pipe-separated string (matches CSV format)."""
    if v is None: return ""
    if isinstance(v, list): return " | ".join(str(x) for x in v if x)
    if isinstance(v, bool): return "true" if v else "false"
    return str(v)


def parse_raw(raw_str: str) -> dict:
    """Parse the 'raw' JSON string from a jsonl row."""
    try:
        return json.loads(raw_str)
    except Exception:
        return {}


def stream_jsonl(path: Path):
    """Yield (fdc_id, raw_dict, top_level_dict) per line."""
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line: continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            fdc = str(row.get("fdc_id", "")).strip()
            if not fdc: continue
            raw = parse_raw(row.get("raw", "{}"))
            yield fdc, raw, row


def build_baseline() -> dict:
    """Pass 1: build fdc_id → record dict from DeepSeek jsonl baseline."""
    print(f"  Stage 1: Parsing {JSONL.name} (892MB, 462,695 records)...")
    t0 = time.time()
    baseline = {}
    n = 0
    for fdc, raw, top in stream_jsonl(JSONL):
        rec = {
            "fdc_id": fdc,
            "title": top.get("title", "") or raw.get("title", ""),
            "branded_food_category": top.get("branded_food_category", ""),
            "retail_type": raw.get("retail_type", "single"),
            "category_path_original": raw.get("category_path", ""),
            "category_path_fixed": raw.get("category_path", ""),
            "path_fixer_applied": "",
            "product_identity_original": raw.get("product_identity", ""),
            "product_identity_fixed": raw.get("product_identity", ""),
            "fixer_applied": "",
            "canonical_path": raw.get("canonical_path", ""),
            "canonical_label": raw.get("canonical_label", ""),
            "variant": list_to_pipe(raw.get("variant", [])),
            "flavor": list_to_pipe(raw.get("flavor", [])),
            "form_texture_cut": list_to_pipe(raw.get("form_texture_cut", [])),
            "processing_storage": list_to_pipe(raw.get("processing_storage", [])),
            "claims": list_to_pipe(raw.get("claims", [])),
            "components": list_to_pipe(raw.get("components", [])),
            "components_count": str(len(raw.get("components", []) or [])),
            "confidence": str(raw.get("confidence", "")),
            "mint_required": list_to_pipe(raw.get("mint_required", "")),
            "review_flags": list_to_pipe(raw.get("review_flags", [])),
            "rationale": raw.get("rationale", ""),
            "modifier": "",  # built later from variant/flavor if needed
            "retail_leaf_path": raw.get("canonical_path", ""),  # default to canonical
        }
        baseline[fdc] = rec
        n += 1
        if n % 50000 == 0:
            print(f"    {n:,} records parsed, {time.time()-t0:.0f}s elapsed")
    print(f"    Stage 1 done: {n:,} records in {time.time()-t0:.0f}s")
    return baseline


def merge_lookup_columns(baseline: dict) -> int:
    """Pass 2: pull FNDDS/ESHA/SR28/match data from current audit by fdc_id."""
    print(f"  Stage 2: Merging FNDDS/ESHA/SR28 columns from {CURRENT_AUDIT.name}...")
    t0 = time.time()
    n_matched = 0
    n_skipped = 0
    LOOKUP_COLS = [
        "fndds_code", "fndds_desc", "sr28_code", "sr28_desc",
        "esha_code", "esha_desc", "match_source", "match_score",
        "matched_key", "portions_json",
    ]
    with CURRENT_AUDIT.open(encoding="utf-8") as fh:
        rdr = csv.DictReader(fh)
        for r in rdr:
            fdc = (r.get("fdc_id") or "").strip()
            if fdc in baseline:
                rec = baseline[fdc]
                for col in LOOKUP_COLS:
                    rec[col] = r.get(col, "") or ""
                # Also pull title from current if jsonl was missing it
                if not rec.get("title"):
                    rec["title"] = r.get("title", "") or ""
                if not rec.get("branded_food_category"):
                    rec["branded_food_category"] = r.get("branded_food_category", "") or ""
                n_matched += 1
            else:
                n_skipped += 1
    # Fill missing lookup columns with empty strings
    for fdc, rec in baseline.items():
        for col in LOOKUP_COLS:
            rec.setdefault(col, "")
    print(f"    Stage 2 done: {n_matched:,} matched, {n_skipped:,} unmatched in current audit, {time.time()-t0:.0f}s")
    return n_matched


def apply_adjudication(baseline: dict) -> int:
    """Stage 3: apply adjudication_decisions.jsonl borderline-case overrides."""
    print(f"  Stage 3: Applying {ADJUDICATION.name}...")
    if not ADJUDICATION.exists():
        print("    no adjudication file — skipping")
        return 0
    n_applied = 0
    n_skipped = 0
    with ADJUDICATION.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line: continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            decision = row.get("decision", "")
            fdc = str(row.get("fdc_id", "")).strip()
            if fdc not in baseline:
                n_skipped += 1
                continue
            if decision == "proposed":
                proposed = row.get("centroid_proposed_path", "")
                if proposed:
                    baseline[fdc]["canonical_path"] = proposed
                    baseline[fdc]["retail_leaf_path"] = proposed
                    n_applied += 1
    print(f"    Stage 3 done: {n_applied:,} adjudication overrides applied, {n_skipped:,} skipped (fdc not in baseline)")
    return n_applied


def replay_log(baseline: dict, log_path: Path) -> tuple[int, int]:
    """Replay one log file. Apply unconditionally — trust the session's intent.
    For any fdc_id in the log, set canonical_path = new_cp (and rlp accordingly).
    Chronological replay order ensures latest log wins."""
    n_applied = 0
    n_skipped = 0
    with log_path.open(encoding="utf-8") as fh:
        rdr = csv.DictReader(fh)
        cols = rdr.fieldnames or []
        cp_new_col = next((c for c in cols if c in ("new_cp", "new_canonical", "new_path")), None)
        rlp_new_col = next((c for c in cols if c in ("new_rlp", "new_retail_leaf")), None)
        for r in rdr:
            fdc = (r.get("fdc_id") or "").strip()
            if not fdc or fdc not in baseline:
                n_skipped += 1
                continue
            rec = baseline[fdc]
            new_cp = (r.get(cp_new_col) if cp_new_col else "") or ""
            new_cp = new_cp.strip()
            new_rlp = (r.get(rlp_new_col) if rlp_new_col else "") or ""
            new_rlp = new_rlp.strip()
            applied = False
            if new_cp:
                rec["canonical_path"] = new_cp
                applied = True
            if new_rlp:
                rec["retail_leaf_path"] = new_rlp
                applied = True
            elif new_cp:
                # Log only had cp; mirror to rlp
                rec["retail_leaf_path"] = new_cp
            if applied:
                n_applied += 1
    return n_applied, n_skipped


def replay_all_logs(baseline: dict) -> dict:
    """Stage 4: Replay all replayable logs, sorted chronologically by mtime."""
    print(f"  Stage 4: Replaying session fix logs (chronological by mtime)...")
    log_paths = []
    for name in REPLAYABLE_LOGS:
        p = V2 / name
        if p.exists():
            log_paths.append(p)
    # Skip destructive
    log_paths = [p for p in log_paths if p.name not in DESTRUCTIVE_LOGS]
    # Sort by mtime ascending
    log_paths.sort(key=lambda p: p.stat().st_mtime)
    print(f"    {len(log_paths)} logs to replay")
    stats = {}
    for p in log_paths:
        t0 = time.time()
        n_app, n_skp = replay_log(baseline, p)
        stats[p.name] = (n_app, n_skp)
        print(f"    {p.name:<45}  applied={n_app:>6,}  skipped={n_skp:>6,}  {time.time()-t0:.0f}s")
    return stats


def final_bfc_validation(baseline: dict) -> int:
    """Stage 5: per-SKU BFC family check; route remaining wrong-family SKUs to BFC's expected family."""
    print(f"  Stage 5: Final BFC-family validation...")
    BFC_TARGETS = {
        'Processed Cereal Products':  ('Pantry', 'Pantry > Cereal'),
        'Cereal':                     ('Pantry', 'Pantry > Cereal'),
        'Frozen Vegetables':          ('Frozen', 'Frozen > Vegetables'),
        'Frozen Fish & Seafood':      ('Frozen', 'Frozen > Prepared Seafood'),
        'Frozen Fruit':               ('Frozen', 'Frozen > Fruit'),
        'Frozen Dinners & Entrees':   ('Frozen', 'Frozen > Single Entrees'),
        'Frozen Pizza':               ('Frozen', 'Frozen > Pizza'),
        "Frozen Appetizers & Hors D'oeuvres": ('Frozen', 'Frozen > Appetizers'),
        'Ice Cream & Frozen Yogurt':  ('Frozen', 'Frozen > Ice Cream'),
        'Frozen Bacon, Sausages & Ribs':('Frozen', 'Frozen > Breakfast'),
        'Milk':                       ('Dairy', 'Dairy > Milk'),
        'Yogurt':                     ('Dairy', 'Dairy > Yogurt'),
        'Cheese':                     ('Dairy', 'Dairy > Cheese'),
        'Butter & Spread':            ('Dairy', 'Dairy > Butter'),
        'Cream/Cream Substitutes':    ('Dairy', 'Dairy > Cream > Coffee Creamer'),
        'Eggs':                       ('Dairy', 'Dairy > Eggs'),
        'Plant Based Milk':           ('Beverage', 'Beverage > Plant Milk'),
        'Cake, Cookie & Cupcake Mixes':('Pantry', 'Pantry > Baking Mixes > Cake Mix'),
        'Bread & Muffin Mixes':       ('Pantry', 'Pantry > Baking Mixes > Bread Mix'),
        'Cakes, Cupcakes, Snack Cakes':('Bakery', 'Bakery > Cake'),
        'Bread & Buns':               ('Bakery', 'Bakery > Bread'),
        'Cookies & Biscuits':         ('Snack', 'Snack > Cookies'),
        'Tortillas, Wraps & Pita Bread':('Bakery', 'Bakery > Tortillas'),
        'Bagels, Muffins, Doughnuts & Pastries':('Bakery', 'Bakery > Pastry'),
        'Pies':                       ('Bakery', 'Bakery > Pie'),
        'Pasta by Shape & Type':      ('Pantry', 'Pantry > Pasta'),
        'Pickles, Olives, Peppers & Relishes':('Pantry', 'Pantry > Pickles'),
        'Pre-Packaged Fruit & Vegetables':('Produce', 'Produce > Vegetables'),
        'Soda':                       ('Beverage', 'Beverage > Soda'),
        'Tea & Infusions':            ('Beverage', 'Beverage > Tea'),
        'Coffee':                     ('Beverage', 'Beverage > Coffee'),
        'Other Drinks':               ('Beverage', 'Beverage > Drink'),
        'Fruit & Vegetable Juice, Nectars & Fruit Drinks':('Beverage', 'Beverage > Juice'),
        'Bottled Water':              ('Beverage', 'Beverage > Water'),
        'Energy & Sports Drinks':     ('Beverage', 'Beverage > Energy Drinks'),
        'Bacon':                      ('Meat & Seafood', 'Meat & Seafood > Bacon'),
        'Sausages, Hotdogs & Brats':  ('Meat & Seafood', 'Meat & Seafood > Sausage'),
        'Pepperoni, Salami & Cold Cuts':('Meat & Seafood', 'Meat & Seafood > Charcuterie'),
        'Chips, Pretzels & Snacks':   ('Snack', 'Snack > Chips'),
        'Popcorn, Peanuts, Seeds & Related Snacks':('Snack', 'Snack > Nuts'),
        'Candy':                      ('Snack', 'Snack > Candy'),
        'Chocolate':                  ('Snack', 'Snack > Candy > Chocolate Candy'),
        'Snack, Energy & Granola Bars':('Snack', 'Snack > Bars'),
        'Crackers, Crispbreads & Rice Cakes':('Snack', 'Snack > Crackers'),
        'Salad Dressing & Mayonnaise':('Pantry', 'Pantry > Salad Dressings'),
        'Ketchup, Mustard, BBQ & Cheese Sauce':('Pantry', 'Pantry > Sauces & Salsas'),
        'Sauces':                     ('Pantry', 'Pantry > Sauces & Salsas > Sauce'),
        'Seasoning Mixes, Salts, Marinades & Tenderizers':('Pantry', 'Pantry > Spices & Seasonings'),
        'Spices & Seasonings':        ('Pantry', 'Pantry > Spices & Seasonings'),
        'Honey, Jam, Marmalade & Spreads':('Pantry', 'Pantry > Spreads'),
        'Sugar & Sweeteners':         ('Pantry', 'Pantry > Sweeteners'),
        'Cooking Oils':               ('Pantry', 'Pantry > Oil'),
        'Vinegars':                   ('Pantry', 'Pantry > Vinegar'),
        'Olives & Capers':            ('Pantry', 'Pantry > Olives'),
        'Soups':                      ('Pantry', 'Pantry > Soup'),
        'Bouillon & Broth':           ('Pantry', 'Pantry > Bouillon & Broth'),
        'Canned Fruit':               ('Pantry', 'Pantry > Canned Fruit'),
        'Canned Vegetables':          ('Pantry', 'Pantry > Canned Vegetables'),
        'Canned & Bottled Beans':     ('Pantry', 'Pantry > Canned Vegetables > Beans'),
        'Vegetable and Lentil Mixes': ('Pantry', 'Pantry > Canned Vegetables > Beans'),
        'Vegetables  Prepared/Processed':('Pantry', 'Pantry > Canned Vegetables'),
    }
    EQUIV = {
        'Bakery': {'Bakery', 'Snack'},
        'Snack': {'Snack', 'Bakery', 'Pantry'},
        'Frozen': {'Frozen'},
        'Beverage': {'Beverage'},
        'Pantry': {'Pantry'},
        'Dairy': {'Dairy'},
        'Produce': {'Produce', 'Pantry'},
        'Meat & Seafood': {'Meat & Seafood', 'Frozen'},
    }
    # Words that should NEVER be a 2nd-level segment under any family (they're leaves/facets)
    FLAVOR_FACET_WORDS = {
        'lemon','strawberry','blueberry','raspberry','cherry','vanilla','chocolate',
        'banana','peach','pineapple','mango','coconut','apple','orange','grape',
        'lime','almond','hazelnut','pistachio','walnut','pecan','cashew',
        'cinnamon','caramel','maple','honey','mint','peppermint','spearmint',
        'pumpkin','organic','natural','plain','original','whole grain',
        'gluten free','dairy free','sugar free','fat free','low fat','reduced fat',
        'iced','frosted','glazed','crispy','crunchy','soft','baked',
        'mini','bite size','jumbo','large','small',
        'sweetened','unsweetened','plant based','vegan','keto','paleo','probiotic',
        'high protein','hot','medium','mild','spicy','sweet','sour','tangy',
    }

    def title_case(s: str) -> str:
        return ' '.join(w.capitalize() for w in s.replace('_', ' ').split())

    def parse_combined(val: str) -> str:
        if not val: return ''
        parts = [title_case(p.strip()) for p in re.split(r'\s*\|\s*', val.strip()) if p.strip()]
        return ' & '.join(parts) if parts else ''

    def parse_separate(val: str) -> list:
        if not val: return []
        parts = [title_case(p.strip()) for p in re.split(r'\s*\|\s*', val.strip()) if p.strip()]
        return sorted(set(parts))

    def collapse_dupes(segs: list) -> list:
        seen = set(); out = []
        for s in segs:
            k = s.lower()
            if k in seen: continue
            seen.add(k); out.append(s)
        return out

    def build_full_path(family: str, identity: str, rec: dict, existing_leaves: list = None) -> str:
        """Build family > identity > variant > flavor > form > processing > claims (at end).
        TYPE FIRST after family — preserves top-down hierarchy. Claims at leaf for filtering."""
        leaves = []
        if identity:
            leaves.append(title_case(identity))
        if existing_leaves:
            leaves.extend(existing_leaves)
        v = parse_combined(rec.get('variant',''))
        if v: leaves.append(v)
        v = parse_combined(rec.get('flavor',''))
        if v: leaves.append(v)
        v = parse_combined(rec.get('form_texture_cut',''))
        if v: leaves.append(v)
        v = parse_combined(rec.get('processing_storage',''))
        if v: leaves.append(v)
        # Claims at END (separate, alphabetical) — leaf-level filter
        leaves.extend(parse_separate(rec.get('claims','')))
        all_segs = [family] + leaves
        return ' > '.join(collapse_dupes(all_segs))

    # Bean type extraction from FNDDS desc for "Beans" SKUs
    BEAN_TYPE_PATTERNS = [
        (re.compile(r'\bgreat northern\b', re.I), 'Great Northern'),
        (re.compile(r'\bpinto\b', re.I), 'Pinto'),
        (re.compile(r'\bblack bean\b', re.I), 'Black'),
        (re.compile(r'\bkidney\b', re.I), 'Kidney'),
        (re.compile(r'\bnavy\b', re.I), 'Navy'),
        (re.compile(r'\blima\b', re.I), 'Lima'),
        (re.compile(r'\bgarbanzo\b|\bchickpea\b', re.I), 'Garbanzo'),
        (re.compile(r'\bcannellini\b', re.I), 'Cannellini'),
        (re.compile(r'\bblack[- ]eye\b', re.I), 'Black Eyed'),
        (re.compile(r'\brefried\b', re.I), 'Refried'),
        (re.compile(r'\bbaked beans?\b|\bpork and beans?\b', re.I), 'Baked'),
        (re.compile(r'\bgreen beans?\b', re.I), 'Green'),
        (re.compile(r'\bbutter beans?\b', re.I), 'Butter'),
        (re.compile(r'\bsoybean\b|\bedamame\b', re.I), 'Soybeans'),
        (re.compile(r'\bmung\b', re.I), 'Mung'),
        (re.compile(r'\bfava\b', re.I), 'Fava'),
        (re.compile(r'\blentils?\b', re.I), 'Lentils'),
        (re.compile(r'\bcranberry beans?\b', re.I), 'Cranberry'),
    ]

    JERKY_RX = re.compile(r"\b(jerky|biltong|slim jim|jack link|chomps|krave|country archer|oberto|epic provisions)\b", re.I)
    JERKY_STICK_RX = re.compile(r"\b(stick|snack stick|pitmaster\s+(?:bbq\s+)?(?:beef\s+)?steak)\b", re.I)

    def derive_bean_type(rec: dict) -> str:
        blob = (rec.get('fndds_desc') or '') + ' || ' + (rec.get('title') or '')
        for rx, name in BEAN_TYPE_PATTERNS:
            if rx.search(blob):
                return name
        return ''

    n_cross_family = 0
    n_shallow_enriched = 0
    n_flavor_at_d2_fixed = 0
    n_jerky_routed = 0
    n_bean_typed = 0

    for fdc, rec in baseline.items():
        bfc = (rec.get("branded_food_category") or "").strip()
        cp = (rec.get("canonical_path") or "").strip()
        if not cp: continue
        identity = (rec.get("product_identity_fixed") or rec.get("product_identity_original") or "").strip()
        title = (rec.get("title") or "")
        current_family = cp.split(" > ")[0]
        segs = cp.split(" > ")

        # SANDWICH override (title says SANDWICH but path doesn't)
        if re.search(r"\bSANDWICH(ES)?\b", title, re.I) and 'Sandwich' not in cp:
            # Don't override Frozen sandwiches (they're already correctly placed)
            if not cp.startswith('Frozen'):
                flavor = parse_combined(rec.get('flavor','')) or ''
                if flavor:
                    new_cp = f"Meal > Sandwiches > Sandwich > {flavor}"
                else:
                    # Try to extract a meaningful descriptor from title
                    # e.g., "ALMOND BUTTER & STRAWBERRY JAM" stays as a leaf
                    desc = re.split(r'\bSANDWICH', title, maxsplit=1, flags=re.I)[0].strip().rstrip(',').strip()
                    if desc and len(desc) < 80:
                        new_cp = f"Meal > Sandwiches > Sandwich > {title_case(desc)}"
                    else:
                        new_cp = "Meal > Sandwiches > Sandwich"
                rec["canonical_path"] = new_cp
                rec["retail_leaf_path"] = new_cp
                continue

        # ALIMENTARY PASTE — fix wrong "Yam" leaf when title says paste only
        if 'ALIMENTARY PASTE' in title.upper() and cp.startswith('Bakery > Alimentary Paste'):
            new_cp = 'Bakery > Dough > Alimentary Paste'
            rec["canonical_path"] = new_cp
            rec["retail_leaf_path"] = new_cp
            continue

        # JERKY override (title-driven; many BFCs miscategorize jerky)
        if (JERKY_RX.search(title) or JERKY_STICK_RX.search(title)) and 'Jerky' not in cp:
            new_cp = 'Snack > Jerky > Beef'
            if re.search(r"\bturkey\b", title, re.I): new_cp = 'Snack > Jerky > Turkey'
            elif re.search(r"\bpork\b", title, re.I): new_cp = 'Snack > Jerky > Pork'
            elif re.search(r"\bchicken\b", title, re.I): new_cp = 'Snack > Jerky > Chicken'
            rec["canonical_path"] = new_cp
            rec["retail_leaf_path"] = new_cp
            n_jerky_routed += 1
            continue

        # 1. Cross-family correction
        if bfc in BFC_TARGETS:
            expected_family, default_target = BFC_TARGETS[bfc]
            allowed = EQUIV.get(expected_family, {expected_family})
            if current_family not in allowed:
                # Build new path with product_identity + facets
                # Strip default_target's family from leaves to avoid family duplication
                target_segs = default_target.split(" > ")
                target_family = target_segs[0]
                target_extras = target_segs[1:]
                rest_leaves = []
                rest_leaves.extend(target_extras)
                if identity and identity.lower() not in {s.lower() for s in target_extras}:
                    rest_leaves.append(title_case(identity))
                v = parse_combined(rec.get('variant',''))
                if v: rest_leaves.append(v)
                v = parse_combined(rec.get('flavor',''))
                if v: rest_leaves.append(v)
                v = parse_combined(rec.get('form_texture_cut',''))
                if v: rest_leaves.append(v)
                v = parse_combined(rec.get('processing_storage',''))
                if v: rest_leaves.append(v)
                # Claims at END (leaf-level filter)
                rest_leaves.extend(parse_separate(rec.get('claims','')))
                new_cp = ' > '.join(collapse_dupes([target_family] + rest_leaves))
                rec["canonical_path"] = new_cp
                rec["retail_leaf_path"] = new_cp
                n_cross_family += 1
                continue

        # 2. Shallow path enrichment (right family, but ≤2 segments and product_identity available)
        if len(segs) <= 2 and identity:
            family = segs[0]
            existing = segs[1:]
            new_cp = build_full_path(family, identity, rec, existing)
            if new_cp != cp:
                rec["canonical_path"] = new_cp
                if not rec.get("retail_leaf_path") or len((rec.get("retail_leaf_path") or "").split(" > ")) <= 2:
                    rec["retail_leaf_path"] = new_cp
                n_shallow_enriched += 1
                continue

        # 3. Flavor-at-depth-2 fix (e.g., "Bakery > Lemon > Bundt" → "Bakery > Bundt Cake > Lemon")
        if len(segs) >= 2 and segs[1].lower() in FLAVOR_FACET_WORDS and identity:
            if title_case(identity).lower() not in {s.lower() for s in segs}:
                family = segs[0]
                # Move identity in front of flavor segment, claims at end
                rest_with_flavor_demoted = [title_case(identity)]
                rest_with_flavor_demoted += segs[1:]
                v = parse_combined(rec.get('variant',''))
                if v: rest_with_flavor_demoted.append(v)
                v = parse_combined(rec.get('flavor',''))
                if v: rest_with_flavor_demoted.append(v)
                v = parse_combined(rec.get('form_texture_cut',''))
                if v: rest_with_flavor_demoted.append(v)
                v = parse_combined(rec.get('processing_storage',''))
                if v: rest_with_flavor_demoted.append(v)
                rest_with_flavor_demoted.extend(parse_separate(rec.get('claims','')))
                new_cp = ' > '.join(collapse_dupes([family] + rest_with_flavor_demoted))
                rec["canonical_path"] = new_cp
                rec["retail_leaf_path"] = new_cp
                n_flavor_at_d2_fixed += 1

    # 4. Bean-type derivation/correction: for any path under "Beans" parent, set the leaf to FNDDS-derived type
    KNOWN_BEAN_TYPES = {'Pinto','Black','Kidney','Navy','Lima','Garbanzo','Cannellini',
                        'Black Eyed','Refried','Baked','Green','Wax','Butter','Mung',
                        'Fava','Great Northern','Soybeans','Cranberry','Mayocoba','Canary',
                        'Roman','Red','White','Pink','Adzuki','Lentils'}
    for fdc, rec in baseline.items():
        cp = (rec.get("canonical_path") or "").strip()
        # Match paths where second-to-last segment OR last segment is "Beans"
        # OR path is under "Pantry > Canned Vegetables > Beans" with any leaf
        if not cp.startswith("Pantry > Canned Vegetables > Beans"): continue
        bean_type = derive_bean_type(rec)
        if not bean_type: continue
        segs = cp.split(" > ")
        # Find the "Beans" segment index
        try:
            beans_idx = segs.index("Beans")
        except ValueError:
            continue
        # Replace any incorrect bean-type leaf, or append if missing
        if beans_idx + 1 < len(segs):
            current_leaf = segs[beans_idx + 1]
            if current_leaf in KNOWN_BEAN_TYPES and current_leaf != bean_type:
                segs[beans_idx + 1] = bean_type
                new_cp = " > ".join(segs)
                rec["canonical_path"] = new_cp
                rec["retail_leaf_path"] = new_cp
                n_bean_typed += 1
        else:
            # Append bean type
            new_cp = cp + " > " + bean_type
            rec["canonical_path"] = new_cp
            rec["retail_leaf_path"] = new_cp
            n_bean_typed += 1

    # 5a. Reorder claims to consistent position: right after type segment (depth 3)
    # This normalizes paths from log replays that may have claims at end vs middle.
    KNOWN_CLAIMS = {
        'organic', 'plant based', 'gluten free', 'dairy free', 'sugar free',
        'fat free', 'low fat', 'reduced fat', 'lactose free', 'caffeine free',
        'high protein', 'high fiber', 'low sodium', 'no salt added', 'unsweetened',
        'sweetened', 'no sugar added', 'reduced sugar', 'zero sugar', 'low calorie',
        'natural', 'all natural', 'fortified', 'probiotic', 'grass fed', 'free range',
        'cage free', 'wild caught', 'fair trade', 'kosher', 'halal', 'vegan',
        'keto', 'paleo', 'whole grain', 'multi grain', '100% whole grain',
        'non gmo', 'non-gmo', 'no preservatives', 'no artificial flavors',
    }
    n_reordered = 0
    for fdc, rec in baseline.items():
        for col in ("canonical_path", "retail_leaf_path"):
            v = (rec.get(col) or "").strip()
            if not v: continue
            segs = v.split(" > ")
            if len(segs) < 3: continue  # need at least family > type > X to reorder
            # Identify which segs are claims (case-insensitive)
            claim_idxs = [i for i, s in enumerate(segs) if s.lower() in KNOWN_CLAIMS]
            if not claim_idxs: continue
            non_claim_segs = [s for i, s in enumerate(segs) if i not in claim_idxs]
            claim_segs = sorted([segs[i] for i in claim_idxs], key=str.lower)
            # Push claims to END (leaf-level filter): family > type > variant > flavor > form > ... > claims
            new_segs = non_claim_segs + claim_segs
            new_v = " > ".join(new_segs)
            if new_v != v:
                rec[col] = new_v
                n_reordered += 1

    # 5b. Final dedupe pass: collapse case-insensitive duplicate segments
    n_dedupe = 0
    for fdc, rec in baseline.items():
        for col in ("canonical_path", "retail_leaf_path"):
            v = (rec.get(col) or "").strip()
            if not v: continue
            segs = v.split(" > ")
            seen = set(); out = []
            for s in segs:
                k = s.lower()
                if k in seen: continue
                seen.add(k); out.append(s)
            new_v = " > ".join(out)
            if new_v != v:
                rec[col] = new_v
                n_dedupe += 1
    print(f"    Stage 5b: {n_reordered:,} paths reordered (claims to consistent depth)")

    # 5c. Final post-process: unconditional fixes for stubborn known bad patterns
    n_post = 0
    for fdc, rec in baseline.items():
        cp = (rec.get("canonical_path") or "").strip()
        title = (rec.get("title") or "")
        # Alimentary Paste with wrong leaf (Yam etc. from FNDDS code mismatch)
        if 'ALIMENTARY PASTE' in title.upper() and cp.startswith('Bakery > Alimentary Paste'):
            new_cp = 'Bakery > Dough > Alimentary Paste'
            rec["canonical_path"] = new_cp
            rec["retail_leaf_path"] = new_cp
            n_post += 1
            continue
        # Almond/Peanut/Cashew/Hazelnut Butter sandwich misrouted to Bakery > Almond Butter
        if (re.search(r"\bSANDWICH(ES)?\b", title, re.I)
            and re.match(r'^Bakery > (Almond|Peanut|Cashew|Hazelnut|Sunflower|Cookie) Butter', cp)):
            flavor = parse_combined(rec.get('flavor','')) or ''
            desc = re.split(r'\bSANDWICH', title, maxsplit=1, flags=re.I)[0].strip().rstrip(',').strip()
            leaf = title_case(desc)[:80] if desc else (flavor or 'Plain')
            new_cp = f"Meal > Sandwiches > Sandwich > {leaf}"
            rec["canonical_path"] = new_cp
            rec["retail_leaf_path"] = new_cp
            n_post += 1
    if n_post:
        print(f"    Stage 5c: {n_post:,} stubborn-pattern post-fixes")

    print(f"    Stage 5: {n_cross_family:,} cross-family + {n_shallow_enriched:,} shallow-enriched + {n_flavor_at_d2_fixed:,} flavor-at-d2 + {n_jerky_routed:,} jerky + {n_bean_typed:,} bean-typed + {n_dedupe:,} deduped")
    return n_cross_family + n_shallow_enriched + n_flavor_at_d2_fixed + n_jerky_routed + n_bean_typed


def write_output(baseline: dict):
    """Stage 6: write the new audit CSV."""
    print(f"  Stage 6: Writing {NEW_AUDIT.name}...")
    t0 = time.time()
    with NEW_AUDIT.open("w", newline="", encoding="utf-8") as fh:
        wtr = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        wtr.writeheader()
        for fdc in sorted(baseline.keys()):
            wtr.writerow(baseline[fdc])
    print(f"    Wrote {len(baseline):,} rows in {time.time()-t0:.0f}s")
    print(f"    File: {NEW_AUDIT}  ({NEW_AUDIT.stat().st_size/1024/1024:.1f} MB)")


def main():
    print("=" * 70)
    print("Audit Recovery: Rebuild from DeepSeek baseline + replay session fixes")
    print("=" * 70)
    t_start = time.time()

    # Stage 1: DeepSeek jsonl → baseline dict
    baseline = build_baseline()
    print(f"  baseline records: {len(baseline):,}")
    print()

    # Stage 2: pull lookup columns from current audit
    merge_lookup_columns(baseline)
    print()

    # Stage 3: adjudication overrides
    apply_adjudication(baseline)
    print()

    # Stage 4: replay session fix logs in chronological order
    stats = replay_all_logs(baseline)
    print()

    # Stage 5: final BFC validation
    final_bfc_validation(baseline)
    print()

    # Stage 6: write output
    write_output(baseline)

    print()
    print("=" * 70)
    print(f"DONE in {time.time()-t_start:.0f}s. Output: {NEW_AUDIT}")
    print("Review the output, then atomically move:")
    print(f"  mv {NEW_AUDIT} {CURRENT_AUDIT}")
    print("Then commit to git LFS as the recovered checkpoint.")


if __name__ == "__main__":
    main()
