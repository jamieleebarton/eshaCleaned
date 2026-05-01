from unittest.mock import patch

from ruvs.tools.walmart import WALMART_TOOL_SCHEMA, walmart_search
from ruvs.schemas import ProductCandidate


def test_walmart_tool_schema():
    assert WALMART_TOOL_SCHEMA["name"] == "walmart_search"
    assert "query" in WALMART_TOOL_SCHEMA["input_schema"]["properties"]
    assert "limit" in WALMART_TOOL_SCHEMA["input_schema"]["properties"]


@patch("ruvs.tools.walmart._http_get")
def test_walmart_search_returns_product_candidates(mock_http):
    mock_http.return_value = {
        "items": [
            {
                "upc": "78742370",
                "name": "Great Value Salted Butter, 16 oz",
                "salePrice": 3.49,
                "size": "16 oz",
                "weightGrams": 454.0,
            },
        ]
    }
    with patch.dict("os.environ", {"WALMART_API_KEY": "test"}):
        results = walmart_search("butter", limit=3)
    assert len(results) == 1
    assert isinstance(results[0], ProductCandidate)
    assert results[0].upc == "78742370"
    assert results[0].grams == 454.0
    assert results[0].price_cents == 349
    assert results[0].retail == "walmart"


@patch("ruvs.tools.walmart._http_get")
def test_walmart_search_handles_empty(mock_http):
    mock_http.return_value = {"items": []}
    with patch.dict("os.environ", {"WALMART_API_KEY": "test"}):
        assert walmart_search("zzznosuchthing", limit=3) == []


@patch("ruvs.tools.walmart._http_get", side_effect=RuntimeError("503"))
def test_walmart_search_error_returns_marker(mock_http):
    with patch.dict("os.environ", {"WALMART_API_KEY": "test"}):
        results = walmart_search("butter", limit=3)
    assert results == [] and mock_http.call_count >= 1
