from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path

from schema import ProductCandidate


ROOT = Path(__file__).resolve().parent.parent
SR28_FOOD_NUTRIENT_PATH = ROOT / "data" / "sr28_csv" / "food_nutrient.csv"

RELEVANT_NUTRIENTS = {
    "1008": "calories",
    "2047": "calories",
    "1003": "protein_g",
    "1004": "fat_g",
    "1005": "carbs_g",
    "1093": "sodium_mg",
}


@dataclass
class NutritionEstimate:
    basis: str
    grams: float
    calories: float | None
    protein_g: float | None
    fat_g: float | None
    carbs_g: float | None
    sodium_mg: float | None
    note: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _scaled(value: float | None, factor: float) -> float | None:
    if value is None:
        return None
    return round(value * factor, 2)


def scale_product_nutrition(candidate: ProductCandidate, grams: float) -> NutritionEstimate | None:
    if grams <= 0:
        return None

    values = (
        candidate.calories,
        candidate.protein_g,
        candidate.fat_g,
        candidate.carbs_g,
        candidate.sodium_mg,
    )
    if all(value is None for value in values):
        return None
    # Reject all-zero stub rows: master_products.db has spice/herb/extract rows with
    # calories=protein_g=fat_g=carbs_g=sodium_mg=0.0. These are catalog stubs, not real
    # data. Treat them as equivalent to missing nutrition so the resolver falls back to
    # SR28 or returns nutrition_unknown instead of silently reporting 0 cal.
    if all(value == 0.0 for value in values if value is not None):
        return None

    factor = grams / 100.0
    return NutritionEstimate(
        basis="product_label",
        grams=grams,
        calories=_scaled(candidate.calories, factor),
        protein_g=_scaled(candidate.protein_g, factor),
        fat_g=_scaled(candidate.fat_g, factor),
        carbs_g=_scaled(candidate.carbs_g, factor),
        sodium_mg=_scaled(candidate.sodium_mg, factor),
        note="scaled from product nutrient columns stored per 100 g / 100 ml",
    )


class Sr28NutrientLookup:
    def __init__(self, path: Path = SR28_FOOD_NUTRIENT_PATH) -> None:
        self.path = Path(path)
        self.by_fdc_id = self._load()

    def _load(self) -> dict[str, dict[str, float]]:
        by_fdc_id: dict[str, dict[str, float]] = {}
        with self.path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                nutrient_id = row["nutrient_id"]
                field = RELEVANT_NUTRIENTS.get(nutrient_id)
                if not field:
                    continue
                fdc_id = row["fdc_id"]
                amount_raw = row["amount"]
                if not amount_raw:
                    continue
                record = by_fdc_id.setdefault(fdc_id, {})
                if field == "calories" and "calories" in record and nutrient_id == "2047":
                    continue
                record[field] = float(amount_raw)
        return by_fdc_id

    def scale(self, fdc_id: str, grams: float, basis: str) -> NutritionEstimate | None:
        nutrients = self.by_fdc_id.get(str(fdc_id))
        if not nutrients or grams <= 0:
            return None
        factor = grams / 100.0
        return NutritionEstimate(
            basis=basis,
            grams=grams,
            calories=_scaled(nutrients.get("calories"), factor),
            protein_g=_scaled(nutrients.get("protein_g"), factor),
            fat_g=_scaled(nutrients.get("fat_g"), factor),
            carbs_g=_scaled(nutrients.get("carbs_g"), factor),
            sodium_mg=_scaled(nutrients.get("sodium_mg"), factor),
        )


def sum_estimates(estimates: list[NutritionEstimate]) -> NutritionEstimate:
    def total(field: str) -> float | None:
        values = [getattr(item, field) for item in estimates if getattr(item, field) is not None]
        if not values:
            return None
        return round(sum(values), 2)

    grams = round(sum(item.grams for item in estimates), 2)
    return NutritionEstimate(
        basis="aggregate",
        grams=grams,
        calories=total("calories"),
        protein_g=total("protein_g"),
        fat_g=total("fat_g"),
        carbs_g=total("carbs_g"),
        sodium_mg=total("sodium_mg"),
    )
