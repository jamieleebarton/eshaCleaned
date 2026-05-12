from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import build_esha_code_query_packs as pack_builder
import build_product_esha_code_rollup as code_rollup
import esha_contracts
import match_esha_to_products as matcher


ROOT = Path(__file__).resolve().parent.parent
ESHA_CSV = ROOT / "esha_cleaned.csv"
PRODUCTS_DB = ROOT / "data" / "master_products.db"
PACK_ROOT = ROOT / "implementation" / "output" / "esha_code_query_packs"
OUT_DIR = ROOT / "implementation" / "output"
OUT_ASSIGNMENTS = OUT_DIR / "product_esha_assignments.csv"
OUT_PRIMARY = OUT_DIR / "product_esha_primary.csv"
OUT_DB = OUT_DIR / "product_esha_lookup.db"
OUT_SUMMARY = OUT_DIR / "product_esha_lookup_summary.json"
DEFAULT_DIRECT_RETRIEVAL_LIMIT = 5000

PRODUCT_HEADERS = {
    "| rank | gtin_upc | fdc_id | description | category | signal | noise_terms |",
    "| rank | gtin_upc | fdc_id | description | category | ingredients | signal | noise_terms |",
}

ASSIGNMENT_FIELDS = [
    "gtin_upc",
    "fdc_id",
    "product_description",
    "brand_owner",
    "brand_name",
    "branded_food_category",
    "esha_code",
    "esha_description",
    "esha_canonical_title",
    "esha_family",
    "match_score",
    "match_reason",
    "required_terms",
    "attributes",
    "assignment_rank",
]

PRIMARY_FIELDS = [
    "gtin_upc",
    "fdc_id",
    "product_description",
    "brand_owner",
    "brand_name",
    "branded_food_category",
    "match_status",
    "esha_code",
    "esha_description",
    "esha_canonical_title",
    "esha_family",
    "match_score",
    "match_reason",
    "candidate_profile_count",
    "assignment_count",
    "required_terms",
    "attributes",
]


def clean_cell(value: object) -> str:
    return str(value or "").replace("\x00", "")


def split_md_row(line: str) -> list[str]:
    return [part.strip() for part in line.strip().strip("|").split("|")]


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        return list(csv.DictReader((line.replace("\x00", "") for line in handle)))


def pack_files(codes: set[str] | None = None) -> list[Path]:
    if not codes:
        return sorted(PACK_ROOT.rglob("*.md"))
    matched: set[Path] = set()
    for code in codes:
        if code.isdigit():
            for path in PACK_ROOT.rglob(f"{int(code):06d}_*.md"):
                matched.add(path)
    if matched:
        return sorted(matched)
    rows = []
    for path in sorted(PACK_ROOT.rglob("*.md")):
        match = re.match(r"# ESHA\s+([^:]+):", path.read_text(encoding="utf-8", errors="replace").splitlines()[0])
        if match and match.group(1).strip() in codes:
            rows.append(path)
    return rows


def parse_pack(path: Path) -> dict[str, Any] | None:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        return None
    match = re.match(r"# ESHA\s+([^:]+):\s*(.*)", lines[0])
    if not match:
        return None
    code = match.group(1).strip()
    description = match.group(2).strip()
    family = path.parent.name
    required_terms = ""
    attrs = ""
    rows: list[dict[str, str]] = []
    in_candidates = False
    for line in lines:
        if line.startswith("- esha_required_terms_from_description:"):
            required_terms = line.split(":", 1)[1].strip().replace(" | ", "|")
            continue
        if line.startswith("- esha_attrs_from_description:"):
            attrs = line.split(":", 1)[1].strip().replace(" | ", "|")
            continue
        if line.startswith("## Candidate Clean Products"):
            in_candidates = False
            continue
        if line in PRODUCT_HEADERS:
            in_candidates = True
            continue
        if not in_candidates:
            continue
        if line.startswith("| ---"):
            continue
        if line.startswith("## "):
            break
        if not line.startswith("| "):
            continue
        parts = split_md_row(line)
        if len(parts) == 7:
            rank, gtin_upc, fdc_id, product_description, category, signal, noise_terms = parts
            ingredients = ""
        elif len(parts) == 8:
            rank, gtin_upc, fdc_id, product_description, category, ingredients, signal, noise_terms = parts
        else:
            continue
        if signal != "contract_accept":
            continue
        rows.append(
            {
                "rank": rank,
                "gtin_upc": gtin_upc,
                "fdc_id": fdc_id,
                "product_description": product_description,
                "branded_food_category": category,
                "ingredients": ingredients,
                "signal": signal,
                "noise_terms": noise_terms,
            }
        )
    return {
        "pack_path": path,
        "esha_code": code,
        "esha_description": description,
        "esha_family": family,
        "required_terms": required_terms,
        "attributes": attrs,
        "rows": rows,
    }


def fetch_product_details(gtin_upc: str, fdc_id: str, con: sqlite3.Connection, cache: dict[tuple[str, str], dict[str, str]]) -> dict[str, str]:
    key = (gtin_upc, fdc_id)
    if key in cache:
        return cache[key]
    row = con.execute(
        """
        SELECT
            COALESCE(brand_owner, ''),
            COALESCE(brand_name, ''),
            COALESCE(branded_food_category, ''),
            COALESCE(description, '')
        FROM products
        WHERE gtin_upc = ? AND fdc_id = ?
        LIMIT 1
        """,
        key,
    ).fetchone()
    if row is None:
        row = con.execute(
            """
            SELECT
                COALESCE(brand_owner, ''),
                COALESCE(brand_name, ''),
                COALESCE(branded_food_category, ''),
                COALESCE(description, '')
            FROM products
            WHERE gtin_upc = ?
            ORDER BY CASE WHEN fdc_id = ? THEN 0 ELSE 1 END, fdc_id
            LIMIT 1
            """,
            (gtin_upc, fdc_id),
        ).fetchone()
    payload = {
        "brand_owner": clean_cell(row[0]) if row else "",
        "brand_name": clean_cell(row[1]) if row else "",
        "branded_food_category": clean_cell(row[2]) if row else "",
        "product_description": clean_cell(row[3]) if row else "",
    }
    cache[key] = payload
    return payload


def assignment_rows_from_pack(parsed: dict[str, Any], con: sqlite3.Connection, cache: dict[tuple[str, str], dict[str, str]], limit: int | None = None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    rows = parsed["rows"][:limit] if limit else parsed["rows"]
    for idx, row in enumerate(rows, start=1):
        details = fetch_product_details(row["gtin_upc"], row["fdc_id"], con, cache)
        out.append(
            {
                "gtin_upc": row["gtin_upc"],
                "fdc_id": row["fdc_id"],
                "product_description": details["product_description"] or row["product_description"],
                "brand_owner": details["brand_owner"],
                "brand_name": details["brand_name"],
                "branded_food_category": details["branded_food_category"] or row["branded_food_category"],
                "esha_code": parsed["esha_code"],
                "esha_description": parsed["esha_description"],
                "esha_canonical_title": parsed["esha_description"],
                "esha_family": parsed["esha_family"],
                "match_score": str(max(1, 1000 - idx)),
                "match_reason": "pack_contract_accept",
                "required_terms": parsed["required_terms"],
                "attributes": parsed["attributes"],
                "assignment_rank": "",
            }
        )
    return out


def load_profiles_by_code() -> dict[str, matcher.EshaProfile]:
    profiles: dict[str, matcher.EshaProfile] = {}
    with ESHA_CSV.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            profile = matcher.profile_for(row)
            profiles[profile.code] = profile
    return profiles


def direct_retrieval_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_DIRECT_RETRIEVAL_LIMIT
    return max(limit, DEFAULT_DIRECT_RETRIEVAL_LIMIT)


def should_use_direct(profile_code: str, source: str) -> bool:
    if source == "direct":
        return True
    if source != "auto":
        return False
    return bool(esha_contracts.contract_source_module(profile_code))


def direct_assignment_rows_for_profile(profile: matcher.EshaProfile, con: sqlite3.Connection, limit: int | None = None) -> list[dict[str, str]]:
    category_terms = pack_builder.category_terms_for_profile(profile)
    semantic_filters = pack_builder.semantic_filters_for_profile(profile)
    attempts = pack_builder.query_attempts_for(profile)
    if not attempts:
        return []

    retrieval_limit = direct_retrieval_limit(limit)
    accepted: dict[tuple[str, str], dict[str, Any]] = {}

    for attempt_index, (label, terms) in enumerate(attempts):
        query = pack_builder.fts_query(terms)
        if not query:
            continue
        for ordinal, product in enumerate(pack_builder.query_products(con, query, retrieval_limit, category_terms), start=1):
            signal, _noise = pack_builder.classify_product(profile, product, semantic_filters)
            if signal != "contract_accept":
                continue
            key = (
                clean_cell(product.get("gtin_upc", "")),
                clean_cell(product.get("fdc_id", "")),
            )
            candidate = {
                "gtin_upc": key[0],
                "fdc_id": key[1],
                "product_description": clean_cell(product.get("description", "")),
                "brand_owner": clean_cell(product.get("brand_owner", "")),
                "brand_name": clean_cell(product.get("brand_name", "")),
                "branded_food_category": clean_cell(product.get("category", "")),
                "esha_code": profile.code,
                "esha_description": profile.description,
                "esha_canonical_title": profile.description,
                "esha_family": profile.family,
                "match_score": "",
                "match_reason": f"direct_contract_accept:{label}",
                "required_terms": "|".join(profile.hard_terms),
                "attributes": "|".join(profile.attrs),
                "assignment_rank": "",
                "_attempt_index": attempt_index,
                "_ordinal": ordinal,
                "_rank": float(product.get("rank") or "0"),
            }
            current = accepted.get(key)
            if current is None or (
                candidate["_attempt_index"],
                candidate["_ordinal"],
                candidate["_rank"],
            ) < (
                current["_attempt_index"],
                current["_ordinal"],
                current["_rank"],
            ):
                accepted[key] = candidate

    rows = sorted(
        accepted.values(),
        key=lambda row: (
            row["_attempt_index"],
            row["_ordinal"],
            row["_rank"],
            row["gtin_upc"],
            row["fdc_id"],
        ),
    )
    if limit is not None:
        rows = rows[:limit]
    out: list[dict[str, str]] = []
    for idx, row in enumerate(rows, start=1):
        copy = dict(row)
        copy["match_score"] = str(max(1, 1_000_000 - idx))
        copy.pop("_attempt_index", None)
        copy.pop("_ordinal", None)
        copy.pop("_rank", None)
        out.append(copy)
    return out


def read_assignments(path: Path = OUT_ASSIGNMENTS) -> list[dict[str, str]]:
    if not path.exists():
        return []
    return csv_rows(path)


def sort_assignments(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        rows,
        key=lambda row: (
            row.get("gtin_upc", ""),
            -int(float(row.get("match_score") or "0")),
            int(row.get("esha_code") or "999999") if (row.get("esha_code") or "").isdigit() else 10**9,
            row.get("fdc_id", ""),
        ),
    )


def assign_ranks(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    counts: dict[str, int] = defaultdict(int)
    ranked: list[dict[str, str]] = []
    for row in sort_assignments(rows):
        copy = dict(row)
        gtin = copy.get("gtin_upc", "")
        counts[gtin] += 1
        copy["assignment_rank"] = str(counts[gtin])
        ranked.append(copy)
    return ranked


def primary_rows(assignments: list[dict[str, str]]) -> list[dict[str, str]]:
    by_gtin: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in assignments:
        gtin = row.get("gtin_upc", "")
        if gtin:
            by_gtin[gtin].append(row)
    out: list[dict[str, str]] = []
    for gtin, rows in sorted(by_gtin.items()):
        rows.sort(key=lambda row: int(row.get("assignment_rank") or "999999"))
        first = rows[0]
        out.append(
            {
                "gtin_upc": first["gtin_upc"],
                "fdc_id": first["fdc_id"],
                "product_description": first["product_description"],
                "brand_owner": first["brand_owner"],
                "brand_name": first["brand_name"],
                "branded_food_category": first["branded_food_category"],
                "match_status": "accepted",
                "esha_code": first["esha_code"],
                "esha_description": first["esha_description"],
                "esha_canonical_title": first["esha_canonical_title"],
                "esha_family": first["esha_family"],
                "match_score": first["match_score"],
                "match_reason": first["match_reason"],
                "candidate_profile_count": str(len(rows)),
                "assignment_count": str(len(rows)),
                "required_terms": first["required_terms"],
                "attributes": first["attributes"],
            }
        )
    return out


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def write_lookup_db(assignments: list[dict[str, str]], primary: list[dict[str, str]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT_DB.with_suffix(".db.tmp")
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(tmp)
    try:
        con.execute(
            """
            CREATE TABLE product_esha_assignments (
                gtin_upc TEXT,
                fdc_id TEXT,
                product_description TEXT,
                brand_owner TEXT,
                brand_name TEXT,
                branded_food_category TEXT,
                esha_code TEXT,
                esha_description TEXT,
                esha_canonical_title TEXT,
                esha_family TEXT,
                match_score TEXT,
                match_reason TEXT,
                required_terms TEXT,
                attributes TEXT,
                assignment_rank TEXT
            )
            """
        )
        con.execute(
            """
            CREATE TABLE product_esha_primary (
                gtin_upc TEXT PRIMARY KEY,
                fdc_id TEXT,
                product_description TEXT,
                brand_owner TEXT,
                brand_name TEXT,
                branded_food_category TEXT,
                match_status TEXT,
                esha_code TEXT,
                esha_description TEXT,
                esha_canonical_title TEXT,
                esha_family TEXT,
                match_score TEXT,
                match_reason TEXT,
                candidate_profile_count TEXT,
                assignment_count TEXT,
                required_terms TEXT,
                attributes TEXT
            )
            """
        )
        if assignments:
            con.executemany(
                """
                INSERT INTO product_esha_assignments VALUES (
                    :gtin_upc, :fdc_id, :product_description, :brand_owner, :brand_name,
                    :branded_food_category, :esha_code, :esha_description, :esha_canonical_title,
                    :esha_family, :match_score, :match_reason, :required_terms, :attributes, :assignment_rank
                )
                """,
                assignments,
            )
        if primary:
            con.executemany(
                """
                INSERT INTO product_esha_primary VALUES (
                    :gtin_upc, :fdc_id, :product_description, :brand_owner, :brand_name,
                    :branded_food_category, :match_status, :esha_code, :esha_description,
                    :esha_canonical_title, :esha_family, :match_score, :match_reason,
                    :candidate_profile_count, :assignment_count, :required_terms, :attributes
                )
                """,
                primary,
            )
        con.execute("CREATE INDEX idx_product_esha_assignments_gtin ON product_esha_assignments(gtin_upc)")
        con.execute("CREATE INDEX idx_product_esha_assignments_code ON product_esha_assignments(esha_code)")
        con.commit()
    finally:
        con.close()
    tmp.replace(OUT_DB)


def write_lookup_artifacts(rows: list[dict[str, str]]) -> dict[str, Any]:
    ranked = assign_ranks(rows)
    primary = primary_rows(ranked)
    write_csv(OUT_ASSIGNMENTS, ASSIGNMENT_FIELDS, ranked)
    write_csv(OUT_PRIMARY, PRIMARY_FIELDS, primary)
    write_lookup_db(ranked, primary)
    rollup = code_rollup.build_rollup(write_db=True)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "assignment_rows": len(ranked),
        "primary_rows": len(primary),
        "codes_with_assignments": len({row["esha_code"] for row in ranked}),
        "lookup_db": str(OUT_DB),
        "assignments_csv": str(OUT_ASSIGNMENTS),
        "primary_csv": str(OUT_PRIMARY),
        "rollup": rollup,
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def collect_assignment_rows(
    codes: set[str] | None = None,
    limit_per_code: int | None = None,
    source: str = "auto",
) -> list[dict[str, str]]:
    cache: dict[tuple[str, str], dict[str, str]] = {}
    assignments: list[dict[str, str]] = []
    profiles_by_code = load_profiles_by_code()
    target_codes = set(codes or profiles_by_code.keys())
    fallback_codes: set[str] = set()
    with sqlite3.connect(PRODUCTS_DB) as con:
        for code in sorted(target_codes, key=lambda value: int(value) if value.isdigit() else 10**9):
            if not should_use_direct(code, source):
                fallback_codes.add(code)
                continue
            if source in {"auto", "direct"}:
                profile = profiles_by_code.get(code)
                if profile is None:
                    fallback_codes.add(code)
                    continue
                direct_rows = direct_assignment_rows_for_profile(profile, con, limit=limit_per_code)
                if direct_rows:
                    assignments.extend(direct_rows)
                elif source == "auto":
                    fallback_codes.add(code)

        if fallback_codes:
            for path in pack_files(fallback_codes):
                parsed = parse_pack(path)
                if not parsed:
                    continue
                assignments.extend(assignment_rows_from_pack(parsed, con, cache, limit=limit_per_code))
    return assignments


def build_lookup(codes: set[str] | None = None, limit_per_code: int | None = None, source: str = "auto") -> dict[str, Any]:
    assignments = collect_assignment_rows(codes=codes, limit_per_code=limit_per_code, source=source)
    summary = write_lookup_artifacts(assignments)
    summary["codes_requested"] = sorted(codes) if codes else []
    summary["source"] = source
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build reviewed product->ESHA lookup artifacts from pack contract accepts")
    parser.add_argument("--code", action="append", default=[])
    parser.add_argument("--limit-per-code", type=int, default=None)
    parser.add_argument("--source", choices=("auto", "pack", "direct"), default="auto")
    args = parser.parse_args()
    codes = {str(code).strip() for code in args.code if str(code).strip()} or None
    print(json.dumps(build_lookup(codes=codes, limit_per_code=args.limit_per_code, source=args.source), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
