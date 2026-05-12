#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import match_esha_to_products as matcher
import self_heal_common as sh


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"

DEFAULT_MAP = OUT_DIR / "product_to_best_esha_full_map.csv"
DEFAULT_MEMBERS = OUT_DIR / "product_evidence_cluster_members_v2.csv"
DEFAULT_OUT_DIR = OUT_DIR / "assignment_verification"


TOKEN_ALIASES = {
    "bbq": "barbecue",
    "barbeque": "barbecue",
    "citru": "citrus",
    "tomatoes": "tomato",
    "doughnuts": "doughnut",
    "donuts": "doughnut",
    "hotsauce": "hot_sauce",
    "hot": "hot",
    "gochu": "gochujang",
    "jang": "gochujang",
}

GENERIC_TERMS = {
    "100",
    "added",
    "artificial",
    "beverage",
    "brand",
    "burst",
    "can",
    "canned",
    "classic",
    "count",
    "dry",
    "flavor",
    "flavored",
    "fresh",
    "frozen",
    "juice",
    "large",
    "medium",
    "natural",
    "original",
    "pack",
    "premium",
    "ready",
    "regular",
    "select",
    "serving",
    "small",
    "style",
    "with",
}

FORM_TERMS = {
    "chopped",
    "chunky",
    "crushed",
    "diced",
    "ground",
    "peeled",
    "petite",
    "puree",
    "pureed",
    "sliced",
    "stewed",
    "whole",
}

IDENTITY_TERMS = (
    set(matcher.FRUITS)
    | set(matcher.VEGETABLES)
    | set(matcher.LEGUMES)
    | {
        "barbecue",
        "basil",
        "bbq",
        "buffalo",
        "cake",
        "cheesecake",
        "cilantro",
        "citrus",
        "clam",
        "chowder",
        "coffee",
        "cream",
        "doughnut",
        "ginger",
        "gochujang",
        "herb",
        "hot_sauce",
        "hotsauce",
        "ice",
        "italian",
        "lychee",
        "mexican",
        "pasta",
        "parfait",
        "pomelo",
        "roasted",
        "sauce",
        "soup",
        "sparkling",
        "smoothie",
        "water",
        "yogurt",
        "yuzu",
    }
)

BERRY_TERMS = {"blackberry", "blueberry", "cranberry", "raspberry", "strawberry"}
WATER_FLAVOR_TERMS = set(matcher.FRUITS) | {"citrus", "ginger", "yuzu", "pomelo", "lychee"}
GENERIC_UMBRELLA_TERMS = {"fruit", "fruits", "vegetable", "vegetables"}
SPECIFIC_FRUITS = set(matcher.FRUITS) - {"fruit", "fruits"}
SPECIFIC_VEGETABLES = set(matcher.VEGETABLES) - {"vegetable", "vegetables"}


def canon(token: str) -> str:
    return TOKEN_ALIASES.get(token, token)


def tokens_for(text: object) -> set[str]:
    return {canon(t) for t in matcher.tokens_for(str(text or "")) if t}


def split_terms(value: object) -> set[str]:
    return {canon(t) for t in str(value or "").split() if t}


def esha_head(description: object) -> str:
    return str(description or "").split(",", 1)[0].strip()


def load_member_evidence(path: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            fdc_id = str(row.get("fdc_id") or "")
            if fdc_id and fdc_id not in out:
                out[fdc_id] = row
    return out


def category_targets(product_description: str, category: str) -> tuple[str, str, tuple[str, ...]]:
    title = tokens_for(product_description)
    lane = sh.category_lane_for(product_description, category, title)
    form = sh.product_form_for(product_description, category, lane, title)
    heads = sh.target_heads_for(lane, form, "main", title)
    return lane, form, heads


def candidate_identity_terms(description: str) -> set[str]:
    tokens = tokens_for(description)
    terms = {t for t in tokens if t in IDENTITY_TERMS and t not in GENERIC_TERMS}
    if "berry" in tokens:
        terms.add("berry")
    if "barbecue" in tokens or "bbq" in tokens:
        terms.add("barbecue")
    if "chowder" in tokens:
        terms.add("chowder")
    if "clam" in tokens:
        terms.add("clam")
    if "pasta" in tokens:
        terms.add("pasta")
    if "sauce" in tokens:
        terms.add("sauce")
    return terms


def product_required_terms(row: dict[str, str], evidence: dict[str, str], lane: str, form: str) -> set[str]:
    title_tokens = tokens_for(row.get("product_description", ""))
    evidence_terms = (
        split_terms(evidence.get("title_identity_terms", ""))
        | split_terms(evidence.get("primary_food", ""))
        | split_terms(evidence.get("product_form", ""))
    )
    required = {t for t in (title_tokens | evidence_terms) if t in IDENTITY_TERMS and t not in GENERIC_TERMS}

    if lane == "water":
        required |= title_tokens & WATER_FLAVOR_TERMS
        required.add("water")
    if form in {"barbecue_sauce", "hot_sauce", "butter_sauce", "pasta_sauce"}:
        if form == "barbecue_sauce":
            required.add("barbecue")
        if form == "hot_sauce":
            required |= title_tokens & {"buffalo", "gochujang", "hot_sauce"}
        if form == "butter_sauce":
            required.add("butter")
        if form == "pasta_sauce":
            required |= {"pasta", "sauce"}
    if form in {"yogurt", "yogurt_smoothie", "yogurt_parfait"}:
        required.add("yogurt")
        if form == "yogurt_smoothie":
            required.add("smoothie")
        if form == "yogurt_parfait":
            required.add("parfait")
    if "sauce" in title_tokens and ("tomato" in title_tokens or lane in {"vegetable", "sauce_condiment"}):
        required.add("sauce")
    if "chowder" in title_tokens:
        required.add("chowder")
    if "clam" in title_tokens:
        required.add("clam")
    if "okra" in title_tokens:
        required.add("okra")
    if "corn" in title_tokens and "okra" in required:
        required.add("corn")
    if "eggplant" in title_tokens:
        required.add("eggplant")
    if required & SPECIFIC_FRUITS:
        required -= {"fruit", "fruits"}
    if required & SPECIFIC_VEGETABLES:
        required -= {"vegetable", "vegetables"}
    return required


def product_all_terms(row: dict[str, str], evidence: dict[str, str]) -> set[str]:
    return (
        tokens_for(row.get("product_description", ""))
        | split_terms(evidence.get("title_identity_terms", ""))
        | split_terms(evidence.get("ingredient_core_terms", ""))
        | split_terms(evidence.get("title_tokens", ""))
        | split_terms(evidence.get("ingredient_tokens", ""))
    )


def term_covered(term: str, candidate_terms: set[str], candidate_tokens: set[str]) -> bool:
    if term in candidate_terms or term in candidate_tokens:
        return True
    if term in BERRY_TERMS and "berry" in candidate_terms:
        return True
    if term == "barbecue" and ({"bbq", "barbecue"} & candidate_terms):
        return True
    if term == "hot_sauce" and ({"buffalo", "hot_sauce", "gochujang"} & candidate_terms):
        return True
    if term == "soup" and "chowder" in (candidate_terms | candidate_tokens):
        return True
    return False


def candidate_extra_terms(candidate_terms: set[str], product_terms: set[str]) -> set[str]:
    out = set()
    for term in candidate_terms:
        if term in GENERIC_TERMS or term in GENERIC_UMBRELLA_TERMS or term in {"water", "soup", "sauce", "tomato"}:
            continue
        if term == "berry" and product_terms & BERRY_TERMS:
            continue
        if term not in product_terms:
            out.add(term)
    return out


def form_mismatch_reason(form: str, row: dict[str, str], candidate_description: str) -> str:
    title = tokens_for(row.get("product_description", ""))
    candidate_tokens = tokens_for(candidate_description)
    sauce_reason = sh.sauce_form_mismatch_reason(form, candidate_description) if hasattr(sh, "sauce_form_mismatch_reason") else ""
    if sauce_reason:
        return sauce_reason
    if "sauce" in title and "tomato" in title and "sauce" not in candidate_tokens:
        return "product_tomato_sauce_to_non_sauce_tomato"
    if "chowder" in title and "chowder" not in candidate_tokens:
        return "product_chowder_to_non_chowder_soup"
    if "clam" in title and "clam" not in candidate_tokens:
        return "product_clam_to_non_clam_candidate"
    return ""


def margin_from_reason(reason: str) -> float | None:
    match = re.search(r"margin=([-+]?\d+(?:\.\d+)?)", reason or "")
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def classify_row(row: dict[str, str], evidence: dict[str, str]) -> dict[str, object]:
    desc = row.get("product_description", "")
    category = row.get("branded_food_category", "")
    assigned_desc = row.get("best_esha_description", "")
    assigned_head = row.get("best_esha_head") or esha_head(assigned_desc)
    lane, form, target_heads = category_targets(desc, category)
    candidate_tokens = tokens_for(assigned_desc)
    candidate_terms = candidate_identity_terms(assigned_desc)
    required = product_required_terms(row, evidence, lane, form)
    all_product_terms = product_all_terms(row, evidence)
    missing = {term for term in required if not term_covered(term, candidate_terms, candidate_tokens)}
    extra = candidate_extra_terms(candidate_terms, all_product_terms)
    envelope_ok, _envelope_reason = sh.policy.category_allows_head(
        category=category,
        product_description=desc,
        title_tokens=tokens_for(desc),
        candidate_head=assigned_head,
    )
    target_ok = sh.head_compatible(target_heads, assigned_head) if target_heads else True
    category_ok = envelope_ok and target_ok
    form_reason = form_mismatch_reason(form, row, assigned_desc)
    margin = margin_from_reason(row.get("self_heal_reason", ""))

    reasons: list[str] = []
    if not category_ok:
        reasons.append("category_head_mismatch")
    if form_reason:
        reasons.append(form_reason)
    if missing:
        reasons.append("missing_product_identity:" + "+".join(sorted(missing)))
    if extra:
        reasons.append("candidate_unasked_identity:" + "+".join(sorted(extra)))
    if margin is not None and margin < 2.0 and reasons:
        reasons.append(f"low_margin:{margin:.3f}")

    if not row.get("best_esha_code"):
        verdict = "unassigned"
    elif not category_ok:
        verdict = "category_mismatch"
    elif form_reason:
        verdict = "form_mismatch"
    elif missing:
        verdict = "identity_missing"
    elif extra:
        verdict = "candidate_extra_identity"
    elif margin is not None and margin < 2.0:
        verdict = "low_margin_compatible"
    else:
        verdict = "perfect_or_strong"

    return {
        "verification_verdict": verdict,
        "verification_reasons": " | ".join(reasons),
        "computed_lane": lane,
        "computed_form": form,
        "computed_target_heads": "|".join(target_heads),
        "assigned_head": assigned_head,
        "required_identity_terms": " ".join(sorted(required)),
        "candidate_identity_terms": " ".join(sorted(candidate_terms)),
        "missing_product_identity_terms": " ".join(sorted(missing)),
        "candidate_extra_identity_terms": " ".join(sorted(extra)),
        "category_ok": "1" if category_ok else "0",
        "category_envelope_ok": "1" if envelope_ok else "0",
        "target_head_ok": "1" if target_ok else "0",
        "margin": "" if margin is None else f"{margin:.3f}",
    }


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def summarize_counts(values: Iterable[str], limit: int = 8) -> str:
    return " | ".join(f"{k}:{v}" for k, v in Counter(v for v in values if v).most_common(limit))


def build_workbench(args: argparse.Namespace) -> dict[str, object]:
    evidence_by_fdc = load_member_evidence(args.product_members)
    rows: list[dict[str, object]] = []
    perfect_rows: list[dict[str, object]] = []
    review_rows: list[dict[str, object]] = []
    with args.input_map.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for i, row in enumerate(reader, start=1):
            if args.limit and i > args.limit:
                break
            if not row.get("best_esha_code"):
                continue
            evidence = evidence_by_fdc.get(str(row.get("fdc_id") or ""), {})
            verification = classify_row(row, evidence)
            out = {
                **{k: row.get(k, "") for k in reader.fieldnames or []},
                **verification,
                "cluster_id": evidence.get("cluster_id", ""),
                "evidence_category_lane": evidence.get("category_lane", ""),
                "evidence_product_form": evidence.get("product_form", ""),
                "evidence_primary_food": evidence.get("primary_food", ""),
                "evidence_title_identity_terms": evidence.get("title_identity_terms", ""),
                "evidence_ingredient_core_terms": evidence.get("ingredient_core_terms", ""),
            }
            rows.append(out)
            if verification["verification_verdict"] == "perfect_or_strong":
                perfect_rows.append(out)
            else:
                review_rows.append(out)

    cluster_groups: dict[tuple[str, str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        key = (
            str(row.get("verification_verdict", "")),
            str(row.get("branded_food_category", "")),
            str(row.get("best_esha_code", "")),
            str(row.get("computed_lane", "")),
            str(row.get("required_identity_terms", "")),
        )
        cluster_groups[key].append(row)

    cluster_rows: list[dict[str, object]] = []
    for (verdict, category, code, lane, required), group in cluster_groups.items():
        group.sort(key=lambda r: str(r.get("product_description", "")))
        cluster_rows.append(
            {
                "verification_verdict": verdict,
                "n_products": len(group),
                "branded_food_category": category,
                "best_esha_code": code,
                "best_esha_description": group[0].get("best_esha_description", ""),
                "computed_lane": lane,
                "required_identity_terms": required,
                "top_reasons": summarize_counts((str(r.get("verification_reasons", "")) for r in group), 5),
                "top_forms": summarize_counts((str(r.get("computed_form", "")) for r in group), 5),
                "sample_products": " || ".join(str(r.get("product_description", "")) for r in group[:8]),
                "sample_fdc_ids": " ".join(str(r.get("fdc_id", "")) for r in group[:12]),
            }
        )
    cluster_rows.sort(
        key=lambda r: (
            {"category_mismatch": 5, "form_mismatch": 4, "identity_missing": 3, "candidate_extra_identity": 2, "low_margin_compatible": 1}.get(
                str(r["verification_verdict"]),
                0,
            ),
            int(r["n_products"]),
        ),
        reverse=True,
    )

    rows_path = args.output_dir / "assignment_verification_rows.csv"
    review_path = args.output_dir / "assignment_verification_review_rows.csv"
    perfect_path = args.output_dir / "assignment_verification_perfect_rows.csv"
    clusters_path = args.output_dir / "assignment_verification_clusters.csv"
    summary_path = args.output_dir / "assignment_verification_summary.json"
    md_path = args.output_dir / "assignment_verification_summary.md"

    base_fields = [
        "gtin_upc",
        "fdc_id",
        "product_description",
        "branded_food_category",
        "brand_owner",
        "brand_name",
        "best_esha_code",
        "best_esha_description",
        "best_esha_head",
        "best_esha_family",
        "score",
        "n_candidates",
        "assignment_source",
        "self_heal_status",
        "self_heal_reason",
        "self_heal_target_heads",
        "verification_verdict",
        "verification_reasons",
        "computed_lane",
        "computed_form",
        "computed_target_heads",
        "assigned_head",
        "required_identity_terms",
        "candidate_identity_terms",
        "missing_product_identity_terms",
        "candidate_extra_identity_terms",
        "category_ok",
        "category_envelope_ok",
        "target_head_ok",
        "margin",
        "cluster_id",
        "evidence_category_lane",
        "evidence_product_form",
        "evidence_primary_food",
        "evidence_title_identity_terms",
        "evidence_ingredient_core_terms",
    ]
    write_csv(rows_path, rows, base_fields)
    write_csv(review_path, review_rows, base_fields)
    write_csv(perfect_path, perfect_rows[: args.perfect_sample_limit], base_fields)
    write_csv(
        clusters_path,
        cluster_rows,
        [
            "verification_verdict",
            "n_products",
            "branded_food_category",
            "best_esha_code",
            "best_esha_description",
            "computed_lane",
            "required_identity_terms",
            "top_reasons",
            "top_forms",
            "sample_products",
            "sample_fdc_ids",
        ],
    )

    summary = {
        "input_map": str(args.input_map),
        "rows_scanned": len(rows),
        "review_rows": len(review_rows),
        "perfect_or_strong_rows": len(perfect_rows),
        "verdict_counts": Counter(str(r["verification_verdict"]) for r in rows).most_common(),
        "top_review_clusters": [
            {k: r[k] for k in ("verification_verdict", "n_products", "branded_food_category", "best_esha_code", "best_esha_description", "top_reasons", "sample_products")}
            for r in cluster_rows[:25]
        ],
        "outputs": {
            "rows": str(rows_path),
            "review_rows": str(review_path),
            "perfect_rows": str(perfect_path),
            "clusters": str(clusters_path),
            "markdown": str(md_path),
            "summary": str(summary_path),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(md_path, summary, cluster_rows)
    return summary


def write_markdown(path: Path, summary: dict[str, object], cluster_rows: list[dict[str, object]]) -> None:
    lines = [
        "# Assignment Verification Workbench\n\n",
        "This is a human-readable verification layer over the product->ESHA map. It compares product-required identity terms against the assigned ESHA leaf and groups failures into review clusters.\n\n",
        "## Summary\n\n",
        f"- Rows scanned: {summary['rows_scanned']:,}\n",
        f"- Perfect/strong rows: {summary['perfect_or_strong_rows']:,}\n",
        f"- Review rows: {summary['review_rows']:,}\n",
        f"- Verdict counts: {summary['verdict_counts']}\n\n",
        "## Top Review Clusters\n\n",
    ]
    for row in [r for r in cluster_rows if r["verification_verdict"] != "perfect_or_strong"][:60]:
        lines.extend(
            [
                f"### `{row['verification_verdict']}` n={row['n_products']} code={row['best_esha_code']}\n",
                f"- ESHA: {row['best_esha_description']}\n",
                f"- category/lane: {row['branded_food_category']} / {row['computed_lane']}\n",
                f"- required: `{row['required_identity_terms']}`\n",
                f"- reasons: {row['top_reasons']}\n",
                f"- samples: {row['sample_products']}\n\n",
            ]
        )
    lines.append("## Files\n\n")
    outputs = summary["outputs"]
    assert isinstance(outputs, dict)
    for label, output in outputs.items():
        lines.append(f"- {label}: `{output}`\n")
    path.write_text("".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build human-review verification artifacts for product->ESHA assignments.")
    parser.add_argument("--input-map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--product-members", type=Path, default=DEFAULT_MEMBERS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--perfect-sample-limit", type=int, default=50000)
    return parser.parse_args()


def main() -> None:
    print(json.dumps(build_workbench(parse_args()), indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
