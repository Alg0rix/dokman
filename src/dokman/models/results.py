"""Operation result data models for Dokman."""

from dataclasses import dataclass, field


@dataclass
class OperationResult:
    """Result of a service operation (start, stop, restart, etc.)."""

    success: bool
    message: str
    affected_services: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "success": self.success,
            "message": self.message,
            "affected_services": self.affected_services,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OperationResult":
        """Deserialize from dictionary."""
        return cls(
            success=data["success"],
            message=data["message"],
            affected_services=data.get("affected_services", []),
            errors=data.get("errors", []),
        )


@dataclass
class PullResult:
    """Result of an image pull operation."""

    updated: list[str] = field(default_factory=list)
    up_to_date: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (image, error)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "updated": self.updated,
            "up_to_date": self.up_to_date,
            "failed": [{"image": img, "error": err} for img, err in self.failed],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PullResult":
        """Deserialize from dictionary."""
        return cls(
            updated=data.get("updated", []),
            up_to_date=data.get("up_to_date", []),
            failed=[(f["image"], f["error"]) for f in data.get("failed", [])],
        )


@dataclass
class BuildResult:
    """Result of an image build operation."""

    built: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (service, error)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "built": self.built,
            "skipped": self.skipped,
            "failed": [{"service": svc, "error": err} for svc, err in self.failed],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BuildResult":
        """Deserialize from dictionary."""
        return cls(
            built=data.get("built", []),
            skipped=data.get("skipped", []),
            failed=[(f["service"], f["error"]) for f in data.get("failed", [])],
        )


@dataclass
class ComposeResult:
    """Result of a Docker Compose command execution."""

    success: bool
    output: str
    error: str | None = None
    return_code: int = 0

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "return_code": self.return_code,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ComposeResult":
        """Deserialize from dictionary."""
        return cls(
            success=data["success"],
            output=data["output"],
            error=data.get("error"),
            return_code=data.get("return_code", 0),
        )
