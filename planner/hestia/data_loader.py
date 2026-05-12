"""
Safe data loading utilities for the Hydra meal planner.

IMPORTANT: Do NOT use pandas .to_dict('records') on large DataFrames!
           It causes segfaults with certain pandas/numpy version combinations
           on DataFrames with 500k+ rows.

This module provides safe alternatives that use numpy arrays internally.

Usage:
    from hestia.data_loader import load_recipes, load_recipes_df

    # Get list of dicts (safe alternative to df.to_dict('records'))
    recipe_pool = load_recipes()

    # Get DataFrame if you need it
    df, recipe_pool = load_recipes_df()
"""

import os
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd
import numpy as np

# Find base path
def _get_base_path() -> str:
    """Get the base path to the hydra project."""
    # Check common locations
    if Path("/workspace/data/recipes2.csv").exists():
        return "/workspace"
    if Path("/workspace/data/recipes.csv").exists():
        return "/workspace"

    # Try relative to this file
    this_file = Path(__file__).resolve()
    parent = this_file.parent.parent  # hydra/multi2 -> hydra
    if (parent / "data" / "recipes2.csv").exists():
        return str(parent)
    if (parent / "data" / "recipes.csv").exists():
        return str(parent)

    # Try environment variable
    if os.environ.get("HYDRA_BASE_PATH"):
        return os.environ["HYDRA_BASE_PATH"]

    raise FileNotFoundError(
        "Could not find recipes.csv or recipes2.csv. "
        "Set HYDRA_BASE_PATH environment variable or ensure data/ folder exists."
    )


BASE_PATH = _get_base_path()


def _resolve_recipe_csv_path(csv_name: str, base_path: str) -> str:
    override = os.environ.get("HESTIA_RECIPES_CSV")
    if override and csv_name == "recipes2.csv":
        return str(Path(override).expanduser())
    candidate = Path(csv_name).expanduser()
    if candidate.is_absolute():
        return str(candidate)
    return os.path.join(base_path, "data", csv_name)


def df_to_records_safe(df: pd.DataFrame, chunk_size: int = 5000) -> List[Dict[str, Any]]:
    """
    Convert DataFrame to list of dicts WITHOUT using .to_dict('records').

    This is the SAFE alternative to df.to_dict('records') which causes
    segmentation faults on large DataFrames (500k+ rows) with certain
    pandas/numpy version combinations.

    Uses pure Python dict comprehension (no pandas methods that segfault).

    Args:
        df: pandas DataFrame
        chunk_size: Not used but kept for API compatibility

    Returns:
        List of dictionaries, one per row
    """
    # Convert to list of dicts using pure Python
    # This avoids all pandas internal methods that can segfault
    cols = list(df.columns)
    n_rows = len(df)

    # Reset index to ensure sequential integer index
    df = df.reset_index(drop=True)

    records = []
    for i in range(n_rows):
        row_dict = {}
        for col in cols:
            try:
                val = df.at[i, col]  # Use .at[] for scalar access (faster than .loc)
            except Exception:
                val = None

            # Convert to native Python types
            if val is None or (isinstance(val, float) and np.isnan(val)):
                row_dict[col] = None
            elif hasattr(val, 'item'):
                # numpy scalar - convert to Python
                row_dict[col] = val.item()
            else:
                row_dict[col] = val

        records.append(row_dict)

        # Progress
        if n_rows > 100000 and (i + 1) % 100000 == 0:
            print(f"  Converted {i + 1:,}/{n_rows:,} rows...")

    return records


def load_recipes(
    csv_name: str = "recipes2.csv",
    base_path: Optional[str] = None,
    verbose: bool = True,
) -> List[Dict[str, Any]]:
    """
    Load recipes from CSV file safely.

    Uses Python's csv module directly to avoid pandas segfaults on large files.

    Args:
        csv_name: Name of CSV file in data/ folder (default: "recipes2.csv")
        base_path: Base path to hydra project (auto-detected if None)
        verbose: Print progress messages

    Returns:
        List of recipe dictionaries

    Example:
        from hestia.data_loader import load_recipes

        recipe_pool = load_recipes()  # Uses recipes2.csv
        recipe_pool = load_recipes("recipes.csv")  # Uses older file
    """
    import csv

    if base_path is None:
        base_path = BASE_PATH

    csv_path = _resolve_recipe_csv_path(csv_name, base_path)

    if not os.path.exists(csv_path):
        # Try alternate name
        alt_name = "recipes.csv" if csv_name == "recipes2.csv" else "recipes2.csv"
        alt_path = _resolve_recipe_csv_path(alt_name, base_path)
        if os.path.exists(alt_path):
            csv_path = alt_path
            csv_name = alt_name
        else:
            raise FileNotFoundError(f"Recipe file not found: {csv_path}")

    if verbose:
        print(f"Loading recipes from {csv_path} (pure Python)...")

    recipe_pool = []

    # Define numeric columns that should be converted from string
    NUMERIC_COLS = {
        'recipeNum', 'servings', 'calories', 'protein', 'carbs', 'fat',
        'saturatedFat', 'fiber', 'sodium', 'cost', 'totalMass',
        'ndb_id', 'price', 'grams', 'cookingMinutes', 'prepMinutes',
        # Food group columns (with both naming conventions)
        'food_groups.vegetables_g', 'food_groups.fruits_g', 'food_groups.grains_g',
        'food_groups.dairy_g', 'food_groups.protein_g',
        'vegetables_g', 'fruits_g', 'grains_g', 'dairy_g', 'protein_foods_g',
        'food_groups.fats_g', 'food_groups.fats_pct',
        'food_groups.other_g', 'food_groups.other_pct',
        'fats_g', 'other_g',
    }

    with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)

        row_count = 0
        for row in reader:
            # Convert numeric fields - create new dict directly
            new_row = dict(row)  # Copy the row

            for col_name in NUMERIC_COLS:
                if col_name in new_row:
                    val = new_row[col_name]
                    if val == '' or val is None:
                        new_row[col_name] = None
                    else:
                        try:
                            if '.' in str(val):
                                new_row[col_name] = float(val)
                            else:
                                new_row[col_name] = int(val)
                        except (ValueError, TypeError):
                            pass  # Keep original value

            # Handle empty strings -> None for all columns
            for k in list(new_row.keys()):
                if new_row[k] == '':
                    new_row[k] = None

            recipe_pool.append(new_row)
            row_count += 1

            # Progress
            if verbose and row_count % 100000 == 0:
                print(f"  Loaded {row_count:,} recipes...")

    if verbose:
        print(f"Loaded {len(recipe_pool):,} recipes")

    return recipe_pool


def load_recipes_df(
    csv_name: str = "recipes2.csv",
    base_path: Optional[str] = None,
    verbose: bool = True,
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """
    Load recipes and return both DataFrame and list of dicts.

    Useful when you need the DataFrame for analysis but also need
    the dict format for the planner.

    Args:
        csv_name: Name of CSV file in data/ folder
        base_path: Base path to hydra project
        verbose: Print progress messages

    Returns:
        Tuple of (DataFrame, list of dicts)

    Example:
        df, recipe_pool = load_recipes_df()
    """
    if base_path is None:
        base_path = BASE_PATH

    csv_path = _resolve_recipe_csv_path(csv_name, base_path)

    if not os.path.exists(csv_path):
        alt_name = "recipes.csv" if csv_name == "recipes2.csv" else "recipes2.csv"
        alt_path = _resolve_recipe_csv_path(alt_name, base_path)
        if os.path.exists(alt_path):
            csv_path = alt_path
        else:
            raise FileNotFoundError(f"Recipe file not found: {csv_path}")

    if verbose:
        print(f"Loading recipes from {csv_path}...")

    df = pd.read_csv(csv_path)

    if verbose:
        print(f"Converting {len(df)} recipes (safe method)...")

    recipe_pool = df_to_records_safe(df)

    if verbose:
        print(f"Loaded {len(recipe_pool)} recipes")

    return df, recipe_pool


def build_recipe_name_lookup(recipe_pool: List[Dict[str, Any]]) -> Dict[int, str]:
    """
    Build a recipe ID -> name lookup dictionary.

    Args:
        recipe_pool: List of recipe dictionaries

    Returns:
        Dict mapping recipeNum to recipeName
    """
    return {
        int(r['recipeNum']): r['recipeName']
        for r in recipe_pool
        if r.get('recipeNum') is not None
    }


# Convenience: Pre-load when module is imported
# (Only in interactive mode, skip during import)
_cached_recipes: Optional[List[Dict[str, Any]]] = None


def get_recipes(force_reload: bool = False) -> List[Dict[str, Any]]:
    """
    Get cached recipes or load them.

    This is more efficient when multiple scripts need the same data.

    Args:
        force_reload: Force reload from disk even if cached

    Returns:
        List of recipe dictionaries
    """
    global _cached_recipes

    if _cached_recipes is None or force_reload:
        _cached_recipes = load_recipes(verbose=False)

    return _cached_recipes


if __name__ == "__main__":
    # Quick test
    print("Testing safe data loader...")
    recipes = load_recipes()
    print(f"Loaded {len(recipes)} recipes")
    print(f"First recipe: {recipes[0].get('recipeName', 'N/A')}")
    print(f"Last recipe: {recipes[-1].get('recipeName', 'N/A')}")
