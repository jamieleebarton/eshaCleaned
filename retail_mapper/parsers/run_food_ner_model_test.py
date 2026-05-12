#!/usr/bin/env python3
"""Run downloaded food NER models on a deterministic product sample."""
from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter, OrderedDict


MODEL_STATUS_FIELDS = [
    "model_id",
    "local_path",
    "status",
    "notes",
]

OUTPUT_FIELDS = [
    "sample_source",
    "fdc_id",
    "gtin_upc",
    "product_description",
    "branded_food_category",
    "parser_retail_type",
    "parser_category_group",
    "parser_category",
    "parser_primary_food",
    "parser_form",
    "parser_flavor",
    "parser_retail_leaf",
    "axis_review_issues",
    "category_candidates",
    "form_candidates",
    "flavor_candidates",
    "unselected_category_candidates",
    "unselected_form_candidates",
    "unselected_flavor_candidates",
    "unaccounted_tokens",
    "ckauth_food_ner_entities",
    "ckauth_food_ner_menu_text",
    "ckauth_food_ner_menu_score_max",
    "spacy_foodner_entities",
    "spacy_foodner_labels",
]


def load_csv_by_fdc(path: str) -> dict[str, dict[str, str]]:
    with open(path, newline="") as fh:
        return {row["fdc_id"]: row for row in csv.DictReader(fh)}


def add_sample(samples: OrderedDict[str, str], fdc_id: str, source: str, limit: int | None = None) -> None:
    if not fdc_id or fdc_id in samples:
        return
    if limit is not None and sum(1 for value in samples.values() if value == source) >= limit:
        return
    samples[fdc_id] = source


def collect_samples(parsed_path: str, mistake_paths: list[str], limit: int) -> OrderedDict[str, str]:
    samples: OrderedDict[str, str] = OrderedDict()

    priority_ids = [
        "2243801",
        "2746465",
        "2744535",
        "2491056",
        "2052954",
        "1766233",
        "2521535",
        "2541020",
        "2556089",
        "1651693",
        "444863",
        "2185615",
        "1475258",
        "1977436",
        "2365001",
    ]
    for fdc_id in priority_ids:
        add_sample(samples, fdc_id, "priority_examples")

    for path in mistake_paths:
        if not os.path.exists(path):
            continue
        source = os.path.splitext(os.path.basename(path))[0]
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                add_sample(samples, row.get("fdc_id", ""), source, limit=30)
                if len(samples) >= limit:
                    return samples

    issue_counts: Counter[str] = Counter()
    with open(parsed_path, newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                issues = json.loads(row.get("axis_review_issues", "[]") or "[]")
            except json.JSONDecodeError:
                issues = []
            if not issues:
                continue
            for issue in issues:
                if issue_counts[issue] < 15:
                    add_sample(samples, row.get("fdc_id", ""), f"axis_review:{issue}")
                    issue_counts[issue] += 1
                    break
            if len(samples) >= limit:
                return samples

    step = 997
    with open(parsed_path, newline="") as fh:
        for idx, row in enumerate(csv.DictReader(fh)):
            if idx % step == 0:
                add_sample(samples, row.get("fdc_id", ""), "deterministic_stride")
            if len(samples) >= limit:
                break
    return samples


def clean_tf_entity(entity: dict[str, object]) -> dict[str, object]:
    return {
        "entity_group": str(entity.get("entity_group", "")),
        "score": round(float(entity.get("score", 0.0)), 4),
        "word": str(entity.get("word", "")),
        "start": int(entity.get("start", -1)),
        "end": int(entity.get("end", -1)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run food NER model smoke test on product titles.")
    parser.add_argument("--parsed", default="codex_parsed_titles_audit.csv")
    parser.add_argument("--source", default="product_esha_fixy.v6.csv")
    parser.add_argument("--output", default="codex_food_ner_model_test.csv")
    parser.add_argument("--status-output", default="codex_food_ner_model_status.csv")
    parser.add_argument("--limit", type=int, default=120)
    args = parser.parse_args()

    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    from transformers import pipeline
    import spacy

    ckauth_model_path = "models/hf/ckauth__food-ner"
    spacy_model_name = "en_foodNERspaCyRobarta"

    ckauth_pipe = pipeline(
        "token-classification",
        model=ckauth_model_path,
        tokenizer=ckauth_model_path,
        aggregation_strategy="simple",
        framework="tf",
    )
    spacy_nlp = spacy.load(spacy_model_name)

    parsed_by_fdc = load_csv_by_fdc(args.parsed)
    source_by_fdc = load_csv_by_fdc(args.source)
    sample_sources = collect_samples(
        args.parsed,
        ["codex_found_mistakes.csv", "codex_found_packaging_mistakes.csv"],
        args.limit,
    )
    fdc_ids = [fdc_id for fdc_id in sample_sources if fdc_id in parsed_by_fdc]
    titles = [parsed_by_fdc[fdc_id]["product_description"] for fdc_id in fdc_ids]

    ckauth_outputs = ckauth_pipe(titles, batch_size=16)
    spacy_docs = list(spacy_nlp.pipe(titles, batch_size=16))

    with open(args.output, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for fdc_id, ckauth_entities, doc in zip(fdc_ids, ckauth_outputs, spacy_docs):
            parsed = parsed_by_fdc[fdc_id]
            source = source_by_fdc.get(fdc_id, {})
            tf_entities = [clean_tf_entity(entity) for entity in ckauth_entities]
            menu_text = [entity["word"] for entity in tf_entities if entity["entity_group"] == "MENU"]
            menu_scores = [entity["score"] for entity in tf_entities if entity["entity_group"] == "MENU"]
            spacy_entities = [
                {
                    "text": ent.text,
                    "label": ent.label_,
                    "start": ent.start_char,
                    "end": ent.end_char,
                }
                for ent in doc.ents
            ]
            writer.writerow(
                {
                    "sample_source": sample_sources[fdc_id],
                    "fdc_id": fdc_id,
                    "gtin_upc": parsed.get("gtin_upc", ""),
                    "product_description": parsed.get("product_description", ""),
                    "branded_food_category": source.get("branded_food_category", ""),
                    "parser_retail_type": parsed.get("retail_type", ""),
                    "parser_category_group": parsed.get("category_group", ""),
                    "parser_category": parsed.get("category", ""),
                    "parser_primary_food": parsed.get("primary_food", ""),
                    "parser_form": parsed.get("form", ""),
                    "parser_flavor": parsed.get("flavor", ""),
                    "parser_retail_leaf": parsed.get("retail_leaf", ""),
                    "axis_review_issues": parsed.get("axis_review_issues", ""),
                    "category_candidates": parsed.get("category_candidates", ""),
                    "form_candidates": parsed.get("form_candidates", ""),
                    "flavor_candidates": parsed.get("flavor_candidates", ""),
                    "unselected_category_candidates": parsed.get("unselected_category_candidates", ""),
                    "unselected_form_candidates": parsed.get("unselected_form_candidates", ""),
                    "unselected_flavor_candidates": parsed.get("unselected_flavor_candidates", ""),
                    "unaccounted_tokens": parsed.get("unaccounted_tokens", ""),
                    "ckauth_food_ner_entities": json.dumps(tf_entities, separators=(",", ":")),
                    "ckauth_food_ner_menu_text": json.dumps(menu_text, separators=(",", ":")),
                    "ckauth_food_ner_menu_score_max": max(menu_scores) if menu_scores else "",
                    "spacy_foodner_entities": json.dumps(spacy_entities, separators=(",", ":")),
                    "spacy_foodner_labels": json.dumps(sorted({ent["label"] for ent in spacy_entities}), separators=(",", ":")),
                }
            )

    statuses = [
        {
            "model_id": "ckauth/food-ner",
            "local_path": ckauth_model_path,
            "status": "ran",
            "notes": "TensorFlow BERT token-classification model; labels: O, B-MENU, I-MENU.",
        },
        {
            "model_id": "DavidEB2/foodner-bert-large-ner",
            "local_path": "models/hf/DavidEB2__foodner-bert-large-ner",
            "status": "downloaded_unusable",
            "notes": "Repository snapshot only exposed .gitattributes; no config/tokenizer/weights were available.",
        },
        {
            "model_id": "munavvard2/foodNERspaCyRobarta",
            "local_path": "models/hf/munavvard2__foodNERspaCyRobarta",
            "status": "downloaded_unusable",
            "notes": "Repository snapshot only exposed .gitattributes; no runnable spaCy model files were available.",
        },
        {
            "model_id": "munavvard2/en_foodNERspaCyRobarta",
            "local_path": "models/hf/munavvard2__en_foodNERspaCyRobarta",
            "status": "ran",
            "notes": "spaCy transformer NER model; labels are additive/source oriented, not food category/form/flavor.",
        },
    ]
    with open(args.status_output, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=MODEL_STATUS_FIELDS)
        writer.writeheader()
        writer.writerows(statuses)

    print(f"Wrote {len(fdc_ids)} rows to {args.output}")
    print(f"Wrote model status to {args.status_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
