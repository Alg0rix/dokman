"""Shared CLI helpers and utilities."""

from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console

from dokman.cli.formatter import OutputFormatter
from dokman.clients.compose_client import ComposeClient
from dokman.clients.docker_client import DockerClient
from dokman.exceptions import (
    ComposeFileNotFoundError,
    DockerConnectionError,
    DokmanError,
    OrphanContainersError,
    ProjectNotFoundError,
    ServiceNotFoundError,
    ServiceNotRunningError,
    StaleRegistryEntryError,
)
from dokman.services.project_manager import ProjectManager
from dokman.services.resource_manager import ResourceManager
from dokman.services.service_manager import ServiceManager
from dokman.storage.registry import ProjectRegistry

if TYPE_CHECKING:
    from dokman.models.project import Project
    from dokman.services.config_manager import ConfigManager

console = Console()
formatter = OutputFormatter(console)

EXIT_SUCCESS = 0
EXIT_GENERAL_ERROR = 1
EXIT_PROJECT_NOT_FOUND = 2
EXIT_SERVICE_NOT_FOUND = 3
EXIT_DOCKER_CONNECTION_ERROR = 4
EXIT_COMPOSE_FILE_ERROR = 5
EXIT_OPERATION_FAILED = 6
EXIT_NO_PROJECT_DETECTED = 7


class OutputFormat(str, Enum):
    """Output format options."""

    table = "table"
    json = "json"


def get_project_manager() -> ProjectManager:
    """Create and return a ProjectManager instance with pooled clients."""
    registry = ProjectRegistry()
    docker = DockerClient.get_shared()
    compose = ComposeClient.get_shared()
    return ProjectManager(registry, docker, compose)


def get_service_manager() -> ServiceManager:
    """Create and return a ServiceManager instance with pooled clients."""
    docker = DockerClient.get_shared()
    compose = ComposeClient.get_shared()
    return ServiceManager(docker, compose)


def get_resource_manager() -> ResourceManager:
    """Create and return a ResourceManager instance with pooled clients."""
    docker = DockerClient.get_shared()
    compose = ComposeClient.get_shared()
    return ResourceManager(docker, compose)


def get_config_manager() -> "ConfigManager":
    """Create and return a ConfigManager instance with pooled clients."""
    from dokman.services.config_manager import ConfigManager

    docker = DockerClient.get_shared()
    compose = ComposeClient.get_shared()
    return ConfigManager(docker, compose)


def close_shared_clients() -> None:
    """Close shared Docker client connections. Call on app exit."""
    DockerClient.reset_shared()
    ComposeClient.reset_shared()


def resolve_project(
    pm: ProjectManager,
    project_name: str | None,
    auto_detect_message: bool = True,
) -> "Project":
    """Resolve a project by name or auto-detect from current directory.

    This helper reduces code duplication across commands that need to
    resolve a project from either an explicit name or the current directory.

    Args:
        pm: ProjectManager instance
        project_name: Explicit project name, or None to auto-detect
        auto_detect_message: If True, print a message when auto-detecting

    Returns:
        The resolved Project

    Raises:
        ProjectNotFoundError: If project name given but not found
        typer.Exit: If no project specified and none found in current directory
    """
    if project_name:
        proj = pm.get_project(project_name)
        if proj is None:
            raise ProjectNotFoundError(project_name)
        return proj

    # Auto-detect from current directory
    proj = pm.get_project_by_path(Path.cwd())
    if proj:
        if auto_detect_message:
            console.print(f"[dim]Auto-detected project: [cyan]{proj.name}[/cyan][/dim]")
        return proj

    console.print(
        "[red]Error:[/red] No project specified and none found in current directory."
    )
    raise typer.Exit(EXIT_NO_PROJECT_DETECTED)


def handle_error(e: Exception) -> None:
    """Handle exceptions and exit with appropriate code."""
    if isinstance(e, ProjectNotFoundError):
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(EXIT_PROJECT_NOT_FOUND)
    elif isinstance(e, ServiceNotFoundError):
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(EXIT_SERVICE_NOT_FOUND)
    elif isinstance(e, ServiceNotRunningError):
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(EXIT_OPERATION_FAILED)
    elif isinstance(e, DockerConnectionError):
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(EXIT_DOCKER_CONNECTION_ERROR)
    elif isinstance(e, ComposeFileNotFoundError):
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(EXIT_COMPOSE_FILE_ERROR)
    elif isinstance(e, OrphanContainersError):
        console.print(f"[red]Error:[/red] {e}")
        console.print()
        console.print("[yellow]Tip:[/yellow] To clean up orphan containers:")
        for orphan in e.orphans:
            console.print(
                f"  - Run 'docker stop {orphan.container_name}' and 'docker rm {orphan.container_name}'"
            )
        raise typer.Exit(EXIT_GENERAL_ERROR)
    elif isinstance(e, StaleRegistryEntryError):
        console.print(f"[yellow]Warning:[/yellow] {e}")
        raise typer.Exit(EXIT_GENERAL_ERROR)
    elif isinstance(e, DokmanError):
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(EXIT_GENERAL_ERROR)
    else:
        console.print(f"[red]Unexpected error:[/red] {e}")
        raise typer.Exit(EXIT_GENERAL_ERROR)
