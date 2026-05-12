"""Gate and apply staged ESHA audit patches.

This validates staged patches before any source file can be touched. `--apply`
only runs after file-scope checks and `git apply --check` pass.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN_FILES = {"implementation/approved_normalization_rules.csv"}
ALLOWED_GLOBS = [
    "implementation/esha_contracts/reviewed_*.py",
    "implementation/surface_lab_calculator.py",
    "implementation/build_top_ingredient_coverage_audit.py",
    "implementation/tests/test_top2500_cleanup_regressions.py",
    "implementation/output/**",
    "implementation/*.md",
]


def normalize_patch_path(path: str) -> str | None:
    path = path.strip()
    if path == "/dev/null":
        return None
    if path.startswith("a/") or path.startswith("b/"):
        path = path[2:]
    return path


def touched_files(patch_text: str) -> list[str]:
    paths: set[str] = set()
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            for raw in parts[2:4]:
                path = normalize_patch_path(raw)
                if path:
                    paths.add(path)
        elif line.startswith("--- ") or line.startswith("+++ "):
            raw = line[4:].split("\t", 1)[0]
            path = normalize_patch_path(raw)
            if path:
                paths.add(path)
    return sorted(paths)


def is_allowed(path: str) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in ALLOWED_GLOBS)


def patch_path_from_args(args: argparse.Namespace) -> Path:
    if args.patch:
        return Path(args.patch)
    if args.bundle_dir:
        return Path(args.bundle_dir) / "proposal.patch"
    raise SystemExit("provide --patch or --bundle-dir")


def run_patch_command(args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        args,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "command": args,
    }


def run_git_apply_check(patch_path: Path) -> dict[str, Any]:
    if shutil.which("git"):
        return run_patch_command(["git", "apply", "--check", str(patch_path)])
    if shutil.which("patch"):
        return run_patch_command(["patch", "--dry-run", "-p1", "-i", str(patch_path)])
    return {
        "ok": False,
        "returncode": 127,
        "stdout": "",
        "stderr": "neither git nor patch is installed",
        "command": [],
    }


def run_git_apply(patch_path: Path) -> dict[str, Any]:
    if shutil.which("git"):
        return run_patch_command(["git", "apply", str(patch_path)])
    if shutil.which("patch"):
        return run_patch_command(["patch", "-p1", "-i", str(patch_path)])
    return {
        "ok": False,
        "returncode": 127,
        "stdout": "",
        "stderr": "neither git nor patch is installed",
        "command": [],
    }


def validate_patch(patch_path: Path, run_apply_check: bool) -> dict[str, Any]:
    patch_text = patch_path.read_text(encoding="utf-8", errors="replace")
    files = touched_files(patch_text)
    forbidden = [path for path in files if path in FORBIDDEN_FILES]
    disallowed = [path for path in files if path not in forbidden and not is_allowed(path)]

    report: dict[str, Any] = {
        "patch_path": str(patch_path),
        "touched_files": files,
        "forbidden_files": forbidden,
        "disallowed_files": disallowed,
        "allowed_globs": ALLOWED_GLOBS,
        "preflight_ok": not forbidden and not disallowed,
    }

    if run_apply_check and report["preflight_ok"]:
        report["git_apply_check"] = run_git_apply_check(patch_path)
        report["preflight_ok"] = report["preflight_ok"] and report["git_apply_check"]["ok"]
    elif run_apply_check:
        report["git_apply_check"] = {"ok": False, "skipped": "file_scope_preflight_failed"}

    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gate and apply staged ESHA audit patch")
    parser.add_argument("--bundle-dir")
    parser.add_argument("--patch")
    parser.add_argument("--git-apply-check", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--out")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    patch_path = patch_path_from_args(args)
    report = validate_patch(patch_path, args.git_apply_check or args.apply)
    if args.apply:
        if report["preflight_ok"]:
            report["git_apply"] = run_git_apply(patch_path)
            report["applied"] = report["git_apply"]["ok"]
        else:
            report["applied"] = False
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
