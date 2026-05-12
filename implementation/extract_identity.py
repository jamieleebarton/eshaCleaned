from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from identity_contract import esha_identity, product_identity, tokenize


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output" / "identity"
PRODUCTS_DB = ROOT / "data" / "master_products.db"
ESHA_CSV = ROOT / "esha_cleaned.csv"
FOODEX2_CSV = ROOT / "foodex2_terms.csv"

DEFAULT_PRODUCT_OUT = OUT_DIR / "product_identity_records.jsonl"
DEFAULT_ESHA_OUT = OUT_DIR / "esha_identity_records.jsonl"

TOKEN_RE = re.compile(r"[a-z][a-z0-9']*")

MODIFIER_WORDS = {
    "baby",
    "classic",
    "extra",
    "fresh",
    "jumbo",
    "large",
    "light",
    "medium",
    "mini",
    "natural",
    "organic",
    "original",
    "premium",
    "small",
    "whole",
}

PREP_STATE_WORDS = {
    "baked",
    "canned",
    "cooked",
    "dehydrated",
    "dried",
    "dry",
    "evaporated",
    "freeze",
    "frozen",
    "grilled",
    "raw",
    "roasted",
    "smoked",
    "steamed",
}

FAT_WORDS = {
    "fat free": "fat_free",
    "nonfat": "fat_free",
    "low fat": "low_fat",
    "reduced fat": "reduced_fat",
    "whole milk": "whole",
}

SWEET_WORDS = {
    "unsweetened": "unsweetened",
    "sweetened": "sweetened",
    "no sugar": "no_sugar",
    "sugar free": "sugar_free",
}


@dataclass(frozen=True)
class IdentityRecord:
    entity_type: str
    entity_id: str
    text: str
    category: str = ""
    brand: str = ""
    head_noun: str = ""
    form: str = ""
    modifiers: tuple[str, ...] = ()
    prep_state: str = ""
    sweetness: str = ""
    fat_level: str = ""
    foodex2_code: str = ""
    foodex2_name: str = ""
    confidence: float = 0.0
    extractor: str = ""
    notes: str = ""


def norm_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def norm_token(value: object) -> str:
    text = norm_text(value)
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return text


def split_words(value: object) -> tuple[str, ...]:
    return tuple(TOKEN_RE.findall(norm_text(value)))


def clean_head(value: object) -> str:
    text = norm_token(value)
    if text.endswith("ies") and len(text) > 4:
        text = text[:-3] + "y"
    elif text.endswith("es") and len(text) > 4:
        text = text[:-2]
    elif text.endswith("s") and len(text) > 3:
        text = text[:-1]
    return text


def load_foodex2_terms(path: Path) -> list[tuple[str, str, set[str]]]:
    if not path.exists():
        return []
    out: list[tuple[str, str, set[str]]] = []
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            code = str(row.get("termCode") or "").strip()
            name = str(row.get("termExtendedName") or "").strip()
            if not code or not name:
                continue
            terms = set(tokenize(name))
            out.append((code, name, terms))
    return out


def foodex_match(head_noun: str, form: str, foodex_terms: list[tuple[str, str, set[str]]]) -> tuple[str, str]:
    if not head_noun or not foodex_terms:
        return "", ""
    head_terms = set(split_words(head_noun))
    if form:
        head_terms.update(split_words(form))
    if not head_terms:
        return "", ""
    best: tuple[int, int, str, str] | None = None
    for code, name, terms in foodex_terms:
        overlap = head_terms & terms
        if not overlap:
            continue
        exact_bonus = 4 if norm_token(name).startswith(head_noun) else 0
        score = exact_bonus + len(overlap)
        width = len(terms)
        if best is None or (score, -width, code) > (best[0], -best[1], best[2]):
            best = (score, width, code, name)
    if not best:
        return "", ""
    return best[2], best[3]


def detect_prep_state(text: str) -> str:
    tokens = set(split_words(text))
    for state in ("dehydrated", "dried", "dry", "freeze", "frozen", "canned", "evaporated", "condensed", "raw", "roasted", "smoked", "cooked"):
        if state in tokens:
            return "freeze_dried" if state == "freeze" else state
    return ""


def detect_sweetness(text: str) -> str:
    lower = norm_text(text)
    for phrase, value in SWEET_WORDS.items():
        if phrase in lower:
            return value
    return ""


def detect_fat_level(text: str) -> str:
    lower = norm_text(text)
    for phrase, value in FAT_WORDS.items():
        if phrase in lower:
            return value
    return ""


def heuristic_identity(
    *,
    entity_type: str,
    entity_id: str,
    text: str,
    category: str = "",
    brand: str = "",
    ingredients: str = "",
    foodex_terms: list[tuple[str, str, set[str]]] | None = None,
) -> IdentityRecord:
    if entity_type == "esha":
        fact = esha_identity(text)
    else:
        fact = product_identity(
            product_description=text,
            category=category,
            ingredient_signature=" ".join(tokenize(ingredients)),
        )
    primary = sorted(fact.primary_terms)
    identity = sorted(fact.identity_terms)
    head = clean_head(primary[0] if primary else (identity[0] if identity else ""))
    if not head:
        first = str(text or "").split(",", 1)[0]
        head = clean_head(first)
    tokens = set(split_words(text)) | set(split_words(category))
    modifiers = tuple(sorted((tokens & MODIFIER_WORDS) - {head}))
    prep_state = detect_prep_state(f"{text} {category} {ingredients}") or ("dried" if fact.form == "dried_fruit" else "")
    foodex_code, foodex_name = foodex_match(head, fact.form, foodex_terms or [])
    confidence = 0.75 if head else 0.2
    return IdentityRecord(
        entity_type=entity_type,
        entity_id=str(entity_id),
        text=str(text or ""),
        category=str(category or ""),
        brand=str(brand or ""),
        head_noun=head,
        form=fact.form,
        modifiers=modifiers,
        prep_state=prep_state,
        sweetness=detect_sweetness(f"{text} {ingredients}"),
        fat_level=detect_fat_level(f"{text} {category}"),
        foodex2_code=foodex_code,
        foodex2_name=foodex_name,
        confidence=confidence,
        extractor="heuristic_identity_contract",
        notes="heuristic fallback; use LLM extraction for production gates",
    )


IDENTITY_SCHEMA = {
    "type": "object",
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "entity_type",
                    "entity_id",
                    "head_noun",
                    "form",
                    "modifiers",
                    "prep_state",
                    "sweetness",
                    "fat_level",
                    "foodex2_code",
                    "confidence",
                ],
                "properties": {
                    "entity_type": {"type": "string"},
                    "entity_id": {"type": "string"},
                    "head_noun": {"type": "string"},
                    "form": {"type": "string"},
                    "modifiers": {"type": "array", "items": {"type": "string"}},
                    "prep_state": {"type": "string"},
                    "sweetness": {"type": "string"},
                    "fat_level": {"type": "string"},
                    "foodex2_code": {"type": "string"},
                    "foodex2_name": {"type": "string"},
                    "confidence": {"type": "number"},
                    "notes": {"type": "string"},
                },
            },
        }
    },
}


def anthropic_extract(
    records: list[dict[str, str]],
    *,
    api_key: str,
    model: str,
    max_retries: int = 3,
) -> list[dict[str, object]]:
    prompt = (
        "Extract typed food identity records. Return JSON only with key 'items'. "
        "head_noun is the food identity, not size/brand/state. "
        "form is the product form such as milk, dressing, dried_fruit, jelly, cookie, sausage, produce, beverage. "
        "prep_state is a state like raw, fresh, dried, canned, frozen, evaporated, condensed, cooked, or empty. "
        "modifiers are meaningful subtype/flavor/form tokens. Do not put weak size words as head_noun. "
        "foodex2_code/name may be empty if uncertain. Input records:\n"
        + json.dumps(records, ensure_ascii=True)
    )
    body = {
        "model": model,
        "max_tokens": 6000,
        "temperature": 0,
        "system": "You are a food taxonomy extraction engine. Return valid JSON matching the requested schema.",
        "messages": [{"role": "user", "content": prompt}],
    }
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=data,
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = json.loads(response.read().decode("utf-8"))
            text = "".join(part.get("text", "") for part in payload.get("content", []) if part.get("type") == "text")
            parsed = json.loads(text)
            items = parsed.get("items", [])
            if not isinstance(items, list):
                raise ValueError("LLM JSON did not contain list key 'items'")
            return items
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            time.sleep(2**attempt)
    raise RuntimeError(f"Anthropic extraction failed after {max_retries} retries: {last_error}")


def load_esha_rows(path: Path, limit: int = 0) -> Iterable[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        for i, row in enumerate(csv.DictReader(handle), start=1):
            if limit and i > limit:
                break
            yield {
                "entity_type": "esha",
                "entity_id": str(row.get("EshaCode") or row.get("Code") or "").strip(),
                "text": str(row.get("Description") or "").strip(),
                "category": "",
                "brand": "",
                "ingredients": "",
            }


def load_product_rows(
    db_path: Path,
    *,
    limit: int = 0,
    category_like: str = "",
) -> Iterable[dict[str, str]]:
    sql = (
        "SELECT gtin_upc, fdc_id, description, brand_owner, brand_name, branded_food_category, ingredients "
        "FROM products"
    )
    params: list[object] = []
    if category_like:
        sql += " WHERE lower(branded_food_category) LIKE ?"
        params.append(f"%{category_like.lower()}%")
    sql += " ORDER BY gtin_upc"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    con = sqlite3.connect(db_path)
    try:
        for row in con.execute(sql, params):
            gtin, fdc_id, desc, brand_owner, brand_name, category, ingredients = row
            yield {
                "entity_type": "product",
                "entity_id": str(fdc_id or gtin or ""),
                "gtin_upc": str(gtin or ""),
                "text": str(desc or ""),
                "category": str(category or ""),
                "brand": str(brand_name or brand_owner or ""),
                "ingredients": str(ingredients or ""),
            }
    finally:
        con.close()


def coerce_llm_record(source: dict[str, str], item: dict[str, object], foodex_terms: list[tuple[str, str, set[str]]]) -> IdentityRecord:
    head = clean_head(item.get("head_noun", ""))
    foodex_code = str(item.get("foodex2_code") or "").strip()
    foodex_name = str(item.get("foodex2_name") or "").strip()
    if not foodex_code:
        foodex_code, foodex_name = foodex_match(head, str(item.get("form") or ""), foodex_terms)
    modifiers = item.get("modifiers") or []
    if not isinstance(modifiers, list):
        modifiers = []
    try:
        confidence = float(item.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return IdentityRecord(
        entity_type=source["entity_type"],
        entity_id=source["entity_id"],
        text=source["text"],
        category=source.get("category", ""),
        brand=source.get("brand", ""),
        head_noun=head,
        form=norm_token(item.get("form", "")),
        modifiers=tuple(sorted({norm_token(v) for v in modifiers if norm_token(v)})),
        prep_state=norm_token(item.get("prep_state", "")),
        sweetness=norm_token(item.get("sweetness", "")),
        fat_level=norm_token(item.get("fat_level", "")),
        foodex2_code=foodex_code,
        foodex2_name=foodex_name,
        confidence=confidence,
        extractor="anthropic",
        notes=str(item.get("notes") or ""),
    )


def write_jsonl(records: Iterable[IdentityRecord], out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record), sort_keys=True, ensure_ascii=True) + "\n")
            count += 1
    tmp.replace(out_path)
    return count


def extract_records(
    source_rows: list[dict[str, str]],
    *,
    mode: str,
    batch_size: int,
    model: str,
    foodex_terms: list[tuple[str, str, set[str]]],
) -> Iterable[IdentityRecord]:
    if mode == "heuristic":
        for row in source_rows:
            yield heuristic_identity(
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                text=row["text"],
                category=row.get("category", ""),
                brand=row.get("brand", ""),
                ingredients=row.get("ingredients", ""),
                foodex_terms=foodex_terms,
            )
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY is required for --mode anthropic")
    if not model:
        raise SystemExit("ANTHROPIC_MODEL or --model is required for --mode anthropic")
    for start in range(0, len(source_rows), batch_size):
        chunk = source_rows[start : start + batch_size]
        llm_items = anthropic_extract(chunk, api_key=api_key, model=model)
        by_id = {str(item.get("entity_id") or ""): item for item in llm_items if isinstance(item, dict)}
        for row in chunk:
            item = by_id.get(row["entity_id"])
            if item is None:
                yield heuristic_identity(
                    entity_type=row["entity_type"],
                    entity_id=row["entity_id"],
                    text=row["text"],
                    category=row.get("category", ""),
                    brand=row.get("brand", ""),
                    ingredients=row.get("ingredients", ""),
                    foodex_terms=foodex_terms,
                )
            else:
                yield coerce_llm_record(row, item, foodex_terms)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract cached typed identity records for products or ESHA rows.")
    parser.add_argument("entity", choices=("esha", "products"))
    parser.add_argument("--mode", choices=("heuristic", "anthropic"), default="heuristic")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--category-like", default="")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--model", default=os.environ.get("ANTHROPIC_MODEL", ""))
    parser.add_argument("--esha-csv", type=Path, default=ESHA_CSV)
    parser.add_argument("--products-db", type=Path, default=PRODUCTS_DB)
    parser.add_argument("--foodex2-csv", type=Path, default=FOODEX2_CSV)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    foodex_terms = load_foodex2_terms(args.foodex2_csv)
    if args.entity == "esha":
        rows = list(load_esha_rows(args.esha_csv, args.limit))
        out = args.out or DEFAULT_ESHA_OUT
    else:
        rows = list(load_product_rows(args.products_db, limit=args.limit, category_like=args.category_like))
        out = args.out or DEFAULT_PRODUCT_OUT

    records = extract_records(
        rows,
        mode=args.mode,
        batch_size=args.batch_size,
        model=args.model,
        foodex_terms=foodex_terms,
    )
    count = write_jsonl(records, out)
    print(json.dumps({"entity": args.entity, "mode": args.mode, "rows": count, "out": str(out)}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
