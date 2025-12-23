"""Custom exceptions for Dokman."""

from pathlib import Path


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
