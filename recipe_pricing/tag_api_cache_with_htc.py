#!/usr/bin/env python3
"""Tag Walmart/Kroger API cache products with identity HTC codes."""
from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "recipe_mapper" / "v1"))

from htc.encoder import HTC, code_from_parts, encode  # noqa: E402
from htc.food_slots import effective_food_name  # noqa: E402

DEFAULT_INPUT = ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_tagged.csv"
DEFAULT_OUTPUT = ROOT / "recipe_pricing" / "output" / "api_cache_htc_tagged.csv"

PACKAGE_RE = re.compile(
    r"\b(?:\d+(?:\.\d+)?|\d+/\d+)\s*(?:fl\s*)?"
    r"(?:oz|ounce|ounces|lb|lbs|pound|pounds|g|gram|grams|kg|ml|l|ct|count|pack|pk)\b",
    re.I,
)
MARKETING_RE = re.compile(
    r"\b(?:fresh|premium|natural|naturally|classic|original|great value|simple truth|kroger|walmart|big deal)\b",
    re.I,
)


def clean_title(name: str) -> str:
    value = PACKAGE_RE.sub(" ", name or "")
    value = MARKETING_RE.sub(" ", value)
    value = re.sub(r"\s+", " ", value).strip(" ,;-")
    return value


def non_food_htc() -> HTC:
    code = code_from_parts("N", "0", "00")
    return HTC(
        code=code, group="N", family="0", food="00",
        form="0", processing="0", ptype="0", check=code[-1],
        confidence=1.0, source="taxonomy_non_food",
    )


def unresolved_htc() -> HTC:
    return HTC(
        code="00000000", group="0", family="0", food="00",
        form="0", processing="0", ptype="0", check="0",
        confidence=0.2, source="taxonomy_unresolved",
    )


def encode_row(row: dict[str, str], clean: str) -> HTC:
    name = row.get("name") or ""
    hint = row.get("search_term") or ""
    title_blob = f"{name} {clean} {hint}"
    canonical_path = (row.get("canonical_path") or "").strip()
    product_identity = (row.get("product_identity_fixed") or "").strip()
    modifier = (row.get("modifier") or "").strip()
    taxonomy_source = (row.get("taxonomy_source") or "").strip()

    if taxonomy_source == "non_food":
        return non_food_htc()
    if taxonomy_source == "unresolved":
        return unresolved_htc()

    # Product-class guards for cheese-flavored non-cheese items. The taxonomy
    # matcher may see "pepper jack cheese" before "crackers/taco shells"; the
    # purchasable identity is the carrier food, not the flavor.
    if re.search(r"\b(?:nut[- ]?thins?|rice\s+crackers?|crackers?)\b", title_blob, re.I):
        return encode(
            category="",
            description=name,
            extra=hint,
            food_name="Rice Crackers" if re.search(r"\brice\s+crackers?\b|nut[- ]?thins?", title_blob, re.I) else "Crackers",
            canonical_path="Snack > Crackers > Rice Crackers" if re.search(r"\brice\s+crackers?\b|nut[- ]?thins?", title_blob, re.I) else "Snack > Crackers",
        )
    if re.search(r"\btaco\s+shells?\b", title_blob, re.I):
        return encode(
            category="",
            description=name,
            extra=hint,
            food_name="Taco Shells",
            canonical_path="Pantry > Grain > Shells > Taco Shells",
        )
    if re.search(r"\btaquitos?\b", title_blob, re.I):
        return encode(category="", description=name, extra=hint, food_name="Taquitos", canonical_path="Frozen > Tacos")
    if re.search(r"\bmini\s+tacos?\b", title_blob, re.I):
        return encode(category="", description=name, extra=hint, food_name="Tacos", canonical_path="Frozen > Tacos")

    if canonical_path and product_identity:
        food_name = effective_food_name(
            canonical_path,
            product_identity,
            modifier,
            " || ".join(part for part in (name, clean) if part),
            flavor=row.get("flavor", ""),
        )
        return encode(
            category="",
            description=name,
            extra=hint,
            food_name=food_name or product_identity,
            canonical_path=canonical_path,
            modifier=modifier,
        )

    # search_term is useful context, but title remains the primary signal.
    htc = encode(category="", description=clean or name, extra=hint, food_name=clean or hint or name)
    # Fallback: if registry didn't resolve a real food slot, retry with
    # search_term as the food_name. The API cache search_term comes from the
    # FNDDS query and is usually a clean food noun. Only override if the retry
    # actually finds a slot AND keeps the same group/family.
    if htc.food == "00" and hint:
        retry = encode(category="", description=clean or name, extra=hint, food_name=hint)
        if retry.food != "00" and retry.group == htc.group and retry.family == htc.family:
            htc = retry
    return htc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    counts: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    rows = 0

    with args.input.open(encoding="utf-8", errors="replace", newline="") as src, args.output.open(
        "w", encoding="utf-8", newline=""
    ) as dst:
        reader = csv.DictReader(src)
        output_fields = [
            "clean_name",
            "htc_code",
            "htc_group",
            "htc_family",
            "htc_food",
            "htc_form",
            "htc_processing",
            "htc_ptype",
            "htc_check",
            "htc_confidence",
            "htc_source",
        ]
        fieldnames = list(reader.fieldnames or []) + [field for field in output_fields if field not in (reader.fieldnames or [])]
        writer = csv.DictWriter(dst, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            rows += 1
            name = row.get("name") or ""
            clean = clean_title(name)
            htc = encode_row(row, clean)
            row.update({
                "clean_name": clean,
                "htc_code": "~" + htc.code,
                "htc_group": htc.group,
                "htc_family": htc.family,
                "htc_food": htc.food,
                "htc_form": htc.form,
                "htc_processing": htc.processing,
                "htc_ptype": htc.ptype,
                "htc_check": htc.check,
                "htc_confidence": f"{htc.confidence:.2f}",
                "htc_source": htc.source,
            })
            writer.writerow(row)
            counts[htc.group] += 1
            sources[htc.source] += 1
            if rows % 50000 == 0:
                print(f"  tagged {rows:,} products", flush=True)

    print(f"wrote {args.output} ({rows:,} rows, {time.time() - t0:.1f}s)")
    print("groups:", dict(counts.most_common()))
    print("sources:", dict(sources.most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
