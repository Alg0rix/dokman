"""Backup and restore data models for Dokman."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class BackupInfo:
    """Information about a volume backup."""

    filename: str
    project_name: str
    volumes: list[str]
    created_at: datetime
    size_bytes: int

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "filename": self.filename,
            "project_name": self.project_name,
            "volumes": self.volumes,
            "created_at": self.created_at.isoformat(),
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BackupInfo":
        """Deserialize from dictionary."""
        return cls(
            filename=data["filename"],
            project_name=data["project_name"],
            volumes=data["volumes"],
            created_at=datetime.fromisoformat(data["created_at"]),
            size_bytes=data["size_bytes"],
        )


@dataclass
class BackupResult:
    """Result of a backup operation."""

    success: bool
    backup_path: str | None
    volumes_backed_up: list[str] = field(default_factory=list)
    volumes_skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "success": self.success,
            "backup_path": self.backup_path,
            "volumes_backed_up": self.volumes_backed_up,
            "volumes_skipped": self.volumes_skipped,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BackupResult":
        """Deserialize from dictionary."""
        return cls(
            success=data["success"],
            backup_path=data.get("backup_path"),
            volumes_backed_up=data.get("volumes_backed_up", []),
            volumes_skipped=data.get("volumes_skipped", []),
            errors=data.get("errors", []),
        )


@dataclass
class RestoreResult:
    """Result of a restore operation."""

    success: bool
    volumes_restored: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "success": self.success,
            "volumes_restored": self.volumes_restored,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RestoreResult":
        """Deserialize from dictionary."""
        return cls(
            success=data["success"],
            volumes_restored=data.get("volumes_restored", []),
            errors=data.get("errors", []),
        )
