from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from pydantic import ValidationError

from advisory.budget import BudgetExceededError, InMemoryBudgetLedger, Pricing
from advisory.career import ApplicationCreate, ApplicationStatus, ApplicationUpdate
from advisory.career_repository import InMemoryCareerRepository, NotFoundError
from advisory.ingestion import CvDocumentParser
from advisory.tracker_service import TrackerService


def test_application_contract_normalizes_and_validates_input() -> None:
    payload = ApplicationCreate(
        company="  Acme  ",
        role="  Staff Engineer ",
        job_url="https://jobs.example/staff",
        location=" Remote ",
        applied_date=date(2026, 8, 9),
    )
    assert payload.company == "Acme"
    assert payload.role == "Staff Engineer"
    assert payload.location == "Remote"
    with pytest.raises(ValidationError):
        ApplicationCreate(company=" ", role="Engineer")
    with pytest.raises(ValidationError):
        ApplicationCreate(company="Acme", role="Engineer", job_url="http://jobs.example/role")


def test_repository_crud_is_owner_scoped_and_status_update_is_idempotent() -> None:
    repository = InMemoryCareerRepository()
    created = repository.create_application("owner-a", ApplicationCreate(company="Acme", role="AI Engineer"))
    assert repository.list_applications("owner-a")[0].id == created.id
    assert repository.list_applications("owner-b") == []
    with pytest.raises(NotFoundError):
        repository.update_application(
            "owner-b", created.id, ApplicationUpdate(status=ApplicationStatus.APPLIED)
        )
    first = repository.update_application(
        "owner-a", created.id, ApplicationUpdate(status=ApplicationStatus.APPLIED)
    )
    second = repository.update_application(
        "owner-a", created.id, ApplicationUpdate(status=ApplicationStatus.APPLIED)
    )
    assert first.status == second.status == ApplicationStatus.APPLIED
    repository.clear()
    assert repository.list_applications("owner-a") == []


def test_immutable_cv_version_can_be_attached_only_by_its_owner() -> None:
    repository = InMemoryCareerRepository()
    service = TrackerService(repository, CvDocumentParser(max_file_bytes=5_000, max_chars=30_000))
    content = b"EXPERIENCE\nBuilt reliable Python services"
    version = service.create_cv_version(
        "owner-a", label="Platform CV", filename="../resume.txt", content_type="text/plain", content=content
    )
    assert version.filename == "resume.txt"
    assert len(version.sha256) == 64
    assert repository.get_cv_content("owner-a", version.id) == content
    with pytest.raises(NotFoundError):
        repository.get_cv_version("owner-b", version.id)
    application = repository.create_application(
        "owner-a", ApplicationCreate(company="Acme", role="Engineer", cv_version_id=version.id)
    )
    assert application.cv_version_id == version.id
    with pytest.raises(NotFoundError):
        repository.create_application(
            "owner-b", ApplicationCreate(company="Other", role="Engineer", cv_version_id=version.id)
        )
    with pytest.raises(ValueError, match="label"):
        service.create_cv_version(
            "owner-a", label=" ", filename="resume.txt", content_type="text/plain", content=content
        )


def test_pricing_uses_integer_micro_dollars() -> None:
    assert Pricing().cost(1_000_000, 1_000_000) == 2_800_000
    assert Pricing().cost(1, 1) == 4


def test_budget_reserve_reconcile_release_and_cap() -> None:
    ledger = InMemoryBudgetLedger(100)
    first = ledger.reserve("user", 70, "2026-08")
    assert ledger.snapshot("user", "2026-08").remaining_micro_usd == 30
    with pytest.raises(BudgetExceededError):
        ledger.reserve("user", 31, "2026-08")
    snapshot = ledger.reconcile(first, 25)
    assert snapshot.used_micro_usd == 25
    second = ledger.reserve("user", 50, "2026-08")
    assert ledger.release(second).remaining_micro_usd == 75
    with pytest.raises(ValueError):
        ledger.reserve("user", 0)
    with pytest.raises(ValueError):
        ledger.reconcile(first, 1)


def test_parallel_budget_reservations_cannot_cross_cap() -> None:
    ledger = InMemoryBudgetLedger(100)

    def reserve() -> bool:
        try:
            ledger.reserve("same-user", 60, "2026-08")
            return True
        except BudgetExceededError:
            return False

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: reserve(), range(8)))
    assert results.count(True) == 1
    snapshot = ledger.snapshot("same-user", "2026-08")
    assert snapshot.reserved_micro_usd == 60
    assert snapshot.used_micro_usd + snapshot.reserved_micro_usd <= snapshot.limit_micro_usd
