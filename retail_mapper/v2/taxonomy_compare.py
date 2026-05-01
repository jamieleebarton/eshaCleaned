#!/usr/bin/env python3
"""Side-by-side per-case comparison across multiple rescore JSONs.

Designed for the iterative test loop:

    python3 retail_mapper/v2/taxonomy_compare.py \
        --pair "DeepSeek raw=retail_mapper/v2/llm_taxonomy_diabolical_deepseek.rescore_baseline.json" \
        --pair "DeepSeek+norm=retail_mapper/v2/llm_taxonomy_diabolical_deepseek.rescore_normalized.json" \
        --pair "Qwen raw=retail_mapper/v2/llm_taxonomy_diabolical_qwen235.rescore_baseline.json" \
        --pair "Qwen+norm=retail_mapper/v2/llm_taxonomy_diabolical_qwen235.rescore_normalized.json" \
        --out retail_mapper/v2/taxonomy_compare.md

Each rescore JSON is what `llm_taxonomy_cleanup.py --rescore` writes. The
comparator picks the union of cases across files, prints a column-per-source
PASS/FAIL grid, and lists each case's remaining error fingerprints (so you can
diff how a tweak changes the failure modes).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_rescore(path: Path) -> dict[str, dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(c.get("case", "")): c for c in data.get("cases", []) if c.get("case")}


def collect_case_order(loaded: list[tuple[str, dict[str, dict[str, object]]]]) -> list[str]:
    order: list[str] = []
    seen: set[str] = set()
    for _, by_case in loaded:
        for name in by_case:
            if name not in seen:
                seen.add(name)
                order.append(name)
    return order


def status_token(case: dict[str, object] | None) -> str:
    if not case:
        return "    -"
    core = "P" if case.get("core_passed") else "F"
    exact = "P" if case.get("exact_passed") else "F"
    return f"{core}/{exact}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Per-case side-by-side rescore comparison")
    parser.add_argument(
        "--pair",
        action="append",
        default=[],
        required=True,
        help="LABEL=PATH pair. Repeat the flag once per rescore JSON.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional markdown output path. If omitted, prints to stdout.",
    )
    args = parser.parse_args()

    labels: list[str] = []
    files: list[Path] = []
    for pair in args.pair:
        if "=" not in pair:
            print(f"ignoring malformed --pair (need LABEL=PATH): {pair!r}", file=sys.stderr)
            continue
        lbl, _, raw_path = pair.partition("=")
        labels.append(lbl.strip())
        files.append(Path(raw_path.strip()))

    loaded: list[tuple[str, dict[str, dict[str, object]]]] = []
    totals: list[dict[str, int]] = []
    for label, path in zip(labels, files):
        if not path.exists():
            print(f"warning: {path} not found", file=sys.stderr)
            continue
        by_case = load_rescore(path)
        loaded.append((label, by_case))
        totals.append({
            "core_pass": sum(1 for c in by_case.values() if c.get("core_passed")),
            "exact_pass": sum(1 for c in by_case.values() if c.get("exact_passed")),
            "total": len(by_case),
        })

    if not loaded:
        print("no rescore files loaded", file=sys.stderr)
        raise SystemExit(1)

    case_order = collect_case_order(loaded)

    out_lines: list[str] = []
    out_lines.append("# Taxonomy rescore comparison")
    out_lines.append("")
    out_lines.append("Cell format: `core/exact` (P=pass, F=fail).")
    out_lines.append("")
    # Header
    header = ["case"] + [lbl for lbl, _ in loaded]
    sep = ["---"] + ["---"] * len(loaded)
    out_lines.append("| " + " | ".join(header) + " |")
    out_lines.append("| " + " | ".join(sep) + " |")
    for name in case_order:
        cells = [name]
        for _, by_case in loaded:
            cells.append(status_token(by_case.get(name)))
        out_lines.append("| " + " | ".join(cells) + " |")

    out_lines.append("")
    out_lines.append("## Totals")
    out_lines.append("")
    out_lines.append("| label | core | exact | total |")
    out_lines.append("|-------|------|-------|-------|")
    for (lbl, _), tot in zip(loaded, totals):
        out_lines.append(
            f"| {lbl} | {tot['core_pass']}/{tot['total']} | {tot['exact_pass']}/{tot['total']} | {tot['total']} |"
        )

    out_lines.append("")
    out_lines.append("## Remaining failures by source")
    for lbl, by_case in loaded:
        out_lines.append("")
        out_lines.append(f"### {lbl}")
        any_fail = False
        for name in case_order:
            c = by_case.get(name)
            if not c:
                continue
            if c.get("core_passed") and c.get("exact_passed"):
                continue
            any_fail = True
            errs = c.get("core_errors") if not c.get("core_passed") else c.get("exact_errors")
            errs = errs or []
            short_errs = [str(e) for e in errs][:8]
            joined = "; ".join(short_errs) if short_errs else "—"
            out_lines.append(f"- `{name}` {('core' if not c.get('core_passed') else 'exact')}: {joined}")
        if not any_fail:
            out_lines.append("(all passing)")

    text = "\n".join(out_lines) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        # Always also dump headline numbers to stdout
        for (lbl, _), tot in zip(loaded, totals):
            print(f"{lbl:30s}  core {tot['core_pass']:>3d}/{tot['total']}  exact {tot['exact_pass']:>3d}/{tot['total']}")
        print(f"wrote: {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
