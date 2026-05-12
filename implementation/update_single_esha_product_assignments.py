from __future__ import annotations

import argparse
import json

import build_product_esha_lookup as lookup


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh one ESHA code's reviewed product assignments from its pack")
    parser.add_argument("--code", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--source", choices=("auto", "pack", "direct"), default="auto")
    args = parser.parse_args()

    code = str(args.code).strip()
    if not code:
        raise SystemExit("missing ESHA code")

    existing = [row for row in lookup.read_assignments() if row.get("esha_code") != code]
    fresh = lookup.collect_assignment_rows(codes={code}, limit_per_code=args.limit, source=args.source)
    merged_summary = lookup.write_lookup_artifacts(existing + fresh)
    merged_summary["esha_code"] = code
    merged_summary["refreshed_assignment_rows"] = len(fresh)
    merged_summary["single_code_lookup_summary"] = {
        "codes_requested": [code],
        "assignment_rows": len(fresh),
        "source": args.source,
    }
    print(json.dumps(merged_summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
