from __future__ import annotations

from datetime import UTC, datetime
from threading import RLock
from typing import Protocol

from advisory.career import Application, ApplicationCreate, ApplicationUpdate, CvVersion


class NotFoundError(LookupError):
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


class InMemoryCareerRepository:
    """Thread-safe owner-scoped repository used by local preview and tests."""

    def __init__(self) -> None:
        self._applications: dict[tuple[str, str], Application] = {}
        self._cv_versions: dict[tuple[str, str], CvVersion] = {}
        self._cv_content: dict[tuple[str, str], bytes] = {}
        self._lock = RLock()

    def clear(self) -> None:
        with self._lock:
            self._applications.clear()
            self._cv_versions.clear()
            self._cv_content.clear()

    def list_applications(self, owner_id: str) -> list[Application]:
        with self._lock:
            values = [
                item.model_copy(deep=True)
                for (owner, _), item in self._applications.items()
                if owner == owner_id
            ]
        return sorted(values, key=lambda item: item.updated_at, reverse=True)

    def get_application(self, owner_id: str, application_id: str) -> Application:
        with self._lock:
            item = self._applications.get((owner_id, application_id))
            if item is None:
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
            if current is None:
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
                if owner == owner_id
            ]
        return sorted(values, key=lambda item: item.created_at, reverse=True)

    def get_cv_version(self, owner_id: str, cv_version_id: str) -> CvVersion:
        with self._lock:
            item = self._cv_versions.get((owner_id, cv_version_id))
            if item is None:
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
