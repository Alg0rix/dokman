"""Enums for Dokman data models."""

from enum import Enum


class ServiceStatus(Enum):
    """Status of a Docker Compose service."""

    RUNNING = "running"
    STOPPED = "stopped"
    RESTARTING = "restarting"
    PAUSED = "paused"
    EXITED = "exited"
    DEAD = "dead"


class ProjectHealth(Enum):
    """Overall health status of a Docker Compose project."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
