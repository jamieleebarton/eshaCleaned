"""
Clean up the canonical_surface CSV using the concept router.

For each row, run the concept router and decide per-source what to write
into the canonical sr28_code / fndds_code / esha_code columns:

  RFT verdict EXACT / STRONG:
      use RFT codes (own or inherited along the identity leg)
  RFT verdict WEAK:
      keep original code if present; else fill from RFT (flag review)
  RFT verdict NEEDS_NEW_CONCEPT / NO_MATCH / NO_IDENTITY:
      keep original — RFT can't help

Original codes are preserved in `<src>_original_code` columns for audit.
A `<src>_change_reason` column explains every replacement.

Default I/O:
  in : implementation/output/canonical_surface_normalized_with_product_proxies.csv
  out: implementation/output/canonical_surface_normalized_with_product_proxies_CLEANED.csv
"""

from __future__ import annotations

import csv
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rft_concept import build_concept_index, build_token_to_concepts, route

csv.field_size_limit(sys.maxsize)

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
# Working file: the CLEANED canonical lives in the bundle output dir and
# we re-clean it in place each pass. The script preserves _original_code
# columns from prior passes so the audit trail keeps the truly-original
# source codes, not the previous cleanup's output.
DEFAULT_IN = ROOT / "implementation" / "output" / "canonical_surface_normalized_with_product_proxies_CLEANED.csv"
DEFAULT_OUT = DEFAULT_IN

TOKEN_RE = re.compile(r"[a-z0-9]+")


def _load_description_maps() -> dict[str, dict[str, str]]:
    maps: dict[str, dict[str, str]] = {"esha": {}, "fndds": {}, "sr28": {}}
    esha_path = ROOT / "esha_cleaned.csv"
    if esha_path.exists():
        with esha_path.open(newline="", encoding="utf-8", errors="replace") as handle:
            for row in csv.DictReader(handle):
                code = (row.get("EshaCode") or "").strip()
                desc = (row.get("Description") or "").strip()
                if code and desc:
                    maps["esha"][code] = desc

    fndds_path = ROOT / "data" / "fndds" / "MainFoodDesc16.csv"
    if fndds_path.exists():
        with fndds_path.open(newline="", encoding="utf-8", errors="replace") as handle:
            for row in csv.DictReader(handle):
                code = (row.get("Food code") or "").strip()
                desc = (row.get("Main food description") or "").strip()
                if code and desc:
                    maps["fndds"][code] = desc
    return maps


def _milk_subtype_signature(text: str) -> set[str]:
    norm = (text or "").lower().replace("-", " ")
    tokens = set(TOKEN_RE.findall(norm))
    sig: set[str] = set()
    if not ("milk" in tokens or any(tok.endswith("milk") for tok in tokens)):
        return sig
    if re.search(r"\b1\s*%|\b1\s*percent\b", norm):
        sig.add("one_percent")
    if re.search(r"\b2\s*%|\b2\s*percent\b", norm):
        sig.add("two_percent")
    if "lowfat" in tokens or {"low", "fat"} <= tokens:
        sig.add("one_percent")
    if "reduced" in tokens and "fat" in tokens:
        sig.add("two_percent")
    if "skim" in tokens or "nonfat" in tokens or {"fat", "free"} <= tokens:
        sig.add("skim")
    if "whole" in tokens or {"full", "fat"} <= tokens:
        sig.add("whole")
    for token in (
        "evaporated", "condensed", "buttermilk", "kefir", "goat", "human",
        "almond", "soy", "soymilk", "oat", "oatmilk", "coconut",
        "coconutmilk", "cashew", "hemp", "lactose", "chocolate", "vanilla",
        "strawberry",
    ):
        if token in tokens:
            sig.add(token)
    if tokens & {"dry", "dried", "powder", "powdered"}:
        sig.add("dry")
    return sig


def _looks_like_milk_text(text: str) -> bool:
    tokens = set(TOKEN_RE.findall((text or "").lower().replace("-", " ")))
    return "milk" in tokens or any(tok.endswith("milk") for tok in tokens)


def _milk_subtype_loss(
    src: str,
    surface: str,
    orig_code: str,
    current_desc: str,
    new_code: str,
    new_desc: str,
    desc_maps: dict[str, dict[str, str]],
) -> str:
    surface_sig = _milk_subtype_signature(surface)
    if not surface_sig:
        return ""
    orig_desc = desc_maps.get(src, {}).get(orig_code, "")
    resolved_new_desc = new_desc or desc_maps.get(src, {}).get(new_code, "")
    old_sig = surface_sig | _milk_subtype_signature(orig_desc or current_desc)
    new_sig = _milk_subtype_signature(resolved_new_desc)
    if not old_sig:
        return ""
    if not new_sig and _looks_like_milk_text(resolved_new_desc):
        return ",".join(sorted(old_sig - {"lactose"}))
    if not new_sig:
        return ""
    lost = old_sig - new_sig
    # Generic "milk" can be a good repair only when it does not erase a real
    # subtype such as 1%, 2%, skim, evaporated, condensed, plant milk, goat, etc.
    material_lost = lost - {"lactose"}
    if material_lost:
        return ",".join(sorted(material_lost))
    return ""


def _milk_unasked_variant(surface: str, description: str) -> str:
    surface_tokens = set(TOKEN_RE.findall((surface or "").lower().replace("-", " ")))
    desc_tokens = set(TOKEN_RE.findall((description or "").lower().replace("-", " ")))
    if not ("milk" in surface_tokens or any(tok.endswith("milk") for tok in surface_tokens)):
        return ""
    if not ("milk" in desc_tokens or any(tok.endswith("milk") for tok in desc_tokens)):
        return ""
    surface_sig = _milk_subtype_signature(surface)
    desc_sig = _milk_subtype_signature(description)
    plant_sig = {"almond", "soy", "soymilk", "oat", "oatmilk", "coconut", "coconutmilk"}
    if not (surface_sig & plant_sig and surface_sig & desc_sig):
        return ""
    extra = (desc_tokens - surface_tokens) & {"puerto", "rican"}
    if extra:
        return ",".join(sorted(extra))
    return ""


def main():
    inp = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IN
    out = (Path(sys.argv[2]) if len(sys.argv) > 2
           else DEFAULT_OUT)
    if not inp.exists():
        sys.exit(f"input not found: {inp}")

    print("Building concept index…", flush=True)
    concepts = build_concept_index()
    token_idx = build_token_to_concepts(concepts)
    desc_maps = _load_description_maps()
    print(f"  {len(concepts):,} concepts")

    print(f"\nReading: {inp}\nWriting: {out}\n", flush=True)
    t0 = time.time()
    n = 0
    audit = {
        "sr28": Counter(),
        "fndds": Counter(),
        "esha": Counter(),
    }
    verdict_total = Counter()

    NEW_COLS = [
        "rft_verdict", "rft_concept_tokens", "rft_canonical_name",
        "rft_surface_concept", "rft_missing", "rft_extra",
        "rft_composite_pieces", "rft_composite_secondary",
        "sr28_original_code", "sr28_change_reason", "sr28_inherited_from",
        "fndds_original_code", "fndds_change_reason", "fndds_inherited_from",
        "esha_original_code", "esha_change_reason", "esha_inherited_from",
    ]

    # COMPOSITE behaves like NEEDS_NEW_CONCEPT for code substitution: the
    # primary concept's code is recorded for reference but we don't replace
    # the original because composite products shouldn't substitute for
    # single-ingredient recipe calls.
    KEEP_ORIG_VERDICTS = {"NEEDS_NEW_CONCEPT", "NO_MATCH", "NO_IDENTITY",
                          "COMPOSITE"}

    def decide(src: str, surface: str, current_desc: str, verdict: str, orig_code: str, rft_info: dict | None) -> tuple[str, str, str, str, str]:
        """Return (new_code, new_desc, change_reason, level, inherited_from)."""
        rft_code = (rft_info or {}).get("code") or ""
        rft_desc = (rft_info or {}).get("desc") or ""
        rft_level = (rft_info or {}).get("level") or ""
        rft_inh = (rft_info or {}).get("inherited_from") or []
        inh_str = "|".join(rft_inh) if rft_inh else ""
        orig_code = (orig_code or "").strip()
        if src == "esha" and orig_code:
            desc_for_orig = desc_maps.get(src, {}).get(orig_code, "") or current_desc
            extra = _milk_unasked_variant(surface, desc_for_orig)
            if extra:
                return "", "", f"blanked_milk_unasked_variant:{extra}", "", ""
        if verdict in KEEP_ORIG_VERDICTS:
            tag = "composite" if verdict == "COMPOSITE" else "no_match"
            return orig_code, "", f"kept_orig_{tag}", "", ""
        if not rft_code:
            return orig_code, "", "kept_orig_no_rft", "", ""
        if verdict in ("EXACT", "STRONG"):
            if orig_code == rft_code:
                return rft_code, rft_desc, "kept_agree", rft_level, inh_str
            if not orig_code:
                return rft_code, rft_desc, "filled", rft_level, inh_str
            lost = _milk_subtype_loss(
                src, surface, orig_code, current_desc, rft_code, rft_desc, desc_maps
            )
            if lost:
                return (
                    orig_code,
                    desc_maps.get(src, {}).get(orig_code, ""),
                    f"kept_orig_milk_subtype_loss:{lost}",
                    "",
                    "",
                )
            return rft_code, rft_desc, "replaced", rft_level, inh_str
        # WEAK
        if orig_code == rft_code:
            return rft_code, rft_desc, "kept_agree", rft_level, inh_str
        if not orig_code:
            return rft_code, rft_desc, "filled_weak", rft_level, inh_str
        return orig_code, "", "kept_orig_weak", "", ""

    # Atomic-write via tempfile when input == output (re-clean in place).
    tmp_out = out.with_suffix(out.suffix + ".tmp")
    with inp.open(encoding="utf-8", errors="replace") as fin, \
         tmp_out.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        existing = list(reader.fieldnames or [])
        # Dedupe — if the input already has rft_*/_original_code columns
        # (re-running on a previously-cleaned file), don't add duplicates.
        out_fields = list(existing)
        for col in NEW_COLS:
            if col not in out_fields:
                out_fields.append(col)
        writer = csv.DictWriter(fout, fieldnames=out_fields)
        writer.writeheader()

        for r in reader:
            surf = (r.get("canonical_surface") or "").strip().lower()
            res = route(surf, concepts, token_idx)
            v = res["verdict"]
            verdict_total[v] += 1
            c = res.get("concept")
            bt = res.get("backtracked") or {}
            comp = res.get("composite") or None

            row_out = dict(r)
            row_out["rft_verdict"] = v
            row_out["rft_concept_tokens"] = "|".join(sorted(c.concept_id)) if c else ""
            row_out["rft_canonical_name"] = c.canonical_name if c else ""
            row_out["rft_surface_concept"] = "|".join(sorted(res.get("surface_concept") or []))
            row_out["rft_missing"] = "|".join(sorted(res.get("missing") or []))
            row_out["rft_extra"] = "|".join(sorted(res.get("extra") or []))
            if comp:
                row_out["rft_composite_pieces"] = " | ".join(comp.get("pieces", []))
                row_out["rft_composite_secondary"] = " | ".join(
                    s.get("canonical", "") for s in comp.get("secondary", []))
            else:
                row_out["rft_composite_pieces"] = ""
                row_out["rft_composite_secondary"] = ""

            for src in ("sr28", "fndds", "esha"):
                # Idempotency: prefer the truly-original code preserved from
                # any prior cleanup pass; only fall back to the current
                # `<src>_code` on the very first run.
                preserved = (r.get(f"{src}_original_code") or "").strip()
                current = (r.get(f"{src}_code") or "").strip()
                orig_code = preserved if preserved else current
                row_out[f"{src}_original_code"] = orig_code
                new_code, new_desc, reason, level, inh = decide(
                    src, surf, r.get(f"{src}_description") or "", v, orig_code, bt.get(src))
                row_out[f"{src}_code"] = new_code
                authoritative_desc = desc_maps.get(src, {}).get(new_code, "")
                if not new_code:
                    row_out[f"{src}_description"] = ""
                elif authoritative_desc:
                    row_out[f"{src}_description"] = authoritative_desc
                elif new_desc and (reason in ("replaced", "filled", "filled_weak") or reason.startswith("kept_orig_milk_subtype_loss")):
                    row_out[f"{src}_description"] = new_desc
                row_out[f"{src}_change_reason"] = (
                    reason + (f"_{level}" if level else ""))
                row_out[f"{src}_inherited_from"] = inh
                audit[src][reason] += 1

            writer.writerow(row_out)
            n += 1
    tmp_out.replace(out)

    print(f"Cleaned {n:,} rows in {time.time()-t0:.1f}s\n")
    print("VERDICT MIX:")
    for v, c in verdict_total.most_common():
        print(f"  {v:20s} {c:>6,}  ({100*c/n:5.1f}%)")
    print()
    for src in ("sr28", "fndds", "esha"):
        print(f"{src.upper()} change actions:")
        for reason, c in audit[src].most_common():
            print(f"  {reason:24s} {c:>6,}  ({100*c/n:5.1f}%)")
        print()
    print(f"Output: {out}")


if __name__ == "__main__":
    main()
