from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"


@dataclass(frozen=True)
class ResolverArtifacts:
    """Canonical artifact paths for the recipe -> concept -> product funnel."""

    recipe_funnel_db: Path = OUTPUT / "recipe_funnel.db"
    recipe_qa_db: Path = ROOT.parent / "data" / "recipe_qa.db"
    master_products_db: Path = ROOT.parent / "data" / "master_products.db"
    fndds_main_food_desc_csv: Path = ROOT.parent / "data" / "fndds" / "MainFoodDesc16.csv"
    fndds_sr_links_csv: Path = ROOT.parent / "data" / "fndds" / "FNDDSSRLinks.csv"
    dictionary_csv: Path = OUTPUT / "sr28_BASE_DICTIONARY_CODEX.csv"
    clean_dictionary_csv: Path = OUTPUT / "canonical_concept_dictionary.csv"
    identity_bridge_db: Path = OUTPUT / "identity_bridge.db"
    supplemental_concepts_csv: Path = ROOT / "supplemental_concepts_seed.csv"
    approved_normalization_rules_csv: Path = ROOT / "approved_normalization_rules.csv"
    approved_product_contracts_csv: Path = ROOT / "approved_product_contracts.csv"
    product_family_safety_rules_csv: Path = ROOT / "product_family_safety_rules.csv"
    reviewed_nutrition_anchors_csv: Path = ROOT / "reviewed_nutrition_anchors.csv"
    reviewed_density_bridge_csv: Path = ROOT / "reviewed_density_bridge.csv"
    reviewed_external_catalog_items_csv: Path = ROOT / "reviewed_external_catalog_items.csv"
    reviewed_household_unit_gram_rules_csv: Path = (
        ROOT.parent / "recipe_pricing" / "reviewed_household_portions.csv"
    )
    legacy_reviewed_household_unit_gram_rules_csv: Path = ROOT / "reviewed_household_unit_gram_rules.csv"
    reviewed_quantity_policies_csv: Path = ROOT / "reviewed_quantity_policies.csv"
    reviewed_sr28_nutrition_fallbacks_csv: Path = ROOT / "reviewed_sr28_nutrition_fallbacks.csv"
    reviewed_to_taste_defaults_csv: Path = ROOT / "reviewed_to_taste_defaults.csv"
    reviewed_work_item_ledger_csv: Path = ROOT / "reviewed_work_item_ledger.csv"
    reviewed_recipe_line_patches_csv: Path = ROOT / "reviewed_recipe_line_patches.csv"
    product_cards_csv: Path = OUTPUT / "product_card_coverage_97_cards.csv"
    product_contract_audit_csv: Path = OUTPUT / "product_contract_audit.csv"
    product_nutrition_state_db: Path = OUTPUT / "product_nutrition_state.db"
    pipeline_work_queue_csv: Path = ROOT / "pipeline_work_queue.csv"
    recipe_calculation_work_queue_csv: Path = ROOT / "recipe_calculation_work_queue.csv"
    funnel_state_db: Path = OUTPUT / "funnel_state.db"
    calculator_recipe_status_csv: Path = OUTPUT / "calculator_recipe_status.csv"
    calculator_ready_recipe_ids_csv: Path = OUTPUT / "calculator_ready_recipe_ids.csv"
    calculator_attack_recipe_ids_csv: Path = OUTPUT / "calculator_attack_recipe_ids.csv"
    calculator_baseline_summary_json: Path = OUTPUT / "calculator_baseline_summary.json"
    ge10_line_mapping_csv: Path = OUTPUT / "recipe_line_to_concept_ge10.csv"
    ge10_line_mapping_misses_csv: Path = OUTPUT / "recipe_line_to_concept_ge10_misses.csv"
    ge10_line_mapping_summary_json: Path = OUTPUT / "recipe_line_to_concept_ge10_summary.json"
    ge10_line_mapping_report_md: Path = OUTPUT / "recipe_line_to_concept_ge10_report.md"
    full_line_mapping_csv: Path = OUTPUT / "recipe_line_to_concept_full.csv"
    full_line_mapping_misses_csv: Path = OUTPUT / "recipe_line_to_concept_full_misses.csv"
    full_line_mapping_summary_json: Path = OUTPUT / "recipe_line_to_concept_full_summary.json"
    full_line_mapping_report_md: Path = OUTPUT / "recipe_line_to_concept_full_report.md"
    full_calculation_audit_db: Path = OUTPUT / "recipe_calculation_audit_full.db"
    recipe_qa_nutrition_audit_db: Path = OUTPUT / "recipe_qa_nutrition_calculation_audit.db"
    recipe_qa_nutrition_audit_json: Path = OUTPUT / "recipe_qa_nutrition_calculation_audit.json"
    recipe_unlock_frontier_csv: Path = OUTPUT / "recipe_unlock_frontier.csv"
    recipe_unlock_frontier_summary_json: Path = OUTPUT / "recipe_unlock_frontier_summary.json"
    recipe_unlock_frontier_examples_csv: Path = OUTPUT / "recipe_unlock_frontier_examples.csv"
    funnel_validation_report_json: Path = OUTPUT / "funnel_validation_report.json"
    funnel_validation_report_md: Path = OUTPUT / "funnel_validation_report.md"
    attack_surface_csv: Path = OUTPUT / "attack_surface_current.csv"
    ready_for_audit_csv: Path = OUTPUT / "ready_for_audit_current.csv"
    regressions_csv: Path = OUTPUT / "regressions_current.csv"
    work_item_ledger_summary_json: Path = OUTPUT / "work_item_ledger_summary.json"
    recipeqa_item_review_ge10_csv: Path = OUTPUT / "recipeqa_item_review_ge10.csv"
    normalized_item_bridge_csv: Path = OUTPUT / "normalized_item_concept_bridge.csv"
    normalized_item_bridge_db: Path = OUTPUT / "normalized_item_concept_bridge.db"
    normalized_item_bridge_summary_json: Path = OUTPUT / "normalized_item_concept_bridge_summary.json"
    full_line_item_candidate_cache_csv: Path = OUTPUT / "full_line_item_candidate_cache.csv"
    full_line_item_candidate_cache_db: Path = OUTPUT / "full_line_item_candidate_cache.db"
    normalized_item_line_rollup_csv: Path = OUTPUT / "normalized_item_line_rollup.csv"
    normalized_item_line_rollup_summary_json: Path = OUTPUT / "normalized_item_line_rollup_summary.json"
    normalized_item_attack_surface_csv: Path = OUTPUT / "normalized_item_attack_surface_ge10.csv"
    normalized_item_attack_surface_summary_json: Path = OUTPUT / "normalized_item_attack_surface_ge10_summary.json"
    crf_model_path: Path = OUTPUT / "crf_model.crfsuite"
    crf_training_data_path: Path = OUTPUT / "crf_training_data.jsonl"
    crf_candidate_alias_rules_csv: Path = OUTPUT / "crf_candidate_alias_rules.csv"
    crf_tail_classification_csv: Path = OUTPUT / "crf_tail_classification.csv"
    concept_candidate_scratch_dir: Path = OUTPUT / "scratch" / "20260413_fndds_concept_expansion"
    proposed_concepts_csv: Path = OUTPUT / "scratch" / "20260413_fndds_concept_expansion" / "proposed_concepts.csv"
    proposed_normalization_rules_csv: Path = OUTPUT / "scratch" / "20260413_fndds_concept_expansion" / "proposed_normalization_rules.csv"
    proposed_product_contracts_csv: Path = OUTPUT / "scratch" / "20260413_fndds_concept_expansion" / "proposed_product_contracts.csv"
    concept_candidate_quarantine_csv: Path = OUTPUT / "scratch" / "20260413_fndds_concept_expansion" / "quarantined_rows.csv"
    proposed_local_label_concepts_csv: Path = OUTPUT / "scratch" / "20260413_fndds_concept_expansion" / "proposed_local_label_concepts.csv"
    proposed_local_label_rules_csv: Path = OUTPUT / "scratch" / "20260413_fndds_concept_expansion" / "proposed_local_label_rules.csv"
    proposed_local_label_contracts_csv: Path = OUTPUT / "scratch" / "20260413_fndds_concept_expansion" / "proposed_local_label_contracts.csv"
    local_label_unmatched_csv: Path = OUTPUT / "scratch" / "20260413_fndds_concept_expansion" / "local_label_unmatched.csv"
    proposed_seed_parents_csv: Path = ROOT / "proposed_seed_parents.csv"
    merge_ready_dir: Path = OUTPUT / "scratch" / "20260413_fndds_concept_expansion" / "merge_ready"
    merge_ready_auto_concepts_csv: Path = OUTPUT / "scratch" / "20260413_fndds_concept_expansion" / "merge_ready" / "merge_ready_auto_concepts.csv"
    merge_ready_auto_rules_csv: Path = OUTPUT / "scratch" / "20260413_fndds_concept_expansion" / "merge_ready" / "merge_ready_auto_rules.csv"
    merge_ready_auto_contracts_csv: Path = OUTPUT / "scratch" / "20260413_fndds_concept_expansion" / "merge_ready" / "merge_ready_auto_contracts.csv"
    merge_ready_review_concepts_csv: Path = OUTPUT / "scratch" / "20260413_fndds_concept_expansion" / "merge_ready" / "merge_ready_review_concepts.csv"
    merge_ready_review_rules_csv: Path = OUTPUT / "scratch" / "20260413_fndds_concept_expansion" / "merge_ready" / "merge_ready_review_rules.csv"
    merge_ready_review_contracts_csv: Path = OUTPUT / "scratch" / "20260413_fndds_concept_expansion" / "merge_ready" / "merge_ready_review_contracts.csv"
    merge_rejected_csv: Path = OUTPUT / "scratch" / "20260413_fndds_concept_expansion" / "merge_ready" / "merge_rejected.csv"
    proposed_parent_contract_updates_csv: Path = OUTPUT / "scratch" / "20260413_fndds_concept_expansion" / "merge_ready" / "proposed_parent_contract_updates.csv"
    canonical_pseudos_csv: Path = ROOT / "canonical_pseudos.csv"
    non_food_words_csv: Path = ROOT / "non_food_words.csv"
    each_weights_csv: Path = ROOT / "each_weights.csv"
    product_code_tags_db: Path = ROOT.parent / "data" / "master_products.db"
    cross_verify_disputes_csv: Path = OUTPUT / "cross_verify_disputes.csv"
    pseudo_candidates_csv: Path = OUTPUT / "pseudo_candidates.csv"
    canonical_unknown_csv: Path = OUTPUT / "canonical_unknown.csv"


DEFAULT_ARTIFACTS = ResolverArtifacts()


REVIEWED_REGISTRIES = {
    "normalization": DEFAULT_ARTIFACTS.approved_normalization_rules_csv,
    "product_contracts": DEFAULT_ARTIFACTS.approved_product_contracts_csv,
    "product_family_safety_rules": DEFAULT_ARTIFACTS.product_family_safety_rules_csv,
    "nutrition_anchors": DEFAULT_ARTIFACTS.reviewed_nutrition_anchors_csv,
    "density_bridge": DEFAULT_ARTIFACTS.reviewed_density_bridge_csv,
    "external_catalog": DEFAULT_ARTIFACTS.reviewed_external_catalog_items_csv,
    "household_units": DEFAULT_ARTIFACTS.reviewed_household_unit_gram_rules_csv,
    "quantity_policies": DEFAULT_ARTIFACTS.reviewed_quantity_policies_csv,
    "sr28_fallbacks": DEFAULT_ARTIFACTS.reviewed_sr28_nutrition_fallbacks_csv,
    "to_taste_defaults": DEFAULT_ARTIFACTS.reviewed_to_taste_defaults_csv,
    "work_item_ledger": DEFAULT_ARTIFACTS.reviewed_work_item_ledger_csv,
    "recipe_line_patches": DEFAULT_ARTIFACTS.reviewed_recipe_line_patches_csv,
}


CANONICAL_SCRIPTS = {
    "map_recipe_lines": ROOT / "map_recipe_lines_to_concepts.py",
    "build_product_cards": ROOT / "build_product_card_coverage_85.py",
    "audit_product_contracts": ROOT / "audit_product_contracts.py",
    "audit_full_calculation": ROOT / "audit_full_recipe_calculation.py",
    "audit_recipe_qa_nutrition": ROOT / "audit_recipe_qa_nutrition_calculation.py",
    "build_work_queue": ROOT / "build_pipeline_work_queue.py",
    "build_recipe_calculation_work_queue": ROOT / "build_recipe_calculation_work_queue.py",
    "recipe_calculator_baseline": ROOT / "recipe_calculator_baseline.py",
    "recipe_unlock_frontier": ROOT / "recipe_unlock_frontier.py",
    "validate_funnel": ROOT / "run_funnel_validation.py",
    "audit_work_item_ledger": ROOT / "audit_work_item_ledger.py",
    "family_assigner": ROOT / "family_assigner.py",
    "fuzzy_surface_resolver": ROOT / "fuzzy_surface_resolver.py",
    "build_normalized_item_bridge": ROOT / "build_normalized_item_bridge.py",
    "build_full_line_item_candidate_cache": ROOT / "build_full_line_item_candidate_cache.py",
    "build_normalized_item_line_rollup": ROOT / "build_normalized_item_line_rollup.py",
    "build_normalized_item_attack_surface": ROOT / "build_normalized_item_attack_surface.py",
    "audit_cart_identity_safety": ROOT / "audit_cart_identity_safety.py",
}


def csv_row_count(path: Path) -> int | None:
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as handle:
        return max(sum(1 for _ in csv.DictReader(handle)), 0)


def artifact_status() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for layer, path in REVIEWED_REGISTRIES.items():
        rows.append(
            {
                "layer": layer,
                "path": str(path),
                "exists": path.exists(),
                "rows": csv_row_count(path),
            }
        )
    return rows


def assert_canonical_artifacts_exist() -> None:
    missing = [row["path"] for row in artifact_status() if not row["exists"]]
    if missing:
        raise FileNotFoundError("Missing resolver artifacts: " + ", ".join(missing))
