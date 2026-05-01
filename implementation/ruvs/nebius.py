"""Nebius/DeepSeek-V3.2-fast client with tool-use, extracted from deepseek_plate_template_experiment.py."""
from __future__ import annotations
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

DEFAULT_BASE_URL = "https://api.studio.nebius.com/v1"
DEFAULT_MODEL    = "deepseek-ai/DeepSeek-V3.2-fast"

# Per-1M-token pricing (USD) as of 2026-05.
PRICE_CACHE_HIT_PER_1M  = 0.0028
PRICE_CACHE_MISS_PER_1M = 0.14
PRICE_OUTPUT_PER_1M     = 0.28


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class MessageResult:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


def estimate_cost_usd(prompt_tokens: int, completion_tokens: int, cache_hit_tokens: int) -> float:
    cache_miss = max(0, prompt_tokens - cache_hit_tokens)
    return (
        cache_hit_tokens / 1_000_000 * PRICE_CACHE_HIT_PER_1M
        + cache_miss / 1_000_000 * PRICE_CACHE_MISS_PER_1M
        + completion_tokens / 1_000_000 * PRICE_OUTPUT_PER_1M
    )


@dataclass
class NebiusClient:
    api_key: str
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    timeout: int = 60

    def chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        temperature: float = 0.0,
    ) -> MessageResult:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        msg = data["choices"][0]["message"]
        tc_list: list[ToolCall] = []
        for tc in (msg.get("tool_calls") or []):
            args_raw = tc["function"].get("arguments") or "{}"
            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            tc_list.append(ToolCall(id=tc.get("id", ""), name=tc["function"]["name"], arguments=args))
        usage = data.get("usage", {}) or {}
        cost = estimate_cost_usd(
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            cache_hit_tokens=int(usage.get("prompt_cache_hit_tokens") or 0),
        )
        return MessageResult(
            content=msg.get("content", "") or "",
            tool_calls=tc_list,
            usage=usage,
            cost_usd=cost,
            raw=data,
        )
