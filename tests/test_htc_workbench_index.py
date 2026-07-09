from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from htc_workbench_index import build_dashboard, build_index


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_dashboard_surfaces_baby_oatmeal_join_risk(tmp_path: Path):
    products = tmp_path / "products.csv"
    consensus = tmp_path / "consensus.csv"
    recipes = tmp_path / "recipes.csv"
    db = tmp_path / "workbench.sqlite"

    write_csv(products, [
        {
            "source": "kroger",
            "rowid": "126979",
            "upc": "0002392390017",
            "name": "Earth's Best Organic Whole Grain Oatmeal Baby Cereal",
            "brand": "Earth's Best",
            "size_display": "8 oz",
            "category_path": "Pantry > Hot Cereal",
            "category_path_walmart": "",
            "search_term": "multigrain oatmeal",
            "raw_htc_code": "868E000H",
            "tree_authority": "api_taxonomy_v2",
            "taxonomy_status": "identity_map",
            "tree_product_identity": "Hot Cereal",
            "tree_canonical_path": "Pantry > Hot Cereal",
            "tree_modifier": "Oatmeal Organic Whole Grain",
            "htc_code": "868E000H",
            "htc_confidence": "0.99",
            "htc_source": "api_taxonomy_v2",
            "non_food_path": "0",
        },
        {
            "source": "kroger",
            "rowid": "126980",
            "upc": "0002392390017",
            "name": "Earth's Best Organic Whole Grain Oatmeal Baby Cereal",
            "brand": "Earth's Best",
            "size_display": "8 oz",
            "category_path": "Pantry > Hot Cereal",
            "category_path_walmart": "",
            "search_term": "baby oatmeal",
            "raw_htc_code": "868E000H",
            "tree_authority": "api_taxonomy_v2",
            "taxonomy_status": "identity_map",
            "tree_product_identity": "Hot Cereal",
            "tree_canonical_path": "Pantry > Hot Cereal",
            "tree_modifier": "Oatmeal Organic Whole Grain",
            "htc_code": "868E000H",
            "htc_confidence": "0.99",
            "htc_source": "api_taxonomy_v2",
            "non_food_path": "0",
        },
    ])
    write_csv(consensus, [
        {
            "fdc_id": "1",
            "title": "OLD FASHIONED OATMEAL",
            "branded_food_category": "Cereal",
            "product_identity_fixed": "Oatmeal",
            "canonical_path": "Pantry > Grain > Oats > Oatmeal",
            "retail_leaf_path": "Pantry > Grain > Oats > Oatmeal > Plain",
            "modifier": "Plain",
            "htc_code": "~85000003",
            "htc_full_code": "~85000003-000000-0000",
            "htc_confidence": "0.90",
            "htc_source": "canonical_path",
        },
        {
            "fdc_id": "2",
            "title": "ORGANIC OATMEAL BABY CEREAL",
            "branded_food_category": "Baby/Infant Foods",
            "product_identity_fixed": "Baby Cereal",
            "canonical_path": "Baby > Cereal > Baby Cereal",
            "retail_leaf_path": "Baby > Cereal > Baby Cereal > Oatmeal > Organic",
            "modifier": "Oatmeal > Organic",
            "htc_code": "~86E50008",
            "htc_full_code": "~86E50008-AB12CD-2001",
            "htc_confidence": "0.90",
            "htc_source": "canonical_path",
        },
    ])
    write_csv(recipes, [
        {
            "recipe_id": "1",
            "recipe_title": "Oatmeal Cookies",
            "ingredient_item": "oatmeal",
            "display": "2 cups oatmeal",
            "htc_code": "85000003",
            "htc_confidence": "0.60",
            "normalized_canonical_text": "oatmeal",
            "normalized_identity_phrase": "oatmeal",
            "normalized_user_claims": "",
            "normalized_form_facets": "",
            "normalized_processing_facets": "",
        },
        {
            "recipe_id": "2",
            "recipe_title": "Baby Oatmeal Drink",
            "ingredient_item": "baby oatmeal cereal",
            "display": "8 ounces baby oatmeal cereal",
            "htc_code": "86E50008",
            "htc_confidence": "0.60",
            "normalized_canonical_text": "baby oatmeal cereal",
            "normalized_identity_phrase": "baby oatmeal cereal",
            "normalized_user_claims": "",
            "normalized_form_facets": "",
            "normalized_processing_facets": "",
        },
    ])

    meta = build_index(db, products, consensus, recipes)
    dashboard = build_dashboard(db, rowid="126979")

    assert meta["product_rows"] == 2
    assert dashboard["observed_facets"]["audience"] == ["baby"]
    assert dashboard["witnesses"]["same_upc"]
    assert dashboard["witnesses"]["recipe_use"]
    assert dashboard["candidate_families"]
    assert dashboard["expandable_branches"] == []
    assert dashboard["join_risks"][0]["risk"] == "audience_mismatch"
    assert dashboard["candidate_families"][0]["top_full_codes"]
    assert "expand_candidate_family" in dashboard["candidate_families"][0]["expand_tools"][0]
