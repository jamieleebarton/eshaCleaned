from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"
IDENTITY_DIR = OUT_DIR / "identity"

DEFAULT_PRODUCT_IDENTITY = IDENTITY_DIR / "product_identity_records.jsonl"
DEFAULT_ESHA_IDENTITY = IDENTITY_DIR / "esha_identity_records.jsonl"
DEFAULT_OUT = OUT_DIR / "product_to_best_esha_typed_identity_map.csv"
DEFAULT_SUMMARY = OUT_DIR / "product_to_best_esha_typed_identity_summary.json"

BASE_COLUMNS = [
    "entity_id",
    "product_description",
    "branded_food_category",
    "brand",
    "product_head_noun",
    "product_form",
    "product_prep_state",
    "best_esha_code",
    "best_esha_description",
    "best_esha_head_noun",
    "best_esha_form",
    "score",
    "n_candidates",
    "assignment_source",
    "reject_reason",
]


@dataclass(frozen=True)
class IdentityRecord:
    entity_type: str
    entity_id: str
    text: str
    category: str
    brand: str
    head_noun: str
    form: str
    modifiers: frozenset[str]
    prep_state: str
    sweetness: str
    fat_level: str
    foodex2_code: str
    foodex2_name: str
    confidence: float
    extractor: str
    notes: str


def norm(value: object) -> str:
    return " ".join(str(value or "").lower().replace("_", " ").split())


def load_identity_jsonl(path: Path, entity_type: str) -> list[IdentityRecord]:
    rows: list[IdentityRecord] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            raw = json.loads(line)
            if raw.get("entity_type") != entity_type:
                continue
            modifiers = raw.get("modifiers") or []
            if not isinstance(modifiers, list):
                modifiers = []
            try:
                confidence = float(raw.get("confidence") or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            rows.append(
                IdentityRecord(
                    entity_type=entity_type,
                    entity_id=str(raw.get("entity_id") or ""),
                    text=str(raw.get("text") or ""),
                    category=str(raw.get("category") or ""),
                    brand=str(raw.get("brand") or ""),
                    head_noun=norm(raw.get("head_noun")),
                    form=norm(raw.get("form")),
                    modifiers=frozenset(norm(v) for v in modifiers if norm(v)),
                    prep_state=norm(raw.get("prep_state")),
                    sweetness=norm(raw.get("sweetness")),
                    fat_level=norm(raw.get("fat_level")),
                    foodex2_code=str(raw.get("foodex2_code") or "").strip(),
                    foodex2_name=str(raw.get("foodex2_name") or ""),
                    confidence=confidence,
                    extractor=str(raw.get("extractor") or ""),
                    notes=str(raw.get("notes") or ""),
                )
            )
    return rows


def build_esha_index(records: Iterable[IdentityRecord]) -> dict[str, list[IdentityRecord]]:
    index: dict[str, list[IdentityRecord]] = defaultdict(list)
    for rec in records:
        if rec.head_noun:
            index[f"head:{rec.head_noun}"].append(rec)
        if rec.foodex2_code:
            index[f"foodex2:{rec.foodex2_code}"].append(rec)
    return dict(index)


def candidate_pool(product: IdentityRecord, index: dict[str, list[IdentityRecord]]) -> list[IdentityRecord]:
    seen: set[str] = set()
    out: list[IdentityRecord] = []
    keys = []
    if product.head_noun:
        keys.append(f"head:{product.head_noun}")
    if product.foodex2_code:
        keys.append(f"foodex2:{product.foodex2_code}")
    for key in keys:
        for cand in index.get(key, []):
            if cand.entity_id in seen:
                continue
            seen.add(cand.entity_id)
            out.append(cand)
    return out


def reject_reason(product: IdentityRecord, candidate: IdentityRecord) -> str:
    if not product.head_noun:
        return "missing_product_head_noun"
    same_head = product.head_noun and candidate.head_noun and product.head_noun == candidate.head_noun
    same_foodex = product.foodex2_code and candidate.foodex2_code and product.foodex2_code == candidate.foodex2_code
    if not (same_head or same_foodex):
        return f"head_noun_mismatch:{product.head_noun}!={candidate.head_noun}"
    if product.form and candidate.form and product.form != candidate.form:
        strict_forms = {
            "dressing",
            "salad dressing",
            "milk",
            "plant milk",
            "jelly",
            "jam",
            "cookie",
            "biscuit",
            "sausage",
            "produce",
            "dried fruit",
            "dried_fruit",
        }
        if product.form in strict_forms or candidate.form in strict_forms:
            return f"form_mismatch:{product.form}!={candidate.form}"
    if product.prep_state and candidate.prep_state:
        strict_states = {"evaporated", "condensed", "dried", "canned", "frozen"}
        if (product.prep_state in strict_states or candidate.prep_state in strict_states) and product.prep_state != candidate.prep_state:
            return f"prep_state_mismatch:{product.prep_state}!={candidate.prep_state}"
    if product.sweetness and candidate.sweetness and product.sweetness != candidate.sweetness:
        return f"sweetness_mismatch:{product.sweetness}!={candidate.sweetness}"
    if product.fat_level and candidate.fat_level and product.fat_level != candidate.fat_level:
        return f"fat_level_mismatch:{product.fat_level}!={candidate.fat_level}"
    return ""


def score_candidate(product: IdentityRecord, candidate: IdentityRecord) -> float:
    reason = reject_reason(product, candidate)
    if reason:
        return -math.inf
    score = 0.0
    if product.head_noun == candidate.head_noun:
        score += 100.0
    if product.foodex2_code and product.foodex2_code == candidate.foodex2_code:
        score += 40.0
    if product.form and product.form == candidate.form:
        score += 14.0
    if product.prep_state and product.prep_state == candidate.prep_state:
        score += 10.0
    if product.sweetness and product.sweetness == candidate.sweetness:
        score += 4.0
    if product.fat_level and product.fat_level == candidate.fat_level:
        score += 4.0
    score += 3.0 * len(product.modifiers & candidate.modifiers)
    score -= 1.0 * len(candidate.modifiers - product.modifiers)
    score += min(product.confidence, candidate.confidence) * 3.0
    return score


def choose(product: IdentityRecord, index: dict[str, list[IdentityRecord]]) -> tuple[IdentityRecord | None, float, int, str]:
    pool = candidate_pool(product, index)
    if not pool:
        return None, 0.0, 0, "no_typed_candidate_pool"
    best: tuple[float, IdentityRecord] | None = None
    rejects: dict[str, int] = defaultdict(int)
    for cand in pool:
        reason = reject_reason(product, cand)
        if reason:
            rejects[reason] += 1
            continue
        score = score_candidate(product, cand)
        if best is None or (score, cand.entity_id) > (best[0], best[1].entity_id):
            best = (score, cand)
    if best is None:
        top_reject = max(rejects.items(), key=lambda item: item[1])[0] if rejects else "all_candidates_rejected"
        return None, 0.0, len(pool), top_reject
    return best[1], best[0], len(pool), ""


def build_map(products: list[IdentityRecord], eshas: list[IdentityRecord], out_path: Path) -> dict[str, object]:
    index = build_esha_index(eshas)
    rows: list[dict[str, object]] = []
    assigned = 0
    rejects: dict[str, int] = defaultdict(int)
    for product in products:
        cand, score, n_candidates, reason = choose(product, index)
        if cand is None:
            rejects[reason] += 1
            rows.append(
                {
                    "entity_id": product.entity_id,
                    "product_description": product.text,
                    "branded_food_category": product.category,
                    "brand": product.brand,
                    "product_head_noun": product.head_noun,
                    "product_form": product.form,
                    "product_prep_state": product.prep_state,
                    "best_esha_code": "",
                    "best_esha_description": "",
                    "best_esha_head_noun": "",
                    "best_esha_form": "",
                    "score": "0",
                    "n_candidates": str(n_candidates),
                    "assignment_source": "typed_identity_no_match",
                    "reject_reason": reason,
                }
            )
            continue
        assigned += 1
        rows.append(
            {
                "entity_id": product.entity_id,
                "product_description": product.text,
                "branded_food_category": product.category,
                "brand": product.brand,
                "product_head_noun": product.head_noun,
                "product_form": product.form,
                "product_prep_state": product.prep_state,
                "best_esha_code": cand.entity_id,
                "best_esha_description": cand.text,
                "best_esha_head_noun": cand.head_noun,
                "best_esha_form": cand.form,
                "score": f"{score:.4f}",
                "n_candidates": str(n_candidates),
                "assignment_source": "typed_identity_gate",
                "reject_reason": "",
            }
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=BASE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(out_path)
    return {
        "products": len(products),
        "esha_records": len(eshas),
        "assigned": assigned,
        "unassigned": len(products) - assigned,
        "output": str(out_path),
        "top_reject_reasons": dict(sorted(rejects.items(), key=lambda item: item[1], reverse=True)[:30]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a typed identity gated Product -> ESHA map.")
    parser.add_argument("--product-identity", type=Path, default=DEFAULT_PRODUCT_IDENTITY)
    parser.add_argument("--esha-identity", type=Path, default=DEFAULT_ESHA_IDENTITY)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    products = load_identity_jsonl(args.product_identity, "product")
    eshas = load_identity_jsonl(args.esha_identity, "esha")
    summary = build_map(products, eshas, args.out)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
