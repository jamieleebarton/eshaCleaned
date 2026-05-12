#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"

DEFAULT_MAP_CSV = OUT_DIR / "product_to_best_esha_full_map.vConceptAnchor.csv"
FALLBACK_MAP_CSV = OUT_DIR / "product_to_best_esha_full_map.csv"
PRODUCT_MEMBERS_CSV = OUT_DIR / "product_evidence_cluster_members_v2.csv"
PARSED_UNIFIED_CSV = OUT_DIR / "rft_poc" / "parsed_unified.csv"
OUT_BASE_DIR = OUT_DIR / "leaf_refinement_poc"

TOKEN_RE = re.compile(r"[a-z][a-z0-9']*")

TOKEN_NORMALIZATION = {
    "crackers": "cracker",
    "biscuits": "biscuit",
    "biscotti": "biscotti",
    "crisps": "crisp",
    "chips": "chip",
    "thins": "thin",
    "seeds": "seed",
    "grains": "grain",
    "wheats": "wheat",
    "cheeses": "cheese",
    "cheddars": "cheddar",
    "herbs": "herb",
    "flavors": "flavor",
    "flavoured": "flavored",
    "flavoring": "flavored",
    "flavored": "flavored",
    "tarallini": "taralli",
    "matzoh": "matzo",
    "matzos": "matzo",
    "matzahs": "matzo",
    "lavash": "lahvosh",
    "lahvash": "lahvosh",
    "triscuit": "triscuit",
    "wheatable": "wheatable",
    "cheez": "cheezit",
    "cheezit": "cheezit",
    "cheez-it": "cheezit",
    "cheezits": "cheezit",
}

STOP_TOKENS = {
    "and",
    "with",
    "the",
    "for",
    "from",
    "made",
    "oz",
    "ounce",
    "pack",
    "packs",
    "count",
    "ct",
    "variety",
    "collection",
    "assorted",
    "naturally",
    "original",
    "classic",
    "traditional",
    "light",
    "flaky",
    "baked",
    "organic",
    "simply",
    "brand",
}

CRACKER_ANCHOR_HEADS = {"cracker", "crackers", "cracker crumbs", "cracker meal"}

STRONG_KINDS = {
    "animal",
    "butter",
    "cheese",
    "club",
    "cream",
    "crostini",
    "cuban",
    "flatbread",
    "graham",
    "lahvosh",
    "matzo",
    "melba_toast",
    "milk",
    "multigrain",
    "nut_thin",
    "oat",
    "oyster",
    "papad",
    "rice",
    "rye",
    "saltine",
    "sandwich",
    "seeded",
    "sesame",
    "snack",
    "taralli",
    "water",
    "wheat",
    "whole_wheat",
}

KNOWN_GAP_KINDS = {"taralli", "lahvosh", "crostini"}


@dataclass(frozen=True)
class LeafConcept:
    lane: str
    kind: str
    grains: tuple[str, ...]
    flavors: tuple[str, ...]
    forms: tuple[str, ...]
    diets: tuple[str, ...]

    @property
    def path(self) -> str:
        return "/".join(
            (
                self.lane,
                self.kind or "generic",
                "+".join(self.grains) if self.grains else "generic",
                "+".join(self.flavors) if self.flavors else "plain",
                "+".join(self.forms) if self.forms else "generic",
                "+".join(self.diets) if self.diets else "standard",
            )
        )

    @property
    def concept_id(self) -> str:
        return hashlib.sha1(self.path.encode("utf-8")).hexdigest()[:14]


@dataclass(frozen=True)
class Anchor:
    source: str
    code: str
    description: str
    concept: LeafConcept


@dataclass(frozen=True)
class AnchorMatch:
    anchor: Anchor
    score: float
    reason: str


def normalized_token(raw: str) -> str:
    token = raw.lower().strip("'")
    token = TOKEN_NORMALIZATION.get(token, token)
    if len(token) > 3 and token.endswith("s"):
        token = TOKEN_NORMALIZATION.get(token[:-1], token[:-1])
    return token


def tokens_for(text: object) -> set[str]:
    text_s = str(text or "").lower().replace("&", " and ").replace("-", " ")
    tokens = {normalized_token(t) for t in TOKEN_RE.findall(text_s)}
    if "cheez it" in text_s or "cheez-it" in text_s:
        tokens.add("cheezit")
    if "water cracker" in text_s or "table water" in text_s:
        tokens.update({"water", "cracker"})
    if "whole wheat" in text_s:
        tokens.update({"whole", "wheat"})
    if "multi grain" in text_s or "multi-grain" in text_s:
        tokens.add("multigrain")
    if "gluten free" in text_s or "gluten-free" in text_s:
        tokens.add("gluten_free")
    if "peanut butter" in text_s:
        tokens.update({"peanut", "butter"})
    if "melba toast" in text_s:
        tokens.update({"melba", "toast"})
    if "flat bread" in text_s or "flatbread" in text_s:
        tokens.add("flatbread")
    return {t for t in tokens if len(t) >= 2}


def compact(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({v for v in values if v and v != "generic"}))


def detect_kind(title_tokens: set[str], ingredient_tokens: set[str], description: str) -> str:
    tokens = title_tokens
    desc_l = description.lower()
    priority = [
        ("sandwich", {"sandwich", "filled", "filling", "peanut"}),
        ("graham", {"graham"}),
        ("saltine", {"saltine", "soda"}),
        ("oyster", {"oyster"}),
        ("water", {"water"}),
        ("cuban", {"cuban"}),
        ("lahvosh", {"lahvosh"}),
        ("taralli", {"taralli"}),
        ("crostini", {"crostini"}),
        ("matzo", {"matzo"}),
        ("melba_toast", {"melba", "toast"}),
        ("cream", {"cream"}),
        ("club", {"club"}),
        ("butter", {"butter"}),
        ("milk", {"milk"}),
        ("rice", {"rice"}),
        ("nut_thin", {"almond", "pecan", "hazelnut", "nut"}),
        ("sesame", {"sesame"}),
        ("seeded", {"seed", "flax", "chia", "sunflower", "pumpkin", "ancient"}),
        ("whole_wheat", {"whole", "wheat"}),
        ("multigrain", {"multigrain", "grain"}),
        ("wheat", {"wheat", "wheatable"}),
        ("rye", {"rye", "crispbread"}),
        ("oat", {"oat", "oatmeal"}),
        ("flatbread", {"flatbread"}),
        ("cheese", {"cheese", "cheddar", "parmesan", "asiago", "cheezit"}),
        ("animal", {"animal"}),
        ("papad", {"papad", "poppadum", "pappadom"}),
        ("snack", {"snack", "snacker"}),
    ]
    for kind, markers in priority:
        if tokens & markers:
            return kind
    if "cracker" in tokens or "crackers" in desc_l:
        return "original"
    return "unknown"


def detect_grains(tokens: set[str]) -> tuple[str, ...]:
    out = set()
    for grain in ("wheat", "whole_wheat", "rice", "rye", "oat", "corn", "barley", "sesame", "flax", "multigrain"):
        if grain in tokens:
            out.add(grain)
    if {"whole", "wheat"} <= tokens:
        out.add("whole_wheat")
    if "grain" in tokens or "multigrain" in tokens:
        out.add("multigrain")
    if "brown" in tokens and "rice" in tokens:
        out.add("brown_rice")
    return compact(out)


def detect_flavors(tokens: set[str]) -> tuple[str, ...]:
    out = set()
    flavor_terms = {
        "cheese",
        "cheddar",
        "parmesan",
        "asiago",
        "garlic",
        "herb",
        "italian",
        "sesame",
        "pepper",
        "coconut",
        "curry",
        "ranch",
        "rosemary",
        "olive",
        "tomato",
        "onion",
        "honey",
        "cinnamon",
        "chocolate",
        "chocolaty",
        "spicy",
        "wasabi",
        "seaweed",
        "butter",
        "smokehouse",
        "salt",
        "sea",
    }
    out |= tokens & flavor_terms
    if "white" in tokens and "cheddar" in tokens:
        out.add("white_cheddar")
    if "black" in tokens and "sesame" in tokens:
        out.add("black_sesame")
    if "roasted" in tokens and "garlic" in tokens:
        out.add("roasted_garlic")
    if "sea" in tokens and "salt" in tokens:
        out.add("sea_salt")
    if "flavored" in tokens and not out:
        out.add("flavored")
    return compact(out)


def detect_forms(tokens: set[str]) -> tuple[str, ...]:
    out = set()
    form_terms = {
        "thin",
        "crisp",
        "chip",
        "stick",
        "wafer",
        "round",
        "square",
        "mini",
        "bite",
        "meal",
        "crumb",
        "crushed",
        "toast",
        "flatbread",
        "sandwich",
        "filled",
        "filling",
    }
    out |= tokens & form_terms
    if "cracker" in tokens and "meal" in tokens:
        out.add("meal")
    if "cracker" in tokens and "chip" in tokens:
        out.add("chip")
    return compact(out)


def detect_diets(tokens: set[str]) -> tuple[str, ...]:
    out = set()
    if "gluten_free" in tokens:
        out.add("gluten_free")
    if "reduced" in tokens and "fat" in tokens:
        out.add("reduced_fat")
    if "low" in tokens and "sodium" in tokens:
        out.add("low_sodium")
    if "unsalted" in tokens:
        out.add("unsalted")
    if "organic" in tokens:
        out.add("organic")
    return compact(out)


def cracker_concept(description: object, category: object = "", title_terms: object = "", ingredient_terms: object = "") -> LeafConcept | None:
    description_s = str(description or "")
    category_s = str(category or "")
    title_tokens = tokens_for(f"{description_s} {title_terms}")
    ingredient_tokens = tokens_for(ingredient_terms)
    category_tokens = tokens_for(category_s)
    if "cracker" not in (title_tokens | category_tokens | ingredient_tokens) and "crackers" not in description_s.lower():
        return None
    kind = detect_kind(title_tokens, ingredient_tokens, description_s)
    all_tokens = title_tokens | ingredient_tokens
    return LeafConcept(
        lane="cracker",
        kind=kind,
        grains=detect_grains(all_tokens),
        flavors=detect_flavors(title_tokens),
        forms=detect_forms(title_tokens),
        diets=detect_diets(title_tokens),
    )


def anchor_allowed(row: dict[str, str]) -> bool:
    if row.get("source") != "esha":
        return False
    head = (row.get("head") or "").lower().strip()
    desc = (row.get("full_desc") or "").lower()
    if head in CRACKER_ANCHOR_HEADS:
        return True
    if desc.startswith("cracker,") or desc.startswith("crackers,"):
        return True
    return False


def load_anchors(path: Path) -> list[Anchor]:
    anchors: list[Anchor] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if not anchor_allowed(row):
                continue
            concept = cracker_concept(row.get("full_desc", ""))
            if not concept:
                continue
            anchors.append(Anchor("esha", str(row.get("code") or ""), str(row.get("full_desc") or ""), concept))
    return anchors


def score_anchor(product: LeafConcept, anchor: Anchor) -> AnchorMatch | None:
    candidate = anchor.concept
    if product.lane != candidate.lane:
        return None
    score = 0.0
    reasons: list[str] = []

    if product.kind == candidate.kind:
        score += 60.0
        reasons.append(f"kind:{product.kind}")
    elif product.kind == "original" and candidate.kind in {"original", "snack"}:
        score += 40.0
        reasons.append("generic_original_to_snack")
    elif candidate.kind == "original":
        score += 18.0
        reasons.append("original_proxy")
    elif product.kind not in STRONG_KINDS or product.kind == "unknown":
        score += 10.0
        reasons.append("unknown_kind_proxy")
    else:
        score -= 30.0
        reasons.append(f"kind_mismatch:{candidate.kind}")

    product_grains = set(product.grains)
    anchor_grains = set(candidate.grains)
    if product_grains:
        overlap = product_grains & anchor_grains
        if overlap:
            score += 12.0 + min(8.0, 2.0 * len(overlap))
            reasons.append("grain:" + "+".join(sorted(overlap)))
        elif candidate.kind == product.kind:
            score -= 4.0
            reasons.append("grain_proxy")

    product_flavors = set(product.flavors)
    anchor_flavors = set(candidate.flavors)
    if product_flavors:
        overlap = product_flavors & anchor_flavors
        if overlap:
            score += 10.0 + min(8.0, 2.0 * len(overlap))
            reasons.append("flavor:" + "+".join(sorted(overlap)))
        elif product.kind in {"cheese", "sesame", "butter"}:
            score -= 8.0
            reasons.append("flavor_proxy")
        else:
            score -= 3.0
            reasons.append("flavor_unmatched")

    product_forms = set(product.forms)
    anchor_forms = set(candidate.forms)
    if product_forms:
        overlap = product_forms & anchor_forms
        if overlap:
            score += 8.0 + min(6.0, 2.0 * len(overlap))
            reasons.append("form:" + "+".join(sorted(overlap)))
        elif product.kind == candidate.kind:
            score -= 3.0
            reasons.append("form_proxy")

    product_diets = set(product.diets)
    anchor_diets = set(candidate.diets)
    if product_diets and product_diets & anchor_diets:
        score += 4.0
        reasons.append("diet:" + "+".join(sorted(product_diets & anchor_diets)))

    if candidate.kind in {"pie_crust", "meal"} and product.kind not in {"pie_crust", "meal"}:
        score -= 20.0
        reasons.append("bad_anchor_form")

    return AnchorMatch(anchor=anchor, score=score, reason=";".join(reasons))


def best_anchor(concept: LeafConcept, anchors: list[Anchor]) -> AnchorMatch | None:
    matches = [match for anchor in anchors for match in [score_anchor(concept, anchor)] if match]
    if not matches:
        return None
    matches.sort(key=lambda m: (m.score, -len(m.anchor.description)), reverse=True)
    return matches[0]


def load_member_evidence(path: Path) -> dict[str, dict[str, str]]:
    evidence: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            fdc_id = str(row.get("fdc_id") or "")
            if fdc_id and fdc_id not in evidence:
                evidence[fdc_id] = row
    return evidence


def concept_status(concept: LeafConcept, current_code: str, match: AnchorMatch | None, target_code: str) -> tuple[str, str]:
    if concept.kind in KNOWN_GAP_KINDS:
        return "esha_gap", f"no_specific_{concept.kind}_cracker_anchor"
    if not match:
        return "review", "no_anchor_match"
    if match.anchor.code == target_code:
        return "keep_current", "current_best_anchor"
    if match.score >= 58.0:
        return "move_candidate", f"better_specific_anchor:{match.anchor.code}"
    if concept.kind != "original" and match.score < 58.0:
        return "review", "weak_specific_anchor"
    return "keep_current", "compatible_generic_original"


def read_target_products(map_path: Path, target_code: str, evidence: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with map_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if str(row.get("best_esha_code") or "") != target_code:
                continue
            fdc_id = str(row.get("fdc_id") or "")
            ev = evidence.get(fdc_id, {})
            concept = cracker_concept(
                row.get("product_description", ""),
                row.get("branded_food_category", ""),
                ev.get("title_identity_terms", ""),
                ev.get("ingredient_core_terms", ""),
            )
            if not concept:
                continue
            rows.append(
                {
                    "gtin_upc": row.get("gtin_upc", ""),
                    "fdc_id": fdc_id,
                    "product_description": row.get("product_description", ""),
                    "branded_food_category": row.get("branded_food_category", ""),
                    "brand_owner": row.get("brand_owner", ""),
                    "brand_name": row.get("brand_name", ""),
                    "current_esha_code": row.get("best_esha_code", ""),
                    "current_esha_description": row.get("best_esha_description", ""),
                    "assignment_source": row.get("assignment_source", ""),
                    "score": row.get("score", ""),
                    "cluster_id": ev.get("cluster_id", ""),
                    "category_lane": ev.get("category_lane", ""),
                    "product_form": ev.get("product_form", ""),
                    "primary_food": ev.get("primary_food", ""),
                    "title_identity_terms": ev.get("title_identity_terms", ""),
                    "ingredient_core_terms": ev.get("ingredient_core_terms", ""),
                    "concept_id": concept.concept_id,
                    "concept_path": concept.path,
                    "kind": concept.kind,
                    "grains": " ".join(concept.grains),
                    "flavors": " ".join(concept.flavors),
                    "forms": " ".join(concept.forms),
                    "diets": " ".join(concept.diets),
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def summarize_counts(values: Iterable[str], limit: int = 10) -> str:
    return " | ".join(f"{k}:{v}" for k, v in Counter(v for v in values if v).most_common(limit))


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "leaf"


def build_refinement(args: argparse.Namespace) -> dict[str, object]:
    map_path = args.map_csv
    if not map_path.exists() and args.map_csv == DEFAULT_MAP_CSV:
        map_path = FALLBACK_MAP_CSV
    anchors = load_anchors(args.parsed_unified)
    evidence = load_member_evidence(args.product_members)
    product_rows = read_target_products(map_path, args.esha_code, evidence)

    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in product_rows:
        groups[str(row["concept_path"])].append(row)

    concept_rows: list[dict[str, object]] = []
    enriched_products: list[dict[str, object]] = []
    for path, rows in groups.items():
        first = rows[0]
        parts = path.split("/")
        concept = LeafConcept(
            lane=parts[0],
            kind=parts[1],
            grains=tuple(() if parts[2] == "generic" else parts[2].split("+")),
            flavors=tuple(() if parts[3] == "plain" else parts[3].split("+")),
            forms=tuple(() if parts[4] == "generic" else parts[4].split("+")),
            diets=tuple(() if parts[5] == "standard" else parts[5].split("+")),
        )
        match = best_anchor(concept, anchors)
        status, reason = concept_status(concept, args.esha_code, match, args.esha_code)
        concept_row = {
            "concept_id": concept.concept_id,
            "concept_path": concept.path,
            "status": status,
            "reason": reason,
            "n_products": len(rows),
            "kind": concept.kind,
            "grains": " ".join(concept.grains),
            "flavors": " ".join(concept.flavors),
            "forms": " ".join(concept.forms),
            "diets": " ".join(concept.diets),
            "top_categories": summarize_counts((str(r["branded_food_category"]) for r in rows), 8),
            "top_brands": summarize_counts((str(r["brand_name"]) for r in rows), 8),
            "sample_products": " || ".join(str(r["product_description"]) for r in rows[:10]),
            "current_code": args.esha_code,
            "candidate_code": match.anchor.code if match else "",
            "candidate_description": match.anchor.description if match else "",
            "candidate_score": f"{match.score:.1f}" if match else "",
            "candidate_reason": match.reason if match else "",
        }
        concept_rows.append(concept_row)
        for row in rows:
            enriched = dict(row)
            enriched.update(
                {
                    "refinement_status": status,
                    "refinement_reason": reason,
                    "candidate_esha_code": concept_row["candidate_code"],
                    "candidate_esha_description": concept_row["candidate_description"],
                    "candidate_score": concept_row["candidate_score"],
                    "candidate_reason": concept_row["candidate_reason"],
                }
            )
            enriched_products.append(enriched)

    concept_rows.sort(key=lambda r: ({"move_candidate": 3, "esha_gap": 2, "review": 1, "keep_current": 0}.get(str(r["status"]), 0), int(r["n_products"])), reverse=True)
    enriched_products.sort(key=lambda r: (str(r["refinement_status"]), str(r["concept_path"]), str(r["product_description"])))
    gap_rows = [r for r in concept_rows if r["status"] in {"move_candidate", "esha_gap", "review"}]

    out_dir = args.output_dir / f"{args.esha_code}_{safe_slug(args.leaf_name)}"
    products_path = out_dir / "products.csv"
    concepts_path = out_dir / "concepts.csv"
    gaps_path = out_dir / "gaps_and_moves.csv"
    summary_path = out_dir / "summary.json"
    md_path = out_dir / "summary.md"

    concept_fields = [
        "concept_id",
        "concept_path",
        "status",
        "reason",
        "n_products",
        "kind",
        "grains",
        "flavors",
        "forms",
        "diets",
        "top_categories",
        "top_brands",
        "sample_products",
        "current_code",
        "candidate_code",
        "candidate_description",
        "candidate_score",
        "candidate_reason",
    ]
    product_fields = [
        "gtin_upc",
        "fdc_id",
        "product_description",
        "branded_food_category",
        "brand_owner",
        "brand_name",
        "current_esha_code",
        "current_esha_description",
        "assignment_source",
        "score",
        "cluster_id",
        "category_lane",
        "product_form",
        "primary_food",
        "title_identity_terms",
        "ingredient_core_terms",
        "concept_id",
        "concept_path",
        "kind",
        "grains",
        "flavors",
        "forms",
        "diets",
        "refinement_status",
        "refinement_reason",
        "candidate_esha_code",
        "candidate_esha_description",
        "candidate_score",
        "candidate_reason",
    ]
    write_csv(concepts_path, concept_rows, concept_fields)
    write_csv(products_path, enriched_products, product_fields)
    write_csv(gaps_path, gap_rows, concept_fields)

    status_counts = Counter(str(r["refinement_status"]) for r in enriched_products)
    kind_counts = Counter(str(r["kind"]) for r in enriched_products)
    summary = {
        "map_csv": str(map_path),
        "target_code": args.esha_code,
        "target_name": args.leaf_name,
        "anchors_indexed": len(anchors),
        "products": len(enriched_products),
        "concepts": len(concept_rows),
        "status_counts": status_counts.most_common(),
        "kind_counts": kind_counts.most_common(),
        "outputs": {
            "concepts": str(concepts_path),
            "products": str(products_path),
            "gaps_and_moves": str(gaps_path),
            "markdown": str(md_path),
            "summary": str(summary_path),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(md_path, summary, concept_rows, gap_rows)
    return summary


def write_markdown(
    path: Path,
    summary: dict[str, object],
    concept_rows: list[dict[str, object]],
    gap_rows: list[dict[str, object]],
) -> None:
    lines = [
        f"# Leaf refinement POC: {summary['target_code']} {summary['target_name']}\n\n",
        "Products already assigned to this ESHA leaf are clustered by title/category/ingredient evidence, then compared with specific ESHA cracker anchors.\n\n",
        "## Summary\n\n",
        f"- Products: {summary['products']:,}\n",
        f"- Concepts: {summary['concepts']:,}\n",
        f"- ESHA cracker anchors indexed: {summary['anchors_indexed']:,}\n",
        f"- Status counts: {summary['status_counts']}\n\n",
        "## Top Moves And Gaps\n\n",
    ]
    for row in gap_rows[:40]:
        lines.extend(markdown_block(row))
    lines.append("## Top Clusters\n\n")
    for row in sorted(concept_rows, key=lambda r: int(r["n_products"]), reverse=True)[:40]:
        lines.extend(markdown_block(row))
    lines.append("## Files\n\n")
    outputs = summary["outputs"]
    assert isinstance(outputs, dict)
    for label, output_path in outputs.items():
        lines.append(f"- {label}: `{output_path}`\n")
    path.write_text("".join(lines), encoding="utf-8")


def markdown_block(row: dict[str, object]) -> list[str]:
    return [
        f"### `{row['concept_path']}` (n={row['n_products']}, {row['status']})\n",
        f"- reason: `{row['reason']}`\n",
        f"- candidate: [{row['candidate_code']}] {row['candidate_description']} (score={row['candidate_score']})\n",
        f"- categories: {row['top_categories']}\n",
        f"- samples: {row['sample_products']}\n\n",
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cluster products inside one ESHA leaf and find specific move/gap candidates.")
    parser.add_argument("--esha-code", default="43785")
    parser.add_argument("--leaf-name", default="Cracker original")
    parser.add_argument("--map-csv", type=Path, default=DEFAULT_MAP_CSV)
    parser.add_argument("--product-members", type=Path, default=PRODUCT_MEMBERS_CSV)
    parser.add_argument("--parsed-unified", type=Path, default=PARSED_UNIFIED_CSV)
    parser.add_argument("--output-dir", type=Path, default=OUT_BASE_DIR)
    return parser.parse_args()


def main() -> None:
    print(json.dumps(build_refinement(parse_args()), indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
