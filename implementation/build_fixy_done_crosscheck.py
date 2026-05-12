from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import build_product_to_best_esha_full_map as full_map
import match_esha_to_products as matcher


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"

DEFAULT_FIXY_DIR = ROOT / "fixy_done"
DEFAULT_VM_MAP = OUT_DIR / "product_to_best_esha_full_map.vM.csv"
DEFAULT_VCLUSTER_MAP = OUT_DIR / "product_to_best_esha_full_map.vCluster.csv"
DEFAULT_PRODUCT_CLUSTERS = OUT_DIR / "product_evidence_cluster_members_v2.csv"
DEFAULT_INGREDIENT_CLUSTERS = OUT_DIR / "ingredient_only_cluster_members.csv"
DEFAULT_CLUSTER_ASSIGNMENTS = OUT_DIR / "cluster_to_esha_assignments.csv"
DEFAULT_VCLUSTER_AUDIT = OUT_DIR / "vm_vcluster_agreement_audit.csv"
DEFAULT_STRUCTURAL_DIFF = OUT_DIR / "vm_cluster_structural_quarantine_diff.csv"
DEFAULT_CANONICAL = OUT_DIR / "canonical_surface_normalized_with_product_proxies_CLEANED.csv"
DEFAULT_ESHA_SPINE = OUT_DIR / "esha_spine.csv"
DEFAULT_SINGLE_CATEGORY_QUEUE = OUT_DIR / "esha_single_category_fix_queue.csv"
DEFAULT_OUTPUT_DIR = OUT_DIR / "fixy_done_crosscheck"

GRAPH_CLUSTER_REPORTS = (
    (ROOT / "graph" / "review" / "evidence_cluster_conflicts_from_graph.csv", "graph_cluster_conflict"),
    (ROOT / "graph" / "review" / "evidence_cluster_structural_rejects_from_graph.csv", "graph_structural_reject"),
)

GRAPH_FDC_REPORTS = (
    (ROOT / "graph" / "quarantine" / "needs_remap.csv", "graph_needs_remap"),
    (ROOT / "graph" / "quarantine" / "needs_remap_l.csv", "graph_needs_remap_l"),
    (ROOT / "graph" / "quarantine" / "low_score_candidates.csv", "graph_low_score_candidate"),
)

GRAPH_GTIN_REPORTS = (
    (ROOT / "graph" / "review" / "review_queue.csv", "graph_review_queue"),
    (ROOT / "graph" / "review" / "low_quality.csv", "graph_low_quality"),
    (ROOT / "graph" / "review" / "regressions.csv", "graph_regression"),
    (ROOT / "graph" / "review" / "unassigned.csv", "graph_unassigned"),
)

PRODUCT_FIELDNAMES = [
    "verdict",
    "review_reasons",
    "fixy_file",
    "fixy_fndds_code",
    "fixy_fndds_description",
    "fixy_fdc_id",
    "fixy_product_description",
    "fixy_category",
    "vm_gtin_upc",
    "vm_product_description",
    "vm_category",
    "vm_brand_owner",
    "vm_brand_name",
    "vm_esha_code",
    "vm_esha_description",
    "vm_esha_head",
    "vm_esha_family",
    "vm_score",
    "vm_assignment_source",
    "canonical_surface_esha_codes",
    "trusted_canonical_fndds_esha_codes",
    "canonical_anchor_status",
    "fndds_identity_terms",
    "product_identity_terms",
    "esha_identity_terms",
    "fndds_esha_identity_overlap",
    "product_esha_identity_overlap",
    "product_cluster_id",
    "product_cluster_primary_food",
    "product_cluster_title_identity_terms",
    "product_cluster_ingredient_core_terms",
    "cluster_assignment_status",
    "cluster_assigned_esha_code",
    "cluster_assigned_esha_description",
    "cluster_assignment_reason",
    "ingredient_cluster_id",
    "ingredient_signature",
    "graph_cluster_flags",
    "graph_cluster_reject_reason",
    "graph_product_flags",
    "vcluster_code",
    "vcluster_description",
    "vcluster_status",
    "vcluster_guard_reason",
    "vcluster_agreement_status",
    "vcluster_audit_blocker",
    "structural_quarantine_reason",
]

CODE_SUMMARY_FIELDNAMES = [
    "fixy_fndds_code",
    "fixy_fndds_description",
    "total_rows",
    "mapped_rows",
    "map_coverage_pct",
    "assigned_rows",
    "assigned_pct",
    "out_of_scope_rows",
    "ok_rows",
    "watch_rows",
    "review_rows",
    "review_pct",
    "top_vm_esha_codes",
    "top_vm_esha_heads",
    "top_assignment_sources",
    "top_review_reasons",
    "canonical_surface_esha_codes",
    "trusted_canonical_fndds_esha_codes",
    "graph_structural_reject_rows",
    "graph_cluster_conflict_rows",
    "vcluster_disagreement_rows",
    "sample_review_products",
]

HARD_REVIEW_REASONS = {
    "unassigned_vM",
    "canonical_surface_code_disagreement",
    "trusted_canonical_fndds_code_disagreement",
    "product_esha_no_identity_overlap",
    "graph_structural_reject",
    "vcluster_code_disagreement",
    "multi_category_esha_code_used_by_fallback",
}

WATCH_REVIEW_REASONS = {
    "broad_fallback_source",
    "fndds_esha_no_identity_overlap",
    "graph_cluster_conflict",
    "low_score",
    "vcluster_unassigned",
}

FALLBACK_SOURCES = {
    "fallback_category_family",
    "fallback_category_family_no_match",
    "fallback_family",
    "fallback_family_no_match",
}


@dataclass
class CanonicalAnchors:
    by_surface: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    by_trusted_fndds_code: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))


@dataclass
class CodeSummary:
    description_counter: Counter[str] = field(default_factory=Counter)
    total_rows: int = 0
    mapped_rows: int = 0
    assigned_rows: int = 0
    out_of_scope_rows: int = 0
    ok_rows: int = 0
    watch_rows: int = 0
    review_rows: int = 0
    vm_codes: Counter[str] = field(default_factory=Counter)
    vm_heads: Counter[str] = field(default_factory=Counter)
    sources: Counter[str] = field(default_factory=Counter)
    reasons: Counter[str] = field(default_factory=Counter)
    canonical_surface_codes: set[str] = field(default_factory=set)
    trusted_fndds_codes: set[str] = field(default_factory=set)
    graph_structural_reject_rows: int = 0
    graph_cluster_conflict_rows: int = 0
    vcluster_disagreement_rows: int = 0
    samples: list[str] = field(default_factory=list)


def normalize_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("&", " and ").replace("|", " ")
    return " ".join(re.sub(r"[^a-z0-9%]+", " ", text).split())


def normalize_code(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    if re.fullmatch(r"0+\d+", text):
        text = text.lstrip("0") or "0"
    return text


def normalize_fdc_id(value: str) -> str:
    return normalize_code(value)


def normalize_gtin(value: str) -> str:
    digits = re.sub(r"\D+", "", str(value or ""))
    return digits or str(value or "").strip()


def read_csv(path: Path) -> Iterable[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        yield from csv.DictReader(handle)


def sort_codes(codes: Iterable[str]) -> list[str]:
    return sorted({code for code in codes if code}, key=lambda code: (not code.isdigit(), int(code) if code.isdigit() else code))


def join_values(values: Iterable[str], limit: int = 12) -> str:
    clean = [value for value in values if value]
    if not clean:
        return ""
    clean = clean[:limit]
    return " | ".join(clean)


def counter_summary(counter: Counter[str], limit: int = 8) -> str:
    return " | ".join(f"{value}:{count}" for value, count in counter.most_common(limit) if value)


def terms_for(*texts: str) -> set[str]:
    tokens: list[str] = []
    for text in texts:
        tokens.extend(tok for tok in matcher.tokens_for(text or "") if tok and tok not in matcher.STOPWORDS)
    expanded = full_map.expand_compound_tokens(tokens)
    meaningful = {
        tok
        for tok in expanded
        if tok
        and tok not in matcher.STOPWORDS
        and tok not in full_map.WEAK_FALLBACK_TOKENS
        and tok not in full_map.GENERIC_FAMILY_TOKENS
    }
    return set(meaningful)


def term_string(terms: Iterable[str], limit: int = 16) -> str:
    return " ".join(sorted(terms)[:limit])


def is_trusted_fndds_anchor(row: dict[str, str]) -> bool:
    match_type = (row.get("fndds_match_type") or "").strip().lower()
    if not match_type:
        return False
    if "proxy_backfill" in match_type or "bridge_gap" in match_type:
        return False
    trusted_markers = ("terminal_proxy", "reference_match", "fndds_match", "exact", "reviewed")
    return any(marker in match_type for marker in trusted_markers)


def load_canonical_anchors(path: Path) -> CanonicalAnchors:
    anchors = CanonicalAnchors()
    if not path.exists():
        return anchors
    for row in read_csv(path):
        esha_code = normalize_code(row.get("esha_code", ""))
        if not esha_code:
            continue
        for field in ("canonical_surface", "canonical_normalized", "canonical_shopping_item"):
            key = normalize_key(row.get(field, ""))
            if key:
                anchors.by_surface[key].add(esha_code)
        fndds_code = normalize_code(row.get("fndds_code", ""))
        if fndds_code and is_trusted_fndds_anchor(row):
            anchors.by_trusted_fndds_code[fndds_code].add(esha_code)
    return anchors


def load_index(path: Path, key_field: str, fields: list[str], *, key_normalizer=normalize_fdc_id) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    if not path.exists():
        return out
    for row in read_csv(path):
        key = key_normalizer(row.get(key_field, ""))
        if not key:
            continue
        out.setdefault(key, {field: row.get(field, "") for field in fields})
    return out


def load_code_risk_set(spine_path: Path, queue_path: Path) -> set[str]:
    risky: set[str] = set()
    if spine_path.exists():
        for row in read_csv(spine_path):
            if (row.get("needs_fix") or "").strip() in {"1", "true", "TRUE", "yes"}:
                risky.add(normalize_code(row.get("esha_code", "")))
    if queue_path.exists():
        for row in read_csv(queue_path):
            if (row.get("needs_fix") or "").strip() in {"1", "true", "TRUE", "yes"}:
                risky.add(normalize_code(row.get("esha_code", "")))
    return {code for code in risky if code}


def append_flag(flags: dict[str, list[str]], key: str, value: str) -> None:
    if key and value and value not in flags[key]:
        flags[key].append(value)


def load_graph_cluster_flags() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = defaultdict(lambda: {"flags": "", "reject_reason": ""})
    for path, tag in GRAPH_CLUSTER_REPORTS:
        if not path.exists():
            continue
        for row in read_csv(path):
            cluster_id = (row.get("ingredient_cluster_id") or "").strip()
            if not cluster_id:
                continue
            flags = [flag for flag in out[cluster_id]["flags"].split("|") if flag]
            if tag not in flags:
                flags.append(tag)
            audit_flags = (row.get("audit_flags") or "").strip()
            if audit_flags:
                flags.extend(flag for flag in audit_flags.split("|") if flag and flag not in flags)
            out[cluster_id]["flags"] = "|".join(flags)
            reject_reason = (row.get("current_reject_reason") or row.get("current_reject_reason_from_edge") or "").strip()
            if reject_reason and not out[cluster_id]["reject_reason"]:
                out[cluster_id]["reject_reason"] = reject_reason
    return dict(out)


def load_product_flags() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    fdc_flags: dict[str, list[str]] = defaultdict(list)
    gtin_flags: dict[str, list[str]] = defaultdict(list)
    for path, tag in GRAPH_FDC_REPORTS:
        if not path.exists():
            continue
        for row in read_csv(path):
            key = normalize_fdc_id(row.get("fdc_id", ""))
            reason = (row.get("quarantine_reason") or row.get("status") or "").strip()
            append_flag(fdc_flags, key, tag if not reason else f"{tag}:{reason}")
    for path, tag in GRAPH_GTIN_REPORTS:
        if not path.exists():
            continue
        for row in read_csv(path):
            key = normalize_gtin(row.get("gtin_upc", ""))
            reason = (row.get("quality_score") or row.get("delta") or row.get("original_assignment_source") or "").strip()
            append_flag(gtin_flags, key, tag if not reason else f"{tag}:{reason}")
    return dict(fdc_flags), dict(gtin_flags)


def fixy_files(fixy_dir: Path) -> list[Path]:
    return sorted(path for path in fixy_dir.glob("*.csv") if path.is_file())


def canonical_anchor_status(
    vm_code: str,
    surface_codes: set[str],
    trusted_fndds_codes: set[str],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if surface_codes:
        if vm_code and vm_code in surface_codes:
            return "canonical_surface_match", reasons
        if vm_code:
            reasons.append("canonical_surface_code_disagreement")
            return "canonical_surface_disagreement", reasons
        return "canonical_surface_unassigned", reasons
    if trusted_fndds_codes:
        if vm_code and vm_code in trusted_fndds_codes:
            return "trusted_fndds_code_match", reasons
        if vm_code:
            reasons.append("trusted_canonical_fndds_code_disagreement")
            return "trusted_fndds_code_disagreement", reasons
        return "trusted_fndds_code_unassigned", reasons
    return "no_canonical_anchor", reasons


def decide_verdict(reasons: list[str]) -> str:
    reason_set = set(reasons)
    if "missing_vM_row" in reason_set:
        return "out_of_scope"
    if reason_set & HARD_REVIEW_REASONS:
        return "review"
    if reason_set & WATCH_REVIEW_REASONS or reasons:
        return "watch"
    return "ok"


def build_row(
    fixy_file: Path,
    fixy_row: dict[str, str],
    vm_by_fdc: dict[str, dict[str, str]],
    vcluster_by_fdc: dict[str, dict[str, str]],
    product_cluster_by_fdc: dict[str, dict[str, str]],
    ingredient_cluster_by_fdc: dict[str, dict[str, str]],
    cluster_assignment_by_id: dict[str, dict[str, str]],
    vcluster_audit_by_fdc: dict[str, dict[str, str]],
    structural_diff_by_fdc: dict[str, dict[str, str]],
    graph_cluster_flags: dict[str, dict[str, str]],
    graph_fdc_flags: dict[str, list[str]],
    graph_gtin_flags: dict[str, list[str]],
    canonical: CanonicalAnchors,
    risky_esha_codes: set[str],
) -> dict[str, str]:
    fdc_id = normalize_fdc_id(fixy_row.get("fdc_id", ""))
    fixy_code = normalize_code(fixy_row.get("fndds", "")) or normalize_code(fixy_file.stem)
    fixy_description = (fixy_row.get("fndds_description") or fixy_row.get("fndds_descripton") or "").strip()
    fixy_product_description = (fixy_row.get("description") or "").strip()
    fixy_category = (fixy_row.get("branded_food_category") or "").strip()

    vm = vm_by_fdc.get(fdc_id, {})
    vm_code = normalize_code(vm.get("best_esha_code", ""))
    vm_gtin = vm.get("gtin_upc", "")
    vm_score = vm.get("score_num") or vm.get("score") or ""
    vm_source = vm.get("assignment_source", "")

    vcluster = vcluster_by_fdc.get(fdc_id, {})
    product_cluster = product_cluster_by_fdc.get(fdc_id, {})
    product_cluster_id = product_cluster.get("cluster_id", "") or vcluster.get("cluster_id", "")
    cluster_assignment = cluster_assignment_by_id.get(product_cluster_id, {})
    ingredient_cluster = ingredient_cluster_by_fdc.get(fdc_id, {})
    ingredient_cluster_id = ingredient_cluster.get("ingredient_cluster_id", "")
    vcluster_audit = vcluster_audit_by_fdc.get(fdc_id, {})
    structural_diff = structural_diff_by_fdc.get(fdc_id, {})

    surface_key = normalize_key(fixy_description)
    canonical_surface_codes = canonical.by_surface.get(surface_key, set())
    trusted_fndds_codes = canonical.by_trusted_fndds_code.get(fixy_code, set())

    reasons: list[str] = []
    if not vm:
        reasons.append("missing_vM_row")
    elif not vm_code:
        reasons.append("unassigned_vM")

    anchor_status, anchor_reasons = canonical_anchor_status(vm_code, canonical_surface_codes, trusted_fndds_codes)
    reasons.extend(anchor_reasons)

    product_terms = terms_for(fixy_product_description, fixy_category)
    fndds_terms = terms_for(fixy_description)
    esha_terms = terms_for(vm.get("best_esha_description", ""), vm.get("best_esha_head", ""))
    product_esha_overlap = product_terms & esha_terms
    fndds_esha_overlap = fndds_terms & esha_terms

    if product_terms and esha_terms and not product_esha_overlap:
        reasons.append("product_esha_no_identity_overlap")
    if fndds_terms and esha_terms and not fndds_esha_overlap:
        reasons.append("fndds_esha_no_identity_overlap")

    score_float: float | None
    try:
        score_float = float(vm_score) if vm_score != "" else None
    except ValueError:
        score_float = None
    if score_float is not None and score_float < 8.0:
        reasons.append("low_score")
    if vm_source in FALLBACK_SOURCES:
        reasons.append("broad_fallback_source")
    if vm_code in risky_esha_codes and vm_source in FALLBACK_SOURCES:
        reasons.append("multi_category_esha_code_used_by_fallback")

    cluster_graph = graph_cluster_flags.get(ingredient_cluster_id, {})
    graph_flags = cluster_graph.get("flags", "")
    graph_reject = cluster_graph.get("reject_reason", "")
    if "graph_structural_reject" in graph_flags or graph_reject:
        reasons.append("graph_structural_reject")
    elif "graph_cluster_conflict" in graph_flags:
        reasons.append("graph_cluster_conflict")

    product_flags = list(graph_fdc_flags.get(fdc_id, []))
    gtin_key = normalize_gtin(vm_gtin)
    product_flags.extend(flag for flag in graph_gtin_flags.get(gtin_key, []) if flag not in product_flags)

    structural_reason = structural_diff.get("current_reject_reason") or structural_diff.get("quarantine_reason") or ""
    if structural_reason:
        reasons.append("graph_structural_reject")

    agreement_status = vcluster_audit.get("agreement_status", "")
    if agreement_status == "different_assigned_code":
        reasons.append("vcluster_code_disagreement")
    elif agreement_status == "vm_only_assigned":
        reasons.append("vcluster_unassigned")

    verdict = decide_verdict(reasons)

    return {
        "verdict": verdict,
        "review_reasons": "|".join(dict.fromkeys(reasons)),
        "fixy_file": str(fixy_file.relative_to(ROOT)),
        "fixy_fndds_code": fixy_code,
        "fixy_fndds_description": fixy_description,
        "fixy_fdc_id": fdc_id,
        "fixy_product_description": fixy_product_description,
        "fixy_category": fixy_category,
        "vm_gtin_upc": vm_gtin,
        "vm_product_description": vm.get("product_description", ""),
        "vm_category": vm.get("branded_food_category", ""),
        "vm_brand_owner": vm.get("brand_owner", ""),
        "vm_brand_name": vm.get("brand_name", ""),
        "vm_esha_code": vm_code,
        "vm_esha_description": vm.get("best_esha_description", ""),
        "vm_esha_head": vm.get("best_esha_head", ""),
        "vm_esha_family": vm.get("best_esha_family", ""),
        "vm_score": vm_score,
        "vm_assignment_source": vm_source,
        "canonical_surface_esha_codes": join_values(sort_codes(canonical_surface_codes)),
        "trusted_canonical_fndds_esha_codes": join_values(sort_codes(trusted_fndds_codes)),
        "canonical_anchor_status": anchor_status,
        "fndds_identity_terms": term_string(fndds_terms),
        "product_identity_terms": term_string(product_terms),
        "esha_identity_terms": term_string(esha_terms),
        "fndds_esha_identity_overlap": term_string(fndds_esha_overlap),
        "product_esha_identity_overlap": term_string(product_esha_overlap),
        "product_cluster_id": product_cluster_id,
        "product_cluster_primary_food": product_cluster.get("primary_food", ""),
        "product_cluster_title_identity_terms": product_cluster.get("title_identity_terms", ""),
        "product_cluster_ingredient_core_terms": product_cluster.get("ingredient_core_terms", ""),
        "cluster_assignment_status": cluster_assignment.get("assignment_status", ""),
        "cluster_assigned_esha_code": normalize_code(cluster_assignment.get("assigned_esha_code", "")),
        "cluster_assigned_esha_description": cluster_assignment.get("assigned_esha_description", ""),
        "cluster_assignment_reason": cluster_assignment.get("assignment_reason", ""),
        "ingredient_cluster_id": ingredient_cluster_id,
        "ingredient_signature": ingredient_cluster.get("ingredient_signature", ""),
        "graph_cluster_flags": graph_flags,
        "graph_cluster_reject_reason": graph_reject,
        "graph_product_flags": "|".join(product_flags),
        "vcluster_code": normalize_code(vcluster.get("best_esha_code", "")),
        "vcluster_description": vcluster.get("best_esha_description", ""),
        "vcluster_status": vcluster.get("cluster_assignment_status", ""),
        "vcluster_guard_reason": vcluster.get("projection_guard_reason", ""),
        "vcluster_agreement_status": agreement_status,
        "vcluster_audit_blocker": vcluster_audit.get("done_blocker", ""),
        "structural_quarantine_reason": structural_reason,
    }


def update_summary(summary: CodeSummary, row: dict[str, str]) -> None:
    summary.total_rows += 1
    summary.description_counter.update([row["fixy_fndds_description"]])
    if row["vm_gtin_upc"] or row["vm_product_description"]:
        summary.mapped_rows += 1
    if row["vm_esha_code"]:
        summary.assigned_rows += 1
        summary.vm_codes.update([f'{row["vm_esha_code"]} {row["vm_esha_description"]}'.strip()])
    if row["vm_esha_head"]:
        summary.vm_heads.update([row["vm_esha_head"]])
    if row["vm_assignment_source"]:
        summary.sources.update([row["vm_assignment_source"]])
    summary.canonical_surface_codes.update(row["canonical_surface_esha_codes"].split(" | ") if row["canonical_surface_esha_codes"] else [])
    summary.trusted_fndds_codes.update(row["trusted_canonical_fndds_esha_codes"].split(" | ") if row["trusted_canonical_fndds_esha_codes"] else [])
    verdict = row["verdict"]
    if verdict == "out_of_scope":
        summary.out_of_scope_rows += 1
    elif verdict == "ok":
        summary.ok_rows += 1
    elif verdict == "watch":
        summary.watch_rows += 1
    else:
        summary.review_rows += 1
    for reason in row["review_reasons"].split("|"):
        if reason and verdict != "out_of_scope":
            summary.reasons.update([reason])
    if "graph_structural_reject" in row["review_reasons"]:
        summary.graph_structural_reject_rows += 1
    if "graph_cluster_conflict" in row["review_reasons"]:
        summary.graph_cluster_conflict_rows += 1
    if "vcluster_code_disagreement" in row["review_reasons"]:
        summary.vcluster_disagreement_rows += 1
    if verdict == "review" and len(summary.samples) < 5:
        summary.samples.append(f'{row["fixy_fdc_id"]}:{row["fixy_product_description"]} -> {row["vm_esha_code"]} {row["vm_esha_description"]}'.strip())


def pct(part: int, whole: int) -> str:
    if not whole:
        return "0.0000"
    return f"{(part / whole) * 100:.4f}"


def write_code_summaries(path: Path, review_path: Path, summaries: dict[str, CodeSummary]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle, review_path.open("w", newline="", encoding="utf-8") as review_handle:
        writer = csv.DictWriter(handle, fieldnames=CODE_SUMMARY_FIELDNAMES)
        review_writer = csv.DictWriter(review_handle, fieldnames=CODE_SUMMARY_FIELDNAMES)
        writer.writeheader()
        review_writer.writeheader()
        for code, summary in sorted(summaries.items(), key=lambda item: (-item[1].review_rows, item[0])):
            row = {
                "fixy_fndds_code": code,
                "fixy_fndds_description": summary.description_counter.most_common(1)[0][0] if summary.description_counter else "",
                "total_rows": summary.total_rows,
                "mapped_rows": summary.mapped_rows,
                "map_coverage_pct": pct(summary.mapped_rows, summary.total_rows),
                "assigned_rows": summary.assigned_rows,
                "assigned_pct": pct(summary.assigned_rows, summary.total_rows),
                "out_of_scope_rows": summary.out_of_scope_rows,
                "ok_rows": summary.ok_rows,
                "watch_rows": summary.watch_rows,
                "review_rows": summary.review_rows,
                "review_pct": pct(summary.review_rows, summary.total_rows),
                "top_vm_esha_codes": counter_summary(summary.vm_codes),
                "top_vm_esha_heads": counter_summary(summary.vm_heads),
                "top_assignment_sources": counter_summary(summary.sources),
                "top_review_reasons": counter_summary(summary.reasons),
                "canonical_surface_esha_codes": join_values(sort_codes(summary.canonical_surface_codes)),
                "trusted_canonical_fndds_esha_codes": join_values(sort_codes(summary.trusted_fndds_codes)),
                "graph_structural_reject_rows": summary.graph_structural_reject_rows,
                "graph_cluster_conflict_rows": summary.graph_cluster_conflict_rows,
                "vcluster_disagreement_rows": summary.vcluster_disagreement_rows,
                "sample_review_products": " || ".join(summary.samples),
            }
            writer.writerow(row)
            if summary.review_rows or summary.watch_rows:
                review_writer.writerow(row)


def build(args: argparse.Namespace) -> dict[str, object]:
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    product_out = output_dir / "fixy_done_product_crosscheck.csv"
    review_out = output_dir / "fixy_done_review_queue.csv"
    code_summary_out = output_dir / "fixy_done_code_summary.csv"
    code_review_out = output_dir / "fixy_done_code_review_queue.csv"
    summary_out = output_dir / "fixy_done_crosscheck_summary.json"

    canonical = load_canonical_anchors(args.canonical)
    risky_esha_codes = load_code_risk_set(args.esha_spine, args.single_category_queue)

    vm_by_fdc = load_index(
        args.vm_map,
        "fdc_id",
        [
            "gtin_upc",
            "product_description",
            "branded_food_category",
            "brand_owner",
            "brand_name",
            "best_esha_code",
            "best_esha_description",
            "best_esha_head",
            "best_esha_family",
            "score",
            "score_num",
            "assignment_source",
        ],
    )
    vcluster_by_fdc = load_index(
        args.vcluster_map,
        "fdc_id",
        [
            "best_esha_code",
            "best_esha_description",
            "cluster_id",
            "cluster_assignment_status",
            "projection_guard_reason",
        ],
    )
    product_cluster_by_fdc = load_index(
        args.product_clusters,
        "fdc_id",
        [
            "cluster_id",
            "primary_food",
            "title_identity_terms",
            "ingredient_core_terms",
        ],
    )
    ingredient_cluster_by_fdc = load_index(
        args.ingredient_clusters,
        "fdc_id",
        [
            "ingredient_cluster_id",
            "ingredient_signature",
        ],
    )
    cluster_assignment_by_id = load_index(
        args.cluster_assignments,
        "cluster_id",
        [
            "assignment_status",
            "assignment_reason",
            "assigned_esha_code",
            "assigned_esha_description",
        ],
        key_normalizer=lambda value: (value or "").strip(),
    )
    vcluster_audit_by_fdc = load_index(
        args.vcluster_audit,
        "fdc_id",
        [
            "agreement_status",
            "done_blocker",
        ],
    )
    structural_diff_by_fdc = load_index(
        args.structural_diff,
        "fdc_id",
        [
            "current_reject_reason",
            "quarantine_reason",
        ],
    )
    graph_cluster_flags = load_graph_cluster_flags()
    graph_fdc_flags, graph_gtin_flags = load_product_flags()

    summaries: dict[str, CodeSummary] = defaultdict(CodeSummary)
    verdict_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    total_rows = 0
    total_files = 0

    with product_out.open("w", newline="", encoding="utf-8") as product_handle, review_out.open("w", newline="", encoding="utf-8") as review_handle:
        product_writer = csv.DictWriter(product_handle, fieldnames=PRODUCT_FIELDNAMES)
        review_writer = csv.DictWriter(review_handle, fieldnames=PRODUCT_FIELDNAMES)
        product_writer.writeheader()
        review_writer.writeheader()

        for fixy_file in fixy_files(args.fixy_dir):
            total_files += 1
            for fixy_row in read_csv(fixy_file):
                total_rows += 1
                row = build_row(
                    fixy_file,
                    fixy_row,
                    vm_by_fdc,
                    vcluster_by_fdc,
                    product_cluster_by_fdc,
                    ingredient_cluster_by_fdc,
                    cluster_assignment_by_id,
                    vcluster_audit_by_fdc,
                    structural_diff_by_fdc,
                    graph_cluster_flags,
                    graph_fdc_flags,
                    graph_gtin_flags,
                    canonical,
                    risky_esha_codes,
                )
                product_writer.writerow(row)
                if row["verdict"] in {"review", "watch"}:
                    review_writer.writerow(row)
                update_summary(summaries[row["fixy_fndds_code"]], row)
                verdict_counts.update([row["verdict"]])
                for reason in row["review_reasons"].split("|"):
                    if reason:
                        reason_counts.update([reason])

    write_code_summaries(code_summary_out, code_review_out, summaries)

    summary = {
        "inputs": {
            "fixy_dir": str(args.fixy_dir),
            "canonical": str(args.canonical),
            "vm_map": str(args.vm_map),
            "vcluster_map": str(args.vcluster_map),
            "product_clusters": str(args.product_clusters),
            "ingredient_clusters": str(args.ingredient_clusters),
            "cluster_assignments": str(args.cluster_assignments),
            "vcluster_audit": str(args.vcluster_audit),
            "structural_diff": str(args.structural_diff),
        },
        "outputs": {
            "product_crosscheck": str(product_out),
            "review_queue": str(review_out),
            "code_summary": str(code_summary_out),
            "code_review_queue": str(code_review_out),
        },
        "fixy_files": total_files,
        "fixy_rows": total_rows,
        "fixy_codes": len(summaries),
        "vm_index_rows": len(vm_by_fdc),
        "canonical_surface_anchor_count": len(canonical.by_surface),
        "trusted_canonical_fndds_anchor_count": len(canonical.by_trusted_fndds_code),
        "risky_esha_code_count": len(risky_esha_codes),
        "verdict_counts": dict(verdict_counts),
        "reason_counts": dict(reason_counts.most_common()),
    }
    with summary_out.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crosscheck fixy_done FNDDS product files against vM, canonical surfaces, clusters, and graph flags.")
    parser.add_argument("--fixy-dir", type=Path, default=DEFAULT_FIXY_DIR)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--vm-map", type=Path, default=DEFAULT_VM_MAP)
    parser.add_argument("--vcluster-map", type=Path, default=DEFAULT_VCLUSTER_MAP)
    parser.add_argument("--product-clusters", type=Path, default=DEFAULT_PRODUCT_CLUSTERS)
    parser.add_argument("--ingredient-clusters", type=Path, default=DEFAULT_INGREDIENT_CLUSTERS)
    parser.add_argument("--cluster-assignments", type=Path, default=DEFAULT_CLUSTER_ASSIGNMENTS)
    parser.add_argument("--vcluster-audit", type=Path, default=DEFAULT_VCLUSTER_AUDIT)
    parser.add_argument("--structural-diff", type=Path, default=DEFAULT_STRUCTURAL_DIFF)
    parser.add_argument("--esha-spine", type=Path, default=DEFAULT_ESHA_SPINE)
    parser.add_argument("--single-category-queue", type=Path, default=DEFAULT_SINGLE_CATEGORY_QUEUE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    summary = build(parse_args())
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
