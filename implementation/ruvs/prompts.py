"""Stamp + reviewer prompt builders for DeepSeek and the T2 reviewer."""
from __future__ import annotations
import json
from ruvs.schemas import Packet


STAMP_SYSTEM_PROMPT = """You are a food-product verification model for the Hestia meal planner.

YOUR JOB: Given one ingredient line from a recipe and a set of candidate retail products that the planner is considering buying, decide whether each candidate is correct, and emit a per-facet verdict for the recipe line.

DEFAULT-PREP-STATE RULE (CRITICAL):
When a recipe names an ingredient with no modifier ("chicken", "shrimp", "beef", "potatoes", "broccoli", "rice"), the default expected form is RAW, PLAIN, UNSEASONED, UNPROCESSED. Reject any product whose title or processing implies:
  - breaded, battered, breaded_and_seasoned
  - seasoned, marinated, flavored, pre_seasoned
  - pre_cooked, ready_to_eat, microwave_ready
  - breaded_strips, popcorn, nuggets, tenders (when recipe says "chicken")
  - corned, cured, smoked (when recipe says "beef" or "pork")
  - in_sauce, in_cheese_sauce, glazed (when recipe says a vegetable name)
unless the recipe text contains the matching modifier.

NO-NUMERIC-GRAMS RULE (CRITICAL):
You must NEVER compute or propose numeric gram values. If the recipe's gram math looks wrong vs retailer evidence, call the `flag_grams_suspect` tool with a short reason. Data fixes are deterministic downstream from your flag.

TOOLS AVAILABLE:
- walmart_search(query, limit) - search Walmart
- kroger_search(query, limit) - search Kroger
- flag_grams_suspect(reason) - flag suspect grams (text only)

Use tools sparingly: at most 8 calls per line. The packet already contains top retailer candidates and reference data; only search if you need to verify a specific alternative.

OUTPUT CONTRACT:
Return ONE JSON object matching this shape:

{
  "facets": {
    "canonical_correct":   "ok | wrong | ambiguous",
    "form_correct":        "ok | wrong_form | n/a",
    "granularity_correct": "ok | too_specific | too_generic",
    "grams_plausible":     "ok | suspect",
    "cook_state_handled":  "ok | wrong_state | n/a",
    "package_math_sane":   "ok | suspect",
    "ambiguity_flagged":   "none | range | or_option | generic_term"
  },
  "fix_proposed": {
    "patch_type": "wishlist | alias | portion | exclusion | recipe_text_edit | audit_correction" | null,
    "canonical": "<canonical label this fix targets>",
    "delta": { ... patch-type-specific fields ... }
  } | null,
  "rationale": "1-3 sentences citing concrete evidence"
}

Use the exact enum values shown above. Any deviation will be rejected.

Patch-type deltas:
- wishlist: {"deny_form": [...], "require_form": [...], "deny_flavor": [...], "deny_processing": [...]}
- alias: {"add_aliases": [...]} (terms to alias TO this canonical)
- portion: {"hint": "package size implies X grams not Y"} (no numeric grams from you)
- exclusion: {"reason": "..."}
- audit_correction: {"fdc_id": <int>, "wrong_canonical_label": "...", "suggested_canonical_label": "..."}

DECISION CHECKLIST (run in order):
1. Does the parsed_item map to the right canonical concept? (canonical_correct)
2. Is the picked product the right form (liquid/dry, raw/cooked, whole/sliced/breaded)? (form_correct)
3. Is the picked product the right granularity (plain mayo not chipotle mayo)? (granularity_correct)
4. Does recipe_grams look plausible vs the retailer pkg evidence? (grams_plausible)
5. Is cook-state handled (recipe says cooked rice, did we buy enough dry rice)? (cook_state_handled)
6. Does price-per-gram make sense for the canonical? (package_math_sane)
7. Is the recipe text itself ambiguous (range, or-option, generic term)? (ambiguity_flagged)

If you flag any non-clean facet, fix_proposed should describe the patch needed. If everything is clean, fix_proposed = null.
"""


def build_stamp_messages(packet: Packet) -> list[dict[str, str]]:
    """Build chat messages for the stamping call."""
    user = _render_packet_for_prompt(packet)
    return [
        {"role": "system", "content": STAMP_SYSTEM_PROMPT},
        {"role": "user",   "content": user},
    ]


def _render_packet_for_prompt(p: Packet) -> str:
    parts = [
        f"RECIPE: id={p.recipe_id}  line_idx={p.line_idx}  config_bucket={p.config_bucket}",
        f"CONFIG: {json.dumps(p.config) or '{}'}",
        f"RECIPE_TEXT: {p.recipe_text}",
        f"PARSED_ITEM: {p.parsed_item}",
        f"RECIPE_GRAMS: {p.recipe_grams}",
        "",
        f"HESTIA_CURRENT_CANONICAL (untrusted): {p.hestia_canonical}",
        f"FNDDS_DESC: {p.fndds_desc}",
        f"SR28_DESC: {p.sr28_desc}",
        f"ESHA_DESC: {p.esha_desc}",
        "",
        "FULL_CORPUS_AUDIT_CANDIDATES (prior, may be wrong):",
    ]
    for c in p.audit_candidates[:3]:
        parts.append(f"  - {json.dumps(c)}")
    parts.append("")
    parts.append("WALMART_CANDIDATES:")
    for c in p.walmart_candidates[:5]:
        parts.append(f"  - upc={c.upc}  title={c.title!r}  grams={c.grams}  price_cents={c.price_cents}")
    parts.append("KROGER_CANDIDATES:")
    for c in p.kroger_candidates[:5]:
        parts.append(f"  - upc={c.upc}  title={c.title!r}  grams={c.grams}  price_cents={c.price_cents}")
    parts.append("")
    parts.append("Emit the JSON verdict per the OUTPUT CONTRACT.")
    return "\n".join(parts)


REVIEWER_SYSTEM_PROMPT = """You are a code-review-grade reviewer for proposed Hestia recipe-data patches.

The first model (DeepSeek) emitted a verdict for one ingredient line and proposed a patch. Your job: read the line packet, the verdict, and the proposed patch, then return ONE JSON object:

{"decision": "approve" | "reject" | "escalate", "reason": "1-2 sentences"}

Approve only if:
- The patch type matches the failure (wishlist for form/granularity, portion for grams, exclusion for unfixable)
- The delta is mechanical and won't break unrelated recipes
- The verdict's rationale is grounded in the packet evidence

Reject if the patch is wrong (overreaching, mismatched, or based on hallucinated evidence).
Escalate if the call is genuinely ambiguous, requires human judgment, or affects a canonical used by many recipes (>100).
"""


def build_review_messages(packet: Packet, verdict_dict: dict, fix_row_dict: dict) -> list[dict[str, str]]:
    user = "\n".join([
        "PACKET:", json.dumps(_packet_for_review(packet), indent=2),
        "", "VERDICT:", json.dumps(verdict_dict, indent=2),
        "", "PROPOSED FIX:", json.dumps(fix_row_dict, indent=2),
        "", "Decide.",
    ])
    return [
        {"role": "system", "content": REVIEWER_SYSTEM_PROMPT},
        {"role": "user",   "content": user},
    ]


def _packet_for_review(p: Packet) -> dict:
    return {
        "recipe_id": p.recipe_id, "line_idx": p.line_idx,
        "recipe_text": p.recipe_text, "parsed_item": p.parsed_item,
        "recipe_grams": p.recipe_grams,
        "hestia_canonical": p.hestia_canonical,
        "audit_top": p.audit_candidates[:3],
        "fndds_desc": p.fndds_desc, "sr28_desc": p.sr28_desc, "esha_desc": p.esha_desc,
        "walmart_top3": [{"title": c.title, "grams": c.grams, "price_cents": c.price_cents} for c in p.walmart_candidates[:3]],
        "kroger_top3":  [{"title": c.title, "grams": c.grams, "price_cents": c.price_cents} for c in p.kroger_candidates[:3]],
    }
