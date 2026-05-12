from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "implementation" / "output"

PIPELINE_QUEUE_CSV = ROOT / "implementation" / "pipeline_work_queue.csv"
NO_CANDIDATES_CSV = OUTPUT_DIR / "no_candidates_diagnostic.csv"
QUERY_TERM_STATS_CSV = OUTPUT_DIR / "query_term_retail_stats.csv"
CART_QUEUE_CSV = OUTPUT_DIR / "cart_coverage_fix_queue_baseline37.csv"
SINGLE_CATEGORY_FIX_QUEUE_CSV = OUTPUT_DIR / "esha_single_category_fix_queue.csv"
HEAD_REMAP_MISSING_LEAF_QUEUE_CSV = OUTPUT_DIR / "head_remap_missing_leaf_queue.csv"
PRODUCT_MAP_SUMMARY_JSON = OUTPUT_DIR / "product_to_best_esha_full_map_summary.json"
CURRENT_STATUS_MD = ROOT / "implementation" / "CURRENT_STATUS.md"
TOP2500_COVERAGE_SUMMARY_MD = OUTPUT_DIR / "top2500_ingredient_coverage_summary.md"
TOP2500_CLEANUP_PROGRESS_CSV = OUTPUT_DIR / "top2500_cleanup_progress.csv"
RELEASE_BLOCKER_QUEUE_CSV = OUTPUT_DIR / "release_blocker_queue.csv"
WRONG_PRODUCT_QUEUE_CSV = OUTPUT_DIR / "wrong_product_accepted_queue.csv"

TOP2500_REQUIRED_INPUTS = [
    OUTPUT_DIR / "normalized_item_concept_bridge.csv",
    OUTPUT_DIR / "normalized_item_concept_bridge_summary.json",
    OUTPUT_DIR / "recipe_line_to_concept_full_summary.json",
    OUTPUT_DIR / "canonical_surface_esha_process_eval.csv",
    OUTPUT_DIR / "canonical_surface_wrongness_audit_rows.csv",
    OUTPUT_DIR / "canonical_surface_esha_cleanup_queue.csv",
    OUTPUT_DIR / "ingredient_card_candidates_ge10.csv",
]

OUT_PLAN_MD = OUTPUT_DIR / "comprehensive_fix_plan.md"
OUT_INVENTORY_CSV = OUTPUT_DIR / "comprehensive_fix_inventory.csv"


@dataclass
class InventoryRow:
    class_id: str
    layer: str
    severity: str
    row_count: str
    occurrence_count: str
    metric: str
    source_artifact: str
    symptom: str
    examples: str
    fix_wave: str
    definition_of_done: str


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def count_data_rows(path: Path) -> int:
    return len(load_csv(path))


def fmt_int(value: int) -> str:
    return f"{value:,}"


def pct(numerator: int, denominator: int) -> str:
    if not denominator:
        return "0.0%"
    return f"{(numerator / denominator) * 100:.1f}%"


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def parse_current_status_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    targets = {
        "total products": "total_products",
        "legacy assignments kept after validation": "legacy_assignments_kept",
        "fallback assignments": "fallback_assignments",
        "unassigned products": "unassigned_products",
    }
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- `"):
            continue
        for needle, key in targets.items():
            if needle in stripped:
                raw = stripped.split("`")[1].replace(",", "")
                try:
                    counts[key] = int(raw)
                except ValueError:
                    pass
    return counts


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        rows = [["-", "-", "-", "-"][: len(headers)]]

    def sanitize(value: str) -> str:
        return str(value).replace("|", " / ")

    lines = [
        "| " + " | ".join(sanitize(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        padded = row + [""] * (len(headers) - len(row))
        lines.append("| " + " | ".join(sanitize(cell) for cell in padded[: len(headers)]) + " |")
    return "\n".join(lines)


def top_counter_rows(counter: Counter[str], limit: int) -> list[list[str]]:
    return [[name, fmt_int(count)] for name, count in counter.most_common(limit)]


def build_inventory() -> tuple[list[InventoryRow], dict[str, object]]:
    pipeline_rows = [row for row in load_csv(PIPELINE_QUEUE_CSV) if (row.get("status") or "").strip() == "todo"]
    pipeline_by_id = {row["work_id"]: row for row in pipeline_rows}
    no_candidates_rows = load_csv(NO_CANDIDATES_CSV)
    query_term_rows = load_csv(QUERY_TERM_STATS_CSV)
    cart_rows = load_csv(CART_QUEUE_CSV)
    wrong_product_rows = load_csv(WRONG_PRODUCT_QUEUE_CSV)
    single_category_rows = load_csv(SINGLE_CATEGORY_FIX_QUEUE_CSV)
    missing_leaf_rows = load_csv(HEAD_REMAP_MISSING_LEAF_QUEUE_CSV)
    product_map_summary = load_json(PRODUCT_MAP_SUMMARY_JSON)
    current_status_counts = parse_current_status_counts(read_text(CURRENT_STATUS_MD))

    inventory: list[InventoryRow] = []

    def add_pipeline_item(work_id: str, layer: str, symptom: str, fix_wave: str) -> None:
        row = pipeline_by_id[work_id]
        inventory.append(
            InventoryRow(
                class_id=work_id,
                layer=layer,
                severity=row.get("priority", ""),
                row_count=row.get("row_count", ""),
                occurrence_count=row.get("occurrence_count", ""),
                metric=row.get("percent_of_current_debt", ""),
                source_artifact=str(PIPELINE_QUEUE_CSV),
                symptom=symptom,
                examples=row.get("examples", ""),
                fix_wave=fix_wave,
                definition_of_done=row.get("definition_of_done", ""),
            )
        )

    missing_top2500_inputs = [str(path.relative_to(ROOT)) for path in TOP2500_REQUIRED_INPUTS if not path.exists()]
    top2500_summary_text = read_text(TOP2500_COVERAGE_SUMMARY_MD)
    coverage_zeroed = "audited_top_n: 0" in top2500_summary_text and "top_0_occurrences: 0" in top2500_summary_text
    inventory.append(
        InventoryRow(
            class_id="observability_top2500_coverage_invalid",
            layer="observability",
            severity="P0",
            row_count="",
            occurrence_count="",
            metric=f"missing_inputs={len(missing_top2500_inputs)}; zeroed_output={'yes' if coverage_zeroed else 'no'}",
            source_artifact=f"{TOP2500_COVERAGE_SUMMARY_MD}; {', '.join(missing_top2500_inputs)}",
            symptom="The top-ingredient coverage audit is currently lying with zero coverage because required upstream files are missing.",
            examples=", ".join(Path(path).name for path in missing_top2500_inputs),
            fix_wave="wave_0_truth_and_observability",
            definition_of_done="Coverage audit refuses to emit fake zero rows; all required upstream files exist or the build fails loud.",
        )
    )

    release_source_rows = count_data_rows(TOP2500_CLEANUP_PROGRESS_CSV)
    release_queue_rows = count_data_rows(RELEASE_BLOCKER_QUEUE_CSV)
    inventory.append(
        InventoryRow(
            class_id="observability_release_blocker_invalid",
            layer="observability",
            severity="P0",
            row_count=str(release_queue_rows),
            occurrence_count="",
            metric=f"source_rows={release_source_rows}",
            source_artifact=f"{TOP2500_CLEANUP_PROGRESS_CSV}; {RELEASE_BLOCKER_QUEUE_CSV}",
            symptom="The release blocker queue is effectively blank because its source file only has a header row.",
            examples="release_blocker_queue.csv currently contains only a newline; top2500_cleanup_progress.csv has no data rows",
            fix_wave="wave_0_truth_and_observability",
            definition_of_done="Release blocker builder either has a real populated source or fails loud with an explicit invalid-state message.",
        )
    )

    summary_rows = int(product_map_summary.get("rows") or 0)
    summary_assigned_after = int(product_map_summary.get("assigned_after") or 0)
    summary_unassigned = max(summary_rows - summary_assigned_after, 0)
    current_status_unassigned = current_status_counts.get("unassigned_products", 0)
    inventory.append(
        InventoryRow(
            class_id="observability_whole_map_count_mismatch",
            layer="observability",
            severity="P0",
            row_count=fmt_int(summary_rows),
            occurrence_count=fmt_int(summary_unassigned),
            metric=f"CURRENT_STATUS_unassigned={fmt_int(current_status_unassigned)} vs summary_json_unassigned={fmt_int(summary_unassigned)}",
            source_artifact=f"{CURRENT_STATUS_MD}; {PRODUCT_MAP_SUMMARY_JSON}",
            symptom="The whole-map status docs disagree on how many products are still unassigned.",
            examples=f"CURRENT_STATUS says {fmt_int(current_status_unassigned)} unassigned; summary json implies {fmt_int(summary_unassigned)}",
            fix_wave="wave_0_truth_and_observability",
            definition_of_done="CURRENT_STATUS and the summary json report the same artifact and the same counts.",
        )
    )

    add_pipeline_item(
        "product_covered_needs_contract_audit",
        "product_contract",
        "Automatic product coverage is still unsafe because many covered cards do not yet encode subtype/form guardrails.",
        "wave_1_product_safety_contracts",
    )
    add_pipeline_item(
        "product_contract_failed_candidates",
        "product_contract",
        "These are already-proven wrong buys, not missing coverage.",
        "wave_1_product_safety_contracts",
    )
    add_pipeline_item(
        "product_gap_no_card",
        "product_contract",
        "There is no approved product contract for many reachable ingredients, which forces unsafe substitutions or invisible gaps.",
        "wave_5_store_coverage_and_external_gap_policy",
    )
    add_pipeline_item(
        "product_gap_no_product",
        "product_contract",
        "The catalog path currently finds no safe buyable product for these rows.",
        "wave_5_store_coverage_and_external_gap_policy",
    )
    add_pipeline_item(
        "product_gap_external_catalog",
        "product_contract",
        "These rows need explicit external-catalog or manual-gap policy instead of pretending a local store product exists.",
        "wave_5_store_coverage_and_external_gap_policy",
    )
    add_pipeline_item(
        "recipe_true_alternatives_other",
        "recipe_normalization",
        "Large blocks of recipe lines still collapse legitimate alternatives into noisy unresolved text.",
        "wave_2_recipe_normalization_and_parser",
    )
    add_pipeline_item(
        "recipe_dictionary_gaps",
        "recipe_normalization",
        "Common recipe concepts still do not map cleanly into the dictionary or supplemental concept layer.",
        "wave_2_recipe_normalization_and_parser",
    )
    add_pipeline_item(
        "recipe_component_splits_other",
        "recipe_normalization",
        "Composite ingredient lines are still being carried forward unsafely instead of being split or forced manual.",
        "wave_2_recipe_normalization_and_parser",
    )
    add_pipeline_item(
        "parser_fragment_review",
        "parser",
        "The parser still emits dangling fragments that poison downstream concept and product resolution.",
        "wave_2_recipe_normalization_and_parser",
    )
    add_pipeline_item(
        "parser_review_needed",
        "parser",
        "Open parser failures still need either deterministic repair or explicit skip policy.",
        "wave_2_recipe_normalization_and_parser",
    )
    add_pipeline_item(
        "recipe_qualified_tuple_review",
        "recipe_normalization",
        "Qualified variants like form/state/fat-level are still being flattened too early.",
        "wave_2_recipe_normalization_and_parser",
    )

    bucket_counter = Counter(row.get("bucket", "") for row in no_candidates_rows)
    zero_rewrite_available = bucket_counter.get("zero_matches_rewrite_available", 0)
    zero_no_rewrite = bucket_counter.get("zero_matches_no_rewrite", 0)
    inventory.append(
        InventoryRow(
            class_id="retrieval_zero_matches_rewrite_available",
            layer="retrieval",
            severity="P1",
            row_count=fmt_int(zero_rewrite_available),
            occurrence_count="",
            metric=pct(zero_rewrite_available, len(no_candidates_rows)),
            source_artifact=str(NO_CANDIDATES_CSV),
            symptom="Most no-candidate packs already have a known rewrite path; the rewrite work simply has not been driven through.",
            examples="prepared_food, beverage, meat, fruit, dessert_snack, spice",
            fix_wave="wave_3_retrieval_query_rewrites",
            definition_of_done="Known safe rewrites are materialized and the rewrite-available bucket is driven toward zero for ordinary grocery surfaces.",
        )
    )
    inventory.append(
        InventoryRow(
            class_id="retrieval_zero_matches_no_rewrite",
            layer="retrieval",
            severity="P2",
            row_count=fmt_int(zero_no_rewrite),
            occurrence_count="",
            metric=pct(zero_no_rewrite, len(no_candidates_rows)),
            source_artifact=str(NO_CANDIDATES_CSV),
            symptom="A smaller but still real set of packs has no good rewrite yet and needs manual retrieval policy or gap policy.",
            examples="fruit, prepared_food, cheese, nut_seed, dessert_snack, meat",
            fix_wave="wave_3_retrieval_query_rewrites",
            definition_of_done="Every no-rewrite pack has either a safe query plan, a contract-scoped external catalog path, or an explicit manual gap.",
        )
    )

    query_term_rows.sort(
        key=lambda row: (
            int(row.get("selected_drop_count") or 0),
            int(row.get("strict_zero_count") or 0),
        ),
        reverse=True,
    )
    top_query_terms = ", ".join(
        f"{row['term']}({row['selected_drop_count']})" for row in query_term_rows[:10]
    )
    inventory.append(
        InventoryRow(
            class_id="retrieval_query_term_poison",
            layer="retrieval",
            severity="P1",
            row_count=fmt_int(len(query_term_rows)),
            occurrence_count=fmt_int(sum(int(row.get("selected_drop_count") or 0) for row in query_term_rows)),
            metric="top-ranked by selected_drop_count",
            source_artifact=str(QUERY_TERM_STATS_CSV),
            symptom="Core query terms are still poisoning retail retrieval and forcing rescue drops or category leaks.",
            examples=top_query_terms,
            fix_wave="wave_3_retrieval_query_rewrites",
            definition_of_done="High-poison terms have explicit demote/drop/query-rewrite policy and no longer dominate strict-zero or rescue behavior.",
        )
    )

    flagged_single_category = [row for row in single_category_rows if (row.get("needs_fix") or "").strip() == "1"]
    family_counter = Counter(row.get("family", "") for row in flagged_single_category)
    inventory.append(
        InventoryRow(
            class_id="whole_map_single_category_spread",
            layer="whole_map",
            severity="P1",
            row_count=fmt_int(len(flagged_single_category)),
            occurrence_count="",
            metric=f"codes_scanned={fmt_int(len(single_category_rows))}",
            source_artifact=str(SINGLE_CATEGORY_FIX_QUEUE_CSV),
            symptom="Too many ESHA queries are still broad enough to spray across unrelated retail categories.",
            examples=", ".join(f"{name}({count})" for name, count in family_counter.most_common(8)),
            fix_wave="wave_4_whole_map_query_singularity_and_identity",
            definition_of_done="Flagged ESHA codes collapse toward a dominant category with identity-safe queries instead of broad category spray.",
        )
    )

    quarantine_counter = Counter(row.get("quarantine_reason", "") for row in missing_leaf_rows)
    inventory.append(
        InventoryRow(
            class_id="whole_map_missing_leaf_quarantine",
            layer="whole_map",
            severity="P1",
            row_count=fmt_int(len(missing_leaf_rows)),
            occurrence_count="",
            metric="head_remap_quarantine_rows",
            source_artifact=str(HEAD_REMAP_MISSING_LEAF_QUEUE_CSV),
            symptom="A large missing-leaf backlog still blocks exact head routing for common retail products.",
            examples=", ".join(f"{name}({count})" for name, count in quarantine_counter.most_common(8)),
            fix_wave="wave_4_whole_map_query_singularity_and_identity",
            definition_of_done="Missing-leaf quarantine rows are either promoted to safe heads or kept explicitly quarantined with visible rationale.",
        )
    )

    inventory.append(
        InventoryRow(
            class_id="whole_map_unassigned_products",
            layer="whole_map",
            severity="P1",
            row_count=fmt_int(current_status_counts.get("total_products", summary_rows)),
            occurrence_count=fmt_int(current_status_unassigned or summary_unassigned),
            metric="unassigned_product_backlog",
            source_artifact=f"{CURRENT_STATUS_MD}; {PRODUCT_MAP_SUMMARY_JSON}",
            symptom="The whole-corpus assignment layer still leaves a large tail of products without safe ESHA assignment.",
            examples="milk subtype routing, produce leaf specificity, pepper jelly/preserves, category-singularity cleanup",
            fix_wave="wave_4_whole_map_query_singularity_and_identity",
            definition_of_done="Unassigned product count is materially reduced by targeted routers, not by forced-coverage lies.",
        )
    )

    gap_bucket_counter = Counter(row.get("gap_bucket", "") for row in cart_rows)
    inventory.append(
        InventoryRow(
            class_id="cart_store_coverage_tail",
            layer="cart",
            severity="P2",
            row_count=fmt_int(len(cart_rows)),
            occurrence_count="",
            metric=", ".join(f"{name}={count}" for name, count in sorted(gap_bucket_counter.items())),
            source_artifact=str(CART_QUEUE_CSV),
            symptom="The current 37-recipe cart queue still has explicit store misses even after the earlier cleanup passes.",
            examples=", ".join(f"{row['label']}[{row['gap_scope']}]" for row in cart_rows),
            fix_wave="wave_5_store_coverage_and_external_gap_policy",
            definition_of_done="Ordinary grocery lines price on at least one store, and missing cases are explicit specialty/manual gaps instead of silent dead ends.",
        )
    )

    if wrong_product_rows:
        inventory.append(
            InventoryRow(
                class_id="observability_wrong_product_queue_bootstrapped",
                layer="observability",
                severity="P1",
                row_count=fmt_int(len(wrong_product_rows)),
                occurrence_count=f"{pipeline_by_id['product_covered_needs_contract_audit']['occurrence_count']} + {pipeline_by_id['product_contract_failed_candidates']['occurrence_count']}",
                metric="pipeline-derived false-accept queue present",
                source_artifact=str(WRONG_PRODUCT_QUEUE_CSV),
                symptom="The bundle now has an explicit wrong-product queue, but it is still derived from pipeline evidence rather than a live recipe/store join.",
                examples="wrong_product_accepted and covered_product_contract_needs_audit rows",
                fix_wave="wave_0_truth_and_observability",
                definition_of_done="Wrong-product queue is generated from live recipe/store selections with selected product, violated rule, and reject reason.",
            )
        )
    else:
        inventory.append(
            InventoryRow(
                class_id="observability_missing_wrong_product_recipe_audit",
                layer="observability",
                severity="P0",
                row_count=f"{pipeline_by_id['product_covered_needs_contract_audit']['row_count']} + {pipeline_by_id['product_contract_failed_candidates']['row_count']}",
                occurrence_count=f"{pipeline_by_id['product_covered_needs_contract_audit']['occurrence_count']} + {pipeline_by_id['product_contract_failed_candidates']['occurrence_count']}",
                metric="cart gap queue only measures misses, not false accepts",
                source_artifact=f"{PIPELINE_QUEUE_CSV}; {CART_QUEUE_CSV}",
                symptom="The bundle tracks missing products directly, but it does not yet emit a recipe-level wrong-product-accepted queue.",
                examples="covered product reachability is not product safety until contracts are audited",
                fix_wave="wave_0_truth_and_observability",
                definition_of_done="A generated wrong-product queue exists for recipe/store selections, with selected product, violated rule, and reject reason.",
            )
        )

    meta = {
        "pipeline_rows": pipeline_rows,
        "pipeline_by_id": pipeline_by_id,
        "no_candidates_rows": no_candidates_rows,
        "query_term_rows": query_term_rows,
        "cart_rows": cart_rows,
        "wrong_product_rows": wrong_product_rows,
        "single_category_rows": single_category_rows,
        "missing_leaf_rows": missing_leaf_rows,
        "product_map_summary": product_map_summary,
        "current_status_counts": current_status_counts,
        "missing_top2500_inputs": missing_top2500_inputs,
    }
    return inventory, meta


def render_plan(inventory: list[InventoryRow], meta: dict[str, object]) -> str:
    pipeline_rows: list[dict[str, str]] = meta["pipeline_rows"]  # type: ignore[assignment]
    query_term_rows: list[dict[str, str]] = meta["query_term_rows"]  # type: ignore[assignment]
    no_candidates_rows: list[dict[str, str]] = meta["no_candidates_rows"]  # type: ignore[assignment]
    cart_rows: list[dict[str, str]] = meta["cart_rows"]  # type: ignore[assignment]
    wrong_product_rows: list[dict[str, str]] = meta["wrong_product_rows"]  # type: ignore[assignment]
    current_status_counts: dict[str, int] = meta["current_status_counts"]  # type: ignore[assignment]
    missing_top2500_inputs: list[str] = meta["missing_top2500_inputs"]  # type: ignore[assignment]
    product_map_summary: dict[str, object] = meta["product_map_summary"]  # type: ignore[assignment]

    pipeline_by_layer = Counter(row.get("layer", "") for row in pipeline_rows)
    pipeline_by_priority = Counter(row.get("priority", "") for row in pipeline_rows)
    no_candidates_by_bucket = Counter(row.get("bucket", "") for row in no_candidates_rows)
    rewrite_available_families = Counter(
        row.get("family", "")
        for row in no_candidates_rows
        if row.get("bucket", "") == "zero_matches_rewrite_available"
    )
    top_query_rows = query_term_rows[:10]
    summary_rows = int(product_map_summary.get("rows") or 0)
    summary_assigned_after = int(product_map_summary.get("assigned_after") or 0)
    summary_unassigned = max(summary_rows - summary_assigned_after, 0)

    inventory_rows = [
        [
            item.class_id,
            item.layer,
            item.severity,
            item.row_count or "-",
            item.occurrence_count or "-",
            item.metric or "-",
        ]
        for item in inventory
    ]

    top_pipeline_rows = sorted(
        pipeline_rows,
        key=lambda row: float((row.get("percent_of_current_debt") or "0").rstrip("%") or 0),
        reverse=True,
    )[:10]

    lines = [
        f"# Comprehensive Fix Plan ({date.today().isoformat()})",
        "",
        "## Bottom Line",
        "",
        "The bundle is not one bug away from done. It has six active failure classes plus three observability failures that are currently making the audit lie about coverage or progress.",
        "",
        "The biggest mistake so far was treating `coverage` as if it meant `correct product selection`. The current bundle has explicit queues for product-contract false accepts, missing contracts, retrieval poison, recipe normalization debt, whole-map identity spread, and store coverage tail work. Those need to be driven as separate waves.",
        "",
        "## Source Of Truth Used For This Plan",
        "",
        "- `implementation/pipeline_work_queue.csv`",
        "- `implementation/output/no_candidates_diagnostic.csv`",
        "- `implementation/output/query_term_retail_stats.csv`",
        "- `implementation/output/esha_single_category_fix_queue.csv`",
        "- `implementation/output/head_remap_missing_leaf_queue.csv`",
        "- `implementation/output/cart_coverage_fix_queue_baseline37.csv`",
        "- `implementation/output/wrong_product_accepted_queue.csv`",
        "- `implementation/output/product_to_best_esha_full_map_summary.json`",
        "- `implementation/CURRENT_STATUS.md`",
        "",
        "## What Is Broken Right Now",
        "",
        "### 1. Observability Is Not Trustworthy Yet",
        "",
        f"- The top-ingredient coverage audit is invalid. It emits zero coverage while `{len(missing_top2500_inputs)}` required upstream files are missing.",
        "- The release blocker queue is invalid. Its source file only has a header row, and the generated queue is effectively blank.",
        f"- Whole-map counts disagree. `CURRENT_STATUS.md` says `{fmt_int(current_status_counts.get('unassigned_products', 0))}` unassigned products, while `product_to_best_esha_full_map_summary.json` implies `{fmt_int(summary_unassigned)}`.",
        (
            f"- The bundle now has a bootstrapped wrong-product queue with `{fmt_int(len(wrong_product_rows))}` rows, "
            "but it is still pipeline-derived rather than a live recipe/store join."
            if wrong_product_rows
            else "- The bundle does not yet generate a recipe-level wrong-product-accepted queue, so false confidence is still possible when cart coverage looks good."
        ),
        "",
        "### 2. Recipe Normalization And Parser Debt Is Still The Biggest Surface Area",
        "",
        markdown_table(
            ["bucket", "open work rows", "occurrences"],
            [
                ["recipe_normalization", fmt_int(pipeline_by_layer.get("recipe_normalization", 0)), "-"],
                ["parser", fmt_int(pipeline_by_layer.get("parser", 0)), "-"],
                ["quantity_policy", fmt_int(pipeline_by_layer.get("quantity_policy", 0)), "-"],
            ],
        ),
        "",
        markdown_table(
            ["work_id", "priority", "rows", "occurrences", "% current debt"],
            [
                [
                    row["work_id"],
                    row["priority"],
                    row["row_count"],
                    row["occurrence_count"],
                    row["percent_of_current_debt"],
                ]
                for row in top_pipeline_rows
                if row["layer"] in {"recipe_normalization", "parser", "quantity_policy"}
            ],
        ),
        "",
        "This is the front-end poison layer. If alternatives, dictionary gaps, component splits, and parser fragments are wrong, every downstream ESHA, product, and pricing step inherits the error.",
        "",
        "### 3. Product Safety Contracts Are Still Underspecified",
        "",
        markdown_table(
            ["work_id", "priority", "rows", "occurrences", "why it matters"],
            [
                [
                    "product_covered_needs_contract_audit",
                    meta["pipeline_by_id"]["product_covered_needs_contract_audit"]["priority"],  # type: ignore[index]
                    meta["pipeline_by_id"]["product_covered_needs_contract_audit"]["row_count"],  # type: ignore[index]
                    meta["pipeline_by_id"]["product_covered_needs_contract_audit"]["occurrence_count"],  # type: ignore[index]
                    "Coverage without subtype/form rules is unsafe.",
                ],
                [
                    "product_contract_failed_candidates",
                    meta["pipeline_by_id"]["product_contract_failed_candidates"]["priority"],  # type: ignore[index]
                    meta["pipeline_by_id"]["product_contract_failed_candidates"]["row_count"],  # type: ignore[index]
                    meta["pipeline_by_id"]["product_contract_failed_candidates"]["occurrence_count"],  # type: ignore[index]
                    "These are already-proven wrong buys.",
                ],
                [
                    "product_gap_no_card",
                    meta["pipeline_by_id"]["product_gap_no_card"]["priority"],  # type: ignore[index]
                    meta["pipeline_by_id"]["product_gap_no_card"]["row_count"],  # type: ignore[index]
                    meta["pipeline_by_id"]["product_gap_no_card"]["occurrence_count"],  # type: ignore[index]
                    "No approved product contract exists.",
                ],
                [
                    "product_gap_no_product",
                    meta["pipeline_by_id"]["product_gap_no_product"]["priority"],  # type: ignore[index]
                    meta["pipeline_by_id"]["product_gap_no_product"]["row_count"],  # type: ignore[index]
                    meta["pipeline_by_id"]["product_gap_no_product"]["occurrence_count"],  # type: ignore[index]
                    "No safe local product is currently reachable.",
                ],
            ],
        ),
        "",
        "This is where false accepts live. The bundle already says that covered product reachability is not product safety until contracts are audited.",
        "",
        "### 4. Retrieval And Query Poison Are Still Huge",
        "",
        f"- No-candidate packs: `{fmt_int(len(no_candidates_rows))}`",
        f"- Rewrite available: `{fmt_int(no_candidates_by_bucket.get('zero_matches_rewrite_available', 0))}`",
        f"- No rewrite yet: `{fmt_int(no_candidates_by_bucket.get('zero_matches_no_rewrite', 0))}`",
        "",
        "Top rewrite-available families:",
        "",
        markdown_table(
            ["family", "count"],
            top_counter_rows(rewrite_available_families, 10),
        ),
        "",
        "Worst query poison terms by selected-drop count:",
        "",
        markdown_table(
            ["term", "selected_drop_count", "strict_zero_count", "families"],
            [
                [
                    row["term"],
                    row["selected_drop_count"],
                    row["strict_zero_count"],
                    row["families"],
                ]
                for row in top_query_rows
            ],
        ),
        "",
        "This is the reason generic terms like `milk`, `cheese`, `water`, `salt`, `topping`, `sandwich`, and `butter` still blow queries open unless they are demoted or rewritten.",
        "",
        "### 5. Whole-Corpus ESHA Routing Is Safer But Still Too Broad",
        "",
        f"- Total product rows in current whole-map summary: `{fmt_int(summary_rows)}`",
        f"- Assigned after current rebuild: `{fmt_int(summary_assigned_after)}`",
        f"- Unassigned tail still outstanding: `{fmt_int(current_status_counts.get('unassigned_products', summary_unassigned))}`",
        f"- Single-category fix queue rows: `{fmt_int(len(meta['single_category_rows']))}` with `{fmt_int(len([r for r in meta['single_category_rows'] if (r.get('needs_fix') or '').strip() == '1']))}` flagged",
        f"- Missing-leaf quarantine rows: `{fmt_int(len(meta['missing_leaf_rows']))}`",
        "",
        "The bundle’s own current-status note already calls out the remaining whole-map high-priority work:",
        "",
        "- milk subtype routing",
        "- produce leaf specificity",
        "- jelly / preserve / spread routing",
        "- category-singularity cleanup",
        "- unassigned reduction by targeted routers",
        "",
        "### 6. Cart Coverage Tail Is Small But Not The Full Story",
        "",
        f"- Current 37-recipe cart gap queue rows: `{fmt_int(len(cart_rows))}`",
        "",
        markdown_table(
            ["recipe", "label", "gap_scope", "gap_bucket"],
            [
                [row["recipe_name"], row["label"], row["gap_scope"], row["gap_bucket"]]
                for row in cart_rows
            ],
        ),
        "",
        "This queue is only the visible tail of store misses. It does not count wrong accepted products. That is why a recipe can show `100%` coverage and still buy the wrong thing.",
        "",
        "## Inventory",
        "",
        markdown_table(
            ["class_id", "layer", "severity", "rows", "occurrences", "metric"],
            inventory_rows,
        ),
        "",
        "## Fix Waves",
        "",
        "### Wave 0: Truth And Observability",
        "",
        "1. Make broken audits fail loud instead of silently emitting lies.",
        "2. Reconcile the whole-map count mismatch between `CURRENT_STATUS.md` and `product_to_best_esha_full_map_summary.json`.",
        "3. Add a generated `wrong_product_accepted_queue` for recipe/store selections so false accepts are enumerated the same way misses are.",
        "4. Stop using `top2500_ingredient_coverage_summary.md` and `release_blocker_queue.csv` as truth until their upstreams are repaired.",
        "",
        "### Wave 1: Product Safety Contracts",
        "",
        "1. Drive `product_covered_needs_contract_audit` first.",
        "2. Then clear `product_contract_failed_candidates` because those are proven misbuys.",
        "3. Every contract must encode required tokens, forbidden tokens, allowed categories, positive examples, and negative examples.",
        "4. Wrong-family substitutions must fail hard instead of counting as success.",
        "",
        "### Wave 2: Recipe Normalization And Parser",
        "",
        "1. Clear the big normalization buckets in order: alternatives, dictionary gaps, component splits.",
        "2. Repair parser fragments before concept matching.",
        "3. Preserve qualified form/state/fat-level variants instead of flattening them away.",
        "",
        "### Wave 3: Retrieval Rewrites And Query Poison",
        "",
        "1. Drive the `zero_matches_rewrite_available` bucket down first.",
        "2. Demote or rewrite the top poison terms from `query_term_retail_stats.csv`.",
        "3. For the no-rewrite tail, force explicit manual or external-gap policy instead of open-ended retrieval.",
        "",
        "### Wave 4: Whole-Map Query Singularity And Identity",
        "",
        "1. Work `esha_single_category_fix_queue.csv` by dominant off-category spray.",
        "2. Work `head_remap_missing_leaf_queue.csv` by quarantine reason frequency.",
        "3. Attack the remaining whole-map priorities already called out in `CURRENT_STATUS.md`.",
        "",
        "### Wave 5: Store Coverage And External Gap Policy",
        "",
        "1. Clear the remaining cart misses.",
        "2. Clear `product_gap_no_card` and `product_gap_no_product` for ordinary grocery items.",
        "3. Keep `product_gap_external_catalog` visible instead of silently substituting local garbage.",
        "",
        "### Wave 6: Acceptance Gates",
        "",
        "The system is only allowed to claim success when all of these are true:",
        "",
        "- no invalid observability artifacts are being treated as truth",
        "- wrong-product queue is empty for the current audited set at P0 severity",
        "- contract-failed candidate queue is empty or explicitly manual/external",
        "- ordinary grocery cart misses are gone",
        "- whole-map and retrieval metrics are trending down by generated artifacts, not by anecdotes",
        "",
        "## First Targets, In Order",
        "",
        "1. Repair observability so the audit stops lying.",
        "2. Build the missing wrong-product recipe/store queue.",
        "3. Clear `product_covered_needs_contract_audit`.",
        "4. Clear `product_contract_failed_candidates`.",
        "5. Clear the top recipe normalization buckets.",
        "6. Drive the rewrite-available retrieval bucket down.",
        "7. Collapse single-category ESHA spray and missing-leaf quarantine.",
        "8. Only then trust the cart coverage queue as a tail instead of the whole picture.",
        "",
    ]
    return "\n".join(lines)


def write_inventory_csv(rows: list[InventoryRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "class_id",
                "layer",
                "severity",
                "row_count",
                "occurrence_count",
                "metric",
                "source_artifact",
                "symptom",
                "examples",
                "fix_wave",
                "definition_of_done",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def main() -> None:
    inventory, meta = build_inventory()
    plan_text = render_plan(inventory, meta)
    OUT_PLAN_MD.write_text(plan_text + "\n", encoding="utf-8")
    write_inventory_csv(inventory, OUT_INVENTORY_CSV)
    print(f"wrote {OUT_PLAN_MD}")
    print(f"wrote {OUT_INVENTORY_CSV}")


if __name__ == "__main__":
    main()
