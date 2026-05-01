"""Walmart search tool for DeepSeek tool-calling.

Stdlib-only. On missing API key or HTTP error, returns []. The caller (Task 8)
handles tool-call budgeting and retries; this wrapper is intentionally
deterministic so the LLM gets a stable contract.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ruvs.schemas import ProductCandidate

WALMART_TOOL_SCHEMA = {
    "name": "walmart_search",
    "description": (
        "Search Walmart for products matching a query. Returns up to `limit` "
        "candidates with UPC, title, grams, and price. Use to verify whether a "
        "recipe ingredient maps to a real, plain product (not a flavored/breaded/"
        "seasoned variant)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "search term, e.g. 'plain mayonnaise', 'whole ham', 'beef gravy jar'",
            },
            "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 25},
        },
        "required": ["query"],
    },
}


def _http_get(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 (stdlib only)
        return json.loads(resp.read().decode("utf-8"))


def walmart_search(query: str, limit: int = 10) -> list[ProductCandidate]:
    """Search Walmart and return ProductCandidate list. Returns [] on error."""
    api_key = os.environ.get("WALMART_API_KEY")
    if not api_key:
        return []
    qs = urllib.parse.urlencode(
        {"query": query, "numItems": limit, "format": "json", "apiKey": api_key}
    )
    url = f"https://api.walmartlabs.com/v1/search?{qs}"
    try:
        data = _http_get(url)
    except (urllib.error.URLError, RuntimeError, TimeoutError):
        return []
    out: list[ProductCandidate] = []
    for item in (data.get("items") or [])[:limit]:
        price_cents = int(round(float(item.get("salePrice", 0)) * 100))
        out.append(
            ProductCandidate(
                upc=str(item.get("upc", "")),
                title=str(item.get("name", "")),
                grams=float(item.get("weightGrams", 0.0)),
                price_cents=price_cents,
                retail="walmart",
                raw=item,
            )
        )
    return out
