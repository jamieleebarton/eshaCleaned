from unittest.mock import MagicMock
import json
from ruvs.schemas import Packet, ProductCandidate, LineVerdict
from ruvs.nebius import MessageResult, ToolCall
from ruvs_verify import verify_line


def _packet():
    return Packet(
        recipe_id=506745, line_idx=4, config_bucket="hh4|none|3meal",
        recipe_text="1 lb butter", parsed_item="butter", recipe_grams=454.0,
        hestia_canonical="Butter, salted", audit_candidates=[],
        fndds_desc="butter, salted", sr28_desc="Butter, salted", esha_desc="Butter (salted)",
        walmart_candidates=[ProductCandidate(upc="x", title="GV Butter", grams=454.0, price_cents=349, retail="walmart")],
        kroger_candidates=[],
    )


def _verdict_msg(facets, fix=None):
    return MessageResult(
        content=json.dumps({"facets": facets, "fix_proposed": fix, "rationale": "ok"}),
        tool_calls=[], usage={"prompt_tokens": 100, "completion_tokens": 30}, cost_usd=0.001,
    )


def test_verify_line_clean_returns_clean_verdict():
    client = MagicMock()
    client.model = "deepseek-v3.2-fast"
    client.chat.return_value = _verdict_msg({
        "canonical_correct": "ok", "form_correct": "ok", "granularity_correct": "ok",
        "grams_plausible": "ok", "cook_state_handled": "n/a", "package_math_sane": "ok",
        "ambiguity_flagged": "none",
    })
    v = verify_line(packet=_packet(), client=client, run_id="r1")
    assert isinstance(v, LineVerdict)
    assert v.is_clean()
    assert v.fix_proposed is None
    client.chat.assert_called_once()


def test_verify_line_dispatches_tool_call_then_continues():
    client = MagicMock()
    client.model = "deepseek-v3.2-fast"
    first = MessageResult(
        content="",
        tool_calls=[ToolCall(id="t1", name="walmart_search", arguments={"query": "plain butter", "limit": 5})],
        usage={"prompt_tokens": 100, "completion_tokens": 5}, cost_usd=0.0005,
    )
    second = _verdict_msg({"canonical_correct": "ok", "form_correct": "ok", "granularity_correct": "ok",
                           "grams_plausible": "ok", "cook_state_handled": "n/a", "package_math_sane": "ok",
                           "ambiguity_flagged": "none"})
    client.chat.side_effect = [first, second]
    v = verify_line(packet=_packet(), client=client, run_id="r1")
    assert v.is_clean()
    assert client.chat.call_count == 2
    assert "tool_calls" in v.evidence


def test_verify_line_caps_tool_calls_at_8():
    client = MagicMock()
    client.model = "deepseek-v3.2-fast"
    looping = MessageResult(
        content="",
        tool_calls=[ToolCall(id="t", name="walmart_search", arguments={"query": "x", "limit": 1})],
        usage={"prompt_tokens": 50, "completion_tokens": 5}, cost_usd=0.0,
    )
    client.chat.return_value = looping
    v = verify_line(packet=_packet(), client=client, run_id="r1")
    assert v.facets.get("canonical_correct") == "ambiguous"
    assert "tool_loop_exceeded" in json.dumps(v.evidence)
