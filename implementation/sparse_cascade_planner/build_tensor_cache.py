#!/usr/bin/env python3
"""Build a sparse-cascade tensor cache from this bundle's calculator-native data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Dict

from pricing_guard import assert_no_default_priced_ingredients


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "implementation" / "output" / "sparse_cascade_planner"
DEFAULT_HESTIA_API = Path("/Users/jamiebarton/Desktop/Hestia/api")
DEFAULT_RECIPES_CSV = OUT_DIR / "recipe_qa_calculator_native.csv"
DEFAULT_PACKAGE_DB = OUT_DIR / "food_packages_calculator_native.db"
DEFAULT_INGREDIENT_META = OUT_DIR / "ingredient_meta.json"
DEFAULT_TENSOR_CACHE_DIR = OUT_DIR / "tensor_cache"
DEFAULT_RECIPE_QA_DB = ROOT / "data" / "recipe_qa.db"


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def package_summary(db_path: Path) -> Dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            """
            SELECT
              COUNT(*) AS package_rows,
              COUNT(DISTINCT fndds_code) AS ingredient_keys,
              SUM(CASE WHEN kroger_price_cents > 0 THEN 1 ELSE 0 END) AS kroger_rows,
              SUM(CASE WHEN walmart_price_cents > 0 THEN 1 ELSE 0 END) AS walmart_rows
            FROM packages
            """
        ).fetchone()
    finally:
        conn.close()
    return {
        "package_rows": int(rows[0] or 0),
        "ingredient_keys": int(rows[1] or 0),
        "kroger_rows": int(rows[2] or 0),
        "walmart_rows": int(rows[3] or 0),
    }


def write_cache_files(recipe_db, ingredient_index, package_index, cache_dir: Path, torch_module) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)

    torch_module.save(
        {
            "recipe_ids": recipe_db.recipe_ids.cpu(),
            "ingredient_indices": recipe_db.ingredient_indices.cpu(),
            "ingredient_amounts": recipe_db.ingredient_amounts.cpu(),
            "nutrition": recipe_db.nutrition.cpu(),
            "food_groups": recipe_db.food_groups.cpu(),
            "servings": recipe_db.servings.cpu(),
            "nnz": recipe_db.nnz.cpu(),
            "protein_source": recipe_db.protein_source.cpu(),
            "ingredient_indices_flat": recipe_db.ingredient_indices_flat.cpu(),
            "packed_metadata": recipe_db.packed_metadata.cpu(),
            "gpu_recipe_id_to_idx": recipe_db.gpu_recipe_id_to_idx.cpu(),
            "gpu_recipe_to_template": recipe_db.gpu_recipe_to_template.cpu(),
            "gpu_recipe_is_one_dish": recipe_db.gpu_recipe_is_one_dish.cpu(),
            "gpu_side_compat": recipe_db.gpu_side_compat.cpu(),
            "is_fixed_portion": recipe_db.is_fixed_portion.cpu(),
            "sodium_per_serving": recipe_db.sodium_per_serving.cpu(),
            "recipe_names": recipe_db.names,
        },
        cache_dir / "recipe_db_tensors.pt",
    )

    torch_module.save(
        {
            "fpid_to_idx": ingredient_index.fpid_to_idx,
            "idx_to_fpid": ingredient_index.idx_to_fpid,
            "num_ingredients": ingredient_index.num_ingredients,
        },
        cache_dir / "ingredient_index.pt",
    )

    torch_module.save(
        {
            "meal_main_indices": {k: v.cpu() for k, v in recipe_db.meal_main_indices.items()},
            "meal_side_indices": {k: v.cpu() for k, v in recipe_db.meal_side_indices.items()},
            "template_to_sides": {k: v.cpu() for k, v in recipe_db.template_to_sides.items()},
            "template_to_side_pool_ids": {
                k: v.cpu() for k, v in recipe_db.template_to_side_pool_ids.items()
            },
        },
        cache_dir / "template_tensors.pt",
    )

    torch_module.save(
        {
            "prices": package_index._gpu_prices.cpu(),
            "sizes": package_index._gpu_sizes.cpu(),
        },
        cache_dir / "package_index.pt",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hestia-api", type=Path, default=DEFAULT_HESTIA_API)
    parser.add_argument("--recipes-csv", type=Path, default=DEFAULT_RECIPES_CSV)
    parser.add_argument("--package-db", type=Path, default=DEFAULT_PACKAGE_DB)
    parser.add_argument("--ingredient-meta", type=Path, default=DEFAULT_INGREDIENT_META)
    parser.add_argument("--recipe-qa-db", type=Path, default=DEFAULT_RECIPE_QA_DB)
    parser.add_argument("--tensor-cache-dir", type=Path, default=DEFAULT_TENSOR_CACHE_DIR)
    parser.add_argument("--device", default="cpu")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    hestia_api = args.hestia_api.expanduser().resolve()
    recipes_csv = args.recipes_csv.expanduser().resolve()
    package_db = args.package_db.expanduser().resolve()
    ingredient_meta = args.ingredient_meta.expanduser().resolve()
    recipe_qa_db = args.recipe_qa_db.expanduser().resolve()
    cache_dir = args.tensor_cache_dir.expanduser().resolve()

    for label, path in {
        "Hestia API": hestia_api,
        "recipes CSV": recipes_csv,
        "package DB": package_db,
        "ingredient meta": ingredient_meta,
        "recipe-QA DB": recipe_qa_db,
    }.items():
        if not path.exists():
            raise FileNotFoundError(f"{label} not found: {path}")

    os.environ["HESTIA_RECIPES_CSV"] = str(recipes_csv)
    os.environ["HESTIA_PACKAGES_DB"] = str(package_db)
    os.environ["HESTIA_INGREDIENT_META_JSON"] = str(ingredient_meta)
    os.environ["HESTIA_TENSOR_CACHE_DIR"] = str(cache_dir)
    os.environ.setdefault("HESTIA_SKIP_TENSOR_STALENESS_CHECK", "1")
    sys.path.insert(0, str(hestia_api))

    import torch
    import hestia.sparse_cascade as sparse_cascade
    from hestia.data_loader import load_recipes
    from hestia.data_structures import PackageIndex
    from hestia.plate_builder import PlateBuilder

    sparse_cascade.BASE_PATH = str(ROOT)

    class LocalVerdictPlateBuilder(PlateBuilder):
        def __init__(self, local_recipe_qa_db: Path, **kwargs):
            self._local_recipe_qa_db = local_recipe_qa_db
            super().__init__(**kwargs)

        def _load_verdict_exclusions(self) -> set:
            conn = sqlite3.connect(str(self._local_recipe_qa_db))
            try:
                excluded_rows = conn.execute(
                    """
                    SELECT recipe_id
                    FROM recipe_verdicts
                    WHERE verdict IN (
                      'component', 'beverage', 'not_food', 'invalid', 'derived_fat_only'
                    )
                    """
                ).fetchall()
                dessert_rows = conn.execute(
                    "SELECT recipe_id FROM recipe_verdicts WHERE verdict = 'dessert'"
                ).fetchall()
            finally:
                conn.close()

            excluded = {int(row[0]) for row in excluded_rows}
            self.dessert_recipe_ids = {int(row[0]) for row in dessert_rows}
            print(
                f"Loaded {len(excluded):,} local verdict exclusions and "
                f"{len(self.dessert_recipe_ids):,} local dessert exclusions"
            )
            return excluded

    device = torch.device(args.device)
    print("=" * 70)
    print("BUILDING LOCAL SPARSE CASCADE TENSOR CACHE")
    print("=" * 70)
    print(f"recipes_csv={recipes_csv}")
    print(f"package_db={package_db}")
    print(f"recipe_qa_db={recipe_qa_db}")
    print(f"cache_dir={cache_dir}")

    recipe_pool = load_recipes("recipes2.csv", verbose=True)

    templates_dir = hestia_api / "assets" / "plate_templates"
    plate_builder = LocalVerdictPlateBuilder(
        local_recipe_qa_db=recipe_qa_db,
        templates_dir=str(templates_dir),
    )
    plate_builder.index_recipes(recipe_pool)

    ingredient_index = sparse_cascade.IngredientIndex(device)
    ingredient_index.build_from_recipes(recipe_pool)
    print(f"IngredientIndex: {ingredient_index.num_ingredients:,} calculator-native keys")

    recipe_db = sparse_cascade.SparseRecipeDatabase(
        recipe_pool=recipe_pool,
        ingredient_index=ingredient_index,
        plate_builder=plate_builder,
        device=device,
        use_cache=False,
    )

    package_index = PackageIndex(packages_db=str(package_db))
    assert_no_default_priced_ingredients(
        ingredient_index,
        package_index,
        context="Local sparse tensor cache",
    )
    package_index.build_gpu_tensors(ingredient_index, device)

    write_cache_files(recipe_db, ingredient_index, package_index, cache_dir, torch)

    source_hashes = {
        "recipes": hash_file(recipes_csv),
        "packages_db": hash_file(package_db),
        "recipe_qa": hash_file(recipe_qa_db),
        "ingredient_meta": hash_file(ingredient_meta),
    }
    (cache_dir / "source_hashes.json").write_text(
        json.dumps(source_hashes, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    summary = {
        "recipes_csv": str(recipes_csv),
        "package_db": str(package_db),
        "ingredient_meta": str(ingredient_meta),
        "recipe_qa_db": str(recipe_qa_db),
        "tensor_cache_dir": str(cache_dir),
        "recipe_pool_rows": len(recipe_pool),
        "indexed_recipes": len(plate_builder.all_recipes),
        "tensor_recipes": int(recipe_db.num_recipes),
        "ingredient_keys": int(ingredient_index.num_ingredients),
        "package_summary": package_summary(package_db),
        "cache_files": {
            path.name: path.stat().st_size
            for path in sorted(cache_dir.glob("*.pt"))
        },
        "source_hashes": source_hashes,
    }
    summary_path = cache_dir / "tensor_cache.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
