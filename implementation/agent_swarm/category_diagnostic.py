"""
Category diagnostic tool for the RFT product-map cleanup swarm.

For a single branded_food_category, this script:
  1. Loads all products in that category
  2. Loads all ESHA codes/descriptions from the canonical surface file
  3. Finds products where the current assignment is "generic" but a "specific"
     ESHA code exists that better matches the product description
  4. Detects phrase-tokenization mismatches (e.g. "apple sauce" vs "applesauce")
  5. Outputs a CSV report with proposed fixes

Usage:
    python3 category_diagnostic.py "Wholesome Snacks"
"""

from __future__ import annotations

import csv
import sys
import re
from collections import defaultdict, Counter
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
PRODUCT_MAP = ROOT / "implementation/output/product_to_best_esha_full_map.vIdentity.csv"
CANONICAL_SURFACE = ROOT / "implementation/output/canonical_surface_normalized_with_product_proxies_CLEANED.csv"
OUT_DIR = ROOT / "implementation/agent_swarm/reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)

WORD = re.compile(r"[a-z][a-z0-9'%-]*")

def tokens(s: str) -> list[str]:
    return WORD.findall(s.lower())


def load_esha_index() -> dict[str, set[str]]:
    """Map ESHA code -> set of description tokens."""
    idx: dict[str, set[str]] = {}
    with open(CANONICAL_SURFACE, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            code = r.get("esha_code", "").strip()
            desc = r.get("esha_description", "").strip().lower()
            if code and desc:
                idx[code] = set(tokens(desc))
    return idx


def load_esha_desc_index() -> dict[str, str]:
    """Map ESHA code -> best description."""
    idx: dict[str, str] = {}
    with open(CANONICAL_SURFACE, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            code = r.get("esha_code", "").strip()
            desc = r.get("esha_description", "").strip()
            if code and desc:
                # Prefer shorter, more canonical descriptions
                if code not in idx or len(desc) < len(idx[code]):
                    idx[code] = desc
    return idx


def find_phrase_aliases(esha_desc_index: dict[str, str]) -> dict[str, str]:
    """
    Discover two-word phrases in product descriptions that have a single-word
    equivalent in ESHA descriptions.  E.g. 'apple sauce' -> 'applesauce'.
    Returns a mapping of lower-case phrase -> canonical token.
    """
    # Build set of single-word ESHA identity tokens
    esha_single_tokens: set[str] = set()
    for desc in esha_desc_index.values():
        toks = tokens(desc)
        if len(toks) == 1:
            esha_single_tokens.add(toks[0])

    # Count two-word phrases in product descriptions
    phrase_counts: Counter = Counter()
    with open(PRODUCT_MAP, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            desc = r.get("product_description", "").lower()
            toks = tokens(desc)
            for i in range(len(toks) - 1):
                phrase = f"{toks[i]} {toks[i+1]}"
                phrase_counts[phrase] += 1

    aliases: dict[str, str] = {}
    for phrase, count in phrase_counts.most_common():
        combined = phrase.replace(" ", "")
        if combined in esha_single_tokens and count >= 3:
            aliases[phrase] = combined
    return aliases


def tokenize_with_phrases(text: str, phrase_aliases: dict[str, str]) -> list[str]:
    """Tokenize text, collapsing known phrases first."""
    text = text.lower()
    for phrase, replacement in phrase_aliases.items():
        text = text.replace(phrase, replacement)
    return tokens(text)


def diagnose_category(category: str, esha_index: dict[str, set[str]],
                        esha_desc_index: dict[str, str],
                        phrase_aliases: dict[str, str]) -> list[dict]:
    """Return list of misassignment records for the category."""
    findings: list[dict] = []

    # Build reverse index: token -> set of ESHA codes
    token_to_codes: dict[str, set[str]] = defaultdict(set)
    for code, toks in esha_index.items():
        for t in toks:
            token_to_codes[t].add(code)

    with open(PRODUCT_MAP, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            if r.get("branded_food_category", "").strip() != category:
                continue

            desc = r.get("product_description", "").strip()
            if not desc:
                continue

            current_code = r.get("best_esha_code", "").strip()
            current_desc = r.get("best_esha_description", "").strip()
            verdict = r.get("rft_verdict", "").strip()

            # Tokenize product description with phrase aliases
            prod_toks = set(tokenize_with_phrases(desc, phrase_aliases))

            # Find candidate ESHA codes that share tokens
            code_scores: Counter = Counter()
            for t in prod_toks:
                for code in token_to_codes.get(t, []):
                    code_scores[code] += 1

            if not code_scores:
                continue

            # Normalize by ESHA token count (Jaccard-ish)
            ranked = []
            for code, shared in code_scores.most_common(50):
                esha_toks = esha_index.get(code, set())
                if not esha_toks:
                    continue
                # Coverage: what fraction of product tokens are covered?
                cov = len(prod_toks & esha_toks) / max(1, len(prod_toks))
                # Specificity: how many extra ESHA tokens?
                extra = len(esha_toks - prod_toks)
                # Prefer high coverage, low extra
                ranked.append((code, cov, extra, shared, esha_toks))

            # Sort: highest coverage, then fewest extras
            ranked.sort(key=lambda x: (-x[1], x[2], -x[3]))

            if not ranked:
                continue

            best_code, best_cov, best_extra, best_shared, best_toks = ranked[0]

            # Skip if current assignment is already the best
            if current_code == best_code:
                continue

            # Skip if best coverage is too low
            if best_cov < 0.5:
                continue

            # Heuristic: current is "generic" if its ESHA tokens are a strict
            # subset of the best candidate's tokens.
            current_toks = esha_index.get(current_code, set())
            is_generic_upgrade = (
                current_toks
                and current_toks < best_toks
                and len(best_toks - current_toks) >= 1
            )

            # Also flag phrase-alias mismatches even without subset relation
            phrase_mismatch = False
            for phrase, replacement in phrase_aliases.items():
                if phrase in desc.lower():
                    # If the product contains the two-word phrase but the
                    # current ESHA description uses the single-word form,
                    # and the best candidate uses the single-word form.
                    if replacement in best_toks and replacement not in current_toks:
                        phrase_mismatch = True
                        break

            if not is_generic_upgrade and not phrase_mismatch:
                continue

            best_desc = esha_desc_index.get(best_code, "")
            findings.append({
                "gtin_upc": r.get("gtin_upc", ""),
                "fdc_id": r.get("fdc_id", ""),
                "product_description": desc,
                "current_esha_code": current_code,
                "current_esha_desc": current_desc,
                "current_verdict": verdict,
                "proposed_esha_code": best_code,
                "proposed_esha_desc": best_desc,
                "coverage": round(best_cov, 3),
                "shared_tokens": "|".join(sorted(prod_toks & best_toks)),
                "missing_tokens": "|".join(sorted(prod_toks - best_toks)),
                "extra_tokens": "|".join(sorted(best_toks - prod_toks)),
                "fix_reason": "phrase_alias" if phrase_mismatch else "generic_to_specific",
            })

    return findings


def main():
    category = sys.argv[1] if len(sys.argv) > 1 else "Wholesome Snacks"

    print(f"Loading ESHA index...")
    esha_index = load_esha_index()
    esha_desc_index = load_esha_desc_index()
    print(f"  {len(esha_index):,} ESHA codes")

    print(f"Discovering phrase aliases...")
    phrase_aliases = find_phrase_aliases(esha_desc_index)
    print(f"  {len(phrase_aliases)} phrase aliases found")
    for phrase, canon in list(phrase_aliases.items())[:10]:
        print(f"    '{phrase}' -> '{canon}'")

    print(f"\nDiagnosing category: {category}")
    findings = diagnose_category(category, esha_index, esha_desc_index, phrase_aliases)
    print(f"  {len(findings)} potential fixes found")

    out_path = OUT_DIR / f"{category.replace('/', '_').replace(' ', '_')}.csv"
    with open(out_path, "w", newline="") as f:
        if findings:
            writer = csv.DictWriter(f, fieldnames=list(findings[0].keys()))
            writer.writeheader()
            writer.writerows(findings)
    print(f"  Report written to: {out_path}")


if __name__ == "__main__":
    main()
