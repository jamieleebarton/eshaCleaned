"""Build canonical PC mappings for ESHA codes (Pass M).

Reads the current product_to_esha_final.csv (trusted observations) plus
esha_cleaned.csv (full ESHA universe), computes canonical PC per ESHA, and
saves to graph/cache/esha_canonical_pcs.json.

Run before re-running the matcher with PC-anchored selection.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEGACY_CSV = ROOT / "implementation" / "output" / "product_to_esha_final.csv"
ESHA_CSV = ROOT / "esha_cleaned.csv"
CACHE_DIR = ROOT / "graph" / "cache"
OUT_PATH = CACHE_DIR / "esha_canonical_pcs.json"

sys.path.insert(0, str(ROOT / "implementation"))
from pc_anchored_assignment import (  # noqa: E402
    load_trusted_pc_mappings, compute_canonical_pcs, save_canonical_pcs,
)
from match_esha_to_products import profile_for  # noqa: E402


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"loading trusted ESHA -> PC observations from {LEGACY_CSV.name}", flush=True)
    obs = load_trusted_pc_mappings(LEGACY_CSV)
    print(f"  trusted observations: {len(obs):,}", flush=True)

    print(f"loading ESHA universe from {ESHA_CSV.name}", flush=True)
    all_esha = []
    with ESHA_CSV.open(newline="", encoding="utf-8-sig", errors="replace") as fh:
        for row in csv.DictReader(fh):
            if "EshaCode" not in row and "Code" in row:
                row = {**row, "EshaCode": row.get("Code", "")}
            profile = profile_for(row)
            if not profile.code or profile.skip_reason:
                continue
            all_esha.append((profile.code.strip(), profile.description, profile.family))
    print(f"  ESHA codes: {len(all_esha):,}", flush=True)

    print("computing canonical PCs", flush=True)
    canonical, pool = compute_canonical_pcs(obs, all_esha)
    print(f"  ESHAs with canonical PC: {len(canonical):,}", flush=True)
    print(f"  PCs with candidate pool: {len(pool):,}", flush=True)

    # Sanity check the bug examples
    print("\n=== Spot-check canonical PC for bug-example ESHAs ===", flush=True)
    for code, label in [
        ("3759", "Adam's Apple, sections, fresh"),
        ("3760", "Adam's Apple, fresh"),
        ("18",   "Milk, chocolate, 2%, with added vit A & D"),
        ("48985", "Almond Butter, crunchy, with roasted flaxseed"),
        ("92688", "Candy, hard, lollipop, with gum"),
        ("12436", "Cereal, granola, Ginger Zing, with cashews"),
        ("4571",  "Nuts, almonds, dry roasted, salted, whole"),
        ("4504",  "Nuts, almonds, whole"),
        ("3006",  "Applesauce, unsweetened, canned"),
        ("48001", "Pie Filling, apple, 21oz can"),
        ("50737", "Soup, cream of celery, 98% fat free, condensed, canned"),
    ]:
        pcs = canonical.get(code, [])
        pcs_str = "; ".join(f"{pc} ({share:.0%})" for pc, share in pcs)
        print(f"  ESHA {code} {label[:50]} -> {pcs_str or '(none)'}", flush=True)

    save_canonical_pcs(canonical, OUT_PATH)
    print(f"\nwrote {OUT_PATH.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
