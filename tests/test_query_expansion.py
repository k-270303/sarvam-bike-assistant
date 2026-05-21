from backend.app.retrieval.query_expansion import expand_query


def test_starts_then_dies_expands_to_manual_language() -> None:
    expanded = expand_query("My Glamour starts, then immediately dies.")
    assert "engine starts but stalls" in expanded.expansion_terms


def test_oil_warning_expands_to_low_oil_pressure_indicator() -> None:
    expanded = expand_query("The red oil warning came on.")
    assert "low oil pressure indicator" in expanded.expansion_terms


def test_side_stand_expansion() -> None:
    expanded = expand_query("My TVS Sport will not start because the stand is down.")
    assert "side stand" in expanded.expansion_terms
