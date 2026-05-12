#!/usr/bin/env python3
"""Upload and verify audit artifacts in Cloudflare R2 via the AWS CLI.

Credentials are read from environment variables or an optional local env file.
No credentials are printed, persisted by this script, or required in repo files.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


AUTH_ENV = ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_ENDPOINT_URL")
BUCKET_ENV = AUTH_ENV + ("R2_BUCKET",)
DEFAULT_ARTIFACTS = [
    "audit_results/concept_package_class_audit_2026-05-11.json",
    "audit_results/picked_recipe_audit_r4_at_r5_line_class_findings.json",
    "audit_results/picked_recipe_audit_r4_at_r5_line_class_findings.csv",
    "planner/data/config_runs/p4_2000_thrifty_l75_p15_final_lineclass.json",
    "planner/data/config_runs/p4_2000_thrifty_l75_p15_final_lineclass.audit.json",
    "planner/data/config_runs/p4_2000_thrifty_l75_p15_final_lineclass.form_facet_audit.json",
    "planner/data/config_runs/p4_2000_thrifty_l75_p15_final_lineclass.multipacks.csv",
]


def load_env_file(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"env file not found: {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_env_stdin() -> None:
    """Read KEY=VALUE lines from stdin until a blank line."""
    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            break
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def require_env(required: tuple[str, ...]) -> dict[str, str]:
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise SystemExit(
            "missing required env vars: "
            + ", ".join(missing)
            + "\ncopy .env.r2.example to .env.r2.local, fill it, then pass --env-file .env.r2.local"
        )
    return {key: os.environ[key] for key in set(required) | {"R2_BUCKET"} if os.environ.get(key)}


def aws_env(cfg: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"] = cfg["R2_ACCESS_KEY_ID"]
    env["AWS_SECRET_ACCESS_KEY"] = cfg["R2_SECRET_ACCESS_KEY"]
    env.setdefault("AWS_EC2_METADATA_DISABLED", "true")
    return env


def aws_cmd(cfg: dict[str, str], args: list[str]) -> list[str]:
    return [
        "aws",
        "--endpoint-url",
        cfg["R2_ENDPOINT_URL"],
        *args,
    ]


def run(cfg: dict[str, str], args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        aws_cmd(cfg, args),
        env=aws_env(cfg),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def require_aws() -> None:
    if shutil.which("aws"):
        return
    raise SystemExit("aws CLI not found; install awscli or add it to PATH")


def object_uri(cfg: dict[str, str], key: str) -> str:
    return f"s3://{cfg['R2_BUCKET']}/{key.lstrip('/')}"


def normalize_prefix(prefix: str) -> str:
    prefix = prefix.strip("/")
    return f"{prefix}/" if prefix else ""


def upload(cfg: dict[str, str], paths: list[Path], prefix: str, dry_run: bool) -> None:
    prefix_norm = normalize_prefix(prefix)
    for path in paths:
        if not path.exists() or not path.is_file():
            raise SystemExit(f"artifact not found: {path}")
        key = f"{prefix_norm}{path.as_posix()}"
        uri = object_uri(cfg, key)
        if dry_run:
            print(f"DRY-RUN upload {path} -> {uri}")
            continue
        result = run(cfg, ["s3", "cp", str(path), uri, "--only-show-errors"])
        if result.returncode != 0:
            sys.stderr.write(result.stderr)
            raise SystemExit(result.returncode)
        print(f"uploaded {path} -> {uri}")


def verify(cfg: dict[str, str], paths: list[Path], prefix: str) -> None:
    prefix_norm = normalize_prefix(prefix)
    for path in paths:
        key = f"{prefix_norm}{path.as_posix()}"
        uri = object_uri(cfg, key)
        result = run(cfg, ["s3", "ls", uri])
        if result.returncode != 0:
            sys.stderr.write(result.stderr)
            raise SystemExit(result.returncode)
        print(f"verified {uri}")


def list_bucket(cfg: dict[str, str], prefix: str) -> None:
    uri = object_uri(cfg, normalize_prefix(prefix))
    result = run(cfg, ["s3", "ls", uri])
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    print(result.stdout.rstrip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("buckets", "check", "upload", "verify", "list"))
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--stdin-env", action="store_true")
    parser.add_argument("--prefix", default=os.environ.get("R2_PREFIX", "esha-audit-bundle"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("artifacts", nargs="*", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.env_file:
        load_env_file(args.env_file)
    if args.stdin_env:
        load_env_stdin()
    require_aws()
    cfg = require_env(AUTH_ENV if args.command == "buckets" else BUCKET_ENV)
    paths = args.artifacts or [Path(p) for p in DEFAULT_ARTIFACTS]

    if args.command == "buckets":
        if args.dry_run:
            print("DRY-RUN list buckets")
            return
        result = run(cfg, ["s3", "ls"])
        if result.returncode != 0:
            sys.stderr.write(result.stderr)
            raise SystemExit(result.returncode)
        print(result.stdout.rstrip())
    elif args.command == "check":
        if args.dry_run:
            print(f"DRY-RUN check s3://{cfg['R2_BUCKET']}")
            return
        result = run(cfg, ["s3", "ls", f"s3://{cfg['R2_BUCKET']}"])
        if result.returncode != 0:
            sys.stderr.write(result.stderr)
            raise SystemExit(result.returncode)
        print("R2 credentials and bucket access: OK")
    elif args.command == "upload":
        upload(cfg, paths, args.prefix, args.dry_run)
    elif args.command == "verify":
        if args.dry_run:
            print("DRY-RUN verify artifacts")
            return
        verify(cfg, paths, args.prefix)
    elif args.command == "list":
        if args.dry_run:
            print(f"DRY-RUN list {object_uri(cfg, normalize_prefix(args.prefix))}")
            return
        list_bucket(cfg, args.prefix)


if __name__ == "__main__":
    main()
