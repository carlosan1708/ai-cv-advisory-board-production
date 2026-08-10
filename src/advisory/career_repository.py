from __future__ import annotations

from datetime import UTC, datetime
from threading import RLock
from typing import Protocol
from uuid import uuid4

from advisory.career import (
    Application,
    ApplicationCreate,
    ApplicationUpdate,
    CvVersion,
    WorkspaceArchive,
    WorkspaceArchiveDetail,
)


class NotFoundError(LookupError):
    pass


class EmptyWorkspaceError(ValueError):
    pass


class CareerRepository(Protocol):
    def list_applications(self, owner_id: str) -> list[Application]: ...
    def get_application(self, owner_id: str, application_id: str) -> Application: ...
    def create_application(self, owner_id: str, payload: ApplicationCreate) -> Application: ...
    def update_application(
        self, owner_id: str, application_id: str, payload: ApplicationUpdate
    ) -> Application: ...
    def list_cv_versions(self, owner_id: str) -> list[CvVersion]: ...
    def get_cv_version(self, owner_id: str, cv_version_id: str) -> CvVersion: ...
    def create_cv_version(self, version: CvVersion, content: bytes) -> CvVersion: ...
    def get_cv_content(self, owner_id: str, cv_version_id: str) -> bytes: ...
    def list_workspace_archives(self, owner_id: str) -> list[WorkspaceArchive]: ...
    def archive_workspace(self, owner_id: str, label: str) -> WorkspaceArchive: ...
    def get_workspace_archive(self, owner_id: str, archive_id: str) -> WorkspaceArchiveDetail: ...
    def get_archived_cv_content(
        self, owner_id: str, archive_id: str, cv_version_id: str
    ) -> bytes: ...


class InMemoryCareerRepository:
    """Thread-safe owner-scoped repository used by local preview and tests."""

    def __init__(self) -> None:
        self._applications: dict[tuple[str, str], Application] = {}
        self._cv_versions: dict[tuple[str, str], CvVersion] = {}
        self._cv_content: dict[tuple[str, str], bytes] = {}
        self._archives: dict[tuple[str, str], WorkspaceArchive] = {}
        self._lock = RLock()

    def clear(self) -> None:
        with self._lock:
            self._applications.clear()
            self._cv_versions.clear()
            self._cv_content.clear()
            self._archives.clear()

    def list_applications(self, owner_id: str) -> list[Application]:
        with self._lock:
            values = [
                item.model_copy(deep=True)
                for (owner, _), item in self._applications.items()
                if owner == owner_id and item.archive_id is None
            ]
        return sorted(values, key=lambda item: item.updated_at, reverse=True)

    def get_application(self, owner_id: str, application_id: str) -> Application:
        with self._lock:
            item = self._applications.get((owner_id, application_id))
            if item is None or item.archive_id is not None:
                raise NotFoundError("Application not found")
            return item.model_copy(deep=True)

    def create_application(self, owner_id: str, payload: ApplicationCreate) -> Application:
        if payload.cv_version_id:
            self.get_cv_version(owner_id, payload.cv_version_id)
        application = Application.new(owner_id, payload)
        with self._lock:
            self._applications[(owner_id, application.id)] = application
        return application.model_copy(deep=True)

    def update_application(
        self, owner_id: str, application_id: str, payload: ApplicationUpdate
    ) -> Application:
        key = (owner_id, application_id)
        with self._lock:
            current = self._applications.get(key)
            if current is None or current.archive_id is not None:
                raise NotFoundError("Application not found")
            changes = payload.model_dump(exclude_unset=True)
            cv_version_id = changes.get("cv_version_id")
            if cv_version_id:
                self.get_cv_version(owner_id, cv_version_id)
            updated = current.model_copy(update={**changes, "updated_at": datetime.now(UTC)})
            self._applications[key] = updated
            return updated.model_copy(deep=True)

    def list_cv_versions(self, owner_id: str) -> list[CvVersion]:
        with self._lock:
            values = [
                item.model_copy(deep=True)
                for (owner, _), item in self._cv_versions.items()
                if owner == owner_id and item.archive_id is None
            ]
        return sorted(values, key=lambda item: item.created_at, reverse=True)

    def get_cv_version(self, owner_id: str, cv_version_id: str) -> CvVersion:
        with self._lock:
            item = self._cv_versions.get((owner_id, cv_version_id))
            if item is None or item.archive_id is not None:
                raise NotFoundError("CV version not found")
            return item.model_copy(deep=True)

    def create_cv_version(self, version: CvVersion, content: bytes) -> CvVersion:
        key = (version.owner_id, version.id)
        with self._lock:
            if key in self._cv_versions:
                raise ValueError("CV version already exists")
            self._cv_versions[key] = version.model_copy(deep=True)
            self._cv_content[key] = bytes(content)
        return version.model_copy(deep=True)

    def get_cv_content(self, owner_id: str, cv_version_id: str) -> bytes:
        self.get_cv_version(owner_id, cv_version_id)
        with self._lock:
            return bytes(self._cv_content[(owner_id, cv_version_id)])

    def list_workspace_archives(self, owner_id: str) -> list[WorkspaceArchive]:
        with self._lock:
            archives = [
                item.model_copy(deep=True)
                for (owner, _), item in self._archives.items()
                if owner == owner_id
            ]
        return sorted(archives, key=lambda item: item.created_at, reverse=True)

    def archive_workspace(self, owner_id: str, label: str) -> WorkspaceArchive:
        cleaned_label = label.strip()
        if not cleaned_label:
            raise ValueError("Archive name must not be blank")
        with self._lock:
            applications = [
                item for (owner, _), item in self._applications.items()
                if owner == owner_id and item.archive_id is None
            ]
            versions = [
                item for (owner, _), item in self._cv_versions.items()
                if owner == owner_id and item.archive_id is None
            ]
            if not applications and not versions:
                raise EmptyWorkspaceError("The workspace is already empty")
            archive = WorkspaceArchive(
                id=uuid4().hex,
                owner_id=owner_id,
                label=cleaned_label,
                application_count=len(applications),
                cv_version_count=len(versions),
                created_at=datetime.now(UTC),
            )
            for application in applications:
                self._applications[(owner_id, application.id)] = application.model_copy(
                    update={"archive_id": archive.id}
                )
            for version in versions:
                self._cv_versions[(owner_id, version.id)] = version.model_copy(
                    update={"archive_id": archive.id}
                )
            self._archives[(owner_id, archive.id)] = archive
            return archive.model_copy(deep=True)

    def get_workspace_archive(self, owner_id: str, archive_id: str) -> WorkspaceArchiveDetail:
        with self._lock:
            archive = self._archives.get((owner_id, archive_id))
            if archive is None:
                raise NotFoundError("Workspace archive not found")
            applications = [
                item.model_copy(deep=True)
                for (owner, _), item in self._applications.items()
                if owner == owner_id and item.archive_id == archive_id
            ]
            versions = [
                item.model_copy(deep=True)
                for (owner, _), item in self._cv_versions.items()
                if owner == owner_id and item.archive_id == archive_id
            ]
            return WorkspaceArchiveDetail(
                archive=archive.model_copy(deep=True),
                applications=sorted(applications, key=lambda item: item.updated_at, reverse=True),
                cv_versions=sorted(versions, key=lambda item: item.created_at, reverse=True),
            )

    def get_archived_cv_content(
        self, owner_id: str, archive_id: str, cv_version_id: str
    ) -> bytes:
        with self._lock:
            version = self._cv_versions.get((owner_id, cv_version_id))
            if version is None or version.archive_id != archive_id:
                raise NotFoundError("Archived CV version not found")
            return bytes(self._cv_content[(owner_id, cv_version_id)])
