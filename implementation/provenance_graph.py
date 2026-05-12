from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
IMPLEMENTATION_ROOT = ROOT / "implementation"
OUTPUT_ROOT = IMPLEMENTATION_ROOT / "output"
DEFAULT_GRAPH_DB = OUTPUT_ROOT / "provenance_graph.db"

CANONICAL_SURFACE = OUTPUT_ROOT / "canonical_surface_normalized_with_product_proxies_CLEANED.csv"
PACK_INDEX = OUTPUT_ROOT / "esha_code_query_pack_index.csv"
TOP2500_PROGRESS = OUTPUT_ROOT / "top2500_cleanup_progress.csv"
LOOKUP_DB = OUTPUT_ROOT / "product_esha_lookup.db"
REVIEWED_CONTRACT_SPECS = OUTPUT_ROOT / "nebius_contract_decisions" / "reviewed_nebius_generated_specs.json"
CANONICAL_TO_ESHA = IMPLEMENTATION_ROOT / "canonical_to_esha.csv"
ESHA_CANONICAL = ROOT / "esha_cleaned_canonical.csv"


SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edges (
    src_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    dst_id TEXT NOT NULL,
    provenance TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (src_id, edge_type, dst_id)
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_path TEXT PRIMARY KEY,
    artifact_kind TEXT NOT NULL,
    exists_flag INTEGER NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rebuild_dependencies (
    src_kind TEXT NOT NULL,
    src_key TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    reason TEXT NOT NULL,
    PRIMARY KEY (src_kind, src_key, artifact_path, reason)
);
"""


@dataclass(frozen=True)
class GraphCounts:
    node_count: int
    edge_count: int
    artifact_count: int
    dependency_count: int


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _safe_payload(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=None, sort_keys=True, ensure_ascii=False)


def _canonical_id(name: str) -> str:
    return f"canonical:{name.strip().lower()}"


def _esha_id(code: str) -> str:
    return f"esha:{str(code).strip()}"


def _pack_id(code: str) -> str:
    return f"pack:{str(code).strip()}"


def _product_id(gtin: str) -> str:
    return f"product:{str(gtin).strip()}"


def _item_id(name: str) -> str:
    return f"normalized_item:{name.strip().lower()}"


def _contract_id(code: str) -> str:
    return f"contract:{str(code).strip()}"


def node_id_for(kind: str, key: str) -> str:
    key = str(key or "").strip()
    if kind == "canonical":
        return _canonical_id(key)
    if kind == "normalized_item":
        return _item_id(key)
    if kind == "esha_code":
        return _esha_id(key)
    if kind == "gtin":
        return _product_id(key)
    if kind == "pack":
        return _pack_id(key)
    if kind == "contract":
        return _contract_id(key)
    raise ValueError(f"unsupported trace kind: {kind}")


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)


def upsert_node(con: sqlite3.Connection, node_id: str, kind: str, label: str, payload: dict[str, object]) -> None:
    con.execute(
        """
        INSERT INTO nodes(node_id, kind, label, payload_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(node_id) DO UPDATE SET
          kind = excluded.kind,
          label = excluded.label,
          payload_json = excluded.payload_json
        """,
        (node_id, kind, label, _safe_payload(payload)),
    )


def upsert_edge(
    con: sqlite3.Connection,
    src_id: str,
    edge_type: str,
    dst_id: str,
    provenance: str,
    payload: dict[str, object] | None = None,
) -> None:
    con.execute(
        """
        INSERT INTO edges(src_id, edge_type, dst_id, provenance, payload_json)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(src_id, edge_type, dst_id) DO UPDATE SET
          provenance = excluded.provenance,
          payload_json = excluded.payload_json
        """,
        (src_id, edge_type, dst_id, provenance, _safe_payload(payload or {})),
    )


def upsert_artifact(con: sqlite3.Connection, path: Path, kind: str, payload: dict[str, object] | None = None) -> None:
    con.execute(
        """
        INSERT INTO artifacts(artifact_path, artifact_kind, exists_flag, payload_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(artifact_path) DO UPDATE SET
          artifact_kind = excluded.artifact_kind,
          exists_flag = excluded.exists_flag,
          payload_json = excluded.payload_json
        """,
        (str(path), kind, int(path.exists()), _safe_payload(payload or {})),
    )


def add_dependency(con: sqlite3.Connection, src_kind: str, src_key: str, artifact_path: Path, reason: str) -> None:
    con.execute(
        """
        INSERT OR REPLACE INTO rebuild_dependencies(src_kind, src_key, artifact_path, reason)
        VALUES (?, ?, ?, ?)
        """,
        (src_kind, src_key, str(artifact_path), reason),
    )


def _load_reviewed_contract_codes() -> set[str]:
    try:
        import sys

        sys.path.insert(0, str(IMPLEMENTATION_ROOT))
        import esha_contracts  # type: ignore

        contracts = getattr(esha_contracts, "CONTRACTS", {})
        return {str(code).lstrip("0") for code in contracts.keys()}
    except Exception:
        return set()


def _iter_lookup_rows() -> Iterable[dict[str, str]]:
    if not LOOKUP_DB.exists():
        return []
    con = sqlite3.connect(LOOKUP_DB)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT
              gtin_upc,
              COALESCE(product_description, '') AS product_description,
              COALESCE(brand_name, '') AS brand_name,
              COALESCE(branded_food_category, '') AS branded_food_category,
              COALESCE(esha_code_count, '') AS esha_code_count,
              COALESCE(esha_codes, '') AS esha_codes,
              COALESCE(primary_esha_code, '') AS primary_esha_code,
              COALESCE(collision_status, '') AS collision_status
            FROM product_esha_code_rollup
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        con.close()


def build_graph(db_path: Path) -> GraphCounts:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        ensure_schema(con)
        con.execute("DELETE FROM nodes")
        con.execute("DELETE FROM edges")
        con.execute("DELETE FROM artifacts")
        con.execute("DELETE FROM rebuild_dependencies")

        reviewed_contract_codes = _load_reviewed_contract_codes()

        if CANONICAL_SURFACE.exists():
            rows = read_csv(CANONICAL_SURFACE)
            upsert_artifact(con, CANONICAL_SURFACE, "canonical_surface")
            for row in rows:
                canonical = (row.get("canonical_normalized") or "").strip().lower()
                shopping = (row.get("canonical_shopping_item") or "").strip().lower()
                if canonical:
                    upsert_node(
                        con,
                        _canonical_id(canonical),
                        "canonical",
                        canonical,
                        {
                            "record_type": row.get("record_type", ""),
                            "sr28_code": row.get("sr28_code", ""),
                            "fndds_code": row.get("fndds_code", ""),
                            "esha_code": row.get("esha_code", ""),
                            "nutrition_match_state": row.get("nutrition_match_state", ""),
                            "product_proxy_match_state": row.get("product_proxy_match_state", ""),
                        },
                    )
                    add_dependency(con, "canonical", canonical, CANONICAL_SURFACE, "calculator_l0_surface")
                surface = (row.get("canonical_surface") or "").strip().lower()
                if surface and canonical:
                    upsert_node(con, _item_id(surface), "surface", surface, {"record_type": row.get("record_type", "")})
                    upsert_edge(con, _item_id(surface), "normalizes_to", _canonical_id(canonical), str(CANONICAL_SURFACE))
                if shopping and canonical and shopping != canonical:
                    upsert_node(con, _canonical_id(shopping), "shopping_canonical", shopping, {})
                    upsert_edge(con, _canonical_id(canonical), "shops_as", _canonical_id(shopping), str(CANONICAL_SURFACE))
                esha_code = (row.get("esha_code") or "").strip()
                if canonical and esha_code:
                    upsert_node(con, _esha_id(esha_code), "esha_code", esha_code, {"esha_description": row.get("esha_description", "")})
                    upsert_edge(
                        con,
                        _canonical_id(canonical),
                        "maps_to_esha",
                        _esha_id(esha_code),
                        str(CANONICAL_SURFACE),
                        {"esha_match_type": row.get("esha_match_type", "")},
                    )
                    add_dependency(con, "esha_code", esha_code, PACK_INDEX, "canonical_to_esha_affects_pack_selection")

        if CANONICAL_TO_ESHA.exists():
            rows = read_csv(CANONICAL_TO_ESHA)
            upsert_artifact(con, CANONICAL_TO_ESHA, "canonical_to_esha")
            for row in rows:
                canonical = (row.get("canonical_name") or "").strip().lower()
                code = (row.get("esha_code") or "").strip()
                if not canonical or not code:
                    continue
                upsert_node(con, _canonical_id(canonical), "canonical", canonical, {})
                upsert_node(con, _esha_id(code), "esha_code", code, {"esha_description": row.get("esha_description", "")})
                upsert_edge(con, _canonical_id(canonical), "maps_to_esha", _esha_id(code), str(CANONICAL_TO_ESHA))

        if ESHA_CANONICAL.exists():
            rows = read_csv(ESHA_CANONICAL)
            upsert_artifact(con, ESHA_CANONICAL, "esha_canonical")
            for row in rows:
                code = (row.get("EshaCode") or "").strip()
                shopping = (row.get("canonical_shopping_item") or "").strip().lower()
                if not code:
                    continue
                upsert_node(con, _esha_id(code), "esha_code", code, {"description": row.get("Description", "")})
                if shopping:
                    upsert_node(con, _canonical_id(shopping), "esha_canonical_hint", shopping, {})
                    upsert_edge(con, _esha_id(code), "canonical_hint", _canonical_id(shopping), str(ESHA_CANONICAL))
                    add_dependency(con, "esha_code", code, PACK_INDEX, "esha_canonical_hint_affects_pack_query")

        if PACK_INDEX.exists():
            rows = read_csv(PACK_INDEX)
            upsert_artifact(con, PACK_INDEX, "pack_index")
            for row in rows:
                code = (row.get("esha_code") or "").strip()
                if not code:
                    continue
                pack_path = Path(row.get("pack_path") or "")
                upsert_node(
                    con,
                    _pack_id(code),
                    "pack",
                    str(pack_path),
                    {
                        "family": row.get("family", ""),
                        "query": row.get("query", ""),
                        "total_product_matches": row.get("total_product_matches", ""),
                    },
                )
                upsert_node(con, _esha_id(code), "esha_code", code, {"description": row.get("description", "")})
                upsert_edge(con, _esha_id(code), "has_pack", _pack_id(code), str(PACK_INDEX))
                upsert_artifact(con, pack_path, "pack_markdown", {"esha_code": code})
                add_dependency(con, "esha_code", code, pack_path, "rebuild_pack_for_code")
                add_dependency(con, "esha_code", code, TOP2500_PROGRESS, "pack_changes_affect_top2500")

        if TOP2500_PROGRESS.exists():
            rows = read_csv(TOP2500_PROGRESS)
            upsert_artifact(con, TOP2500_PROGRESS, "top2500_progress")
            for row in rows:
                item = (row.get("normalized_item") or "").strip().lower()
                code = (row.get("esha_code") or "").strip()
                if item:
                    upsert_node(
                        con,
                        _item_id(item),
                        "normalized_item",
                        item,
                        {
                            "occurrence_count": row.get("occurrence_count", ""),
                            "issue_class": row.get("issue_class", ""),
                            "check_status": row.get("check_status", ""),
                        },
                    )
                    add_dependency(con, "normalized_item", item, TOP2500_PROGRESS, "launch_queue_view")
                if item and code:
                    upsert_node(con, _esha_id(code), "esha_code", code, {"esha_description": row.get("esha_description", "")})
                    upsert_edge(
                        con,
                        _item_id(item),
                        "launch_maps_to_esha",
                        _esha_id(code),
                        str(TOP2500_PROGRESS),
                        {"issue_class": row.get("issue_class", "")},
                    )

        for row in _iter_lookup_rows():
            gtin = (row.get("gtin_upc") or "").strip()
            if not gtin:
                continue
            upsert_node(
                con,
                _product_id(gtin),
                "product",
                row.get("product_description", "") or gtin,
                {
                    "brand_name": row.get("brand_name", ""),
                    "branded_food_category": row.get("branded_food_category", ""),
                    "collision_status": row.get("collision_status", ""),
                },
            )
            for code in [value for value in (row.get("esha_codes") or "").split("|") if value]:
                upsert_node(con, _esha_id(code), "esha_code", code, {})
                upsert_edge(
                    con,
                    _product_id(gtin),
                    "assigned_to_esha",
                    _esha_id(code),
                    str(LOOKUP_DB),
                    {"primary_esha_code": row.get("primary_esha_code", "")},
                )
                add_dependency(con, "esha_code", code, LOOKUP_DB, "product_assignment_rollup")

        if reviewed_contract_codes:
            upsert_artifact(con, REVIEWED_CONTRACT_SPECS, "reviewed_contract_specs")
            for code in reviewed_contract_codes:
                upsert_node(con, _contract_id(code), "reviewed_contract", code, {})
                upsert_node(con, _esha_id(code), "esha_code", code, {})
                upsert_edge(con, _esha_id(code), "reviewed_by_contract", _contract_id(code), "implementation/esha_contracts")
                add_dependency(con, "esha_code", code, LOOKUP_DB, "contract_changes_affect_assignments")
                add_dependency(con, "esha_code", code, TOP2500_PROGRESS, "contract_changes_affect_launch_queue")

        con.commit()
        return GraphCounts(
            node_count=con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0],
            edge_count=con.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
            artifact_count=con.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0],
            dependency_count=con.execute("SELECT COUNT(*) FROM rebuild_dependencies").fetchone()[0],
        )
    finally:
        con.close()


def trace_entity(kind: str, key: str, db_path: Path = DEFAULT_GRAPH_DB, edge_limit: int = 50) -> dict[str, object]:
    node_id = node_id_for(kind, key)
    if not db_path.exists():
        return {"ok": False, "error": "graph_missing", "graph_db": str(db_path), "node_id": node_id}

    dependency_key = str(key).strip().lower() if kind in {"canonical", "normalized_item"} else str(key).strip()
    edge_limit = max(1, int(edge_limit))
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        node = con.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
        if node is None:
            return {"ok": False, "error": "node_not_found", "graph_db": str(db_path), "node_id": node_id}

        outgoing_count = int(con.execute("SELECT COUNT(*) FROM edges WHERE src_id = ?", (node_id,)).fetchone()[0])
        outgoing = [
            dict(row)
            for row in con.execute(
                """
                SELECT e.src_id, e.edge_type, e.dst_id, e.provenance, e.payload_json,
                       n.kind AS dst_kind, n.label AS dst_label
                FROM edges e
                LEFT JOIN nodes n ON n.node_id = e.dst_id
                WHERE e.src_id = ?
                ORDER BY e.edge_type, e.dst_id
                LIMIT ?
                """,
                (node_id, edge_limit),
            ).fetchall()
        ]
        incoming_count = int(con.execute("SELECT COUNT(*) FROM edges WHERE dst_id = ?", (node_id,)).fetchone()[0])
        incoming = [
            dict(row)
            for row in con.execute(
                """
                SELECT e.src_id, e.edge_type, e.dst_id, e.provenance, e.payload_json,
                       n.kind AS src_kind, n.label AS src_label
                FROM edges e
                LEFT JOIN nodes n ON n.node_id = e.src_id
                WHERE e.dst_id = ?
                ORDER BY e.edge_type, e.src_id
                LIMIT ?
                """,
                (node_id, edge_limit),
            ).fetchall()
        ]
        dependencies = [
            dict(row)
            for row in con.execute(
                """
                SELECT src_kind, src_key, artifact_path, reason
                FROM rebuild_dependencies
                WHERE src_kind = ? AND src_key = ?
                ORDER BY artifact_path, reason
                """,
                (kind, dependency_key),
            ).fetchall()
        ]
        artifact_paths = sorted({row["artifact_path"] for row in dependencies})
        if artifact_paths:
            artifacts = [
                dict(row)
                for row in con.execute(
                    f"SELECT artifact_path, artifact_kind, exists_flag, payload_json FROM artifacts WHERE artifact_path IN ({','.join('?' for _ in artifact_paths)})",
                    artifact_paths,
                ).fetchall()
            ]
        else:
            artifacts = []
        return {
            "ok": True,
            "graph_db": str(db_path),
            "node": dict(node),
            "edge_limit": edge_limit,
            "outgoing_edge_count": outgoing_count,
            "outgoing_edges": outgoing,
            "outgoing_truncated": outgoing_count > len(outgoing),
            "incoming_edge_count": incoming_count,
            "incoming_edges": incoming,
            "incoming_truncated": incoming_count > len(incoming),
            "rebuild_dependencies": dependencies,
            "artifacts": artifacts,
        }
    finally:
        con.close()
