import json
from pathlib import Path
from ruvs.schemas import FACETS, FACET_ENUMS

GOLDEN_DIR = Path(__file__).parent / "ruvs_golden"


def test_all_eight_fixtures_present():
    expected = {
        "506745_booyah.json", "breaded_default_state.json", "green_bean_almondine.json",
        "one_lb_bacon_grams.json", "butter_or_margarine.json", "peppers_range.json",
        "generic_cheese.json", "all_clean_baseline.json",
    }
    actual = {p.name for p in GOLDEN_DIR.glob("*.json")}
    assert expected.issubset(actual), f"missing: {expected - actual}"


def test_each_fixture_has_valid_facets():
    for p in GOLDEN_DIR.glob("*.json"):
        f = json.loads(p.read_text())
        ef = f["expected_facets"]
        for facet in FACETS:
            assert facet in ef, f"{p.name} missing {facet}"
            assert ef[facet] in FACET_ENUMS[facet], f"{p.name} bad value {facet}={ef[facet]}"
