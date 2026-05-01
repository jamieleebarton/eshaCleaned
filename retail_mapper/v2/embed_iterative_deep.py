#!/usr/bin/env python3
"""Deep iterative centroid refinement — three confidence stages.

Stage A (strict, high-confidence): cur < 0.45, new ≥ 0.70, imp ≥ 0.35
Stage B (moderate):                  cur < 0.55, new ≥ 0.65, imp ≥ 0.25
Stage C (relaxed):                   cur < 0.60, new ≥ 0.60, imp ≥ 0.20

Each stage iterates to convergence before moving to the next. By the time
we hit Stage C, the centroids have been purified by Stages A and B —
borderline cases that look ambiguous now resolve cleanly because their
reference clusters are tight.

This is also a DEEPSEEK VERIFICATION pass — wherever DeepSeek put a SKU
at a path whose centroid the embedding rejects, we move it. Net effect:
both the original cleanup pipeline AND DeepSeek get audited by the
embedding model.

Output: retail_mapper/v2/iterative_deep_reroutes.csv
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
EMB = REPO / "implementation" / ".embed_cache" / "prod_emb.npy"
IDS = REPO / "implementation" / ".embed_cache" / "prod_ids.npy"
AUDIT = V2 / "full_corpus_audit.csv"
OUT = V2 / "iterative_deep_reroutes.csv"

MIN_SKUS_PER_PATH = 10
MAX_ITER_PER_STAGE = 10

STAGES = [
    ("A_strict",   {"cur_max": 0.45, "new_min": 0.70, "imp_min": 0.35}),
    ("B_moderate", {"cur_max": 0.55, "new_min": 0.65, "imp_min": 0.25}),
    ("C_relaxed",  {"cur_max": 0.60, "new_min": 0.60, "imp_min": 0.20}),
]

csv.field_size_limit(sys.maxsize)


def main() -> None:
    print(f"  loading embeddings...")
    prod_emb = np.load(EMB)
    prod_ids = np.load(IDS, allow_pickle=True)
    fdc_to_idx = {str(fid): i for i, fid in enumerate(prod_ids)}

    print(f"  reading audit...")
    fdc_to_path: dict[str, str] = {}
    title_by_fdc: dict[str, str] = {}
    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            fdc = r.get("fdc_id", "")
            cp = r.get("canonical_path", "").strip()
            if not (fdc and cp): continue
            if fdc not in fdc_to_idx: continue
            fdc_to_path[fdc] = cp
            title_by_fdc[fdc] = r.get("title", "")[:100]

    all_moves: list[dict] = []
    seen: set[str] = set()  # fdc_ids already moved across all stages

    for stage_name, params in STAGES:
        print(f"\n=== STAGE {stage_name} (cur<{params['cur_max']}, "
              f"new>={params['new_min']}, imp>={params['imp_min']}) ===")
        for iteration in range(1, MAX_ITER_PER_STAGE + 1):
            # Recompute centroids from current state
            path_to_idxs: dict[str, list[int]] = defaultdict(list)
            for fdc, cp in fdc_to_path.items():
                path_to_idxs[cp].append(fdc_to_idx[fdc])
            path_names: list[str] = []
            centroids: list[np.ndarray] = []
            for path, idxs in path_to_idxs.items():
                if len(idxs) < MIN_SKUS_PER_PATH: continue
                members = prod_emb[idxs]
                c = members.mean(axis=0)
                n = np.linalg.norm(c)
                if n < 1e-6: continue
                path_names.append(path)
                centroids.append(c / n)
            centroid_matrix = np.stack(centroids)
            path_idx_lookup = {p: i for i, p in enumerate(path_names)}

            # Find moves under current stage thresholds
            moves: list[tuple[str, str, float, float, float]] = []
            for fdc, cp in fdc_to_path.items():
                if fdc in seen: continue
                if cp not in path_idx_lookup: continue
                vec = prod_emb[fdc_to_idx[fdc]]
                cur_idx = path_idx_lookup[cp]
                cur_sim = float(vec @ centroid_matrix[cur_idx])
                if cur_sim >= params["cur_max"]: continue
                sims = centroid_matrix @ vec
                sims[cur_idx] = -1
                best = int(np.argmax(sims))
                best_sim = float(sims[best])
                imp = best_sim - cur_sim
                if best_sim >= params["new_min"] and imp >= params["imp_min"]:
                    moves.append((fdc, path_names[best], cur_sim, best_sim, imp))

            if not moves:
                print(f"  iter {iteration}: 0 moves — stage converged.")
                break
            for fdc, new_path, cs, ps, im in moves:
                fdc_to_path[fdc] = new_path
                seen.add(fdc)
                all_moves.append({
                    "stage": stage_name,
                    "iteration": str(iteration),
                    "fdc_id": fdc,
                    "title": title_by_fdc.get(fdc, ""),
                    "old_path": "",  # filled below
                    "new_path": new_path,
                    "current_sim": f"{cs:.3f}",
                    "proposed_sim": f"{ps:.3f}",
                    "improvement": f"{im:+.3f}",
                })
            print(f"  iter {iteration}: {len(moves):,} moves applied")

    # Backfill old_path from initial state — we lost it; reload from audit
    initial_paths: dict[str, str] = {}
    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            initial_paths[r.get("fdc_id", "")] = r.get("canonical_path", "").strip()
    for m in all_moves:
        m["old_path"] = initial_paths.get(m["fdc_id"], "")

    cols = ["stage", "iteration", "fdc_id", "title", "old_path", "new_path",
            "current_sim", "proposed_sim", "improvement"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(all_moves)

    print(f"\n=== TOTAL MOVES: {len(all_moves):,} ===")
    print(f"  by stage:")
    from collections import Counter
    by_stage = Counter(m["stage"] for m in all_moves)
    for stage, n in by_stage.items():
        print(f"    {stage}: {n:,}")
    print(f"  wrote {OUT.name}")


if __name__ == "__main__":
    main()
