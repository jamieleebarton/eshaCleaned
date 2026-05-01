from unittest.mock import patch
from ruvs_packets import build_packet, ReferenceData
from ruvs.schemas import Packet, ProductCandidate


REF = ReferenceData(
    fndds_desc_by_code={"22500120": "butter, salted"},
    sr28_desc_by_code={"173430": "Butter, salted"},
    esha_desc_by_code={"3501": "Butter (salted)"},
    audit_rows_by_canonical={
        "butter": [{
            "canonical_label": "Butter",
            "match_score": 3.01,
            "fdc_id": 12345,
            "sr28_code": "173430",
            "esha_code": "3501",
        }],
    },
    hestia_canonical_by_line=("Butter, salted", "22500120"),
)


@patch("ruvs_packets.walmart_search")
@patch("ruvs_packets.kroger_search")
def test_build_packet_returns_full_packet(mock_kr, mock_wm):
    mock_wm.return_value = [ProductCandidate(upc="78742370", title="GV Salted Butter", grams=454.0, price_cents=349, retail="walmart")]
    mock_kr.return_value = []
    p = build_packet(
        recipe_id=506745, line_idx=4, config_bucket="hh4|none|3meal",
        recipe_text="1 lb butter", parsed_item="butter", recipe_grams=454.0,
        ref=REF, config={"household": 4, "dietary": "none", "pattern": "3meal"},
    )
    assert isinstance(p, Packet)
    assert p.hestia_canonical == "Butter, salted"
    assert p.fndds_desc == "butter, salted"
    assert p.sr28_desc == "Butter, salted"
    assert p.esha_desc == "Butter (salted)"
    assert p.audit_candidates[0]["canonical_label"] == "Butter"
    assert len(p.walmart_candidates) == 1
    assert p.config["household"] == 4


@patch("ruvs_packets.walmart_search")
@patch("ruvs_packets.kroger_search")
def test_build_packet_handles_missing_audit_codes(mock_kr, mock_wm):
    mock_wm.return_value = []
    mock_kr.return_value = []
    ref = ReferenceData(
        fndds_desc_by_code={"22500120": "butter, salted"},
        sr28_desc_by_code={"173430": "Butter, salted"},
        esha_desc_by_code={"3501": "Butter (salted)"},
        audit_rows_by_canonical={"butter": [{"canonical_label": "Butter", "match_score": 3.01}]},
        hestia_canonical_by_line=("Butter, salted", "22500120"),
    )
    p = build_packet(
        recipe_id=1, line_idx=0, config_bucket="x",
        recipe_text="1 cup butter", parsed_item="butter", recipe_grams=227.0,
        ref=ref,
    )
    # Without sr28_code/esha_code in audit rows, descs are empty (acceptable degradation).
    assert p.sr28_desc == ""
    assert p.esha_desc == ""
    # FNDDS still resolves via hestia_canonical_by_line.
    assert p.fndds_desc == "butter, salted"
