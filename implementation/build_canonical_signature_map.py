"""Build product -> canonical signature mapping over the full vM corpus.

Reads:
  - implementation/output/canonical_surface_normalized_with_product_proxies_CLEANED.csv (anchor universe)
  - product_to_best_esha_full_map.vM.csv (462k branded products)

Writes:
  - implementation/output/product_to_canonical_signature.csv
  - implementation/output/product_to_canonical_signature_summary.json
"""
from __future__ import annotations
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from implementation.canonical_signature.attribute_extractor import extract_attributes
from implementation.canonical_signature.composite_router import load_category_map
from implementation.canonical_signature.pipeline import (
    CanonicalSignaturePipeline, ProductRow,
)
from implementation.canonical_signature.vocabularies import Vocabularies

OUTPUT_DIR = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output")
CANONICAL_PATH = OUTPUT_DIR / "canonical_surface_normalized_with_product_proxies_CLEANED.csv"
PRODUCT_CLEAN_PATH = OUTPUT_DIR / "product_to_best_esha_full_map.vIdentity.csv"
PRODUCT_PATH = PRODUCT_CLEAN_PATH if PRODUCT_CLEAN_PATH.exists() else OUTPUT_DIR / "product_to_best_esha_full_map.vM.csv"
OUTPUT_CSV = OUTPUT_DIR / "product_to_canonical_signature.csv"
SUMMARY_JSON = OUTPUT_DIR / "product_to_canonical_signature_summary.json"

OUTPUT_FIELDS = [
    "gtin_upc", "fdc_id", "product_description", "branded_food_category", "brand_name",
    "signature_head_noun", "signature_modifiers",
    "signature_form", "signature_state", "signature_flavor", "signature_style",
    "composite", "secondary_ingredients",
    "canonical_anchor_id", "canonical_surface", "canonical_normalized",
    "sr28_code", "fndds_code", "esha_code",
    "match_layer", "match_confidence", "match_reason",
    "stripped_brand", "stripped_fluff", "extracted_attributes_json", "residual",
    "top_candidates_json",
    "prev_best_esha_code", "prev_score", "assignment_changed",
]


def _first_attr(cell):
    if not cell:
        return None
    parts = cell.replace(";", ",").split(",")
    for p in parts:
        v = p.strip().lower()
        if v:
            return v
    return None


def load_canonical_corpus(path: Path, vocab: Vocabularies):
    """Yield (id, normalized_text, form, state, flavor, style) per canonical row.

    Form/state/style come from the canonical_surface attribute columns when populated;
    flavor (no dedicated column) is derived by running the attribute extractor over
    canonical_normalized — this keeps canonical and product signatures comparable.
    Also returns lookup dict id -> full row dict for downstream code/description fields.
    """
    corpus = []
    lookup: dict[str, dict] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            cid = f"canon_{i}"
            text = (row.get("canonical_normalized") or "").strip().lower()
            if not text:
                continue
            ext = extract_attributes(
                text,
                fluff=vocab.fluff_tokens | vocab.noise_tokens,
                flavors=vocab.flavor_vocabulary,
                forms=vocab.form_vocabulary,
                states=vocab.state_vocabulary,
                styles=vocab.style_vocabulary,
                packaging=vocab.packaging_vocabulary,
            )
            form = _first_attr(row.get("form_attributes")) or ext.form
            state = _first_attr(row.get("state_attributes")) or ext.state
            style = _first_attr(row.get("style_attributes")) or ext.style
            flavor = ext.flavor  # canonical_surface has no flavor column

            corpus.append((cid, text, form, state, flavor, style))
            lookup[cid] = row
    return corpus, lookup


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N product rows (smoke test)")
    parser.add_argument("--no-embeddings", action="store_true",
                        help="Skip L5 embedding fallback (faster, lower recall)")
    parser.add_argument("--output", type=Path, default=OUTPUT_CSV)
    args = parser.parse_args(argv)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[1/4] Loading vocabularies from {CANONICAL_PATH.name}")
    vocab = Vocabularies.from_canonical_surface(CANONICAL_PATH)
    print(f"      brand_vocab={len(vocab.brand_vocabulary)} "
          f"form_vocab={len(vocab.form_vocabulary)} "
          f"flavors={len(vocab.flavor_vocabulary)}")

    print(f"[2/4] Loading canonical corpus")
    corpus, canonical_lookup = load_canonical_corpus(CANONICAL_PATH, vocab)
    print(f"      canonical_rows={len(corpus)}")

    print(f"[3/4] Building pipeline (embeddings={'off' if args.no_embeddings else 'on'})")
    category_map = load_category_map()
    pipeline = CanonicalSignaturePipeline.build(
        corpus, vocab, category_map, with_embeddings=not args.no_embeddings,
    )

    print(f"[4/4] Streaming products from {PRODUCT_PATH.name} -> {args.output.name}")
    counters: Counter = Counter()
    rows_written = 0

    with PRODUCT_PATH.open(newline="", encoding="utf-8") as fin, \
         args.output.open("w", newline="", encoding="utf-8") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()

        for i, prow in enumerate(reader):
            if args.limit is not None and i >= args.limit:
                break

            sig, trace, anchor_id = pipeline.process(ProductRow(
                description=prow.get("product_description") or "",
                brand_name=prow.get("brand_name") or None,
                brand_owner=prow.get("brand_owner") or None,
                branded_food_category=prow.get("branded_food_category") or None,
            ))

            anchor_row = canonical_lookup.get(anchor_id) if anchor_id else None
            prev_code = prow.get("best_esha_code") or ""
            new_esha = (anchor_row or {}).get("esha_code", "") if anchor_row else ""
            assignment_changed = (prev_code or "") != (new_esha or "")

            writer.writerow({
                "gtin_upc": prow.get("gtin_upc", ""),
                "fdc_id": prow.get("fdc_id", ""),
                "product_description": prow.get("product_description", ""),
                "branded_food_category": prow.get("branded_food_category", ""),
                "brand_name": prow.get("brand_name", ""),
                "signature_head_noun": sig.head_noun,
                "signature_modifiers": ";".join(sorted(sig.modifiers)),
                "signature_form": sig.form or "",
                "signature_state": sig.state or "",
                "signature_flavor": sig.flavor or "",
                "signature_style": sig.style or "",
                "composite": "true" if sig.composite else "false",
                "secondary_ingredients": ";".join(sig.secondary_ingredients),
                "canonical_anchor_id": anchor_id or "",
                "canonical_surface": (anchor_row or {}).get("canonical_surface", ""),
                "canonical_normalized": (anchor_row or {}).get("canonical_normalized", ""),
                "sr28_code": (anchor_row or {}).get("sr28_code", ""),
                "fndds_code": (anchor_row or {}).get("fndds_code", ""),
                "esha_code": new_esha,
                "match_layer": trace.match_layer,
                "match_confidence": f"{trace.match_confidence:.4f}",
                "match_reason": trace.match_reason,
                "stripped_brand": trace.stripped_brand,
                "stripped_fluff": ";".join(trace.stripped_fluff),
                "extracted_attributes_json": json.dumps(trace.extracted_attributes),
                "residual": trace.residual,
                "top_candidates_json": json.dumps([[c, round(s, 4)] for c, s in trace.top_candidates]),
                "prev_best_esha_code": prev_code,
                "prev_score": prow.get("score", ""),
                "assignment_changed": "true" if assignment_changed else "false",
            })
            counters[trace.match_layer] += 1
            counters["composite" if sig.composite else "non_composite"] += 1
            counters["assignment_changed" if assignment_changed else "assignment_kept"] += 1
            rows_written += 1
            if rows_written % 10000 == 0:
                print(f"      processed {rows_written}", file=sys.stderr)

    summary = {
        "rows_written": rows_written,
        "by_layer": dict(counters),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2))
    print(f"Done. Summary: {SUMMARY_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
