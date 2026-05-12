"""Small JSON API for ESHA MD-card audit workers.

This intentionally uses only the Python standard library so the EC2 worker can
run it without changing the production Hestia API container.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from esha_audit_toolkit import (
    NEBIUS_AUDIT_OUT,
    all_cards,
    compare_nutrient_fingerprint,
    contract_sources,
    cross_reference,
    get_card,
    matrix_slice,
    packet_for_code,
    prior_decisions,
    product_codes,
    product_collisions,
    queue_next,
    recipe_context,
    search_products,
    stage_patch,
    surface_packet,
    trace_entity,
)


ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "implementation" / "esha_patch_gate.py"


def as_int(value: str | None, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def first(query: dict[str, list[str]], name: str, default: str | None = None) -> str | None:
    values = query.get(name)
    return values[0] if values else default


def command_result(args: list[str]) -> dict[str, object]:
    proc = subprocess.run(
        args,
        cwd=ROOT,
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


def gate_bundle(bundle_id: str, apply: bool) -> dict[str, object]:
    bundle_dir = NEBIUS_AUDIT_OUT / bundle_id
    args = ["python3", str(GATE), "--bundle-dir", str(bundle_dir)]
    if apply:
        args.append("--apply")
    else:
        args.append("--git-apply-check")
    result = command_result(args)
    parsed = None
    if result["stdout"]:
        try:
            parsed = json.loads(str(result["stdout"]))
        except json.JSONDecodeError:
            parsed = None
    result["report"] = parsed
    return result


class AuditHandler(BaseHTTPRequestHandler):
    server_version = "EshaAuditAPI/0.1"

    def _auth_ok(self) -> bool:
        expected = os.getenv("ESHA_AUDIT_API_KEY")
        if not expected:
            return True
        return self.headers.get("X-ESHA-Audit-Key") == expected

    def _read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def _write(self, status: int, payload: object) -> None:
        data = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _require_auth(self) -> bool:
        if self._auth_ok():
            return True
        self._write(401, {"error": "unauthorized"})
        return False

    def do_GET(self) -> None:
        if not self._require_auth():
            return
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/health":
                self._write(200, {"status": "ok", "root": str(ROOT)})
            elif parsed.path == "/queue":
                priorities = set(query.get("priority", [])) or None
                self._write(
                    200,
                    queue_next(
                        limit=as_int(first(query, "limit"), 20),
                        priorities=priorities,
                        issue_class=first(query, "issue_class"),
                        status=first(query, "status", "todo"),
                    ),
                )
            elif parsed.path == "/cards":
                self._write(
                    200,
                    all_cards(
                        limit=as_int(first(query, "limit"), 50),
                        offset=as_int(first(query, "offset"), 0),
                        family=first(query, "family"),
                    ),
                )
            elif parsed.path == "/card":
                self._write(
                    200,
                    get_card(
                        int(first(query, "esha_code") or first(query, "code") or "0"),
                        max_chars=as_int(first(query, "max_chars"), 60000),
                    ),
                )
            elif parsed.path == "/packet":
                code = first(query, "esha_code") or first(query, "code")
                if code:
                    self._write(
                        200,
                        packet_for_code(
                            int(code),
                            max_card_chars=as_int(first(query, "max_card_chars"), 60000),
                            crossref_limit=as_int(first(query, "crossref_limit"), 50),
                            product_limit=as_int(first(query, "product_limit"), 25),
                        ),
                    )
                    return
                item = first(query, "item")
                if not item:
                    self._write(400, {"error": "missing_item_or_code"})
                    return
                self._write(
                    200,
                    surface_packet(
                        item,
                        max_card_chars=as_int(first(query, "max_card_chars"), 60000),
                        crossref_limit=as_int(first(query, "crossref_limit"), 50),
                        product_limit=as_int(first(query, "product_limit"), 25),
                    ),
                )
            elif parsed.path == "/packet-code":
                self._write(
                    200,
                    packet_for_code(
                        int(first(query, "esha_code") or first(query, "code") or "0"),
                        max_card_chars=as_int(first(query, "max_card_chars"), 60000),
                        crossref_limit=as_int(first(query, "crossref_limit"), 50),
                        product_limit=as_int(first(query, "product_limit"), 25),
                    ),
                )
            elif parsed.path == "/search-products":
                q = first(query, "q") or first(query, "query")
                if not q:
                    self._write(400, {"error": "missing_query"})
                    return
                self._write(
                    200,
                    search_products(
                        q,
                        limit=as_int(first(query, "limit"), 25),
                        category=first(query, "category"),
                    ),
                )
            elif parsed.path == "/cross-reference":
                self._write(
                    200,
                    cross_reference(
                        int(first(query, "esha_code") or first(query, "code") or "0"),
                        limit=as_int(first(query, "limit"), 100),
                    ),
                )
            elif parsed.path == "/matrix":
                self._write(
                    200,
                    matrix_slice(
                        int(first(query, "esha_code") or first(query, "code") or "0"),
                        limit=as_int(first(query, "limit"), 100),
                        rebuild=(first(query, "rebuild") or "").lower() in {"1", "true", "yes"},
                    ),
                )
            elif parsed.path == "/product-codes":
                self._write(
                    200,
                    product_codes(
                        limit=as_int(first(query, "limit"), 50),
                        gtin=first(query, "gtin"),
                        esha_code=first(query, "esha_code") or first(query, "code"),
                        collision_status=first(query, "collision_status"),
                        q=first(query, "q") or first(query, "query"),
                    ),
                )
            elif parsed.path == "/collisions":
                self._write(
                    200,
                    product_collisions(
                        limit=as_int(first(query, "limit"), 50),
                        esha_code=first(query, "esha_code") or first(query, "code"),
                    ),
                )
            elif parsed.path == "/contract":
                self._write(
                    200,
                    contract_sources(
                        int(first(query, "esha_code") or first(query, "code") or "0"),
                        max_chars=as_int(first(query, "max_chars"), 60000),
                    ),
                )
            elif parsed.path == "/nutrient-compare":
                codes_raw = first(query, "codes") or ""
                codes = [int(c) for c in codes_raw.split(",") if c.strip()]
                self._write(200, compare_nutrient_fingerprint(codes))
            elif parsed.path == "/recipe-context":
                rid = int(first(query, "recipe_id") or "0")
                self._write(200, recipe_context(rid))
            elif parsed.path == "/prior-decisions":
                item = first(query, "normalized_item") or ""
                self._write(200, prior_decisions(item))
            elif parsed.path == "/trace":
                kind = first(query, "kind") or ""
                key = first(query, "key") or ""
                if not kind or not key:
                    self._write(400, {"error": "missing_kind_or_key"})
                    return
                self._write(200, trace_entity(kind, key, limit=as_int(first(query, "limit"), 50)))
            else:
                self._write(404, {"error": "not_found", "path": parsed.path})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "message": str(exc)})

    def do_POST(self) -> None:
        if not self._require_auth():
            return
        parsed = urlparse(self.path)
        try:
            body = self._read_json()
            if parsed.path == "/stage-patch":
                with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
                    json.dump(body, f, indent=2, ensure_ascii=False)
                    bundle_path = f.name
                try:
                    self._write(200, stage_patch(bundle_path))
                finally:
                    Path(bundle_path).unlink(missing_ok=True)
            elif parsed.path == "/validate-patch":
                bundle_id = str(body.get("bundle_id") or "")
                if not bundle_id:
                    self._write(400, {"error": "missing_bundle_id"})
                    return
                self._write(200, gate_bundle(bundle_id, apply=False))
            elif parsed.path == "/apply-patch":
                bundle_id = str(body.get("bundle_id") or "")
                if not bundle_id:
                    self._write(400, {"error": "missing_bundle_id"})
                    return
                self._write(200, gate_bundle(bundle_id, apply=True))
            elif parsed.path == "/refresh-code":
                code = str(body.get("esha_code") or body.get("code") or "")
                if not code:
                    self._write(400, {"error": "missing_esha_code"})
                    return
                max_products = str(body.get("max_products") or 160)
                product_limit = str(body.get("product_limit") or 1000)
                matrix_dir = ROOT / "implementation" / "output" / "esha_cleanup_matrix_slices"
                matrix_dir.mkdir(parents=True, exist_ok=True)
                matrix_csv = matrix_dir / f"{code}.csv"
                matrix_summary = matrix_dir / f"{code}.md"
                build_card = command_result(
                    [
                        "python3",
                        "implementation/build_esha_code_query_packs.py",
                        "--code",
                        code,
                        "--max-products",
                        max_products,
                        ]
                    )
                update = None
                matrix = None
                if build_card["ok"]:
                    update = command_result(
                        [
                            "python3",
                            "implementation/update_single_esha_product_assignments.py",
                            "--code",
                            code,
                            "--limit",
                            product_limit,
                        ]
                    )
                if build_card["ok"]:
                    matrix = command_result(
                        [
                            "python3",
                            "implementation/build_esha_cleanup_matrix.py",
                            "--code",
                            code,
                            "--out-csv",
                            str(matrix_csv),
                            "--out-summary",
                            str(matrix_summary),
                        ]
                    )
                self._write(
                    200,
                    {
                        "esha_code": code,
                        "build_card": build_card,
                        "update_product_codes": update,
                        "update_matrix": matrix,
                        "matrix_csv": str(matrix_csv),
                        "matrix_summary": str(matrix_summary),
                        "ok": bool(build_card["ok"] and update and update["ok"] and matrix and matrix["ok"]),
                    },
                )
            else:
                self._write(404, {"error": "not_found", "path": parsed.path})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "message": str(exc)})

    def log_message(self, fmt: str, *args: object) -> None:
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve ESHA audit JSON tools")
    parser.add_argument("--host", default=os.getenv("ESHA_AUDIT_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("ESHA_AUDIT_PORT", "8765")))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), AuditHandler)
    print(f"ESHA audit API listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
