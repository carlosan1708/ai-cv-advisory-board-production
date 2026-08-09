from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from advisory.career import CvVersion
from advisory.career_repository import CareerRepository
from advisory.ingestion import CvDocumentParser


class TrackerService:
    def __init__(self, repository: CareerRepository, parser: CvDocumentParser) -> None:
        self.repository = repository
        self.parser = parser

    def create_cv_version(
        self,
        owner_id: str,
        *,
        label: str,
        filename: str,
        content_type: str,
        content: bytes,
        parent_version_id: str | None = None,
    ) -> CvVersion:
        safe_filename = Path(filename).name
        clean_label = label.strip()
        if not clean_label:
            raise ValueError("Give this CV version a label")
        if len(clean_label) > 100:
            raise ValueError("CV label must be 100 characters or fewer")
        extracted_text = self.parser.parse(safe_filename, content)
        version = CvVersion(
            id=uuid4().hex,
            owner_id=owner_id,
            label=clean_label,
            filename=safe_filename,
            content_type=content_type or "application/octet-stream",
            byte_count=len(content),
            sha256=sha256(content).hexdigest(),
            extracted_text=extracted_text,
            parent_version_id=parent_version_id,
            created_at=datetime.now(UTC),
        )
        return self.repository.create_cv_version(version, content)
