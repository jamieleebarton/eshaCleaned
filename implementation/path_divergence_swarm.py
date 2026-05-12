#!/usr/bin/env python3
"""
Path Divergence Audit Swarm

Groups products by identity, finds those with multiple canonical paths,
and categorizes them by whether the divergence is clean, mostly clean,
legitimate flavor variance, or real bugs.

Run from repo root:
    python3 implementation/path_divergence_swarm.py

Output:
    implementation/output/path_divergence_report.csv
"""

import csv
import sys
from collections import defaultdict, Counter
from pathlib import Path


def longest_common_prefix(path_parts_list):
    """Find the longest common prefix among a list of path segment lists."""
    if not path_parts_list:
        return []
    min_len = min(len(p) for p in path_parts_list)
    prefix = []
    for i in range(min_len):
        segments = set(p[i] for p in path_parts_list)
        if len(segments) == 1:
            prefix.append(list(segments)[0])
        else:
            break
    return prefix


def get_bug_signals(identity, path_str):
    """Return a list of bug signal strings for a given identity + path."""
    signals = []
    p_lower = path_str.lower()
    id_lower = identity.lower()

    # Hot dog under buns / bakery / sandwiches
    if "hot dog" in id_lower or "hotdog" in id_lower:
        if "bun" in p_lower:
            signals.append("buns_mismatch")
        if any(x in p_lower for x in ["gravy mix", "sandwich", "bread"]):
            signals.append("wrong_category")

    # Juice under drink mix (mid-path)
    if "juice" in id_lower:
        if "drink mix" in p_lower:
            signals.append("drink_mix_midpath")

    # Beans under baking mixes
    if "bean" in id_lower:
        if "baking mixes" in p_lower or "cake mix" in p_lower:
            signals.append("baking_mixes_misplacement")

    # Cheese under candy / soda / cookies
    if id_lower == "cheese":
        if any(x in p_lower for x in ["candy", "soda", "cookie", "snack > candy"]):
            signals.append("candy_misplacement")

    # Potato chips under non-snack categories
    if "potato chip" in id_lower or id_lower == "chips":
        if not any(x in p_lower for x in ["snack", "chip"]):
            signals.append("non_snack_misplacement")

    # Sushi under dairy / dessert / beverage
    if id_lower == "sushi":
        if any(x in p_lower for x in ["dairy", "dessert", "beverage", "candy"]):
            signals.append("non_meal_misplacement")

    # Yogurt under bakery / snack / pantry
    if "yogurt" in id_lower:
        if any(x in p_lower for x in ["bakery > cake", "snack > candy", "beverage > soda", "pantry > nut butters"]):
            signals.append("non_dairy_misplacement")

    # Cake mix under snack / beverage / frozen > ice cream
    if "cake mix" in id_lower:
        if any(x in p_lower for x in ["beverage", "frozen > ice cream", "snack > candy", "dairy > cream cheese"]):
            signals.append("non_pantry_misplacement")

    # Ice cream under pantry / bakery / snack
    if "ice cream" in id_lower:
        if any(x in p_lower for x in ["pantry > nut butters", "bakery > cake", "bakery > cookie dough", "snack > candy > candy canes"]):
            signals.append("non_frozen_misplacement")

    # Cookies under beverage / dairy / frozen
    if id_lower == "cookies":
        if any(x in p_lower for x in ["beverage", "dairy > cheese", "frozen > ice cream", "pantry > spices"]):
            signals.append("non_snack_bakery_misplacement")

    # Bread under snack / beverage / pantry > spices
    if id_lower == "bread":
        if any(x in p_lower for x in ["beverage", "snack > candy", "pantry > spices", "dairy > cheese"]):
            signals.append("non_bakery_misplacement")

    # Seasoning under non-pantry
    if id_lower == "seasoning":
        if not p_lower.startswith("pantry"):
            signals.append("non_pantry_misplacement")

    return signals


def classify_divergence(identity, path_counts, flavor_counts):
    total = sum(path_counts.values())
    top_path, top_count = path_counts.most_common(1)[0]
    top_pct = (top_count / total * 100) if total else 0

    paths = list(path_counts.keys())
    path_parts = [p.split(" > ") for p in paths if p]

    # Category distribution (by product count, not unique path count)
    cat_counts = Counter()
    for p, c in path_counts.items():
        top_cat = p.split(" > ")[0] if p else "Unknown"
        cat_counts[top_cat] += c

    top_cat, top_cat_count = cat_counts.most_common(1)[0]
    top_cat_pct = (top_cat_count / total * 100) if total else 0
    top2_cat_pct = (sum(c for _, c in cat_counts.most_common(2)) / total * 100) if total else 0

    # Common prefix of ALL paths
    common_prefix_all = longest_common_prefix(path_parts)

    # Common prefix of paths covering top 80% of products
    sorted_paths = path_counts.most_common()
    cumulative = 0
    top80_parts = []
    for p, c in sorted_paths:
        top80_parts.append(p.split(" > "))
        cumulative += c
        if cumulative / total >= 0.80:
            break
    common_prefix_top80 = longest_common_prefix(top80_parts)

    top_cats = sorted(cat_counts.keys())
    num_top_cats = len(top_cats)

    # Build paths summary
    path_summaries = []
    flagged_paths = []
    for p, c in path_counts.most_common():
        pct = c / total * 100
        path_summaries.append(f"{c} ({pct:.1f}%) {p}")
        sigs = get_bug_signals(identity, p)
        if sigs:
            flagged_paths.append(f"{c} ({pct:.1f}%) {p} [{', '.join(sigs)}]")
    all_paths_str = " | ".join(path_summaries)
    flagged_paths_str = " | ".join(flagged_paths)

    # Count how many products are in flagged paths
    flagged_count = 0
    for p, c in path_counts.items():
        if get_bug_signals(identity, p):
            flagged_count += c
    flagged_pct = (flagged_count / total * 100) if total else 0

    num_flavors = len(flavor_counts)

    # Bucket by top-path dominance
    if top_pct > 80:
        status = ">80% at one path (clean)"
        issue_type = "clean"
        notes = f"Top path holds {top_pct:.1f}%. Solid anchor."
        return status, issue_type, notes, " > ".join(common_prefix_all), " > ".join(common_prefix_top80), top_cat_pct, top2_cat_pct, " | ".join(top_cats), all_paths_str, flagged_paths_str

    if top_pct >= 50:
        status = "50-80% at one path (mostly clean)"
        issue_type = "mostly_clean"
        notes = f"Top path holds {top_pct:.1f}%. Minor bleed into {len(paths)-1} other path(s)."
        return status, issue_type, notes, " > ".join(common_prefix_all), " > ".join(common_prefix_top80), top_cat_pct, top2_cat_pct, " | ".join(top_cats), all_paths_str, flagged_paths_str

    # <50% — determine legitimate variance vs bugs

    # Explicit bug signals dominating
    if flagged_pct > 15:
        status = "<50% with real bugs to fix"
        issue_type = "flagged_paths_dominant"
        notes = (
            f"Top path only {top_pct:.1f}%. "
            f"{flagged_pct:.1f}% of products sit in flagged (likely wrong) paths."
        )
        return status, issue_type, notes, " > ".join(common_prefix_all), " > ".join(common_prefix_top80), top_cat_pct, top2_cat_pct, " | ".join(top_cats), all_paths_str, flagged_paths_str

    # Concentrated in one department with flavor-driven divergence
    if top_cat_pct >= 90 and num_flavors >= 3:
        status = "<50% — legitimate flavor variance"
        issue_type = "flavor_variance"
        notes = (
            f"Top path {top_pct:.1f}%, but {top_cat_pct:.1f}% of products stay under "
            f"'{top_cat}' with {num_flavors} flavors. Divergence is flavor-driven."
        )
        if flagged_paths:
            notes += f" {len(flagged_paths)} minor outlier path(s)."
        return status, issue_type, notes, " > ".join(common_prefix_all), " > ".join(common_prefix_top80), top_cat_pct, top2_cat_pct, " | ".join(top_cats), all_paths_str, flagged_paths_str

    # Concentrated in 1-2 departments
    if top2_cat_pct >= 95 and len(common_prefix_top80) >= 2:
        status = "<50% — legitimate flavor variance"
        issue_type = "flavor_variance"
        notes = (
            f"Top path {top_pct:.1f}%, but {top2_cat_pct:.1f}% of products are in top 2 "
            f"categories with shared prefix {' > '.join(common_prefix_top80)}. "
            f"{num_flavors} flavor(s)."
        )
        if flagged_paths:
            notes += f" {len(flagged_paths)} minor outlier path(s)."
        return status, issue_type, notes, " > ".join(common_prefix_all), " > ".join(common_prefix_top80), top_cat_pct, top2_cat_pct, " | ".join(top_cats), all_paths_str, flagged_paths_str

    # Truly scattered across many departments
    if top_cat_pct < 70:
        status = "<50% with real bugs to fix"
        issue_type = "scattered_across_departments"
        notes = (
            f"Top path {top_pct:.1f}%. No dominant department — top category only holds "
            f"{top_cat_pct:.1f}%. Spread across {num_top_cats} departments."
        )
        return status, issue_type, notes, " > ".join(common_prefix_all), " > ".join(common_prefix_top80), top_cat_pct, top2_cat_pct, " | ".join(top_cats), all_paths_str, flagged_paths_str

    # Some flagged paths but not dominant
    if flagged_pct > 5:
        status = "<50% with real bugs to fix"
        issue_type = "mixed_with_outliers"
        notes = (
            f"Top path {top_pct:.1f}%. {flagged_pct:.1f}% in flagged paths. "
            f"Review flagged_paths column."
        )
        return status, issue_type, notes, " > ".join(common_prefix_all), " > ".join(common_prefix_top80), top_cat_pct, top2_cat_pct, " | ".join(top_cats), all_paths_str, flagged_paths_str

    # Shallow prefix
    if len(common_prefix_all) <= 1 and len(common_prefix_top80) <= 1:
        status = "<50% with real bugs to fix"
        issue_type = "shallow_common_prefix"
        notes = (
            f"Top path {top_pct:.1f}%. Paths share minimal prefix. "
            f"Likely structural categorization errors."
        )
        return status, issue_type, notes, " > ".join(common_prefix_all), " > ".join(common_prefix_top80), top_cat_pct, top2_cat_pct, " | ".join(top_cats), all_paths_str, flagged_paths_str

    # Default: moderate divergence without clear bug signals
    status = "<50% — legitimate flavor variance"
    issue_type = "moderate_variance"
    notes = f"Top path {top_pct:.1f}%. Moderate divergence with {len(paths)} paths and {num_flavors} flavors."
    return status, issue_type, notes, " > ".join(common_prefix_all), " > ".join(common_prefix_top80), top_cat_pct, top2_cat_pct, " | ".join(top_cats), all_paths_str, flagged_paths_str


def main():
    input_csv = Path("retail_mapper/v2/full_corpus_audit.csv")
    output_csv = Path("implementation/output/path_divergence_report.csv")

    if not input_csv.exists():
        print(f"Input file not found: {input_csv}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {input_csv} ...")

    identity_paths = defaultdict(list)
    identity_flavors = defaultdict(set)
    identity_titles = defaultdict(set)

    with open(input_csv, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            identity = (row.get("product_identity_fixed") or "").strip()
            if not identity:
                identity = (row.get("product_identity_original") or "").strip()
            path = (row.get("canonical_path") or "").strip()
            flavor = (row.get("flavor") or "").strip()
            title = (row.get("title") or "").strip()

            if not identity or not path:
                continue

            identity_paths[identity].append(path)
            if flavor:
                identity_flavors[identity].add(flavor)
            if title:
                identity_titles[identity].add(title)

    print(f"Found {len(identity_paths)} unique identities.")

    rows = []
    multi_path_count = 0

    for identity in sorted(identity_paths.keys(), key=str.lower):
        paths = identity_paths[identity]
        path_counts = Counter(paths)
        total = len(paths)
        num_unique = len(path_counts)

        if num_unique <= 1:
            continue

        multi_path_count += 1
        top_path, top_count = path_counts.most_common(1)[0]
        top_pct = top_count / total * 100

        status, issue_type, notes, common_prefix_all, common_prefix_top80, top_cat_pct, top2_cat_pct, top_cats, all_paths_str, flagged_paths_str = classify_divergence(
            identity,
            path_counts,
            identity_flavors[identity],
        )

        titles_sample = " | ".join(list(identity_titles[identity])[:5])

        rows.append({
            "product_identity": identity,
            "total_products": total,
            "num_unique_paths": num_unique,
            "top_path": top_path,
            "top_path_count": top_count,
            "top_path_pct": round(top_pct, 2),
            "status": status,
            "issue_type": issue_type,
            "common_prefix_all": common_prefix_all,
            "common_prefix_top80": common_prefix_top80,
            "top_category_pct": round(top_cat_pct, 2),
            "top_2_categories_pct": round(top2_cat_pct, 2),
            "top_categories": top_cats,
            "distinct_flavors": len(identity_flavors[identity]),
            "sample_titles": titles_sample,
            "notes": notes,
            "all_paths": all_paths_str,
            "flagged_paths": flagged_paths_str,
        })

    print(f"Identities with multiple paths: {multi_path_count}")
    print(f"Writing {output_csv} ...")

    output_csv.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "product_identity",
        "total_products",
        "num_unique_paths",
        "top_path",
        "top_path_count",
        "top_path_pct",
        "status",
        "issue_type",
        "common_prefix_all",
        "common_prefix_top80",
        "top_category_pct",
        "top_2_categories_pct",
        "top_categories",
        "distinct_flavors",
        "sample_titles",
        "notes",
        "all_paths",
        "flagged_paths",
    ]

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    status_counts = Counter(r["status"] for r in rows)
    print("\n--- Summary ---")
    for status, count in status_counts.most_common():
        print(f"  {count:5d}  {status}")
    print(f"\nOutput written to: {output_csv}")


if __name__ == "__main__":
    main()
