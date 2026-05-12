#!/usr/bin/env python3
"""Build Codex's independent full corpus taxonomy audit.

This intentionally does not write full_corpus_audit.csv or
full_corpus_enriched.csv. It reads full_corpus_cleaned.csv as taxonomy input,
copies only reference match metadata from full_corpus_enriched.csv, applies the
central taxonomy_finalizer.py contract, and writes Codex-named artifacts.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from taxonomy_finalizer import apply_finalized_taxonomy, path_defects


REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
CLEANED = V2 / "full_corpus_cleaned.csv"
ENRICHED = V2 / "full_corpus_enriched.csv"
FNDDS_FILE_HESTIA = REPO.parent / "Hestia" / "api" / "data" / "MainFoodDesc.csv"
FNDDS_FILE_2016 = REPO / "data" / "fndds" / "MainFoodDesc16.csv"
SR_LEGACY = REPO / "data" / "sr28_csv" / "sr_legacy_food.csv"
SR_FOOD = REPO / "data" / "sr28_csv" / "food.csv"
SR_LINKS = REPO / "data" / "fndds" / "FNDDSSRLinks.csv"
ESHA_FILE = REPO / "esha_cleaned.csv"

OUT = V2 / "codex_full_corpus_audit.csv"
REPORT = V2 / "codex_full_corpus_audit_report.json"
BFC_SUMMARY = V2 / "codex_bfc_path_summary.csv"
FRAGMENTATION = V2 / "codex_taxonomy_fragmentation_report.csv"
FRAGMENTATION_EXAMPLES = V2 / "codex_taxonomy_fragmentation_examples.csv"

csv.field_size_limit(sys.maxsize)

REFERENCE_COLUMNS = [
    "fndds_code",
    "sr28_code",
    "esha_code",
    "match_source",
    "match_score",
    "matched_key",
    "portions_json",
]

FINALIZED_COLUMNS = [
    "category_path_fixed",
    "product_identity_fixed",
    "canonical_path",
    "modifier",
    "retail_leaf_path",
]

AUDIT_EXTRA_COLUMNS = [
    "fndds_code",
    "fndds_desc",
    "sr28_code",
    "sr28_desc",
    "esha_code",
    "esha_desc",
    "match_source",
    "match_score",
    "matched_key",
    "portions_json",
    "codex_path_defects",
]

SPOT_CHECK_IDS = {
    "2270621",
    "2639382",
    "2637392",
    "1460868",
    "2613407",
    "2610227",
    "2683955",
    "2610340",
    "2610288",
    "2373574",
    "1556661",
    "753254",
    "753250",
    "345844",
    "1464085",
    "2367430",
    "2150403",
    "1472139",
    "2655955",
    "2593984",
    "2642187",
    "2439882",
    "2368705",
}


def load_enriched_refs() -> dict[str, dict[str, str]]:
    refs: dict[str, dict[str, str]] = {}
    with ENRICHED.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            fdc = (row.get("fdc_id") or "").strip()
            if not fdc:
                continue
            refs[fdc] = {col: row.get(col, "") for col in REFERENCE_COLUMNS}
    return refs


def load_fndds_desc() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in (FNDDS_FILE_HESTIA, FNDDS_FILE_2016):
        if not path.exists():
            continue
        with path.open(encoding="utf-8", errors="replace") as fh:
            for row in csv.DictReader(fh):
                code = (row.get("Food code") or "").strip()
                desc = (row.get("Main food description") or "").strip()
                if code and desc and code not in out:
                    out[code] = desc
    return out


def load_sr28_desc() -> dict[str, str]:
    out: dict[str, str] = {}
    if SR_LEGACY.exists() and SR_FOOD.exists():
        ndb_to_fdc: dict[str, str] = {}
        with SR_LEGACY.open(encoding="utf-8", errors="replace") as fh:
            for row in csv.DictReader(fh):
                ndb = (row.get("NDB_number") or "").strip()
                fdc = (row.get("fdc_id") or "").strip()
                if ndb and fdc:
                    ndb_to_fdc[ndb] = fdc
        fdc_to_desc: dict[str, str] = {}
        with SR_FOOD.open(encoding="utf-8", errors="replace") as fh:
            for row in csv.DictReader(fh):
                fdc = (row.get("fdc_id") or "").strip()
                desc = (row.get("description") or "").strip()
                if fdc and desc:
                    fdc_to_desc[fdc] = desc
        for ndb, fdc in ndb_to_fdc.items():
            desc = fdc_to_desc.get(fdc)
            if desc:
                out[ndb] = desc
    if SR_LINKS.exists():
        with SR_LINKS.open(encoding="utf-8", errors="replace") as fh:
            for row in csv.DictReader(fh):
                code = (row.get("SR code") or "").strip()
                desc = (row.get("SR description") or "").strip()
                if code and desc and code not in out:
                    out[code] = desc
    return out


def load_esha_desc() -> dict[str, str]:
    out: dict[str, str] = {}
    if not ESHA_FILE.exists():
        return out
    with ESHA_FILE.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("EshaCode") or "").strip()
            desc = (row.get("Description") or "").strip()
            if code and desc:
                out[code] = desc
    return out


def identity_key(identity: str) -> str:
    return " ".join((identity or "").lower().replace("&", " ").split())


def main() -> None:
    refs = load_enriched_refs()
    fndds_desc = load_fndds_desc()
    sr28_desc = load_sr28_desc()
    esha_desc = load_esha_desc()

    rows = 0
    fdc_counts: Counter[str] = Counter()
    defect_counts: Counter[str] = Counter()
    canonical_counts: Counter[str] = Counter()
    retail_leaf_counts: Counter[str] = Counter()
    bfc_path_counts: dict[str, Counter[str]] = defaultdict(Counter)
    bfc_totals: Counter[str] = Counter()
    paths_by_identity: dict[str, Counter[str]] = defaultdict(Counter)
    label_by_identity: dict[str, Counter[str]] = defaultdict(Counter)
    fragmentation_examples: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    missing_reference_rows = 0
    spot_checks: dict[str, dict[str, str]] = {}

    with CLEANED.open(encoding="utf-8") as src:
        reader = csv.DictReader(src)
        fieldnames = list(reader.fieldnames or [])
        for col in FINALIZED_COLUMNS:
            if col not in fieldnames:
                fieldnames.append(col)
        for col in AUDIT_EXTRA_COLUMNS:
            if col not in fieldnames:
                fieldnames.append(col)

        with OUT.open("w", encoding="utf-8", newline="") as dst:
            writer = csv.DictWriter(dst, fieldnames=fieldnames)
            writer.writeheader()

            for row in reader:
                rows += 1
                fdc = (row.get("fdc_id") or "").strip()
                fdc_counts[fdc] += 1
                ref = refs.get(fdc, {})
                if not ref:
                    missing_reference_rows += 1

                row["fndds_code"] = ref.get("fndds_code", "")
                row["sr28_code"] = ref.get("sr28_code", "")
                row["esha_code"] = ref.get("esha_code", "")
                row["match_source"] = ref.get("match_source", "")
                row["match_score"] = ref.get("match_score", "")
                row["matched_key"] = ref.get("matched_key", "")
                row["portions_json"] = ref.get("portions_json", "")
                row["fndds_desc"] = fndds_desc.get(row["fndds_code"], "")
                row["sr28_desc"] = sr28_desc.get(row["sr28_code"], "")
                row["esha_desc"] = esha_desc.get(row["esha_code"], "")

                apply_finalized_taxonomy(row)
                defects = path_defects(row)
                row["codex_path_defects"] = "|".join(defects)
                if defects:
                    defect_counts["defect_rows"] += 1
                    defect_counts.update(defects)

                canonical = row.get("canonical_path", "")
                retail_leaf = row.get("retail_leaf_path", "")
                identity = row.get("product_identity_fixed", "")
                bfc = (row.get("branded_food_category") or "").strip()
                canonical_counts[canonical] += 1
                retail_leaf_counts[retail_leaf] += 1
                if bfc:
                    bfc_totals[bfc] += 1
                    bfc_path_counts[bfc][canonical] += 1

                if identity:
                    ikey = identity_key(identity)
                    paths_by_identity[ikey][canonical] += 1
                    label_by_identity[ikey][identity] += 1
                    bucket = (ikey, canonical)
                    if len(fragmentation_examples[bucket]) < 5:
                        fragmentation_examples[bucket].append({
                            "fdc_id": fdc,
                            "title": row.get("title", ""),
                            "branded_food_category": bfc,
                            "category_path_fixed": row.get("category_path_fixed", ""),
                            "product_identity_fixed": identity,
                            "canonical_path": canonical,
                            "retail_leaf_path": retail_leaf,
                        })

                if fdc in SPOT_CHECK_IDS:
                    spot_checks[fdc] = {
                        "title": row.get("title", ""),
                        "branded_food_category": bfc,
                        "category_path_fixed": row.get("category_path_fixed", ""),
                        "product_identity_fixed": identity,
                        "canonical_path": canonical,
                        "modifier": row.get("modifier", ""),
                        "retail_leaf_path": retail_leaf,
                    }

                writer.writerow({col: row.get(col, "") for col in fieldnames})

    with BFC_SUMMARY.open("w", encoding="utf-8", newline="") as fh:
        fields = [
            "branded_food_category",
            "rows",
            "n_canonical_paths",
            "canonical_path",
            "canonical_path_rows",
            "canonical_path_pct",
        ]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for bfc, path_counts in sorted(bfc_path_counts.items()):
            total = bfc_totals[bfc]
            for path, count in path_counts.most_common(20):
                writer.writerow({
                    "branded_food_category": bfc,
                    "rows": total,
                    "n_canonical_paths": len(path_counts),
                    "canonical_path": path,
                    "canonical_path_rows": count,
                    "canonical_path_pct": round(count / total, 4) if total else 0,
                })

    fragmented = {key for key, counts in paths_by_identity.items() if len(counts) > 1}
    with FRAGMENTATION.open("w", encoding="utf-8", newline="") as fh:
        fields = [
            "identity_key",
            "identity_label",
            "total_rows",
            "n_canonical_paths",
            "dominant_canonical_path",
            "dominant_rows",
            "second_canonical_path",
            "second_rows",
            "all_paths",
        ]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for key, path_counts in sorted(
            paths_by_identity.items(),
            key=lambda kv: (-sum(kv[1].values()), kv[0]),
        ):
            if len(path_counts) < 2:
                continue
            ranked = path_counts.most_common()
            label = label_by_identity[key].most_common(1)[0][0]
            writer.writerow({
                "identity_key": key,
                "identity_label": label,
                "total_rows": sum(path_counts.values()),
                "n_canonical_paths": len(path_counts),
                "dominant_canonical_path": ranked[0][0],
                "dominant_rows": ranked[0][1],
                "second_canonical_path": ranked[1][0],
                "second_rows": ranked[1][1],
                "all_paths": " | ".join(f"{path} ({count})" for path, count in ranked),
            })

    with FRAGMENTATION_EXAMPLES.open("w", encoding="utf-8", newline="") as fh:
        fields = [
            "identity_key",
            "canonical_path",
            "fdc_id",
            "title",
            "branded_food_category",
            "category_path_fixed",
            "product_identity_fixed",
            "retail_leaf_path",
        ]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for key in sorted(fragmented):
            for path, _count in paths_by_identity[key].most_common():
                for example in fragmentation_examples[(key, path)]:
                    writer.writerow({"identity_key": key, **example})

    report = {
        "rows": rows,
        "unique_fdc_ids": len([fdc for fdc in fdc_counts if fdc]),
        "duplicate_fdc_extra_rows": sum(max(0, count - 1) for count in fdc_counts.values()),
        "missing_reference_rows": missing_reference_rows,
        "distinct_canonical_paths": len(canonical_counts),
        "distinct_retail_leaf_paths": len(retail_leaf_counts),
        "path_defects": dict(defect_counts),
        "fragmented_identities": len(fragmented),
        "top_canonical_paths": canonical_counts.most_common(50),
        "spot_checks": spot_checks,
        "outputs": {
            "audit_csv": str(OUT),
            "bfc_summary_csv": str(BFC_SUMMARY),
            "fragmentation_report_csv": str(FRAGMENTATION),
            "fragmentation_examples_csv": str(FRAGMENTATION_EXAMPLES),
        },
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"wrote {OUT} ({OUT.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"wrote {REPORT}")
    print(f"wrote {BFC_SUMMARY}")
    print(f"wrote {FRAGMENTATION}")
    print(f"wrote {FRAGMENTATION_EXAMPLES}")
    print(json.dumps({
        "rows": rows,
        "distinct_canonical_paths": len(canonical_counts),
        "distinct_retail_leaf_paths": len(retail_leaf_counts),
        "path_defect_rows": defect_counts.get("defect_rows", 0),
        "fragmented_identities": len(fragmented),
    }, indent=2))


if __name__ == "__main__":
    main()
