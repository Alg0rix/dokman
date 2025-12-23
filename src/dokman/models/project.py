"""Project and service data models for Dokman."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from dokman.models.enums import ProjectHealth, ServiceStatus


@dataclass
class Service:
    """Represents a service within a Docker Compose project."""

    name: str
    container_id: str | None
    image: str
    status: ServiceStatus
    ports: list[str] = field(default_factory=list)
    health: str | None = None
    uptime: datetime | None = None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "container_id": self.container_id,
            "image": self.image,
            "status": self.status.value,
            "ports": self.ports,
            "health": self.health,
            "uptime": self.uptime.isoformat() if self.uptime else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Service":
        """Deserialize from dictionary."""
        return cls(
            name=data["name"],
            container_id=data["container_id"],
            image=data["image"],
            status=ServiceStatus(data["status"]),
            ports=data.get("ports", []),
            health=data.get("health"),
            uptime=datetime.fromisoformat(data["uptime"]) if data.get("uptime") else None,
        )


@dataclass
class Project:
    """Represents a Docker Compose project."""

    name: str
    compose_file: Path
    working_dir: Path
    services: list[Service] = field(default_factory=list)
    status: ProjectHealth = ProjectHealth.UNKNOWN
    created_at: datetime | None = None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "compose_file": str(self.compose_file),
            "working_dir": str(self.working_dir),
            "services": [s.to_dict() for s in self.services],
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        """Deserialize from dictionary."""
        return cls(
            name=data["name"],
            compose_file=Path(data["compose_file"]),
            working_dir=Path(data["working_dir"]),
            services=[Service.from_dict(s) for s in data.get("services", [])],
            status=ProjectHealth(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
        )


@dataclass
class RegisteredProject:
    """Represents a project registered in Dockman's tracking database."""

    name: str
    compose_file: Path
    registered_at: datetime
    last_accessed: datetime | None = None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "compose_file": str(self.compose_file),
            "registered_at": self.registered_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RegisteredProject":
        """Deserialize from dictionary."""
        return cls(
            name=data["name"],
            compose_file=Path(data["compose_file"]),
            registered_at=datetime.fromisoformat(data["registered_at"]),
            last_accessed=datetime.fromisoformat(data["last_accessed"]) if data.get("last_accessed") else None,
        )
