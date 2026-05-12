from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import csv

CANONICAL_SURFACE_PATH = Path(
    "/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output/canonical_surface_normalized_with_product_proxies_CLEANED.csv"
)

FLUFF_TOKENS: frozenset[str] = frozenset({
    "premium", "gourmet", "selection", "selections", "choice", "choicest",
    "fresh-picked", "farm-fresh", "all-natural", "100%", "pure", "real",
    "authentic", "delicious", "homestyle", "traditional", "original",
    "classic", "naturally", "signature", "deluxe", "best", "finest",
    "organic",
    "great", "perfect", "ultimate", "extra", "super",
})

COMPOSITE_TRIGGERS: frozenset[str] = frozenset({
    "with", "filled", "stuffed", "topped", "over", "plus", "containing",
    "flavored", "&",
})

SEED_FLAVOR_TOKENS: frozenset[str] = frozenset({
    "vanilla", "chocolate", "strawberry", "cinnamon", "peach", "blueberry",
    "raspberry", "mint", "peppermint", "caramel", "mocha", "hazelnut",
    "pumpkin", "lemon", "orange", "cherry", "coconut", "coffee", "maple",
    "almond", "banana", "butterscotch", "toffee", "honey",
})

# Units, packaging plurals, count words, size descriptors. Treated like fluff:
# stripped from the residual so they never become a head_noun and never participate
# in lexical/embedding matching. Reason: branded product names are riddled with
# "12 OZ", "6 PACK", "FAMILY SIZE", "BAG OF" etc that carry no identity signal.
NOISE_TOKENS: frozenset[str] = frozenset({
    # weight/volume units
    "oz", "ozs", "fl", "lb", "lbs", "g", "gr", "gram", "grams", "kg",
    "ml", "l", "liter", "liters", "litre", "litres",
    # count words
    "ct", "cnt", "count", "pc", "pcs", "piece", "pieces", "pk", "pks",
    "pkg", "pkgs", "pkt", "pack", "packs", "x",
    # packaging containers (singular and plural — packaging_vocabulary from
    # canonical_surface is incomplete; these are the high-frequency ones)
    "bag", "bags", "box", "boxes", "bottle", "bottles", "can", "cans",
    "cup", "cups", "jar", "jars", "tray", "trays", "tub", "tubs",
    "carton", "cartons", "container", "containers", "case", "cases",
    "pouch", "pouches", "tin", "tins", "stick", "sticks",
    # size descriptors that carry no canonical identity
    "size", "sized", "small", "medium", "large", "mini", "jumbo",
    "family", "value", "single", "individual", "snack", "party",
    "regular",
    # filler connectives that escape normalization
    "of", "the", "a", "an", "in", "for", "made",
    # weak food modifiers flagged in AGENTS.md as non-identity-anchors
    "stems", "naturally",
})


def _split_attr_cell(cell: str) -> list[str]:
    if not cell:
        return []
    parts = cell.replace(";", ",").split(",")
    return [p.strip().lower() for p in parts if p.strip()]


@dataclass(frozen=True)
class Vocabularies:
    fluff_tokens: frozenset[str]
    noise_tokens: frozenset[str]
    composite_triggers: frozenset[str]
    flavor_vocabulary: frozenset[str]
    form_vocabulary: frozenset[str]
    state_vocabulary: frozenset[str]
    style_vocabulary: frozenset[str]
    packaging_vocabulary: frozenset[str]
    brand_vocabulary: frozenset[str]
    head_noun_vocabulary: frozenset[str]
    canonical_head_tokens: frozenset[str]  # rightmost token of every canonical_normalized

    @classmethod
    def from_canonical_surface(cls, path: Path) -> "Vocabularies":
        forms: set[str] = set()
        states: set[str] = set()
        styles: set[str] = set()
        packaging: set[str] = set()
        brands: set[str] = set()
        heads: set[str] = set()
        head_tokens: set[str] = set()
        flavors: set[str] = set(SEED_FLAVOR_TOKENS)

        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                forms.update(_split_attr_cell(row.get("form_attributes", "")))
                states.update(_split_attr_cell(row.get("state_attributes", "")))
                styles.update(_split_attr_cell(row.get("style_attributes", "")))
                packaging.update(_split_attr_cell(row.get("packaging_attributes", "")))
                if (b := (row.get("brand_candidate") or "").strip().lower()):
                    brands.add(b)
                if (h := (row.get("canonical_normalized") or "").strip().lower()):
                    heads.add(h)
                    last = h.replace(",", " ").split()
                    if last:
                        head_tokens.add(last[-1])

        return cls(
            fluff_tokens=FLUFF_TOKENS,
            noise_tokens=NOISE_TOKENS,
            composite_triggers=COMPOSITE_TRIGGERS,
            flavor_vocabulary=frozenset(flavors),
            form_vocabulary=frozenset(forms),
            state_vocabulary=frozenset(states),
            style_vocabulary=frozenset(styles),
            packaging_vocabulary=frozenset(packaging),
            brand_vocabulary=frozenset(brands),
            head_noun_vocabulary=frozenset(heads),
            canonical_head_tokens=frozenset(head_tokens),
        )

    @classmethod
    def from_canonical_surface_default(cls) -> "Vocabularies":
        return cls.from_canonical_surface(CANONICAL_SURFACE_PATH)
