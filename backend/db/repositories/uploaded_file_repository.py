"""Repository for :class:`UploadedFile` entities."""

from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import UploadedFile
from db.repositories.base import BaseRepository


class UploadedFileRepository(BaseRepository[UploadedFile]):
    """CRUD + domain-specific queries for uploaded file tracking."""

    model = UploadedFile

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    # ------------------------------------------------------------------
    # Read – domain-specific lookups
    # ------------------------------------------------------------------

    def get_by_filename(self, filename: str) -> Optional[UploadedFile]:
        """Return the most recent record for a given filename."""
        stmt = (
            select(UploadedFile)
            .where(UploadedFile.filename == filename)
            .order_by(UploadedFile.uploaded_at.desc())
        )
        return self.session.execute(stmt).scalars().first()

    def get_by_filename_and_type(
        self,
        filename: str,
        file_type: str,
    ) -> Optional[UploadedFile]:
        """Return a file record by its (filename, file_type) unique key."""
        stmt = (
            select(UploadedFile)
            .where(UploadedFile.filename == filename)
            .where(UploadedFile.file_type == file_type)
        )
        return self.session.execute(stmt).scalars().first()

    def get_by_checksum(self, checksum: str) -> Optional[UploadedFile]:
        """Return a file record by its SHA-256 checksum.

        Useful for detecting duplicate / unchanged re-uploads.
        """
        stmt = select(UploadedFile).where(UploadedFile.checksum == checksum)
        return self.session.execute(stmt).scalars().first()

    def list_by_type(self, file_type: str) -> List[UploadedFile]:
        """Return all uploaded files of a given type."""
        stmt = (
            select(UploadedFile)
            .where(UploadedFile.file_type == file_type)
            .order_by(UploadedFile.uploaded_at.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_by_status(self, status: str) -> List[UploadedFile]:
        """Return all uploaded files with a given status."""
        stmt = (
            select(UploadedFile)
            .where(UploadedFile.status == status)
            .order_by(UploadedFile.uploaded_at.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_latest_by_type(self, file_type: str) -> Optional[UploadedFile]:
        """Return the most recently uploaded file of a given type."""
        stmt = (
            select(UploadedFile)
            .where(UploadedFile.file_type == file_type)
            .order_by(UploadedFile.uploaded_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalars().first()

    # ------------------------------------------------------------------
    # Create / upsert
    # ------------------------------------------------------------------

    def upsert(self, data: dict[str, Any]) -> UploadedFile:
        """Insert or update a file record by (filename, file_type).

        If a record with the same ``filename`` + ``file_type`` already
        exists, it is updated; otherwise a new row is inserted.
        """
        filename = data.get("filename")
        file_type = data.get("file_type")
        if not filename or not file_type:
            raise ValueError("filename and file_type are required")

        existing = self.get_by_filename_and_type(filename, file_type)
        if existing is not None:
            return self.update(existing, data)
        return self.create(data)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_by_filename_and_type(
        self,
        filename: str,
        file_type: str,
    ) -> bool:
        """Delete a file record by its (filename, file_type) key."""
        entity = self.get_by_filename_and_type(filename, file_type)
        if entity is None:
            return False
        return self.delete(entity)