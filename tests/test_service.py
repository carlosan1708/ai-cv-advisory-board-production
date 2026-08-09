import json
import logging

import pytest

from advisory.observability import emit
from advisory.service import AssessmentService, InputError


def test_service_rejects_empty_input() -> None:
    with pytest.raises(InputError, match="required"):
        AssessmentService(1000).analyze("", "job")


def test_service_rejects_large_input() -> None:
    with pytest.raises(InputError, match="at most"):
        AssessmentService(5).analyze("sixsix", "job")


def test_logs_metadata_not_document_content(caplog: pytest.LogCaptureFixture) -> None:
    private_cv_marker = "PRIVATE_CANDIDATE_PHRASE"
    with caplog.at_level(logging.INFO, logger="advisory"):
        AssessmentService(1000).analyze(f"EXPERIENCE {private_cv_marker}", "Python")
    rendered = "\n".join(caplog.messages)
    assert private_cv_marker not in rendered
    assert any(json.loads(message)["event"] == "assessment.completed" for message in caplog.messages)


def test_log_safety_filter_removes_document_and_location_identifiers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="advisory"):
        emit(
            "ingestion.test",
            filename="PRIVATE_RESUME_NAME.pdf",
            job_url="https://jobs.example/PRIVATE_ROLE",
            cv_text="PRIVATE_CV_TEXT",
            file_bytes=512,
        )
    rendered = "\n".join(caplog.messages)
    assert "PRIVATE_RESUME_NAME" not in rendered
    assert "PRIVATE_ROLE" not in rendered
    assert "PRIVATE_CV_TEXT" not in rendered
    assert json.loads(caplog.messages[-1])["file_bytes"] == 512
