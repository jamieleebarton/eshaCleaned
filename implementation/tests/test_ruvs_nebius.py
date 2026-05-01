from unittest.mock import patch, MagicMock
import json
from ruvs.nebius import NebiusClient, ToolCall, MessageResult, estimate_cost_usd


def test_estimate_cost_uses_published_pricing():
    cents = estimate_cost_usd(prompt_tokens=10000, completion_tokens=2000, cache_hit_tokens=0)
    assert cents > 0


@patch("ruvs.nebius.urllib.request.urlopen")
def test_call_with_tools_dispatches(mock_urlopen):
    payload = {
        "choices": [{"message": {
            "role": "assistant",
            "tool_calls": [{"id": "tc1", "type": "function",
                            "function": {"name": "walmart_search", "arguments": json.dumps({"query": "butter", "limit": 5})}}],
        }}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "prompt_cache_hit_tokens": 0},
    }
    mock_resp = MagicMock(); mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    client = NebiusClient(api_key="x", model="m")
    result = client.chat(messages=[{"role": "user", "content": "hi"}], tools=[{"type": "function", "function": {"name": "walmart_search", "parameters": {}}}])
    assert isinstance(result, MessageResult)
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "walmart_search"
    assert result.tool_calls[0].arguments == {"query": "butter", "limit": 5}


@patch("ruvs.nebius.urllib.request.urlopen")
def test_call_returns_text_when_no_tool_calls(mock_urlopen):
    payload = {
        "choices": [{"message": {"role": "assistant", "content": "{\"facets\": {\"canonical_correct\": \"ok\"}}"}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 30, "prompt_cache_hit_tokens": 50},
    }
    mock_resp = MagicMock(); mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_resp
    client = NebiusClient(api_key="x", model="m")
    result = client.chat(messages=[{"role": "user", "content": "hi"}], tools=[])
    assert result.tool_calls == []
    assert "facets" in result.content
