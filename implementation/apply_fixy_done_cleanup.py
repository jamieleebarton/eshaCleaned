from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import match_esha_to_products as matcher
from identity_contract import FoodIdentity, compatibility_reason, esha_identity, product_identity, tokenize


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"

DEFAULT_INPUT_MAP = OUT_DIR / "product_to_best_esha_full_map.vM.csv"
DEFAULT_CROSSCHECK = OUT_DIR / "fixy_done_crosscheck" / "fixy_done_product_crosscheck.csv"
DEFAULT_ESHA_CSV = ROOT / "esha_cleaned.csv"
DEFAULT_ESHA_SPINE = OUT_DIR / "esha_spine.csv"
DEFAULT_VCLUSTER_MAP = OUT_DIR / "product_to_best_esha_full_map.vCluster.csv"
DEFAULT_OUTPUT_MAP = OUT_DIR / "product_to_best_esha_full_map.vFixy.csv"
DEFAULT_DIFF = OUT_DIR / "fixy_done_cleanup_diff.csv"
DEFAULT_REMAPS = OUT_DIR / "fixy_done_high_confidence_remap_proposals.csv"
DEFAULT_QUARANTINE = OUT_DIR / "fixy_done_quarantine_proposals.csv"
DEFAULT_BRIDGE_REPORT = OUT_DIR / "fixy_done_description_bridge_matches.csv"
DEFAULT_SUMMARY = OUT_DIR / "fixy_done_cleanup_summary.json"

BASE_COLUMNS = [
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
    "score_num",
]

FLAG_COLUMNS = [
    "fixy_cleanup_action",
    "fixy_cleanup_reason",
    "fixy_cleanup_target_source",
    "fixy_cleanup_match_source",
    "fixy_cleanup_old_code",
    "fixy_cleanup_old_description",
    "fixy_cleanup_suggested_code",
    "fixy_cleanup_suggested_description",
    "fixy_cleanup_review_reasons",
]

HARD_QUARANTINE_REASONS = {
    "product_esha_no_identity_overlap",
    "graph_structural_reject",
    "multi_category_esha_code_used_by_fallback",
}

ANCHOR_DISAGREEMENT_REASONS = {
    "canonical_surface_code_disagreement",
    "trusted_canonical_fndds_code_disagreement",
}

QUARANTINE_IF_NO_TARGET_REASONS = HARD_QUARANTINE_REASONS | ANCHOR_DISAGREEMENT_REASONS

SAFE_RECOVERY_REASONS = {
    "unassigned_vM",
    "canonical_surface_code_disagreement",
    "trusted_canonical_fndds_code_disagreement",
    "graph_structural_reject",
    "product_esha_no_identity_overlap",
    "low_score",
}

BROAD_FNDDS_DESCRIPTIONS = {
    "candy",
    "cookie",
    "crackers",
    "ice cream",
    "potato chips",
    "chocolate candy",
    "cereal or granola bar",
    "salsa",
    "popcorn",
    "beef jerky",
    "yogurt",
}

DISTINCTIVE_DROP_TOKENS = {
    "added",
    "all",
    "and",
    "artificial",
    "brand",
    "commercial",
    "dry",
    "extra",
    "fat",
    "flavor",
    "flavored",
    "food",
    "free",
    "from",
    "fresh",
    "fs",
    "generic",
    "grade",
    "homogenized",
    "light",
    "low",
    "lowfat",
    "milkfat",
    "natural",
    "nfs",
    "nonfat",
    "ns",
    "original",
    "percent",
    "prepared",
    "recipe",
    "regular",
    "reduced",
    "serving",
    "style",
    "vitamin",
    "with",
    "whole",
}

GENERIC_FOOD_TOKENS = {
    "bar",
    "beverage",
    "candy",
    "cheese",
    "chips",
    "cookie",
    "cracker",
    "cream",
    "dessert",
    "dip",
    "dish",
    "drink",
    "food",
    "fruit",
    "ice",
    "jelly",
    "juice",
    "meal",
    "milk",
    "mix",
    "oil",
    "salad",
    "sauce",
    "snack",
    "soup",
    "spread",
    "vegetable",
    "water",
    "yogurt",
}

GENERIC_DESCRIPTION_KEYS = {
    "assorted",
    "classic",
    "original",
    "premium",
    "premium selects",
    "rings",
    "select",
    "selects",
}

SAFE_SINGLE_TOKEN_KEYS = {
    "biscuit",
    "honey",
    "kefir",
    "mustard",
    "tofu",
}


@dataclass(frozen=True)
class EshaCode:
    code: str
    description: str
    head: str
    family: str
    fact: FoodIdentity


@dataclass(frozen=True)
class BridgeLabel:
    key: str
    fixy_fndds_code: str
    fixy_fndds_description: str
    canonical_surface_esha_codes: str
    trusted_canonical_fndds_esha_codes: str
    support_count: int
    source_fdc_ids: str
    source_categories: str


def norm_code(value: str) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    if re.fullmatch(r"0+\d+", text):
        text = text.lstrip("0") or "0"
    return text


def norm_fdc(value: str) -> str:
    return norm_code(value)


def norm_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9%]+", " ", text).split())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_codes(value: str) -> list[str]:
    return [norm_code(part) for part in str(value or "").split(" | ") if norm_code(part)]


def useful_bridge_key(key: str) -> tuple[bool, str]:
    if not key:
        return False, "blank_key"
    if key in GENERIC_DESCRIPTION_KEYS:
        return False, "generic_description_key"
    tokens = set(tokenize(key))
    if len(tokens) >= 2:
        return True, "ok"
    if key in SAFE_SINGLE_TOKEN_KEYS:
        return True, "safe_single_token"
    return False, "too_short_or_generic"


def load_esha_catalog(esha_csv: Path, spine_csv: Path) -> dict[str, EshaCode]:
    meta: dict[str, dict[str, str]] = {}
    if spine_csv.exists():
        for row in read_csv(spine_csv):
            code = norm_code(row.get("esha_code", ""))
            if code:
                meta[code] = row

    out: dict[str, EshaCode] = {}
    for row in read_csv(esha_csv):
        code = norm_code(row.get("EshaCode", ""))
        desc = (row.get("Description") or "").strip()
        if not code or not desc:
            continue
        spine = meta.get(code, {})
        out[code] = EshaCode(
            code=code,
            description=desc,
            head=(spine.get("esha_head") or desc.split(",", 1)[0]).strip(),
            family=(spine.get("esha_family") or matcher.detect_family(matcher.tokens_for(desc), desc.lower())).strip(),
            fact=esha_identity(desc),
        )
    return out


def load_vcluster_by_fdc(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    for row in read_csv(path):
        fdc = norm_fdc(row.get("fdc_id", ""))
        if fdc:
            out.setdefault(fdc, row)
    return out


def build_description_bridge_labels(crosscheck_rows: list[dict[str, str]]) -> tuple[dict[str, BridgeLabel], Counter[str]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    reject_counts: Counter[str] = Counter()
    for row in crosscheck_rows:
        key = norm_key(row.get("fixy_product_description", ""))
        ok, reason = useful_bridge_key(key)
        if not ok:
            reject_counts[reason] += 1
            continue
        grouped.setdefault(key, []).append(row)

    labels: dict[str, BridgeLabel] = {}
    for key, rows in grouped.items():
        fndds_labels = {
            (norm_code(row.get("fixy_fndds_code", "")), row.get("fixy_fndds_description", ""))
            for row in rows
            if norm_code(row.get("fixy_fndds_code", ""))
        }
        if len(fndds_labels) != 1:
            reject_counts["ambiguous_fndds_label"] += 1
            continue
        canonical_codes: set[str] = set()
        trusted_codes: set[str] = set()
        fdc_ids: list[str] = []
        categories: set[str] = set()
        for row in rows:
            canonical_codes.update(parse_codes(row.get("canonical_surface_esha_codes", "")))
            trusted_codes.update(parse_codes(row.get("trusted_canonical_fndds_esha_codes", "")))
            fdc = norm_fdc(row.get("fixy_fdc_id", ""))
            if fdc and len(fdc_ids) < 12:
                fdc_ids.append(fdc)
            category = row.get("fixy_category", "")
            if category:
                categories.add(category)
        fndds_code, fndds_description = next(iter(fndds_labels))
        labels[key] = BridgeLabel(
            key=key,
            fixy_fndds_code=fndds_code,
            fixy_fndds_description=fndds_description,
            canonical_surface_esha_codes=" | ".join(sorted(canonical_codes, key=lambda c: (not c.isdigit(), int(c) if c.isdigit() else c))),
            trusted_canonical_fndds_esha_codes=" | ".join(sorted(trusted_codes, key=lambda c: (not c.isdigit(), int(c) if c.isdigit() else c))),
            support_count=len(rows),
            source_fdc_ids=" | ".join(fdc_ids),
            source_categories=" | ".join(sorted(categories)[:12]),
        )
    return labels, reject_counts


def target_from_crosscheck(row: dict[str, str]) -> tuple[str, str]:
    canonical = parse_codes(row.get("canonical_surface_esha_codes", ""))
    trusted = parse_codes(row.get("trusted_canonical_fndds_esha_codes", ""))
    if len(canonical) == 1:
        return canonical[0], "canonical_surface"
    if len(trusted) == 1:
        return trusted[0], "trusted_fndds"
    return "", ""


def reason_set(row: dict[str, str]) -> set[str]:
    return {reason for reason in str(row.get("review_reasons") or "").split("|") if reason}


def numeric_score(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def distinctive_tokens(description: str) -> set[str]:
    tokens = set(tokenize(description))
    out: set[str] = set()
    for token in tokens:
        if token.isdigit() or len(token) < 3:
            continue
        if token in DISTINCTIVE_DROP_TOKENS or token in GENERIC_FOOD_TOKENS:
            continue
        out.add(token)
    return out


def evidence_tokens(row: dict[str, str]) -> set[str]:
    text = " ".join(
        [
            row.get("fixy_product_description", ""),
            row.get("fixy_category", ""),
            row.get("fixy_fndds_description", ""),
            row.get("ingredient_signature", ""),
        ]
    )
    return set(tokenize(text))


def target_is_supported(row: dict[str, str], target: EshaCode, target_source: str) -> tuple[bool, str]:
    product = product_identity(
        product_description=row.get("fixy_product_description", ""),
        category=row.get("fixy_category", ""),
        ingredient_signature=row.get("ingredient_signature", ""),
    )
    reject = compatibility_reason(product, target.fact)
    if reject:
        return False, f"target_identity_reject:{reject}"

    evidence = evidence_tokens(row)
    target_distinctive = distinctive_tokens(target.description)
    absent_distinctive = target_distinctive - evidence
    if absent_distinctive:
        return False, f"target_extra_distinctive_absent:{','.join(sorted(absent_distinctive))}"

    product_primary = set(product.primary_terms)
    target_primary = set(target.fact.primary_terms)
    product_identity_terms = set(product.identity_terms)
    target_identity_terms = set(target.fact.identity_terms)
    if product_primary and target_primary and product_primary & target_primary:
        return True, "primary_identity_overlap"
    if product_identity_terms and target_identity_terms and product_identity_terms & target_identity_terms:
        return True, "identity_overlap"
    if product.form and product.form == target.fact.form:
        return True, "form_overlap"
    if target_source == "canonical_surface" and not target_distinctive:
        return True, "canonical_generic_form"
    return False, "target_without_identity_overlap"


def eligible_for_remap(row: dict[str, str], target: EshaCode, target_source: str) -> tuple[bool, str]:
    reasons = reason_set(row)
    if row.get("verdict") == "out_of_scope":
        return False, "out_of_scope"
    if not (reasons & SAFE_RECOVERY_REASONS):
        return False, "no_cleanup_reason"
    fndds_description = row.get("fixy_fndds_description", "").strip().lower()
    current_code = norm_code(row.get("vm_esha_code", ""))
    vcluster_code = norm_code(row.get("vcluster_code", ""))
    if row.get("fixy_match_source") == "description_bridge" and current_code:
        return False, "description_bridge_no_assigned_remap"
    if fndds_description in BROAD_FNDDS_DESCRIPTIONS and target_source != "canonical_surface":
        return False, "broad_fndds_needs_surface_anchor"
    if target_source == "canonical_surface" and current_code:
        hard_current_failure = bool(reasons & {"graph_structural_reject", "product_esha_no_identity_overlap"})
        if target.code != vcluster_code and not hard_current_failure:
            return False, "canonical_target_without_cluster_agreement"
        if fndds_description in BROAD_FNDDS_DESCRIPTIONS and target.code != vcluster_code and not hard_current_failure:
            return False, "broad_canonical_target_without_cluster_agreement"
    return target_is_supported(row, target, target_source)


def eligible_for_quarantine(row: dict[str, str]) -> tuple[bool, str]:
    reasons = reason_set(row)
    if not row.get("vm_esha_code"):
        return False, "already_unassigned"
    if row.get("fixy_match_source") == "description_bridge":
        if {"product_esha_no_identity_overlap", "low_score", "vcluster_code_disagreement"} <= reasons:
            return True, "description_bridge_low_score_identity_and_cluster_disagreement"
        return False, "description_bridge_no_hard_quarantine_signal"
    hard = reasons & HARD_QUARANTINE_REASONS
    if hard:
        return True, "hard_fixy_signal:" + ",".join(sorted(hard))
    if (reasons & ANCHOR_DISAGREEMENT_REASONS) and "fndds_esha_no_identity_overlap" in reasons and "vcluster_code_disagreement" in reasons:
        return True, "anchor_disagreement_with_identity_and_cluster_disagreement"
    if "fndds_esha_no_identity_overlap" in reasons and "low_score" in reasons and "vcluster_code_disagreement" in reasons:
        return True, "low_score_identity_and_cluster_disagreement"
    return False, "no_hard_quarantine_signal"


def proposal_from(row: dict[str, str], action: str, reason: str, target: EshaCode | None = None, target_source: str = "") -> dict[str, str]:
    return {
        "action": action,
        "action_reason": reason,
        "target_source": target_source,
        "fixy_match_source": row.get("fixy_match_source", "fdc"),
        "fixy_bridge_support_count": row.get("fixy_bridge_support_count", ""),
        "fixy_bridge_source_fdc_ids": row.get("fixy_bridge_source_fdc_ids", ""),
        "fixy_fdc_id": row.get("fixy_fdc_id", ""),
        "gtin_upc": row.get("vm_gtin_upc", ""),
        "product_description": row.get("vm_product_description") or row.get("fixy_product_description", ""),
        "branded_food_category": row.get("vm_category") or row.get("fixy_category", ""),
        "brand_owner": row.get("vm_brand_owner", ""),
        "brand_name": row.get("vm_brand_name", ""),
        "fixy_fndds_code": row.get("fixy_fndds_code", ""),
        "fixy_fndds_description": row.get("fixy_fndds_description", ""),
        "old_best_esha_code": row.get("vm_esha_code", ""),
        "old_best_esha_description": row.get("vm_esha_description", ""),
        "old_best_esha_head": row.get("vm_esha_head", ""),
        "old_best_esha_family": row.get("vm_esha_family", ""),
        "old_assignment_source": row.get("vm_assignment_source", ""),
        "old_score": row.get("vm_score", ""),
        "new_best_esha_code": target.code if target else "",
        "new_best_esha_description": target.description if target else "",
        "new_best_esha_head": target.head if target else "",
        "new_best_esha_family": target.family if target else "",
        "review_reasons": row.get("review_reasons", ""),
        "canonical_surface_esha_codes": row.get("canonical_surface_esha_codes", ""),
        "trusted_canonical_fndds_esha_codes": row.get("trusted_canonical_fndds_esha_codes", ""),
        "graph_cluster_flags": row.get("graph_cluster_flags", ""),
        "graph_cluster_reject_reason": row.get("graph_cluster_reject_reason", ""),
        "vcluster_code": row.get("vcluster_code", ""),
        "vcluster_description": row.get("vcluster_description", ""),
        "vcluster_agreement_status": row.get("vcluster_agreement_status", ""),
    }


def bridge_check_for_row(row: dict[str, str], label: BridgeLabel, vcluster_row: dict[str, str]) -> dict[str, str]:
    current_code = norm_code(row.get("best_esha_code", ""))
    current_description = row.get("best_esha_description", "")
    current_fact = esha_identity(current_description) if current_code and current_description else None
    product = product_identity(
        product_description=row.get("product_description", ""),
        category=row.get("branded_food_category", ""),
        ingredient_signature="",
    )
    target_code, target_source = target_from_crosscheck(
        {
            "canonical_surface_esha_codes": label.canonical_surface_esha_codes,
            "trusted_canonical_fndds_esha_codes": label.trusted_canonical_fndds_esha_codes,
        }
    )
    reasons: list[str] = []
    if not current_code:
        reasons.append("unassigned_vM")
    elif target_code and current_code != target_code:
        if target_source == "canonical_surface":
            reasons.append("canonical_surface_code_disagreement")
        elif target_source == "trusted_fndds":
            reasons.append("trusted_canonical_fndds_code_disagreement")
    if current_fact:
        reject = compatibility_reason(product, current_fact)
        if reject:
            reasons.append("product_esha_no_identity_overlap")
    if numeric_score(row.get("score_num") or row.get("score")) < 8.0 and current_code:
        reasons.append("low_score")
    vcluster_code = norm_code(vcluster_row.get("best_esha_code", ""))
    if vcluster_code and current_code and vcluster_code != current_code:
        reasons.append("vcluster_code_disagreement")

    verdict = "review" if (set(reasons) & (HARD_QUARANTINE_REASONS | ANCHOR_DISAGREEMENT_REASONS)) else ("watch" if reasons else "ok")
    return {
        "verdict": verdict,
        "review_reasons": "|".join(dict.fromkeys(reasons)),
        "fixy_match_source": "description_bridge",
        "fixy_bridge_support_count": str(label.support_count),
        "fixy_bridge_source_fdc_ids": label.source_fdc_ids,
        "fixy_fdc_id": row.get("fdc_id", ""),
        "fixy_fndds_code": label.fixy_fndds_code,
        "fixy_fndds_description": label.fixy_fndds_description,
        "fixy_product_description": row.get("product_description", ""),
        "fixy_category": row.get("branded_food_category", ""),
        "vm_gtin_upc": row.get("gtin_upc", ""),
        "vm_product_description": row.get("product_description", ""),
        "vm_category": row.get("branded_food_category", ""),
        "vm_brand_owner": row.get("brand_owner", ""),
        "vm_brand_name": row.get("brand_name", ""),
        "vm_esha_code": current_code,
        "vm_esha_description": current_description,
        "vm_esha_head": row.get("best_esha_head", ""),
        "vm_esha_family": row.get("best_esha_family", ""),
        "vm_score": row.get("score_num") or row.get("score", ""),
        "vm_assignment_source": row.get("assignment_source", ""),
        "canonical_surface_esha_codes": label.canonical_surface_esha_codes,
        "trusted_canonical_fndds_esha_codes": label.trusted_canonical_fndds_esha_codes,
        "graph_cluster_flags": "",
        "graph_cluster_reject_reason": "",
        "vcluster_code": vcluster_code,
        "vcluster_description": vcluster_row.get("best_esha_description", ""),
        "vcluster_agreement_status": "description_bridge_vcluster_disagreement" if vcluster_code and current_code and vcluster_code != current_code else "",
    }


def apply_assignment(row: dict[str, str], target: EshaCode, source: str) -> None:
    row["best_esha_code"] = target.code
    row["best_esha_description"] = target.description
    row["best_esha_head"] = target.head
    row["best_esha_family"] = target.family
    row["score"] = "42.0000"
    row["score_num"] = "42.0000"
    row["n_candidates"] = "1"
    row["assignment_source"] = source


def blank_assignment(row: dict[str, str]) -> None:
    row["best_esha_code"] = ""
    row["best_esha_description"] = ""
    row["best_esha_head"] = ""
    row["best_esha_family"] = ""
    row["score"] = "0"
    row["score_num"] = "0"
    row["n_candidates"] = "0"
    row["assignment_source"] = "fixy_done_identity_quarantine"


def add_cleanup_flag(
    row: dict[str, str],
    action: str,
    reason: str,
    proposal: dict[str, str] | None = None,
) -> None:
    row["fixy_cleanup_action"] = action
    row["fixy_cleanup_reason"] = reason
    row["fixy_cleanup_target_source"] = (proposal or {}).get("target_source", "")
    row["fixy_cleanup_match_source"] = (proposal or {}).get("fixy_match_source", "")
    row["fixy_cleanup_old_code"] = (proposal or {}).get("old_best_esha_code", "")
    row["fixy_cleanup_old_description"] = (proposal or {}).get("old_best_esha_description", "")
    row["fixy_cleanup_suggested_code"] = (proposal or {}).get("new_best_esha_code", "")
    row["fixy_cleanup_suggested_description"] = (proposal or {}).get("new_best_esha_description", "")
    row["fixy_cleanup_review_reasons"] = (proposal or {}).get("review_reasons", "")


def build(args: argparse.Namespace) -> dict[str, object]:
    esha = load_esha_catalog(args.esha_csv, args.esha_spine)
    crosscheck_rows = read_csv(args.crosscheck)
    crosscheck_by_fdc = {
        norm_fdc(row.get("fixy_fdc_id", "")): row
        for row in crosscheck_rows
        if norm_fdc(row.get("fixy_fdc_id", "")) and row.get("verdict") != "out_of_scope"
    }
    bridge_labels: dict[str, BridgeLabel] = {}
    bridge_reject_counts: Counter[str] = Counter()
    vcluster_by_fdc: dict[str, dict[str, str]] = {}
    if args.use_description_bridge:
        bridge_labels, bridge_reject_counts = build_description_bridge_labels(crosscheck_rows)
        vcluster_by_fdc = load_vcluster_by_fdc(args.vcluster_map)
    rows = read_csv(args.input_map)
    assigned_before = sum(1 for row in rows if norm_code(row.get("best_esha_code", "")))
    out_rows: list[dict[str, str]] = []
    diff_rows: list[dict[str, str]] = []
    remap_rows: list[dict[str, str]] = []
    quarantine_rows: list[dict[str, str]] = []
    bridge_report_rows: list[dict[str, str]] = []
    action_counts: Counter[str] = Counter()
    reject_counts: Counter[str] = Counter()
    bridge_counts: Counter[str] = Counter()

    for row in rows:
        fdc_id = norm_fdc(row.get("fdc_id", ""))
        original = dict(row)
        check = crosscheck_by_fdc.get(fdc_id)
        if check:
            bridge_counts["direct_fdc_match"] += 1
        elif args.use_description_bridge:
            key = norm_key(row.get("product_description", ""))
            label = bridge_labels.get(key)
            if label:
                check = bridge_check_for_row(row, label, vcluster_by_fdc.get(fdc_id, {}))
                bridge_counts["description_bridge_match"] += 1
                bridge_report_rows.append(
                    {
                        "bridge_status": "matched",
                        "vm_fdc_id": fdc_id,
                        "vm_gtin_upc": row.get("gtin_upc", ""),
                        "vm_product_description": row.get("product_description", ""),
                        "vm_category": row.get("branded_food_category", ""),
                        "vm_esha_code": row.get("best_esha_code", ""),
                        "vm_esha_description": row.get("best_esha_description", ""),
                        "fixy_fndds_code": label.fixy_fndds_code,
                        "fixy_fndds_description": label.fixy_fndds_description,
                        "target_code": target_from_crosscheck(check)[0],
                        "target_source": target_from_crosscheck(check)[1],
                        "support_count": str(label.support_count),
                        "source_fdc_ids": label.source_fdc_ids,
                        "review_reasons": check.get("review_reasons", ""),
                    }
                )
            else:
                bridge_counts["no_description_bridge_match"] += 1
        if not check:
            out_rows.append(row)
            action_counts["kept_no_fixy_overlap"] += 1
            continue

        target_code, target_source = target_from_crosscheck(check)
        target = esha.get(target_code) if target_code else None
        current_code = norm_code(row.get("best_esha_code", ""))
        action = "kept"
        proposal: dict[str, str] | None = None

        if target and target.code != current_code:
            ok, reason = eligible_for_remap(check, target, target_source)
            if ok:
                source = "fixy_done_canonical_remap" if current_code else "fixy_done_canonical_recovery"
                if target_source == "trusted_fndds":
                    source = "fixy_done_fndds_remap" if current_code else "fixy_done_fndds_recovery"
                apply_assignment(row, target, source)
                action = source
                proposal = proposal_from(check, action, reason, target, target_source)
                if args.quarantine_mode == "flag":
                    add_cleanup_flag(row, action, reason, proposal)
                remap_rows.append(proposal)
            else:
                reject_counts[reason] += 1

        if action == "kept":
            q_ok, q_reason = eligible_for_quarantine(check)
            if q_ok:
                action = "fixy_done_identity_quarantine"
                proposal = proposal_from(check, action, q_reason)
                if args.quarantine_mode == "blank":
                    blank_assignment(row)
                else:
                    action = "fixy_done_identity_quarantine_flag"
                    proposal["action"] = action
                    add_cleanup_flag(row, action, q_reason, proposal)
                quarantine_rows.append(proposal)
            else:
                reject_counts[q_reason] += 1

        action_counts[action] += 1
        if original != row:
            diff = dict(proposal or {})
            diff.update(
                {
                    "old_assignment_source": original.get("assignment_source", ""),
                    "new_assignment_source": row.get("assignment_source", ""),
                    "new_best_esha_code": row.get("best_esha_code", ""),
                    "new_best_esha_description": row.get("best_esha_description", ""),
                    "new_best_esha_head": row.get("best_esha_head", ""),
                    "new_best_esha_family": row.get("best_esha_family", ""),
                }
            )
            diff_rows.append(diff)
        out_rows.append(row)

    fieldnames = list(rows[0].keys()) if rows else BASE_COLUMNS
    if args.quarantine_mode == "flag":
        fieldnames = fieldnames + [col for col in FLAG_COLUMNS if col not in fieldnames]
    proposal_fields = [
        "action",
        "action_reason",
        "target_source",
        "fixy_match_source",
        "fixy_bridge_support_count",
        "fixy_bridge_source_fdc_ids",
        "fixy_fdc_id",
        "gtin_upc",
        "product_description",
        "branded_food_category",
        "brand_owner",
        "brand_name",
        "fixy_fndds_code",
        "fixy_fndds_description",
        "old_best_esha_code",
        "old_best_esha_description",
        "old_best_esha_head",
        "old_best_esha_family",
        "old_assignment_source",
        "old_score",
        "new_best_esha_code",
        "new_best_esha_description",
        "new_best_esha_head",
        "new_best_esha_family",
        "new_assignment_source",
        "review_reasons",
        "canonical_surface_esha_codes",
        "trusted_canonical_fndds_esha_codes",
        "graph_cluster_flags",
        "graph_cluster_reject_reason",
        "vcluster_code",
        "vcluster_description",
        "vcluster_agreement_status",
    ]
    write_csv(args.output_map, out_rows, fieldnames)
    write_csv(args.diff, diff_rows, proposal_fields)
    write_csv(args.remaps, remap_rows, proposal_fields)
    write_csv(args.quarantine, quarantine_rows, proposal_fields)
    if args.use_description_bridge:
        write_csv(
            args.bridge_report,
            bridge_report_rows,
            [
                "bridge_status",
                "vm_fdc_id",
                "vm_gtin_upc",
                "vm_product_description",
                "vm_category",
                "vm_esha_code",
                "vm_esha_description",
                "fixy_fndds_code",
                "fixy_fndds_description",
                "target_code",
                "target_source",
                "support_count",
                "source_fdc_ids",
                "review_reasons",
            ],
        )

    assigned_after = sum(1 for row in out_rows if norm_code(row.get("best_esha_code", "")))
    summary = {
        "input_map": str(args.input_map),
        "crosscheck": str(args.crosscheck),
        "output_map": str(args.output_map),
        "diff": str(args.diff),
        "rows": len(rows),
        "fixy_overlap_rows": len(crosscheck_by_fdc),
        "description_bridge_enabled": bool(args.use_description_bridge),
        "description_bridge_label_count": len(bridge_labels),
        "description_bridge_counts": dict(bridge_counts.most_common()),
        "description_bridge_reject_counts": dict(bridge_reject_counts.most_common(30)),
        "description_bridge_report": str(args.bridge_report) if args.use_description_bridge else "",
        "quarantine_mode": args.quarantine_mode,
        "assigned_before": assigned_before,
        "assigned_after": assigned_after,
        "coverage_delta": assigned_after - assigned_before,
        "changed_rows": len(diff_rows),
        "remap_or_recovery_rows": len(remap_rows),
        "quarantine_rows": len(quarantine_rows),
        "action_counts": dict(action_counts.most_common()),
        "reject_counts": dict(reject_counts.most_common(50)),
        "top_remap_targets": dict(Counter(row["new_best_esha_description"] for row in remap_rows).most_common(30)),
        "top_quarantine_old_targets": dict(Counter(row["old_best_esha_description"] for row in quarantine_rows).most_common(30)),
        "top_quarantine_reasons": dict(Counter(row["action_reason"] for row in quarantine_rows).most_common(30)),
    }
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply conservative Fixy-labeled cleanup to a product->ESHA map.")
    parser.add_argument("--input-map", type=Path, default=DEFAULT_INPUT_MAP)
    parser.add_argument("--crosscheck", type=Path, default=DEFAULT_CROSSCHECK)
    parser.add_argument("--esha-csv", type=Path, default=DEFAULT_ESHA_CSV)
    parser.add_argument("--esha-spine", type=Path, default=DEFAULT_ESHA_SPINE)
    parser.add_argument("--vcluster-map", type=Path, default=DEFAULT_VCLUSTER_MAP)
    parser.add_argument("--use-description-bridge", action="store_true")
    parser.add_argument(
        "--quarantine-mode",
        choices=("blank", "flag"),
        default="blank",
        help=(
            "blank removes assignments that Fixy evidence rejects; flag keeps coverage intact "
            "and writes fixy_cleanup_* review columns instead"
        ),
    )
    parser.add_argument("--output-map", type=Path, default=DEFAULT_OUTPUT_MAP)
    parser.add_argument("--diff", type=Path, default=DEFAULT_DIFF)
    parser.add_argument("--remaps", type=Path, default=DEFAULT_REMAPS)
    parser.add_argument("--quarantine", type=Path, default=DEFAULT_QUARANTINE)
    parser.add_argument("--bridge-report", type=Path, default=DEFAULT_BRIDGE_REPORT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser.parse_args()


def main() -> None:
    summary = build(parse_args())
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
