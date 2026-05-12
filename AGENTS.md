# Repository Guidelines

## Project Structure & Module Organization

This repository is a Python/data audit bundle for ESHA product mapping and nutrition validation. Root-level `*.py` files are mostly historical or one-off audit/fix passes. Active scripts and shared modules live in `implementation/`; generated artifacts generally belong in `implementation/output/`. Unit tests live in `implementation/tests/` and use import paths from the repository root. Retail taxonomy work lives in `retail_mapper/`, with newer cleanup work under `retail_mapper/v2/`. Graph ingestion, Kuzu data, diagnostics, and explorer queries live in `graph/`. Source datasets are under `data/`; design notes and plans are in `docs/`.

## Build, Test, and Development Commands

Run commands from the repository root.

- `python3 -m unittest discover -s implementation/tests -p 'test*.py' -v` runs the full test suite.
- `python3 -m unittest implementation.tests.test_build_product_to_best_esha_full_map -v` runs a focused regression file.
- `python3 implementation/build_product_to_best_esha_full_map.py` regenerates the main product-to-ESHA map.
- `python3 implementation/build_release_blocker_queue.py` rebuilds release-blocking queues.
- `python3 graph/ingest/build_kuzu_graph.py` rebuilds the graph database when graph inputs change.
- `python3 graph/queries/build_graph_explorer.py` regenerates the interactive graph explorer.
- `pip install -r requirements-graph.txt` installs graph/explorer-only dependencies.

## Coding Style & Naming Conventions

Use Python 3, four-space indentation, and `snake_case` for functions, variables, files, and CSV columns. Prefer small pure functions plus `argparse` entry points guarded by `if __name__ == "__main__":`. Name scripts by action, such as `build_*`, `audit_*`, `apply_*`, or `test_*`. Use `pathlib.Path`, `csv`, `json`, and structured parsing over ad hoc string handling. Write generated outputs to `implementation/output/`, `graph/review/`, or another scoped output directory; avoid overwriting source datasets in `data/`.

## Testing Guidelines

Tests use standard-library `unittest`. Name files `test_<module_or_flow>.py` and keep fixtures small enough to run locally. Add focused regression tests for identity-routing, matcher, quarantine, and artifact-schema changes. For broad data rebuilds, pair script output with a targeted test or summary JSON check.

## Commit & Pull Request Guidelines

This checkout has no `.git` history, so commit conventions cannot be inferred locally. Use concise imperative commit messages such as `Fix identity gate for milk routing` or `Add graph explorer smoke test`. Pull requests should describe the changed artifact or pipeline, list commands run, note data files regenerated, and attach screenshots only for explorer/UI changes.

## Security & Data Handling

Do not commit API keys, local credentials, or private model tokens. Treat large CSV/DB artifacts as deliberate outputs: document the command that created them and avoid changing unrelated generated files in the same patch.
