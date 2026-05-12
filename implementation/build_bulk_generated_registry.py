"""Land every pack the sweep classified as `patch_built`.

Reads ``pack_builder_sweep.csv``, re-runs the deterministic contract builder
for each pack the sweep said would land, and writes two cumulative artifacts:

- ``implementation/esha_contracts/reviewed_nebius_generated.py``
- ``implementation/output/nebius_contract_decisions/reviewed_nebius_generated_specs.json``

No LLM calls. Idempotent: overwrites both files every run. Skips any pack
whose spec no longer builds (e.g. because the pack MD changed between runs).
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPL = ROOT / "implementation"
if str(IMPL) not in sys.path:
    sys.path.insert(0, str(IMPL))

from nebius_contract_patch_builder import (  # noqa: E402
    MODULE_PATH,
    REGISTRY_PATH,
    auto_relax_spec,
    extract_spec,
    render_module,
    render_registry,
    validate_spec,
)
from collections import Counter as _Counter  # noqa: E402

from run_pack_builder_sweep import (  # noqa: E402
    INDEX_CSV,
    STOP_DESCRIPTION_TOKENS,
    STOP_INGREDIENT_TOKENS,
    apply_opposite_excludes,
    enforce_esha_attributes,
    esha_signal_filter,
    normalize_tokens,
    parse_md_tables,
    scrub_garbage_excludes,
    signal_filter_is_safe,
    synth_contract,
    synth_packet,
)

SWEEP_CSV = IMPL / "output" / "pack_builder_sweep.csv"


def load_index() -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with INDEX_CSV.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows[row["esha_code"]] = row
    return rows


def iter_patch_built_codes() -> list[str]:
    codes: list[str] = []
    with SWEEP_CSV.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["status"] == "patch_built":
                codes.append(row["esha_code"])
    return codes


def build_spec_for_code(code: str, index_row: dict[str, str]) -> dict | None:
    pack_path = Path(index_row["pack_path"])
    if not pack_path.exists():
        return None
    tables = parse_md_tables(pack_path.read_text(encoding="utf-8", errors="replace"))
    if not tables["candidate"]:
        return None
    synthesized = synth_contract(
        code,
        index_row.get("description") or "",
        tables,
        top_category=index_row.get("top_category") or "",
    )
    packet = synth_packet(tables)
    final = {"decision": "tighten_current_contract", "structured_contract": synthesized}
    try:
        extracted = extract_spec(packet, final)
    except Exception:
        return None
    auto_relax_spec(packet, extracted)
    enf = enforce_esha_attributes(extracted, index_row.get("description") or "", tables)
    if enf["dropped_for"]:
        return None
    apply_opposite_excludes(extracted, index_row.get("description") or "", tables)
    scrub_garbage_excludes(extracted)
    has_required = any(
        extracted[field]
        for field in (
            "required_description_terms",
            "required_description_phrases",
            "required_description_any_terms",
            "required_ingredient_terms",
            "required_ingredient_phrases",
            "required_ingredient_any_terms",
        )
    )
    has_excludes = any(
        extracted[field]
        for field in (
            "exclude_description_terms",
            "exclude_description_phrases",
            "exclude_ingredient_terms",
            "exclude_ingredient_phrases",
        )
    )
    if not has_required and not has_excludes:
        return None
    validation = validate_spec(packet, extracted)
    if not validation["ok"]:
        # Per-pack exclude rescue: tighten by adding distinctive leak tokens
        failures = validation.get("failures") or []
        too_loose = [f for f in failures if f.get("expected") == "reject" and f.get("actual") == "accept"]
        too_tight = [f for f in failures if f.get("expected") == "accept" and f.get("actual") == "reject"]
        if too_loose and not too_tight:
            leak_gtins = {f.get("gtin_upc", "") for f in too_loose}
            cand_desc: set[str] = set()
            cand_ing: set[str] = set()
            for crow in tables["candidate"]:
                cand_desc |= set(normalize_tokens(crow.get("description", ""), STOP_DESCRIPTION_TOKENS))
                cand_ing |= set(normalize_tokens(crow.get("ingredients", ""), STOP_INGREDIENT_TOKENS))
            leak_desc = _Counter()
            leak_ing = _Counter()
            for crow in tables["cleanup"]:
                if crow.get("gtin_upc", "") not in leak_gtins:
                    continue
                leak_desc.update(set(normalize_tokens(crow.get("description", ""), STOP_DESCRIPTION_TOKENS)))
                leak_ing.update(set(normalize_tokens(crow.get("ingredients", ""), STOP_INGREDIENT_TOKENS)))
            threshold = 1
            for tok, n in leak_desc.most_common():
                if n < threshold or tok in cand_desc or tok in extracted["exclude_description_terms"]:
                    continue
                extracted["exclude_description_terms"].append(tok)
            for tok, n in leak_ing.most_common():
                if n < threshold or tok in cand_ing or tok in extracted["exclude_ingredient_terms"]:
                    continue
                extracted["exclude_ingredient_terms"].append(tok)
            reval = validate_spec(packet, extracted)
            if not reval["ok"]:
                return None
        else:
            return None
    saved_desc = list(extracted["required_description_terms"])
    saved_ing = list(extracted["required_ingredient_terms"])
    dropped = esha_signal_filter(extracted, index_row.get("description") or "")
    if dropped:
        loosened_identity = any(
            extracted[field]
            for field in (
                "required_description_terms",
                "required_description_phrases",
                "required_description_any_terms",
                "required_ingredient_terms",
                "required_ingredient_phrases",
                "required_ingredient_any_terms",
            )
        )
        if loosened_identity and signal_filter_is_safe(len(tables["candidate"]), len(dropped)):
            reval = validate_spec(packet, extracted)
            if not reval["ok"]:
                extracted["required_description_terms"] = saved_desc
                extracted["required_ingredient_terms"] = saved_ing
        else:
            extracted["required_description_terms"] = saved_desc
            extracted["required_ingredient_terms"] = saved_ing
    return extracted


def main() -> None:
    index = load_index()
    codes = iter_patch_built_codes()
    print(f"processing {len(codes)} patch_built packs")
    start = time.time()
    specs: dict[str, dict] = {}
    skipped = 0
    for idx, code in enumerate(codes, start=1):
        index_row = index.get(code)
        if not index_row:
            skipped += 1
            continue
        spec = build_spec_for_code(code, index_row)
        if spec is None:
            skipped += 1
            continue
        specs[code] = spec
        if idx % 2000 == 0:
            print(f"  {idx}/{len(codes)} in {time.time()-start:.1f}s")

    registry = {"contracts": specs}
    MODULE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODULE_PATH.write_text(render_module(registry), encoding="utf-8")
    REGISTRY_PATH.write_text(render_registry(registry), encoding="utf-8")

    print(
        f"wrote {len(specs)} contracts in {time.time()-start:.1f}s"
        f"  skipped={skipped}"
    )
    print(f"  module:  {MODULE_PATH.relative_to(ROOT)}")
    print(f"  registry: {REGISTRY_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
