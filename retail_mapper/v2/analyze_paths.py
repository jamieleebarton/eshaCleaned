"""
Analyze retail_leaf_path from full_corpus_audit.csv
Try to separate identity from flavor/variant/claim modifiers.
"""
import csv
from collections import Counter, defaultdict
import re

CSV_PATH = "/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2/full_corpus_audit.csv"

# Keywords that indicate the node is a modifier/claim/flavor, not identity
MODIFIER_KEYWORDS = {
    # Claims
    "organic", "gluten free", "grain free", "vegan", "non gmo", "probiotic",
    "fortified", "enriched", "light", "low fat", "fat free", "reduced fat",
    "no sugar added", "sugar free", "reduced sugar", "unsweetened", "sweetened",
    "lightly sweetened", "high protein", "low carb", "low sodium", "reduced sodium",
    "whole grain", "whole wheat", "multi grain", "sprouted wheat", "ancient grain",
    "natural", "all natural", "local", "fresh", "shelf stable",
    # Form / cut
    "sliced", "split", "mini", "jumbo", "texas", "thin", "thick",
    # Variants that are usually attributes
    "plain", "original", "classic", "traditional", "homestyle",
    # Common flavor words (will catch most)
}

FLAVOR_PATTERNS = [
    r"chocolate", r"vanilla", r"strawberry", r"blueberry", r"raspberry",
    r"blackberry", r"cherry", r"peach", r"mango", r"banana", r"apple",
    r"cinnamon", r"caramel", r"butter pecan", r"cookies and cream",
    r"mint", r"pumpkin spice", r"egg nog", r"coffee", r"mocha",
    r"espresso", r"honey", r"maple", r"lemon", r"lime", r"orange",
    r"grape", r"barbecue", r"bbq", r"ranch", r"sour cream", r"cheddar",
    r"jalapeno", r"salt and vinegar", r"sea salt", r"bacon", r"buffalo",
    r"garlic", r"onion", r"cheese", r"white cheddar", r"aged white cheddar",
    r"smoked", r"kettle", r"wavy", r"multigrain", r"everything",
    r"asiago", r"brioche", r"corn", r"potato", r"sweet potato",
    r"coconut", r"almond", r"pecan", r"walnut", r"peanut butter",
    r"cocoa", r"pomegranate", r"acai", r"green tea", r"matcha",
    r"chai", r"horchata", r"spice", r"pumpkin", r"carrot", r"cranberry",
    r"raisin", r"sugar", r"frosted", r"glazed", r"powdered",
    r"cream cheese", r"butter", r"garlic bread", r"french",
    r"italian", r"sourdough", r"rye", r"pumpernickel", r"oatmeal",
    r"whole milk", r"2 percent", r"1 percent", r"skim", r"nonfat",
    r"fat free", r"low fat", r"reduced fat", r"whole",
]

def classify_nodes(path: str):
    """Split a retail_leaf_path into identity_nodes and modifier_nodes."""
    nodes = [n.strip() for n in path.split(">")]
    if not nodes:
        return [], []

    identity_nodes = []
    modifier_nodes = []

    # Simple heuristic: walk from the end. If a node looks like a modifier,
    # it and everything after it stays in modifiers. The rest is identity.
    # But some modifiers can appear in the middle (e.g., "Whole Grain" before "Sliced")
    # So we do: strip trailing modifiers, then re-check.

    remaining = list(nodes)
    while remaining:
        last = remaining[-1].lower()
        is_mod = False
        # Check exact modifier matches
        if last in MODIFIER_KEYWORDS:
            is_mod = True
        else:
            # Check flavor patterns
            for pat in FLAVOR_PATTERNS:
                if re.search(pat, last):
                    is_mod = True
                    break
        if is_mod and len(remaining) > 1:
            modifier_nodes.insert(0, remaining.pop())
        else:
            break

    identity_nodes = remaining
    return identity_nodes, modifier_nodes


def main():
    path_counts = Counter()
    identity_counts = Counter()
    modifier_counts = Counter()
    depth_distribution = Counter()
    identity_depth_distribution = Counter()
    modifier_depth_distribution = Counter()
    edge_cases = []

    # For specific categories the user cares about
    milk_identities = Counter()
    bagel_identities = Counter()
    chip_identities = Counter()
    ice_cream_identities = Counter()

    row_count = 0
    with open(CSV_PATH, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row_count += 1
            path = row.get("retail_leaf_path", "").strip()
            if not path:
                continue
            path_counts[path] += 1
            nodes = [n.strip() for n in path.split(">")]
            depth_distribution[len(nodes)] += 1

            identity, modifiers = classify_nodes(path)
            identity_str = " > ".join(identity)
            modifier_str = " > ".join(modifiers)

            identity_counts[identity_str] += 1
            identity_depth_distribution[len(identity)] += 1
            modifier_depth_distribution[len(modifiers)] += 1
            for m in modifiers:
                modifier_counts[m] += 1

            # Categorize examples
            lower_path = path.lower()
            if "milk" in lower_path and ("plant milk" in lower_path or "dairy > milk" in lower_path or lower_path.startswith("dairy > milk") or lower_path.startswith("beverage > plant milk")):
                milk_identities[identity_str] += 1
            if "bagel" in lower_path:
                bagel_identities[identity_str] += 1
            if "potato chip" in lower_path or ("chip" in lower_path and "snack > chip" in lower_path):
                chip_identities[identity_str] += 1
            if "ice cream" in lower_path:
                ice_cream_identities[identity_str] += 1

            # Collect edge cases: very deep modifiers, empty identity, etc.
            if len(identity) == 0:
                edge_cases.append((path, "empty identity"))
            elif len(modifiers) >= 4:
                edge_cases.append((path, f"{len(modifiers)} modifiers"))
            elif len(identity) >= 6:
                edge_cases.append((path, f"{len(identity)} identity nodes"))

    print("=" * 70)
    print(f"TOTAL ROWS PROCESSED: {row_count:,}")
    print(f"UNIQUE retail_leaf_path VALUES: {len(path_counts):,}")
    print()

    print("PATH DEPTH DISTRIBUTION")
    print("-" * 40)
    for depth in sorted(depth_distribution):
        pct = depth_distribution[depth] / row_count * 100
        print(f"  {depth} nodes: {depth_distribution[depth]:>7,} ({pct:5.1f}%)")
    print()

    print("IDENTITY DEPTH DISTRIBUTION (after stripping modifiers)")
    print("-" * 40)
    for depth in sorted(identity_depth_distribution):
        pct = identity_depth_distribution[depth] / row_count * 100
        print(f"  {depth} nodes: {identity_depth_distribution[depth]:>7,} ({pct:5.1f}%)")
    print()

    print("MODIFIER DEPTH DISTRIBUTION")
    print("-" * 40)
    for depth in sorted(modifier_depth_distribution):
        pct = modifier_depth_distribution[depth] / row_count * 100
        print(f"  {depth} mods: {modifier_depth_distribution[depth]:>7,} ({pct:5.1f}%)")
    print()

    print("TOP 20 UNIQUE FULL PATHS")
    print("-" * 40)
    for path, count in path_counts.most_common(20):
        print(f"  {count:>6,} | {path}")
    print()

    print("TOP 20 IDENTITY STRINGS (after modifier stripping)")
    print("-" * 40)
    for ident, count in identity_counts.most_common(20):
        print(f"  {count:>6,} | {ident}")
    print()

    print("TOP 20 MODIFIER NODES")
    print("-" * 40)
    for mod, count in modifier_counts.most_common(20):
        print(f"  {count:>6,} | {mod}")
    print()

    print("=" * 70)
    print("CATEGORY BREAKDOWNS")
    print("=" * 70)

    print("\nMILK IDENTITIES (top 15)")
    print("-" * 40)
    for ident, count in milk_identities.most_common(15):
        print(f"  {count:>6,} | {ident}")

    print("\nBAGEL IDENTITIES (top 15)")
    print("-" * 40)
    for ident, count in bagel_identities.most_common(15):
        print(f"  {count:>6,} | {ident}")

    print("\nPOTATO CHIP IDENTITIES (top 15)")
    print("-" * 40)
    for ident, count in chip_identities.most_common(15):
        print(f"  {count:>6,} | {ident}")

    print("\nICE CREAM IDENTITIES (top 15)")
    print("-" * 40)
    for ident, count in ice_cream_identities.most_common(15):
        print(f"  {count:>6,} | {ident}")

    print()
    print("=" * 70)
    print("EDGE CASES (sample of 30)")
    print("=" * 70)
    for path, reason in edge_cases[:30]:
        identity, modifiers = classify_nodes(path)
        print(f"  [{reason}]")
        print(f"    PATH:     {path}")
        print(f"    IDENTITY: {' > '.join(identity)}")
        print(f"    MODS:     {' > '.join(modifiers)}")
        print()


if __name__ == "__main__":
    main()
