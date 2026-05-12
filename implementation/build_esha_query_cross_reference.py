from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

import build_esha_code_query_packs as packs
import match_esha_to_products as matcher


ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = ROOT / "implementation" / "output" / "esha_query_cross_reference"
OUT_INDEX = ROOT / "implementation" / "output" / "esha_query_cross_reference_index.csv"


def product_matches_terms(product_norm: str, product_tokens: set[str], terms: tuple[str, ...]) -> bool:
    if not terms:
        return False
    return all(matcher.product_has_term(product_norm, product_tokens, term) for term in terms)


def destination_candidates(
    product: dict[str, str],
    source: matcher.EshaProfile,
    profiles: list[matcher.EshaProfile],
    max_destinations: int,
    source_noise_terms: set[str],
) -> list[tuple[matcher.EshaProfile, tuple[str, ...], str]]:
    product_norm = matcher.normalize_text(product["description"])
    product_tokens = set(matcher.tokens_for(product["description"]))
    source_terms = packs.query_terms_for(source)
    candidates = []
    for profile in profiles:
        if profile.code == source.code or profile.skip_reason:
            continue
        terms = packs.query_terms_for(profile)
        if not product_matches_terms(product_norm, product_tokens, terms):
            continue
        if (
            profile.family != source.family
            and packs.category_signal(product["category"], profile.family, set(terms), product["description"]) == "category_noise"
        ):
            continue
        noise_overlap = source_noise_terms & set(terms)
        reason = "more_specific" if len(terms) > len(source_terms) else "alternate"
        if noise_overlap:
            reason = "noise_destination"
        elif profile.family != source.family:
            reason = "different_family"
        candidates.append((profile, terms, reason))
    reason_order = {
        "noise_destination": 0,
        "more_specific": 1,
        "different_family": 2,
        "alternate": 3,
    }
    candidates.sort(
        key=lambda item: (
            reason_order.get(item[2], 9),
            item[0].family != source.family,
            -len(item[1]),
            len(item[0].description),
            int(item[0].code) if item[0].code.isdigit() else 10**9,
        )
    )
    return candidates[:max_destinations]


def write_source_cross_reference(
    source: matcher.EshaProfile,
    rows: list[dict[str, str]],
    out_path: Path,
) -> None:
    lines = [
        f"# ESHA {source.code}: {source.description}",
        "",
        "## Cross Reference",
        "",
        "Products below came back from this ESHA code's product query. The destination columns show other ESHA codes whose query terms also fit the product, especially more-specific codes.",
        "",
        "| product | category | ingredients | source_signal | source_noise | likely_destinations |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        product = row["product_description"].replace("|", "/")
        category = row["category"].replace("|", "/")
        ingredients = packs.table_cell(row.get("ingredients", ""))
        lines.append(
            f"| {product} | {category} | {ingredients} | {row['source_signal']} | {row['source_noise_terms']} | {row['destinations']} |"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_for_source(
    con: sqlite3.Connection,
    source: matcher.EshaProfile,
    profiles: list[matcher.EshaProfile],
    max_products: int,
    max_destinations: int,
    out_root: Path,
) -> list[dict[str, str]]:
    query = packs.fts_query(packs.query_terms_for(source))
    products = packs.query_products(con, query, max_products) if query else []
    source_terms = set(source.tokens)
    rows = []
    for product in products:
        noise = packs.product_noise(product["description"], product["category"], source.family, source_terms, product.get("ingredients", ""))
        signal = packs.category_signal(product["category"], source.family, source_terms, product["description"])
        if noise:
            signal = "review_noise"
        destinations = destination_candidates(product, source, profiles, max_destinations, set(noise))
        destination_text = " ; ".join(
            f"{profile.code} {profile.description} [{reason}: {'/'.join(terms)}]"
            for profile, terms, reason in destinations
        )
        best_reason = destinations[0][2] if destinations else ""
        rows.append(
            {
                "source_code": source.code,
                "source_description": source.description,
                "source_query": query,
                "gtin_upc": product["gtin_upc"],
                "fdc_id": product["fdc_id"],
                "product_description": product["description"],
                "category": product["category"],
                "ingredients": product.get("ingredients", ""),
                "source_signal": signal,
                "source_noise_terms": "/".join(noise),
                "best_destination_reason": best_reason,
                "destinations": destination_text,
            }
        )
    slug = packs.slugify(source.description)
    out_path = out_root / source.family / f"{int(source.code):06d}_{slug}_crossref.md" if source.code.isdigit() else out_root / source.family / f"{slug}_crossref.md"
    write_source_cross_reference(source, rows, out_path)
    return rows


def write_index(rows: list[dict[str, str]]) -> None:
    OUT_INDEX.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "source_code",
        "source_description",
        "source_query",
        "gtin_upc",
        "fdc_id",
        "product_description",
        "category",
        "ingredients",
        "source_signal",
        "source_noise_terms",
        "best_destination_reason",
        "destinations",
    ]
    with OUT_INDEX.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", action="append", default=[])
    parser.add_argument("--contains", default="")
    parser.add_argument("--family", default="")
    parser.add_argument("--limit-codes", type=int, default=None)
    parser.add_argument("--max-products", type=int, default=100)
    parser.add_argument("--max-destinations", type=int, default=8)
    parser.add_argument("--out-root", default=str(OUT_ROOT))
    args = parser.parse_args()

    profiles = packs.load_profiles()
    selected = packs.select_profiles(
        profiles,
        codes=set(args.code),
        contains=args.contains,
        family=args.family,
        limit=args.limit_codes,
    )
    out_root = Path(args.out_root)
    rows = []
    with sqlite3.connect(packs.PRODUCTS_DB) as con:
        for source in selected:
            rows.extend(build_for_source(con, source, profiles, args.max_products, args.max_destinations, out_root))
    write_index(rows)
    print(f"wrote_sources={len(selected)} rows={len(rows)} out_root={out_root} index={OUT_INDEX}")


if __name__ == "__main__":
    main()
