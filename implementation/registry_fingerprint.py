from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

try:
    from resolver_context import DEFAULT_ARTIFACTS
except ModuleNotFoundError:
    from implementation.resolver_context import DEFAULT_ARTIFACTS


FINGERPRINT_VERSION = 1


def canonical_registry_paths() -> list[Path]:
    """Files whose content defines resolver behavior."""

    return [
        DEFAULT_ARTIFACTS.dictionary_csv,
        DEFAULT_ARTIFACTS.supplemental_concepts_csv,
        DEFAULT_ARTIFACTS.approved_normalization_rules_csv,
        DEFAULT_ARTIFACTS.approved_product_contracts_csv,
        DEFAULT_ARTIFACTS.product_family_safety_rules_csv,
        DEFAULT_ARTIFACTS.reviewed_nutrition_anchors_csv,
        DEFAULT_ARTIFACTS.reviewed_density_bridge_csv,
        DEFAULT_ARTIFACTS.reviewed_external_catalog_items_csv,
        DEFAULT_ARTIFACTS.reviewed_household_unit_gram_rules_csv,
        DEFAULT_ARTIFACTS.reviewed_quantity_policies_csv,
        DEFAULT_ARTIFACTS.reviewed_sr28_nutrition_fallbacks_csv,
        DEFAULT_ARTIFACTS.reviewed_to_taste_defaults_csv,
    ]


def file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def file_row_count(path: Path) -> int:
    with path.open("rb") as handle:
        count = sum(1 for _ in handle)
    return max(count - 1, 0)


def registry_fingerprint(paths: Iterable[Path] | None = None) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for path in paths or canonical_registry_paths():
        path = Path(path)
        if not path.exists():
            rows.append(
                {
                    "path": str(path),
                    "exists": False,
                    "rows": None,
                    "mtime_ns": None,
                    "sha256": None,
                }
            )
            continue
        stat = path.stat()
        rows.append(
            {
                "path": str(path),
                "exists": True,
                "rows": file_row_count(path),
                "mtime_ns": stat.st_mtime_ns,
                "sha256": file_digest(path),
            }
        )
    payload = {"version": FINGERPRINT_VERSION, "files": rows}
    payload["fingerprint_id"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return payload


def registry_fingerprint_id(paths: Iterable[Path] | None = None) -> str:
    return str(registry_fingerprint(paths).get("fingerprint_id", ""))


def sidecar_path(output_path: Path) -> Path:
    return output_path.with_suffix(output_path.suffix + ".fingerprint.json")


def write_fingerprint_sidecar(output_path: Path, paths: Iterable[Path] | None = None) -> Path:
    sidecar = sidecar_path(output_path)
    sidecar.write_text(json.dumps(registry_fingerprint(paths), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sidecar


def assert_fingerprint_current(sidecar: Path, paths: Iterable[Path] | None = None) -> None:
    recorded = json.loads(sidecar.read_text(encoding="utf-8"))
    current = registry_fingerprint(paths)
    if recorded.get("fingerprint_id") != current.get("fingerprint_id"):
        raise RuntimeError(
            "Stale generated artifact: registry fingerprint "
            f"{recorded.get('fingerprint_id')} != current {current.get('fingerprint_id')}"
        )
