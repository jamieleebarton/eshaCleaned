from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


IMPLEMENTATION_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = IMPLEMENTATION_ROOT.parent
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from map_recipe_lines_to_concepts import (  # noqa: E402
    DEFAULT_APPROVED_RULES_CSV,
    DEFAULT_DICTIONARY_CSV,
    _collapse_alternative,
    apply_output_defaults,
    approved_rule_for_surface,
    build_arg_parser,
    load_approved_normalization_rules,
    load_dictionary,
    match_dictionary,
    normalize_surface,
    parse_line,
    resolve_approved_rule,
    route_resolution,
)
from resolver_context import CANONICAL_SCRIPTS, DEFAULT_ARTIFACTS, REVIEWED_REGISTRIES, artifact_status  # noqa: E402
from audit_product_contracts import (  # noqa: E402
    CONTRACTS,
    REVIEW_BLOCKING_POLICIES,
    check_candidate,
    family_rule_failures,
    load_family_rules,
)
from build_product_card_coverage_85 import (  # noqa: E402
    PRODUCT_DB,
    ProductCard,
    approved_contract_card,
    choose_product,
    concept_row_from_key,
)
from boil_to_base_food import extract_base_food  # noqa: E402
from hf_v3_collapse_core import collapse_candidate_to_v3  # noqa: E402
from recompute_hf_v3_collapse_from_cache import reject_reason, select_collapse  # noqa: E402
from audit_recipe_qa_nutrition_calculation import (  # noqa: E402
    EXTERNAL_CATALOG_FALLBACK_BUCKETS,
    PRODUCT_NUTRITION_CACHE_TABLES,
    REVIEW_REQUIRED_EXTERNAL_AUTO_CONCEPT_KEYS,
    add_sr28_portion_household_rules,
    copy_cached_product_nutrition_state,
    load_external_catalog_items_with_food_csv,
    load_fndds_nutrients,
    normalize_household_unit,
    load_recipe_line_patches,
    load_recipe_id_filter,
    load_reviewed_branded_nutrition_rows,
    load_reviewed_fndds_nutrition_rows,
    load_reviewed_nutrition_anchors,
    install_split_default_nutrition_functions,
    install_display_parse_functions,
    install_household_unit_functions,
    load_product_nutrition,
    load_sr28_fallbacks,
    normalize_concept_key,
    normalize_concept_key_list,
    normalize_line,
    plausible_external_auto_row,
    plausible_external_alcohol_row,
    populate_quantity_policies,
    populate_recipe_ingredients,
    product_nutrition_cache_is_valid,
    sr28_portion_unit,
)
from audit_full_recipe_calculation import evaluate_line as evaluate_full_recipe_line  # noqa: E402
from recipe_calculator_baseline import STATUS_FULL_READY, classify_recipe  # noqa: E402
from audit_identity_layer_poison import audit_bridge_csv, audit_dictionary_csv  # noqa: E402
from identity_poison import is_poison_base, poison_findings_for_base  # noqa: E402
from audit_sr28_bridge_integrity import (  # noqa: E402
    CSV_SOURCES as SR28_BRIDGE_CSV_SOURCES,
    audit_cache_db as audit_sr28_cache_db,
    audit_csv_source as audit_sr28_csv_source,
    load_sr28_foods as load_sr28_bridge_foods,
)


class ManifestPreflightTests(unittest.TestCase):
    def test_reviewed_registries_exist_and_are_nonempty(self) -> None:
        missing_or_empty = [
            row
            for row in artifact_status()
            if not row["exists"] or row["rows"] is None or row["rows"] <= 0
        ]
        self.assertEqual([], missing_or_empty)

    def test_canonical_scripts_exist(self) -> None:
        missing = {name: str(path) for name, path in CANONICAL_SCRIPTS.items() if not path.exists()}
        self.assertEqual({}, missing)

    def test_sr28_portion_units_normalize_modifier_text(self) -> None:
        units = {"9999": "undetermined"}
        self.assertEqual(
            "cup",
            sr28_portion_unit(
                {"measure_unit_id": "9999", "modifier": "cup, chopped", "portion_description": ""},
                units,
            ),
        )
        self.assertEqual(
            "tsp",
            sr28_portion_unit(
                {"measure_unit_id": "9999", "modifier": "tsp, whole", "portion_description": ""},
                units,
            ),
        )
        self.assertEqual(
            "count",
            sr28_portion_unit(
                {"measure_unit_id": "9999", "modifier": "", "portion_description": "pepper"},
                units,
            ),
        )
        self.assertEqual(
            "piece",
            sr28_portion_unit(
                {"measure_unit_id": "9999", "modifier": "", "portion_description": "1 piece"},
                units,
            ),
        )
        self.assertEqual(
            "package",
            sr28_portion_unit(
                {"measure_unit_id": "9999", "modifier": "", "portion_description": "1 package (10 oz) yields"},
                units,
            ),
        )
        self.assertEqual(
            "count",
            sr28_portion_unit(
                {"measure_unit_id": "9999", "modifier": "roll 1 serving", "portion_description": ""},
                units,
            ),
        )
        self.assertEqual("package", normalize_household_unit("pkg."))
        self.assertEqual("count", normalize_household_unit("bun"))
        self.assertEqual("count", normalize_household_unit("roll"))
        self.assertEqual("ear", normalize_household_unit("ears"))

    def test_sr28_portion_rules_fill_reviewed_concept_units(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            portion_csv = temp / "food_portion.csv"
            portion_csv.write_text(
                "\n".join(
                    [
                        "id,fdc_id,seq_num,amount,measure_unit_id,portion_description,modifier,gram_weight,data_points,footnote,min_year_acquired",
                        "1,169997,1,0.25,9999,,cup,4,,,",
                        "2,169997,2,9,9999,,sprigs,20,,,",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            measure_csv = temp / "measure_unit.csv"
            measure_csv.write_text("id,name\n9999,undetermined\n", encoding="utf-8")
            fallback_csv = temp / "fallback.csv"
            fallback_csv.write_text(
                "concept_key,fdc_id,sr28_description,review_status,notes\n"
                "cilantro|||fresh,169997,\"Coriander (cilantro) leaves, raw\",approved,test\n",
                encoding="utf-8",
            )
            external_csv = temp / "external.csv"
            external_csv.write_text(
                "concept_key,shopping_label,shopping_category,fdc_id,sr28_description,review_status,notes\n",
                encoding="utf-8",
            )
            anchors_csv = temp / "anchors.csv"
            anchors_csv.write_text(
                "concept_key,source_system,food_id,description,food_family,form,state,allowed_description_tokens,forbidden_description_tokens,review_status,notes\n",
                encoding="utf-8",
            )
            conn = sqlite3.connect(":memory:")
            conn.execute(
                """
                CREATE TABLE household_unit_rules (
                    rule_id TEXT PRIMARY KEY,
                    concept_key TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    grams_per_unit REAL NOT NULL,
                    rationale TEXT
                )
                """
            )
            rules: dict[tuple[str, str], dict[str, object]] = {}
            added = add_sr28_portion_household_rules(
                conn,
                rules,
                sr28_portion_csv=portion_csv,
                sr28_measure_unit_csv=measure_csv,
                sr28_fallback_csv=fallback_csv,
                external_catalog_csv=external_csv,
                nutrition_anchor_csv=anchors_csv,
            )
            self.assertGreaterEqual(added, 4)
            self.assertEqual("cup", normalize_household_unit("cups"))
            self.assertAlmostEqual(16.0, float(rules[("cilantro|||fresh", "cup")]["grams_per_unit"]))
            self.assertAlmostEqual(1.0, float(rules[("cilantro|||fresh", "tbsp")]["grams_per_unit"]))
            self.assertAlmostEqual(20.0 / 9.0, float(rules[("cilantro|||fresh", "sprig")]["grams_per_unit"]))
            conn.close()

    def test_canonical_scripts_use_resolver_context_manifest(self) -> None:
        failures = []
        for name, path in CANONICAL_SCRIPTS.items():
            text = path.read_text(encoding="utf-8")
            if "resolver_context" not in text or "DEFAULT_ARTIFACTS" not in text:
                failures.append((name, str(path)))
        self.assertEqual([], failures)

    def test_reviewed_registry_csvs_have_no_extra_columns(self) -> None:
        failures = []
        for registry_name, path in REVIEWED_REGISTRIES.items():
            with path.open(newline="", encoding="utf-8") as handle:
                for line_number, row in enumerate(csv.DictReader(handle), start=2):
                    if None in row:
                        row_id = row.get("rule_id") or row.get("contract_id") or row.get("concept_key") or row.get("family_id") or ""
                        failures.append((registry_name, line_number, row_id, row[None]))
                        if len(failures) >= 20:
                            break
        self.assertEqual([], failures)

    def test_product_family_rule_patterns_compile_and_policies_are_known(self) -> None:
        allowed_policies = {
            "",
            "auto_cart",
            "visible_substitution",
            "manual_product_required",
            "nutrition_proxy_only",
            "no_buy",
        }
        failures = []
        path = REVIEWED_REGISTRIES["product_family_safety_rules"]
        with path.open(newline="", encoding="utf-8") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), start=2):
                family_id = row.get("family_id", "")
                pattern = row.get("applies_when_concept_matches", "")
                try:
                    re.compile(pattern)
                except re.error as exc:
                    failures.append((line_number, family_id, "bad_regex", str(exc)))
                policy = (row.get("cart_policy") or "").strip()
                if policy not in allowed_policies:
                    failures.append((line_number, family_id, "unknown_policy", policy))
                if not any((row.get(field) or "").strip() for field in ["required_any", "required_all", "allowed_categories", "forbidden_any", "forbidden_categories"]):
                    failures.append((line_number, family_id, "rule_has_no_effect", ""))
        self.assertEqual([], failures)

    def test_approved_normalization_regex_patterns_compile(self) -> None:
        failures = []
        with DEFAULT_APPROVED_RULES_CSV.open(newline="", encoding="utf-8") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), start=2):
                if row.get("match_type") != "regex":
                    continue
                try:
                    re.compile(row.get("input_surface") or "")
                except re.error as exc:
                    failures.append((line_number, row.get("rule_id", ""), str(exc)))
        self.assertEqual([], failures)
        load_approved_normalization_rules(DEFAULT_APPROVED_RULES_CSV)

    def test_approved_normalization_rule_ids_are_unique(self) -> None:
        seen: dict[str, int] = {}
        duplicates = []
        with DEFAULT_APPROVED_RULES_CSV.open(newline="", encoding="utf-8") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), start=2):
                rule_id = row.get("rule_id", "")
                if rule_id in seen:
                    duplicates.append((rule_id, seen[rule_id], line_number))
                else:
                    seen[rule_id] = line_number
        self.assertEqual([], duplicates)

    def test_canonical_scripts_do_not_reintroduce_hidden_or_pick_tables(self) -> None:
        forbidden_patterns = [
            r"\bSAFE_LEFT\s*=",
            r'"butter or margarine"\s*:\s*"butter"',
            r'"margarine or butter"\s*:\s*"butter"',
            r'"olive oil or vegetable oil"\s*:\s*"olive oil"',
            r'"whipped cream or ice cream"\s*:\s*"whipped cream"',
        ]
        failures = []
        for name, path in CANONICAL_SCRIPTS.items():
            text = path.read_text(encoding="utf-8")
            for pattern in forbidden_patterns:
                if re.search(pattern, text):
                    failures.append((name, pattern))
        self.assertEqual([], failures)

    def test_docs_define_shared_agent_contract(self) -> None:
        for relative_path in [
            "CLAUDE_HANDOFF.md",
            "SOURCE_OF_TRUTH.md",
            "AGENT_COORDINATION.md",
            "output/README.md",
            "ACCOUNTED_WORK_LEDGER_DESIGN.md",
            "INCREMENTAL_FUNNEL_STATE.md",
        ]:
            self.assertTrue((IMPLEMENTATION_ROOT / relative_path).exists(), relative_path)

    def test_work_item_ledger_schema_statuses_and_ids(self) -> None:
        required_fields = {
            "ledger_id",
            "scope",
            "layer",
            "fingerprint_type",
            "fingerprint",
            "target_state",
            "status",
            "priority",
            "risk_level",
            "source_queue",
            "source_artifact",
            "before_row_count",
            "before_occurrence_count",
            "registry_rows",
            "code_paths",
            "regression_tests",
            "proof_command",
            "proof_artifact",
            "proof_summary",
            "owner",
            "created_at",
            "updated_at",
            "notes",
        }
        allowed_statuses = {
            "todo",
            "claimed",
            "ready_for_audit",
            "audit_passed",
            "accepted_visible_gap",
            "audit_failed",
            "regressed",
            "retired",
        }
        path = REVIEWED_REGISTRIES["work_item_ledger"]
        failures = []
        seen_ids = set()
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            self.assertTrue(required_fields.issubset(set(reader.fieldnames or [])))
            for line_number, row in enumerate(reader, start=2):
                ledger_id = row.get("ledger_id", "")
                if ledger_id in seen_ids:
                    failures.append((line_number, ledger_id, "duplicate_ledger_id"))
                seen_ids.add(ledger_id)
                if row.get("status", "") not in allowed_statuses:
                    failures.append((line_number, ledger_id, "unknown_status", row.get("status", "")))
                for required in ["fingerprint_type", "fingerprint", "target_state", "source_queue"]:
                    if not row.get(required, "").strip():
                        failures.append((line_number, ledger_id, f"missing_{required}"))
                if row.get("status") in {"audit_passed", "accepted_visible_gap"} and not row.get("proof_summary", "").strip():
                    failures.append((line_number, ledger_id, "completed_without_proof_summary"))
        self.assertEqual([], failures)


class CalculatorBaselinePreflightTests(unittest.TestCase):
    def test_calculator_baseline_paths_are_canonical_outputs(self) -> None:
        outputs = [
            DEFAULT_ARTIFACTS.funnel_state_db,
            DEFAULT_ARTIFACTS.calculator_recipe_status_csv,
            DEFAULT_ARTIFACTS.calculator_ready_recipe_ids_csv,
            DEFAULT_ARTIFACTS.calculator_attack_recipe_ids_csv,
            DEFAULT_ARTIFACTS.calculator_baseline_summary_json,
        ]
        for path in outputs:
            with self.subTest(path=path):
                self.assertEqual(DEFAULT_ARTIFACTS.funnel_state_db.parent, path.parent)

    def test_classify_recipe_marks_only_zero_blocker_full_ready(self) -> None:
        status, ready_percent, product_calc_percent, top_bucket, blocked_lines, blocker_summary = classify_recipe(
            ingredient_lines=4,
            nutrition_ready_lines=4,
            product_nutrition_calculable_lines=3,
            blocker_counts=Counter(),
        )
        self.assertEqual(STATUS_FULL_READY, status)
        self.assertEqual(100.0, ready_percent)
        self.assertEqual(75.0, product_calc_percent)
        self.assertEqual("", top_bucket)
        self.assertEqual(0, blocked_lines)
        self.assertEqual("", blocker_summary)

    def test_classify_recipe_keeps_one_blocker_in_attack_surface(self) -> None:
        status, ready_percent, _product_calc_percent, top_bucket, blocked_lines, blocker_summary = classify_recipe(
            ingredient_lines=4,
            nutrition_ready_lines=3,
            product_nutrition_calculable_lines=3,
            blocker_counts=Counter({"concept_unresolved": 1}),
        )
        self.assertEqual("partial_50_79", status)
        self.assertEqual(75.0, ready_percent)
        self.assertEqual("concept_unresolved", top_bucket)
        self.assertEqual(1, blocked_lines)
        self.assertEqual("concept_unresolved=1", blocker_summary)

    def test_recipe_id_filter_loader_requires_recipe_id_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = Path(tmpdir) / "bad.csv"
            bad_path.write_text("id\n1\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_recipe_id_filter(bad_path)

            good_path = Path(tmpdir) / "good.csv"
            good_path.write_text("recipe_id,title\n1,A\n2,B\n", encoding="utf-8")
            self.assertEqual({"1", "2"}, load_recipe_id_filter(good_path))

    def test_external_catalog_loader_repairs_stale_fdc_ids_and_skips_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            food_csv = root / "food.csv"
            external_csv = root / "external.csv"
            food_csv.write_text(
                "\n".join(
                    [
                        "fdc_id,data_type,description,food_category_id,publication_date",
                        "1,sr_legacy_food,Wrong food,2,2019-04-01",
                        "2,sr_legacy_food,Right food,2,2019-04-01",
                        "3,sr_legacy_food,Other right food,2,2019-04-01",
                    ]
                ),
                encoding="utf-8",
            )
            external_csv.write_text(
                "\n".join(
                    [
                        "concept_key,shopping_label,shopping_category,fdc_id,sr28_description,review_status,notes",
                        "right|||,right,external,1,Right food,approved,stale id should repair",
                        "conflict|||,conflict,external,2,Right food,approved,first",
                        "conflict|||,conflict,external,3,Other right food,approved,second",
                    ]
                ),
                encoding="utf-8",
            )
            rows, stats = load_external_catalog_items_with_food_csv(
                external_csv,
                {
                    "2": {"calories": 10.0},
                    "3": {"calories": 20.0},
                },
                food_csv,
            )
            self.assertEqual(["right|||"], [row["concept_key"] for row in rows])
            self.assertEqual("2", rows[0]["sr28_fdc_id"])
            self.assertEqual(1, stats["fdc_id_repaired_from_description"])
            self.assertEqual(1, stats["duplicate_conflict_skipped"])

    def test_sr28_fallback_loader_repairs_stale_fdc_ids_from_description(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            food_csv = root / "food.csv"
            fallback_csv = root / "fallback.csv"
            food_csv.write_text(
                "\n".join(
                    [
                        "fdc_id,data_type,description,food_category_id,publication_date",
                        "1,sr_legacy_food,Wrong food,2,2019-04-01",
                        "2,sr_legacy_food,Right food,2,2019-04-01",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fallback_csv.write_text(
                "\n".join(
                    [
                        "concept_key,fdc_id,sr28_description,review_status,notes",
                        "right|||,1,Right food,approved,stale id should repair",
                        "bad|||,1,Missing food,approved,stale id should not load",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fallbacks = load_sr28_fallbacks(fallback_csv, food_csv)
        self.assertEqual("2", fallbacks["right|||"]["fdc_id"])
        self.assertEqual("Right food", fallbacks["right|||"]["sr28_description"])
        self.assertNotIn("bad|||", fallbacks)

    def test_reviewed_nutrition_anchor_loader_repairs_stale_fdc_ids_from_description(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            food_csv = root / "food.csv"
            anchor_csv = root / "anchors.csv"
            food_csv.write_text(
                "\n".join(
                    [
                        "fdc_id,data_type,description,food_category_id,publication_date",
                        "1,sr_legacy_food,Wrong food,2,2019-04-01",
                        "2,sr_legacy_food,Right food,2,2019-04-01",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            anchor_csv.write_text(
                "\n".join(
                    [
                        "concept_key,source_system,food_id,description,food_family,form,state,allowed_description_tokens,forbidden_description_tokens,review_status,notes",
                        "right|||,SR28,1,Right food,food,,,right,wrong,approved,stale id should repair",
                        "bad|||,SR28,1,Missing food,food,,,right,wrong,approved,stale id should not load",
                        "fndds|||,FNDDS,1,Right food,food,,,right,wrong,approved,not SR28",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            anchors = load_reviewed_nutrition_anchors(anchor_csv, food_csv)
        self.assertEqual("2", anchors["right|||"]["fdc_id"])
        self.assertEqual("Right food", anchors["right|||"]["sr28_description"])
        self.assertNotIn("bad|||", anchors)
        self.assertNotIn("fndds|||", anchors)

    def test_sr28_bridge_integrity_has_no_stale_approved_ids(self) -> None:
        food_csv = IMPLEMENTATION_ROOT.parent / "data" / "sr28_csv" / "food.csv"
        id_to_description, description_to_ids = load_sr28_bridge_foods(food_csv)
        rows = []
        for source in SR28_BRIDGE_CSV_SOURCES:
            rows.extend(audit_sr28_csv_source(source, id_to_description, description_to_ids))
        rows.extend(
            audit_sr28_cache_db(
                DEFAULT_ARTIFACTS.product_nutrition_state_db,
                id_to_description,
                description_to_ids,
            )
        )
        issue_statuses = {
            "description_mismatch",
            "missing_description",
            "missing_fdc_id",
            "repairable_by_description",
        }
        failures = [
            (
                row["source"],
                row["row_number"],
                row["concept_key"],
                row["fdc_id"],
                row["status"],
                row["reviewed_description"],
                row["actual_description"],
            )
            for row in rows
            if row["status"] in issue_statuses
        ]
        self.assertEqual([], failures[:50])

    def test_high_impact_external_herb_proxies_match_local_sr28(self) -> None:
        food_csv = IMPLEMENTATION_ROOT.parent / "data" / "sr28_csv" / "food.csv"
        id_to_description = {}
        with food_csv.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                id_to_description[(row.get("fdc_id") or "").strip()] = (row.get("description") or "").strip()

        required = {
            "oregano|||fresh": ("173470", "Thyme, fresh"),
            "oregano leaf|||fresh": ("173470", "Thyme, fresh"),
            "oregano sprig|||fresh": ("173470", "Thyme, fresh"),
            "sage|||fresh": ("173470", "Thyme, fresh"),
            "sage leaf|||fresh": ("173470", "Thyme, fresh"),
            "sage sprig|||fresh": ("173470", "Thyme, fresh"),
            "tarragon|||fresh": ("173470", "Thyme, fresh"),
            "tarragon leaf|||fresh": ("173470", "Thyme, fresh"),
            "tarragon sprig|||fresh": ("173470", "Thyme, fresh"),
            "thyme||ground|": ("170938", "Spices, thyme, dried"),
        }
        external_rows = {}
        with REVIEWED_REGISTRIES["external_catalog"].open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("review_status") == "approved":
                    external_rows[(row.get("concept_key") or "").strip()] = row

        failures = []
        for concept_key, (expected_id, expected_description) in required.items():
            row = external_rows.get(concept_key)
            if not row:
                failures.append((concept_key, "missing external catalog row"))
                continue
            actual_id = (row.get("fdc_id") or "").strip()
            actual_description = (row.get("sr28_description") or "").strip()
            if actual_id != expected_id or actual_description != expected_description:
                failures.append((concept_key, actual_id, actual_description))
            if id_to_description.get(actual_id) != actual_description:
                failures.append((concept_key, actual_id, actual_description, id_to_description.get(actual_id)))
        self.assertEqual([], failures)

    def test_implausible_external_alcohol_rows_are_blocked(self) -> None:
        allowed = [
            ("vodka|||", "vodka"),
            ("grand marnier|||", "grand marnier"),
            ("baileys irish cream|||", "baileys irish cream"),
            ("chardonnay|||", "chardonnay"),
            ("creme de cacao|||", "creme de cacao"),
            ("crème de menthe|||", "creme de menthe"),
            ("peach schnapp|||", "peach schnapps"),
            ("ale|||", "ale"),
            ("goldschlager|||", "goldschlager"),
        ]
        blocked = [
            ("gingersnap cookie||crumb|", "gingersnap cookie"),
            ("hidden valley original ranch dressing|||", "hidden valley original ranch dressing"),
            ("crumbled rosemary|||", "crumbled rosemary"),
            ("imported bay leaf|||", "imported bay leaf"),
            ("red wine vinegar|||", "red wine vinegar"),
            ("cold ginger ale|||", "cold ginger ale"),
        ]
        for concept_key, label in allowed:
            with self.subTest(concept_key=concept_key):
                self.assertTrue(
                    plausible_external_alcohol_row(
                        {
                            "concept_key": concept_key,
                            "shopping_label": label,
                            "shopping_category": "external_alcohol",
                        }
                    )
                )
        for concept_key, label in blocked:
            with self.subTest(concept_key=concept_key):
                self.assertFalse(
                    plausible_external_alcohol_row(
                        {
                            "concept_key": concept_key,
                            "shopping_label": label,
                            "shopping_category": "external_alcohol",
                        }
                    )
                )

    def test_no_approved_implausible_external_alcohol_rows(self) -> None:
        failures = []
        with REVIEWED_REGISTRIES["external_catalog"].open(newline="", encoding="utf-8") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), start=2):
                if (
                    row.get("review_status") == "approved"
                    and row.get("shopping_category") == "external_alcohol"
                    and not plausible_external_alcohol_row(row)
                ):
                    failures.append((line_number, row.get("concept_key"), row.get("shopping_label")))
        self.assertEqual([], failures)

    def test_no_approved_review_required_external_auto_rows(self) -> None:
        failures = []
        with REVIEWED_REGISTRIES["external_catalog"].open(newline="", encoding="utf-8") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), start=2):
                if (
                    row.get("review_status") == "approved"
                    and row.get("shopping_category") == "external_auto"
                    and not plausible_external_auto_row(row)
                ):
                    failures.append(
                        (
                            line_number,
                            row.get("concept_key"),
                            REVIEW_REQUIRED_EXTERNAL_AUTO_CONCEPT_KEYS.get(row.get("concept_key") or "", ""),
                        )
                    )
        self.assertEqual([], failures)

    def test_product_nutrition_state_cache_requires_tables_and_matching_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_db = Path(tmpdir) / "product_state.db"
            conn = sqlite3.connect(cache_db)
            conn.execute(
                """
                CREATE TABLE product_nutrition_state_meta (
                    dependency_fingerprint TEXT PRIMARY KEY,
                    generated_at TEXT NOT NULL,
                    product_rows INTEGER NOT NULL,
                    external_rows INTEGER NOT NULL,
                    external_stats_json TEXT NOT NULL,
                    dependency_artifacts_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO product_nutrition_state_meta VALUES (?,?,?,?,?,?)",
                ("abc", "2026-04-12T00:00:00+00:00", 1, 1, "{}", "[]"),
            )
            conn.execute("CREATE TABLE product_nutrition (concept_key TEXT)")
            conn.execute("CREATE TABLE external_catalog_nutrition (concept_key TEXT)")
            conn.execute("INSERT INTO product_nutrition VALUES ('milk|||')")
            conn.execute("INSERT INTO external_catalog_nutrition VALUES ('oregano|||fresh')")
            conn.commit()
            conn.close()

            self.assertTrue(product_nutrition_cache_is_valid(cache_db, "abc"))
            self.assertFalse(product_nutrition_cache_is_valid(cache_db, "different"))

            audit_db = Path(tmpdir) / "audit.db"
            audit_conn = sqlite3.connect(audit_db)
            copy_cached_product_nutrition_state(audit_conn, cache_db)
            for table in PRODUCT_NUTRITION_CACHE_TABLES:
                with self.subTest(table=table):
                    count = audit_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            self.assertEqual(1, count)
            audit_conn.close()

    def test_external_catalog_can_rescue_contract_not_passed_bucket(self) -> None:
        self.assertIn("contract_not_passed", EXTERNAL_CATALOG_FALLBACK_BUCKETS)


class IdentityPoisonPreflightTests(unittest.TestCase):
    def test_modifier_only_bases_are_p0_poison(self) -> None:
        for base in ["fat-free", "additional", "all-purpose", "hot", "cold", "can", "container"]:
            with self.subTest(base=base):
                self.assertTrue(is_poison_base(base))
                self.assertIn("P0", {finding.severity for finding in poison_findings_for_base(base)})

    def test_valid_food_bases_are_not_p0_poison(self) -> None:
        for base in ["orange juice", "all-purpose flour", "fat-free milk", "green bean", "chicken broth"]:
            with self.subTest(base=base):
                self.assertFalse(is_poison_base(base))

    def test_dictionary_poison_audit_catches_fat_free_broth_alias_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dictionary.csv"
            path.write_text(
                "\n".join(
                    [
                        "base_food,variant,form,state,total_recipes,surface_count,example_surfaces,codex_fix_notes",
                        '"fat-free",,,,1765,18,"fat-free, less-sodium chicken broth",',
                        '"orange juice",,,,100,4,"orange juice; orange juice, chilled",',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            rows = audit_dictionary_csv(path, source_name="test_dictionary.csv")
        self.assertEqual(1, len([row for row in rows if row["severity"] == "P0"]))
        self.assertEqual("modifier_only_base", rows[0]["issue"])
        self.assertEqual("fat-free", rows[0]["value"])

    def test_bridge_poison_audit_catches_poison_canonical_concept(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bridge.csv"
            path.write_text(
                "\n".join(
                    [
                        "normalized_item,occurrence_count,canonical_concept_key,canonical_surface,bridge_status,bridge_source,match_rule_id,trust_level,nutrition_anchor_status,product_contract_status,product_contract_key,review_notes,registry_fingerprint",
                        "fat-free less sodium chicken broth,1765,fat-free|||,fat-free,concept_ready,dictionary,,dictionary,,,,,abc",
                        "green beans,100,green bean|||,green bean,concept_ready,dictionary,,dictionary,,,,,abc",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            rows = audit_bridge_csv(path, source_name="test_bridge.csv")
        self.assertEqual(1, len([row for row in rows if row["severity"] == "P0"]))
        self.assertEqual("canonical_modifier_only_base", rows[0]["issue"])
        self.assertEqual("fat-free", rows[0]["value"])


class ProductCardBuilderPreflightTests(unittest.TestCase):
    def test_approved_product_contracts_take_precedence_over_inline_overrides(self) -> None:
        card = approved_contract_card(concept_row_from_key("blueberry|||fresh", 1, "fresh blueberries", "test"))
        self.assertIsNotNone(card)
        assert card is not None
        self.assertEqual("approved_contract:fresh_blueberry", card.source)
        self.assertEqual(("Pre-Packaged Fruit & Vegetables",), card.allowed_categories)
        self.assertIn("frozen", card.forbidden_any)
        self.assertNotIn("Frozen Fruit & Fruit Juice Concentrates", card.allowed_categories)

    def test_parent_food_contract_query_uses_required_any_not_child_phrase(self) -> None:
        card = approved_contract_card(concept_row_from_key("egg yolk|||", 1, "egg yolk", "test"))
        self.assertIsNotNone(card)
        assert card is not None
        self.assertEqual("approved_contract:shell_eggs", card.source)
        self.assertEqual("eggs", card.query)
        self.assertEqual(("eggs", "large eggs"), card.required_any)

    def test_unit_prefixed_fresh_ginger_uses_root_query(self) -> None:
        card = approved_contract_card(concept_row_from_key("inch fresh ginger|||fresh", 1, "inch fresh ginger", "test"))
        self.assertIsNotNone(card)
        assert card is not None
        self.assertEqual("approved_contract:ginger_fresh", card.source)
        self.assertEqual("ginger root", card.query)
        self.assertIn("sesame", card.forbidden_any)
        self.assertIn("fusion", card.forbidden_any)

    def test_product_search_token_fallback_recovers_missing_filler_words(self) -> None:
        conn = sqlite3.connect(PRODUCT_DB)
        conn.row_factory = sqlite3.Row
        try:
            card = ProductCard(
                route="product",
                query="cream mushroom soup",
                allowed_categories=("Canned Condensed Soup",),
                required_all=("cream", "mushroom", "soup"),
                forbidden_any=("broth", "gravy"),
                source="test",
            )
            selected, accepted, _rejected, searched_count = choose_product(conn, card)
        finally:
            conn.close()

        self.assertGreater(searched_count, 0)
        self.assertIsNotNone(selected)
        self.assertTrue(accepted)
        assert selected is not None
        self.assertIn("CREAM OF MUSHROOM", selected.description.upper())

    def test_hestia_plu_herb_rows_supply_fresh_bunches(self) -> None:
        conn = sqlite3.connect(PRODUCT_DB)
        conn.row_factory = sqlite3.Row
        try:
            cases = [
                ("fresh parsley bunch", "Fresh Parsley Bunch"),
                ("fresh dill bunch", "Fresh Dill Bunch"),
                ("fresh cilantro bunch", "Fresh Cilantro Bunch"),
            ]
            for query, expected in cases:
                with self.subTest(query=query):
                    card = ProductCard(
                        route="product",
                        query=query,
                        allowed_categories=("Pre-Packaged Fruit & Vegetables",),
                        required_any=(query,),
                        source="test",
                    )
                    selected, accepted, _rejected, searched_count = choose_product(conn, card)
                    self.assertGreater(searched_count, 0)
                    self.assertTrue(accepted)
                    self.assertIsNotNone(selected)
                    assert selected is not None
                    self.assertEqual(expected, selected.description)
        finally:
            conn.close()


class NormalizationRulePreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = load_approved_normalization_rules(DEFAULT_APPROVED_RULES_CSV)

    def test_no_duplicate_approved_rule_keys(self) -> None:
        rows = self._approved_rows()
        keys = [
            (row["match_type"], row["input_surface"].strip().lower())
            for row in rows
        ]
        duplicates = [key for key, count in Counter(keys).items() if count > 1]
        self.assertEqual([], duplicates)

    def test_approved_rule_csv_has_no_extra_columns(self) -> None:
        failures = []
        with DEFAULT_APPROVED_RULES_CSV.open(newline="", encoding="utf-8") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), start=2):
                if None in row:
                    failures.append((line_number, row.get("rule_id"), row[None]))
        self.assertEqual([], failures)

    def test_normalization_rule_status_values_are_known(self) -> None:
        allowed = {"approved", "rejected", "superseded", "proposed"}
        failures = []
        with DEFAULT_APPROVED_RULES_CSV.open(newline="", encoding="utf-8") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), start=2):
                status = row.get("status", "")
                if status not in allowed:
                    failures.append((line_number, row.get("rule_id", ""), status))
        self.assertEqual([], failures)

    def test_unreviewed_nr_claude_bulk_rows_are_not_approved(self) -> None:
        failures = []
        with DEFAULT_APPROVED_RULES_CSV.open(newline="", encoding="utf-8") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), start=2):
                if not row.get("rule_id", "").startswith("NR-CLAUDE-2026-04-15"):
                    continue
                if row.get("status") == "approved":
                    failures.append((line_number, row["rule_id"], row.get("input_surface", "")))
        self.assertEqual([], failures)

    def test_approved_aliases_do_not_create_numeric_concepts(self) -> None:
        failures = []
        with DEFAULT_APPROVED_RULES_CSV.open(newline="", encoding="utf-8") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), start=2):
                if row.get("status") != "approved" or row.get("rule_type") != "alias":
                    continue
                base = (row.get("canonical_concept_key") or "").split("|", 1)[0].strip()
                if base[:1].isdigit():
                    failures.append((line_number, row.get("rule_id", ""), row.get("canonical_concept_key", "")))
        self.assertEqual([], failures)

    def test_approved_aliases_do_not_create_modifier_only_concepts(self) -> None:
        modifier_only_bases = {
            "additional",
            "bulk",
            "can",
            "chopped",
            "cleaned",
            "complete",
            "crushed",
            "crusty",
            "diced",
            "dried",
            "drop",
            "dry",
            "extra",
            "fine",
            "fresh",
            "frosty",
            "frozen",
            "ground",
            "hard",
            "heavy",
            "jar",
            "large",
            "loaf",
            "medium",
            "natural",
            "outer",
            "package",
            "packet",
            "piece",
            "plain",
            "ready",
            "round",
            "scoop",
            "seeded",
            "several",
            "sheets",
            "shredded",
            "sliced",
            "slices",
            "small",
            "soft",
            "solid",
            "split",
            "thick",
            "thin",
            "vegetarian",
            "whole",
            "wing",
        }
        failures = []
        with DEFAULT_APPROVED_RULES_CSV.open(newline="", encoding="utf-8") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), start=2):
                if row.get("status") != "approved" or row.get("rule_type") != "alias":
                    continue
                base = (row.get("canonical_concept_key") or "").split("|", 1)[0].strip().lower()
                if base in modifier_only_bases:
                    failures.append((line_number, row.get("rule_id", ""), row.get("canonical_concept_key", "")))
        self.assertEqual([], failures)

    def test_craft_glue_rows_are_rejects_not_food_aliases(self) -> None:
        craft_terms = (
            "elmer",
            "school glue",
            "white glue",
            "nontoxic glue",
            "non-toxic glue",
            "glue gun",
            "glue stick",
            "super glue",
            "tacky glue",
            "carpenter glue",
            "craft glue",
            "hot glue",
            "modge podge",
        )
        failures = []
        for row in self._approved_rows():
            surface = row["input_surface"].strip().lower()
            concept_key = row["canonical_concept_key"].strip().lower()
            if concept_key in {"glue|||", "white glue|||"} or any(term in surface for term in craft_terms):
                if row["rule_type"] != "reject" or row["canonical_concept_key"]:
                    failures.append((row["rule_id"], row["input_surface"], row["canonical_concept_key"]))
        self.assertEqual([], failures)

    def test_or_choices_are_visible_alternatives_not_hidden_aliases(self) -> None:
        rows = self._approved_rows()
        unsafe = []
        for row in rows:
            if " or " not in f" {row['input_surface'].lower()} ":
                continue
            if row["rule_type"] == "alternative":
                components = [part.strip() for part in row["components"].split(";") if part.strip()]
                if len(components) < 2:
                    unsafe.append((row["rule_id"], "alternative_without_two_components"))
                if row["canonical_concept_key"] or row["canonical_surface"]:
                    unsafe.append((row["rule_id"], "alternative_has_single_canonical_target"))
                continue
            if row["rule_type"] == "alias":
                evidence = row.get("evidence", "").lower()
                if any(token in evidence for token in ["silent", "pick first", "choose one"]):
                    unsafe.append((row["rule_id"], "hidden_or_alias"))
        self.assertEqual([], unsafe)

    def test_loader_rejects_hidden_or_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rules.csv"
            path.write_text(
                "\n".join(
                    [
                        "rule_id,rule_type,match_type,input_surface,canonical_concept_key,canonical_surface,components,status,evidence,reviewer,created_at",
                        "bad,alias,exact,butter or margarine,butter|||,butter,,approved,silent pick first named,codex,2026-04-11",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_approved_normalization_rules(path)

    def test_reject_regex_overrides_older_alias_regex(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rules.csv"
            path.write_text(
                "\n".join(
                    [
                        "rule_id,rule_type,match_type,input_surface,canonical_concept_key,canonical_surface,components,status,evidence,reviewer,created_at",
                        "old_alias,alias,regex,^hot\\s+glue$,glue|||,glue,,approved,old broad alias,codex,2026-04-15",
                        "new_reject,reject,regex,^hot\\s+glue$,,non_food,,approved,craft material safety override,codex,2026-04-15",
                    ]
                ),
                encoding="utf-8",
            )
            rules = load_approved_normalization_rules(path)
            rule = approved_rule_for_surface("hot glue", rules)
            self.assertIsNotNone(rule)
            self.assertEqual("new_reject", rule["rule_id"])
            self.assertEqual("reject", rule["rule_type"])

    def test_high_risk_or_rows_remain_visible_alternatives(self) -> None:
        rows = {row["rule_id"]: row for row in self._approved_rows()}
        high_risk_rule_ids = {
            "h8_shortening_oleo_001",
            "h8_miracle_whip_001",
            "h8_whipped_cream_topping_002",
            "h9_oleo_shortening_001",
            "h9_whipped_cream_cool_whip_001",
            "h9_butter_not_spread_001",
            "h9_cooking_spray_or_butter_002",
            "h9_corn_peanut_veg_oil_001",
            "h9_mayo_salad_dressing_003",
            "h9_apple_cider_juice_003",
            "h9_crisco_or_butter_001",
            "h9_corn_grapeseed_neutral_001",
            "h9_mayo_2_tbsp_dressing_001",
            "h9_cooking_spray_or_oil_002",
            "h9_butter_nonstick_spray_002",
            "h9_oil_or_fat_001",
            "h9_olive_oil_cooking_spray_002",
            "h9_miracle_whip_light_001",
            "h9_crisco_margarine_001",
            "h9_whipping_cream_cool_whip_002",
            "h9_miracle_whip_cup_mayo_001",
            "h9_fat_or_oil_002",
            "h9_bacon_fat_or_oil_001",
            "h9_margarine_butter_slash_001",
            "h9_butter_oleo_slash_001",
        }
        for rule_id in high_risk_rule_ids:
            with self.subTest(rule_id=rule_id):
                row = rows.get(rule_id)
                self.assertIsNotNone(row)
                assert row is not None
                self.assertEqual("alternative", row["rule_type"])
                components = [part.strip() for part in row["components"].split(";") if part.strip()]
                self.assertGreaterEqual(len(components), 2)

    def test_reversed_cake_mix_rules_preserve_flavor(self) -> None:
        rows = {row["rule_id"]: row for row in self._approved_rows()}
        expected = {
            "h9_cake_mix_white_002": "white cake mix||white|",
            "h9_cake_mix_yellow_reversed_001": "yellow cake mix|||",
            "h9_cake_mix_chocolate_reversed_001": "chocolate cake mix|||",
            "h9_cake_mix_lemon_reversed_001": "lemon cake mix|||",
        }
        for rule_id, concept_key in expected.items():
            with self.subTest(rule_id=rule_id):
                row = rows.get(rule_id)
                self.assertIsNotNone(row)
                assert row is not None
                self.assertEqual("alias", row["rule_type"])
                self.assertEqual(concept_key, row["canonical_concept_key"])

    def test_bouillon_rules_preserve_named_family(self) -> None:
        expectations = {
            "small chicken bouillon cube": "chicken bouillon|||",
            "small vegetable bouillon cubes": "vegetable bouillon|||",
            "large chicken bouillon cube": "chicken bouillon|||",
            "large vegetable bouillon cubes": "vegetable bouillon|||",
            "bouillon cubes (chicken)": "chicken bouillon|||",
            "bouillon cube (vegetable)": "vegetable bouillon|||",
            "chicken bouillon cube dissolved in": "chicken bouillon|||",
        }
        for surface, concept_key in expectations.items():
            with self.subTest(surface=surface):
                rule = approved_rule_for_surface(surface, self.rules)
                self.assertIsNotNone(rule)
                assert rule is not None
                self.assertEqual("alias", rule["rule_type"])
                self.assertEqual(concept_key, rule["canonical_concept_key"])

        alternatives = {
            "beef or vegetable bouillon cubes": {"beef bouillon|||", "vegetable bouillon|||"},
            "chicken or vegetable bouillon cubes": {"chicken bouillon|||", "vegetable bouillon|||"},
        }
        for surface, expected_components in alternatives.items():
            with self.subTest(surface=surface):
                rule = approved_rule_for_surface(surface, self.rules)
                self.assertIsNotNone(rule)
                assert rule is not None
                self.assertEqual("alternative", rule["rule_type"])
                components = {part.strip() for part in rule["components"].split(";") if part.strip()}
                self.assertEqual(expected_components, components)

    def test_grouped_rows_preserve_named_food(self) -> None:
        expectations = {
            "ounce cream cheese": "cream cheese|||",
            "soup chicken noodle": "chicken noodle soup|||",
            "soup cream of mushroom": "cream of mushroom soup|||",
            "kraft thousand island dressing": "thousand island dressing|||",
            "kraft ranch dressing": "ranch dressing|||",
            "duncan hines pineapple cake mix": "pineapple cake mix|||",
            "pineapple supreme cake mix": "pineapple cake mix|||",
            "instant pineapple pudding": "pineapple pudding mix|||",
            "pineapple instant pudding mix": "pineapple pudding mix|||",
        }
        for surface, concept_key in expectations.items():
            with self.subTest(surface=surface):
                rule = approved_rule_for_surface(surface, self.rules)
                self.assertIsNotNone(rule)
                assert rule is not None
                self.assertEqual("alias", rule["rule_type"])
                self.assertEqual(concept_key, rule["canonical_concept_key"])

        rule = approved_rule_for_surface("butter/oleo", self.rules)
        self.assertIsNotNone(rule)
        assert rule is not None
        self.assertEqual("alternative", rule["rule_type"])
        self.assertEqual({"butter|||", "margarine|||"}, set(rule["components"].split(";")))

    def test_loader_rejects_alias_without_canonical_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rules.csv"
            path.write_text(
                "\n".join(
                    [
                        "rule_id,rule_type,match_type,input_surface,canonical_concept_key,canonical_surface,components,status,evidence,reviewer,created_at",
                        "bad,alias,exact,(up to),,,non_food,approved,Parser fragment from quantity range,codex,2026-04-11",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_approved_normalization_rules(path)

    def test_known_or_surfaces_have_visible_components(self) -> None:
        expectations = {
            "butter or margarine": ["butter|||", "margarine|||"],
            "olive oil or vegetable oil": ["olive oil|||", "vegetable oil|||"],
            "ground beef or turkey": ["beef||ground|", "turkey||ground|"],
            "shortening or oil": ["shortening|||", "oil|||"],
            "canola or peanut oil, for deep-frying": ["canola oil|||", "peanut oil|||"],
        }
        for surface, expected_components in expectations.items():
            with self.subTest(surface=surface):
                rule = approved_rule_for_surface(surface, self.rules)
                self.assertIsNotNone(rule)
                self.assertEqual("alternative", rule["rule_type"])
                self.assertEqual(expected_components, rule["components"].split(";"))

    def test_same_food_or_surface_can_be_alias(self) -> None:
        rule = approved_rule_for_surface("heavy or whipping cream", self.rules)
        self.assertIsNotNone(rule)
        self.assertEqual("alias", rule["rule_type"])
        self.assertEqual("heavy cream|||", rule["canonical_concept_key"])

    def test_specific_cake_mix_surfaces_do_not_collapse_to_generic(self) -> None:
        expectations = {
            "yellow cake mix": {"yellow cake mix|||"},
            "yellow cake mix (duncan hines)": {"yellow cake mix|||"},
            "butter yellow cake mix": {"yellow cake mix|||"},
            "duncan hines yellow cake mix": {"yellow cake mix|||"},
            "duncan hines white cake mix": {"white cake mix||white|"},
            "duncan hines chocolate cake mix": {"chocolate cake mix|||"},
            "duncan hines swiss chocolate cake mix": {"swiss chocolate cake mix|||"},
            "duncan hines lemon cake mix": {"lemon cake mix|||"},
            "orange cake mix": {"orange cake mix|||"},
            "duncan hines orange supreme cake mix": {"orange cake mix|||"},
        }
        for surface, expected_concept_keys in expectations.items():
            with self.subTest(surface=surface):
                rule = approved_rule_for_surface(surface, self.rules)
                self.assertIsNotNone(rule)
                self.assertEqual("alias", rule["rule_type"])
                self.assertIn(rule["canonical_concept_key"], expected_concept_keys)
                self.assertNotEqual("cake mix|||", rule["canonical_concept_key"])

    def test_brand_only_cake_mix_can_collapse_to_generic(self) -> None:
        rule = approved_rule_for_surface("duncan hines cake mix", self.rules)
        self.assertIsNotNone(rule)
        assert rule is not None
        self.assertEqual("alias", rule["rule_type"])
        self.assertEqual("cake mix|||", rule["canonical_concept_key"])

    def test_broad_alternative_rules_with_fixed_outputs_are_quarantined(self) -> None:
        rows = {row["rule_id"]: row for row in self._approved_rows(include_all_statuses=True)}
        unsafe_rule_ids = {
            "h9_broad_x_or_y_oil_001",
            "h9_broad_x_or_y_cheese_001",
            "h9_broad_x_or_y_herb_fresh_001",
            "h9_broad_cream_soup_alt_001",
            "h9_broad_nut_alt_001",
            "h9_broad_dried_fresh_alt_001",
            "h6_water_or_stock_001",
            "h6_penne_or_rigatoni_001",
            "h7_red_or_yellow_pepper_001",
            "h8_sherry_red_wine_vinegar_001",
            "h8_balsamic_red_wine_vinegar_001",
            "h9_pinto_kidney_beans_001",
            "h9_white_cider_vinegar_001",
            "h9_pineapple_orange_juice_001",
            "h9_butter_or_veg_oil_001",
            "h9_rum_or_brandy_001",
            "h9_peach_orange_gelatin_001",
            "h9_lemon_lime_jello_002",
        }
        for rule_id in unsafe_rule_ids:
            with self.subTest(rule_id=rule_id):
                self.assertIn(rule_id, rows)
                self.assertNotEqual("approved", rows[rule_id]["status"])

        unsafe_surfaces = {
            "cream of celery soup or cream of potato soup": "cream of mushroom soup|||;cream of chicken soup|||",
            "swiss cheese or gruyere cheese": "cheddar cheese|||;mozzarella cheese|||",
            "peanut oil or coconut oil": "olive oil|||;vegetable oil|||",
            "almonds or cashews": "pecan|||;walnut|||",
            "fresh dill or fresh mint": "basil|||fresh;parsley|||fresh",
            "water or chicken stock": "water|||;vegetable stock|||",
            "ziti or fusilli pasta": "penne|||;rigatoni|||",
            "green bell pepper or orange bell pepper": "red bell pepper|||;yellow bell pepper|||",
            "white wine vinegar or rice vinegar": "white vinegar|||;apple cider vinegar|||",
            "bourbon or cognac": "rum|||;brandy|||",
        }
        for surface, forbidden_components in unsafe_surfaces.items():
            with self.subTest(surface=surface):
                rule = approved_rule_for_surface(surface, self.rules)
                if rule is not None:
                    self.assertNotEqual(forbidden_components, rule.get("components", ""))

    def test_single_flavor_cake_mix_is_not_hidden_yellow_white_alternative(self) -> None:
        unsafe_components = {
            "yellow cake mix|||;white cake mix|||",
            "yellow cake mix|||;white cake mix||white|",
            "white cake mix|||;yellow cake mix|||",
            "white cake mix||white|;yellow cake mix|||",
        }
        for surface in ["lemon cake mix", "chocolate cake mix", "spice cake mix"]:
            with self.subTest(surface=surface):
                rule = approved_rule_for_surface(surface, self.rules)
                if rule is not None:
                    self.assertNotEqual("alternative", rule["rule_type"])
                    self.assertNotIn(rule["components"], unsafe_components)

    def test_cake_mix_flavor_alternatives_keep_visible_flavors(self) -> None:
        rule = approved_rule_for_surface("lemon or chocolate cake mix", self.rules)
        if rule is not None:
            components = {part.strip() for part in rule["components"].split(";") if part.strip()}
            self.assertTrue(any(component.startswith("lemon cake mix|") for component in components), components)
            self.assertTrue(any(component.startswith("chocolate cake mix|") for component in components), components)

    def test_cake_mix_alternative_components_use_contract_keys(self) -> None:
        expectations = {
            "white cake mix or yellow cake mix": {"white cake mix||white|", "yellow cake mix|||"},
            "yellow cake mix or white cake mix": {"white cake mix||white|", "yellow cake mix|||"},
            "yellow or lemon cake mix": {"yellow cake mix|||", "lemon cake mix|||"},
        }
        for surface, expected_components in expectations.items():
            with self.subTest(surface=surface):
                rule = approved_rule_for_surface(surface, self.rules)
                self.assertIsNotNone(rule)
                self.assertEqual("alternative", rule["rule_type"])
                components = {part.strip() for part in rule["components"].split(";") if part.strip()}
                self.assertEqual(expected_components, components)
                self.assertTrue(components.issubset(CONTRACTS.keys()), components)

    def test_static_or_choices_are_not_collapsed_by_private_code(self) -> None:
        self.assertIsNone(_collapse_alternative("butter or margarine"))
        self.assertIsNone(_collapse_alternative("whipped cream or ice cream"))

    def test_split_rule_keeps_salt_and_pepper_separate(self) -> None:
        rule = approved_rule_for_surface("salt and pepper", self.rules)
        self.assertIsNotNone(rule)
        self.assertEqual("split", rule["rule_type"])
        self.assertEqual(["salt|||", "black pepper|||"], rule["components"].split(";"))

    def test_recipe_instruction_rejects_exit_food_debt(self) -> None:
        self.assertEqual(
            ("unresolved_explicit", "non_food", "recipe_instruction"),
            route_resolution("needs_review", "recipe_instruction", ""),
        )

    @staticmethod
    def _approved_rows(include_all_statuses: bool = False) -> list[dict[str, str]]:
        with DEFAULT_APPROVED_RULES_CSV.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if include_all_statuses:
            return rows
        return [row for row in rows if row["status"] == "approved"]


class ParserAndDictionaryPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qualified, cls.bases, cls.aliases = load_dictionary(DEFAULT_DICTIONARY_CSV)

    def test_high_value_parser_surfaces(self) -> None:
        cases = {
            "1 cup orange juice, freshly squeezed": ("1", "cup", "orange juice, freshly squeezed"),
            "1 cup orange juice, chilled": ("1", "cup", "orange juice"),
            "2 cups shredded sharp cheddar cheese": ("2", "cups", "sharp cheddar cheese"),
            "1/4 cup milk": ("1/4", "cup", "milk"),
            "5-6 lb ham": ("5-6", "lb", "ham"),
            "5 lb bone-in ham": ("5", "lb", "bone-in ham"),
            "1 cup green beans, frozen": ("1", "cup", "green beans"),
            "zest of 1 lemon": ("", "", "lemon zest"),
            "small pkg vanilla pudding mix": ("", "", "vanilla pudding mix"),
            "1 c. 7-Up": ("1", "c", "lemon lime soda"),
            "1 cup 4% cottage cheese": ("1", "cup", "4% cottage cheese"),
            "1 lb 90% lean ground beef": ("1", "lb", "90% lean ground beef"),
            "1 box 10x powdered sugar": ("1", "box", "10x powdered sugar"),
            "1 can onion soup": ("1", "can", "onion soup"),
            "1 cup v8 vegetable juice": ("1", "cup", "vegetable juice"),
            "scant 1/2 teaspoon salt": ("1/2", "teaspoon", "salt"),
            "1\\2 tsp. salt": ("1/2", "tsp", "salt"),
            "juice 1 lemon": ("1", "count", "lemon juice"),
            "juice 1/2 lemon": ("1/2", "count", "lemon juice"),
            "juice from 2 lemons": ("2", "count", "lemon juice"),
            "1 cup shredded mozzarella cheese about 4 oz": ("1", "cup", "mozzarella cheese"),
            "1 cup all-purpose flour + 2 tbsp": ("1", "cup", "all-purpose flour"),
            "1 cup all-purpose flour, plus 2 tbsp": ("1", "cup", "all-purpose flour"),
            "1 stick unsalted butter, chilled and cut into 1\" pieces": ("1", "stick", "unsalted butter"),
            "1 bottle of water, 20 fl oz": ("1", "bottle", "water"),
            "1 cup blueberries Whole Foods 3 For $10.00 thru 02/09": ("1", "cup", "blueberries"),
            "2 cups cooked chicken": ("2", "cups", "cooked chicken"),
            "2 cups chopped cooked chicken Whole Foods 1 lb For $3.99 thru 02/09": ("2", "cups", "cooked chicken"),
            "2 8-ounce packages cream cheese, room temperature": ("16", "ounce", "cream cheese"),
            "1 14 1/2-ounce can diced tomatoes in juice": ("14.5", "ounce", "tomatoes in juice"),
            "1 cup 2% cheddar cheese, shredded": ("1", "cup", "reduced-fat cheddar cheese"),
            "2 cups cold 2% milk": ("2", "cups", "reduced-fat milk"),
            "1 tablespoon minced garlic (3 cloves)": ("1", "tablespoon", "garlic"),
            "1 head garlic, separated into cloves and peeled": ("1", "head", "garlic"),
            "Zest of 1 lemon, finely grated": ("", "", "lemon zest"),
            "1 c. milk, scalded and cooled": ("1", "c", "milk"),
            "3 tablespoons unsalted butter, melted and cooled slightly": ("3", "tablespoons", "unsalted butter"),
            "4 chicken breasts (boneless and skinless)": ("4", "", "chicken breast"),
            "1 lemon, juice of, only": ("1", "", "lemon juice"),
            "1 pkg. (10 oz.) frozen chopped spinach, thawed, squeezed dry": ("10", "ounce", "frozen chopped spinach"),
            "1 (12 oz.) cool whip": ("12", "ounce", "cool whip"),
            "1 (1 lb. 4 oz.) can crushed pineapple": ("20", "ounce", "pineapple"),
            "2 Tbls butter": ("2", "tablespoons", "butter"),
            "sprig of parsley": ("1", "sprig", "parsley"),
            "2 envelopes Fleischmann's(R) RapidRise Yeast": ("2", "envelopes", "rapidrise yeast"),
            "1 vanilla bean, split, seeds scraped": ("1", "", "vanilla bean"),
            "2 slices red onion, separated into rings": ("2", "slices", "red onion"),
            "4 skinned and boned chicken breast halves": ("4", "", "chicken breast"),
            "4 pork chops, 1 inch thick": ("4", "", "pork chop"),
            "1 package Taco Seasoning, 1 Ounce Packet": ("1", "package", "taco seasoning"),
            "2 c. Nabisco 100% bran": ("2", "c", "100% bran"),
            "1/2 cup PHILADELPHIA Chive & Onion Cream Cheese Spread": ("1/2", "cup", "chive onion cream cheese spread"),
            "1 can green chily": ("1", "can", "green chili"),
            "1 cup oreo cooky crumbs": ("1", "cup", "oreo cookie crumbs"),
            "1 tsp. tumeric": ("1", "tsp", "turmeric"),
            "1 cup chedder cheese": ("1", "cup", "cheddar cheese"),
            "1 chicken boullion cube": ("1", "", "chicken bouillon cube"),
            "2 tablespoons oilve oil": ("2", "tablespoons", "olive oil"),
            "4 pita bread rounds": ("4", "round", "pita bread"),
            "4 celery ribs": ("4", "rib", "celery"),
            "1 lemon, sliced into rounds": ("1", "", "lemon"),
            "2 medium zucchini, sliced into 1/4-inch rounds": ("2", "", "zucchini"),
            "1 large eggplant, sliced into 1/2-inch rounds": ("1", "", "large eggplant"),
            "1 baguette, sliced into 1/2-inch rounds": ("1", "", "baguette"),
        }
        for raw, (quantity, unit, surface) in cases.items():
            with self.subTest(raw=raw):
                parsed = parse_line(raw)
                self.assertEqual(quantity, parsed["parsed_quantity"])
                self.assertEqual(unit, parsed["parsed_unit"])
                self.assertEqual(surface, parsed["cleaned_surface"])

    def test_dangerous_dictionary_distinctions(self) -> None:
        expectations = {
            "green beans": ("surface_alias_match", "green bean"),
            "green bean casserole": ("no_dictionary_match", None),
            "ham": ("surface_alias_match", "ham"),
            "deli ham": ("surface_alias_match", "deli ham"),
            "caster sugar": ("surface_alias_match", "caster sugar"),
            "orange juice": ("surface_alias_match", "orange juice"),
            "lemon lime soda": ("surface_alias_match", "lemon lime soda"),
            "fat-free, less-sodium chicken broth": ("no_dictionary_match", None),
        }
        for surface, (expected_status, expected_base) in expectations.items():
            with self.subTest(surface=surface):
                normalized, review_reason = normalize_surface(surface)
                status, row, _ = match_dictionary(
                    normalized,
                    review_reason,
                    self.qualified,
                    self.bases,
                    self.aliases,
                    surface,
                )
                self.assertEqual(expected_status, status)
                actual_base = row["base_food"] if row else None
                self.assertEqual(expected_base, actual_base)

    def test_recent_high_frequency_rules_route_safely(self) -> None:
        rules = load_approved_normalization_rules(DEFAULT_APPROVED_RULES_CSV)
        expectations = {
            "water, for steaming": ("manual_quantity", "water|||", ""),
            "use as much hot cooked white rice": ("manual_quantity", "white rice|||cooked", ""),
            "sugar substitute equivalent to 1/2 cup sugar": ("manual_quantity", "sugar substitute|||", ""),
            "garlic powder, salt and pepper": ("split", "", "garlic powder|||;salt|||;black pepper|||"),
            "bone-in, skin-on chicken thighs": ("alias", "chicken thigh|||bone-in skin-on", ""),
            "frozen strawberries": ("alias", "strawberry|||frozen", ""),
            "frozen strawberries, partially thawed": ("alias", "strawberry|||frozen", ""),
            "whole red bell pepper": ("alias", "red bell pepper|||", ""),
            "whole green bell pepper": ("alias", "green bell pepper|||", ""),
            "whole bell pepper": ("alias", "bell pepper|||", ""),
            "red sweet pepper": ("alias", "red pepper|||", ""),
            "sweet green pepper": ("alias", "green pepper|||", ""),
            "green sweet pepper": ("alias", "green pepper|||", ""),
            "sweet yellow pepper": ("alias", "yellow pepper|||", ""),
            "lower sodium soy sauce": ("alias", "low sodium soy sauce|||", ""),
            "italian cheese blend": ("alias", "italian cheese blend||cheese|", ""),
            "four cheese blend": ("alias", "italian cheese blend||cheese|", ""),
            "cheese blend": ("alias", "italian cheese blend||cheese|", ""),
            "hot red pepper sauce": ("alias", "red hot pepper sauce|||", ""),
            "tabasco pepper sauce": ("alias", "tabasco sauce|||", ""),
            "few dashes hot sauce": ("alias", "hot sauce|||", ""),
            "several dashes hot sauce": ("alias", "hot sauce|||", ""),
            "fat-free, less-sodium chicken broth": ("alias", "chicken broth|reduced-sodium||", ""),
            "fat-free, lower-sodium chicken broth": ("alias", "chicken broth|reduced-sodium||", ""),
        }
        for surface, (rule_type, concept_key, components) in expectations.items():
            with self.subTest(surface=surface):
                rule = approved_rule_for_surface(surface, rules)
                self.assertIsNotNone(rule)
                self.assertEqual(rule_type, rule["rule_type"])
                self.assertEqual(concept_key, rule["canonical_concept_key"])
                self.assertEqual(components, rule["components"])

    def test_reviewed_rules_override_generated_brand_dictionary_aliases(self) -> None:
        rules = load_approved_normalization_rules(DEFAULT_APPROVED_RULES_CSV)
        cases = {
            "1 (20 ounce) package Simply Potatoes® shredded hash browns": "hash brown",
            "1 tablespoon McCormick's Montreal Brand steak seasoning": "steak seasoning",
            "1 lb. ground round": "ground beef",
            "2 racks pork ribs, membrane removed": "pork spareribs",
            "2 1/2 to 3 pounds pork spareribs, St. Louis cut": "pork spareribs",
            "3 tablespoons green sweet relish": "sweet relish",
            "1/2 teaspoon clove powder": "ground cloves",
            "jalapeño peppers, chopped (seeds removed for less heat)": "jalapeno",
            "3/4 cup Caesar style vinaigrette dressing": "caesar dressing",
            "1 lb dry penne pasta": "dry penne pasta",
            "8 ounces uncooked penne pasta": "uncooked penne pasta",
            "1 cup uncooked macaroni": "uncooked macaroni",
            "Hot cooked rice, cooked without salt": "cooked rice",
            "1/2 teaspoon savory": "savory",
            "1 tablespoon freshly grated gingerroot": "grated ginger",
            "1/2 cup freshly grated romano cheese": "romano cheese",
            "6 whole allspice berries": "allspice berry",
            "hot steamed rice, for serving": "cooked rice",
            "Cooked noodles or rice, for serving": "cooked rice",
            "Cooked rice or pasta, for serving": "cooked rice",
            "2 cups hot cooked white rice": "cooked rice",
            "2 cups cooked rice": "cooked rice",
            "2 cups cooked brown rice": "cooked brown rice",
            "2 cups uncooked minute white rice": "minute white rice",
            "1 additional tablespoon milk, if needed": "milk",
            "2 tablespoons reserved bacon drippings": "bacon dripping",
            "4 whole wheat hamburger buns, toasted": "whole wheat hamburger bun",
            "2 ripe hass avocados": "avocado",
            "2 large eggplants": "eggplant",
            "1 tablespoon freshly chopped parsley": "parsley",
            "freshly grated black pepper, to taste": "black pepper",
            "1/2 cup pecan pieces, toasted": "pecan",
            "1/2 cup walnut pieces, toasted": "walnut",
            "hot cooked noodles": "egg noodle",
            "2 cups uncooked medium egg noodles": "egg noodle",
            "1 cup m&m's plain chocolate candy": "m&m's milk chocolate candies",
            "1 hot dog bun": "hot dog bun",
            "1 teaspoon ground caraway": "caraway seed",
            "2 ounces unsweetened chocolate squares": "baking chocolate",
            "Pita chips, for serving": "pita chips",
            "2 large bell peppers, chopped": "bell pepper",
            "1 ounce prepared sweet-and-sour mix": "sweet-and-sour mix",
            "2 whole cinnamon sticks": "cinnamon stick",
            "2 whole wheat pita breads": "wheat pita bread",
            "1 (9 inch) chocolate crumb crust": "chocolate crumb crust",
            "1 teaspoon red pepper powder": "cayenne pepper",
            "2 cups rice bubbles": "puffed rice cereal",
            "1 can (6 oz) Italian-style tomato paste": "tomato paste",
            "1 tablespoon light sesame oil": "sesame oil",
            "1 tablespoon whole coriander seeds": "coriander",
            "1 chocolate graham cracker pie crust (9 inches)": "chocolate crumb crust",
            "1 cup whole milk yogurt": "yogurt",
            "1 tablespoon oil from sun-dried tomatoes": "olive oil",
            "1 cup crumbled queso fresco": "queso fresco",
            "2 scoops whey protein powder": "whey protein powder",
            "freshly ground coarse black pepper": "black pepper",
            "toasted chopped pecans": "pecan",
            "freshly grated pecorino romano cheese": "pecorino romano",
            "unsweetened chocolate square": "baking chocolate",
            "freshly shredded parmesan cheese": "grated parmesan cheese",
            "walnut halves, toasted": "walnut",
        }
        for raw, expected_base in cases.items():
            with self.subTest(raw=raw):
                parsed = parse_line(raw)
                rule = approved_rule_for_surface(parsed["cleaned_surface"], rules)
                self.assertIsNotNone(rule)
                normalized, _, status, _, dictionary_row = resolve_approved_rule(rule)
                self.assertEqual("approved_alias_match", status)
                self.assertIsNone(dictionary_row)
                self.assertEqual(expected_base, normalized["base_food"])

    def test_generic_cheese_is_nutrition_proxy_not_auto_cart(self) -> None:
        contract = CONTRACTS["generic cheese|||"]
        self.assertEqual("review_required", contract.policy)
        self.assertIn(contract.policy, REVIEW_BLOCKING_POLICIES)
        failures = check_candidate(
            contract,
            "generic cheese|||",
            "generic cheese",
            "CHEDDAR CHEESE",
            "Cheese",
            require_nutrition=False,
        )
        self.assertEqual([], failures)
        self.assertTrue(
            check_candidate(
                contract,
                "generic cheese|||",
                "generic cheese",
                "MACARONI AND CHEESE DINNER",
                "Mexican Dinner Mixes",
                require_nutrition=False,
            )
        )


class FullRecipeCalculationAuditTests(unittest.TestCase):
    def test_reviewed_alternative_uses_visible_default_for_calculation(self) -> None:
        row = {
            "dictionary_match_status": "approved_alternative_match",
            "resolution_action": "approved_alternative_options",
            "concept_base_food": "",
            "concept_variant": "",
            "concept_form": "",
            "concept_state": "",
            "approved_rule_components": "butter|||;margarine|||",
            "parsed_quantity": "1/2",
            "parsed_unit": "c",
            "normalized_line": "1/2 c. butter or margarine",
            "example_raw_line": "1/2 c. butter or margarine",
            "cleaned_surface": "butter or margarine",
            "recipe_count": "1",
        }
        product_statuses = {
            "butter|||": {
                "audit_status": "contract_passed",
                "policy": "direct_buy",
            }
        }
        result = evaluate_full_recipe_line(row, product_statuses, set(), set(), {})
        self.assertEqual("calculation_candidate", result["failure_bucket"])
        self.assertEqual("butter|||", result["concept_key"])
        self.assertIn("alternative_default_first_option", result["product_policy"])

    def test_unmeasured_alternative_still_needs_quantity(self) -> None:
        row = {
            "dictionary_match_status": "approved_alternative_match",
            "resolution_action": "approved_alternative_options",
            "concept_base_food": "",
            "concept_variant": "",
            "concept_form": "",
            "concept_state": "",
            "approved_rule_components": "butter|||;margarine|||",
            "parsed_quantity": "",
            "parsed_unit": "",
            "normalized_line": "butter or margarine",
            "example_raw_line": "butter or margarine",
            "cleaned_surface": "butter or margarine",
            "recipe_count": "1",
        }
        product_statuses = {
            "butter|||": {
                "audit_status": "contract_passed",
                "policy": "direct_buy",
            }
        }
        result = evaluate_full_recipe_line(row, product_statuses, set(), set(), {})
        self.assertEqual("quantity_missing", result["failure_bucket"])
        self.assertEqual("butter|||", result["concept_key"])

    def test_reviewed_sr28_anchor_counts_as_calculation_coverage(self) -> None:
        row = {
            "dictionary_match_status": "approved_alias_match",
            "resolution_action": "approved_alias",
            "concept_base_food": "hash brown",
            "concept_variant": "",
            "concept_form": "",
            "concept_state": "",
            "approved_rule_components": "",
            "parsed_quantity": "20",
            "parsed_unit": "ounce",
            "normalized_line": "1 (20 ounce) package simply potatoes® shredded hash browns",
            "example_raw_line": "1 (20 ounce) package Simply Potatoes® shredded hash browns",
            "cleaned_surface": "simply potatoes® shredded hash browns",
            "recipe_count": "1",
        }
        product_statuses = {
            "hash brown|||": {
                "audit_status": "not_candidate_covered",
                "policy": "",
            }
        }
        result = evaluate_full_recipe_line(row, product_statuses, set(), set(), {}, {"hash brown|||"})
        self.assertEqual("calculation_candidate", result["failure_bucket"])
        self.assertEqual("sr28_covered", result["product_audit_status"])
        self.assertEqual("sr28_nutrition_anchor", result["product_policy"])

    def test_reviewed_manual_quantity_policy_can_calculate(self) -> None:
        row = {
            "dictionary_match_status": "approved_manual_quantity_match",
            "resolution_action": "manual_quantity_required",
            "concept_base_food": "flour",
            "concept_variant": "",
            "concept_form": "",
            "concept_state": "",
            "approved_rule_components": "",
            "parsed_quantity": "",
            "parsed_unit": "",
            "normalized_line": "flour for dredging",
            "example_raw_line": "flour for dredging",
            "cleaned_surface": "flour for dredging",
            "recipe_count": "1",
        }
        product_statuses = {
            "flour|||": {
                "audit_status": "contract_passed",
                "policy": "direct_buy",
            }
        }
        quantity_policies = {
            ("flour|||", "manual_quantity_required"): [
                {
                    "include": re.compile(r"(?i)\bfor dredging\b"),
                    "exclude": None,
                }
            ]
        }
        result = evaluate_full_recipe_line(row, product_statuses, set(), set(), quantity_policies)
        self.assertEqual("calculation_candidate", result["failure_bucket"])
        self.assertEqual("quantity_default_applied", result["quantity_bucket"])

    def test_split_to_taste_components_have_nutrition_totals(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE product_nutrition (
                concept_key TEXT PRIMARY KEY,
                nutrition_status TEXT,
                calories_per_g REAL,
                protein_g_per_g REAL,
                fat_g_per_g REAL,
                carbs_g_per_g REAL,
                sodium_mg_per_g REAL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE to_taste_defaults (
                concept_key TEXT PRIMARY KEY,
                default_grams REAL NOT NULL,
                rationale TEXT,
                reviewer TEXT,
                evidence TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO product_nutrition VALUES (?,?,?,?,?,?,?)",
            [
                ("salt|||", "nutrition_ready_sr28_fallback", 0.0, 0.0, 0.0, 0.0, 387.58),
                ("black pepper|||", "nutrition_ready_sr28_anchor", 2.51, 0.1039, 0.0326, 0.6395, 0.2),
            ],
        )
        conn.executemany(
            "INSERT INTO to_taste_defaults VALUES (?,?,?,?,?)",
            [
                ("salt|||", 1.0, "", "", ""),
                ("black pepper|||", 0.3, "", "", ""),
            ],
        )
        install_split_default_nutrition_functions(conn)

        row = conn.execute(
            """
            SELECT
                split_default_ready('salt|||;black pepper|||'),
                split_default_grams('salt|||;black pepper|||'),
                split_default_nutrient('salt|||;black pepper|||', 'calories'),
                split_default_nutrient('salt|||;black pepper|||', 'sodium')
            """
        ).fetchone()
        self.assertEqual(1, row[0])
        self.assertAlmostEqual(1.3, row[1])
        self.assertAlmostEqual(0.753, row[2])
        self.assertAlmostEqual(387.64, row[3])
        conn.close()

    def test_audit_converts_mass_and_density_volume_units_to_grams(self) -> None:
        conn = sqlite3.connect(":memory:")
        install_household_unit_functions(conn, {})

        row = conn.execute(
            """
            SELECT
                mass_unit_grams('85', 'g'),
                mass_unit_grams('2', 'ounces'),
                mass_unit_grams('1', 'lb'),
                density_volume_unit_grams('1', 'cup', 1.0),
                density_volume_unit_grams('2', 'tablespoons', 0.92)
            """
        ).fetchone()
        self.assertAlmostEqual(85.0, row[0])
        self.assertAlmostEqual(56.699, row[1], places=3)
        self.assertAlmostEqual(453.592, row[2], places=3)
        self.assertAlmostEqual(236.588, row[3], places=3)
        self.assertAlmostEqual(27.208, row[4], places=3)
        conn.close()

    def test_display_parse_surfaces_drop_prep_prefixes_for_item_fallback(self) -> None:
        conn = sqlite3.connect(":memory:")
        install_display_parse_functions(conn)

        row = conn.execute(
            """
            SELECT
                parsed_display_surface('1 cup packed julienned strips fresh spinach'),
                parsed_display_surface('2 cups cut up seedless watermelon'),
                parsed_display_surface('500 g pureed fresh papayas (paw paw)'),
                parsed_display_unit('1 large garlic clove'),
                parsed_display_unit('4 slices fresh ginger'),
                parsed_display_surface('4 slices fresh ginger'),
                parsed_display_unit('2 -3 pieces pared fresh lemon rind'),
                parsed_display_surface('2 -3 pieces pared fresh lemon rind'),
                parsed_display_surface('4 cups loosely packed baby spinach'),
                parsed_display_surface('1/3 cup very thin slices red onion'),
                parsed_display_unit('1 punnet raspberries'),
                parsed_display_surface('1 punnet raspberries'),
                parsed_display_unit('3 - 4 chive blossoms, pulled apart'),
                parsed_display_surface('3 - 4 chive blossoms, pulled apart')
            """
        ).fetchone()
        self.assertEqual("spinach", row[0])
        self.assertEqual("watermelon", row[1])
        self.assertEqual("papayas", row[2])
        self.assertEqual("clove", row[3])
        self.assertEqual("slice", normalize_household_unit(row[4]))
        self.assertEqual("fresh ginger", row[5])
        self.assertEqual("piece", normalize_household_unit(row[6]))
        self.assertEqual("lemon rind", row[7])
        self.assertEqual("baby spinach", row[8])
        self.assertEqual("red onion", row[9])
        self.assertEqual("punnet", normalize_household_unit(row[10]))
        self.assertEqual("raspberries", row[11])
        self.assertEqual("blossom", normalize_household_unit(row[12]))
        self.assertEqual("chive blossoms", row[13])
        conn.close()


class ProductContractPreflightTests(unittest.TestCase):
    def test_product_contract_json_fields_parse_and_concept_keys_are_unique(self) -> None:
        path = REVIEWED_REGISTRIES["product_contracts"]
        seen: dict[str, str] = {}
        failures = []
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                parsed = {}
                for field in [
                    "concept_keys",
                    "allowed_categories",
                    "required_all",
                    "required_any",
                    "forbidden_any",
                ]:
                    try:
                        parsed[field] = json.loads(row[field])
                    except json.JSONDecodeError as exc:
                        failures.append((row["contract_id"], field, str(exc)))
                for concept_key in parsed.get("concept_keys", []):
                    if concept_key in seen:
                        failures.append((row["contract_id"], "duplicate_concept_key", concept_key))
                    seen[concept_key] = row["contract_id"]
                has_positive_gate = bool(parsed.get("required_all") or parsed.get("required_any"))
                if row["policy"] != "no_buy" and not has_positive_gate:
                    failures.append((row["contract_id"], "missing_positive_gate", row["policy"]))
        self.assertEqual([], failures)

    def test_product_family_rules_block_known_wrong_cart_items(self) -> None:
        self.assertGreater(len(load_family_rules()), 0)
        cases = [
            ("oscar mayer deli fresh ham|||fresh", "oscar mayer deli fresh ham", "Ham Steaks, 5 count, 32 oz.", "Meat/Poultry/Other Animals  Prepared/Processed"),
            ("blue cheese dressing||cheese|", "blue cheese dressing", "BLUE CHEESE", "Cheese"),
            ("honey mustard dressing|||", "honey mustard dressing", "MUSTARD", "Ketchup, Mustard, BBQ & Cheese Sauce"),
            ("buttermilk ranch salad dressing mix|||", "buttermilk ranch salad dressing mix", "BUTTERMILK", "Milk"),
            ("skim milk||powder|", "skim milk powder", "SKIM MILK", "Milk"),
            ("chicken stock||powder|", "chicken stock powder", "CHICKEN STOCK", "Canned Soup"),
            ("red cinnamon candy|||", "red cinnamon candy", "CINNAMON", "Herbs & Spices"),
            ("cinnamon baking chip|||", "cinnamon baking chip", "CINNAMON", "Herbs & Spices"),
            ("fritos corn chip|||", "fritos corn chip", "CORN", "Frozen Vegetables"),
            ("canned corn|||", "canned corn", "CORN", "Frozen Vegetables"),
            ("ears corn|||", "ears corn", "CORN", "Frozen Vegetables"),
            ("corn on the cob|||", "corn on the cob", "CORN", "Frozen Vegetables"),
            ("baby corn|||", "baby corn", "CORN", "Frozen Vegetables"),
            ("snipped fresh dill|||fresh", "snipped fresh dill", "DILL WEED", "Herbs & Spices"),
            ("dill|||fresh", "fresh dill", "DILL STIR-IN PASTE, DILL", "Pre-Packaged Fruit & Vegetables"),
            ("snipped fresh parsley|||fresh", "snipped fresh parsley", "PARSLEY", "Herbs & Spices"),
            ("parsley|||fresh", "fresh parsley", "PARSLEY HERB PUREE", "Pre-Packaged Fruit & Vegetables"),
            ("cilantro sprig|||", "cilantro sprig", "CILANTRO", "Herbs & Spices"),
            ("graham cracker crumb crust|||", "graham cracker crumb crust", "GRAHAM CRACKERS", "Cookies & Biscuits"),
            ("green bean|||fresh", "fresh green bean", "GREEN BEANS", "Frozen Vegetables"),
        ]
        for concept_key, phrase, description, category in cases:
            with self.subTest(concept_key=concept_key):
                failures = family_rule_failures(concept_key, phrase, description, category)
                self.assertTrue(failures, (concept_key, description, category))

    def test_product_family_rules_allow_positive_examples(self) -> None:
        cases = [
            ("deli ham|||", "deli ham", "sliced deli ham", "Ham/Cold Meats"),
            ("blue cheese dressing||cheese|", "blue cheese dressing", "BLUE CHEESE DRESSING", "Salad Dressing & Mayonnaise"),
            ("cinnamon baking chip|||", "cinnamon baking chip", "CINNAMON BAKING CHIPS", "Baking Decorations & Dessert Toppings"),
            ("fritos corn chip|||", "fritos corn chip", "FRITOS CORN CHIPS", "Chips, Pretzels & Snacks"),
            ("graham cracker crumb crust|||", "graham cracker crumb crust", "GRAHAM CRACKER PIE CRUST", "Crusts & Dough"),
            ("graham cracker crust|||prepared", "prepared graham cracker crust", "GRAHAM CRACKER", "Crusts & Dough"),
            ("skim milk||powder|", "skim milk powder", "INSTANT NONFAT DRY MILK POWDER", "Milk"),
            ("chicken stock||powder|", "chicken stock powder", "CHICKEN BOUILLON POWDER", "Seasoning Mixes, Salts, Marinades & Tenderizers"),
            ("red cinnamon candy|||", "red cinnamon candy", "CINNAMON HARD CANDY", "Candy"),
            ("canned corn|||", "canned corn", "WHOLE KERNEL CORN", "Canned Vegetables"),
            ("ears corn|||", "ears corn", "CORN ON THE COB", "Pre-Packaged Fruit & Vegetables"),
            ("baby corn|||", "baby corn", "BABY CORN", "Canned Vegetables"),
            ("cilantro sprig|||", "cilantro sprig", "CILANTRO", "Pre-Packaged Fruit & Vegetables"),
            ("parsley|||fresh", "fresh parsley", "PREMIUM CHOPPED PARSLEY", "Pre-Packaged Fruit & Vegetables"),
        ]
        for concept_key, phrase, description, category in cases:
            with self.subTest(concept_key=concept_key):
                failures = family_rule_failures(concept_key, phrase, description, category)
                self.assertEqual([], failures)

    def test_product_family_rules_ignore_known_compound_false_positives(self) -> None:
        cases = [
            ("steak sauce|||", "steak sauce", "STEAK SAUCE", "Ketchup, Mustard, BBQ & Cheese Sauce"),
            ("butter bean||butter|", "butter bean", "BUTTER BEANS", "Canned & Bottled Beans"),
            ("hot red pepper flake|red||", "red hot pepper flakes", "EXTRA HOT RED PEPPER FLAKES", "Herbs & Spices"),
            ("crusty bread|||", "crusty bread", "BREAD", "Breads & Buns"),
            ("cheese whiz|||", "cheese whiz", "CHEEZ WHIZ, ORIGINAL PASTEURIZED CHEESE SAUCE", "Cheese"),
            ("milk chocolate chip||milk|", "milk chocolate chip", "MILK CHOCOLATE CHIPS", "Baking Decorations & Dessert Toppings"),
            ("lemon juice|||fresh", "fresh lemon juice", "LEMONS", "Pre-Packaged Fruit & Vegetables"),
            ("parsley|||fresh", "fresh parsley", "PREMIUM CHOPPED PARSLEY", "Pre-Packaged Fruit & Vegetables"),
            ("ginger|||fresh", "fresh ginger", "GINGER ROOT, GINGER", "Herbs & Spices"),
            ("butter flavored cooking spray|||", "butter flavored cooking spray", "BUTTER FLAVORED COOKING SPRAY", "Vegetable & Cooking Oils"),
            ("butter cake mix||butter|", "butter cake mix", "CAKE MIX, VANILLA", "Cake, Cookie & Cupcake Mixes"),
            ("butter lettuce||butter|", "butter lettuce", "LETTUCE WRAPS", "Pre-Packaged Fruit & Vegetables"),
            ("cream cheese frosting||cheese|", "cream cheese frosting", "CREAM CHEESE FROSTING", "Baking Decorations & Dessert Toppings"),
            ("white breadcrumb||white|fresh", "fresh white breadcrumb", "BREAD CRUMBS", "Bread & Muffin Mixes"),
            ("yeast|||fresh", "fresh yeast", "YEAST EXTRACT", "Baking Additives & Extracts"),
            ("whipped cream|||fresh", "fresh whipped cream", "SWEETENED LIGHT WHIPPED CREAM", "Cream"),
            ("linguine|||fresh", "fresh linguine", "LINGUINE", "Pasta by Shape & Type"),
            ("key lime juice|||fresh", "fresh key lime juice", "LIME BLEND FROM CONCENTRATE", "Fruit & Vegetable Juice, Nectars & Fruit Drinks"),
            ("colby cheese|||", "colby cheese", "COLBY", "Cheese"),
            ("mozzarella cheese|||fresh", "fresh mozzarella cheese", "MOZZARELLA", "Cheese"),
            ("whole milk ricotta cheese|||", "whole milk ricotta cheese", "WHOLE MILK RICOTTA", "Cheese"),
            ("steak seasoning|||", "steak seasoning", "STEAK SEASONING", "Herbs & Spices"),
            ("grated parmesan cheese|||", "grated parmesan cheese", "PARMESAN CHEESE", "Cheese"),
            ("cooked rice|||", "cooked rice", "ORGANIC COOKED WHITE RICE", "Rice"),
            ("hamburger buns|||", "hamburger buns", "HAMBURGER BUNS", "Breads & Buns"),
            ("bay leaves|||", "bay leaves", "BAY LEAVES", "Herbs & Spices"),
            ("crushed red pepper|||", "crushed red pepper", "CRUSHED RED PEPPER", "Herbs & Spices"),
            ("cumin seeds|||", "cumin seeds", "CUMIN SEEDS", "Herbs & Spices"),
            ("grated ginger|||", "grated ginger", "ORGANIC GRATED GINGER", "Herbs & Spices"),
        ]
        for concept_key, phrase, description, category in cases:
            with self.subTest(concept_key=concept_key):
                failures = family_rule_failures(concept_key, phrase, description, category)
                self.assertEqual([], failures)

    def test_review_required_contract_policy_is_not_autocartable(self) -> None:
        contract = CONTRACTS["cake mix|||"]
        failures = check_candidate(
            contract,
            "cake mix|||",
            "cake mix",
            "CAKE MIX",
            "Cake, Cookie & Cupcake Mixes",
            require_nutrition=False,
        )
        self.assertEqual([], failures)
        self.assertEqual("review_required", contract.policy)

    def test_external_catalog_manual_product_policy_is_not_autocartable(self) -> None:
        for concept_key in [
            "asparagus|||fresh",
            "bean sprout|||fresh",
            "blueberry|||fresh",
            "broccoli|||fresh",
            "broccoli floret|||fresh",
            "corn|||fresh",
            "ears fresh corn|||fresh",
            "green bean|||fresh",
            "pea|||fresh",
            "peache|||fresh",
            "pineapple chunk|||fresh",
            "strawberry|||fresh",
            "okra|||fresh",
            "asparagus spear|||fresh",
            "jalapeno|||fresh",
            "jalapeno pepper|||fresh",
            "baby carrot|||fresh",
            "green pea|||fresh",
            "snow pea|||fresh",
            "broccoli floweret|||fresh",
            "brussels sprout|||fresh",
            "torn fresh spinach|||fresh",
        ]:
            with self.subTest(concept_key=concept_key):
                contract = CONTRACTS[concept_key]
                self.assertEqual("external_catalog_manual_product", contract.policy)
                self.assertIn(contract.policy, REVIEW_BLOCKING_POLICIES)
                self.assertNotIn("Frozen Vegetables", contract.allowed_categories)
                self.assertNotIn("Frozen Fruit & Fruit Juice Concentrates", contract.allowed_categories)


class NutritionAnchorPreflightTests(unittest.TestCase):
    def test_approved_sr28_fallback_ids_match_local_food_descriptions(self) -> None:
        food_csv = IMPLEMENTATION_ROOT.parent / "data" / "sr28_csv" / "food.csv"
        id_to_description = {}
        with food_csv.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                id_to_description[(row.get("fdc_id") or "").strip()] = (row.get("description") or "").strip()

        failures = []
        with REVIEWED_REGISTRIES["sr28_fallbacks"].open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["review_status"] != "approved":
                    continue
                fdc_id = row["fdc_id"]
                reviewed_description = row["sr28_description"]
                actual_description = id_to_description.get(fdc_id)
                if normalize_line(actual_description) != normalize_line(reviewed_description):
                    failures.append((row["concept_key"], fdc_id, reviewed_description, actual_description))
        self.assertEqual([], failures)

    def test_reviewed_sr28_fallbacks_cover_label_rounded_cases(self) -> None:
        food_csv = IMPLEMENTATION_ROOT.parent / "data" / "sr28_csv" / "food.csv"
        id_to_description = {}
        with food_csv.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                id_to_description[(row.get("fdc_id") or "").strip()] = (row.get("description") or "").strip()

        expected = {
            "vanilla essence|||": ("173471", "Vanilla extract"),
            "salt|||": ("173468", "Salt, table"),
            "pepper|||": ("170931", "Spices, pepper, black"),
            "mint|||": ("172239", "Spearmint, dried"),
            "wine vinegar|||": ("172240", "Vinegar, red wine"),
            "wine vinegar|red||": ("172240", "Vinegar, red wine"),
            "grated parmesan cheese|||": ("171247", "Cheese, parmesan, grated"),
            "cooked rice|||": ("168878", "Rice, white, long-grain, regular, enriched, cooked"),
            "hamburger buns|||": ("172796", "Rolls, hamburger or hotdog, plain"),
            "grated ginger|||": ("169231", "Ginger root, raw"),
            "cilantro sprig|||": ("169997", "Coriander (cilantro) leaves, raw"),
            "cilantro sprig|||fresh": ("169997", "Coriander (cilantro) leaves, raw"),
            "snipped fresh cilantro|||fresh": ("169997", "Coriander (cilantro) leaves, raw"),
            "dill|||fresh": ("172233", "Dill weed, fresh"),
            "fresh dill|||": ("172233", "Dill weed, fresh"),
            "snipped fresh dill|||fresh": ("172233", "Dill weed, fresh"),
            "handful fresh dill|||fresh": ("172233", "Dill weed, fresh"),
            "flat leaf parsley|||fresh": ("170416", "Parsley, fresh"),
            "flat-leaf parsley|||fresh": ("170416", "Parsley, fresh"),
            "flat-leaf parsley leaf|||fresh": ("170416", "Parsley, fresh"),
            "italian parsley|||fresh": ("170416", "Parsley, fresh"),
            "snipped fresh parsley|||fresh": ("170416", "Parsley, fresh"),
            "bay leaves|||": ("170917", "Spices, bay leaf"),
            "cumin seeds|||": ("170923", "Spices, cumin seed"),
            "crushed red pepper|||": ("170932", "Spices, pepper, red or cayenne"),
            "savory|||": ("170936", "Spices, savory, ground"),
            "romano cheese|||": ("171249", "Cheese, romano"),
            "minute white rice|||": ("169709", "Rice, white, long-grain, precooked or instant, enriched, dry"),
            "bacon dripping|||": ("172345", "Animal fat, bacon grease"),
            "whole wheat hamburger bun|||": ("174090", "Rolls, hamburger or hot dog, whole wheat"),
            "walnut|||": ("170187", "Nuts, walnuts, english"),
            "m&m's milk chocolate candies|||": ("169583", "Candies, MARS SNACKFOOD US, M&M's Milk Chocolate Candies"),
            "baguette|||": ("172675", "Bread, french or vienna (includes sourdough)"),
            "hot dog bun|||": ("172796", "Rolls, hamburger or hotdog, plain"),
            "caraway|||": ("170918", "Spices, caraway seed"),
            "baking chocolate|unsweetened|squares|": ("167568", "Baking chocolate, unsweetened, squares"),
            "pita chips|||": ("173147", "Snacks, pita chips, salted"),
            "sweet-and-sour mix|||": ("174811", "Beverages, Whiskey sour mix, bottled"),
            "cinnamon stick|||": ("171320", "Spices, cinnamon, ground"),
            "wheat pita bread|||": ("174916", "Bread, pita, whole-wheat"),
            "pita bread|||": ("174915", "Bread, pita, white, enriched"),
            "chocolate crumb crust|||": ("167521", "Pie Crust, Cookie-type, Chocolate, Ready Crust"),
            "caramels|||": ("167974", "Candies, caramels"),
            "puffed rice cereal|||": ("173912", "Cereals ready-to-eat, rice, puffed, fortified"),
            "tomato paste|||": (
                "170459",
                "Tomato products, canned, paste, without salt added (Includes foods for USDA's Food Distribution Program)",
            ),
            "buffalo meat|||": ("175299", "Game meat, buffalo, water, raw"),
            "bison|||": ("173851", "Game meat, bison, separable lean only, raw"),
            "ground beef|||": ("174036", "Beef, ground, 80% lean meat / 20% fat, raw"),
            "ground sirloin|||": ("174030", "Beef, ground, 90% lean meat / 10% fat, raw"),
            "butter|low-fat||": ("172344", "Butter, light, stick, without salt"),
            "instant chicken bouillon granules|||": ("171562", "Soup, chicken broth or bouillon, dry"),
            "yogurt|whole-milk||": ("171284", "Yogurt, plain, whole milk"),
            "peas|||frozen": (
                "170016",
                "Peas, green, frozen, unprepared (Includes foods for USDA's Food Distribution Program)",
            ),
            "queso fresco|||": ("172223", "Cheese, fresh, queso fresco"),
            "soymilk|light||": ("173766", "Soymilk, original and vanilla, light, with added calcium, vitamins A and D"),
            "large egg|||": ("171287", "Egg, whole, raw, fresh"),
            "gingersnap||crumb|": ("174956", "Cookies, gingersnaps"),
            "beef stock||powder|": ("171560", "Soup, beef broth or bouillon, powder, dry"),
            "whey protein powder|||": ("173180", "Beverages, Protein powder whey based"),
            "white chicken meat|||": ("171110", "Chicken, canned, no broth"),
            "canned biscuit|||": ("172670", "Biscuits, plain or buttermilk, prepared from recipe"),
        }
        fallback_rows = {}
        with REVIEWED_REGISTRIES["sr28_fallbacks"].open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["review_status"] == "approved":
                    fallback_rows[row["concept_key"]] = row

        failures = []
        for concept_key, (expected_id, expected_description) in expected.items():
            row = fallback_rows.get(concept_key)
            if not row:
                failures.append((concept_key, "missing fallback row"))
                continue
            actual_id = row["fdc_id"]
            actual_description = row["sr28_description"]
            if (actual_id, actual_description) != (expected_id, expected_description):
                failures.append((concept_key, actual_id, actual_description))
            if id_to_description.get(actual_id) != actual_description:
                failures.append((concept_key, actual_id, actual_description, id_to_description.get(actual_id)))
        self.assertEqual([], failures)

    def test_reviewed_nutrition_anchors_cover_known_wrong_family_audit_cases(self) -> None:
        path = REVIEWED_REGISTRIES["nutrition_anchors"]
        with path.open(newline="", encoding="utf-8") as handle:
            anchors = {row["concept_key"]: row for row in csv.DictReader(handle)}
        expected = {
            "cinnamon|||": ("SR28", "171320"),
            "ginger||ground|": ("SR28", "170926"),
            "ginger|||fresh": ("SR28", "169231"),
            "fresh ginger|||": ("SR28", "169231"),
            "zucchini|||": ("SR28", "169291"),
            "buttermilk|||": ("SR28", "172225"),
            "vanilla extract|||": ("SR28", "173471"),
            "white onion||white|": ("SR28", "170000"),
            "red potato|||": ("SR28", "170029"),
            "egg noodle|||": ("SR28", "169732"),
            "light cream|||": ("SR28", "170857"),
            "white rum||white|": ("FNDDS", "93504000"),
            "cola|||": ("FNDDS", "92410310"),
        }
        for concept_key, (system, food_id) in expected.items():
            with self.subTest(concept_key=concept_key):
                self.assertIn(concept_key, anchors)
                self.assertEqual("approved", anchors[concept_key]["review_status"])
                self.assertEqual(system, anchors[concept_key]["source_system"])
                self.assertEqual(food_id, anchors[concept_key]["food_id"])

    def test_sr28_proxy_semantic_spot_checks_stay_conceptually_close(self) -> None:
        with REVIEWED_REGISTRIES["sr28_fallbacks"].open(newline="", encoding="utf-8") as handle:
            sr28_fallbacks = {
                row["concept_key"]: row for row in csv.DictReader(handle) if row["review_status"] == "approved"
            }
        with REVIEWED_REGISTRIES["external_catalog"].open(newline="", encoding="utf-8") as handle:
            external_rows = {
                row["concept_key"]: row for row in csv.DictReader(handle) if row["review_status"] == "approved"
            }
        with REVIEWED_REGISTRIES["household_units"].open(newline="", encoding="utf-8") as handle:
            household_rules = {
                (row["concept_key"], normalize_household_unit(row["unit"])): row
                for row in csv.DictReader(handle)
                if row["review_status"] == "approved"
            }

        sr28_expected = {
            "rutabaga|||": "168454",
            "lasagna noodles|||": "169736",
            "halloumi cheese|||": "173420",
            "sazon seasoning|||": "172242",
            "rum|||": "174817",
            "almond flour|||": "170567",
            "cashew flour|||": "170162",
            "steak seasoning|||": "171319",
            "green cardamom|||": "170919",
            "black cardamom|||": "170919",
            "black cardamom pod|||": "170919",
            "orange food coloring|||": "174158",
            "gumbo file|||": "170938",
            "black soy sauce|||": "174277",
            "white flour|||": "168936",
            "active yeast|||": "175043",
            "cabernet sauvignon wine|||": "174833",
            "sliced almonds|||": "170567",
            "coriander sprig|||fresh": "169997",
            "basil sprig|||fresh": "172232",
            "mint sprigs|||": "173475",
            "warm maple syrup|||": "169661",
            "pepper flakes|||": "170932",
            "chocolate covered english toffee bar|||": "168757",
            "texas chili||powder|": "171319",
            "no sugar added applesauce|||": "167772",
            "white frosting||white|": "169620",
            "cinnamon graham cracker||crumb|": "174957",
            "rice|||": "168877",
            "brown rice|||": "169703",
            "brown rice|||raw": "169703",
            "cooked brown rice|||": "169704",
            "arborio rice|||raw": "168879",
            "great northern bean|||": "175192",
            "white bean||white|": "175204",
            "red lentil|||": "174284",
            "baking mix|||": "174902",
            "pork and beans|||": "173733",
            "anchovy fillet|||": "174183",
            "strawberry gelatin|||": "168775",
            "clam juice|||": "171882",
            "plain fat-free yogurt|||": "170894",
            "fresh mozzarella|||": "170845",
            "beef chuck|||": "169491",
            "garbanzo bean|||canned drained rinsed": "173801",
            "ice cream|||": "167575",
            "dried cherry|||": "171708",
            "sultana|||": "168164",
            "raspberry jam|||": "169641",
            "strawberry jam|||": "169641",
            "crisco|||": "173584",
            "nutmeg|||fresh": "171326",
            "brussels sprout|||": "170383",
            "bamboo shoot|||": "169212",
            "sheet puff pastry|||": "172790",
            "semisweet chocolate morsel|||": "167976",
            "devil's food cake mix|||": "174935",
            "mixed nuts|||": "168599",
            "fine sea salt|||": "173468",
            "cake mix|white||": "175054",
            "vanilla wafer|||": "174974",
            "mixed vegetable|||": "170471",
            "lemon gelatin|||": "168775",
            "chuck roast|||": "169491",
            "coarse sea salt|||": "173468",
            "clove||ground|": "171321",
            "orange||slice|": "169097",
            "habanero pepper|||": "170106",
            "flax seed|||": "169414",
            "round steak|||": "171743",
            "pecorino romano cheese|||": "171249",
            "chocolate cake mix|||": "174935",
            "almond milk|||": "174832",
            "imitation crabmeat|||": "174203",
            "mixed spice|||": "171332",
            "mixed herb|||": "171331",
            "maraschino cherry|||drained": "167766",
            "tomato puree|||canned": "170546",
            "chili|green||": "170426",
            "soda water|||": "174842",
            "corn muffin mix|||": "174908",
            "polenta|||": "169697",
            "pumpkin seed|||": "170556",
            "evaporated skim milk|||": "170878",
            "vanilla pudding mix|||": "168784",
            "chocolate hazelnut spread|||": "168000",
            "blackberrie|||": "173946",
            "navel orange|||": "169917",
            "tuna in water|||canned drained": "173709",
            "cilantro|||dried": "170921",
            "pickling salt|||": "173468",
            "linguine|||": "169736",
            "raw shrimp|||": "175179",
            "pepper|green||": "170427",
            "bell pepper|green||": "170427",
            "crusty bread|||": "172675",
            "relish|||": "168561",
            "garbanzo bean|||canned drained": "173800",
            "brown rice flour|||": "168898",
            "potato||diced|": "170026",
            "pineapple in juice|||": "169126",
            "ranch salad dressing|||": "173592",
            "tuna|||drained": "173709",
            "jasmine rice|||raw": "168877",
            "instant lemon pudding mix|||": "169654",
            "orange gelatin|||": "168775",
            "farfalle|||": "169736",
            "clarified butter|||": "171314",
            "chicken liver|||": "171060",
            "smoked gouda cheese|||": "171241",
            "tasty cheese|||": "173414",
            "sheets puff pastry|||": "172790",
            "onion|green||": "170006",
            "lime gelatin|||": "168775",
            "tomato||juice|canned": "170458",
            "coarse kosher salt|||": "173468",
            "almond butter|||": "168588",
            "apple pie spice|||": "171332",
            "raspberry gelatin|||": "168775",
            "vanilla frosting|||": "169620",
            "water chestnut|||drained": "170067",
            "light brown sugar|||": "168833",
            "celtic sea salt|||": "173468",
            "lamb shoulder|||": "172496",
            "broccoli rabe|||": "170381",
            "soy milk|||": "172456",
            "oleo|||": "171040",
            "whipping cream|||": "170859",
            "celeriac|||": "170400",
            "savoy cabbage|||": "170388",
            "jellied cranberry sauce|||": "167804",
            "cranberry||sauce|": "173961",
            "fine salt|||": "173468",
            "bacon fat|||": "168324",
            "cheese whiz|||": "172209",
            "bulk italian sausage|||": "171631",
            "portabella mushroom cap|||": "169255",
            "ranch style bean|||": "169065",
            "cheerios toasted oat cereal|||": "173884",
            "chocolate wafer||crumb|": "172714",
            "lobster meat|||": "174209",
            "instant chicken bouillon||granule|": "171562",
            "minced garlic|||": "169230",
            "sweet and sour sauce|||": "174066",
            "liquid pectin|||": "167682",
            "salmon steak|||": "173686",
            "pitted green olive|green||": "169096",
            "beef stock|||": "172883",
            "pecorino cheese|||": "171249",
            "spanish paprika|||": "171329",
            "sandwich bread|||": "174924",
            "lime||slice|": "168155",
            "genoa salami|||": "174603",
            "coconut||flakes|": "170577",
            "english cucumber|||": "168409",
            "coarse sugar|||": "169655",
            "fusilli|||": "169736",
            "condensed mushroom soup|||": "171155",
            "french baguette|||": "172675",
            "semolina flour|||": "169715",
            "boneless skinless chicken breast half|||": "171077",
            "cannellini bean|||drained": "175204",
            "chopped spinach|||": "169287",
            "cornish hen|||": "171507",
            "custard||powder|": "168772",
            "chili|red||": "170106",
            "french onion soup|||canned": "171551",
            "pepper|red||": "170108",
            "lamb chop|||": "174321",
            "chili beans|||": "169065",
            "streaky bacon|||": "168277",
            "frying chicken|||": "171447",
            "rump roast|||": "169523",
            "zesty italian dressing|||": "171019",
            "seasoned crouton|||": "172752",
            "mushroom piece|||": "169254",
            "spiral shaped pasta|||": "169736",
            "cranberry sauce|||": "173961",
            "chicken breast|||raw": "171077",
            "sushi rice|||": "168881",
            "pork rib|||": "167853",
            "flounder fillet|||": "174196",
            "yellow split pea|||": "172428",
            "corn niblet|||": "169214",
            "tuna in water|||": "173709",
            "crumbled bacon|||": "167914",
            "sesame seed oil|||": "171016",
            "bacon grease|||": "168324",
            "asian fish sauce|||": "174531",
            "vanilla wafers|||": "174974",
            "chocolate milk|||": "170879",
            "tempeh|||": "174272",
            "head broccoli|||": "170379",
            "thai chile|||": "170497",
            "chili pepper|red||": "170106",
            "potato|white||": "170028",
            "shelled pistachio|||": "170184",
            "hash browns|||": "170043",
            "japanese eggplant|||": "169228",
            "condensed chicken broth|||": "171542",
            "quick oatmeal|||": "172989",
            "herb stuffing mix|||": "174930",
            "cornbread stuffing mix|||": "172692",
            "french onion soup mix|||": "171165",
            "belgian endive|||": "168412",
            "tartar sauce|||": "171826",
            "horseradish sauce|||": "171833",
            "sour cherry|||": "173954",
            "asparagus spear|||": "168389",
            "baby spinach leaf|||fresh": "168462",
            "phyllo pastry sheet|||": "172791",
            "red hot pepper sauce|||": "174527",
            "pimento stuffed green olive|green||": "169096",
            "stuffed olive|||": "169096",
            "sweet basil|||": "172232",
            "large green bell peppers|medium||": "170427",
            "tomato||slice|": "170457",
            "splenda granular sugar substitute|||": "170257",
            "double crust pie pastry|||": "172814",
            "strips bacon|||": "168277",
            "hot italian sausage|||": "171631",
            "peach||slice|": "169928",
            "garbanzo bean|||dried": "173756",
            "chili with bean|||": "175207",
            "ditalini pasta|||": "169736",
            "canning salt|||": "173468",
            "original ranch dressing|||": "173592",
            "chia seed|||": "170554",
            "tamari|||": "174278",
            "lukewarm milk|||": "171265",
            "oriental sesame oil|||": "171016",
            "flax seed oil|||": "167702",
            "risotto rice|||": "168881",
            "chocolate wafer|||": "172714",
            "chocolate wafer cooky|||": "172714",
            "gala apple|||": "168204",
            "eyed pea|black||": "173758",
            "vegetable||juice|": "170063",
            "mung bean sprout|||": "169957",
            "lemon twist|||": "167749",
            "head of cabbage|||": "169975",
            "haddock fillet|||": "171964",
            "pepper|black||": "170931",
            "garlic clove|||fresh": "169230",
            "corkscrew macaroni|||": "169736",
            "macaroni noodle|||": "169736",
            "beef bouillon||powder|": "171560",
            "raspberry gelatin||powder|": "168775",
            "tomato|||fresh": "170457",
            "butter lettuce||butter|": "168429",
            "wild mushroom|||": "169251",
            "coarse ground black pepper|black||fresh": "170931",
            "chili without bean|||": "172098",
            "chocolate ice cream|||": "168809",
            "black walnut|||": "170186",
            "white sesame seed||white|": "170150",
            "caviar|||": "174188",
            "cauliflower floret|||": "169986",
            "skim milk|||": "171269",
            "baby lima bean|||": "168396",
            "sweetened flaked coconut|||": "170577",
            "wax bean|||": "169320",
            "halibut steak|||": "174200",
            "graham cracker square|||": "174957",
            "double crust pie crust|||": "172814",
            "vanilla wafer cooky|||": "174974",
            "french mustard|||": "172234",
            "chili|red||dried": "170932",
            "bean sprout|||canned drained": "170079",
            "strawberry jelly|||": "169641",
            "chili bean|||canned drained": "175207",
            "no added salt tomato paste|||": "170459",
            "mahi mahi fillet|||": "171959",
            "chocolate|semi-sweet||": "167976",
            "phyllo pastry|||": "172791",
            "boneless skinless chicken thigh|||": "173627",
            "bleu cheese salad dressing||cheese|": "173562",
            "wonton skin|||": "172802",
            "venison||ground|": "172602",
            "parmigiano cheese|||": "170848",
            "delicious apple|golden||": "168202",
            "orange section|||": "169097",
            "dehydrated onion|||": "170002",
            "brewed espresso|||": "171891",
            "bell pepper|yellow||": "169383",
            "tomato|green||": "170456",
            "romano cheese|||fresh": "171249",
            "french fry|||": "168442",
            "tuna in vegetable oil|||": "173708",
            "pork baby back rib|||": "168299",
            "cavatappi pasta|||": "169736",
            "truffle oil|||": "171413",
            "shell macaroni|||": "169736",
            "fine sugar|||": "169655",
            "water chestnut|||canned": "170067",
            "vegetable bouillon||granule|": "171613",
            "cream of onion soup|||": "171552",
            "tri color spiral pasta|||": "169736",
            "mcintosh apple|||": "171688",
            "peppermint candy|||": "167990",
            "russian salad dressing|||": "171005",
            "star fruit|||": "171715",
            "brown lentil|||": "172420",
            "string bean|||": "169961",
            "pork shoulder roast|||": "167843",
            "cannellini beans|||": "175204",
            "wheat berry|||": "168890",
            "tonic water|||": "171869",
            "rotini pasta|||": "169736",
            "porridge oat|||": "173904",
            "mushroom cap|||": "169251",
            "straw mushroom|||": "168582",
            "pork steak|||": "167849",
            "top sirloin steak|||": "168726",
            "self raising flour|||": "168895",
            "full fat milk|||": "171265",
            "white raisin||white|": "168164",
            "sweet pea|||": "170419",
            "fleur de sel|||": "173468",
            "creamy caesar salad dressing|||": "169055",
            "mango juice|||": "167785",
            "pecan nut|||": "170182",
            "fast rising active dry yeast|||": "175043",
            "candied red cherry|red||": "167766",
            "tomato|sun-dried||drained": "169384",
            "tomato|sun-dried||": "168567",
            "summer savory|||": "170936",
            "grape leaf|||": "169393",
            "soy margarine|||": "171018",
            "shortbread|||": "174967",
            "vegemite|||": "167717",
            "pitted cherry|||": "171719",
            "sultana raisin|||": "168164",
            "garbanzo bean|||": "173800",
            "creamed horseradish|||": "171833",
            "pepper sauce|||": "174527",
            "firm tomato|||": "170457",
            "white truffle oil|||": "171413",
            "shoyu|||": "174277",
            "plum jam|||": "169641",
            "mineral water|||": "174827",
            "water chestnut|||drained canned": "170067",
            "ripe pear|||": "169118",
            "tuna in water|||drained": "173709",
            "orecchiette pasta|||": "169736",
            "london broil beef|||": "171743",
            "liquid fruit pectin|||": "167682",
            "israeli couscou|||": "169699",
            "pappardelle pasta|||": "169736",
            "canola oil cooking spray||oil|": "171430",
            "brown onions|medium||": "170000",
            "broad egg noodle|||": "169731",
            "nutmeg||ground|": "171326",
            "head green cabbage|||": "169975",
            "top round steak|||": "171743",
            "chicken leg quarter|||": "172378",
            "sriracha hot chili sauce|hot||": "171186",
            "red miso|||": "172442",
            "horseradish cream|||": "171833",
            "vegetarian worcestershire sauce|||": "171610",
            "fine grain sea salt|||": "173468",
            "crisco cooking oil|||": "172370",
            "chunky applesauce|||": "171696",
            "apple|green||": "168203",
            "soft cream cheese|||": "173418",
            "turkey breast tenderloin|||": "174515",
            "ladyfinger|||": "172821",
            "graham cracker crust|reduced-fat||": "167520",
            "gluten free soy sauce|||": "174277",
            "sambal oelek chili paste|||": "171186",
            "vinaigrette dressing|||": "171019",
            "curry leaf|||fresh": "172232",
        }
        external_expected = {
            "cashew piece|||": "170162",
            "whole cashew|||": "170162",
            "toasted cashew|||": "170571",
            "salted cashew halve|||": "169421",
            "gluten free flour blend|||": "169714",
            "sifted all purpose flour|||": "168936",
            "white corn meal||white|": "169750",
            "green beans|||": "169961",
            "coffee liqueur|||": "173665",
            "madeira|||": "173176",
        }
        household_expected = {
            ("almond flour|||", "cup"): "95",
            ("cashew flour|||", "cup"): "95",
            ("cashew piece|||", "cup"): "137",
            ("gluten free flour blend|||", "cup"): "158",
            ("white corn meal||white|", "cup"): "122",
        }

        for concept_key, expected_id in sr28_expected.items():
            with self.subTest(concept_key=concept_key, source="sr28_fallback"):
                self.assertEqual(expected_id, sr28_fallbacks[concept_key]["fdc_id"])
        for concept_key, expected_id in external_expected.items():
            with self.subTest(concept_key=concept_key, source="external_catalog"):
                self.assertEqual(expected_id, external_rows[concept_key]["fdc_id"])
        for key, expected_grams in household_expected.items():
            with self.subTest(concept_key=key[0], unit=key[1]):
                self.assertEqual(expected_grams, household_rules[key]["grams_per_unit"])

    def test_reviewed_nutrition_anchors_do_not_approve_known_bad_codes(self) -> None:
        bad_ids = {
            "51113010",  # cinnamon bread
            "53223000",  # gingersnaps
            "52407000",  # zucchini bread
            "53341500",  # buttermilk pie
            "91713070",  # vanilla fudge
            "170705",  # Subway sweet onion sandwich
            "174924",  # white bread
            "53100050",  # chocolate cake batter
        }
        path = REVIEWED_REGISTRIES["nutrition_anchors"]
        failures = []
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["review_status"] == "approved" and row["food_id"] in bad_ids:
                    failures.append((row["concept_key"], row["food_id"], row["description"]))
        self.assertEqual([], failures)

    def test_recipe_nutrition_audit_loads_reviewed_sr28_anchors(self) -> None:
        anchors = load_reviewed_nutrition_anchors(REVIEWED_REGISTRIES["nutrition_anchors"])
        self.assertEqual("171320", anchors["cinnamon|||"]["fdc_id"])
        self.assertEqual("170926", anchors["ginger||ground|"]["fdc_id"])
        self.assertEqual("169291", anchors["zucchini|||"]["fdc_id"])
        self.assertEqual("174528", anchors["tabasco sauce|||"]["fdc_id"])
        self.assertEqual("175142", anchors["sea bass fillet|||"]["fdc_id"])
        self.assertEqual("168157", anchors["key lime juice|||"]["fdc_id"])
        self.assertEqual("169374", anchors["cut wax bean|||"]["fdc_id"])
        self.assertEqual("170027", anchors["large baking potatoes|||"]["fdc_id"])
        self.assertEqual("170577", anchors["baker's angel flake coconut|||"]["fdc_id"])
        self.assertEqual("172232", anchors["loosely packed basil leaf|||"]["fdc_id"])
        self.assertEqual("167520", anchors["graham cracker pie crusts|||"]["fdc_id"])
        self.assertEqual("174928", anchors["coarse dry breadcrumb|||"]["fdc_id"])
        self.assertEqual("168462", anchors["packed baby spinach|||"]["fdc_id"])
        self.assertEqual("169709", anchors["minute white rice|white|white|"]["fdc_id"])
        self.assertEqual("169998", anchors["ears corn|||"]["fdc_id"])
        self.assertEqual("169998", anchors["ears corn on the cob|||"]["fdc_id"])
        self.assertEqual("173911", anchors["shreddies cereal|||"]["fdc_id"])
        self.assertEqual("171613", anchors["instant bouillon||granule|"]["fdc_id"])
        self.assertEqual("168396", anchors["lima bean|||fresh"]["fdc_id"])
        self.assertEqual("171009", anchors["whole egg mayonnaise|||"]["fdc_id"])
        self.assertEqual("172796", anchors["buns|||"]["fdc_id"])
        self.assertEqual("169671", anchors["almond brickle chips|||"]["fdc_id"])
        self.assertEqual("170918", anchors["carom seed|||"]["fdc_id"])
        self.assertEqual("168462", anchors["baby spinach|||"]["fdc_id"])
        self.assertEqual("174974", anchors["vanilla wafer|||"]["fdc_id"])
        self.assertNotIn("chocolate|||", anchors)
        self.assertIn("buttermilk|||", anchors)
        self.assertEqual("172225", anchors["buttermilk|||"]["fdc_id"])

    def test_live_quantity_policy_rows_cover_current_top_blockers(self) -> None:
        conn = sqlite3.connect(":memory:")
        policies = populate_quantity_policies(conn, REVIEWED_REGISTRIES["quantity_policies"])
        conn.close()
        by_id = {str(row["policy_id"]): row for row in policies}
        expected_defaults = {
            "codex_b50_shortening_frying_missing_001": 15.0,
            "codex_by_ramen_noodles_seasoning_packet_default_20260416": 2.0,
            "codex_by_lemon_lime_soda_splash_default_20260416": 30.0,
            "codex_by_chili_oil_to_taste_default_20260416": 4.5,
            "codex_by_orange_food_coloring_bare_default_20260416": 0.5,
            "codex_by_icing_sugar_to_taste_default_20260416": 4.0,
            "codex_by_pizza_dough_12_inch_default_20260416": 225.0,
            "codex_ca_milk_tablespoon_if_needed_default_20260416": 15.0,
            "codex_ca_milk_tablespoon_if_needed_grams_default_20260416": 15.0,
            "codex_ca_cooked_rice_serving_default_20260416": 158.0,
        }
        for policy_id, grams in expected_defaults.items():
            self.assertEqual("apply_default", by_id[policy_id]["action"])
            self.assertAlmostEqual(grams, float(by_id[policy_id]["default_grams"]))

    def test_recipe_nutrition_audit_loads_reviewed_fndds_anchors(self) -> None:
        nutrient_csv = PROJECT_ROOT / "data" / "fndds" / "fndds_nutrient_lookup.csv"
        nutrients = load_fndds_nutrients(nutrient_csv)
        self.assertEqual(347.0, nutrients["62120100"]["calories"])
        rows = load_reviewed_fndds_nutrition_rows(REVIEWED_REGISTRIES["nutrition_anchors"])
        dried_pineapple = rows["dried pineapple|||"]
        self.assertEqual("nutrition_ready_fndds_anchor", dried_pineapple["nutrition_status"])
        self.assertEqual("FNDDS:62120100", dried_pineapple["sr28_fdc_id"])
        self.assertAlmostEqual(3.47, dried_pineapple["calories_per_g"])
        self.assertAlmostEqual(0.7712, dried_pineapple["sugar_g_per_g"])
        self.assertEqual("nutrition_ready_fndds_anchor", rows["round angel food cake|||"]["nutrition_status"])
        self.assertEqual("FNDDS:53101100", rows["round angel food cake|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_fndds_anchor", rows["mixed grain hamburger bun|||"]["nutrition_status"])
        self.assertEqual("FNDDS:51620030", rows["mixed grain hamburger bun|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_fndds_anchor", rows["lyle's golden syrup|||"]["nutrition_status"])
        self.assertEqual("FNDDS:91301030", rows["lyle's golden syrup|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_fndds_anchor", rows["sweet biscuits|||"]["nutrition_status"])
        self.assertEqual("FNDDS:53241510", rows["sweet biscuits|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_fndds_anchor", rows["peppermint schnapp|||"]["nutrition_status"])
        self.assertEqual("FNDDS:93201000", rows["peppermint schnapp|||"]["sr28_fdc_id"])

    def test_recipe_nutrition_audit_loads_reviewed_branded_fdc_proxy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            products_db = temp / "products.db"
            conn = sqlite3.connect(products_db)
            conn.execute(
                """
                CREATE TABLE products (
                    fdc_id TEXT,
                    gtin_upc TEXT,
                    description TEXT,
                    brand_owner TEXT,
                    branded_food_category TEXT,
                    serving_size REAL,
                    serving_size_unit TEXT,
                    calories REAL,
                    protein_g REAL,
                    fat_g REAL,
                    carbs_g REAL,
                    fiber_g REAL,
                    sugar_g REAL,
                    sodium_mg REAL
                )
                """
            )
            conn.execute(
                """
                INSERT INTO products VALUES (
                    '2596456',
                    '0041449450148',
                    'GLUTEN FREE ALL PURPOSE FLOUR',
                    'Continental Mills, Inc.',
                    'Flours & Corn Meal',
                    30,
                    'GRM',
                    367,
                    6.67,
                    3.33,
                    76.67,
                    3.3,
                    0,
                    17
                )
                """
            )
            conn.execute(
                """
                INSERT INTO products VALUES (
                    '2482931',
                    '075450268799',
                    'GLUTEN FREE ALL PURPOSE FLOUR',
                    'Hy-Vee, Inc.',
                    'Flours & Corn Meal',
                    34,
                    'g',
                    529,
                    11.76,
                    0,
                    114.71,
                    5.9,
                    NULL,
                    132
                )
                """
            )
            conn.commit()
            conn.close()

            anchors_csv = temp / "anchors.csv"
            anchors_csv.write_text(
                "\n".join(
                    [
                        "concept_key,source_system,food_id,description,food_family,form,state,allowed_description_tokens,forbidden_description_tokens,review_status,notes",
                        "gluten free all-purpose flour|||,BRANDED_FDC,2596456,GLUTEN FREE ALL PURPOSE FLOUR,flour,gluten_free_blend,dry,gluten free;flour,cake mix;pancake mix,approved,test",
                        "bad gluten free flour|||,BRANDED_FDC,2482931,GLUTEN FREE ALL PURPOSE FLOUR,flour,gluten_free_blend,dry,gluten free;flour,,approved,macros exceed 100g",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            rows = load_reviewed_branded_nutrition_rows(anchors_csv, products_db=products_db)

        self.assertIn("gluten free all-purpose flour|||", rows)
        self.assertNotIn("bad gluten free flour|||", rows)
        flour = rows["gluten free all-purpose flour|||"]
        self.assertEqual("nutrition_ready_branded_fdc_proxy", flour["nutrition_status"])
        self.assertEqual("branded_fdc_nutrition_proxy", flour["policy"])
        self.assertEqual("BRANDED_FDC:2596456", flour["sr28_fdc_id"])
        self.assertEqual("0041449450148", flour["gtin_upc"])
        self.assertAlmostEqual(3.67, float(flour["calories_per_g"]))
        self.assertAlmostEqual(0.7667, float(flour["carbs_g_per_g"]))

    def test_live_branded_fdc_proxy_rows_load_from_master_products(self) -> None:
        rows = load_reviewed_branded_nutrition_rows(
            REVIEWED_REGISTRIES["nutrition_anchors"],
            products_db=DEFAULT_ARTIFACTS.master_products_db,
        )
        self.assertEqual(
            "nutrition_ready_branded_fdc_proxy",
            rows["gluten free all-purpose flour|||"]["nutrition_status"],
        )
        self.assertEqual("BRANDED_FDC:2596456", rows["gluten free all-purpose flour|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["salt substitute||salt|"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2573388", rows["salt substitute||salt|"]["sr28_fdc_id"])
        self.assertAlmostEqual(0.0, float(rows["salt substitute||salt|"]["calories_per_g"]))
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["all-purpose gluten free flour|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2596456", rows["all-purpose gluten free flour|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["all-purpose greek seasoning|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2023505", rows["all-purpose greek seasoning|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["red pepper jelly|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2288577", rows["red pepper jelly|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["candied pecan|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2151920", rows["candied pecan|||"]["sr28_fdc_id"])
        self.assertEqual(
            "nutrition_ready_branded_fdc_proxy",
            rows["reese's peanut butter chip||butter|"]["nutrition_status"],
        )
        self.assertEqual("BRANDED_FDC:1898078", rows["reese's peanut butter chip||butter|"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["hawaiian bread|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2139986", rows["hawaiian bread|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["nacho cheese soup|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2651087", rows["nacho cheese soup|||"]["sr28_fdc_id"])
        self.assertEqual("branded_fdc_per_100ml_density_bridge", rows["nacho cheese soup|||"]["nutrition_basis"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["strawberries|||dried"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2400347", rows["strawberries|||dried"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["piri-piri sauce|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:1865521", rows["piri-piri sauce|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["banana pepper rings|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2023084", rows["banana pepper rings|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["xanthan gum|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2022912", rows["xanthan gum|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["crescent roll|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:1578054", rows["crescent roll|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["whole grain mustard|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:1896423", rows["whole grain mustard|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["spicy brown mustard|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:1467257", rows["spicy brown mustard|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["taco sauce|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:1791360", rows["taco sauce|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["rice krispies|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:1595079", rows["rice krispies|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["cheddar cheese soup|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2649320", rows["cheddar cheese soup|||"]["sr28_fdc_id"])
        self.assertEqual("branded_fdc_per_100ml_density_bridge", rows["cheddar cheese soup|||"]["nutrition_basis"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["mango chutney|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2669818", rows["mango chutney|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["adobo sauce|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:1904475", rows["adobo sauce|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["potato starch|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2009676", rows["potato starch|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["chili sauce|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2021903", rows["chili sauce|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["peanut butter chip|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2009370", rows["peanut butter chip|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["curry paste|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:1871019", rows["curry paste|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["simple syrup|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2164536", rows["simple syrup|||"]["sr28_fdc_id"])
        self.assertEqual("branded_fdc_per_100ml_density_bridge", rows["simple syrup|||"]["nutrition_basis"])
        self.assertAlmostEqual(1.30, float(rows["simple syrup|||"]["density_g_per_ml"]))
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["espresso powder|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2059824", rows["espresso powder|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["coarse grain mustard|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:1896423", rows["coarse grain mustard|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["chili oil|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2083143", rows["chili oil|||"]["sr28_fdc_id"])
        self.assertEqual("branded_fdc_per_100ml_density_bridge", rows["chili oil|||"]["nutrition_basis"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["accent seasoning|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:1849860", rows["accent seasoning|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["lawry's seasoned salt|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:1506618", rows["lawry's seasoned salt|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["chow mein noodle|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2164608", rows["chow mein noodle|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["sriracha|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2020566", rows["sriracha|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["tapioca flour|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2424708", rows["tapioca flour|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["tapioca starch|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2420676", rows["tapioca starch|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["ginger paste|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2024762", rows["ginger paste|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["vanilla sugar|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2530600", rows["vanilla sugar|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["anchovy paste|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2286099", rows["anchovy paste|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["raspberry vinegar|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:1973104", rows["raspberry vinegar|||"]["sr28_fdc_id"])
        self.assertEqual("branded_fdc_per_100ml_density_bridge", rows["raspberry vinegar|||"]["nutrition_basis"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["almond meal|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2446259", rows["almond meal|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["cream of potato soup|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2650905", rows["cream of potato soup|||"]["sr28_fdc_id"])
        self.assertEqual("branded_fdc_per_100ml_density_bridge", rows["cream of potato soup|||"]["nutrition_basis"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["seasoned rice vinegar|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2084989", rows["seasoned rice vinegar|||"]["sr28_fdc_id"])
        self.assertEqual("branded_fdc_per_100ml_density_bridge", rows["seasoned rice vinegar|||"]["nutrition_basis"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["rice krispies cereal|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:1595079", rows["rice krispies cereal|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["palm sugar|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2624471", rows["palm sugar|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["apple butter|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2008488", rows["apple butter|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["french-fried onion|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2410774", rows["french-fried onion|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["apple pie filling|||canned"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2008226", rows["apple pie filling|||canned"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["chili-garlic||sauce|"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2339281", rows["chili-garlic||sauce|"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["sweetened whipped cream|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2118678", rows["sweetened whipped cream|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["seedless raspberry jam|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2127300", rows["seedless raspberry jam|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["malt vinegar|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2268217", rows["malt vinegar|||"]["sr28_fdc_id"])
        self.assertEqual("branded_fdc_per_100ml_density_bridge", rows["malt vinegar|||"]["nutrition_basis"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["tamarind paste|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2174116", rows["tamarind paste|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["ginger-garlic||paste|"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2164342", rows["ginger-garlic||paste|"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["spelt flour|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2015846", rows["spelt flour|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["red currant jelly|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:1551309", rows["red currant jelly|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["sambal|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2016176", rows["sambal|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["msg|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2269416", rows["msg|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["green enchilada sauce|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2367891", rows["green enchilada sauce|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["champagne vinegar|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2081694", rows["champagne vinegar|||"]["sr28_fdc_id"])
        self.assertEqual("branded_fdc_per_100ml_density_bridge", rows["champagne vinegar|||"]["nutrition_basis"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["garlic pepper seasoning|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2016923", rows["garlic pepper seasoning|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["lemon curd|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:1458179", rows["lemon curd|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["havarti cheese|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2469575", rows["havarti cheese|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["apple jelly|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:1547758", rows["apple jelly|||"]["sr28_fdc_id"])
        batch_ch_expected = {
            "condensed cheddar cheese soup|||": ("BRANDED_FDC:2649320", "branded_fdc_per_100ml_density_bridge"),
            "condensed golden mushroom soup|||": ("BRANDED_FDC:2650912", "branded_fdc_per_100ml_density_bridge"),
            "french style green bean|green||": ("BRANDED_FDC:2658705", None),
            "cut green bean|green||": ("BRANDED_FDC:1467403", None),
            "candy sprinkle|||": ("BRANDED_FDC:1970828", None),
            "yoghurt|||": ("BRANDED_FDC:2399552", None),
            "condensed milk|||": ("BRANDED_FDC:2470464", None),
            "vegetable stock|||": ("BRANDED_FDC:1884745", None),
            "chicken base|||": ("BRANDED_FDC:2447237", None),
            "balsamic vinaigrette|||": ("BRANDED_FDC:2679711", None),
            "caramel||sauce|": ("BRANDED_FDC:2440285", None),
            "grape jelly|||": ("BRANDED_FDC:2185598", None),
            "instant pistachio pudding mix|||": ("BRANDED_FDC:2031542", None),
            "mexicorn|||": ("BRANDED_FDC:1630116", None),
            "pickling spice|||": ("BRANDED_FDC:2027556", None),
            "pomegranate seed|||": ("BRANDED_FDC:2678141", None),
            "coconut flour|||": ("BRANDED_FDC:2339682", None),
            "dark chocolate chip|||": ("BRANDED_FDC:2122435", None),
            "french-fried onion|||canned": ("BRANDED_FDC:2410774", None),
            "season salt|||": ("BRANDED_FDC:2658103", None),
            "ciabatta|||": ("BRANDED_FDC:2585877", None),
            "steel cut oat|||": ("BRANDED_FDC:2033575", None),
        }
        for concept_key, (fdc_id, nutrition_basis) in batch_ch_expected.items():
            with self.subTest(concept_key=concept_key, source="branded_fdc_batch_ch"):
                self.assertEqual("nutrition_ready_branded_fdc_proxy", rows[concept_key]["nutrition_status"])
                self.assertEqual(fdc_id, rows[concept_key]["sr28_fdc_id"])
                if nutrition_basis is not None:
                    self.assertEqual(nutrition_basis, rows[concept_key]["nutrition_basis"])
        batch_ci_expected = {
            "pico de gallo|||": "BRANDED_FDC:2146158",
            "stew meat|||": "BRANDED_FDC:1458886",
            "spice cake mix|||": "BRANDED_FDC:758582",
            "catalina dressing|||": "BRANDED_FDC:2297055",
            "karo syrup|||": "BRANDED_FDC:1457287",
            "lemon cake mix|||": "BRANDED_FDC:2482416",
            "fajita seasoning mix|||": "BRANDED_FDC:2024332",
            "harissa|||": "BRANDED_FDC:2546030",
            "german chocolate cake mix|||": "BRANDED_FDC:1897728",
            "plum sauce|||": "BRANDED_FDC:2019661",
            "black bean sauce|||": "BRANDED_FDC:2296989",
            "beef base|||": "BRANDED_FDC:2679605",
            "angel food cake mix|||": "BRANDED_FDC:2545546",
            "chili bean|||canned undrained": "BRANDED_FDC:2400365",
        }
        for concept_key, fdc_id in batch_ci_expected.items():
            with self.subTest(concept_key=concept_key, source="branded_fdc_batch_ci"):
                self.assertEqual("nutrition_ready_branded_fdc_proxy", rows[concept_key]["nutrition_status"])
                self.assertEqual(fdc_id, rows[concept_key]["sr28_fdc_id"])
        batch_cj_expected = {
            "chipotle hot sauce|hot||": "BRANDED_FDC:2148694",
            "almond flavoring|||": "BRANDED_FDC:2124896",
            "picante sauce|||": "BRANDED_FDC:1379298",
            "coffee ice cream|||": "BRANDED_FDC:2106496",
            "green curry paste|||": "BRANDED_FDC:2440966",
            "green chili salsa|||": "BRANDED_FDC:2622409",
            "vegan mayonnaise|||": "BRANDED_FDC:2026678",
            "stone ground mustard|||": "BRANDED_FDC:2579144",
            "buffalo wing sauce|||": "BRANDED_FDC:2387773",
            "rice chex|||": "BRANDED_FDC:2746519",
            "pomegranate molasses|||": "BRANDED_FDC:1862942",
            "dill pickle relish|||": "BRANDED_FDC:2029604",
            "jarlsberg cheese|||": "BRANDED_FDC:360389",
            "honey peanut|||": "BRANDED_FDC:2443001",
            "fudge sauce|||": "BRANDED_FDC:1502094",
            "kitchen bouquet|||": "BRANDED_FDC:500150",
            "english mustard|||": "BRANDED_FDC:2285459",
            "fritos corn chip|||": "BRANDED_FDC:1458768",
        }
        for concept_key, fdc_id in batch_cj_expected.items():
            with self.subTest(concept_key=concept_key, source="branded_fdc_batch_cj"):
                self.assertEqual("nutrition_ready_branded_fdc_proxy", rows[concept_key]["nutrition_status"])
                self.assertEqual(fdc_id, rows[concept_key]["sr28_fdc_id"])
        batch_ck_expected = {
            "herb seasoning|||": "BRANDED_FDC:2010528",
            "italian herb seasoning|||": "BRANDED_FDC:1868447",
            "stilton cheese|||": "BRANDED_FDC:2402181",
            "espresso||powder|": "BRANDED_FDC:2059824",
            "seafood seasoning|||": "BRANDED_FDC:2034680",
            "salsa||thick & chunky|": "BRANDED_FDC:2400827",
            "crumbled gorgonzola cheese|||": "BRANDED_FDC:2385923",
            "grill seasoning|||": "BRANDED_FDC:2154732",
            "browning sauce|||": "BRANDED_FDC:2039703",
            "minute tapioca|||": "BRANDED_FDC:2565981",
            "greek seasoning|||": "BRANDED_FDC:2023505",
            "chili bean|||canned": "BRANDED_FDC:2400365",
        }
        for concept_key, fdc_id in batch_ck_expected.items():
            with self.subTest(concept_key=concept_key, source="branded_fdc_batch_ck"):
                self.assertEqual("nutrition_ready_branded_fdc_proxy", rows[concept_key]["nutrition_status"])
                self.assertEqual(fdc_id, rows[concept_key]["sr28_fdc_id"])
        batch_cl_expected = {
            "seasoned pepper|||": "BRANDED_FDC:2034841",
            "heath candy bar|||": "BRANDED_FDC:1952934",
            "corn chex|||": "BRANDED_FDC:2746529",
            "cream of broccoli soup|||": "BRANDED_FDC:2633008",
            "sofrito sauce|||": "BRANDED_FDC:2079665",
            "pineapple preserve|||": "BRANDED_FDC:2442851",
            "oyster cracker|||": "BRANDED_FDC:2054439",
            "currant jelly|||": "BRANDED_FDC:2442854",
            "asian chili sauce|||": "BRANDED_FDC:2025737",
            "butter recipe cake mix||butter|": "BRANDED_FDC:2251412",
            "digestive biscuit|||": "BRANDED_FDC:1568362",
            "red chili paste|||": "BRANDED_FDC:2035063",
            "almond essence|||": "BRANDED_FDC:2124896",
            "peach pie filling|||": "BRANDED_FDC:1856279",
            "chicken soup base||soup|": "BRANDED_FDC:2447237",
            "shrimp||paste|": "BRANDED_FDC:391912",
        }
        for concept_key, fdc_id in batch_cl_expected.items():
            with self.subTest(concept_key=concept_key, source="branded_fdc_batch_cl"):
                self.assertEqual("nutrition_ready_branded_fdc_proxy", rows[concept_key]["nutrition_status"])
                self.assertEqual(fdc_id, rows[concept_key]["sr28_fdc_id"])
        batch_cm_expected = {
            "orange roughy fillet|||": "BRANDED_FDC:2444987",
            "wondra flour|||": "BRANDED_FDC:2235440",
            "beau monde seasoning|||": "BRANDED_FDC:2675800",
            "loaf frozen bread dough|||": "BRANDED_FDC:1851457",
            "passion fruit pulp|||": "BRANDED_FDC:2499805",
            "non dairy coffee creamer|||": "BRANDED_FDC:2404457",
            "caribbean jerk seasoning|||": "BRANDED_FDC:360644",
            "strawberry syrup|||": "BRANDED_FDC:2320332",
            "caramel syrup|||": "BRANDED_FDC:2064799",
            "butterfinger candy bar|||": "BRANDED_FDC:691042",
        }
        for concept_key, fdc_id in batch_cm_expected.items():
            with self.subTest(concept_key=concept_key, source="branded_fdc_batch_cm"):
                self.assertEqual("nutrition_ready_branded_fdc_proxy", rows[concept_key]["nutrition_status"])
                self.assertEqual(fdc_id, rows[concept_key]["sr28_fdc_id"])
        batch_cn_expected = {
            "black forest ham|||": "BRANDED_FDC:2403314",
            "dill relish|||": "BRANDED_FDC:2541457",
            "chocolate graham cracker||crumb|": "BRANDED_FDC:2632308",
            "cream of chicken soup|reduced-fat||": "BRANDED_FDC:2468627",
            "broccoli coleslaw mix|||": "BRANDED_FDC:2377766",
            "udon noodle|||": "BRANDED_FDC:2622953",
            "popcorn kernel|||": "BRANDED_FDC:2500155",
            "english toffee bit|||": "BRANDED_FDC:2658069",
            "cornichon|||": "BRANDED_FDC:1854601",
            "margarita mix|||": "BRANDED_FDC:2144272",
            "blackening seasoning|||": "BRANDED_FDC:2061052",
            "green tea bag|||": "BRANDED_FDC:2023935",
            "seasoned rice wine vinegar|||": "BRANDED_FDC:2084989",
            "ciabatta roll|||": "BRANDED_FDC:2633059",
            "brioche bread|||": "BRANDED_FDC:2462657",
        }
        for concept_key, fdc_id in batch_cn_expected.items():
            with self.subTest(concept_key=concept_key, source="branded_fdc_batch_cn"):
                self.assertEqual("nutrition_ready_branded_fdc_proxy", rows[concept_key]["nutrition_status"])
                self.assertEqual(fdc_id, rows[concept_key]["sr28_fdc_id"])
        batch_co_expected = {
            "four cheese mexican blend cheese|||": "BRANDED_FDC:1419634",
            "meat tenderizer|||": "BRANDED_FDC:2034771",
            "texas toast thick bread|||": "BRANDED_FDC:2572922",
            "non dairy powdered coffee creamer|||": "BRANDED_FDC:2702956",
            "rye cocktail bread|||": "BRANDED_FDC:1855188",
            "pizza seasoning|||": "BRANDED_FDC:2327062",
            "sloppy joe sandwich sauce|||": "BRANDED_FDC:2024104",
            "preserved lemon|||": "BRANDED_FDC:2076581",
            "marzipan|||": "BRANDED_FDC:2680156",
            "quartered artichoke heart|||": "BRANDED_FDC:2313271",
            "wheat chex|||": "BRANDED_FDC:2745337",
            "vanilla almond milk|||": "BRANDED_FDC:2551168",
        }
        for concept_key, fdc_id in batch_co_expected.items():
            with self.subTest(concept_key=concept_key, source="branded_fdc_batch_co"):
                self.assertEqual("nutrition_ready_branded_fdc_proxy", rows[concept_key]["nutrition_status"])
                self.assertEqual(fdc_id, rows[concept_key]["sr28_fdc_id"])
        batch_cp_expected = {
            "candied orange peel|||": "BRANDED_FDC:2031264",
            "chocolate covered coffee bean|||": "BRANDED_FDC:2442159",
            "refrigerated breadstick dough|||": "BRANDED_FDC:2555573",
            "sugar cookie mix|||": "BRANDED_FDC:2367418",
            "carob chip|||": "BRANDED_FDC:2032052",
            "muesli|||": "BRANDED_FDC:2671789",
            "ener g egg substitute|||": "BRANDED_FDC:2598653",
            "pink peppercorn|||": "BRANDED_FDC:2034141",
            "honey dijon mustard|||": "BRANDED_FDC:2579134",
        }
        for concept_key, fdc_id in batch_cp_expected.items():
            with self.subTest(concept_key=concept_key, source="branded_fdc_batch_cp"):
                self.assertEqual("nutrition_ready_branded_fdc_proxy", rows[concept_key]["nutrition_status"])
                self.assertEqual(fdc_id, rows[concept_key]["sr28_fdc_id"])
        self.assertEqual(
            "nutrition_ready_branded_fdc_proxy",
            rows["refrigerated reduced fat crescent roll|||"]["nutrition_status"],
        )
        self.assertEqual(
            "BRANDED_FDC:1368534",
            rows["refrigerated reduced fat crescent roll|||"]["sr28_fdc_id"],
        )
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["mesquite powder|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:403385", rows["mesquite powder|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["dipping chocolate|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2011619", rows["dipping chocolate|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["roll mix|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:1626808", rows["roll mix|||"]["sr28_fdc_id"])
        self.assertEqual(
            "nutrition_ready_branded_fdc_proxy",
            rows["chocolate whey protein powder|||"]["nutrition_status"],
        )
        self.assertEqual("BRANDED_FDC:1375854", rows["chocolate whey protein powder|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["instant flour|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2235440", rows["instant flour|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["wheat pizza dough|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2544853", rows["wheat pizza dough|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["chocolate chip ice cream|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2471083", rows["chocolate chip ice cream|||"]["sr28_fdc_id"])
        self.assertEqual(
            "nutrition_ready_branded_fdc_proxy",
            rows["chocolate graham wafer pie crust|||"]["nutrition_status"],
        )
        self.assertEqual(
            "BRANDED_FDC:2652721",
            rows["chocolate graham wafer pie crust|||"]["sr28_fdc_id"],
        )
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["hot italian turkey sausage|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2040877", rows["hot italian turkey sausage|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["shortbread pie crust|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2676515", rows["shortbread pie crust|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["kellogg's rice krispies cereal|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2651250", rows["kellogg's rice krispies cereal|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["molly mcbutter|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:1860205", rows["molly mcbutter|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["madras curry paste|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2064022", rows["madras curry paste|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["pizza crust mix|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2313204", rows["pizza crust mix|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["lemon supreme cake mix|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2482416", rows["lemon supreme cake mix|||"]["sr28_fdc_id"])
        self.assertEqual(
            "nutrition_ready_branded_fdc_proxy",
            rows["honey maid graham cracker||crumb|"]["nutrition_status"],
        )
        self.assertEqual("BRANDED_FDC:1458915", rows["honey maid graham cracker||crumb|"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["sesame seed hamburger bun|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2579761", rows["sesame seed hamburger bun|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["dry rub seasoning|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2670179", rows["dry rub seasoning|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["canola mayonnaise|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2022347", rows["canola mayonnaise|||"]["sr28_fdc_id"])
        self.assertEqual(
            "nutrition_ready_branded_fdc_proxy",
            rows["buttermilk ranch salad dressing mix|||"]["nutrition_status"],
        )
        self.assertEqual(
            "BRANDED_FDC:2405578",
            rows["buttermilk ranch salad dressing mix|||"]["sr28_fdc_id"],
        )
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["wheat pizza crust|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2052491", rows["wheat pizza crust|||"]["sr28_fdc_id"])
        self.assertEqual("nutrition_ready_branded_fdc_proxy", rows["red decorating gel|||"]["nutrition_status"])
        self.assertEqual("BRANDED_FDC:2276371", rows["red decorating gel|||"]["sr28_fdc_id"])

    def test_reviewed_branded_fdc_rows_ignore_product_audit_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            products_db = temp / "products.db"
            conn = sqlite3.connect(products_db)
            conn.execute(
                """
                CREATE TABLE products (
                    fdc_id TEXT,
                    gtin_upc TEXT,
                    description TEXT,
                    brand_owner TEXT,
                    branded_food_category TEXT,
                    serving_size REAL,
                    serving_size_unit TEXT,
                    calories REAL,
                    protein_g REAL,
                    fat_g REAL,
                    carbs_g,
                    fiber_g REAL,
                    sugar_g REAL,
                    sodium_mg REAL
                )
                """
            )
            conn.execute(
                """
                INSERT INTO products VALUES (
                    '2596456',
                    '0041449450148',
                    'GLUTEN FREE ALL PURPOSE FLOUR',
                    'Continental Mills, Inc.',
                    'Flours & Corn Meal',
                    30,
                    'GRM',
                    367,
                    6.67,
                    3.33,
                    76.67,
                    3.3,
                    0,
                    17
                )
                """
            )
            conn.commit()
            conn.close()
            product_audit = temp / "product_audit.csv"
            product_audit.write_text(
                "concept_key,audit_status,policy,selected_description,selected_category\n"
                "gluten free all-purpose flour|||,contract_failed,review_required,BAD PRODUCT,Mexican Dinner Mixes\n",
                encoding="utf-8",
            )
            fallback_csv = temp / "fallback.csv"
            fallback_csv.write_text("concept_key,fdc_id,sr28_description,review_status,notes\n", encoding="utf-8")
            anchors_csv = temp / "anchors.csv"
            anchors_csv.write_text(
                "concept_key,source_system,food_id,description,food_family,form,state,allowed_description_tokens,forbidden_description_tokens,review_status,notes\n"
                "gluten free all-purpose flour|||,BRANDED_FDC,2596456,GLUTEN FREE ALL PURPOSE FLOUR,flour,gluten_free_blend,dry,gluten free;flour,cake mix,approved,test\n",
                encoding="utf-8",
            )
            density_csv = temp / "density.csv"
            density_csv.write_text("scope_type,scope_key,density_g_per_ml,review_status,notes\n", encoding="utf-8")
            nutrients_csv = temp / "food_nutrient.csv"
            nutrients_csv.write_text("id,fdc_id,nutrient_id,amount\n", encoding="utf-8")
            rows = load_product_nutrition(
                product_audit,
                products_db,
                density_csv,
                anchors_csv,
                fallback_csv,
                nutrients_csv,
            )
        by_concept = {row["concept_key"]: row for row in rows}
        self.assertIn("gluten free all-purpose flour|||", by_concept)
        flour = by_concept["gluten free all-purpose flour|||"]
        self.assertEqual("nutrition_ready_branded_fdc_proxy", flour["nutrition_status"])
        self.assertEqual("branded_fdc_nutrition_proxy", flour["policy"])
        self.assertEqual("GLUTEN FREE ALL PURPOSE FLOUR", flour["selected_description"])
        self.assertEqual("Flours & Corn Meal", flour["selected_category"])
        self.assertAlmostEqual(3.67, float(flour["calories_per_g"]))

    def test_reviewed_branded_fdc_ml_rows_use_density_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            products_db = temp / "products.db"
            conn = sqlite3.connect(products_db)
            conn.execute(
                """
                CREATE TABLE products (
                    fdc_id TEXT,
                    gtin_upc TEXT,
                    description TEXT,
                    brand_owner TEXT,
                    branded_food_category TEXT,
                    serving_size REAL,
                    serving_size_unit TEXT,
                    calories REAL,
                    protein_g REAL,
                    fat_g REAL,
                    carbs_g REAL,
                    fiber_g REAL,
                    sugar_g REAL,
                    sodium_mg REAL
                )
                """
            )
            conn.execute(
                """
                INSERT INTO products VALUES (
                    '2126290',
                    '',
                    'VANILLA FLAVORED SYRUP, VANILLA',
                    'Starbucks Coffee Company',
                    'Syrups & Molasses',
                    30,
                    'ml',
                    260,
                    0,
                    0,
                    65,
                    0,
                    65,
                    0
                )
                """
            )
            conn.commit()
            conn.close()
            anchors_csv = temp / "anchors.csv"
            anchors_csv.write_text(
                "concept_key,source_system,food_id,description,food_family,form,state,allowed_description_tokens,forbidden_description_tokens,review_status,notes\n"
                "vanilla flavored syrup|||,BRANDED_FDC,2126290,\"VANILLA FLAVORED SYRUP, VANILLA\",sweetener,syrup,liquid,vanilla;syrup,sugar-free,approved,test\n",
                encoding="utf-8",
            )
            density_csv = temp / "density.csv"
            density_csv.write_text(
                "scope_type,scope_key,density_g_per_ml,review_status,notes\n"
                "concept,vanilla flavored syrup|||,1.30,approved,test\n",
                encoding="utf-8",
            )
            rows = load_reviewed_branded_nutrition_rows(
                anchors_csv,
                products_db=products_db,
                density_bridge_csv=density_csv,
            )
        syrup = rows["vanilla flavored syrup|||"]
        self.assertEqual("nutrition_ready_branded_fdc_proxy", syrup["nutrition_status"])
        self.assertEqual("branded_fdc_per_100ml_density_bridge", syrup["nutrition_basis"])
        self.assertAlmostEqual(1.30, float(syrup["density_g_per_ml"]))
        self.assertAlmostEqual(2.0, float(syrup["calories_per_g"]))

    def test_reviewed_fndds_rows_ignore_product_audit_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            products_db = temp / "products.db"
            conn = sqlite3.connect(products_db)
            conn.execute(
                """
                CREATE TABLE products (
                    gtin_upc TEXT,
                    description TEXT,
                    brand_owner TEXT,
                    branded_food_category TEXT,
                    serving_size REAL,
                    serving_size_unit TEXT,
                    calories REAL,
                    protein_g REAL,
                    fat_g REAL,
                    carbs_g REAL,
                    fiber_g REAL,
                    sugar_g REAL,
                    sodium_mg REAL
                )
                """
            )
            conn.close()
            product_audit = temp / "product_audit.csv"
            product_audit.write_text(
                "concept_key,audit_status,policy,selected_description,selected_category\n"
                "pineapple|||dried,contract_failed,review_required,BAD RETAIL PRODUCT,Candy\n",
                encoding="utf-8",
            )
            fallback_csv = temp / "fallback.csv"
            fallback_csv.write_text("concept_key,fdc_id,sr28_description,review_status,notes\n", encoding="utf-8")
            anchors_csv = temp / "anchors.csv"
            anchors_csv.write_text(
                "concept_key,source_system,food_id,description,food_family,form,state,allowed_description_tokens,forbidden_description_tokens,review_status,notes\n"
                "pineapple|||dried,FNDDS,62120100,\"Pineapple, dried\",fruit,dried,sweetened,pineapple;dried,canned;fresh,approved,test\n",
                encoding="utf-8",
            )
            density_csv = temp / "density.csv"
            density_csv.write_text("scope_type,scope_key,density_g_per_ml,review_status,notes\n", encoding="utf-8")
            nutrients_csv = temp / "food_nutrient.csv"
            nutrients_csv.write_text("id,fdc_id,nutrient_id,amount\n", encoding="utf-8")
            rows = load_product_nutrition(
                product_audit,
                products_db,
                density_csv,
                anchors_csv,
                fallback_csv,
                nutrients_csv,
            )
        dried = {row["concept_key"]: row for row in rows}["pineapple|||dried"]
        self.assertEqual("nutrition_ready_fndds_anchor", dried["nutrition_status"])
        self.assertEqual("fndds_nutrition_only", dried["policy"])
        self.assertEqual("Pineapple, dried", dried["selected_description"])
        self.assertEqual("FNDDS", dried["selected_category"])
        self.assertEqual("FNDDS:62120100", dried["sr28_fdc_id"])

    def test_reviewed_sr28_rows_ignore_product_audit_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            products_db = temp / "products.db"
            conn = sqlite3.connect(products_db)
            conn.execute(
                """
                CREATE TABLE products (
                    gtin_upc TEXT,
                    description TEXT,
                    brand_owner TEXT,
                    branded_food_category TEXT,
                    serving_size REAL,
                    serving_size_unit TEXT,
                    calories REAL,
                    protein_g REAL,
                    fat_g REAL,
                    carbs_g REAL,
                    fiber_g REAL,
                    sugar_g REAL,
                    sodium_mg REAL
                )
                """
            )
            conn.close()
            product_audit = temp / "product_audit.csv"
            product_audit.write_text(
                "concept_key,audit_status,policy,selected_description,selected_category\n"
                "feta cheese|||,contract_passed,direct_buy,BAD RETAIL PRODUCT,Candy\n",
                encoding="utf-8",
            )
            fallback_csv = temp / "fallback.csv"
            fallback_csv.write_text(
                "concept_key,fdc_id,sr28_description,review_status,notes\n"
                "feta cheese|||,173420,\"Cheese, feta\",approved,test\n",
                encoding="utf-8",
            )
            anchors_csv = temp / "anchors.csv"
            anchors_csv.write_text(
                "concept_key,source_system,food_id,description,food_family,form,state,allowed_description_tokens,forbidden_description_tokens,review_status,notes\n",
                encoding="utf-8",
            )
            density_csv = temp / "density.csv"
            density_csv.write_text("scope_type,scope_key,density_g_per_ml,review_status,notes\n", encoding="utf-8")
            nutrients_csv = temp / "food_nutrient.csv"
            nutrients_csv.write_text(
                "id,fdc_id,nutrient_id,amount\n"
                "1,173420,1008,265\n"
                "2,173420,1003,14.21\n"
                "3,173420,1004,21.28\n"
                "4,173420,1005,3.88\n"
                "5,173420,1093,1139\n",
                encoding="utf-8",
            )
            rows = load_product_nutrition(
                product_audit,
                products_db,
                density_csv,
                anchors_csv,
                fallback_csv,
                nutrients_csv,
            )
        feta = {row["concept_key"]: row for row in rows}["feta cheese|||"]
        self.assertEqual("nutrition_ready_sr28_fallback", feta["nutrition_status"])
        self.assertEqual("sr28_nutrition_only", feta["policy"])
        self.assertEqual("Cheese, feta", feta["selected_description"])
        self.assertEqual("SR28", feta["selected_category"])
        self.assertEqual("173420", feta["sr28_fdc_id"])

    def test_reviewed_sr28_rows_do_not_require_product_audit_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            products_db = temp / "products.db"
            conn = sqlite3.connect(products_db)
            conn.execute(
                """
                CREATE TABLE products (
                    gtin_upc TEXT,
                    description TEXT,
                    brand_owner TEXT,
                    branded_food_category TEXT,
                    serving_size REAL,
                    serving_size_unit TEXT,
                    calories REAL,
                    protein_g REAL,
                    fat_g REAL,
                    carbs_g REAL,
                    fiber_g REAL,
                    sugar_g REAL,
                    sodium_mg REAL
                )
                """
            )
            conn.close()
            product_audit = temp / "product_audit.csv"
            product_audit.write_text(
                "concept_key,audit_status,policy,selected_description,selected_category\n",
                encoding="utf-8",
            )
            fallback_csv = temp / "fallback.csv"
            fallback_csv.write_text(
                "concept_key,fdc_id,sr28_description,review_status,notes\n"
                "feta cheese|||,173420,\"Cheese, feta\",approved,test\n",
                encoding="utf-8",
            )
            anchors_csv = temp / "anchors.csv"
            anchors_csv.write_text(
                "concept_key,source_system,food_id,description,food_family,form,state,allowed_description_tokens,forbidden_description_tokens,review_status,notes\n",
                encoding="utf-8",
            )
            density_csv = temp / "density.csv"
            density_csv.write_text("scope_type,scope_key,density_g_per_ml,review_status,notes\n", encoding="utf-8")
            nutrients_csv = temp / "food_nutrient.csv"
            nutrients_csv.write_text(
                "id,fdc_id,nutrient_id,amount\n"
                "1,173420,1008,265\n"
                "2,173420,1003,14.21\n"
                "3,173420,1004,21.28\n"
                "4,173420,1005,3.88\n"
                "5,173420,1093,1139\n",
                encoding="utf-8",
            )
            rows = load_product_nutrition(
                product_audit,
                products_db,
                density_csv,
                anchors_csv,
                fallback_csv,
                nutrients_csv,
            )
        by_concept = {row["concept_key"]: row for row in rows}
        self.assertIn("feta cheese|||", by_concept)
        feta = by_concept["feta cheese|||"]
        self.assertEqual("nutrition_ready_sr28_fallback", feta["nutrition_status"])
        self.assertEqual("sr28_nutrition_only", feta["policy"])
        self.assertEqual("173420", feta["sr28_fdc_id"])
        self.assertAlmostEqual(2.65, float(feta["calories_per_g"]))


class GeneratedArtifactPreflightTests(unittest.TestCase):
    def test_mapper_default_outputs_follow_min_recipe_count(self) -> None:
        parser = build_arg_parser()
        ge10_args = apply_output_defaults(parser.parse_args([]))
        self.assertEqual(DEFAULT_ARTIFACTS.ge10_line_mapping_csv, ge10_args.output_csv)
        self.assertEqual(DEFAULT_ARTIFACTS.ge10_line_mapping_misses_csv, ge10_args.misses_csv)
        self.assertEqual(DEFAULT_ARTIFACTS.ge10_line_mapping_summary_json, ge10_args.summary_json)
        self.assertEqual(DEFAULT_ARTIFACTS.ge10_line_mapping_report_md, ge10_args.report_md)

        full_args = apply_output_defaults(parser.parse_args(["--min-recipe-count", "1"]))
        self.assertEqual(DEFAULT_ARTIFACTS.full_line_mapping_csv, full_args.output_csv)
        self.assertEqual(DEFAULT_ARTIFACTS.full_line_mapping_misses_csv, full_args.misses_csv)
        self.assertEqual(DEFAULT_ARTIFACTS.full_line_mapping_summary_json, full_args.summary_json)
        self.assertEqual(DEFAULT_ARTIFACTS.full_line_mapping_report_md, full_args.report_md)

    def test_generated_recipe_mapping_csvs_have_parseable_counts(self) -> None:
        for relative_path in [
            "output/recipe_line_to_concept_ge10.csv",
            "output/recipe_line_to_concept_ge10_misses.csv",
        ]:
            path = IMPLEMENTATION_ROOT / relative_path
            if not path.exists():
                continue
            failures = []
            with path.open(newline="", encoding="utf-8") as handle:
                for line_number, row in enumerate(csv.DictReader(handle), start=2):
                    try:
                        int(row["recipe_count"])
                    except (KeyError, TypeError, ValueError) as exc:
                        failures.append((line_number, row.get("normalized_line"), row.get("recipe_count"), str(exc)))
                        if len(failures) >= 10:
                            break
            self.assertEqual([], failures, relative_path)

    def test_ge10_summary_is_not_stale_relative_to_mapping(self) -> None:
        mapping = DEFAULT_ARTIFACTS.ge10_line_mapping_csv
        summary = DEFAULT_ARTIFACTS.ge10_line_mapping_summary_json
        if not mapping.exists() or not summary.exists():
            return
        self.assertGreaterEqual(
            summary.stat().st_mtime + 1,
            mapping.stat().st_mtime,
            "canonical ge10 summary is older than the mapping CSV; rerun mapper with default artifact paths",
        )

    def test_legacy_dot_summary_is_not_newer_than_canonical_summary(self) -> None:
        legacy = IMPLEMENTATION_ROOT / "output" / "recipe_line_to_concept_ge10.summary.json"
        canonical = DEFAULT_ARTIFACTS.ge10_line_mapping_summary_json
        if not legacy.exists() or not canonical.exists():
            return
        self.assertLessEqual(
            legacy.stat().st_mtime,
            canonical.stat().st_mtime + 1,
            "legacy dot-summary is newer than canonical summary; rerun mapper with default artifact paths",
        )


class HistoricalBoilStageTests(unittest.TestCase):
    def test_downstream_hf_consumers_use_corrected_table(self) -> None:
        required = [
            IMPLEMENTATION_ROOT / "build_hf_v3_base_rollup.py",
            IMPLEMENTATION_ROOT / "probe_hf_v3_parser_calculation.py",
            IMPLEMENTATION_ROOT / "build_hf_v3_identity_layer.py",
        ]
        for path in required:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("hf_v3_line_collapse_corrected", text)

    def test_v1_preserves_meaningful_compound_foods(self) -> None:
        cases = {
            "container frozen whipped topping, thawed": "whipped topping",
            "frozen whipped topping, thawed": "whipped topping",
            "fat-free cool whip": "fat-free cool whip",
            "flank steak": "flank steak",
            "(1 liter)-Up": "7-up",
            "1 (10 oz.) 7 up": "7-up",
            "0,08 kg bacon": "bacon",
            "0,5 adzuki beans": "adzuki beans",
            "tomato sauce": "tomato sauce",
        }
        for surface, expected in cases.items():
            with self.subTest(surface=surface):
                self.assertEqual(expected, extract_base_food(surface))

    def test_v1_repairs_modifier_left_comma_phrases(self) -> None:
        cases = {
            "frozen, chopped broccoli": "broccoli",
            "fat-free, less-sodium chicken broth": "less-sodium chicken broth",
        }
        for surface, expected in cases.items():
            with self.subTest(surface=surface):
                self.assertEqual(expected, extract_base_food(surface))

    def test_hf_historical_chain_does_not_emit_known_poison_bases(self) -> None:
        cases = {
            "container frozen whipped topping, thawed": "whipped topping",
            "frozen whipped topping, thawed": "whipped topping",
            "flank steak": "flank steak",
            "7-up": "7-up",
            "fat-free cool whip": "fat-free whipped topping",
            "cool whip topping": "whipped topping",
            "fat-free cool whip topping": "fat-free whipped topping",
            "cool whip whipped topping": "whipped topping",
            "cool whip frozen whipped topping": "whipped topping",
            "half and half": "half and half",
            "c. half and half": "half and half",
            "half and half, divided": "half and half",
            "heddar cheese": "cheddar cheese",
            "% low-fat milk": "low-fat milk",
            "firmly packed brown sugar": "brown sugar",
            "frozen, chopped broccoli": "broccoli",
            "fat-free, less-sodium chicken broth": "less-sodium chicken broth",
        }
        poison = {"topping", "flank", "frozen", "fat-free", "up"}
        for surface, expected in cases.items():
            with self.subTest(surface=surface):
                _v1, _v2, v3 = collapse_candidate_to_v3(surface)
                self.assertEqual(expected, v3)
                self.assertNotIn(v3, poison)


class CorrectedHfCollapseTests(unittest.TestCase):
    def test_reject_reason_blocks_known_poison_bases(self) -> None:
        for value in ["", "fat-free", "frozen", "topping", "flank", "up", "and", "&nbsp", "*", "5", "a"]:
            with self.subTest(value=value):
                self.assertTrue(reject_reason(value))

    def test_corrected_collapse_uses_raw_fallback_when_hf_loses_digit(self) -> None:
        selected = select_collapse(
            normalized_line="1 (10 oz.) 7 up",
            example_raw_line="1 (10 oz.) 7 up",
            hf_candidate="(.) up",
        )
        self.assertEqual("fallback_valid", selected["collapse_status"])
        self.assertEqual("lemon lime soda", selected["boil_v3_base_food"])

    def test_corrected_collapse_recovers_parenthetical_food_candidate(self) -> None:
        selected = select_collapse(
            normalized_line="(2-3 garlic cloves, minced)*",
            example_raw_line="(2-3 garlic cloves, minced)*",
            hf_candidate="(",
        )
        self.assertEqual("fallback_valid", selected["collapse_status"])
        self.assertEqual("garlic", selected["boil_v3_base_food"])


class ItemFieldFallbackTests(unittest.TestCase):
    """Tests for Phase 1 item-field fallback in audit_recipe_qa_nutrition_calculation.py.

    MUST fallback: lines where the parser mangled the surface to |||
    but the item field contains a known food.

    MUST NOT fallback: alternatives, compounds, and context-dependent lines.
    """

    def setUp(self) -> None:
        # Load known concepts for validation
        self.known: set[str] = set()
        dict_csv = DEFAULT_ARTIFACTS.dictionary_csv
        supp_csv = DEFAULT_ARTIFACTS.supplemental_concepts_csv
        if dict_csv.exists():
            with dict_csv.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    base = row.get("base_food", "").strip().lower()
                    if base:
                        self.known.add(base)
        if supp_csv.exists():
            with supp_csv.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    for field in ("canonical_concept", "alias"):
                        val = row.get(field, "").strip().lower()
                        if val:
                            self.known.add(val)

    def test_must_fallback_items_are_known_concepts(self) -> None:
        """Items that MUST use fallback should resolve to known concepts."""
        must_fallback = [
            ("butter", "butter"),
            ("unsalted butter", "unsalted butter"),
            ("zucchini", "zucchini"),
        ]
        for item, expected_base in must_fallback:
            with self.subTest(item=item):
                self.assertIn(
                    expected_base.lower(),
                    self.known,
                    f"Item '{item}' should resolve to known concept '{expected_base}' but it's not in dictionary/supplemental",
                )

    def test_must_not_fallback_alternatives_blocked(self) -> None:
        """Lines with 'or' / 'and' must NOT use item-field fallback."""
        blocked_items = [
            "rice wine or dry sherry",
            "butter or non-stick spray",
            "Monterey Jack and cheddar cheese blend",
        ]
        for item in blocked_items:
            with self.subTest(item=item):
                self.assertTrue(
                    " or " in item.lower() or " and " in item.lower(),
                    f"Item '{item}' should contain 'or'/'and' to be blocked from fallback",
                )

    def test_fallback_condition_excludes_alternatives(self) -> None:
        """The ITEM_FALLBACK_BLOCKED_ACTIONS constant should block alternatives and splits."""
        from audit_recipe_qa_nutrition_calculation import (
            ITEM_FALLBACK_ALWAYS_TRUSTED_SOURCES,
            ITEM_FALLBACK_BLOCKED_ACTIONS,
        )
        self.assertIn("true_alternative_review", ITEM_FALLBACK_BLOCKED_ACTIONS)
        self.assertIn("component_split_review", ITEM_FALLBACK_BLOCKED_ACTIONS)
        self.assertIn("approved_alternative_options", ITEM_FALLBACK_BLOCKED_ACTIONS)
        self.assertIn("approved_split", ITEM_FALLBACK_BLOCKED_ACTIONS)
        self.assertIn("recipe_line_patch_item", ITEM_FALLBACK_ALWAYS_TRUSTED_SOURCES)

    def test_fallback_lookup_builder_exists_and_is_callable(self) -> None:
        """build_item_fallback_lookup should be importable."""
        from audit_recipe_qa_nutrition_calculation import build_item_fallback_lookup
        self.assertTrue(callable(build_item_fallback_lookup))

    def test_recipe_line_patch_items_feed_item_fallback_lookup(self) -> None:
        from audit_recipe_qa_nutrition_calculation import build_item_fallback_lookup

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            patch_csv = temp / "reviewed_recipe_line_patches.csv"
            patch_csv.write_text(
                "patch_id,recipe_id,old_ingredient_text,new_display,new_item,new_grams,problem,cooking_step,reason,review_status,source_artifact,notes\n"
                "p1,40731,\"1 cup cooked ham, diced\","
                "\"1 cup ham, diced\","
                "\"ham, diced\",188,cooked_ham_no_step,"
                "\"cook ham steak\","
                "\"recipe-level patch\",approved,legacy_json,"
                "\"legacy code fields intentionally excluded\"\n",
                encoding="utf-8",
            )
            line_audit_db = temp / "line_audit.db"
            line_conn = sqlite3.connect(line_audit_db)
            line_conn.execute(
                """
                CREATE TABLE line_eval (
                    cleaned_surface TEXT,
                    concept_key TEXT,
                    product_contract_key TEXT,
                    product_audit_status TEXT,
                    product_policy TEXT,
                    dictionary_match_status TEXT,
                    resolution_action TEXT,
                    failure_bucket TEXT,
                    is_concept_mapped INTEGER,
                    parsed_quantity TEXT,
                    parsed_unit TEXT,
                    quantity_bucket TEXT,
                    recipe_count INTEGER
                )
                """
            )
            line_conn.commit()
            line_conn.close()

            conn = sqlite3.connect(":memory:")
            conn.execute(f"ATTACH DATABASE '{line_audit_db}' AS line_audit")
            build_item_fallback_lookup(conn, normalized_item_bridge_csv=None, recipe_line_patches_csv=patch_csv)
            row = conn.execute(
                """
                SELECT concept_key, lookup_source
                FROM item_fallback_lookup
                WHERE cleaned_surface = 'ham, diced'
                """
            ).fetchone()
            conn.close()

            self.assertEqual(("ham steak|||", "recipe_line_patch_item"), row)

    def test_approved_regex_rules_feed_item_fallback_lookup(self) -> None:
        from audit_recipe_qa_nutrition_calculation import build_item_fallback_lookup

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            approved_rules_csv = temp / "approved_normalization_rules.csv"
            approved_rules_csv.write_text(
                "rule_id,rule_type,match_type,input_surface,canonical_concept_key,canonical_surface,components,status,evidence,source,review_date\n"
                "oil_regex,manual_quantity,regex,"
                "\"^(?P<oil>vegetable oil|olive oil),?\\s+for\\s+fry(?:ing)?$\","
                "\\g<oil>|||,manual_quantity_required,,approved,"
                "\"Extract oil identity; consumed grams handled by quantity policy.\",codex,2026-04-15\n",
                encoding="utf-8",
            )
            line_audit_db = temp / "line_audit.db"
            line_conn = sqlite3.connect(line_audit_db)
            line_conn.execute(
                """
                CREATE TABLE line_eval (
                    cleaned_surface TEXT,
                    concept_key TEXT,
                    product_contract_key TEXT,
                    product_audit_status TEXT,
                    product_policy TEXT,
                    dictionary_match_status TEXT,
                    resolution_action TEXT,
                    failure_bucket TEXT,
                    is_concept_mapped INTEGER,
                    parsed_quantity TEXT,
                    parsed_unit TEXT,
                    quantity_bucket TEXT,
                    recipe_count INTEGER
                )
                """
            )
            line_conn.commit()
            line_conn.close()

            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE TABLE recipe_qa_ingredients (item TEXT)")
            conn.execute("INSERT INTO recipe_qa_ingredients VALUES ('olive oil for frying')")
            conn.execute(f"ATTACH DATABASE '{line_audit_db}' AS line_audit")
            build_item_fallback_lookup(
                conn,
                normalized_item_bridge_csv=None,
                recipe_line_patches_csv=None,
                sr28_fallback_csv=None,
                approved_rules_csv=approved_rules_csv,
            )
            row = conn.execute(
                """
                SELECT concept_key, lookup_source, dictionary_match_status
                FROM item_fallback_lookup
                WHERE cleaned_surface = 'olive oil for frying'
                """
            ).fetchone()
            conn.close()

            self.assertEqual(("olive oil|||", "approved_normalization_regex", "approved_normalization_regex_match"), row)

    def test_approved_regex_rules_feed_parsed_display_lookup_key(self) -> None:
        from audit_recipe_qa_nutrition_calculation import build_item_fallback_lookup, install_display_parse_functions

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            approved_rules_csv = temp / "approved_normalization_rules.csv"
            approved_rules_csv.write_text(
                "rule_id,rule_type,match_type,input_surface,canonical_concept_key,canonical_surface,components,status,evidence,source,review_date\n"
                "pepper_regex,alias,regex,\"^red\\s+organic\\s+bell\\s+pepper.*$\","
                "red bell pepper|||,red bell pepper,,approved,"
                "\"Organic is shopping detail; red bell pepper is identity.\",codex,2026-04-15\n",
                encoding="utf-8",
            )
            line_audit_db = temp / "line_audit.db"
            line_conn = sqlite3.connect(line_audit_db)
            line_conn.execute(
                """
                CREATE TABLE line_eval (
                    cleaned_surface TEXT,
                    concept_key TEXT,
                    product_contract_key TEXT,
                    product_audit_status TEXT,
                    product_policy TEXT,
                    dictionary_match_status TEXT,
                    resolution_action TEXT,
                    failure_bucket TEXT,
                    is_concept_mapped INTEGER,
                    parsed_quantity TEXT,
                    parsed_unit TEXT,
                    quantity_bucket TEXT,
                    recipe_count INTEGER
                )
                """
            )
            line_conn.commit()
            line_conn.close()

            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE TABLE recipe_qa_ingredients (item TEXT, display TEXT)")
            conn.execute(
                "INSERT INTO recipe_qa_ingredients VALUES (?, ?)",
                ("1 red organic bell pepper (diced)", "1 red organic bell pepper (diced)"),
            )
            install_display_parse_functions(conn)
            conn.execute(f"ATTACH DATABASE '{line_audit_db}' AS line_audit")
            build_item_fallback_lookup(
                conn,
                normalized_item_bridge_csv=None,
                recipe_line_patches_csv=None,
                sr28_fallback_csv=None,
                approved_rules_csv=approved_rules_csv,
            )
            row = conn.execute(
                """
                SELECT concept_key, lookup_source
                FROM item_fallback_lookup
                WHERE cleaned_surface = 'red organic bell pepper'
                """
            ).fetchone()
            conn.close()

            self.assertEqual(("red bell pepper|||", "approved_normalization_regex"), row)

    def test_approved_reject_rules_feed_item_fallback_lookup(self) -> None:
        from audit_recipe_qa_nutrition_calculation import build_item_fallback_lookup, install_display_parse_functions

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            approved_rules_csv = temp / "approved_normalization_rules.csv"
            approved_rules_csv.write_text(
                "rule_id,rule_type,match_type,input_surface,canonical_concept_key,canonical_surface,components,status,evidence,source,review_date\n"
                "push_pin_reject,reject,regex,^push\\s+pin$,,non_food,,approved,"
                "\"Craft hardware is not a food ingredient.\",codex,2026-04-15\n",
                encoding="utf-8",
            )
            line_audit_db = temp / "line_audit.db"
            line_conn = sqlite3.connect(line_audit_db)
            line_conn.execute(
                """
                CREATE TABLE line_eval (
                    cleaned_surface TEXT,
                    concept_key TEXT,
                    product_contract_key TEXT,
                    product_audit_status TEXT,
                    product_policy TEXT,
                    dictionary_match_status TEXT,
                    resolution_action TEXT,
                    failure_bucket TEXT,
                    is_concept_mapped INTEGER,
                    parsed_quantity TEXT,
                    parsed_unit TEXT,
                    quantity_bucket TEXT,
                    recipe_count INTEGER
                )
                """
            )
            line_conn.commit()
            line_conn.close()

            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE TABLE recipe_qa_ingredients (item TEXT, display TEXT)")
            conn.execute("INSERT INTO recipe_qa_ingredients VALUES ('Push pin', 'Push pin')")
            install_display_parse_functions(conn)
            conn.execute(f"ATTACH DATABASE '{line_audit_db}' AS line_audit")
            build_item_fallback_lookup(
                conn,
                normalized_item_bridge_csv=None,
                recipe_line_patches_csv=None,
                sr28_fallback_csv=None,
                approved_rules_csv=approved_rules_csv,
            )
            row = conn.execute(
                """
                SELECT concept_key, lookup_source, failure_bucket
                FROM item_fallback_lookup
                WHERE cleaned_surface = 'push pin'
                """
            ).fetchone()
            conn.close()

            self.assertEqual(("", "approved_normalization_reject", "intentional_skip"), row)

    def test_approved_regex_rules_do_not_replace_bridge_rows(self) -> None:
        from audit_recipe_qa_nutrition_calculation import build_item_fallback_lookup

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            bridge_csv = temp / "normalized_item_concept_bridge.csv"
            bridge_csv.write_text(
                "normalized_item,occurrence_count,canonical_concept_key,canonical_surface,bridge_status,"
                "bridge_source,match_rule_id,trust_level,product_contract_status,product_contract_key,"
                "review_notes,registry_fingerprint\n"
                "salt,12,salt|||,salt,concept_ready,dictionary,,dictionary,contract_passed,salt|||,,abc\n",
                encoding="utf-8",
            )
            approved_rules_csv = temp / "approved_normalization_rules.csv"
            approved_rules_csv.write_text(
                "rule_id,rule_type,match_type,input_surface,canonical_concept_key,canonical_surface,components,status,evidence,source,review_date\n"
                "salt_regex,alias,regex,^salt$,salt|||,salt,,approved,Generic salt regex,codex,2026-04-15\n",
                encoding="utf-8",
            )
            line_audit_db = temp / "line_audit.db"
            line_conn = sqlite3.connect(line_audit_db)
            line_conn.execute(
                """
                CREATE TABLE line_eval (
                    cleaned_surface TEXT,
                    concept_key TEXT,
                    product_contract_key TEXT,
                    product_audit_status TEXT,
                    product_policy TEXT,
                    dictionary_match_status TEXT,
                    resolution_action TEXT,
                    failure_bucket TEXT,
                    is_concept_mapped INTEGER,
                    parsed_quantity TEXT,
                    parsed_unit TEXT,
                    quantity_bucket TEXT,
                    recipe_count INTEGER
                )
                """
            )
            line_conn.commit()
            line_conn.close()

            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE TABLE recipe_qa_ingredients (item TEXT)")
            conn.execute("INSERT INTO recipe_qa_ingredients VALUES ('salt')")
            conn.execute(f"ATTACH DATABASE '{line_audit_db}' AS line_audit")
            build_item_fallback_lookup(
                conn,
                normalized_item_bridge_csv=bridge_csv,
                recipe_line_patches_csv=None,
                sr28_fallback_csv=None,
                approved_rules_csv=approved_rules_csv,
            )
            row = conn.execute(
                """
                SELECT product_audit_status, lookup_source
                FROM item_fallback_lookup
                WHERE cleaned_surface = 'salt'
                """
            ).fetchone()
            conn.close()

            self.assertEqual(("contract_passed", "normalized_item_bridge"), row)

    def test_approved_reject_rules_replace_bridge_rows(self) -> None:
        from audit_recipe_qa_nutrition_calculation import build_item_fallback_lookup

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            bridge_csv = temp / "normalized_item_concept_bridge.csv"
            bridge_csv.write_text(
                "normalized_item,occurrence_count,canonical_concept_key,canonical_surface,bridge_status,"
                "bridge_source,match_rule_id,trust_level,product_contract_status,product_contract_key,"
                "review_notes,registry_fingerprint\n"
                "orange essential oil,12,orange essential oil|||,orange essential oil,concept_ready,"
                "dictionary,,dictionary,contract_passed,orange essential oil|||,,abc\n",
                encoding="utf-8",
            )
            approved_rules_csv = temp / "approved_normalization_rules.csv"
            approved_rules_csv.write_text(
                "rule_id,rule_type,match_type,input_surface,canonical_concept_key,canonical_surface,components,status,evidence,source,review_date\n"
                "essential_oil_reject,reject,regex,^orange\\s+essential\\s+oil$,,non_food,,approved,"
                "Air-freshener essential oil is not a food ingredient.,codex,2026-04-15\n",
                encoding="utf-8",
            )
            line_audit_db = temp / "line_audit.db"
            line_conn = sqlite3.connect(line_audit_db)
            line_conn.execute(
                """
                CREATE TABLE line_eval (
                    cleaned_surface TEXT,
                    concept_key TEXT,
                    product_contract_key TEXT,
                    product_audit_status TEXT,
                    product_policy TEXT,
                    dictionary_match_status TEXT,
                    resolution_action TEXT,
                    failure_bucket TEXT,
                    is_concept_mapped INTEGER,
                    parsed_quantity TEXT,
                    parsed_unit TEXT,
                    quantity_bucket TEXT,
                    recipe_count INTEGER
                )
                """
            )
            line_conn.commit()
            line_conn.close()

            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE TABLE recipe_qa_ingredients (item TEXT)")
            conn.execute("INSERT INTO recipe_qa_ingredients VALUES ('orange essential oil')")
            conn.execute(f"ATTACH DATABASE '{line_audit_db}' AS line_audit")
            build_item_fallback_lookup(
                conn,
                normalized_item_bridge_csv=bridge_csv,
                recipe_line_patches_csv=None,
                sr28_fallback_csv=None,
                approved_rules_csv=approved_rules_csv,
            )
            row = conn.execute(
                """
                SELECT concept_key, lookup_source, failure_bucket
                FROM item_fallback_lookup
                WHERE cleaned_surface = 'orange essential oil'
                """
            ).fetchone()
            conn.close()

            self.assertEqual(("", "approved_normalization_reject", "intentional_skip"), row)

    def test_spaced_concept_keys_are_canonicalized_before_gram_lookup(self) -> None:
        self.assertEqual("lemon juice|||", normalize_concept_key(" lemon juice ||| "))
        self.assertEqual(
            "salt|||;black pepper|||",
            normalize_concept_key_list(" salt||| ; black pepper ||| "),
        )

        conn = sqlite3.connect(":memory:")
        try:
            install_household_unit_functions(
                conn,
                {
                    ("lemon juice|||", "cup"): {
                        "grams_per_unit": 244.0,
                        "rationale": "test lemon juice cup",
                    }
                },
            )
            grams = conn.execute("SELECT household_unit_grams('lemon juice |||', '1', 'cup')").fetchone()[0]
        finally:
            conn.close()

        self.assertEqual(244.0, grams)

    def test_recipe_line_patch_loader_uses_clean_sr28_side_fields_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            patch_csv = Path(temp_dir) / "reviewed_recipe_line_patches.csv"
            patch_csv.write_text(
                "patch_id,recipe_id,old_ingredient_text,new_display,new_item,new_grams,problem,cooking_step,reason,review_status,source_artifact,notes\n"
                "p1,39845,\"2 cups cooked chicken, shredded or diced\","
                "\"1 1/2 lbs boneless skinless chicken breast\","
                "boneless skinless chicken breast,680,cooked_chicken_no_step,"
                "\"cook chicken\","
                "\"recipe-level patch\",approved,legacy_json,"
                "\"legacy code fields intentionally excluded\"\n",
                encoding="utf-8",
            )
            patches = load_recipe_line_patches(patch_csv)
            patch = patches[("39845", "2 cups cooked chicken, shredded or diced")]
            self.assertEqual("boneless skinless chicken breast", patch["new_item"])
            self.assertEqual(680.0, patch["new_grams"])
            self.assertNotIn("new_fpid", patch)
            self.assertNotIn("old_fpid", patch)

    def test_recipe_line_patch_is_applied_before_sr28_bridge_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            recipe_db = temp / "recipe_qa.db"
            conn = sqlite3.connect(recipe_db)
            conn.execute("CREATE TABLE recipe_cleaned (recipe_id TEXT, title TEXT, ingredients_json TEXT)")
            conn.execute(
                "INSERT INTO recipe_cleaned VALUES (?,?,?)",
                (
                    "39845",
                    "Chicken test",
                    json.dumps(
                        [
                            {
                                "display": "2 cups cooked chicken, shredded or diced",
                                "item": "cooked chicken",
                                "grams": 280,
                            }
                        ]
                    ),
                ),
            )
            conn.commit()
            conn.close()

            patch_csv = temp / "reviewed_recipe_line_patches.csv"
            patch_csv.write_text(
                "patch_id,recipe_id,old_ingredient_text,new_display,new_item,new_grams,problem,cooking_step,reason,review_status,source_artifact,notes\n"
                "p1,39845,\"2 cups cooked chicken, shredded or diced\","
                "\"1 1/2 lbs boneless skinless chicken breast\","
                "boneless skinless chicken breast,680,cooked_chicken_no_step,"
                "\"cook chicken\","
                "\"recipe-level patch\",approved,legacy_json,"
                "\"legacy code fields intentionally excluded\"\n",
                encoding="utf-8",
            )

            out = sqlite3.connect(":memory:")
            applied = populate_recipe_ingredients(out, recipe_db, recipe_line_patches_csv=patch_csv)
            row = out.execute(
                """
                SELECT display, item, normalized_line, grams, patch_id, patch_problem, patched_old_display
                FROM recipe_qa_ingredients
                """
            ).fetchone()
            out.close()

            self.assertEqual(1, applied)
            self.assertEqual("1 1/2 lbs boneless skinless chicken breast", row[0])
            self.assertEqual("boneless skinless chicken breast", row[1])
            self.assertEqual("1 1/2 lbs boneless skinless chicken breast", row[2])
            self.assertEqual(680.0, row[3])
            self.assertEqual("p1", row[4])
            self.assertEqual("cooked_chicken_no_step", row[5])
            self.assertEqual("2 cups cooked chicken, shredded or diced", row[6])


if __name__ == "__main__":
    unittest.main()
