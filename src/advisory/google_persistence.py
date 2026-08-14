from __future__ import annotations

from datetime import UTC, datetime

from advisory.ai_audit import AiAuditEvent
from advisory.budget import BudgetExceededError, BudgetSnapshot, Reservation
from advisory.career import (
    Application,
    ApplicationCreate,
    ApplicationUpdate,
    CvVersion,
    WorkspaceArchive,
    WorkspaceArchiveDetail,
)
from advisory.career_repository import EmptyWorkspaceError, NotFoundError


class FirestoreAiAuditRepository:
    """Admin-only AI operations ledger. It deliberately excludes source and generated text."""

    def __init__(self, project: str) -> None:
        import google.cloud.firestore as firestore

        self.firestore = firestore
        self.collection = firestore.Client(project=project).collection("ai_audit_events")

    def record(self, event: AiAuditEvent) -> None:
        self.collection.document(event.id).set(event.model_dump(mode="json"))

    def list_recent(self, limit: int = 50) -> list[AiAuditEvent]:
        bounded_limit = max(1, min(limit, 500))
        query = self.collection.order_by(
            "created_at", direction=self.firestore.Query.DESCENDING
        ).limit(bounded_limit)
        return [AiAuditEvent.model_validate(item.to_dict()) for item in query.stream()]

    def count_since(self, since: datetime) -> int:
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = self.collection.where(filter=FieldFilter("created_at", ">=", since))
        return sum(1 for _ in query.stream())


class GoogleCareerRepository:
    """Firestore metadata plus private Cloud Storage CV objects."""

    def __init__(self, project: str, bucket_name: str) -> None:
        import google.cloud.firestore as firestore
        import google.cloud.storage as storage  # type: ignore[import-untyped]

        self.db = firestore.Client(project=project)
        self.bucket = storage.Client(project=project).bucket(bucket_name)

    def _user(self, owner_id: str):  # type: ignore[no-untyped-def]
        return self.db.collection("users").document(owner_id)

    def list_applications(self, owner_id: str) -> list[Application]:
        documents = self._user(owner_id).collection("applications").stream()
        applications = [
            item
            for document in documents
            if (item := Application.model_validate(document.to_dict())).archive_id is None
        ]
        return sorted(applications, key=lambda item: item.updated_at, reverse=True)

    def get_application(self, owner_id: str, application_id: str) -> Application:
        snapshot = self._user(owner_id).collection("applications").document(application_id).get()
        if not snapshot.exists:
            raise NotFoundError("Application not found")
        application = Application.model_validate(snapshot.to_dict())
        if application.archive_id is not None:
            raise NotFoundError("Application not found")
        return application

    def create_application(self, owner_id: str, payload: ApplicationCreate) -> Application:
        if payload.cv_version_id:
            self.get_cv_version(owner_id, payload.cv_version_id)
        application = Application.new(owner_id, payload)
        self._user(owner_id).collection("applications").document(application.id).create(
            application.model_dump(mode="json")
        )
        return application

    def update_application(
        self, owner_id: str, application_id: str, payload: ApplicationUpdate
    ) -> Application:
        current = self.get_application(owner_id, application_id)
        changes = payload.model_dump(exclude_unset=True, mode="json")
        cv_version_id = changes.get("cv_version_id")
        if cv_version_id:
            self.get_cv_version(owner_id, cv_version_id)
        updated = current.model_copy(update={**changes, "updated_at": datetime.now(UTC)})
        self._user(owner_id).collection("applications").document(application_id).set(
            updated.model_dump(mode="json")
        )
        return updated

    def list_cv_versions(self, owner_id: str) -> list[CvVersion]:
        documents = self._user(owner_id).collection("cv_versions").stream()
        versions = [
            item
            for document in documents
            if (item := CvVersion.model_validate(document.to_dict())).archive_id is None
        ]
        return sorted(versions, key=lambda item: item.created_at, reverse=True)

    def get_cv_version(self, owner_id: str, cv_version_id: str) -> CvVersion:
        snapshot = self._user(owner_id).collection("cv_versions").document(cv_version_id).get()
        if not snapshot.exists:
            raise NotFoundError("CV version not found")
        version = CvVersion.model_validate(snapshot.to_dict())
        if version.archive_id is not None:
            raise NotFoundError("CV version not found")
        return version

    def create_cv_version(self, version: CvVersion, content: bytes) -> CvVersion:
        object_name = f"users/{version.owner_id}/cv-versions/{version.id}/{version.filename}"
        blob = self.bucket.blob(object_name)
        blob.upload_from_string(content, content_type=version.content_type, if_generation_match=0)
        metadata = version.model_dump(mode="json")
        metadata["object_name"] = object_name
        try:
            self._user(version.owner_id).collection("cv_versions").document(version.id).create(metadata)
        except Exception:
            blob.delete()
            raise
        return version

    def get_cv_content(self, owner_id: str, cv_version_id: str) -> bytes:
        version = self.get_cv_version(owner_id, cv_version_id)
        object_name = f"users/{owner_id}/cv-versions/{version.id}/{version.filename}"
        return bytes(self.bucket.blob(object_name).download_as_bytes())

    def list_workspace_archives(self, owner_id: str) -> list[WorkspaceArchive]:
        documents = self._user(owner_id).collection("workspace_archives").stream()
        archives = [WorkspaceArchive.model_validate(document.to_dict()) for document in documents]
        return sorted(archives, key=lambda item: item.created_at, reverse=True)

    def archive_workspace(self, owner_id: str, label: str) -> WorkspaceArchive:
        cleaned_label = label.strip()
        if not cleaned_label:
            raise ValueError("Archive name must not be blank")
        applications = self.list_applications(owner_id)
        versions = self.list_cv_versions(owner_id)
        if not applications and not versions:
            raise EmptyWorkspaceError("The workspace is already empty")
        if len(applications) + len(versions) > 450:
            raise ValueError("A workspace archive can contain at most 450 records")
        archive = WorkspaceArchive(
            id=self._user(owner_id).collection("workspace_archives").document().id,
            owner_id=owner_id,
            label=cleaned_label,
            application_count=len(applications),
            cv_version_count=len(versions),
            created_at=datetime.now(UTC),
        )
        batch = self.db.batch()
        archive_ref = self._user(owner_id).collection("workspace_archives").document(archive.id)
        batch.create(archive_ref, archive.model_dump(mode="json"))
        for application in applications:
            reference = self._user(owner_id).collection("applications").document(application.id)
            batch.update(reference, {"archive_id": archive.id})
        for version in versions:
            reference = self._user(owner_id).collection("cv_versions").document(version.id)
            batch.update(reference, {"archive_id": archive.id})
        batch.commit()
        return archive

    def get_workspace_archive(
        self, owner_id: str, archive_id: str
    ) -> WorkspaceArchiveDetail:
        archive_ref = self._user(owner_id).collection("workspace_archives").document(archive_id)
        snapshot = archive_ref.get()
        if not snapshot.exists:
            raise NotFoundError("Workspace archive not found")
        archive = WorkspaceArchive.model_validate(snapshot.to_dict())
        applications = [
            Application.model_validate(document.to_dict())
            for document in self._user(owner_id).collection("applications").stream()
            if (document.to_dict() or {}).get("archive_id") == archive_id
        ]
        versions = [
            CvVersion.model_validate(document.to_dict())
            for document in self._user(owner_id).collection("cv_versions").stream()
            if (document.to_dict() or {}).get("archive_id") == archive_id
        ]
        return WorkspaceArchiveDetail(
            archive=archive,
            applications=sorted(applications, key=lambda item: item.updated_at, reverse=True),
            cv_versions=sorted(versions, key=lambda item: item.created_at, reverse=True),
        )

    def get_archived_cv_content(
        self, owner_id: str, archive_id: str, cv_version_id: str
    ) -> bytes:
        snapshot = self._user(owner_id).collection("cv_versions").document(cv_version_id).get()
        if not snapshot.exists:
            raise NotFoundError("Archived CV version not found")
        metadata = snapshot.to_dict() or {}
        version = CvVersion.model_validate(metadata)
        if version.archive_id != archive_id:
            raise NotFoundError("Archived CV version not found")
        object_name = metadata.get(
            "object_name",
            f"users/{owner_id}/cv-versions/{version.id}/{version.filename}",
        )
        return bytes(self.bucket.blob(object_name).download_as_bytes())


class FirestoreBudgetLedger:
    """Atomic monthly per-user reservation ledger shared by every Cloud Run instance."""

    def __init__(self, project: str, monthly_limit_micro_usd: int) -> None:
        import google.cloud.firestore as firestore

        self.firestore = firestore
        self.db = firestore.Client(project=project)
        self.monthly_limit_micro_usd = monthly_limit_micro_usd

    @staticmethod
    def month(now: datetime | None = None) -> str:
        return (now or datetime.now(UTC)).strftime("%Y-%m")

    def _ledger(self, owner_id: str, month: str):  # type: ignore[no-untyped-def]
        return self.db.collection("users").document(owner_id).collection("ai_usage").document(month)

    def snapshot(self, owner_id: str, month: str | None = None) -> BudgetSnapshot:
        active_month = month or self.month()
        data = self._ledger(owner_id, active_month).get().to_dict() or {}
        return BudgetSnapshot(
            self.monthly_limit_micro_usd,
            int(data.get("used_micro_usd", 0)),
            int(data.get("reserved_micro_usd", 0)),
        )

    def reserve(self, owner_id: str, amount_micro_usd: int, month: str | None = None) -> Reservation:
        if amount_micro_usd <= 0:
            raise ValueError("Reservation amount must be positive")
        active_month = month or self.month()
        reservation = Reservation(
            self.db.collection("_ids").document().id, owner_id, active_month, amount_micro_usd
        )
        ledger_ref = self._ledger(owner_id, active_month)
        reservation_ref = ledger_ref.collection("reservations").document(reservation.id)
        transaction = self.db.transaction()

        @self.firestore.transactional
        def reserve_atomic(tx):  # type: ignore[no-untyped-def]
            data = ledger_ref.get(transaction=tx).to_dict() or {}
            used = int(data.get("used_micro_usd", 0))
            reserved = int(data.get("reserved_micro_usd", 0))
            if used + reserved + amount_micro_usd > self.monthly_limit_micro_usd:
                raise BudgetExceededError("Monthly AI budget reached")
            tx.set(
                ledger_ref,
                {
                    "used_micro_usd": used,
                    "reserved_micro_usd": reserved + amount_micro_usd,
                    "limit_micro_usd": self.monthly_limit_micro_usd,
                    "updated_at": self.firestore.SERVER_TIMESTAMP,
                },
            )
            tx.create(reservation_ref, {"amount_micro_usd": amount_micro_usd})

        reserve_atomic(transaction)
        return reservation

    def reconcile(self, reservation: Reservation, actual_micro_usd: int) -> BudgetSnapshot:
        if actual_micro_usd < 0 or actual_micro_usd > reservation.amount_micro_usd:
            raise ValueError("Actual cost must fit within the reservation")
        self._finish(reservation, actual_micro_usd)
        return self.snapshot(reservation.owner_id, reservation.month)

    def release(self, reservation: Reservation) -> BudgetSnapshot:
        self._finish(reservation, 0)
        return self.snapshot(reservation.owner_id, reservation.month)

    def _finish(self, reservation: Reservation, actual_micro_usd: int) -> None:
        ledger_ref = self._ledger(reservation.owner_id, reservation.month)
        reservation_ref = ledger_ref.collection("reservations").document(reservation.id)
        transaction = self.db.transaction()

        @self.firestore.transactional
        def finish_atomic(tx):  # type: ignore[no-untyped-def]
            ledger = ledger_ref.get(transaction=tx).to_dict() or {}
            active = reservation_ref.get(transaction=tx)
            if not active.exists:
                raise ValueError("Reservation is not active")
            tx.update(
                ledger_ref,
                {
                    "used_micro_usd": int(ledger.get("used_micro_usd", 0)) + actual_micro_usd,
                    "reserved_micro_usd": max(
                        0,
                        int(ledger.get("reserved_micro_usd", 0)) - reservation.amount_micro_usd,
                    ),
                    "updated_at": self.firestore.SERVER_TIMESTAMP,
                },
            )
            tx.delete(reservation_ref)

        finish_atomic(transaction)
