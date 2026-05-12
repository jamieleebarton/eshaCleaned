from __future__ import annotations

import argparse
import csv
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import build_esha_code_query_packs as packs
import build_esha_query_cross_reference as crossref
import match_esha_to_products as matcher


ROOT = Path(__file__).resolve().parent.parent
PACK_INDEX = ROOT / "implementation" / "output" / "esha_code_query_pack_index.csv"
OUT_CSV = ROOT / "implementation" / "output" / "esha_cleanup_matrix.csv"
OUT_SUMMARY = ROOT / "implementation" / "output" / "esha_cleanup_matrix_summary.md"


PRODUCT_HEADERS = {
    "| rank | gtin_upc | fdc_id | description | category | signal | noise_terms |",
    "| rank | gtin_upc | fdc_id | description | category | ingredients | signal | noise_terms |",
}


def split_md_row(line: str) -> list[str]:
    return [part.strip() for part in line.strip().strip("|").split("|")]


def iter_pack_products(pack_path: Path):
    if not pack_path.exists():
        return
    in_products = False
    for line in pack_path.read_text(encoding="utf-8").splitlines():
        if line in PRODUCT_HEADERS:
            in_products = True
            continue
        if not in_products:
            continue
        if line.startswith("| ---"):
            continue
        if not line.startswith("| "):
            if in_products and line.startswith("## "):
                in_products = False
            continue
        parts = split_md_row(line)
        if len(parts) == 7:
            rank, gtin_upc, fdc_id, description, category, signal, noise_terms = parts
            ingredients = ""
        elif len(parts) == 8:
            rank, gtin_upc, fdc_id, description, category, ingredients, signal, noise_terms = parts
        else:
            if line.startswith("## "):
                in_products = False
            continue
        yield {
            "rank": rank,
            "gtin_upc": gtin_upc,
            "fdc_id": fdc_id,
            "description": description,
            "category": category,
            "ingredients": ingredients,
            "signal": signal,
            "noise_terms": noise_terms,
        }


def load_pack_index() -> list[dict[str, str]]:
    with PACK_INDEX.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def product_terms(product: dict[str, str]) -> set[str]:
    terms = set(matcher.tokens_for(product["description"]))
    terms.update(matcher.tokens_for(product["category"]))
    if "garbanzo" in terms:
        terms.add("chickpea")
    if "chickpea" in terms:
        terms.add("garbanzo")
    if "mayo" in terms:
        terms.add("mayonnaise")
    if "mayonnaise" in terms:
        terms.add("mayo")
    if "powder" in terms:
        terms.add("dry")
    if "dry" in terms:
        terms.add("powder")
    if "skim" in terms:
        terms.add("nonfat")
    if "nonfat" in terms:
        terms.add("skim")
    return terms


def product_ingredients(con: sqlite3.Connection, cache: dict[str, str], gtin_upc: str) -> str:
    if not gtin_upc:
        return ""
    if gtin_upc not in cache:
        row = con.execute(
            """
            SELECT COALESCE(NULLIF(ingredients_clean, ''), NULLIF(ingredients, ''), '')
            FROM products
            WHERE gtin_upc = ?
            LIMIT 1
            """,
            (gtin_upc,),
        ).fetchone()
        cache[gtin_upc] = str(row[0] or "") if row else ""
    return cache[gtin_upc]


def build_destination_index(profiles: list[matcher.EshaProfile]):
    by_term: dict[str, list[matcher.EshaProfile]] = defaultdict(list)
    terms_by_code: dict[str, tuple[str, ...]] = {}
    for profile in profiles:
        if profile.skip_reason:
            continue
        terms = packs.query_terms_for(profile)
        if not terms:
            continue
        terms_by_code[profile.code] = terms
        for term in terms:
            by_term[term].append(profile)
            for variant in packs.term_variants(term):
                by_term[variant].append(profile)
    return by_term, terms_by_code


def destination_candidates_fast(
    product: dict[str, str],
    source: matcher.EshaProfile,
    by_term: dict[str, list[matcher.EshaProfile]],
    terms_by_code: dict[str, tuple[str, ...]],
    max_destinations: int,
    source_noise_terms: set[str],
    max_profiles_per_seed_term: int,
) -> list[tuple[matcher.EshaProfile, tuple[str, ...], str]]:
    product_norm = matcher.normalize_text(product["description"])
    tokens = product_terms(product)
    candidates: dict[str, matcher.EshaProfile] = {}
    source_terms = terms_by_code.get(source.code, packs.query_terms_for(source))
    seed_terms = set(source_noise_terms) or (tokens - set(source_terms))
    if not seed_terms:
        seed_terms = tokens
    for term in seed_terms:
        profiles_for_term = by_term.get(term, ())
        if (
            max_profiles_per_seed_term
            and len(profiles_for_term) > max_profiles_per_seed_term
            and term not in source_noise_terms
        ):
            continue
        for profile in profiles_for_term:
            candidates[profile.code] = profile
    rows = []
    for profile in candidates.values():
        if profile.code == source.code:
            continue
        terms = terms_by_code.get(profile.code)
        if not terms:
            continue
        if not crossref.product_matches_terms(product_norm, set(matcher.tokens_for(product["description"])), terms):
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
        rows.append((profile, terms, reason))
    reason_order = {
        "noise_destination": 0,
        "more_specific": 1,
        "different_family": 2,
        "alternate": 3,
    }
    rows.sort(
        key=lambda item: (
            reason_order.get(item[2], 9),
            item[0].family != source.family,
            -len(item[1]),
            len(item[0].description),
            int(item[0].code) if item[0].code.isdigit() else 10**9,
        )
    )
    return rows[:max_destinations]


def action_for(
    source: matcher.EshaProfile,
    product: dict[str, str],
    destinations: list[tuple[matcher.EshaProfile, tuple[str, ...], str]],
) -> str:
    noise = bool(product["noise_terms"])
    category_noise = product["signal"] == "category_noise"
    if destinations:
        best = destinations[0]
        if best[2] == "noise_destination":
            return "add_source_exclude_and_destination_contract"
        if best[0].family != source.family:
            return "route_to_other_family_contract"
        if best[2] == "more_specific":
            return "route_to_more_specific_code"
    if category_noise and noise:
        return "tighten_query_and_exclude_noise"
    if category_noise:
        return "tighten_query_or_category_rules"
    if noise:
        return "add_source_exclude_or_embedding_review"
    return "review"


def destination_text(destinations: list[tuple[matcher.EshaProfile, tuple[str, ...], str]]) -> str:
    return " ; ".join(
        f"{profile.code} {profile.description} [{reason}: {'/'.join(terms)}]"
        for profile, terms, reason in destinations
    )


def best_destination_fields(destinations: list[tuple[matcher.EshaProfile, tuple[str, ...], str]]) -> dict[str, str]:
    if not destinations:
        return {
            "best_destination_code": "",
            "best_destination_description": "",
            "best_destination_family": "",
            "best_destination_reason": "",
        }
    profile, _, reason = destinations[0]
    return {
        "best_destination_code": profile.code,
        "best_destination_description": profile.description,
        "best_destination_family": profile.family,
        "best_destination_reason": reason,
    }


def source_rows(
    pack_rows: list[dict[str, str]],
    profile_by_code: dict[str, matcher.EshaProfile],
    by_term: dict[str, list[matcher.EshaProfile]],
    terms_by_code: dict[str, tuple[str, ...]],
    max_destinations: int,
    max_rows: int | None,
    max_rows_per_code: int | None,
    progress_every: int,
    con: sqlite3.Connection,
    max_profiles_per_seed_term: int,
) -> list[dict[str, str]]:
    output = []
    ingredient_cache: dict[str, str] = {}
    for pack_idx, pack in enumerate(pack_rows, start=1):
        if progress_every and pack_idx % progress_every == 0:
            print(f"matrix_sources={pack_idx} noisy_rows={len(output)}", flush=True)
        source = profile_by_code.get(pack["esha_code"])
        if not source:
            continue
        source_row_count = 0
        for product in iter_pack_products(Path(pack["pack_path"])):
            if not product.get("ingredients"):
                product["ingredients"] = product_ingredients(con, ingredient_cache, product["gtin_upc"])
            signal, noise = packs.classify_product(source, product)
            product["noise_terms"] = "/".join(noise)
            product["signal"] = signal
            if product["signal"] in {"in_scope_category", "contract_accept"} and not product["noise_terms"]:
                continue
            noise_terms = set(noise)
            destinations = destination_candidates_fast(
                product,
                source,
                by_term,
                terms_by_code,
                max_destinations,
                noise_terms,
                max_profiles_per_seed_term,
            )
            row = {
                "source_code": source.code,
                "source_description": source.description,
                "source_family": source.family,
                "source_query": pack["query"],
                "pack_path": pack["pack_path"],
                "product_rank": product["rank"],
                "gtin_upc": product["gtin_upc"],
                "fdc_id": product["fdc_id"],
                "product_description": product["description"],
                "product_category": product["category"],
                "product_ingredients": product.get("ingredients", ""),
                "source_signal": product["signal"],
                "source_noise_terms": product["noise_terms"],
                "action": action_for(source, product, destinations),
                "destinations": destination_text(destinations),
            }
            row.update(best_destination_fields(destinations))
            output.append(row)
            source_row_count += 1
            if max_rows is not None and len(output) >= max_rows:
                return output
            if max_rows_per_code is not None and source_row_count >= max_rows_per_code:
                break
    return output


def write_matrix(rows: list[dict[str, str]], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "source_code",
        "source_description",
        "source_family",
        "source_query",
        "pack_path",
        "product_rank",
        "gtin_upc",
        "fdc_id",
        "product_description",
        "product_category",
        "product_ingredients",
        "source_signal",
        "source_noise_terms",
        "action",
        "best_destination_code",
        "best_destination_description",
        "best_destination_family",
        "best_destination_reason",
        "destinations",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict[str, str]], out_summary: Path) -> None:
    action_counts = Counter(row["action"] for row in rows)
    source_counts = Counter((row["source_code"], row["source_description"], row["source_family"]) for row in rows)
    family_counts = Counter(row["source_family"] for row in rows)
    category_counts = Counter((row["source_family"], row["product_category"]) for row in rows)
    lines = [
        "# ESHA Cleanup Matrix Summary",
        "",
        f"- noisy_rows: {len(rows)}",
        "",
        "## Actions",
        "",
        "| count | action |",
        "| ---: | --- |",
    ]
    for action, count in action_counts.most_common():
        lines.append(f"| {count} | {action} |")
    lines.extend(["", "## Source Families", "", "| count | family |", "| ---: | --- |"])
    for family, count in family_counts.most_common():
        lines.append(f"| {count} | {family} |")
    lines.extend(["", "## Worst Source Codes", "", "| count | source_code | family | description |", "| ---: | --- | --- | --- |"])
    for (code, description, family), count in source_counts.most_common(30):
        lines.append(f"| {count} | {code} | {family} | {description.replace('|', '/')} |")
    lines.extend(["", "## Noisy Categories", "", "| count | source_family | product_category |", "| ---: | --- | --- |"])
    for (family, category), count in category_counts.most_common(30):
        lines.append(f"| {count} | {family} | {category.replace('|', '/')} |")
    out_summary.write_text("\n".join(lines) + "\n", encoding="utf-8")


def selected_pack_rows(args) -> list[dict[str, str]]:
    rows = load_pack_index()
    families = set(args.family)
    codes = set(args.code)
    contains = matcher.normalize_text(args.contains) if args.contains else ""
    selected = []
    for row in rows:
        if families and row["family"] not in families:
            continue
        if codes and row["esha_code"] not in codes:
            continue
        if contains and contains not in matcher.normalize_text(row["description"]):
            continue
        if args.only_with_products and int(row["candidate_count_capped"] or "0") == 0:
            continue
        selected.append(row)
        if args.limit_codes is not None and len(selected) >= args.limit_codes:
            break
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", action="append", default=[])
    parser.add_argument("--code", action="append", default=[])
    parser.add_argument("--contains", default="")
    parser.add_argument("--limit-codes", type=int, default=None)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--max-rows-per-code", type=int, default=None)
    parser.add_argument("--max-destinations", type=int, default=8)
    parser.add_argument("--max-profiles-per-seed-term", type=int, default=2000)
    parser.add_argument("--progress-every", type=int, default=500)
    parser.add_argument("--only-with-products", action="store_true")
    parser.add_argument("--out-csv", default=str(OUT_CSV))
    parser.add_argument("--out-summary", default=str(OUT_SUMMARY))
    args = parser.parse_args()

    profiles = packs.load_profiles()
    profile_by_code = {profile.code: profile for profile in profiles}
    by_term, terms_by_code = build_destination_index(profiles)
    pack_rows = selected_pack_rows(args)
    with sqlite3.connect(packs.PRODUCTS_DB) as con:
        rows = source_rows(
            pack_rows,
            profile_by_code,
            by_term,
            terms_by_code,
            args.max_destinations,
            args.max_rows,
            args.max_rows_per_code,
            args.progress_every,
            con,
            args.max_profiles_per_seed_term,
        )
    rows.sort(
        key=lambda row: (
            row["action"] != "add_source_exclude_and_destination_contract",
            row["source_family"],
            int(row["source_code"]) if row["source_code"].isdigit() else 10**9,
            float(row["product_rank"]) if re.match(r"^-?\d+(?:\.\d+)?$", row["product_rank"]) else 0.0,
            row["product_description"],
        )
    )
    out_csv = Path(args.out_csv)
    out_summary = Path(args.out_summary)
    write_matrix(rows, out_csv)
    summarize(rows, out_summary)
    print(f"selected_codes={len(pack_rows)} noisy_rows={len(rows)} out_csv={out_csv} out_summary={out_summary}")


if __name__ == "__main__":
    main()
