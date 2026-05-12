"""Rank top2500 rows by how much they block Hestia.

impact_score = occurrence_count * brokenness_weight

brokenness_weight:
  - product_contract_status in {"contract_failed", "contract_missing", "no_products",
    "not_candidate_covered", "stale_normalization_artifact"} => 4
  - issue_class contains "poison" / "wrong_class" / "broad_query_warning" / "suspicious" => 3
  - check_status in {"needs_review", "open", "todo"} => 2
  - default => 1

Skips rows already reviewed_terminal / done.
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "implementation" / "output" / "top2500_cleanup_progress.csv"
OUT = ROOT / "implementation" / "output" / "release_blocker_queue.csv"

SKIP_STATUS = {"reviewed_terminal", "done"}

BROKEN_CONTRACT_STATUSES = {
    "contract_failed",
    "contract_missing",
    "no_products",
    "not_candidate_covered",
    "stale_normalization_artifact",
}

BROKEN_ISSUE_TOKENS = ("poison", "wrong_class", "broad_query_warning", "suspicious")

OPEN_CHECK_STATUSES = {"needs_review", "open", "todo"}


def load_progress_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"release blocker queue source is missing: {path}")
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError(
            "release blocker queue cannot be rebuilt from an empty cleanup progress file; "
            f"source={path}"
        )
    return rows


def brokenness(row: dict) -> int:
    contract = (row.get("product_contract_status") or "").strip()
    issue = (row.get("issue_class") or "").strip().lower()
    status = (row.get("check_status") or "").strip().lower()
    if contract in BROKEN_CONTRACT_STATUSES:
        return 4
    if any(tok in issue for tok in BROKEN_ISSUE_TOKENS):
        return 3
    if status in OPEN_CHECK_STATUSES:
        return 2
    return 1


def blocker_reason(row: dict) -> str:
    parts = []
    c = (row.get("product_contract_status") or "").strip()
    if c and c not in {"contract_passed", "external_catalog_covered"}:
        parts.append(f"contract={c}")
    i = (row.get("issue_class") or "").strip()
    if i and i != "ok":
        parts.append(f"issue={i}")
    s = (row.get("check_status") or "").strip()
    if s and s not in {"done", "reviewed_terminal"}:
        parts.append(f"status={s}")
    return "; ".join(parts) or "unspecified"


def main() -> None:
    rows = [r for r in load_progress_rows(SRC) if (r.get("check_status") or "").strip() not in SKIP_STATUS]
    scored = []
    for r in rows:
        try:
            occ = int(r.get("occurrence_count") or 0)
        except ValueError:
            occ = 0
        score = occ * brokenness(r)
        r2 = dict(r)
        r2["impact_score"] = str(score)
        r2["blocker_reason"] = blocker_reason(r)
        scored.append(r2)
    scored.sort(key=lambda r: int(r["impact_score"]), reverse=True)
    fieldnames = list(scored[0].keys()) if scored else []
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(scored)
    print(f"wrote {len(scored)} blockers to {OUT}")


if __name__ == "__main__":
    main()
