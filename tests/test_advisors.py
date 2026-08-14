from advisory.advisors import DEFAULT_ADVISOR_IDS, advisor_context, normalize_advisor_ids


def test_advisor_ids_are_allowlisted_deduplicated_and_bounded() -> None:
    assert normalize_advisor_ids(
        ["executive", "unknown", "executive", "impact", "startup", "technical"]
    ) == ["executive", "impact", "startup"]
    assert normalize_advisor_ids([]) == []
    assert normalize_advisor_ids(None) == list(DEFAULT_ADVISOR_IDS)
    assert [item["id"] for item in advisor_context(["impact"])] == ["impact"]
