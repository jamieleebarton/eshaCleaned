#!/usr/bin/env python3
"""
Build tensor cache from corrected recipes CSV.

This script loads recipes2.csv, indexes them through PlateBuilder (which applies
template category matching), and builds + saves the tensor cache that the
SparseRecipeDatabase loads at startup.

Also recalculates recipe costs from the package database to fix stale/wrong cost data.

Usage:
    python build_tensor_cache.py
"""

import sys
import json
import sqlite3
import torch
import numpy as np
from pathlib import Path
from typing import Dict, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from hestia.data_loader import load_recipes
from hestia.plate_builder import PlateBuilder
from hestia.sparse_cascade import (
    SparseRecipeDatabase, IngredientIndex,
    PROTEIN_SOURCE_CODES, MAX_NNZ, is_fixed_portion_recipe,
)


def build_price_cache(db_path: Path) -> Dict[str, float]:
    """
    Build a cache of best price per gram for each FNDDS code.
    Returns dict: fndds_code -> $/gram
    """
    print("\nLoading prices from food_packages_final.db...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT fndds_code, package_weight_grams, 
               CASE WHEN walmart_price_cents > 0 THEN walmart_price_cents 
                    ELSE kroger_price_cents END as price_cents
        FROM packages 
        WHERE (walmart_price_cents > 0 OR kroger_price_cents > 0)
        ORDER BY fndds_code, price_cents / package_weight_grams ASC
    ''')
    
    # Keep only the cheapest option per FNDDS code
    price_per_gram = {}
    for fndds_code, weight_g, price_cents in cursor.fetchall():
        if weight_g and price_cents and weight_g > 0:
            ppg = price_cents / 100.0 / weight_g
            if fndds_code not in price_per_gram or ppg < price_per_gram[fndds_code]:
                price_per_gram[fndds_code] = ppg
    
    conn.close()
    print(f"  Loaded prices for {len(price_per_gram):,} ingredients")
    return price_per_gram


def recalculate_recipe_costs(recipe_pool: list, price_cache: Dict[str, float]) -> None:
    """
    Recalculate costs for all recipes using current package prices.
    Modifies recipe dicts in place.
    """
    print("\nRecalculating recipe costs...")
    
    updated = 0
    unchanged = 0
    zero_to_real = 0
    
    for recipe in recipe_pool:
        # Handle both dict and object formats
        if isinstance(recipe, dict):
            old_cost = float(recipe.get('total_estimated_cost', 0.0) or 0.0)
            ingredient_needs = recipe.get('ingredient_needs', {})
            servings = max(int(recipe.get('servings_produced', 1) or 1), 1)
            
            # Calculate new cost from ingredients
            new_cost = 0.0
            for fndds_code, grams in ingredient_needs.items():
                ppg = price_cache.get(fndds_code)
                if ppg:
                    new_cost += ppg * grams
            
            # Update the recipe dict
            recipe['total_estimated_cost'] = round(new_cost, 2)
            recipe['cost_per_serving'] = round(new_cost / servings, 2)
        else:
            # Object format (Recipe dataclass)
            old_cost = getattr(recipe, 'total_estimated_cost', 0.0) or 0.0
            
            new_cost = 0.0
            if hasattr(recipe, 'ingredient_needs') and recipe.ingredient_needs:
                for fndds_code, grams in recipe.ingredient_needs.items():
                    ppg = price_cache.get(fndds_code)
                    if ppg:
                        new_cost += ppg * grams
            
            recipe.total_estimated_cost = round(new_cost, 2)
            servings = max(getattr(recipe, 'servings_produced', 1) or 1, 1)
            recipe.cost_per_serving = round(new_cost / servings, 2)
        
        if old_cost == 0 and new_cost > 0:
            zero_to_real += 1
        elif abs(new_cost - old_cost) > 0.01:
            updated += 1
        else:
            unchanged += 1
    
    print(f"  Updated: {updated:,} recipes")
    print(f"  Fixed $0 -> actual cost: {zero_to_real:,} recipes")
    print(f"  Unchanged: {unchanged:,} recipes")


def build_and_save_cache():
    device = torch.device("cpu")  # Build on CPU, cache is device-agnostic

    print("=" * 60)
    print("Building tensor cache from corrected recipes2.csv")
    print("=" * 60)

    # Step 1: Load recipes
    recipe_pool = load_recipes("recipes2.csv", verbose=True)
    print(f"Loaded {len(recipe_pool):,} recipes from CSV")
    
    # Step 1.5: Recalculate costs from package database
    packages_db = Path("data/food_packages_final.db")
    if packages_db.exists():
        price_cache = build_price_cache(packages_db)
        recalculate_recipe_costs(recipe_pool, price_cache)
    else:
        print(f"\nWARNING: {packages_db} not found, using stale costs from CSV")

    # Step 2: Build PlateBuilder and index recipes
    print("\nIndexing recipes through PlateBuilder...")
    plate_builder = PlateBuilder()
    plate_builder.index_recipes(recipe_pool)

    # Step 3: Build IngredientIndex
    print("\nBuilding IngredientIndex...")
    ingredient_index = IngredientIndex(device)
    ingredient_index.build_from_recipes(recipe_pool)
    print(f"  {ingredient_index.num_ingredients:,} unique ingredients")

    # Step 4: Build SparseRecipeDatabase (bypasses cache, builds from scratch)
    print("\nBuilding SparseRecipeDatabase from scratch (no cache)...")
    recipe_db = SparseRecipeDatabase(
        recipe_pool, ingredient_index, plate_builder, device,
        use_cache=False
    )
    print(f"  {recipe_db.num_recipes:,} recipes in database")

    # Step 5: Save tensor cache
    cache_dir = Path("data/tensor_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Save main recipe database tensors
    cache_path = cache_dir / "recipe_db_tensors.pt"
    print(f"\nSaving recipe database cache to {cache_path}...")

    cache_data = {
        'recipe_ids': recipe_db.recipe_ids.cpu(),
        'ingredient_indices': recipe_db.ingredient_indices.cpu(),
        'ingredient_amounts': recipe_db.ingredient_amounts.cpu(),
        'nutrition': recipe_db.nutrition.cpu(),
        'food_groups': recipe_db.food_groups.cpu(),
        'servings': recipe_db.servings.cpu(),
        'nnz': recipe_db.nnz.cpu(),
        'protein_source': recipe_db.protein_source.cpu(),
        'ingredient_indices_flat': recipe_db.ingredient_indices_flat.cpu(),
        'packed_metadata': recipe_db.packed_metadata.cpu(),
        'gpu_recipe_id_to_idx': recipe_db.gpu_recipe_id_to_idx.cpu(),
        'gpu_recipe_to_template': recipe_db.gpu_recipe_to_template.cpu(),
        'gpu_recipe_is_one_dish': recipe_db.gpu_recipe_is_one_dish.cpu(),
        'gpu_side_compat': recipe_db.gpu_side_compat.cpu(),
        'is_fixed_portion': recipe_db.is_fixed_portion.cpu(),
        'sodium_per_serving': recipe_db.sodium_per_serving.cpu(),
        'recipe_names': recipe_db.names,
    }

    torch.save(cache_data, cache_path)
    cache_size = cache_path.stat().st_size
    print(f"  Saved: {cache_size / 1024 / 1024:.1f} MB")

    # Save ingredient index
    ing_cache_path = cache_dir / "ingredient_index.pt"
    print(f"Saving ingredient index to {ing_cache_path}...")
    torch.save({
        'fpid_to_idx': ingredient_index.fpid_to_idx,
        'idx_to_fpid': ingredient_index.idx_to_fpid,
        'num_ingredients': ingredient_index.num_ingredients,
    }, ing_cache_path)

    # Save template structures (meal_main_indices, template_to_sides, etc.)
    template_cache_path = cache_dir / "template_tensors.pt"
    print(f"Saving template tensors to {template_cache_path}...")
    try:
        template_data = {
            'meal_main_indices': {
                k: v.cpu() for k, v in recipe_db.meal_main_indices.items()
            },
            'meal_side_indices': {
                k: v.cpu() for k, v in recipe_db.meal_side_indices.items()
            },
            'template_to_sides': {
                k: v.cpu() for k, v in recipe_db.template_to_sides.items()
            },
            'template_to_side_pool_ids': {
                k: v.cpu() for k, v in recipe_db.template_to_side_pool_ids.items()
            },
        }
        torch.save(template_data, template_cache_path)
        template_size = template_cache_path.stat().st_size
        print(f"  Saved: {template_size / 1024 / 1024:.1f} MB")
    except Exception as e:
        print(f"  WARNING: Could not save template tensors: {e}")

    # Save package index if it exists
    pkg_cache_path = cache_dir / "package_index.pt"
    # Package index is built separately in server.py

    print("\n" + "=" * 60)
    print("Cache build complete!")
    print(f"  Recipes: {recipe_db.num_recipes:,}")
    print(f"  Ingredients: {ingredient_index.num_ingredients:,}")
    print(f"  Cache files in: {cache_dir}")
    print("=" * 60)


if __name__ == "__main__":
    build_and_save_cache()
