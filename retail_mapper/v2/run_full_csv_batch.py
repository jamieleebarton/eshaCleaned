#!/usr/bin/env python3
"""Full-CSV submission via Nebius batch API.

Workflow:
  build  -> writes a JSONL of one request-per-row
  submit -> uploads JSONL to /v1/files, creates /v1/batches job
  status -> shows current state of a batch
  fetch  -> downloads output_file when done, parses into the same JSONL shape
            our other live runs produce (so all downstream tools work)

Why batch:
  - ~50% cheaper than real-time
  - 24h SLA, server-managed (no rate-limit dance on our side)
  - Already in use on the user's account ('Hestia ingredient normalization')

Usage examples:

    # 1. Build the batch input file (no API spend)
    python3 retail_mapper/v2/run_full_csv_batch.py build \
        --out retail_mapper/v2/batch_input.jsonl

    # 2. (optional) Estimate cost before submitting
    python3 retail_mapper/v2/run_full_csv_batch.py estimate \
        --batch retail_mapper/v2/batch_input.jsonl

    # 3. Submit (uploads file, creates batch)
    NEBIUS_API_KEY=... python3 retail_mapper/v2/run_full_csv_batch.py submit \
        --batch retail_mapper/v2/batch_input.jsonl \
        --description 'retail taxonomy v2 full corpus'

    # 4. Check status
    NEBIUS_API_KEY=... python3 retail_mapper/v2/run_full_csv_batch.py status \
        --batch-id batch_xxx

    # 5. Fetch results when status=completed
    NEBIUS_API_KEY=... python3 retail_mapper/v2/run_full_csv_batch.py fetch \
        --batch-id batch_xxx \
        --out retail_mapper/v2/full_csv_run.live.jsonl
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
DEFAULT_CSV = V2 / "retail_leaf_v2_enriched_v2.csv"
DEFAULT_MODEL = "deepseek-ai/DeepSeek-V3.2"
NEBIUS_BASE = "https://api.studio.nebius.com"

csv.field_size_limit(sys.maxsize)


def load_module():
    sp = importlib.util.spec_from_file_location("ltc", V2 / "llm_taxonomy_cleanup.py")
    m = importlib.util.module_from_spec(sp); sys.modules["ltc"] = m
    sp.loader.exec_module(m)
    return m


def api_key() -> str:
    k = os.environ.get("NEBIUS_API_KEY", "").strip()
    if not k:
        raise SystemExit("NEBIUS_API_KEY not set")
    return k


def get_client():
    """OpenAI-compatible Nebius client (same pattern Hestia uses)."""
    from openai import OpenAI
    return OpenAI(api_key=api_key(), base_url=NEBIUS_BASE + "/v1/")


STATE_FILE = V2 / "full_csv_batch_state.json"


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


# ---------------- subcommands ----------------

def cmd_build(args) -> None:
    m = load_module()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with args.csv.open(encoding="utf-8", errors="replace", newline="") as src, \
         args.out.open("w", encoding="utf-8") as dst:
        for row in csv.DictReader(src):
            if not row.get("title") or not row.get("fdc_id"):
                continue
            if args.bfc_filter and args.bfc_filter.lower() not in (row.get("branded_food_category") or "").lower():
                continue
            req_body = {
                "model": args.model,
                "messages": [
                    {"role": "system", "content": m.SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({"source_row": m.compact_source_row(row)},
                                                            indent=2, sort_keys=True)},
                ],
                "temperature": 0.0,
                "max_tokens": 1200,
                "response_format": {"type": "json_object"},
            }
            dst.write(json.dumps({
                "custom_id": str(row["fdc_id"]),
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": req_body,
            }) + "\n")
            n += 1
            if args.limit and n >= args.limit:
                break
    print(f"wrote {n:,} request lines -> {args.out}")
    print(f"size: {args.out.stat().st_size / 1024 / 1024:.1f} MB")


def cmd_estimate(args) -> None:
    n = 0
    in_chars = 0
    out_tokens = 600
    with args.batch.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            n += 1
            d = json.loads(line)
            in_chars += sum(len(m.get("content", "")) for m in d["body"]["messages"])
    in_tok = in_chars // 4
    avg_in = in_tok // max(n, 1)
    in_cost = n * avg_in * 0.27 / 1e6
    out_cost = n * out_tokens * 1.10 / 1e6
    realtime = in_cost + out_cost
    batch = realtime * 0.5  # typical batch discount
    print(f"requests: {n:,}")
    print(f"avg input tokens: ~{avg_in:,}")
    print(f"avg output tokens: ~{out_tokens}")
    print(f"realtime cost: ~${realtime:.2f}")
    print(f"batch cost (50% off): ~${batch:.2f}")


def cmd_submit(args) -> None:
    client = get_client()
    print(f"uploading {args.batch}...", flush=True)
    with args.batch.open("rb") as f:
        uploaded = client.files.create(file=f, purpose="batch")
    print(f"file_id: {uploaded.id}")
    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
        metadata={"description": args.description},
    )
    state = {
        "batch_id": batch.id,
        "file_id": uploaded.id,
        "model": DEFAULT_MODEL,
        "status": batch.status,
        "input_path": str(args.batch),
    }
    save_state(state)
    print(f"\nbatch_id: {batch.id}")
    print(f"status:   {batch.status}")
    print(f"state saved -> {STATE_FILE}")


def cmd_status(args) -> None:
    client = get_client()
    batch_id = args.batch_id or load_state().get("batch_id")
    if not batch_id:
        raise SystemExit("no batch_id (pass --batch-id or run submit first)")
    batch = client.batches.retrieve(batch_id)
    print(f"batch: {batch.id}")
    print(f"status: {batch.status}")
    if batch.request_counts:
        rc = batch.request_counts
        total = rc.total or 0
        completed = rc.completed or 0
        failed = rc.failed or 0
        print(f"progress: {completed:,}/{total:,}" + (f" ({completed/total*100:.1f}%)" if total else ""))
        if failed:
            print(f"failed: {failed:,}")
    if batch.status == "completed":
        state = load_state() or {"batch_id": batch_id}
        state["status"] = "completed"
        state["output_file_id"] = batch.output_file_id
        if batch.error_file_id:
            state["error_file_id"] = batch.error_file_id
        save_state(state)
        print("batch complete. run fetch next.")


def cmd_fetch(args) -> None:
    client = get_client()
    state = load_state()
    batch_id = args.batch_id or state.get("batch_id")
    if not batch_id:
        raise SystemExit("no batch_id (pass --batch-id or run submit first)")
    batch = client.batches.retrieve(batch_id)
    if batch.status != "completed":
        print(f"batch is {batch.status!r}, not completed yet"); raise SystemExit(1)
    out_file_id = batch.output_file_id
    if not out_file_id:
        raise SystemExit("no output_file_id on batch")
    print(f"downloading output_file_id={out_file_id}...", flush=True)
    content = client.files.content(out_file_id)
    raw = content.read()
    import re
    out_lines: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        cid = d.get("custom_id", "")
        body = d.get("response", {}).get("body", {}) or {}
        choices = body.get("choices") or []
        raw_msg = (choices[0].get("message", {}) or {}).get("content", "") if choices else ""
        record: dict = {}
        try:
            match = re.search(r"\{.*\}", raw_msg, re.DOTALL)
            record = json.loads(match.group(0)) if match else {"_parse_error": "no JSON object found"}
        except Exception as exc:
            record = {"_parse_error": str(exc)}
        out_lines.append({"fdc_id": cid, "raw": raw_msg, "record": record})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for o in out_lines:
            fh.write(json.dumps(o, sort_keys=True) + "\n")
    print(f"wrote {len(out_lines):,} rows -> {args.out}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    pb = sub.add_parser("build")
    pb.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    pb.add_argument("--bfc-filter", type=str, default=None)
    pb.add_argument("--limit", type=int, default=None)
    pb.add_argument("--model", default=DEFAULT_MODEL)
    pb.add_argument("--out", type=Path, required=True)
    pb.set_defaults(func=cmd_build)

    pe = sub.add_parser("estimate")
    pe.add_argument("--batch", type=Path, required=True)
    pe.set_defaults(func=cmd_estimate)

    ps = sub.add_parser("submit")
    ps.add_argument("--batch", type=Path, required=True)
    ps.add_argument("--description", default="retail taxonomy v2 full corpus")
    ps.set_defaults(func=cmd_submit)

    pst = sub.add_parser("status")
    pst.add_argument("--batch-id", default=None,
                     help="Optional. If omitted, uses saved state from last submit.")
    pst.set_defaults(func=cmd_status)

    pf = sub.add_parser("fetch")
    pf.add_argument("--batch-id", default=None)
    pf.add_argument("--out", type=Path, required=True)
    pf.set_defaults(func=cmd_fetch)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
