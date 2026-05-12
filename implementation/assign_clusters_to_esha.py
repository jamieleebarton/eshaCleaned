from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

import pandas as pd

import cluster_spine_common as common
import self_heal_policy as policy


OUT_CSV = common.CLUSTER_ASSIGNMENTS_CSV
OUT_JSON = common.OUT_DIR / "cluster_to_esha_assignments_summary.json"
MAX_FILTERED_POOL = 350


def build_idf(spine: pd.DataFrame) -> dict[str, float]:
    docfreq: Counter[str] = Counter()
    for _, row in spine.iterrows():
        terms = set(common.split_terms(row.get("all_terms", ""))) | set(common.split_terms(row.get("meaningful_terms", "")))
        for term in terms:
            docfreq[term] += 1
    n = max(len(spine), 1)
    return {term: math.log((1 + n) / (1 + df)) + 1.0 for term, df in docfreq.items()}


def build_head_index(spine: pd.DataFrame) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for idx, row in spine.iterrows():
        out.setdefault(str(row.get("esha_head_norm") or ""), []).append(idx)
    return out


def build_term_sets(spine: pd.DataFrame) -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    for idx, row in spine.iterrows():
        out[idx] = (
            set(common.split_terms(row.get("meaningful_terms", "")))
            | set(common.split_terms(row.get("identity_terms", "")))
            | set(common.split_terms(row.get("subtype_keys", "")))
        )
    return out


def build_supports(spine: pd.DataFrame) -> dict[int, int]:
    out: dict[int, int] = {}
    for idx, row in spine.iterrows():
        try:
            out[idx] = int(float(row.get("category_support") or 0))
        except ValueError:
            out[idx] = 0
    return out


def pool_for_targets(target_heads: str, spine: pd.DataFrame, head_index: dict[str, list[int]]) -> list[int]:
    heads = [h for h in str(target_heads or "").split("|") if h]
    norms = policy.head_norms_for_targets(heads)
    out: list[int] = []
    for head in norms:
        out.extend(head_index.get(head, []))
    seen: set[int] = set()
    deduped: list[int] = []
    for idx in out:
        if idx not in seen:
            seen.add(idx)
            deduped.append(idx)
    return deduped


def _assigned_payload(score: float, second: float, reason: str, cand: pd.Series, pool_size: int, confidence: str) -> dict[str, object]:
    return {
        "assignment_status": "assigned",
        "assignment_confidence": confidence,
        "assignment_reason": f"{reason};margin={score - second:.3f}",
        "candidate_pool_size": pool_size,
        "assigned_esha_code": cand["esha_code"],
        "assigned_esha_description": cand["esha_description"],
        "assigned_esha_head": cand["esha_head"],
        "assigned_esha_family": cand["esha_family"],
        "assignment_score": round(score, 4),
        "second_best_score": round(second, 4),
    }


def _dominant_current_count(cluster: pd.Series, current_code: str) -> int:
    for item in str(cluster.get("top_current_codes") or "").split(" | "):
        if not item or ":" not in item:
            continue
        code, count = item.split(":", 1)
        if code.strip().split(".")[0] == current_code:
            try:
                return int(float(count))
            except ValueError:
                return 0
    return 0


def choose_assignment(
    cluster: pd.Series,
    spine: pd.DataFrame,
    pool: list[int],
    pool_set: set[int],
    idf: dict[str, float],
    spine_by_code: dict[str, int],
    term_sets: dict[int, set[str]],
    supports: dict[int, int],
) -> dict[str, object]:
    if not pool:
        return {
            "assignment_status": "unassigned",
            "assignment_reason": "no_candidate_pool_for_target_heads",
        }
    current_code = str(cluster.get("dominant_current_code") or "").split(".")[0].strip()
    evidence = common.cluster_tokens(cluster)
    if current_code and current_code in spine_by_code:
        current_idx = spine_by_code[current_code]
        current = spine.iloc[current_idx]
        target_heads = str(cluster.get("target_heads") or "").split("|")
        overlap = evidence & term_sets.get(current_idx, set())
        if (
            current_idx in pool_set
            and overlap
            and policy.head_matches_targets(target_heads, str(current.get("esha_head") or ""))
            and not common.hard_reject_cluster_candidate(cluster, current)
        ):
            support = _dominant_current_count(cluster, current_code)
            score = 32.0 + min(8.0, support ** 0.5 / 2.0) + min(8.0, len(overlap) * 2.0)
            reason = (
                f"kept_cluster_current_fast;head={current.get('esha_head')};"
                f"overlap={len(overlap)};current_support={support}"
            )
            return _assigned_payload(score, 0.0, reason, current, 1, "high")

        if current_idx in pool_set:
            result = common.score_cluster_candidate(cluster, current, idf)
            if result is not None:
                score, reason = result
                if score >= 30.0:
                    return _assigned_payload(score, 0.0, "kept_cluster_current;" + reason, current, 1, "high")

    filtered = [idx for idx in pool if evidence & term_sets.get(idx, set())]
    if filtered:
        pool = filtered
        if len(pool) > MAX_FILTERED_POOL:
            pool = sorted(
                pool,
                key=lambda idx: (len(evidence & term_sets.get(idx, set())), supports.get(idx, 0)),
                reverse=True,
            )[:MAX_FILTERED_POOL]
    elif len(pool) > 200:
        return {
            "assignment_status": "unassigned",
            "assignment_reason": "no_evidence_overlap_in_large_pool",
            "candidate_pool_size": len(pool),
        }
    scored: list[tuple[float, str, pd.Series]] = []
    rejects = Counter()
    for idx in pool:
        cand = spine.iloc[idx]
        result = common.score_cluster_candidate(cluster, cand, idf)
        if result is None:
            rejects["score_filtered"] += 1
            continue
        score, reason = result
        scored.append((score, reason, cand))
    if not scored:
        return {
            "assignment_status": "unassigned",
            "assignment_reason": "no_candidate_survived:" + common.top_counts((r for r, n in rejects.items() for _ in range(n)), 5),
            "candidate_pool_size": len(pool),
        }
    scored.sort(key=lambda x: (x[0], int(float(x[2].get("category_support") or 0))), reverse=True)
    best_score, reason, best = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    margin = best_score - second
    min_score = 18.0
    if best_score < min_score:
        return {
            "assignment_status": "unassigned",
            "assignment_reason": f"best_score_below_threshold:{best_score:.3f}",
            "candidate_pool_size": len(pool),
            "best_rejected_code": best["esha_code"],
            "best_rejected_description": best["esha_description"],
            "best_rejected_score": round(best_score, 4),
        }
    confidence = "high" if best_score >= 30.0 and margin >= 1.0 else "medium" if best_score >= 24.0 else "low"
    if confidence == "low":
        return {
            "assignment_status": "unassigned",
            "assignment_reason": f"low_confidence:{best_score:.3f};margin={margin:.3f}",
            "candidate_pool_size": len(pool),
            "best_rejected_code": best["esha_code"],
            "best_rejected_description": best["esha_description"],
            "best_rejected_score": round(best_score, 4),
        }
    return _assigned_payload(best_score, second, reason, best, len(pool), confidence)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spine", type=Path, default=common.ESHA_SPINE_CSV)
    parser.add_argument("--clusters", type=Path, default=common.PRODUCT_CLUSTERS_CSV)
    parser.add_argument("--output", type=Path, default=OUT_CSV)
    args = parser.parse_args()

    print("loading spine/clusters", flush=True)
    spine = common.load_spine(args.spine)
    clusters = common.load_clusters(args.clusters)
    idf = build_idf(spine)
    head_index = build_head_index(spine)
    term_sets = build_term_sets(spine)
    supports = build_supports(spine)
    spine_by_code = {str(r["esha_code"]): i for i, r in spine.iterrows()}
    pool_set_cache: dict[str, set[int]] = {}
    pool_cache: dict[str, list[int]] = {}
    rows: list[dict[str, object]] = []
    for i, cluster in clusters.iterrows():
        if (i + 1) % 5000 == 0:
            print(f"  assigned clusters: {i + 1:,}/{len(clusters):,}", flush=True)
        target_heads = str(cluster.get("target_heads") or "")
        pool = pool_cache.get(target_heads)
        if pool is None:
            pool = pool_for_targets(target_heads, spine, head_index)
            pool_cache[target_heads] = pool
            pool_set_cache[target_heads] = set(pool)
        decision = choose_assignment(cluster, spine, pool, pool_set_cache[target_heads], idf, spine_by_code, term_sets, supports)
        rows.append(
            {
                **{k: cluster.get(k, "") for k in clusters.columns},
                **decision,
            }
        )
    out = pd.DataFrame(rows)
    out.to_csv(args.output, index=False)
    assigned = out[out["assignment_status"] == "assigned"].copy()
    summary = {
        "spine": str(args.spine),
        "clusters": str(args.clusters),
        "output": str(args.output),
        "clusters_total": int(len(out)),
        "clusters_assigned": int(len(assigned)),
        "products_total": int(out["n_products"].astype(int).sum()),
        "products_assigned": int(assigned["n_products"].astype(int).sum()) if len(assigned) else 0,
        "status_counts": out["assignment_status"].value_counts().to_dict(),
        "confidence_counts": out.get("assignment_confidence", pd.Series(dtype=str)).value_counts().to_dict(),
        "top_assigned_heads": assigned["assigned_esha_head"].value_counts().head(40).to_dict() if len(assigned) else {},
        "top_unassigned_reasons": out.loc[out["assignment_status"] != "assigned", "assignment_reason"].value_counts().head(40).to_dict(),
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
