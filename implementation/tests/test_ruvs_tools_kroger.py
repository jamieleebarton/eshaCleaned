from unittest.mock import patch

from ruvs.tools.kroger import KROGER_TOOL_SCHEMA, kroger_search
from ruvs.schemas import ProductCandidate


def test_kroger_tool_schema():
    assert KROGER_TOOL_SCHEMA["name"] == "kroger_search"


@patch("ruvs.tools.kroger._http_get")
def test_kroger_search_returns_product_candidates(mock_http):
    mock_http.return_value = {
        "data": [
            {
                "upc": "0001111041700",
                "description": "Kroger Salted Butter Sticks",
                "items": [{"price": {"regular": 3.99}, "size": "16 oz"}],
            },
        ]
    }
    with patch.dict("os.environ", {"KROGER_ACCESS_TOKEN": "test"}):
        results = kroger_search("butter", limit=3)
    assert len(results) == 1
    assert isinstance(results[0], ProductCandidate)
    assert results[0].retail == "kroger"
    assert results[0].price_cents == 399
    assert results[0].upc == "0001111041700"


def test_kroger_search_no_token_returns_empty(monkeypatch):
    monkeypatch.delenv("KROGER_ACCESS_TOKEN", raising=False)
    assert kroger_search("butter", limit=3) == []
