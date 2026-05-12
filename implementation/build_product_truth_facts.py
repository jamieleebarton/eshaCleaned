from __future__ import annotations

import argparse
from pathlib import Path

import self_heal_common as sh


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-map", type=Path, default=sh.DEFAULT_INPUT_MAP)
    parser.add_argument("--output", type=Path, default=sh.SELF_HEAL_DIR / "product_facts.csv")
    args = parser.parse_args()

    sh.SELF_HEAL_DIR.mkdir(parents=True, exist_ok=True)
    current = sh.ingredient_clusters.load_current_map(args.input_map) if args.input_map.exists() else None
    facts = sh.build_product_facts(current)
    facts.to_csv(args.output, index=False)
    summary = {
        "input_map": str(args.input_map),
        "output": str(args.output),
        "rows": int(len(facts)),
        "category_lanes": facts["category_lane"].value_counts().head(50).to_dict(),
        "product_forms": facts["product_form"].value_counts().head(50).to_dict(),
        "product_roles": facts["product_role"].value_counts().to_dict(),
    }
    sh.summarize_json(args.output.with_suffix(".summary.json"), summary)
    print(f"wrote {args.output} ({len(facts):,})", flush=True)


if __name__ == "__main__":
    main()
