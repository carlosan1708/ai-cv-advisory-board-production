import pytest
from fastapi import HTTPException

from advisory.access import InMemoryAccessControl, access_id, normalize_email
from advisory.auth import UserIdentity

ADMIN = UserIdentity("admin-sub", "admin@example.com")
PERSON = UserIdentity("person-sub", "Person@Example.com")


def test_normalization_and_admin_bootstrap() -> None:
    assert normalize_email(" Person@Example.COM ") == "person@example.com"
    assert access_id("person@example.com") == access_id(" PERSON@example.com ")
    control = InMemoryAccessControl({"admin@example.com"})
    record = control.require_admin(ADMIN)
    assert record.status == "approved"
    assert record.role == "admin"


def test_request_approve_and_reject_lifecycle() -> None:
    control = InMemoryAccessControl({"admin@example.com"})
    assert control.status(PERSON).status == "pending"
    with pytest.raises(HTTPException) as denied:
        control.require_access(PERSON)
    assert denied.value.status_code == 403
    requested = control.request_access(PERSON)
    assert requested.subject == "person-sub"
    assert control.list_records(ADMIN)[0].email == "person@example.com"
    approved = control.decide(ADMIN, requested.id, "approved")
    assert approved.status == "approved"
    assert control.require_access(PERSON).email == "person@example.com"
    rejected = control.decide(ADMIN, requested.id, "rejected")
    assert rejected.status == "rejected"


def test_admin_can_preapprove_and_validation_is_enforced() -> None:
    control = InMemoryAccessControl({"admin@example.com"})
    record = control.approve_email(ADMIN, " Invited@Example.com ")
    assert record.email == "invited@example.com"
    assert record.status == "approved"
    assert control.status(UserIdentity("new-sub", "invited@example.com")).status == "approved"
    with pytest.raises(HTTPException) as invalid:
        control.approve_email(ADMIN, "not-an-email")
    assert invalid.value.status_code == 422
    with pytest.raises(HTTPException) as missing:
        control.decide(ADMIN, "missing", "approved")
    assert missing.value.status_code == 404


def test_non_admin_cannot_manage_access_and_dev_allow_all() -> None:
    control = InMemoryAccessControl({"admin@example.com"}, allow_all=True)
    assert control.require_access(PERSON).role == "user"
    with pytest.raises(HTTPException) as denied:
        control.list_records(PERSON)
    assert denied.value.status_code == 403


def test_request_requires_an_email() -> None:
    control = InMemoryAccessControl({"admin@example.com"})
    with pytest.raises(HTTPException) as missing:
        control.request_access(UserIdentity("subject-only"))
    assert missing.value.status_code == 422
