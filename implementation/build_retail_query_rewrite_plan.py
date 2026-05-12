from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

import build_esha_code_query_packs as packs


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"
OUT_CSV = OUT_DIR / "retail_query_rewrite_plan.csv"
SUMMARY_MD = OUT_DIR / "retail_query_rewrite_plan_summary.md"

FIELDNAMES = [
    "esha_code",
    "description",
    "family",
    "selected_attempt_before",
    "selected_attempt_after",
    "recommended_attempt",
    "query_before",
    "query_after",
    "recommended_query",
    "query_terms_before",
    "query_terms_after",
    "recommended_query_terms",
    "category_terms_after",
    "demoted_query_terms",
    "translated_query_terms",
    "semantic_filter_terms",
    "term_roles_json",
    "top_categories_json",
    "title_match_count",
    "in_scope_category_count",
    "noise_count",
    "exact_product_count",
    "exactness_status",
    "routing_fix_applied",
    "reason",
]


def current_pack_state(index_path: Path) -> dict[str, dict[str, str]]:
    if not index_path.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    with index_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            code = str(row.get("esha_code") or "").strip()
            if not code:
                continue
            selected_attempt = ""
            pack_path = Path(str(row.get("pack_path") or ""))
            if pack_path.exists():
                lines = pack_path.read_text(encoding="utf-8", errors="replace").splitlines()
                selected_attempt = packs.metric_from_lines(lines, "selected_query_attempt")
            out[code] = {
                "selected_attempt_before": selected_attempt or "strict",
                "query_before": str(row.get("query") or ""),
            }
    return out


def load_codes_file(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    codes: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        code = raw.strip()
        if code:
            codes.add(code)
    return codes


def dedupe_attempts(attempts: list[tuple[str, tuple[str, ...]]]) -> list[tuple[str, tuple[str, ...]]]:
    out: list[tuple[str, tuple[str, ...]]] = []
    seen_terms: set[tuple[str, ...]] = set()
    for label, terms in attempts:
        deduped = packs.dedupe_terms(list(terms))
        if not deduped or deduped in seen_terms:
            continue
        seen_terms.add(deduped)
        out.append((label, deduped))
    return out


def attempt_metrics(
    profile: packs.matcher.EshaProfile,
    label: str,
    terms: tuple[str, ...],
    category_terms: tuple[str, ...],
    semantic_filters: tuple[str, ...],
    term_roles: dict[str, str],
    con: sqlite3.Connection,
    query_cache: dict[tuple[str, tuple[str, ...]], tuple[int, list[tuple[str, int]], list[dict[str, str]], str]],
) -> dict[str, Any]:
    query = packs.fts_query(terms)
    if not query:
        return {
            "label": label,
            "terms": terms,
            "query": "",
            "top_categories_json": "[]",
            "total_matches": 0,
            "in_scope_category_count": 0,
            "noise_count": 0,
            "exact_product_count": 0,
            "score": -10_000.0,
            "exactness_status": "unresolved",
        }
    cache_key = (query, category_terms)
    if cache_key in query_cache:
        total_matches, categories, products, error = query_cache[cache_key]
    else:
        total_matches = packs.query_total(con, query, category_terms)
        categories = packs.query_categories(con, query, 30, category_terms)
        products = packs.query_products(con, query, 80, category_terms)
        error = ""
        query_cache[cache_key] = (total_matches, categories, products, error)
    if error:
        return {
            "label": label,
            "terms": terms,
            "query": query,
            "top_categories_json": "[]",
            "total_matches": 0,
            "in_scope_category_count": 0,
            "noise_count": 0,
            "exact_product_count": 0,
            "score": -10_000.0,
            "exactness_status": "unresolved",
        }
    exact_product_count = packs.clean_product_count(
        profile,
        products,
        semantic_filters,
        allow_generated_contracts=False,
    )
    noise_count = sum(
        1
        for product in products
        if packs.classify_product(
            profile,
            product,
            semantic_filters,
            allow_generated_contracts=False,
        )[1]
    )
    in_scope_category_count = sum(
        count
        for category, count in categories
        if packs.category_signal(category, profile.family, set(profile.tokens), profile.description) == "in_scope_category"
    )
    non_retail_penalty = sum(
        1
        for term in terms
        if term_roles.get(term) in {"do_not_query", "ingredient_only", "process_only", "state_only"}
    )
    if exact_product_count == 0:
        exactness_status = "unresolved"
        score = 300.0 if total_matches == 0 else -float(noise_count * 5 + total_matches)
    else:
        strong = noise_count == 0 or exact_product_count >= 5 or exact_product_count / max(len(products), 1) >= 0.2
        exactness_status = "strong" if strong else "uncertain"
        base = 2000.0 if strong else 1000.0
        score = base + (exact_product_count * 60.0) - (noise_count * 5.0) - float(total_matches * 0.5) - (non_retail_penalty * 20.0)
    top_categories = [
        {
            "category": category,
            "count": count,
            "signal": packs.category_signal(category, profile.family, set(profile.tokens), profile.description),
        }
        for category, count in categories[:5]
    ]
    return {
        "label": label,
        "terms": terms,
        "query": query,
        "top_categories_json": json.dumps(top_categories, sort_keys=True),
        "total_matches": total_matches,
        "in_scope_category_count": in_scope_category_count,
        "noise_count": noise_count,
        "exact_product_count": exact_product_count,
        "score": score,
        "exactness_status": exactness_status,
    }


def unresolved_metrics(label: str = "no_viable_query") -> dict[str, Any]:
    return {
        "label": label,
        "terms": (),
        "query": "",
        "top_categories_json": "[]",
        "total_matches": 0,
        "in_scope_category_count": 0,
        "noise_count": 0,
        "exact_product_count": 0,
        "score": -10_000.0,
        "exactness_status": "unresolved",
    }


def select_row(
    profile: packs.matcher.EshaProfile,
    before: dict[str, str],
    best: dict[str, Any],
    primary: tuple[str, ...],
    category_terms: tuple[str, ...],
    semantic_filters: tuple[str, ...],
    term_roles: dict[str, str],
    translations: dict[str, tuple[str, ...]],
) -> dict[str, str]:
    before_label = before.get("selected_attempt_before", "strict")
    before_query = before.get("query_before", "")
    strong = best["exactness_status"] == "strong"
    unresolved = best["exactness_status"] == "unresolved"
    selected_after = best["label"] if strong else ""
    query_after = best["query"] if strong else ""
    if unresolved:
        reason = "clean_zero_preferred"
    elif strong and best["label"] != before_label:
        reason = "rewrite_selected"
    elif strong:
        reason = "current_query_retained"
    else:
        reason = "review_required"
    demoted = [term for term in primary if term not in best["terms"]]
    translated_terms = {
        term: list(values)
        for term, values in translations.items()
        if term in demoted or term in primary
    }
    return {
        "esha_code": profile.code,
        "description": profile.description,
        "family": profile.family,
        "selected_attempt_before": before_label,
        "selected_attempt_after": selected_after,
        "recommended_attempt": best["label"],
        "query_before": before_query,
        "query_after": query_after,
        "recommended_query": best["query"],
        "query_terms_before": " | ".join(primary),
        "query_terms_after": " | ".join(best["terms"]) if strong else "",
        "recommended_query_terms": " | ".join(best["terms"]),
        "category_terms_after": " | ".join(category_terms),
        "demoted_query_terms": " | ".join(demoted),
        "translated_query_terms": json.dumps(translated_terms, sort_keys=True),
        "semantic_filter_terms": " | ".join(semantic_filters),
        "term_roles_json": json.dumps(term_roles, sort_keys=True),
        "top_categories_json": str(best.get("top_categories_json", "[]")),
        "title_match_count": str(best["total_matches"]),
        "in_scope_category_count": str(best["in_scope_category_count"]),
        "noise_count": str(best["noise_count"]),
        "exact_product_count": str(best["exact_product_count"]),
        "exactness_status": str(best["exactness_status"]),
        "routing_fix_applied": "true" if packs.routing_fix_applied_for(profile, primary) else "false",
        "reason": reason,
    }


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, rows: list[dict[str, str]]) -> None:
    by_status: dict[str, int] = {}
    for row in rows:
        status = row["exactness_status"]
        by_status[status] = by_status.get(status, 0) + 1
    top_rewrites = [
        row for row in rows
        if row["selected_attempt_after"] and row["selected_attempt_after"] != row["selected_attempt_before"]
    ][:50]
    unresolved = [row for row in rows if row["exactness_status"] == "unresolved"][:50]
    lines = [
        "# Retail Query Rewrite Plan",
        "",
        f"- rows: {len(rows)}",
        f"- strong: {by_status.get('strong', 0)}",
        f"- uncertain: {by_status.get('uncertain', 0)}",
        f"- unresolved: {by_status.get('unresolved', 0)}",
        "",
        "## Strong Auto-Selected Rewrites",
        "",
        "| esha_code | before | after | category terms | reason | description |",
        "| ---: | --- | --- | --- | --- | --- |",
    ]
    for row in top_rewrites:
        lines.append(
            f"| {row['esha_code']} | {row['selected_attempt_before']} | {row['selected_attempt_after']} | "
            f"{row['category_terms_after']} | {row['reason']} | {row['description']} |"
        )
    lines.extend(
        [
            "",
            "## Clean-Zero / Review Cases",
            "",
            "| esha_code | recommended | semantic filters | reason | description |",
            "| ---: | --- | --- | --- | --- |",
        ]
    )
    for row in unresolved:
        lines.append(
            f"| {row['esha_code']} | {row['recommended_attempt']} | {row['semantic_filter_terms']} | "
            f"{row['reason']} | {row['description']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_rows(
    profiles: list[packs.matcher.EshaProfile],
    current: dict[str, dict[str, str]],
    progress_every: int = 0,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    query_cache: dict[tuple[str, tuple[str, ...]], tuple[int, list[tuple[str, int]], list[dict[str, str]], str]] = {}
    term_cache: dict[str, int] = {}
    started = time.time()
    with sqlite3.connect(packs.PRODUCTS_DB) as con:
        total_products = packs.product_count(con)
        total_profiles = len(profiles)
        for idx, profile in enumerate(profiles, start=1):
            primary = packs.dedupe_terms(list(packs.query_terms_for(profile) or profile.fts_terms or profile.hard_terms))
            category_terms = packs.recommended_category_terms_for(profile, primary)
            term_roles = packs.term_roles_for(profile, primary)
            semantic_filters = packs.semantic_filter_terms_for(profile, primary)
            translations = packs.translated_retail_terms_for(profile, primary)
            attempts = list(packs.query_attempts_for(profile))
            attempts.extend(packs.weighted_query_attempts(packs.term_stats_for(profile, con, total_products, term_cache)))
            attempts.extend(packs.diagnostic_rescue_attempts_for(profile))
            deduped_attempts = dedupe_attempts(attempts)
            if deduped_attempts:
                best = max(
                    (
                        attempt_metrics(profile, label, terms, category_terms, semantic_filters, term_roles, con, query_cache)
                        for label, terms in deduped_attempts
                    ),
                    key=lambda row: (row["score"], row["exact_product_count"], -row["noise_count"]),
                )
            else:
                best = unresolved_metrics()
            rows.append(
                select_row(
                    profile,
                    current.get(profile.code, {}),
                    best,
                    primary,
                    category_terms,
                    semantic_filters,
                    term_roles,
                    translations,
                )
            )
            if progress_every and (idx % progress_every == 0 or idx == total_profiles):
                elapsed = time.time() - started
                rate = idx / elapsed if elapsed > 0 else 0.0
                eta = (total_profiles - idx) / rate if rate > 0 else 0.0
                print(
                    json.dumps(
                        {
                            "processed": idx,
                            "total": total_profiles,
                            "elapsed_s": round(elapsed, 1),
                            "rate_cards_per_s": round(rate, 2),
                            "eta_s": round(eta, 1),
                        }
                    ),
                    file=sys.stderr,
                    flush=True,
                )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a whole-corpus retail query rewrite plan for ESHA packs")
    parser.add_argument("--code", action="append", default=[])
    parser.add_argument("--contains", default="")
    parser.add_argument("--family", default="")
    parser.add_argument("--limit-codes", type=int, default=None)
    parser.add_argument("--out-csv", type=Path, default=OUT_CSV)
    parser.add_argument("--summary-out", type=Path, default=SUMMARY_MD)
    parser.add_argument("--index", type=Path, default=packs.OUT_INDEX)
    parser.add_argument("--codes-file", type=Path, default=None)
    parser.add_argument("--progress-every", type=int, default=1000)
    args = parser.parse_args()

    packs._RETAIL_QUERY_REWRITE_PLAN_CACHE = {}
    codes = {str(code).strip() for code in args.code if str(code).strip()}
    codes |= load_codes_file(args.codes_file)
    profiles = packs.select_profiles(
        packs.load_profiles(),
        codes=codes,
        contains=args.contains,
        family=args.family,
        limit=args.limit_codes,
    )
    current = current_pack_state(args.index)
    rows = build_rows(profiles, current, progress_every=max(0, int(args.progress_every)))
    write_csv(args.out_csv, rows)
    write_summary(args.summary_out, rows)
    print(
        json.dumps(
            {
                "rows": len(rows),
                "out_csv": str(args.out_csv),
                "summary_out": str(args.summary_out),
                "strong": sum(1 for row in rows if row["exactness_status"] == "strong"),
                "uncertain": sum(1 for row in rows if row["exactness_status"] == "uncertain"),
                "unresolved": sum(1 for row in rows if row["exactness_status"] == "unresolved"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
