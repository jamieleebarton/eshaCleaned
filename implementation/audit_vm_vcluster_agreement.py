from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"

DEFAULT_VM = OUT_DIR / "product_to_best_esha_full_map.vM.csv"
DEFAULT_VCLUSTER = OUT_DIR / "product_to_best_esha_full_map.vCluster.csv"
DEFAULT_VKG = OUT_DIR / "product_to_best_esha_full_map.vKG.csv"
DEFAULT_OUT = OUT_DIR / "vm_vcluster_agreement_audit.csv"
DEFAULT_SUMMARY = OUT_DIR / "vm_vcluster_agreement_summary.json"
DEFAULT_RISK = OUT_DIR / "vm_vcluster_agreed_code_category_risk.csv"


BASE_COLUMNS = [
    "gtin_upc",
    "fdc_id",
    "product_description",
    "branded_food_category",
    "brand_owner",
    "brand_name",
    "best_esha_code",
    "best_esha_description",
    "best_esha_head",
    "best_esha_family",
    "score",
    "n_candidates",
    "assignment_source",
    "score_num",
]


def product_key(row: dict[str, str], row_number: int) -> str:
    fdc_id = (row.get("fdc_id") or "").strip()
    if fdc_id:
        return f"fdc:{fdc_id}"
    gtin = (row.get("gtin_upc") or "").strip()
    if gtin:
        return f"gtin:{gtin}"
    return f"row:{row_number}"


def read_rows(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            key = product_key(row, i)
            row["_row_number"] = str(i)
            rows[key] = row
    return rows


def assigned(row: dict[str, str] | None) -> bool:
    return bool(row and (row.get("best_esha_code") or "").strip())


def code(row: dict[str, str] | None) -> str:
    return (row.get("best_esha_code") or "").strip() if row else ""


def text(row: dict[str, str] | None, col: str) -> str:
    return (row.get(col) or "").strip() if row else ""


def top_values(values: Counter[str], n: int = 8) -> str:
    return " | ".join(f"{k}:{v}" for k, v in values.most_common(n))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vm", type=Path, default=DEFAULT_VM)
    parser.add_argument("--vcluster", type=Path, default=DEFAULT_VCLUSTER)
    parser.add_argument("--vkg", type=Path, default=DEFAULT_VKG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--risk", type=Path, default=DEFAULT_RISK)
    args = parser.parse_args()

    vm = read_rows(args.vm)
    vcluster = read_rows(args.vcluster)
    vkg = read_rows(args.vkg) if args.vkg.exists() else {}
    keys = sorted(set(vm) | set(vcluster))

    status_counts: Counter[str] = Counter()
    agreement_source_counts: Counter[str] = Counter()
    agreed_head_counts: Counter[str] = Counter()
    not_done_reasons: Counter[str] = Counter()
    code_category_counts: dict[str, Counter[str]] = defaultdict(Counter)
    code_brand_counts: dict[str, Counter[str]] = defaultdict(Counter)
    code_desc: dict[str, str] = {}
    code_head: dict[str, str] = {}

    audit_fields = [
        "agreement_status",
        "done_candidate",
        "done_blocker",
        "product_key",
        "gtin_upc",
        "fdc_id",
        "product_description",
        "branded_food_category",
        "brand_owner",
        "brand_name",
        "vm_code",
        "vm_description",
        "vm_head",
        "vm_assignment_source",
        "vcluster_code",
        "vcluster_description",
        "vcluster_head",
        "vcluster_assignment_source",
        "vcluster_cluster_assignment_status",
        "vcluster_projection_guard_reason",
        "vkg_code",
        "vkg_assignment_source",
    ]

    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=audit_fields)
        writer.writeheader()

        for key in keys:
            m = vm.get(key)
            c = vcluster.get(key)
            k = vkg.get(key)
            m_assigned = assigned(m)
            c_assigned = assigned(c)
            k_assigned = assigned(k)
            m_code = code(m)
            c_code = code(c)
            k_code = code(k)

            done_candidate = "0"
            blocker = ""
            if m_assigned and c_assigned and m_code == c_code:
                status = "same_assigned_code"
                if k and not k_assigned:
                    blocker = "structural_quarantine_in_vKG"
                elif k and k_code and k_code != m_code:
                    blocker = "vKG_changed_code"
                elif text(c, "cluster_assignment_status") == "projection_rejected":
                    blocker = "vCluster_projection_rejected"
                else:
                    done_candidate = "1"

                agreement_source_counts[f"{text(m, 'assignment_source')}|{text(c, 'assignment_source')}"] += 1
                agreed_head_counts[text(m, "best_esha_head")] += 1
                cat = text(m, "branded_food_category")
                brand = text(m, "brand_name") or text(m, "brand_owner")
                code_category_counts[m_code][cat] += 1
                code_brand_counts[m_code][brand] += 1
                code_desc[m_code] = text(m, "best_esha_description")
                code_head[m_code] = text(m, "best_esha_head")
            elif not m_assigned and not c_assigned:
                status = "both_unassigned"
                blocker = "both_unassigned"
            elif m_assigned and not c_assigned:
                status = "vm_only_assigned"
                blocker = "vCluster_unassigned"
            elif c_assigned and not m_assigned:
                status = "vcluster_only_assigned"
                blocker = "vM_unassigned"
            else:
                status = "different_assigned_code"
                blocker = "assigned_code_disagreement"

            status_counts[status] += 1
            if blocker:
                not_done_reasons[blocker] += 1

            writer.writerow(
                {
                    "agreement_status": status,
                    "done_candidate": done_candidate,
                    "done_blocker": blocker,
                    "product_key": key,
                    "gtin_upc": text(m or c, "gtin_upc"),
                    "fdc_id": text(m or c, "fdc_id"),
                    "product_description": text(m or c, "product_description"),
                    "branded_food_category": text(m or c, "branded_food_category"),
                    "brand_owner": text(m or c, "brand_owner"),
                    "brand_name": text(m or c, "brand_name"),
                    "vm_code": m_code,
                    "vm_description": text(m, "best_esha_description"),
                    "vm_head": text(m, "best_esha_head"),
                    "vm_assignment_source": text(m, "assignment_source"),
                    "vcluster_code": c_code,
                    "vcluster_description": text(c, "best_esha_description"),
                    "vcluster_head": text(c, "best_esha_head"),
                    "vcluster_assignment_source": text(c, "assignment_source"),
                    "vcluster_cluster_assignment_status": text(c, "cluster_assignment_status"),
                    "vcluster_projection_guard_reason": text(c, "projection_guard_reason"),
                    "vkg_code": k_code,
                    "vkg_assignment_source": text(k, "assignment_source"),
                }
            )

    risk_rows = []
    for esha_code, cats in code_category_counts.items():
        n = sum(cats.values())
        distinct_categories = len([c for c in cats if c])
        brands = code_brand_counts[esha_code]
        risk_rows.append(
            {
                "best_esha_code": esha_code,
                "best_esha_description": code_desc.get(esha_code, ""),
                "best_esha_head": code_head.get(esha_code, ""),
                "agreed_rows": str(n),
                "distinct_branded_food_categories": str(distinct_categories),
                "top_branded_food_categories": top_values(cats),
                "distinct_brands": str(len([b for b in brands if b])),
                "top_brands": top_values(brands),
            }
        )
    risk_rows.sort(
        key=lambda r: (
            int(r["distinct_branded_food_categories"]),
            int(r["agreed_rows"]),
        ),
        reverse=True,
    )
    with args.risk.open("w", newline="", encoding="utf-8") as f:
        fields = [
            "best_esha_code",
            "best_esha_description",
            "best_esha_head",
            "agreed_rows",
            "distinct_branded_food_categories",
            "top_branded_food_categories",
            "distinct_brands",
            "top_brands",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(risk_rows)

    same = status_counts["same_assigned_code"]
    # Re-read done count without retaining rows in memory.
    done_candidates = 0
    structural_blocked = 0
    with args.out.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["done_candidate"] == "1":
                done_candidates += 1
            if row["done_blocker"] == "structural_quarantine_in_vKG":
                structural_blocked += 1

    summary = {
        "vm": str(args.vm),
        "vcluster": str(args.vcluster),
        "vkg": str(args.vkg) if args.vkg.exists() else None,
        "audit": str(args.out),
        "risk": str(args.risk),
        "rows_compared": len(keys),
        "status_counts": dict(status_counts),
        "same_assigned_code": same,
        "same_assigned_code_share_of_all_rows": round(same / len(keys), 6) if keys else 0,
        "done_candidate_rows": done_candidates,
        "done_candidate_share_of_all_rows": round(done_candidates / len(keys), 6) if keys else 0,
        "same_assigned_but_structurally_quarantined_in_vKG": structural_blocked,
        "not_done_reasons": dict(not_done_reasons),
        "top_agreed_heads": dict(agreed_head_counts.most_common(30)),
        "top_agreement_sources": dict(agreement_source_counts.most_common(30)),
        "highest_category_spread_agreed_codes": risk_rows[:30],
    }
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
