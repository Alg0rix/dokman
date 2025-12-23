"""Resource data models for Dokman."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ImageInfo:
    """Information about a Docker image."""

    id: str
    repository: str
    tag: str
    size: int
    created: datetime
    used_by: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "repository": self.repository,
            "tag": self.tag,
            "size": self.size,
            "created": self.created.isoformat(),
            "used_by": self.used_by,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ImageInfo":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            repository=data["repository"],
            tag=data["tag"],
            size=data["size"],
            created=datetime.fromisoformat(data["created"]),
            used_by=data.get("used_by", []),
        )


@dataclass
class VolumeInfo:
    """Information about a Docker volume."""

    name: str
    driver: str
    mountpoint: str
    size: int | None = None
    used_by: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "driver": self.driver,
            "mountpoint": self.mountpoint,
            "size": self.size,
            "used_by": self.used_by,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VolumeInfo":
        """Deserialize from dictionary."""
        return cls(
            name=data["name"],
            driver=data["driver"],
            mountpoint=data["mountpoint"],
            size=data.get("size"),
            used_by=data.get("used_by", []),
        )


@dataclass
class NetworkInfo:
    """Information about a Docker network."""

    name: str
    driver: str
    subnet: str | None = None
    gateway: str | None = None
    containers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "driver": self.driver,
            "subnet": self.subnet,
            "gateway": self.gateway,
            "containers": self.containers,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NetworkInfo":
        """Deserialize from dictionary."""
        return cls(
            name=data["name"],
            driver=data["driver"],
            subnet=data.get("subnet"),
            gateway=data.get("gateway"),
            containers=data.get("containers", []),
        )


@dataclass
class ContainerStats:
    """Resource usage statistics for a container."""

    container_id: str
    name: str
    cpu_percent: float
    memory_usage: int
    memory_limit: int
    memory_percent: float
    network_rx: int
    network_tx: int

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "container_id": self.container_id,
            "name": self.name,
            "cpu_percent": self.cpu_percent,
            "memory_usage": self.memory_usage,
            "memory_limit": self.memory_limit,
            "memory_percent": self.memory_percent,
            "network_rx": self.network_rx,
            "network_tx": self.network_tx,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContainerStats":
        """Deserialize from dictionary."""
        return cls(
            container_id=data["container_id"],
            name=data["name"],
            cpu_percent=data["cpu_percent"],
            memory_usage=data["memory_usage"],
            memory_limit=data["memory_limit"],
            memory_percent=data["memory_percent"],
            network_rx=data["network_rx"],
            network_tx=data["network_tx"],
        )
