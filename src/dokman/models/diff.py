"""Configuration diff data models for Dokman."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ResourceLimitsDiff:
    """Differences in resource limits for a service."""

    memory: tuple[str | None, str | None] | None = None  # (expected, actual) in bytes or None
    memory_swap: tuple[str | None, str | None] | None = None
    cpu_period: tuple[str | None, str | None] | None = None
    cpu_quota: tuple[str | None, str | None] | None = None
    cpu_shares: tuple[str | None, str | None] | None = None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "memory": self.memory,
            "memory_swap": self.memory_swap,
            "cpu_period": self.cpu_period,
            "cpu_quota": self.cpu_quota,
            "cpu_shares": self.cpu_shares,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ResourceLimitsDiff":
        """Deserialize from dictionary."""
        if not data:
            return cls()
        return cls(
            memory=data.get("memory"),
            memory_swap=data.get("memory_swap"),
            cpu_period=data.get("cpu_period"),
            cpu_quota=data.get("cpu_quota"),
            cpu_shares=data.get("cpu_shares"),
        )

    def has_changes(self) -> bool:
        """Check if any limits differ."""
        return bool(
            self.memory or self.memory_swap or self.cpu_period or self.cpu_quota or self.cpu_shares
        )


@dataclass
class ServiceDiff:
    """Differences detected for a single service."""

    service_name: str
    status: Literal["unchanged", "modified", "missing", "extra"]
    image_diff: tuple[str, str] | None = None  # (expected, actual)
    env_diff: dict[str, tuple[str | None, str | None]] = field(
        default_factory=dict
    )  # {key: (expected, actual)}
    ports_diff: tuple[list[str], list[str]] | None = None  # (expected, actual)
    volumes_diff: tuple[list[str], list[str]] | None = None  # (expected, actual)
    labels_diff: dict[str, tuple[str | None, str | None]] = field(
        default_factory=dict
    )  # {key: (expected, actual)}
    limits_diff: ResourceLimitsDiff | None = None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "service_name": self.service_name,
            "status": self.status,
            "image_diff": list(self.image_diff) if self.image_diff else None,
            "env_diff": {
                k: [v[0], v[1]] for k, v in self.env_diff.items()
            },
            "ports_diff": [list(self.ports_diff[0]), list(self.ports_diff[1])]
            if self.ports_diff
            else None,
            "volumes_diff": [list(self.volumes_diff[0]), list(self.volumes_diff[1])]
            if self.volumes_diff
            else None,
            "labels_diff": {
                k: [v[0], v[1]] for k, v in self.labels_diff.items()
            },
            "limits_diff": self.limits_diff.to_dict() if self.limits_diff else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ServiceDiff":
        """Deserialize from dictionary."""
        image_diff = None
        if data.get("image_diff"):
            image_diff = tuple(data["image_diff"])

        env_diff = {}
        for k, v in data.get("env_diff", {}).items():
            env_diff[k] = (v[0], v[1])

        ports_diff = None
        if data.get("ports_diff"):
            ports_diff = (data["ports_diff"][0], data["ports_diff"][1])

        volumes_diff = None
        if data.get("volumes_diff"):
            volumes_diff = (data["volumes_diff"][0], data["volumes_diff"][1])

        labels_diff = {}
        for k, v in data.get("labels_diff", {}).items():
            labels_diff[k] = (v[0], v[1])

        limits_diff = None
        if data.get("limits_diff"):
            limits_diff = ResourceLimitsDiff.from_dict(data["limits_diff"])

        return cls(
            service_name=data["service_name"],
            status=data["status"],
            image_diff=image_diff,
            env_diff=env_diff,
            ports_diff=ports_diff,
            volumes_diff=volumes_diff,
            labels_diff=labels_diff,
            limits_diff=limits_diff,
        )


@dataclass
class ConfigDiff:
    """Overall configuration diff result."""

    project_name: str
    has_changes: bool
    services: list[ServiceDiff] = field(default_factory=list)
    missing_services: list[str] = field(default_factory=list)  # In config but not running
    extra_services: list[str] = field(default_factory=list)  # Running but not in config

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "project_name": self.project_name,
            "has_changes": self.has_changes,
            "services": [s.to_dict() for s in self.services],
            "missing_services": self.missing_services,
            "extra_services": self.extra_services,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConfigDiff":
        """Deserialize from dictionary."""
        return cls(
            project_name=data["project_name"],
            has_changes=data["has_changes"],
            services=[ServiceDiff.from_dict(s) for s in data.get("services", [])],
            missing_services=data.get("missing_services", []),
            extra_services=data.get("extra_services", []),
        )
