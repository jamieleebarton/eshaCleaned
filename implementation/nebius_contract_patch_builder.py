"""Build deterministic ESHA contract patches from structured Nebius output.

Nebius is allowed to propose contract intent. This builder owns Python source
generation, diff formatting, and evidence self-checks so raw model diffs never
touch the patch gate.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any


IMPLEMENTATION_ROOT = Path(__file__).resolve().parent
ROOT = IMPLEMENTATION_ROOT.parent
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

from esha_contracts.contract_base import ProductFacts
import esha_audit_toolkit as _toolkit

MODULE_REL = "implementation/esha_contracts/reviewed_nebius_generated.py"
REGISTRY_REL = "implementation/output/nebius_contract_decisions/reviewed_nebius_generated_specs.json"
MODULE_PATH = ROOT / MODULE_REL
REGISTRY_PATH = ROOT / REGISTRY_REL

# max acceptable euclidean distance between current and proposed (kcal, protein, fat, carbs) vectors
NUTRIENT_SANITY_MAX_DISTANCE = 150.0


def nutrient_sanity_check(current_esha_code, proposed_esha_code):
    """Return {passed, distance, profiles, reason} for a proposed ESHA reassignment.

    - Either code missing          => pass (can't compare; human decides)
    - Same code                    => pass (distance 0)
    - Distance > threshold         => fail (blocks auto-apply; human review only)
    """
    if not current_esha_code or not proposed_esha_code:
        return {"passed": True, "reason": "missing code", "distance": None, "profiles": []}
    if int(current_esha_code) == int(proposed_esha_code):
        return {"passed": True, "reason": "same code", "distance": 0.0, "profiles": []}
    cmp = _toolkit.compare_nutrient_fingerprint([int(current_esha_code), int(proposed_esha_code)])
    if not cmp["pairwise_euclid"]:
        return {"passed": True, "reason": "no pair", "distance": None, "profiles": cmp["profiles"]}
    dist = cmp["pairwise_euclid"][0]["distance"]
    passed = dist <= NUTRIENT_SANITY_MAX_DISTANCE
    return {
        "passed": passed,
        "distance": dist,
        "threshold": NUTRIENT_SANITY_MAX_DISTANCE,
        "reason": "within threshold" if passed else "nutrient category shift",
        "profiles": cmp["profiles"],
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def normalize_phrase(value: Any) -> str:
    text = str(value or "").lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9.]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def unique_clean(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        text = normalize_phrase(value)
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned


def split_terms_and_phrases(values: Any) -> tuple[list[str], list[str]]:
    terms: list[str] = []
    phrases: list[str] = []
    for value in unique_clean(values):
        if " " in value:
            phrases.append(value)
        else:
            terms.append(value)
    return terms, phrases


def clean_gtins(rows: Any) -> list[str]:
    if not isinstance(rows, list):
        return []
    gtins: list[str] = []
    seen: set[str] = set()
    for row in rows:
        value = row.get("gtin_upc") if isinstance(row, dict) else row
        if value in (None, ""):
            continue
        gtin = str(value)
        if gtin not in seen:
            seen.add(gtin)
            gtins.append(gtin)
    return gtins


def extract_spec(packet: dict[str, Any], final: dict[str, Any]) -> dict[str, Any]:
    structured = final.get("structured_contract")
    if not isinstance(structured, dict):
        structured = {}
    changes = final.get("contract_changes")
    if not isinstance(changes, dict):
        changes = {}

    code = str(structured.get("esha_code") or final.get("esha_code") or packet.get("esha_code") or "")
    if not code:
        raise ValueError("missing ESHA code")

    required_terms, required_phrases = split_terms_and_phrases(
        structured.get("required_description_terms") or changes.get("required_terms")
    )
    extra_required_phrases = unique_clean(structured.get("required_description_phrases"))
    for phrase in extra_required_phrases:
        if phrase not in required_phrases:
            required_phrases.append(phrase)

    exclude_terms, exclude_phrases = split_terms_and_phrases(
        structured.get("exclude_description_terms") or changes.get("exclude_terms")
    )
    for phrase in unique_clean(structured.get("exclude_description_phrases")):
        if phrase not in exclude_phrases:
            exclude_phrases.append(phrase)

    ingredient_required_terms, ingredient_required_phrases = split_terms_and_phrases(
        structured.get("required_ingredient_terms")
    )
    for phrase in unique_clean(structured.get("required_ingredient_phrases")):
        if phrase not in ingredient_required_phrases:
            ingredient_required_phrases.append(phrase)

    ingredient_exclude_terms, ingredient_exclude_phrases = split_terms_and_phrases(
        structured.get("exclude_ingredient_terms") or changes.get("ingredient_exclude_terms")
    )
    for phrase in unique_clean(structured.get("exclude_ingredient_phrases")):
        if phrase not in ingredient_exclude_phrases:
            ingredient_exclude_phrases.append(phrase)

    allowed_categories = unique_clean(structured.get("allowed_categories") or changes.get("allowed_categories"))
    required_any_groups = [
        unique_clean(group)
        for group in structured.get("required_description_any_terms", [])
        if isinstance(group, list) and unique_clean(group)
    ]
    required_ingredient_any_groups = [
        unique_clean(group)
        for group in structured.get("required_ingredient_any_terms", [])
        if isinstance(group, list) and unique_clean(group)
    ]
    accepted_gtins = unique_clean(structured.get("accepted_gtins")) or clean_gtins(final.get("clean_products"))
    rejected_gtins = unique_clean(structured.get("rejected_gtins")) or clean_gtins(final.get("reject_products"))

    if not allowed_categories:
        raise ValueError(f"{code} missing allowed_categories")
    if (
        not required_terms
        and not required_phrases
        and not required_any_groups
        and not ingredient_required_terms
        and not ingredient_required_phrases
        and not required_ingredient_any_groups
    ):
        # Permit category+exclude-only contracts when there is enough exclude
        # signal to discriminate. Validates against pack evidence downstream;
        # without any excludes a category-only contract would accept everything.
        has_excludes = bool(
            exclude_terms
            or exclude_phrases
            or ingredient_exclude_terms
            or ingredient_exclude_phrases
        )
        if not has_excludes:
            raise ValueError(f"{code} missing required contract identity terms")

    return {
        "esha_code": code,
        "esha_description": str(
            structured.get("esha_description")
            or final.get("esha_description")
            or packet.get("esha_description")
            or packet.get("normalized_item")
            or ""
        ),
        "allowed_categories": allowed_categories,
        "required_description_terms": required_terms,
        "required_description_phrases": required_phrases,
        "required_description_any_terms": required_any_groups,
        "exclude_description_terms": exclude_terms,
        "exclude_description_phrases": exclude_phrases,
        "required_ingredient_terms": ingredient_required_terms,
        "required_ingredient_phrases": ingredient_required_phrases,
        "required_ingredient_any_terms": required_ingredient_any_groups,
        "exclude_ingredient_terms": ingredient_exclude_terms,
        "exclude_ingredient_phrases": ingredient_exclude_phrases,
        "accepted_gtins": accepted_gtins,
        "rejected_gtins": rejected_gtins,
        "decision": str(final.get("decision") or ""),
        "summary": str(final.get("summary") or ""),
    }


def parse_markdown_products(card_markdown: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in card_markdown.splitlines():
        line = raw.strip()
        if not line.startswith("|") or "---" in line or "gtin_upc" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 8:
            continue
        rank, gtin, fdc_id, description, category, ingredients, signal, noise_terms = cells[:8]
        if not gtin or gtin.lower() in {"gtin_upc", "null"}:
            continue
        rows.append(
            {
                "rank": rank,
                "gtin_upc": gtin,
                "fdc_id": fdc_id,
                "description": description,
                "branded_food_category": category,
                "ingredients": ingredients,
                "signal": signal,
                "noise_terms": noise_terms,
            }
        )
    return rows


def evidence_products(packet: dict[str, Any]) -> dict[str, ProductFacts]:
    products: dict[str, ProductFacts] = {}

    def add(row: dict[str, Any]) -> None:
        gtin = str(row.get("gtin_upc") or row.get("gtin") or "").strip()
        if not gtin or gtin in products:
            return
        description = str(row.get("description") or row.get("product_description") or "")
        category = str(row.get("branded_food_category") or row.get("category") or "")
        ingredients = str(row.get("ingredients") or "")
        products[gtin] = ProductFacts.from_components(description, category, ingredients)

    for container_name in ("product_search", "assigned_product_codes"):
        container = packet.get(container_name)
        if isinstance(container, dict):
            for row in container.get("rows") or []:
                if isinstance(row, dict):
                    add(row)
    card = packet.get("card")
    if isinstance(card, dict):
        for row in parse_markdown_products(str(card.get("card_markdown") or "")):
            add(row)
    return products


def evaluate_spec(spec: dict[str, Any], product: ProductFacts) -> tuple[str, str]:
    code = spec["esha_code"]
    categories = tuple(spec["allowed_categories"])
    if categories and not product.category_has_any(*categories):
        return "reject", f"{code} category mismatch"
    missing = [term for term in spec["required_description_terms"] if not product.has_any(term)]
    if missing:
        return "reject", f"{code} missing required term(s): " + "|".join(missing)
    missing_phrases = [phrase for phrase in spec["required_description_phrases"] if not product.has_phrase(phrase)]
    if missing_phrases:
        return "reject", f"{code} missing required phrase(s): " + "|".join(missing_phrases)
    missing_any = [
        "|".join(group)
        for group in spec["required_description_any_terms"]
        if not any(product.has_any(term) for term in group)
    ]
    if missing_any:
        return "reject", f"{code} missing required any-term group(s): " + ";".join(missing_any)
    missing_ingredients = [
        term for term in spec["required_ingredient_terms"] if not product.ingredients_have_any(term)
    ]
    if missing_ingredients:
        return "reject", f"{code} missing required ingredient term(s): " + "|".join(missing_ingredients)
    missing_ingredient_phrases = [
        phrase for phrase in spec["required_ingredient_phrases"] if not product.ingredients_have_phrase(phrase)
    ]
    if missing_ingredient_phrases:
        return "reject", f"{code} missing required ingredient phrase(s): " + "|".join(missing_ingredient_phrases)
    missing_ingredient_any = [
        "|".join(group)
        for group in spec["required_ingredient_any_terms"]
        if not any(product.ingredients_have_any(term) for term in group)
    ]
    if missing_ingredient_any:
        return "reject", f"{code} missing required ingredient any-term group(s): " + ";".join(missing_ingredient_any)
    excluded = [term for term in spec["exclude_description_terms"] if product.has_any(term)]
    if excluded:
        return "reject", f"{code} excluded term(s): " + "|".join(excluded)
    excluded_phrases = [phrase for phrase in spec["exclude_description_phrases"] if product.has_phrase(phrase)]
    if excluded_phrases:
        return "reject", f"{code} excluded phrase(s): " + "|".join(excluded_phrases)
    ingredient_excluded = [
        term for term in spec["exclude_ingredient_terms"] if product.ingredients_have_any(term)
    ]
    if ingredient_excluded:
        return "reject", f"{code} excluded ingredient term(s): " + "|".join(ingredient_excluded)
    ingredient_excluded_phrases = [
        phrase for phrase in spec["exclude_ingredient_phrases"] if product.ingredients_have_phrase(phrase)
    ]
    if ingredient_excluded_phrases:
        return "reject", f"{code} excluded ingredient phrase(s): " + "|".join(ingredient_excluded_phrases)
    return "accept", f"{code} reviewed generated contract accepted"


def auto_relax_spec(packet: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, str]]:
    """Drop required terms that aren't present across all accepted GTINs.

    The verifier tends to union terms seen in the category (e.g. sugar, cornstarch
    for "apple pie filling") instead of intersecting terms that actually appear in
    every accepted GTIN. Terms that fail on any accepted GTIN are pruned so the
    spec can't reject its own evidence. Rejected GTINs are ignored since they
    define what the contract excludes, not what it requires.
    """
    products = evidence_products(packet)
    accepted = [products[g] for g in spec["accepted_gtins"] if g in products]
    if not accepted:
        return []

    relaxed: list[dict[str, str]] = []

    def prune(field: str, values: list[str], check) -> list[str]:
        kept: list[str] = []
        for value in values:
            if all(check(product, value) for product in accepted):
                kept.append(value)
            else:
                relaxed.append({"field": field, "value": value})
        return kept

    spec["required_description_terms"] = prune(
        "required_description_terms",
        spec["required_description_terms"],
        lambda p, t: p.has_any(t),
    )
    spec["required_description_phrases"] = prune(
        "required_description_phrases",
        spec["required_description_phrases"],
        lambda p, t: p.has_phrase(t),
    )
    spec["required_ingredient_terms"] = prune(
        "required_ingredient_terms",
        spec["required_ingredient_terms"],
        lambda p, t: p.ingredients_have_any(t),
    )
    spec["required_ingredient_phrases"] = prune(
        "required_ingredient_phrases",
        spec["required_ingredient_phrases"],
        lambda p, t: p.ingredients_have_phrase(t),
    )
    return relaxed


def validate_spec(packet: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    products = evidence_products(packet)
    failures: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    checks: list[dict[str, str]] = []

    for gtin in spec["accepted_gtins"]:
        product = products.get(gtin)
        if product is None:
            warnings.append({"gtin_upc": gtin, "warning": "accepted_gtin_not_found_in_packet_evidence"})
            continue
        status, reason = evaluate_spec(spec, product)
        checks.append({"gtin_upc": gtin, "expected": "accept", "actual": status, "reason": reason})
        if status != "accept":
            failures.append({"gtin_upc": gtin, "expected": "accept", "actual": status, "reason": reason})

    for gtin in spec["rejected_gtins"]:
        product = products.get(gtin)
        if product is None:
            warnings.append({"gtin_upc": gtin, "warning": "rejected_gtin_not_found_in_packet_evidence"})
            continue
        status, reason = evaluate_spec(spec, product)
        checks.append({"gtin_upc": gtin, "expected": "reject", "actual": status, "reason": reason})
        if status != "reject":
            failures.append({"gtin_upc": gtin, "expected": "reject", "actual": status, "reason": reason})

    return {
        "ok": not failures,
        "failures": failures,
        "warnings": warnings,
        "checks": checks,
        "evidence_product_count": len(products),
    }


def load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {"contracts": {}}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def py_value(value: Any) -> str:
    return repr(value)


def render_module(registry: dict[str, Any]) -> str:
    specs = registry.get("contracts") or {}
    lines = [
        "from __future__ import annotations",
        "",
        "from .contract_base import ContractFn, MatchDecision, ProductFacts, accept, reject",
        "",
        "",
        "GENERATED_CONTRACT_SPECS = {",
    ]
    for code in sorted(specs, key=lambda item: int(item) if str(item).isdigit() else str(item)):
        spec = specs[code]
        lines.append(f"    {code!r}: {py_value(spec)},")
    lines.extend(
        [
            "}",
            "",
            "",
            "def _generated_contract(esha_code: str, spec: dict[str, object]) -> ContractFn:",
            "    categories = tuple(spec.get('allowed_categories') or ())",
            "    required_terms = tuple(spec.get('required_description_terms') or ())",
            "    required_phrases = tuple(spec.get('required_description_phrases') or ())",
            "    required_any_groups = tuple(tuple(group) for group in (spec.get('required_description_any_terms') or ()))",
            "    exclude_terms = tuple(spec.get('exclude_description_terms') or ())",
            "    exclude_phrases = tuple(spec.get('exclude_description_phrases') or ())",
            "    required_ingredient_terms = tuple(spec.get('required_ingredient_terms') or ())",
            "    required_ingredient_phrases = tuple(spec.get('required_ingredient_phrases') or ())",
            "    required_ingredient_any_groups = tuple(tuple(group) for group in (spec.get('required_ingredient_any_terms') or ()))",
            "    exclude_ingredient_terms = tuple(spec.get('exclude_ingredient_terms') or ())",
            "    exclude_ingredient_phrases = tuple(spec.get('exclude_ingredient_phrases') or ())",
            "",
            "    def contract(product: ProductFacts) -> MatchDecision:",
            "        if categories and not product.category_has_any(*categories):",
            "            return reject(f'{esha_code} category mismatch')",
            "        missing = [term for term in required_terms if not product.has_any(term)]",
            "        if missing:",
            "            return reject(f'{esha_code} missing required term(s): ' + '|'.join(missing))",
            "        missing_phrases = [phrase for phrase in required_phrases if not product.has_phrase(phrase)]",
            "        if missing_phrases:",
            "            return reject(f'{esha_code} missing required phrase(s): ' + '|'.join(missing_phrases))",
            "        missing_any = ['|'.join(group) for group in required_any_groups if not any(product.has_any(term) for term in group)]",
            "        if missing_any:",
            "            return reject(f'{esha_code} missing required any-term group(s): ' + ';'.join(missing_any))",
            "        missing_ingredients = [term for term in required_ingredient_terms if not product.ingredients_have_any(term)]",
            "        if missing_ingredients:",
            "            return reject(f'{esha_code} missing required ingredient term(s): ' + '|'.join(missing_ingredients))",
            "        missing_ingredient_phrases = [phrase for phrase in required_ingredient_phrases if not product.ingredients_have_phrase(phrase)]",
            "        if missing_ingredient_phrases:",
            "            return reject(f'{esha_code} missing required ingredient phrase(s): ' + '|'.join(missing_ingredient_phrases))",
            "        missing_ingredient_any = ['|'.join(group) for group in required_ingredient_any_groups if not any(product.ingredients_have_any(term) for term in group)]",
            "        if missing_ingredient_any:",
            "            return reject(f'{esha_code} missing required ingredient any-term group(s): ' + ';'.join(missing_ingredient_any))",
            "        excluded = [term for term in exclude_terms if product.has_any(term)]",
            "        if excluded:",
            "            return reject(f'{esha_code} excluded term(s): ' + '|'.join(excluded))",
            "        excluded_phrases = [phrase for phrase in exclude_phrases if product.has_phrase(phrase)]",
            "        if excluded_phrases:",
            "            return reject(f'{esha_code} excluded phrase(s): ' + '|'.join(excluded_phrases))",
            "        ingredient_excluded = [term for term in exclude_ingredient_terms if product.ingredients_have_any(term)]",
            "        if ingredient_excluded:",
            "            return reject(f'{esha_code} excluded ingredient term(s): ' + '|'.join(ingredient_excluded))",
            "        ingredient_excluded_phrases = [phrase for phrase in exclude_ingredient_phrases if product.ingredients_have_phrase(phrase)]",
            "        if ingredient_excluded_phrases:",
            "            return reject(f'{esha_code} excluded ingredient phrase(s): ' + '|'.join(ingredient_excluded_phrases))",
            "        return accept(f'{esha_code} reviewed generated contract accepted')",
            "",
            "    return contract",
            "",
            "",
            "CONTRACTS: dict[str, ContractFn] = {",
            "    code: _generated_contract(code, spec)",
            "    for code, spec in GENERATED_CONTRACT_SPECS.items()",
            "}",
            "",
        ]
    )
    return "\n".join(lines)


def render_registry(registry: dict[str, Any]) -> str:
    return json.dumps(registry, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def file_diff(rel_path: str, old_text: str, new_text: str, existed: bool) -> str:
    if old_text == new_text:
        return ""
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    fromfile = f"a/{rel_path}" if existed else "/dev/null"
    tofile = f"b/{rel_path}"
    diff_lines = list(difflib.unified_diff(old_lines, new_lines, fromfile=fromfile, tofile=tofile))
    header = [f"diff --git a/{rel_path} b/{rel_path}\n"]
    if not existed:
        header.append("new file mode 100644\n")
    return "".join(header + diff_lines)


def build_patch(packet: dict[str, Any], final: dict[str, Any]) -> dict[str, Any]:
    if final.get("decision") in {"no_change", "needs_more_context"}:
        return {"status": "no_patch", "reason": f"decision={final.get('decision')}"}

    spec = extract_spec(packet, final)
    auto_relaxed = auto_relax_spec(packet, spec)
    has_identity = any(
        spec[field]
        for field in (
            "required_description_terms",
            "required_description_phrases",
            "required_description_any_terms",
            "required_ingredient_terms",
            "required_ingredient_phrases",
            "required_ingredient_any_terms",
        )
    )
    if not has_identity:
        return {
            "status": "semantic_validation_failed",
            "spec": spec,
            "auto_relaxed_terms": auto_relaxed,
            "validation": {
                "ok": False,
                "failures": [{"reason": "all required identity terms pruned against accepted evidence"}],
                "warnings": [],
                "checks": [],
                "evidence_product_count": len(evidence_products(packet)),
            },
            "patch": None,
        }
    validation = validate_spec(packet, spec)
    if not validation["ok"]:
        return {
            "status": "semantic_validation_failed",
            "spec": spec,
            "auto_relaxed_terms": auto_relaxed,
            "validation": validation,
            "patch": None,
        }

    registry = load_registry()
    contracts = registry.setdefault("contracts", {})
    contracts[spec["esha_code"]] = spec

    old_module = MODULE_PATH.read_text(encoding="utf-8") if MODULE_PATH.exists() else ""
    new_module = render_module(registry)
    old_registry = REGISTRY_PATH.read_text(encoding="utf-8") if REGISTRY_PATH.exists() else ""
    new_registry = render_registry(registry)
    patch = (
        file_diff(MODULE_REL, old_module, new_module, MODULE_PATH.exists())
        + file_diff(REGISTRY_REL, old_registry, new_registry, REGISTRY_PATH.exists())
    )
    return {
        "status": "patch_built",
        "spec": spec,
        "auto_relaxed_terms": auto_relaxed,
        "validation": validation,
        "touched_files": [MODULE_REL, REGISTRY_REL],
        "patch": patch,
    }


def build_bundle(packet: dict[str, Any], final: dict[str, Any], bundle_id: str) -> dict[str, Any]:
    built = build_patch(packet, final)
    bundle = dict(final)
    bundle["bundle_id"] = bundle_id
    bundle["raw_model_patch_ignored"] = bool(final.get("patch"))
    bundle["structured_patch_builder"] = {k: v for k, v in built.items() if k != "patch"}
    bundle["patch"] = built.get("patch")
    return bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build deterministic ESHA contract patch from Nebius JSON")
    parser.add_argument("--packet", required=True)
    parser.add_argument("--final", required=True)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--out")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    packet = json.loads(Path(args.packet).read_text(encoding="utf-8"))
    final = json.loads(Path(args.final).read_text(encoding="utf-8"))
    bundle = build_bundle(packet, final, args.bundle_id)
    if args.out:
        write_json(Path(args.out), bundle)
    else:
        print(json.dumps(bundle, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
