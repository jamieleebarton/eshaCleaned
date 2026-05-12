from __future__ import annotations

import argparse
from pathlib import Path

import self_heal_common as sh


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=sh.SELF_HEAL_DIR / "esha_facts.csv")
    args = parser.parse_args()

    sh.SELF_HEAL_DIR.mkdir(parents=True, exist_ok=True)
    candidates, _category_to_codes, _family_to_codes, _idf = sh.full_map.build_candidates()
    facts = sh.build_esha_facts(candidates)
    facts.to_csv(args.output, index=False)
    summary = {
        "output": str(args.output),
        "rows": int(len(facts)),
        "heads": facts["esha_head"].value_counts().head(50).to_dict(),
        "families": facts["esha_family"].value_counts().head(50).to_dict(),
        "needs_fix": int(facts["needs_fix"].sum()),
    }
    sh.summarize_json(args.output.with_suffix(".summary.json"), summary)
    print(f"wrote {args.output} ({len(facts):,})", flush=True)


if __name__ == "__main__":
    main()
