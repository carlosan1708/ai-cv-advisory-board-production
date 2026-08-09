from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from threading import RLock
from typing import Literal, Protocol

from fastapi import HTTPException
from pydantic import BaseModel

from advisory.auth import UserIdentity

AccessStatus = Literal["pending", "approved", "rejected"]
AccessRole = Literal["user", "admin"]


class AccessRecord(BaseModel):
    id: str
    email: str
    subject: str = ""
    status: AccessStatus
    role: AccessRole = "user"
    requested_at: datetime
    updated_at: datetime


class AccessInvite(BaseModel):
    email: str


class AccessDecision(BaseModel):
    status: Literal["approved", "rejected"]


class AccessControl(Protocol):
    def status(self, identity: UserIdentity) -> AccessRecord: ...
    def request_access(self, identity: UserIdentity) -> AccessRecord: ...
    def list_records(self, identity: UserIdentity) -> list[AccessRecord]: ...
    def approve_email(self, identity: UserIdentity, email: str) -> AccessRecord: ...
    def decide(self, identity: UserIdentity, record_id: str, status: AccessStatus) -> AccessRecord: ...

    def require_access(self, identity: UserIdentity) -> AccessRecord: ...
    def require_admin(self, identity: UserIdentity) -> AccessRecord: ...


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def access_id(email: str) -> str:
    return sha256(normalize_email(email).encode()).hexdigest()[:32]


class InMemoryAccessControl:
    def __init__(self, admin_emails: set[str], *, allow_all: bool = False) -> None:
        self.admin_emails = {normalize_email(email) for email in admin_emails}
        self.allow_all = allow_all
        self._records: dict[str, AccessRecord] = {}
        self._lock = RLock()

    def _admin_record(self, identity: UserIdentity) -> AccessRecord:
        now = datetime.now(UTC)
        email = normalize_email(identity.email)
        return AccessRecord(
            id=access_id(email),
            email=email,
            subject=identity.subject,
            status="approved",
            role="admin",
            requested_at=now,
            updated_at=now,
        )

    def status(self, identity: UserIdentity) -> AccessRecord:
        email = normalize_email(identity.email)
        if email in self.admin_emails:
            return self._admin_record(identity)
        if self.allow_all:
            now = datetime.now(UTC)
            return AccessRecord(
                id=access_id(email or identity.subject),
                email=email,
                subject=identity.subject,
                status="approved",
                role="user",
                requested_at=now,
                updated_at=now,
            )
        with self._lock:
            record = self._records.get(access_id(email))
            if record:
                return record.model_copy(deep=True)
        now = datetime.now(UTC)
        return AccessRecord(
            id=access_id(email),
            email=email,
            subject=identity.subject,
            status="pending",
            requested_at=now,
            updated_at=now,
        )

    def request_access(self, identity: UserIdentity) -> AccessRecord:
        email = normalize_email(identity.email)
        if not email:
            raise HTTPException(status_code=422, detail="Google account email is required")
        current = self.status(identity)
        if current.role == "admin" or current.status == "approved":
            return current
        now = datetime.now(UTC)
        record = current.model_copy(
            update={"subject": identity.subject, "status": "pending", "updated_at": now}
        )
        with self._lock:
            self._records[record.id] = record
        return record.model_copy(deep=True)

    def list_records(self, identity: UserIdentity) -> list[AccessRecord]:
        self.require_admin(identity)
        with self._lock:
            values = [record.model_copy(deep=True) for record in self._records.values()]
        return sorted(values, key=lambda record: record.updated_at, reverse=True)

    def approve_email(self, identity: UserIdentity, email: str) -> AccessRecord:
        self.require_admin(identity)
        normalized = normalize_email(email)
        if not normalized or "@" not in normalized:
            raise HTTPException(status_code=422, detail="Enter a valid email address")
        now = datetime.now(UTC)
        key = access_id(normalized)
        with self._lock:
            current = self._records.get(key)
            record = AccessRecord(
                id=key,
                email=normalized,
                subject=current.subject if current else "",
                status="approved",
                role="user",
                requested_at=current.requested_at if current else now,
                updated_at=now,
            )
            self._records[key] = record
        return record.model_copy(deep=True)

    def decide(self, identity: UserIdentity, record_id: str, status: AccessStatus) -> AccessRecord:
        self.require_admin(identity)
        if status not in {"approved", "rejected"}:
            raise HTTPException(status_code=422, detail="Decision must be approved or rejected")
        with self._lock:
            current = self._records.get(record_id)
            if current is None:
                raise HTTPException(status_code=404, detail="Access request not found")
            updated = current.model_copy(update={"status": status, "updated_at": datetime.now(UTC)})
            self._records[record_id] = updated
            return updated.model_copy(deep=True)

    def require_access(self, identity: UserIdentity) -> AccessRecord:
        record = self.status(identity)
        if record.status != "approved":
            raise HTTPException(
                status_code=403,
                detail={"code": f"access_{record.status}", "message": "Workspace access is not approved"},
            )
        return record

    def require_admin(self, identity: UserIdentity) -> AccessRecord:
        record = self.require_access(identity)
        if record.role != "admin":
            raise HTTPException(status_code=403, detail="Administrator access is required")
        return record


class FirestoreAccessControl(InMemoryAccessControl):
    def __init__(self, project: str, admin_emails: set[str]) -> None:
        import google.cloud.firestore as firestore

        super().__init__(admin_emails)
        self.db = firestore.Client(project=project)
        self.collection = self.db.collection("workspace_access")

    def status(self, identity: UserIdentity) -> AccessRecord:
        email = normalize_email(identity.email)
        if email in self.admin_emails:
            return self._admin_record(identity)
        snapshot = self.collection.document(access_id(email)).get()
        if snapshot.exists:
            return AccessRecord.model_validate(snapshot.to_dict())
        return super().status(identity)

    def request_access(self, identity: UserIdentity) -> AccessRecord:
        record = super().request_access(identity)
        if record.role != "admin" and record.status != "approved":
            self.collection.document(record.id).set(record.model_dump(mode="json"), merge=True)
        return record

    def list_records(self, identity: UserIdentity) -> list[AccessRecord]:
        self.require_admin(identity)
        records = [AccessRecord.model_validate(item.to_dict()) for item in self.collection.stream()]
        return sorted(records, key=lambda record: record.updated_at, reverse=True)

    def approve_email(self, identity: UserIdentity, email: str) -> AccessRecord:
        self.require_admin(identity)
        normalized = normalize_email(email)
        if not normalized or "@" not in normalized:
            raise HTTPException(status_code=422, detail="Enter a valid email address")
        key = access_id(normalized)
        snapshot = self.collection.document(key).get()
        now = datetime.now(UTC)
        current = AccessRecord.model_validate(snapshot.to_dict()) if snapshot.exists else None
        record = AccessRecord(
            id=key,
            email=normalized,
            subject=current.subject if current else "",
            status="approved",
            role="user",
            requested_at=current.requested_at if current else now,
            updated_at=now,
        )
        self.collection.document(key).set(record.model_dump(mode="json"))
        return record

    def decide(self, identity: UserIdentity, record_id: str, status: AccessStatus) -> AccessRecord:
        self.require_admin(identity)
        if status not in {"approved", "rejected"}:
            raise HTTPException(status_code=422, detail="Decision must be approved or rejected")
        reference = self.collection.document(record_id)
        snapshot = reference.get()
        if not snapshot.exists:
            raise HTTPException(status_code=404, detail="Access request not found")
        record = AccessRecord.model_validate(snapshot.to_dict()).model_copy(
            update={"status": status, "updated_at": datetime.now(UTC)}
        )
        reference.set(record.model_dump(mode="json"))
        return record
