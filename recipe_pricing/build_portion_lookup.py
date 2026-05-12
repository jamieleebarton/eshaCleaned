#!/usr/bin/env python3
"""Build portion-to-grams lookup with three layers, in order of trust:

  1. SR Legacy direct       — fdc_id matches data/sr28_csv/food_portion.csv
  2. FNDDS bridge           — FNDDS food code → SR code (NDB) → SR Legacy
                              fdc_id → portions, via data/fndds/FNDDSSRLinks.csv
  3. canonical_path tree    — for items without direct portion data, aggregate
                              from products at the SAME canonical_path or
                              its DESCENDANTS only (never siblings — brown sugar
                              ≠ granulated sugar). Walk to parent only as a
                              last resort and tag with `match_distance`.

Outputs:
  - recipe_pricing/output/sr28_fndds_taxonomy_v2.csv  (portions_json column)
  - recipe_pricing/output/canonical_path_portions.csv (cp → grams aggregation)
  - recipe_pricing/output/htc_code_portions.csv       (exact-match lookup)
"""
from __future__ import annotations

import csv
import json
import shutil
import sys
from collections import defaultdict, Counter
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
SR28_DIR = ROOT / "data" / "sr28_csv"
FNDDS_DIR = ROOT / "data" / "fndds"
SR28_TAXONOMY = ROOT / "recipe_pricing" / "output" / "sr28_fndds_taxonomy_v2.csv"
OUT_HTC = ROOT / "recipe_pricing" / "output" / "htc_code_portions.csv"
OUT_CP = ROOT / "recipe_pricing" / "output" / "canonical_path_portions.csv"

UNIT_PATTERNS = [
    ("cup",  ("cup",)),
    ("tbsp", ("tbsp", "tablespoon")),
    ("tsp",  ("tsp", "teaspoon")),
    ("oz",   ("oz", "ounce")),
    ("lb",   ("lb", "pound")),
    ("ml",   ("ml", "milliliter")),
    ("g",    ("gram",)),
    ("piece",("piece", "slice", "stick", "bar", "ball", "patty", "wedge",
              "fillet", "pat", "scoop", "package", "container", "bottle",
              "can", "envelope", "pouch", "bag", "egg")),
    ("serving", ("serving",)),
]


def classify_unit(modifier: str) -> str:
    m = (modifier or "").lower()
    for cls, words in UNIT_PATTERNS:
        for w in words:
            if w == m or m.startswith(w + " ") or m.startswith(w + ",") or \
               (" " + w + " ") in (" " + m + " ") or m.endswith(" " + w):
                return cls
    return "other"


def load_measure_units() -> dict[str, str]:
    out: dict[str, str] = {}
    with (SR28_DIR / "measure_unit.csv").open() as f:
        for row in csv.DictReader(f):
            out[row["id"].strip('"')] = row["name"].strip('"')
    return out


def load_food_portions() -> dict[str, list[dict]]:
    """SR Legacy fdc_id (string, no prefix) -> list of portion dicts."""
    out: defaultdict[str, list[dict]] = defaultdict(list)
    with (SR28_DIR / "food_portion.csv").open() as f:
        for row in csv.DictReader(f):
            fid = (row.get("fdc_id") or "").strip('"').strip()
            if not fid:
                continue
            try:
                amount = float((row.get("amount") or "0").strip('"') or 0)
                grams = float((row.get("gram_weight") or "0").strip('"') or 0)
            except ValueError:
                continue
            modifier = (row.get("modifier") or "").strip('"').lower()
            desc = (row.get("portion_description") or "").strip('"').lower()
            unit_class = classify_unit(modifier or desc)
            unit_label = modifier or desc or "unit"
            out[fid].append({
                "label": f"{amount} {unit_label}".strip(),
                "amount": amount,
                "unit_class": unit_class,
                "raw_unit": unit_label,
                "gram_weight": grams,
            })
    return dict(out)


def load_ndb_to_sr_legacy() -> dict[str, str]:
    """NDB number -> SR Legacy fdc_id. Bridge for FNDDS SR codes."""
    out: dict[str, str] = {}
    with (SR28_DIR / "sr_legacy_food.csv").open() as f:
        for row in csv.DictReader(f):
            ndb = (row.get("NDB_number") or "").strip('"')
            fid = (row.get("fdc_id") or "").strip('"')
            if ndb and fid:
                out[ndb] = fid
    return out


def load_fndds_sr_links() -> dict[str, list[tuple[str, float]]]:
    """FNDDS Food code -> [(SR code, weight_share), ...] sorted by Seq num."""
    raw: defaultdict[str, list[tuple[int, str, float]]] = defaultdict(list)
    fndds_link_path = FNDDS_DIR / "FNDDSSRLinks.csv"
    if not fndds_link_path.exists():
        return {}
    with fndds_link_path.open() as f:
        for row in csv.DictReader(f):
            code = (row.get("Food code") or "").strip()
            sr_code = (row.get("SR code") or "").strip()
            try:
                seq = int((row.get("Seq num") or "999").strip())
                weight = float((row.get("Weight") or "0").strip() or 0)
            except ValueError:
                continue
            if code and sr_code:
                raw[code].append((seq, sr_code, weight))
    out: dict[str, list[tuple[str, float]]] = {}
    for code, links in raw.items():
        links.sort()
        # Use most-recent end-date entries; here we just dedup by SR code
        # keeping highest weight.
        seen: dict[str, float] = {}
        for _, sr, w in links:
            if sr not in seen or w > seen[sr]:
                seen[sr] = w
        out[code] = sorted(seen.items(), key=lambda kv: -kv[1])
    return out


def aggregate_grams_per_unit(portions: list[dict]) -> dict[str, float]:
    """Pick the modal grams-per-unit across a portion list."""
    per_unit: defaultdict[str, list[float]] = defaultdict(list)
    for p in portions:
        cls = p.get("unit_class", "other")
        if cls == "other":
            continue
        if p["amount"] > 0 and p["gram_weight"] > 0:
            per_unit[cls].append(p["gram_weight"] / p["amount"])
    out: dict[str, float] = {}
    for cls, vals in per_unit.items():
        # Mode of rounded values is robust against outliers
        rounded = [round(v, 1) for v in vals]
        out[cls] = float(Counter(rounded).most_common(1)[0][0])
    return out


def main() -> int:
    units = load_measure_units()
    sr_portions = load_food_portions()
    ndb_to_sr = load_ndb_to_sr_legacy()
    fndds_links = load_fndds_sr_links()
    print(f"  measure_units: {len(units)}", file=sys.stderr)
    print(f"  SR Legacy fdc_ids with portions: {len(sr_portions):,}", file=sys.stderr)
    print(f"  NDB → SR Legacy fdc_id bridge:   {len(ndb_to_sr):,}", file=sys.stderr)
    print(f"  FNDDS Food code → SR code links: {len(fndds_links):,}", file=sys.stderr)

    # 1. Attach portions_json to sr28_fndds_taxonomy_v2.csv.
    #    For SR28-* fdc_ids: direct lookup.
    #    For FNDDS-* fdc_ids: bridge via FNDDSSRLinks → NDB → SR Legacy.
    tmp = SR28_TAXONOMY.with_suffix(".csv.tmp")
    sr_n = sr_with_portions = fndds_with_portions = 0
    htc_to_portions: defaultdict[str, list[dict]] = defaultdict(list)
    cp_to_portions: defaultdict[str, list[dict]] = defaultdict(list)
    cp_to_codes: defaultdict[str, set[str]] = defaultdict(set)
    with SR28_TAXONOMY.open(newline="") as fin, tmp.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        fieldnames = list(reader.fieldnames or [])
        if "portions_json" not in fieldnames:
            anchor = "retail_leaf_path" if "retail_leaf_path" in fieldnames else "canonical_path"
            if anchor in fieldnames:
                fieldnames.insert(fieldnames.index(anchor) + 1, "portions_json")
            else:
                fieldnames.append("portions_json")
        if "portions_source" not in fieldnames:
            fieldnames.insert(fieldnames.index("portions_json") + 1, "portions_source")
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            sr_n += 1
            fid_raw = (row.get("fdc_id") or "").strip()
            ports: list[dict] = []
            source = ""
            if fid_raw.startswith("SR28-"):
                sr_id = fid_raw.split("-", 1)[1]
                ports = sr_portions.get(sr_id, [])
                if ports:
                    source = "sr_legacy_direct"
                    sr_with_portions += 1
            elif fid_raw.startswith("FNDDS-"):
                food_code = fid_raw.split("-", 1)[1]
                links = fndds_links.get(food_code, [])
                # Try the highest-weight SR link first
                for sr_code, _ in links[:5]:
                    sr_legacy_id = ndb_to_sr.get(sr_code)
                    if sr_legacy_id and sr_legacy_id in sr_portions:
                        ports = sr_portions[sr_legacy_id]
                        source = f"fndds_bridge_via_sr_{sr_code}"
                        fndds_with_portions += 1
                        break
            # Persist
            if ports:
                d = {p["label"]: p["gram_weight"] for p in ports if p["gram_weight"] > 0}
                row["portions_json"] = json.dumps(d, sort_keys=True)
                row["portions_source"] = source
                hc = (row.get("htc_code") or "").strip()
                cp = (row.get("canonical_path") or "").strip()
                if hc:
                    htc_to_portions[hc].extend(ports)
                if cp:
                    cp_to_portions[cp].extend(ports)
                    cp_to_codes[cp].add(hc)
            else:
                row.setdefault("portions_json", "")
                row.setdefault("portions_source", "")
            writer.writerow(row)
    shutil.move(str(tmp), str(SR28_TAXONOMY))
    total_with = sr_with_portions + fndds_with_portions
    print(f"  SR28/FNDDS taxonomy rows: {sr_n:,}", file=sys.stderr)
    print(f"    with portions (sr_legacy_direct): {sr_with_portions:,}", file=sys.stderr)
    print(f"    with portions (fndds_bridge):     {fndds_with_portions:,}", file=sys.stderr)
    print(f"    total: {total_with:,} ({total_with/sr_n:.1%})", file=sys.stderr)

    # 2. Per-htc_code aggregation (exact-match lookup)
    htc_rows = []
    for hc, ports in htc_to_portions.items():
        agg = aggregate_grams_per_unit(ports)
        if not agg:
            continue
        htc_rows.append({
            "htc_code": hc,
            "n_source_portions": len(ports),
            "grams_per_cup":   agg.get("cup", ""),
            "grams_per_tbsp":  agg.get("tbsp", ""),
            "grams_per_tsp":   agg.get("tsp", ""),
            "grams_per_oz":    agg.get("oz", ""),
            "grams_per_lb":    agg.get("lb", ""),
            "grams_per_piece": agg.get("piece", ""),
        })
    htc_fields = ["htc_code", "n_source_portions", "grams_per_cup",
                  "grams_per_tbsp", "grams_per_tsp", "grams_per_oz",
                  "grams_per_lb", "grams_per_piece"]
    with OUT_HTC.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=htc_fields)
        w.writeheader()
        for r in sorted(htc_rows, key=lambda r: r["htc_code"]):
            w.writerow(r)
    print(f"  htc_code → grams aggregation: {len(htc_rows):,} → {OUT_HTC}", file=sys.stderr)

    # 3. canonical_path aggregation (fallback). Each row has the path's
    #    aggregated portions plus DESCENDANT-aggregated portions (since recipe
    #    ingredients at parent paths legitimately match all sub-leaves).
    cp_rows = []
    all_paths = list(cp_to_portions.keys())
    for cp in all_paths:
        # Self + descendants
        own_ports = list(cp_to_portions[cp])
        descendant_ports: list[dict] = []
        for other in all_paths:
            if other != cp and other.startswith(cp + " > "):
                descendant_ports.extend(cp_to_portions[other])
        agg_self = aggregate_grams_per_unit(own_ports)
        agg_with_desc = aggregate_grams_per_unit(own_ports + descendant_ports) \
                        if descendant_ports else agg_self
        cp_rows.append({
            "canonical_path": cp,
            "n_source_portions_self":     len(own_ports),
            "n_source_portions_subtree":  len(own_ports) + len(descendant_ports),
            "grams_per_cup_self":   agg_self.get("cup", ""),
            "grams_per_tbsp_self":  agg_self.get("tbsp", ""),
            "grams_per_tsp_self":   agg_self.get("tsp", ""),
            "grams_per_piece_self": agg_self.get("piece", ""),
            "grams_per_cup_subtree":   agg_with_desc.get("cup", ""),
            "grams_per_tbsp_subtree":  agg_with_desc.get("tbsp", ""),
            "grams_per_tsp_subtree":   agg_with_desc.get("tsp", ""),
            "grams_per_piece_subtree": agg_with_desc.get("piece", ""),
        })
    cp_fields = list(cp_rows[0].keys()) if cp_rows else []
    if cp_rows:
        with OUT_CP.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cp_fields)
            w.writeheader()
            for r in sorted(cp_rows, key=lambda r: r["canonical_path"]):
                w.writerow(r)
        print(f"  canonical_path → grams aggregation: {len(cp_rows):,} → {OUT_CP}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
