#!/usr/bin/env python3
"""Apply override layers to consensus_full_corpus_audit.csv → v2.

Inputs (read-only):
  consensus_full_corpus_audit.csv               — base
  consensus_taxonomy_overrides.csv              — Claude's right-place fixes
  consensus_reference_overrides.csv             — Codex's FNDDS/SR28/ESHA fixes (optional)
  consensus_source_conflicts.csv                — flag dirty BFCs (informational)

Outputs:
  consensus_full_corpus_audit.v2.csv            — patched audit
  consensus_apply_decision_log.csv              — what changed per fdc_id
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

V2 = Path(__file__).resolve().parent
BASE = V2 / "consensus_full_corpus_audit.csv"
TAX_OVR = V2 / "consensus_taxonomy_overrides.csv"
REF_OVR = V2 / "consensus_reference_overrides.csv"
SRC_CONFLICTS = V2 / "consensus_source_conflicts.csv"
OUT_AUDIT = V2 / "consensus_full_corpus_audit.v2.csv"
OUT_LOG = V2 / "consensus_apply_decision_log.csv"

csv.field_size_limit(sys.maxsize)


def _load_taxonomy_overrides() -> dict[str, dict]:
    if not TAX_OVR.exists(): return {}
    out = {}
    with TAX_OVR.open() as fh:
        for r in csv.DictReader(fh):
            fdc = (r.get("fdc_id") or "").strip()
            if not fdc: continue
            out[fdc] = {
                "new_canonical_path": r["new_canonical_path"],
                "new_product_identity": r.get("new_product_identity", ""),
                "issue_family": r.get("issue_family", ""),
                "reason": r.get("reason", ""),
            }
    return out


def _load_reference_overrides() -> dict[str, dict]:
    """Codex's FNDDS/SR28/ESHA correction layer.
    Expected schema: fdc_id, code_type (FNDDS/SR28/ESHA), new_code, new_desc, reason.
    """
    if not REF_OVR.exists(): return {}
    out: dict[str, dict] = {}
    with REF_OVR.open() as fh:
        for r in csv.DictReader(fh):
            fdc = (r.get("fdc_id") or "").strip()
            if not fdc: continue
            entry = out.setdefault(fdc, {})
            ct = r.get("code_type", "").upper()
            if ct == "FNDDS":
                entry["fndds_code"] = r.get("new_code", "")
                entry["fndds_desc"] = r.get("new_desc", "")
            elif ct == "SR28":
                entry["sr28_code"] = r.get("new_code", "")
                entry["sr28_desc"] = r.get("new_desc", "")
            elif ct == "ESHA":
                entry["esha_code"] = r.get("new_code", "")
                entry["esha_desc"] = r.get("new_desc", "")
    return out


def _load_source_conflicts() -> set[str]:
    if not SRC_CONFLICTS.exists(): return set()
    out = set()
    with SRC_CONFLICTS.open() as fh:
        for r in csv.DictReader(fh):
            fdc = (r.get("fdc_id") or "").strip()
            if fdc: out.add(fdc)
    return out


def main() -> None:
    if not BASE.exists():
        print(f"missing {BASE}", file=sys.stderr); sys.exit(1)

    tax_ovr = _load_taxonomy_overrides()
    ref_ovr = _load_reference_overrides()
    conflicts = _load_source_conflicts()
    print(f"  taxonomy overrides: {len(tax_ovr):,}")
    print(f"  reference overrides: {len(ref_ovr):,}")
    print(f"  source-conflict flags: {len(conflicts):,}")

    log_rows = []
    n_in = 0
    n_tax_applied = 0
    n_ref_applied = 0
    n_conflict_marked = 0
    with BASE.open(encoding="utf-8") as fh_in, OUT_AUDIT.open("w", newline="", encoding="utf-8") as fh_out:
        rdr = csv.DictReader(fh_in)
        fieldnames = list(rdr.fieldnames or [])
        # Add a 'consensus_overrides_applied' column if not present
        if "consensus_overrides_applied" not in fieldnames:
            fieldnames.append("consensus_overrides_applied")
        wtr = csv.DictWriter(fh_out, fieldnames=fieldnames, extrasaction="ignore")
        wtr.writeheader()

        for r in rdr:
            n_in += 1
            applied = []
            fdc = (r.get("fdc_id") or "").strip()
            old_cp = r.get("canonical_path", "")
            old_pi = r.get("product_identity_fixed", "")

            # Apply taxonomy override
            if fdc in tax_ovr:
                ov = tax_ovr[fdc]
                new_cp = ov["new_canonical_path"]
                new_pi = ov["new_product_identity"] or old_pi
                if new_cp and new_cp != old_cp:
                    r["canonical_path"] = new_cp
                    # Also sync category_path_fixed to new family > type
                    new_segs = new_cp.split(" > ")
                    if len(new_segs) >= 2:
                        r["category_path_fixed"] = " > ".join(new_segs[:2])
                    if new_pi:
                        r["product_identity_fixed"] = new_pi
                    # Update retail_leaf_path: replace prefix
                    old_rlp = r.get("retail_leaf_path", "")
                    if old_rlp.startswith(old_cp):
                        modifier = old_rlp[len(old_cp):]
                        r["retail_leaf_path"] = new_cp + modifier
                    elif old_rlp:
                        # No prefix match — just set RLP = new_cp
                        r["retail_leaf_path"] = new_cp
                    applied.append(f"taxonomy:{ov['issue_family']}")
                    log_rows.append({
                        "fdc_id": fdc,
                        "title": (r.get("title") or "")[:80],
                        "change_type": "taxonomy",
                        "issue_family": ov["issue_family"],
                        "old_canonical_path": old_cp,
                        "new_canonical_path": new_cp,
                        "reason": ov["reason"],
                    })
                    n_tax_applied += 1

            # Apply reference override
            if fdc in ref_ovr:
                changed = []
                for k, v in ref_ovr[fdc].items():
                    if v and r.get(k) != v:
                        changed.append((k, r.get(k), v))
                        r[k] = v
                if changed:
                    applied.append("reference")
                    n_ref_applied += 1
                    log_rows.append({
                        "fdc_id": fdc,
                        "title": (r.get("title") or "")[:80],
                        "change_type": "reference",
                        "issue_family": "",
                        "old_canonical_path": "",
                        "new_canonical_path": "",
                        "reason": " ; ".join(f"{k}: {old!r} → {new!r}" for k, old, new in changed),
                    })

            # Flag source conflicts
            if fdc in conflicts:
                applied.append("source_conflict_flagged")
                n_conflict_marked += 1

            r["consensus_overrides_applied"] = "|".join(applied)
            wtr.writerow(r)

    print(f"  read {n_in:,} rows, applied {n_tax_applied:,} taxonomy + {n_ref_applied:,} reference + flagged {n_conflict_marked:,} conflicts")

    log_cols = ["fdc_id", "title", "change_type", "issue_family",
                "old_canonical_path", "new_canonical_path", "reason"]
    with OUT_LOG.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=log_cols)
        w.writeheader()
        for r in log_rows:
            w.writerow(r)
    print(f"  wrote {len(log_rows):,} log rows → {OUT_LOG.name}")
    print(f"  wrote {OUT_AUDIT.name}")


if __name__ == "__main__":
    main()
