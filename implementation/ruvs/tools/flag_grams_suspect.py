"""flag_grams_suspect tool. Emits a structured marker only; never returns numeric grams."""
from __future__ import annotations
from typing import Any

FLAG_GRAMS_TOOL_SCHEMA: dict[str, Any] = {
    "name": "flag_grams_suspect",
    "description": "Flag that the recipe's gram math looks wrong vs retailer evidence. Provide a short text reason. DO NOT propose a corrected gram value; data fixes are deterministic downstream.",
    "input_schema": {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "short explanation, e.g. '1 lb bacon should be ~454g, recipe row says 52g'"},
        },
        "required": ["reason"],
    },
}


def flag_grams_suspect(reason: str) -> dict[str, str]:
    return {"status": "grams_suspect", "reason": reason.strip()}
