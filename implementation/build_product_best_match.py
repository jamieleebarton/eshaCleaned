"""Pick a single best ESHA code per retail GTIN.

For products accepted by multiple shipped contracts (~16% fan-out), score each
candidate by Jaccard overlap between product-description tokens and
ESHA-description tokens (stop-word-filtered). Tie-break by smaller pack size
(more specific contract) then by lowest ESHA code.

Output: ``implementation/output/product_to_best_esha_map.csv`` with one row
per GTIN: gtin_upc, product_description, branded_food_category, brand_owner,
best_esha_code, best_esha_description, score, n_candidates_scored.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPL = ROOT / "implementation"
if str(IMPL) not in sys.path:
    sys.path.insert(0, str(IMPL))

import esha_contracts.reviewed_nebius_generated as mod  # noqa: E402
from run_pack_builder_sweep import STOP_DESCRIPTION_TOKENS, normalize_tokens  # noqa: E402

IN_CSV = ROOT / "implementation" / "output" / "product_to_esha_map.csv"
OUT_CSV = ROOT / "implementation" / "output" / "product_to_best_esha_map.csv"


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def main() -> None:
    # Group rows by gtin
    product_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    with IN_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            product_rows[r["gtin_upc"]].append(r)
    print(f"unique GTINs: {len(product_rows):,}")

    # Pre-tokenize ESHA descriptions and cache pack sizes
    esha_tokens: dict[str, set[str]] = {}
    pack_size: dict[str, int] = {}
    for code, spec in mod.GENERATED_CONTRACT_SPECS.items():
        esha_tokens[code] = set(normalize_tokens(spec.get("esha_description", ""), STOP_DESCRIPTION_TOKENS))
        pack_size[code] = len(spec.get("accepted_gtins") or [])

    fan_out_collapsed = 0
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "gtin_upc",
                "product_description",
                "branded_food_category",
                "brand_owner",
                "best_esha_code",
                "best_esha_description",
                "score",
                "n_candidates",
            ]
        )
        for gtin, rows in product_rows.items():
            if len(rows) == 1:
                r = rows[0]
                writer.writerow(
                    [
                        gtin,
                        r["product_description"],
                        r["branded_food_category"],
                        r["brand_owner"],
                        r["esha_code"],
                        r["esha_description"],
                        "1.0",
                        1,
                    ]
                )
                continue

            fan_out_collapsed += 1
            product_toks = set(normalize_tokens(rows[0]["product_description"], STOP_DESCRIPTION_TOKENS))

            def sort_key(row: dict[str, str]) -> tuple[float, int, int]:
                code = row["esha_code"]
                score = jaccard(product_toks, esha_tokens.get(code, set()))
                size = pack_size.get(code, 0)
                # Sort ascending: -score (highest first), then size (smallest first), then code
                code_int = int(code) if code.isdigit() else 10**9
                return (-score, size, code_int)

            best = min(rows, key=sort_key)
            score = jaccard(product_toks, esha_tokens.get(best["esha_code"], set()))
            writer.writerow(
                [
                    gtin,
                    best["product_description"],
                    best["branded_food_category"],
                    best["brand_owner"],
                    best["esha_code"],
                    best["esha_description"],
                    f"{score:.3f}",
                    len(rows),
                ]
            )

    print(f"wrote {OUT_CSV}")
    print(f"fan-out resolved: {fan_out_collapsed:,} GTINs collapsed to single ESHA code")


if __name__ == "__main__":
    main()
