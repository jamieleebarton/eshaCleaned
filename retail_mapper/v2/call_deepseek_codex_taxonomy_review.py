#!/usr/bin/env python3
"""Send Codex taxonomy review packets to DeepSeek.

Reads `codex_deepseek_taxonomy_review_queue.jsonl` and writes
`codex_deepseek_taxonomy_review_decisions.jsonl`.

DeepSeek is an adjudicator only. It does not rewrite any corpus file. The
output is reviewed and converted into deterministic finalizer rules + tests.

Requires:
    export DEEPSEEK_API_KEY=sk-...

Usage:
    python3 retail_mapper/v2/call_deepseek_codex_taxonomy_review.py --limit 50
    python3 retail_mapper/v2/call_deepseek_codex_taxonomy_review.py --resume --workers 8
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import certifi

    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()


REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
DEFAULT_SRC = V2 / "codex_deepseek_taxonomy_review_queue.jsonl"
DEFAULT_OUT = V2 / "codex_deepseek_taxonomy_review_decisions.jsonl"
DEFAULT_LOG = V2 / "codex_deepseek_taxonomy_review_log.txt"

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"

SYSTEM_PROMPT = """You are a strict grocery retail taxonomy adjudicator.

Your job: decide whether ONE SKU's current retail taxonomy is correct.

Use evidence in this order:
1. SKU title and ingredients
2. branded_food_category and brand/package context
3. reference matches (FNDDS/SR28/ESHA/matched_key), which may be stale or wrong
4. BFC context/outlier context as a prior, never as absolute truth

Taxonomy contract:
- category_path_fixed is the shelf/family path only.
- product_identity_fixed is the product type only.
- canonical_path = category_path_fixed + product_identity_fixed, except when
  the identity is already represented by the shelf.
- flavor, shape, cut, form, claim, marketing line, and package size belong in
  modifier, not in category_path_fixed or product_identity_fixed.
- Do not create duplicate path segments.
- Do not route prepared foods to ingredient carriers: turkey sub on a bun is
  Meal > Sandwiches, not Bakery > Buns.
- Do not route flavor references as product type: cinnamon churro coffee
  creamer is a beverage/dairy creamer, not Bakery > Churros.
- Keep true flavor-only bakery products in Bakery when evidence says the
  product is a cookie/toaster pastry/cake, not frozen dessert.

Return STRICT JSON only, no markdown:
{
  "verdict": "correct" | "wrong" | "ambiguous",
  "product_type": "<plain product type, e.g. Ice Cream Bar, Taco Shells>",
  "proposed_category_path": "<category shelf only, blank if verdict=correct>",
  "proposed_product_identity": "<identity only, blank if verdict=correct>",
  "proposed_modifier_policy": "keep_existing" | "move_flavor_to_modifier" | "drop_noise" | "manual_review",
  "reason_code": "bfc_path_wrong" | "title_path_wrong" | "reference_match_wrong" | "bfc_noisy" | "flavor_only" | "contradictory_evidence" | "other",
  "rule_candidate": true | false,
  "rule_pattern": "<short reusable deterministic rule, or blank>",
  "nearby_false_positive_risk": "low" | "medium" | "high",
  "confidence": <0.0-1.0>,
  "rationale": "<one concise sentence>"
}

Use "ambiguous" when title, ingredients, BFC, and references materially
disagree. Do not force a confident fix from contradictory evidence."""

REQUIRED_KEYS = {
    "verdict",
    "product_type",
    "proposed_category_path",
    "proposed_product_identity",
    "proposed_modifier_policy",
    "reason_code",
    "rule_candidate",
    "rule_pattern",
    "nearby_false_positive_risk",
    "confidence",
    "rationale",
}


def compact_case(case: dict[str, Any]) -> dict[str, Any]:
    """Keep the prompt evidence dense and stable."""
    return {
        "fdc_id": case.get("fdc_id", ""),
        "title": case.get("title", ""),
        "branded_food_category": case.get("branded_food_category", ""),
        "brand_name": case.get("brand_name", ""),
        "brand_owner": case.get("brand_owner", ""),
        "ingredients": case.get("ingredients", ""),
        "package_weight": case.get("package_weight", ""),
        "serving_size": case.get("serving_size", ""),
        "serving_size_unit": case.get("serving_size_unit", ""),
        "current_taxonomy": case.get("current_taxonomy", {}),
        "reference_matches": case.get("reference_matches", {}),
        "bfc_context": case.get("bfc_context", {}),
        "outlier_context": case.get("outlier_context", {}),
        "reason_codes": case.get("reason_codes", []),
        "priority_score": case.get("priority_score", 0),
    }


def parse_json_object(raw: str) -> dict[str, Any]:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        raw = re.sub(r"^json\s*", "", raw, flags=re.I)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def validate_decision(decision: dict[str, Any]) -> dict[str, Any]:
    missing = sorted(REQUIRED_KEYS - set(decision))
    if missing:
        decision["_schema_error"] = f"missing keys: {', '.join(missing)}"
    verdict = decision.get("verdict")
    if verdict not in {"correct", "wrong", "ambiguous"}:
        decision["_schema_error"] = f"bad verdict: {verdict!r}"
    try:
        confidence = float(decision.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
        decision["_schema_error"] = "confidence is not numeric"
    decision["confidence"] = max(0.0, min(1.0, confidence))
    return decision


def call_deepseek(
    *,
    api_key: str,
    base_url: str,
    model: str,
    case: dict[str, Any],
    timeout_s: int,
    max_tokens: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    url = base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(compact_case(case), ensure_ascii=False, sort_keys=True)},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout_s, context=SSL_CONTEXT) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    raw = payload["choices"][0]["message"]["content"]
    usage = payload.get("usage", {})
    return validate_decision(parse_json_object(raw)), usage


def load_cases(path: Path, *, start: int, limit: int) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                cases.append(json.loads(line))
    if start:
        cases = cases[start:]
    if limit:
        cases = cases[:limit]
    return cases


def load_done(path: Path) -> set[str]:
    done: set[str] = set()
    if not path.exists():
        return done
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            fdc = rec.get("fdc_id")
            if fdc:
                done.add(str(fdc))
    return done


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout-s", type=int, default=180)
    parser.add_argument("--max-tokens", type=int, default=1200)
    args = parser.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY not set")
    if not args.src.exists():
        raise SystemExit(f"missing {args.src}; run build_codex_deepseek_taxonomy_queue.py first")

    cases = load_cases(args.src, start=args.start, limit=args.limit)
    done = load_done(args.out) if args.resume else set()
    pending = [case for case in cases if str(case.get("fdc_id", "")) not in done]
    print(f"pending={len(pending):,} total_loaded={len(cases):,} resume_done={len(done):,}")

    out_mode = "a" if args.resume else "w"
    log_mode = "a" if args.resume else "w"
    lock = threading.Lock()
    out_fh = args.out.open(out_mode, encoding="utf-8")
    log_fh = args.log.open(log_mode, encoding="utf-8")
    t0 = time.time()
    usage_totals: Counter[str] = Counter()

    def process(case: dict[str, Any]) -> bool:
        fdc = str(case.get("fdc_id", ""))
        try:
            decision, usage = call_deepseek(
                api_key=api_key,
                base_url=args.base_url,
                model=args.model,
                case=case,
                timeout_s=args.timeout_s,
                max_tokens=args.max_tokens,
            )
            record = {
                "fdc_id": fdc,
                "title": case.get("title", ""),
                "branded_food_category": case.get("branded_food_category", ""),
                "current_taxonomy": case.get("current_taxonomy", {}),
                "reason_codes": case.get("reason_codes", []),
                "priority_score": case.get("priority_score", 0),
                "decision": decision,
                "usage": usage,
                "model": args.model,
            }
            with lock:
                out_fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                out_fh.flush()
                for key, value in (usage or {}).items():
                    if isinstance(value, int):
                        usage_totals[key] += value
                log_fh.write(
                    f"OK {fdc} verdict={decision.get('verdict')} "
                    f"conf={decision.get('confidence')} reason={decision.get('reason_code')}\n"
                )
                log_fh.flush()
            return True
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError) as exc:
            detail = str(exc)
            if isinstance(exc, urllib.error.HTTPError):
                try:
                    detail = exc.read().decode("utf-8", errors="replace")[:500]
                except Exception:
                    detail = str(exc)
            with lock:
                log_fh.write(f"ERR {fdc}: {type(exc).__name__}: {detail}\n")
                log_fh.flush()
            return False

    ok = err = done_count = 0
    try:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = [executor.submit(process, case) for case in pending]
            for future in as_completed(futures):
                done_count += 1
                if future.result():
                    ok += 1
                else:
                    err += 1
                if done_count % 25 == 0 or done_count == len(pending):
                    elapsed = max(time.time() - t0, 0.001)
                    rate = done_count / elapsed
                    remaining = len(pending) - done_count
                    eta_min = remaining / rate / 60 if rate else 0
                    print(
                        f"[{done_count}/{len(pending)}] ok={ok} err={err} "
                        f"rate={rate:.2f}/s eta={eta_min:.1f}m",
                        flush=True,
                    )
    finally:
        out_fh.close()
        log_fh.close()

    print(json.dumps({
        "ok": ok,
        "err": err,
        "out": str(args.out),
        "log": str(args.log),
        "usage_totals": dict(usage_totals),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
