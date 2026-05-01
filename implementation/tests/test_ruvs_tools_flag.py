from ruvs.tools.flag_grams_suspect import flag_grams_suspect, FLAG_GRAMS_TOOL_SCHEMA


def test_flag_schema_takes_only_reason():
    props = FLAG_GRAMS_TOOL_SCHEMA["input_schema"]["properties"]
    assert "reason" in props
    assert "grams" not in props and "value" not in props


def test_flag_returns_structured_marker():
    out = flag_grams_suspect(reason="recipe says 1 lb bacon, package math implies 52g; should be ~454g")
    assert out["status"] == "grams_suspect"
    assert "1 lb bacon" in out["reason"]
    assert "computed_grams" not in out
