"""Concept-key adapter for running Hestia's sparse planner on audit data.

The sparse planner is still keyed through the historical `fndds` field names.
For the concept pipeline those keys are concept strings:

    canonical_path|modifier|htc_form

This module centralizes the monkey patches needed by local smoke/battery
scripts so they do not silently fall back to the default PackageIndex.
"""
from __future__ import annotations
from htc_groups import protein_source as htc_protein_source

import json
import os
from pathlib import Path

import hestia.data_structures as ds
from htc_groups import patch_perishability_index as _patch_pi
_patch_pi(ds)
import hestia.plate_builder as pb
import hestia.sparse_cascade as sc


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CONCEPT_INDEX_PATH = DATA / "concept_index.json"
HINT_PATH = DATA / "priced_to_recipe_leaf.json"




def load_concept_index() -> dict:
    return json.loads(CONCEPT_INDEX_PATH.read_text())


def apply_concept_runtime() -> dict:
    """Patch planner runtime classes to use concept_index package data."""
    os.environ["HESTIA_BASE_PATH"] = str(ROOT)
    concept_index = load_concept_index()
    hints = json.loads(HINT_PATH.read_text()) if HINT_PATH.exists() else {}
    concept_protein = {
        key: _protein_from_path(value.get("canonical_path", ""))
        for key, value in concept_index.items()
    }

    sc._classify_fndds_code = lambda code: concept_protein.get(code, -1)
    sc._tensor_cache_dir = lambda: DATA / "tensor_cache"

    class ConceptPackageIndex(ds.PackageIndex):
        def __init__(self, packages_csv=None, packages_db=None):
            self.packages_by_fndds: dict[str, list[tuple[float, float, str]]] = {}
            self.package_db_path = CONCEPT_INDEX_PATH
            self.package_db_is_override = True
            for concept_key, concept in concept_index.items():
                ranked: list[tuple[float, float, str, str]] = []
                hint_tokens = hints.get(concept_key, [])
                for package in concept.get("packages", []):
                    cents = float(package.get("cents") or 0)
                    grams = float(package.get("grams") or 0)
                    if cents < 0 or grams <= 0:
                        continue
                    name = (package.get("name") or "").lower()
                    display = package.get("size_display") or f"{grams:.0f}g"
                    ranked.append((cents / 100.0, grams, display, name))

                def rank(pkg: tuple[float, float, str, str]) -> tuple[int, float]:
                    name = pkg[3]
                    matches = sum(1 for token in hint_tokens if token in name)
                    return (-matches, pkg[0] / pkg[1])

                ranked.sort(key=rank)
                if ranked:
                    self.packages_by_fndds[concept_key] = [
                        (price, grams, display) for price, grams, display, _name in ranked
                    ]

            n_packages = sum(len(value) for value in self.packages_by_fndds.values())
            print(
                f"ConceptPackageIndex: {len(self.packages_by_fndds):,} concepts, "
                f"{n_packages:,} packages"
            )
            self._gpu_tensors_built = False
            self._gpu_prices = None
            self._gpu_sizes = None
            self._gpu_option_prices = None
            self._gpu_option_sizes = None

        def build_gpu_tensors(self, ingredient_index, device):
            import torch

            missing = [
                concept_key
                for concept_key in ingredient_index.fpid_to_idx
                if concept_key not in self.packages_by_fndds
            ]
            if missing:
                sample = "\n  ".join(sorted(missing)[:20])
                raise RuntimeError(
                    "ConceptPackageIndex refuses to use PackageIndex fallback pricing. "
                    f"{len(missing):,} concept keys have no real package data:\n  {sample}"
                )

            num_ingredients = ingredient_index.num_ingredients
            option_count = self.MAX_PACKAGE_OPTIONS
            prices = torch.zeros(num_ingredients, dtype=torch.float32, device=device)
            sizes = torch.ones(num_ingredients, dtype=torch.float32, device=device)
            option_prices = torch.zeros(
                (num_ingredients, option_count), dtype=torch.float32, device=device
            )
            option_sizes = torch.ones(
                (num_ingredients, option_count), dtype=torch.float32, device=device
            )

            for idx in range(num_ingredients):
                concept_key = ingredient_index.idx_to_fpid[idx]
                packages = self.packages_by_fndds[concept_key]
                first_price, first_size, _first_display = packages[0]
                prices[idx] = float(first_price)
                sizes[idx] = float(first_size)
                option_prices[idx, :] = float(first_price)
                option_sizes[idx, :] = float(first_size)

                seen_sizes: set[float] = set()
                selected: list[tuple[float, float, str]] = []
                for package in packages:
                    price, grams, display = package
                    rounded_size = round(float(grams), 3)
                    if rounded_size in seen_sizes:
                        continue
                    seen_sizes.add(rounded_size)
                    selected.append(package)
                    if len(selected) >= option_count:
                        break

                for opt_idx, (price, grams, _display) in enumerate(selected):
                    option_prices[idx, opt_idx] = float(price)
                    option_sizes[idx, opt_idx] = float(grams)

            self._gpu_prices = prices
            self._gpu_sizes = sizes
            self._gpu_option_prices = option_prices
            self._gpu_option_sizes = option_sizes
            self._gpu_tensors_built = True
            print(
                f"ConceptPackageIndex: Built GPU tensors for {num_ingredients:,} "
                "ingredients using real package data only"
            )

    ds.PackageIndex = ConceptPackageIndex

    class ConceptPlateBuilder(pb.PlateBuilder):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("templates_dir", str(ROOT / "assets" / "plate_templates_v2"))
            super().__init__(*args, **kwargs)

    pb.PlateBuilder = ConceptPlateBuilder
    sc.PlateBuilder = ConceptPlateBuilder
    return concept_index
