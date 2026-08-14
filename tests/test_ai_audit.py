from datetime import UTC, datetime, timedelta

from advisory.ai_audit import AiAuditEvent, InMemoryAiAuditRepository


def test_audit_repository_is_bounded_recent_and_metadata_only() -> None:
    repository = InMemoryAiAuditRepository()
    first = AiAuditEvent.new(
        owner_id="anonymous-free-tier",
        access_tier="anonymous",
        review_type="job_match",
        status="gemini",
        model="gemini-2.5-flash",
        advisor_ids=["recruiter", "technical"],
        score=72,
        input_tokens=120,
        output_tokens=40,
        actual_micro_usd=136,
    )
    second = AiAuditEvent.new(
        owner_id="member-1",
        access_tier="approved",
        review_type="cv",
        status="fallback",
        model="gemini-2.5-flash",
    )
    repository.record(first)
    repository.record(second)

    recent = repository.list_recent(1)
    assert [event.id for event in recent] == [second.id]
    serialized = first.model_dump()
    assert "cv_text" not in serialized
    assert "job_text" not in serialized
    assert "summary" not in serialized
    assert first.advisor_ids == ["recruiter", "technical"]
    assert repository.count_since(datetime.now(UTC) - timedelta(minutes=1)) == 2
    assert repository.count_since(datetime.now(UTC) + timedelta(minutes=1)) == 0
