"""Kroger search tool for DeepSeek tool-calling.

Stdlib-only. On missing access token or HTTP error, returns []. The caller
(Task 8) handles tool-call budgeting and retries; this wrapper is
intentionally deterministic so the LLM gets a stable contract.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ruvs.schemas import ProductCandidate

KROGER_TOOL_SCHEMA = {
    "name": "kroger_search",
    "description": (
        "Search Kroger for products matching a query. Returns up to `limit` "
        "candidates with UPC, title, grams, and price."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 25},
        },
        "required": ["query"],
    },
}


def _http_get(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 (stdlib only)
        return json.loads(resp.read().decode("utf-8"))


def kroger_search(query: str, limit: int = 10) -> list[ProductCandidate]:
    """Search Kroger and return ProductCandidate list. Returns [] on error."""
    token = os.environ.get("KROGER_ACCESS_TOKEN")
    if not token:
        return []
    qs = urllib.parse.urlencode({"filter.term": query, "filter.limit": limit})
    url = f"https://api.kroger.com/v1/products?{qs}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        data = _http_get(url, headers=headers)
    except (urllib.error.URLError, RuntimeError, TimeoutError):
        return []
    out: list[ProductCandidate] = []
    for prod in (data.get("data") or [])[:limit]:
        items = prod.get("items") or []
        price = 0.0
        if items and isinstance(items[0], dict):
            price = float(((items[0].get("price") or {}).get("regular") or 0.0))
        out.append(
            ProductCandidate(
                upc=str(prod.get("upc", "")),
                title=str(prod.get("description", "")),
                grams=0.0,  # kroger size field is text; parsed separately
                price_cents=int(round(price * 100)),
                retail="kroger",
                raw=prod,
            )
        )
    return out
