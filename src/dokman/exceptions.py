"""Custom exceptions for Dokman."""

from pathlib import Path
from typing import NamedTuple


class DokmanError(Exception):
    """Base exception for Dokman errors."""

    pass


class ProjectNotFoundError(DokmanError):
    """Raised when a project cannot be found."""

    def __init__(self, project_name: str):
        self.project_name = project_name
        super().__init__(f"Project '{project_name}' not found")


class ServiceNotFoundError(DokmanError):
    """Raised when a service cannot be found in a project."""

    def __init__(self, project_name: str, service_name: str):
        self.project_name = project_name
        self.service_name = service_name
        super().__init__(
            f"Service '{service_name}' not found in project '{project_name}'"
        )


class ServiceNotRunningError(DokmanError):
    """Raised when an operation requires a running service."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        super().__init__(f"Service '{service_name}' is not running")


class ComposeFileNotFoundError(DokmanError):
    """Raised when compose file doesn't exist at registered path."""

    def __init__(self, path: Path):
        self.path = path
        super().__init__(f"Compose file not found at '{path}'")


class DockerConnectionError(DokmanError):
    """Raised when Docker daemon is not accessible."""

    pass


class RegistryError(DokmanError):
    """Raised for project registry operations failures."""

    pass


class OrphanContainerInfo(NamedTuple):
    """Information about an orphan container."""

    container_id: str
    container_name: str
    project_name: str
    service_name: str
    status: str
    created_at: str | None = None


class OrphanContainersError(DokmanError):
    """Raised when orphan containers are detected from an unregistered project."""

    def __init__(self, orphans: list[OrphanContainerInfo]):
        self.orphans = orphans
        project_names = set(o.project_name for o in orphans)
        if len(project_names) == 1:
            msg = (
                f"Container(s) found for unregistered project '{list(project_names)[0]}'.\n"
                f"  Run 'dokman down --remove-orphans' in the project directory to clean up,\n"
                f"  or use 'dokman doctor' for system diagnostics."
            )
        else:
            msg = (
                f"Container(s) found for unregistered projects: {', '.join(project_names)}.\n"
                f"  Run 'dokman down --remove-orphans' in each project directory to clean up,\n"
                f"  or use 'dokman doctor' for system diagnostics."
            )
        super().__init__(msg)


class StaleRegistryEntryError(DokmanError):
    """Raised when a registered project's compose file has been deleted."""

    def __init__(self, project_name: str, compose_file: Path):
        self.project_name = project_name
        self.compose_file = compose_file
        super().__init__(
            f"Project '{project_name}' is registered but compose file is missing: '{compose_file}'.\n"
            f"  Run 'dokman prune-registry' to clean up stale entries,\n"
            f"  or use 'dokman doctor' to find all stale entries."
        )
