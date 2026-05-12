from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
OUT = ROOT / "implementation" / "output"
REPORT = OUT / "cleanup_candidates.csv"
SUMMARY = OUT / "cleanup_candidates.summary.json"

CURRENT_KEEP = {
    OUT / "canonical_surface_normalized_with_product_proxies_CLEANED.csv",
    OUT / "product_to_best_esha_full_map.vIdentity.csv",
    OUT / "product_to_best_esha_full_map.vKG_RFT.csv",
    OUT / "product_to_best_esha_full_map.vKG_RFT.diff.csv",
    OUT / "product_to_best_esha_full_map.vKG_RFT.summary.json",
    OUT / "product_to_best_esha_full_map.vKG_RFT.identity_contradictions.csv",
    OUT / "product_to_best_esha_full_map.vKG_RFT.identity_contradictions.summary.json",
    OUT / "rft_v2" / "rft_v2_product_to_esha.csv",
    OUT / "rft_v2" / "rft_v2_summary.json",
    OUT / "rft_v2" / "scale" / "full_corpus_routes.csv.gz",
    OUT / "rft_v2" / "scale" / "summary.json",
}

LEGACY_MAP_PREFIXES = (
    "product_to_best_esha_full_map.vFixy",
    "product_to_best_esha_full_map.vKG.csv",
    "product_to_best_esha_full_map.vKG2",
    "product_to_best_esha_full_map.vM2",
    "product_to_best_esha_full_map.vM3",
    "product_to_best_esha_full_map.vSelf",
)


def classify(path: Path) -> tuple[str, str]:
    rel = path.relative_to(ROOT)
    name = path.name
    if path in CURRENT_KEEP:
        return "keep_current", "current RFT/KG artifact or cleaned canonical"
    if "__pycache__" in path.parts or name.endswith((".pyc", ".pyo")):
        return "delete_candidate", "Python cache"
    if "backup" in name.lower() or name.endswith((".bak", ".tmp")):
        return "delete_candidate", "backup/temp artifact"
    if name == "canonical_surface_normalized_with_product_proxies.csv":
        return "archive_candidate", "old uncleaned canonical surface"
    if name == "canonical_surface_normalized_with_product_proxies_CLEANED.csv" and path.parent != OUT:
        return "archive_candidate", "duplicate cleaned canonical outside implementation/output"
    if name.startswith(LEGACY_MAP_PREFIXES):
        return "archive_candidate", "older experimental whole-corpus map"
    if name.startswith("product_to_best_esha_full_map.vM") and name != "product_to_best_esha_full_map.vM.csv":
        return "archive_candidate", "older vM iteration"
    if name.startswith("product_to_best_esha_full_map.vCluster"):
        return "archive_candidate", "cluster experiment output, not truth"
    if name.startswith("product_to_best_esha_full_map.vKG_RFT"):
        return "keep_current", "current RFT/KG output family"
    if rel.parts[:2] == ("implementation", "output"):
        return "review", "generated output; keep unless superseded by current workflow"
    if path.suffix == ".py" and path.parent == ROOT / "implementation":
        stem = path.stem
        if stem.startswith(("rft_poc", "rft_clean_", "rft_scale_concept")):
            return "archive_candidate", "older RFT proof-of-concept/cleanup script"
    return "review", "not automatically classified"


def main() -> None:
    rows = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        if any(part in {".venv", ".git"} for part in path.parts):
            continue
        try:
            rel_parts = path.relative_to(ROOT).parts
        except ValueError:
            continue
        if rel_parts and rel_parts[0] == "archive":
            continue
        if rel_parts[:2] in {("graph", "db"), ("data", "fndds"), ("data", "sr28_csv")}:
            continue
        status, reason = classify(path)
        if status == "review" and not (
            "canonical_surface" in path.name
            or "product_to_best_esha_full_map" in path.name
            or "backup" in path.name.lower()
            or "__pycache__" in path.parts
            or path.suffix == ".py"
        ):
            continue
        rows.append(
            {
                "path": str(path.relative_to(ROOT)),
                "status": status,
                "reason": reason,
                "bytes": str(path.stat().st_size),
            }
        )

    counts: dict[str, int] = {}
    bytes_by_status: dict[str, int] = {}
    for row in rows:
        status = row["status"]
        counts[status] = counts.get(status, 0) + 1
        bytes_by_status[status] = bytes_by_status.get(status, 0) + int(row["bytes"])

    OUT.mkdir(parents=True, exist_ok=True)
    with REPORT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["path", "status", "reason", "bytes"])
        writer.writeheader()
        writer.writerows(rows)
    SUMMARY.write_text(
        json.dumps(
            {
                "report": str(REPORT),
                "rows": len(rows),
                "counts": counts,
                "bytes_by_status": bytes_by_status,
                "note": "No files were deleted. Review archive/delete candidates before removal.",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(SUMMARY.read_text(encoding="utf-8"), end="")


if __name__ == "__main__":
    main()
