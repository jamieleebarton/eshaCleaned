"""Step 6 of GOAL.md: layer DeepSeek on the residual lines that the deterministic
calculator couldn't fully resolve.

INPUT: a calculator report (`run_recipe_cost_smoke.py --out-json X.json`) — one
       entry per recipe with per-line resolution + retailer candidates.
LOGIC:
  - Skip lines we don't shop for (water, parchment paper, wood chips, etc.).
  - Skip lines that are fully clean (canonical resolved + retail accepted +
    no range/or-option/generic-term in the recipe text).
  - For each remaining line, build a Packet from the calculator's output
    (recipe_text=line.input, parsed_item=line.canonical_name, grams=line.grams,
    walmart_candidates from line.walmart_options[:5],
    kroger_candidates from line.kroger_options[:5]).
  - Send to DeepSeek via the existing ruvs_verify.verify_line.
  - Aggregate verdicts -> fix_queue -> patches.
  - Emit suggested rows for canonical_aliases.csv and reviewed_recipe_line_patches.csv.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from ruvs.budget import Budget, BudgetExceeded
from ruvs.nebius import NebiusClient
from ruvs.schemas import Packet, ProductCandidate
from ruvs_verify import verify_line
from ruvs_verdicts import append_verdict, load_verdicts
from ruvs_fix_queue import build_fix_queue
from ruvs_patches import generate_patches


OUT_DIR = Path(__file__).parent / "output" / "ruvs" / "calculator_residual"

# Lines we do NOT shop for — skip without DeepSeek.
SKIP_CANONICALS = {"water", "ice", "tap water"}
SKIP_INPUT_PATTERNS = re.compile(
    r"\b(wood chips?|parchment|skewer|toothpick|aluminum foil|plastic wrap|cheese cloth|"
    r"butcher.?paper|cooking spray)\b", re.IGNORECASE,
)

# Ambiguity hints in the raw recipe text — only TRUE judgment-call cases get
# routed to DeepSeek. A line is sent only if:
#   (a) it has an actual gap (no canonical / shop_gap / nutrition_unknown), OR
#   (b) the recipe text has a numeric range (e.g. "6-8 peppers"), OR
#   (c) the recipe text has an or-option (e.g. "butter or margarine") that
#       looks ingredient-y (not a stylistic "salt or pepper to taste"), OR
#   (d) the canonical itself is one of the bare-generic terms (recipe says
#       just "cheese" with no qualifier).
RANGE_RE   = re.compile(r"\d+\s*[-–]\s*\d+")
# Match an "X or Y" where both X and Y look like ingredient nouns (3+ chars,
# alphabetic, not common stop words). Skip "to taste" style phrasing.
_OR_NOUN = r"[A-Za-z][A-Za-z\-]{2,}"
OR_OPTION_RE = re.compile(rf"\b{_OR_NOUN}(?:\s+{_OR_NOUN})?\s+or\s+{_OR_NOUN}(?:\s+{_OR_NOUN})?\b", re.IGNORECASE)
# Bare-generic canonicals — only the WHOLE canonical, not as a suffix.
GENERIC_CANONICALS = {
    "cheese", "sauce", "seasoning", "spice", "spices",
    "broth", "stock", "vinegar", "oil", "flour", "sugar",
    "rice", "pasta", "noodles", "noodle", "bread",
    "fish", "meat", "beans", "bean", "milk",
}


def _to_product_candidate(opt: dict, retail: str) -> ProductCandidate:
    return ProductCandidate(
        upc=str(opt.get("upc", "")),
        title=str(opt.get("name", "") or opt.get("walmart_name", "")),
        grams=float(opt.get("package_grams", 0) or 0),
        price_cents=int(round(float(opt.get("package_usd", 0) or 0) * 100)),
        retail=retail,
        raw={
            "decision_reason": opt.get("decision_reason", ""),
            "search_term": opt.get("search_term", ""),
            "checkout_usd": opt.get("checkout_usd"),
        },
    )


def _build_packet(recipe_id: int, recipe_name: str, line_idx: int, ln: dict) -> Packet:
    walmart = []
    for opt in (ln.get("walmart_options") or [])[:5]:
        walmart.append(_to_product_candidate(opt, "walmart"))
    if not walmart and ln.get("walmart"):
        walmart = [_to_product_candidate(ln["walmart"], "walmart")]
    kroger = []
    for opt in (ln.get("kroger_options") or [])[:5]:
        kroger.append(_to_product_candidate(opt, "kroger"))
    if not kroger and ln.get("kroger"):
        kroger = [_to_product_candidate(ln["kroger"], "kroger")]

    return Packet(
        recipe_id=recipe_id,
        line_idx=line_idx,
        config_bucket=f"recipe={recipe_id}|name={recipe_name[:40]}",
        recipe_text=str(ln.get("input", "")),
        parsed_item=str(ln.get("original_item") or ln.get("canonical_name") or "").lower(),
        recipe_grams=float(ln.get("grams") or 0),
        hestia_canonical=str(ln.get("normalized_shopping_item") or ln.get("canonical_name") or ""),
        audit_candidates=[],   # could be populated from full_corpus_audit; kept empty in v1 to start lean
        fndds_desc=str(ln.get("fndds_code") or ""),
        sr28_desc=str(ln.get("sr28_fdc_id") or ""),
        esha_desc=str(ln.get("esha_description") or ""),
        walmart_candidates=walmart,
        kroger_candidates=kroger,
        config={"recipe_name": recipe_name, "calculator_path": ln.get("path", [])},
    )


def _classify(ln: dict) -> str:
    """Return 'skip', 'verify', or 'verify_ambiguous'."""
    text = (ln.get("input") or "").strip()
    can = (ln.get("canonical_name") or "").strip().lower()
    ss = ln.get("shopping_state") or ""
    ns = ln.get("nutrition_state") or ""

    if can in SKIP_CANONICALS:
        return "skip"
    if SKIP_INPUT_PATTERNS.search(text):
        return "skip"

    has_gap = (
        not can                                 # unresolved canonical
        or ss == "shopping_gap"                 # no retail product picked
        or (ns == "nutrition_unknown" and not (ln.get("walmart") or ln.get("kroger")))
    )
    # Only flag ambiguity when there's a REAL signal — a numeric range, an
    # or-option, or the canonical itself is bare-generic. Don't flag clean
    # lines like "1 cup all-purpose flour" or "2 tablespoons vegetable oil".
    has_range = bool(RANGE_RE.search(text))
    has_or = bool(OR_OPTION_RE.search(text))
    is_bare_generic = can in GENERIC_CANONICALS
    has_ambiguity = has_range or has_or or is_bare_generic
    if has_gap:
        return "verify"
    if has_ambiguity:
        return "verify_ambiguous"
    return "skip"


def _derive_aliases(verdicts: list, calc_lines: list) -> list[dict]:
    """Suggest canonical_aliases.csv rows from `audit_correction` patches that
    propose a canonical change for an unresolved line."""
    out: list[dict] = []
    by_key = {(int(v.recipe_id), int(v.line_idx)): v for v in verdicts}
    for ln_info in calc_lines:
        v = by_key.get((ln_info["recipe_id"], ln_info["line_idx"]))
        if not v: continue
        fix = v.fix_proposed or {}
        if fix.get("patch_type") in ("audit_correction", "alias", "recipe_text_edit"):
            delta = fix.get("delta") or {}
            out.append({
                "recipe_id": ln_info["recipe_id"],
                "recipe_name": ln_info["recipe_name"],
                "from_text": ln_info["input"],
                "patch_type": fix.get("patch_type"),
                "to_canonical": fix.get("canonical") or delta.get("suggested_canonical_label", ""),
                "suggested_text": delta.get("suggested_text", ""),
                "reason": delta.get("reason", ""),
            })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="input_json", required=True,
                    help="calc report (e.g. /tmp/calc_plan13.json)")
    ap.add_argument("--budget-usd", type=float, default=1.00)
    ap.add_argument("--max-lines", type=int, default=0)
    args = ap.parse_args()

    api_key = os.environ.get("NEBIUS_API_KEY")
    if not api_key:
        print(json.dumps({"error": "NEBIUS_API_KEY required"})); return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    verdict_path = OUT_DIR / "verdicts.jsonl"
    queue_path = OUT_DIR / "fix_queue.csv"
    patches_dir = OUT_DIR / "patches"
    aliases_path = OUT_DIR / "suggested_canonical_aliases.csv"
    line_patches_path = OUT_DIR / "suggested_reviewed_recipe_line_patches.csv"
    summary_path = OUT_DIR / "summary.md"
    for p in (verdict_path, queue_path, aliases_path, line_patches_path, summary_path):
        if p.exists(): p.unlink()
    if patches_dir.exists():
        for sub in patches_dir.iterdir():
            if sub.is_dir():
                for f in sub.iterdir(): f.unlink()
            else:
                sub.unlink()

    calc = json.loads(Path(args.input_json).read_text())
    print(f"calculator report: {len(calc.get('recipes', []))} recipes", file=sys.stderr)

    budget = Budget(cap_usd=args.budget_usd)
    client = NebiusClient(api_key=api_key)

    started = time.time()
    n_skip = n_verify = n_clean = n_dirty = 0
    verdicts_seen: list = []
    line_index: list[dict] = []

    for r in calc.get("recipes", []):
        rid = int(r["recipe_num"])
        rname = r["recipe_name"]
        for line_idx, ln in enumerate(r["lines"]):
            classify = _classify(ln)
            if classify == "skip":
                n_skip += 1
                continue
            if args.max_lines and n_verify >= args.max_lines:
                continue
            packet = _build_packet(rid, rname, line_idx, ln)
            try:
                v = verify_line(packet=packet, client=client, run_id="calc_residual.h4w1")
            except BudgetExceeded as e:
                print(f"BUDGET EXCEEDED at {n_verify} lines: {e}", file=sys.stderr)
                break
            cost = float(v.evidence.get("cost_usd") or 0.0)
            try:
                budget.add(cost)
            except BudgetExceeded as e:
                print(f"BUDGET EXCEEDED on cost add: {e}", file=sys.stderr)
                break
            append_verdict(v, verdict_path)
            verdicts_seen.append(v)
            line_index.append({
                "recipe_id": rid, "line_idx": line_idx, "recipe_name": rname,
                "input": ln.get("input", ""), "classify": classify,
            })
            n_verify += 1
            if v.is_clean(): n_clean += 1
            else: n_dirty += 1
            print(f"  [{classify}] r{rid}:l{line_idx} {ln.get('input','')[:50]!r:<52.52} "
                  f"-> facets={','.join(k+'=' +v_ for k, v_ in v.facets.items() if v_ not in {'ok','none','n/a'}) or 'all clean'}",
                  file=sys.stderr)

    # Build fix_queue + patches via existing pipeline
    build_fix_queue(verdicts_seen, queue_path)
    # mark all rows approved by our automated reviewer if patch type is wishlist/portion (low-risk);
    # leave audit_correction / recipe_text_edit pending so a human eyeballs them
    import csv
    if queue_path.exists():
        rows = list(csv.DictReader(queue_path.open()))
        headers = list(rows[0].keys()) if rows else []
        for r in rows:
            if r["proposed_patch_type"] in ("wishlist", "portion"):
                r["review_status"] = "approved"
        if rows:
            with queue_path.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=headers); w.writeheader(); w.writerows(rows)
    generate_patches(queue_path, patches_dir)

    # Emit candidate edits for human review
    suggestions = _derive_aliases(verdicts_seen, line_index)
    with aliases_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["recipe_id","recipe_name","from_text","patch_type","to_canonical","suggested_text","reason"])
        w.writeheader(); w.writerows(suggestions)

    # Reviewed recipe-line patch suggestions (recipe-specific overrides)
    review_rows = [
        {
            "recipe_id": s["recipe_id"], "ingredient_text": s["from_text"],
            "override_canonical": s["to_canonical"],
            "rationale": s["reason"] or s["suggested_text"],
        }
        for s in suggestions
        if s["patch_type"] in ("recipe_text_edit", "audit_correction")
    ]
    with line_patches_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["recipe_id","ingredient_text","override_canonical","rationale"])
        w.writeheader(); w.writerows(review_rows)

    summary = {
        "lines_total": sum(r["line_count"] for r in calc.get("recipes", [])),
        "lines_skipped_non_purchase_or_clean": n_skip,
        "lines_verified": n_verify,
        "lines_clean": n_clean,
        "lines_dirty": n_dirty,
        "spent_usd": round(budget.spent_usd, 4),
        "elapsed_s": round(time.time() - started, 1),
        "fix_queue": str(queue_path),
        "patches_dir": str(patches_dir),
        "suggested_aliases": str(aliases_path),
        "suggested_recipe_line_patches": str(line_patches_path),
    }
    summary_path.write_text(
        "# RUVS calculator-residual run\n\n"
        + "\n".join(f"- **{k}:** {v}" for k, v in summary.items()) + "\n"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
