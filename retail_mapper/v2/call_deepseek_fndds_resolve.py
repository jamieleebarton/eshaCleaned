#!/usr/bin/env python3
"""Send FNDDS-disagreement clusters to DeepSeek and collect decisions.

Reads `fndds_cluster_input.jsonl` (built by build_fndds_cluster_input.py).
For each cluster, asks DeepSeek to:
  1. Pick the correct FNDDS code for each sample SKU based on title +
     ingredients + branded category + brand name.
  2. Return a cluster-level rule if the choice is uniform across samples,
     else mark `per_row_required` and decide each sample individually.

Output: `fndds_cluster_decisions.jsonl` — one JSON line per cluster:
  {
    "ours_code": ..., "master_code": ..., "n_total_skus": ...,
    "rule": "prefer_master" | "prefer_ours" | "prefer_other" | "per_row_required",
    "rule_fndds": "<8-digit code>" if applicable,
    "rationale": "...",
    "confidence": 0..1,
    "per_row_decisions": [{"fdc_id": ..., "chosen_code": ..., "reason": ...}, ...]
  }

Resumable: skips clusters already in the output file.

Requires:
    export DEEPSEEK_API_KEY=sk-...

Usage:
    python3 retail_mapper/v2/call_deepseek_fndds_resolve.py
    python3 retail_mapper/v2/call_deepseek_fndds_resolve.py --resume --limit 100
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import threading
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# SSL context with certifi CA bundle — Python 3.14 on macOS doesn't pick up
# system certs by default, so api.deepseek.com handshake fails without this.
try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
SRC = V2 / "fndds_cluster_input.jsonl"
OUT = V2 / "fndds_cluster_decisions.jsonl"
LOG = V2 / "fndds_resolve_log.txt"

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"

SYSTEM_PROMPT = """You arbitrate FNDDS food-classification disagreements. \
Two upstream classifiers (OURS and MASTER) tagged a batch of grocery SKUs \
with different FNDDS food codes. Use the SKU title + ingredients + branded \
category + brand to decide which is correct, OR describe the true product \
when both are wrong.

For each sample SKU, decide:
- "ours" — ours_code is correct (returns ours_code, a real FNDDS code)
- "master" — master_code is correct (returns master_code, a real FNDDS code)
- "other" — both are wrong AND the true food is in a meaningfully different \
  category. Describe what the product ACTUALLY is in 4-12 words using \
  FNDDS-style food-language (e.g., "kale chip seasoned", "chocolate chip \
  cookie soft baked", "fruit punch soft drink"). DO NOT invent FNDDS codes. \
  Just describe — the host system will look up the real code.

CRITICAL: do NOT pick 'other' when your intended description aligns with \
either ours_desc or master_desc. Examples:
- ours_desc='cookies & cream ice cream', master_desc='Cookie, NFS', and \
  the products are biscuits → pick "master" (master_desc IS cookie). \
  Don't pick "other" with description 'cookie'.
- ours_desc='whiskey and soda', master_desc='soft drink fruit flavored', \
  product is Welch's tropical punch → pick "master".
Only use "other" for genuinely-third-category cases (kale chip when both \
candidates are pretzel chips and potato chips, etc.).

Cluster-level rule based on per-sample decisions:
- ALL samples → ours: rule = "prefer_ours"
- ALL samples → master: rule = "prefer_master"
- ALL samples → same OTHER description: rule = "prefer_other", rule_desc = \
  that description
- Samples disagree: rule = "per_row_required"

Output STRICT JSON, no markdown. Schema:
{
  "rule": "prefer_ours"|"prefer_master"|"prefer_other"|"per_row_required",
  "rule_desc": "<plain-English food description, only if rule=prefer_other>",
  "rationale": "<1-2 sentences explaining why>",
  "confidence": <0.0-1.0>,
  "per_row_decisions": [
    {"fdc_id": "<id>",
     "decision": "ours"|"master"|"other",
     "chosen_desc": "<plain food description ONLY when decision=other; \
                     leave blank for ours/master>",
     "reason": "<brief>"}
  ]
}

Always populate per_row_decisions for every sample. NEVER output an \
8-digit FNDDS code yourself when decision='other' — only a description. \
Confidence reflects overall certainty (0.95+ if obvious, 0.5-0.7 if mixed).

Heuristics:
- Ingredients are the strongest signal. "Wheat flour, sugar, butter" is \
  cookies, not ice cream — regardless of title.
- Branded category (BFC) is a useful prior.
- "Biscuit" or "cookie" in title → likely cookie family.
- Real ice cream lists "milk, cream, sugar, stabilizers" early.
- "Soda" / "fruit punch" / "sparkling drink" are soft drinks, NOT cocktails \
  unless title literally names a spirit (whiskey, vodka, rum, gin).
- Bars: granola bars have oats + honey; energy/protein bars have whey/soy \
  protein high in the ingredient list.
- Veggie chips, kale chips, plantain chips are vegetable-based snacks, \
  not pretzel chips or potato chips even if both are 'chips'."""


def call_deepseek(api_key: str, messages: list[dict], timeout: int = 240) -> str:
    body = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 4000,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


def cluster_user_prompt(cluster: dict) -> str:
    """Render a cluster as the user-message JSON sent to DeepSeek."""
    return json.dumps({
        "ours_code": cluster["ours_code"],
        "ours_desc": cluster["ours_desc"],
        "master_code": cluster["master_code"],
        "master_desc": cluster["master_desc"],
        "n_total_skus": cluster["n_total_skus"],
        "samples": cluster["samples"],
    }, ensure_ascii=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", action="store_true",
                    help="skip clusters already in output JSONL")
    ap.add_argument("--limit", type=int, default=0,
                    help="0 = all clusters; otherwise process only first N")
    ap.add_argument("--start", type=int, default=0,
                    help="skip first N clusters (for sharded runs)")
    ap.add_argument("--workers", type=int, default=1,
                    help="concurrent API requests (default 1; safe at 10-20)")
    args = ap.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY not set in env. "
                         "export DEEPSEEK_API_KEY=sk-... and re-run.")

    if not SRC.exists():
        raise SystemExit(f"missing {SRC}; run build_fndds_cluster_input.py first")

    # Load clusters
    clusters: list[dict] = []
    with SRC.open() as fh:
        for line in fh:
            if line.strip():
                clusters.append(json.loads(line))
    if args.start:
        clusters = clusters[args.start:]
    if args.limit:
        clusters = clusters[: args.limit]

    # Resume support — skip clusters already done
    done_keys: set[tuple[str, str]] = set()
    if args.resume and OUT.exists():
        with OUT.open() as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                    done_keys.add((rec["ours_code"], rec["master_code"]))
                except Exception:
                    pass
        print(f"  resume: {len(done_keys):,} clusters already done")

    pending = [c for c in clusters
               if (c["ours_code"], c["master_code"]) not in done_keys]
    print(f"  pending: {len(pending):,} clusters")

    out_mode = "a" if args.resume else "w"
    log_mode = "a" if args.resume else "w"
    n_ok = 0
    n_err = 0
    t0 = time.time()
    write_lock = threading.Lock()

    fh_out = OUT.open(out_mode, encoding="utf-8")
    fh_log = LOG.open(log_mode, encoding="utf-8")

    def process_one(cluster: dict) -> tuple[bool, str]:
        ours = cluster["ours_code"]
        master = cluster["master_code"]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": cluster_user_prompt(cluster)},
        ]
        try:
            resp = call_deepseek(api_key, messages)
            decision = json.loads(resp)
            decision["ours_code"] = ours
            decision["master_code"] = master
            decision["n_total_skus"] = cluster["n_total_skus"]
            line_out = json.dumps(decision, ensure_ascii=False) + "\n"
            rule = decision.get("rule", "?")
            conf = decision.get("confidence", 0)
            log_line = (f"OK ours={ours} master={master} rule={rule} "
                        f"conf={conf:.2f} n={cluster['n_total_skus']}")
            with write_lock:
                fh_out.write(line_out)
                fh_out.flush()
                fh_log.write(log_line + "\n")
                fh_log.flush()
            return (True, log_line)
        except (urllib.error.HTTPError, urllib.error.URLError,
                json.JSONDecodeError, KeyError, TimeoutError, ValueError) as e:
            log_line = f"ERR ours={ours} master={master}: {e}"
            with write_lock:
                fh_log.write(log_line + "\n")
                fh_log.flush()
            return (False, log_line)

    if args.workers <= 1:
        # Sequential path (preserve original behavior for debugging)
        for i, cluster in enumerate(pending, 1):
            ok, _ = process_one(cluster)
            if ok: n_ok += 1
            else:
                n_err += 1
                time.sleep(1)
            if i % 25 == 0 or i == len(pending):
                elapsed = time.time() - t0
                rate = i / elapsed if elapsed else 0
                eta = (len(pending) - i) / rate if rate else 0
                print(f"  [{i}/{len(pending)}] ok={n_ok} err={n_err} "
                      f"rate={rate:.1f}/s eta={eta/60:.1f}min", flush=True)
    else:
        # Concurrent path with workers
        print(f"  running with {args.workers} concurrent workers")
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(process_one, c): c for c in pending}
            done = 0
            for fut in as_completed(futures):
                done += 1
                ok, _ = fut.result()
                if ok: n_ok += 1
                else:  n_err += 1
                if done % 50 == 0 or done == len(pending):
                    elapsed = time.time() - t0
                    rate = done / elapsed if elapsed else 0
                    eta = (len(pending) - done) / rate if rate else 0
                    print(f"  [{done}/{len(pending)}] ok={n_ok} err={n_err} "
                          f"rate={rate:.1f}/s eta={eta/60:.1f}min", flush=True)

    fh_out.close()
    fh_log.close()

    print(f"  done: {n_ok} ok, {n_err} errors")
    print(f"  decisions -> {OUT}")
    print(f"  log       -> {LOG}")


if __name__ == "__main__":
    main()
