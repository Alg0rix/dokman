"""Main CLI application for Dokman."""

from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

from dokman.cli.formatter import OutputFormatter
from dokman.clients.compose_client import ComposeClient
from dokman.clients.docker_client import DockerClient
from dokman.exceptions import (
    ComposeFileNotFoundError,
    DockerConnectionError,
    DokmanError,
    ProjectNotFoundError,
    ServiceNotFoundError,
    ServiceNotRunningError,
)
from dokman.services.project_manager import ProjectManager
from dokman.services.resource_manager import ResourceManager
from dokman.services.service_manager import ServiceManager
from dokman.storage.registry import ProjectRegistry
from dokman.models.project import Project

# Console for output
console = Console()
formatter = OutputFormatter(console)

# Exit codes
EXIT_SUCCESS = 0
EXIT_GENERAL_ERROR = 1
EXIT_PROJECT_NOT_FOUND = 2
EXIT_SERVICE_NOT_FOUND = 3
EXIT_DOCKER_CONNECTION_ERROR = 4
EXIT_COMPOSE_FILE_ERROR = 5
EXIT_OPERATION_FAILED = 6


class OutputFormat(str, Enum):
    """Output format options."""

    table = "table"
    json = "json"


# Main app
app = typer.Typer(
    name="dokman",
    help="Centralized Docker Compose deployment management",
    no_args_is_help=True,
)


def get_project_manager() -> ProjectManager:
    """Create and return a ProjectManager instance."""
    registry = ProjectRegistry()
    docker = DockerClient()
    compose = ComposeClient()
    return ProjectManager(registry, docker, compose)


def get_service_manager() -> ServiceManager:
    """Create and return a ServiceManager instance."""
    docker = DockerClient()
    compose = ComposeClient()
    return ServiceManager(docker, compose)


def get_resource_manager() -> ResourceManager:
    """Create and return a ResourceManager instance."""
    docker = DockerClient()
    compose = ComposeClient()
    return ResourceManager(docker, compose)


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
    
    console.print("[red]Error:[/red] No project specified and none found in current directory.")
    raise typer.Exit(EXIT_GENERAL_ERROR)


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
    elif isinstance(e, DokmanError):
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(EXIT_GENERAL_ERROR)
    else:
        console.print(f"[red]Unexpected error:[/red] {e}")
        raise typer.Exit(EXIT_GENERAL_ERROR)


@app.callback()
def main() -> None:
    """Dokman - Manage Docker Compose deployments from anywhere."""
    # Check for updates (uses cache to avoid repeated network calls)
    try:
        from dokman.services.version_checker import VersionChecker
        checker = VersionChecker()
        update_info = checker.check_for_update()
        if update_info:
            console.print()
            console.print(
                f"[bold cyan]📦 Update available:[/bold cyan] "
                f"dokman [green]{update_info.latest_version}[/green] "
                f"[dim](current: {update_info.current_version})[/dim]"
            )
            console.print(
                f"   Run [yellow]`{update_info.upgrade_command}`[/yellow] to update"
            )
            console.print()
    except Exception:
        # Never let update check break the CLI
        pass


# -----------------------------------------------------------------------------
# Project Management Commands
# -----------------------------------------------------------------------------


@app.command("list")
def list_projects(
    all_projects: Annotated[
        bool,
        typer.Option("--all", "-a", help="Include unregistered running projects"),
    ] = False,
    register: Annotated[
        bool,
        typer.Option("--register", "-r", help="Prompt to register discovered unregistered projects"),
    ] = False,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """List all Docker Compose projects.

    Shows registered projects and optionally discovers running unregistered projects.
    Use --register to be prompted to register any discovered unregistered projects.
    """
    try:
        pm = get_project_manager()
        
        # If --register is passed, automatically include unregistered projects
        include_unregistered = all_projects or register
        projects = pm.list_projects(include_unregistered=include_unregistered)

        if not projects:
            console.print("[dim]No projects found.[/dim]")
            if not include_unregistered:
                console.print(
                    "[dim]Tip: Use --all to discover running unregistered projects.[/dim]"
                )
            raise typer.Exit(EXIT_SUCCESS)

        formatter.print_projects(projects, as_json=(output_format == OutputFormat.json))
        
        # If --register flag is set, offer to register unregistered projects
        if register:
            # Get registered project names using public API
            registered_names = pm.get_registered_names()
            
            # Find unregistered projects from the list
            unregistered = [p for p in projects if p.name not in registered_names]
            
            if unregistered:
                console.print()
                console.print(f"[yellow]Found {len(unregistered)} unregistered project(s).[/yellow]")
                
                for project in unregistered:
                    if project.working_dir and project.working_dir.exists():
                        confirm = typer.confirm(
                            f"Register project '{project.name}' from {project.working_dir}?"
                        )
                        if confirm:
                            try:
                                registered = pm.register_project(project.working_dir, project.name)
                                console.print(
                                    f"[green]✓[/green] Registered project [cyan]{registered.name}[/cyan]"
                                )
                            except DokmanError as reg_error:
                                console.print(
                                    f"[red]✗[/red] Failed to register '{project.name}': {reg_error}"
                                )
                    else:
                        console.print(
                            f"[yellow]⚠[/yellow] Cannot register '{project.name}': working directory not found"
                        )
            else:
                console.print("[dim]All discovered projects are already registered.[/dim]")
    except DokmanError as e:
        handle_error(e)


@app.command("info")
def info_project(
    project: Annotated[
        Optional[str],
        typer.Argument(help="Project name (optional if in project directory)"),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """Display detailed information about a project.

    Shows services, status, ports, container IDs, images, and uptime.
    """
    try:
        pm = get_project_manager()
        
        if project:
            proj = pm.get_project(project)
        else:
            # Auto-detect from current directory
            proj = pm.get_project_by_path(Path.cwd())
            if proj:
                console.print(f"[dim]Auto-detected project: [cyan]{proj.name}[/cyan][/dim]")

        if proj is None:
            if project:
                raise ProjectNotFoundError(project)
            else:
                console.print("[red]Error:[/red] No project specified and none found in current directory.")
                raise typer.Exit(EXIT_GENERAL_ERROR)

        # Print project header
        if output_format == OutputFormat.json:
            formatter.print_json(proj)
        else:
            console.print(f"\n[bold cyan]{proj.name}[/bold cyan]")
            console.print(f"  Status: [{formatter._get_health_style(proj.status)}]{proj.status.value}[/{formatter._get_health_style(proj.status)}]")
            console.print(f"  Compose file: [dim]{proj.compose_file}[/dim]")
            console.print(f"  Working dir: [dim]{proj.working_dir}[/dim]")
            console.print()

            if proj.services:
                formatter.print_services(proj.services, proj.name, as_json=False)
            else:
                console.print("[dim]No services found.[/dim]")
    except DokmanError as e:
        handle_error(e)


@app.command("register")
def register_project(
    path: Annotated[
        Path,
        typer.Argument(
            help="Path to compose file or directory containing compose file",
            exists=True,
        ),
    ],
    name: Annotated[
        Optional[str],
        typer.Option("--name", "-n", help="Custom project name"),
    ] = None,
) -> None:
    """Register a Docker Compose project for tracking.

    Adds the project to Dokman's tracking database so it can be managed
    from any directory.
    """
    try:
        pm = get_project_manager()
        project = pm.register_project(path, name)
        console.print(
            f"[green]✓[/green] Registered project [cyan]{project.name}[/cyan]"
        )
        console.print(f"  Compose file: [dim]{project.compose_file}[/dim]")
    except DokmanError as e:
        handle_error(e)


@app.command("unregister")
def unregister_project(
    project: Annotated[str, typer.Argument(help="Project name to unregister")],
) -> None:
    """Remove a project from tracking.

    This does not affect running containers, only removes the project
    from Dokman's tracking database.
    """
    try:
        pm = get_project_manager()
        removed = pm.unregister_project(project)

        if removed:
            console.print(
                f"[green]✓[/green] Unregistered project [cyan]{project}[/cyan]"
            )
        else:
            console.print(f"[yellow]Project '{project}' was not registered.[/yellow]")
    except DokmanError as e:
        handle_error(e)


@app.command("up")
def up_project(
    path: Annotated[
        Optional[Path],
        typer.Option(
            "--file", "-f",
            help="Path to compose file or directory (defaults to current directory)",
        ),
    ] = None,
    name: Annotated[
        Optional[str],
        typer.Option("--name", "-n", help="Custom project name"),
    ] = None,
    detach: Annotated[
        bool,
        typer.Option("--detach", "-d", help="Run in detached mode (default)"),
    ] = True,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """Start a Docker Compose project (auto-registers if needed).

    This is a convenience command that registers the project (if not already
    registered) and starts all services. Use -f to specify a compose file path,
    or run from a directory containing a compose file.

    Examples:
        dokman up                    # Use compose file in current directory
        dokman up -f ./myproject     # Use compose file in ./myproject
        dokman up -f docker-compose.yml -n myapp  # Custom project name
    """
    try:
        pm = get_project_manager()
        compose = ComposeClient()

        # Default to current directory if no path provided
        compose_path = path or Path(".")

        # Resolve to absolute path
        compose_path = compose_path.resolve()

        # Check if path exists
        if not compose_path.exists():
            console.print(f"[red]Error:[/red] Path does not exist: {compose_path}")
            raise typer.Exit(EXIT_COMPOSE_FILE_ERROR)

        # Try to register the project (will use existing if already registered)
        try:
            proj = pm.register_project(compose_path, name)
            console.print(
                f"[green]✓[/green] Registered project [cyan]{proj.name}[/cyan]"
            )
        except DokmanError:
            # Project might already be registered, try to find it
            # Find compose file to determine project name
            if compose_path.is_file():
                working_dir = compose_path.parent
            else:
                working_dir = compose_path

            # Try to get existing project by directory name or custom name
            project_name = name or working_dir.name
            proj = pm.get_project(project_name)

            if proj is None:
                # Re-raise the original error
                raise

            console.print(
                f"[dim]Using existing project [cyan]{proj.name}[/cyan][/dim]"
            )

        # Run docker compose up
        console.print("[dim]Starting services...[/dim]")
        result = compose.up(proj.working_dir, detach=detach)

        if result.success:
            console.print(
                f"[green]✓[/green] Started project [cyan]{proj.name}[/cyan]"
            )
            if output_format == OutputFormat.json:
                formatter.print_json({
                    "project": proj.name,
                    "status": "started",
                    "compose_file": str(proj.compose_file),
                })
        else:
            console.print(f"[red]✗[/red] Failed to start project '{proj.name}'")
            if result.error:
                console.print(f"[red]Error:[/red] {result.error}")
            raise typer.Exit(EXIT_OPERATION_FAILED)
    except DokmanError as e:
        handle_error(e)


# -----------------------------------------------------------------------------
# Service Lifecycle Commands
# -----------------------------------------------------------------------------


@app.command("start")
def start_services(
    project: Annotated[
        Optional[str],
        typer.Argument(help="Project name (optional if in project directory)"),
    ] = None,
    service: Annotated[
        Optional[str],
        typer.Option("--service", "-s", help="Specific service to start"),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """Start services in a Docker Compose project.

    Starts all services or a specific service if --service is provided.
    """
    try:
        pm = get_project_manager()
        sm = get_service_manager()

        if project:
            proj = pm.get_project(project)
        else:
            proj = pm.get_project_by_path(Path.cwd())
            if proj:
                console.print(f"[dim]Auto-detected project: [cyan]{proj.name}[/cyan][/dim]")

        if proj is None:
            if project:
                raise ProjectNotFoundError(project)
            else:
                console.print("[red]Error:[/red] No project specified and none found in current directory.")
                raise typer.Exit(EXIT_GENERAL_ERROR)

        result = sm.start(proj, service)
        formatter.print_operation_result(result, as_json=(output_format == OutputFormat.json))

        if not result.success:
            raise typer.Exit(EXIT_OPERATION_FAILED)
    except DokmanError as e:
        handle_error(e)


@app.command("stop")
def stop_services(
    project: Annotated[
        Optional[str],
        typer.Argument(help="Project name (optional if in project directory)"),
    ] = None,
    service: Annotated[
        Optional[str],
        typer.Option("--service", "-s", help="Specific service to stop"),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """Stop services in a Docker Compose project.

    Stops all services or a specific service if --service is provided.
    """
    try:
        pm = get_project_manager()
        sm = get_service_manager()

        if project:
            proj = pm.get_project(project)
        else:
            proj = pm.get_project_by_path(Path.cwd())
            if proj:
                console.print(f"[dim]Auto-detected project: [cyan]{proj.name}[/cyan][/dim]")

        if proj is None:
            if project:
                raise ProjectNotFoundError(project)
            else:
                console.print("[red]Error:[/red] No project specified and none found in current directory.")
                raise typer.Exit(EXIT_GENERAL_ERROR)

        result = sm.stop(proj, service)
        formatter.print_operation_result(result, as_json=(output_format == OutputFormat.json))

        if not result.success:
            raise typer.Exit(EXIT_OPERATION_FAILED)
    except DokmanError as e:
        handle_error(e)


@app.command("restart")
def restart_services(
    project: Annotated[
        Optional[str],
        typer.Argument(help="Project name (optional if in project directory)"),
    ] = None,
    service: Annotated[
        Optional[str],
        typer.Option("--service", "-s", help="Specific service to restart"),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """Restart services in a Docker Compose project.

    Restarts all services or a specific service if --service is provided.
    Displays the new status of affected services.
    """
    try:
        pm = get_project_manager()
        sm = get_service_manager()

        if project:
            proj = pm.get_project(project)
        else:
            proj = pm.get_project_by_path(Path.cwd())
            if proj:
                console.print(f"[dim]Auto-detected project: [cyan]{proj.name}[/cyan][/dim]")

        if proj is None:
            if project:
                raise ProjectNotFoundError(project)
            else:
                console.print("[red]Error:[/red] No project specified and none found in current directory.")
                raise typer.Exit(EXIT_GENERAL_ERROR)

        result = sm.restart(proj, service)
        formatter.print_operation_result(result, as_json=(output_format == OutputFormat.json))

        if not result.success:
            raise typer.Exit(EXIT_OPERATION_FAILED)
    except DokmanError as e:
        handle_error(e)


@app.command("down")
def down_project(
    project: Annotated[
        Optional[str],
        typer.Argument(help="Project name (optional if in project directory)"),
    ] = None,
    volumes: Annotated[
        bool,
        typer.Option("--volumes", "-v", help="Also remove associated volumes"),
    ] = False,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """Stop and remove containers and networks for a project.

    Stops all running containers and removes containers, networks created
    by the project. Use --volumes to also remove associated volumes.
    """
    try:
        pm = get_project_manager()
        sm = get_service_manager()

        if project:
            proj = pm.get_project(project)
        else:
            proj = pm.get_project_by_path(Path.cwd())
            if proj:
                console.print(f"[dim]Auto-detected project: [cyan]{proj.name}[/cyan][/dim]")

        if proj is None:
            if project:
                raise ProjectNotFoundError(project)
            else:
                console.print("[red]Error:[/red] No project specified and none found in current directory.")
                raise typer.Exit(EXIT_GENERAL_ERROR)

        result = sm.down(proj, remove_volumes=volumes)
        formatter.print_operation_result(result, as_json=(output_format == OutputFormat.json))

        if not result.success:
            raise typer.Exit(EXIT_OPERATION_FAILED)
    except DokmanError as e:
        handle_error(e)


@app.command("redeploy")
def redeploy_project(
    project: Annotated[
        Optional[str],
        typer.Argument(help="Project name (optional if in project directory)"),
    ] = None,
    no_pull: Annotated[
        bool,
        typer.Option("--no-pull", help="Skip pulling latest images"),
    ] = False,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Fail if any image pull fails"),
    ] = False,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """Redeploy a project with updated images.

    Pulls the latest images and recreates all containers. Use --no-pull
    to recreate containers using existing local images. Use --strict to
    fail the operation if any image pull fails.
    """
    try:
        pm = get_project_manager()
        sm = get_service_manager()

        if project:
            proj = pm.get_project(project)
        else:
            proj = pm.get_project_by_path(Path.cwd())
            if proj:
                console.print(f"[dim]Auto-detected project: [cyan]{proj.name}[/cyan][/dim]")

        if proj is None:
            if project:
                raise ProjectNotFoundError(project)
            else:
                console.print("[red]Error:[/red] No project specified and none found in current directory.")
                raise typer.Exit(EXIT_GENERAL_ERROR)

        result = sm.redeploy(proj, pull=not no_pull, strict=strict)
        formatter.print_operation_result(result, as_json=(output_format == OutputFormat.json))

        if not result.success:
            raise typer.Exit(EXIT_OPERATION_FAILED)
    except DokmanError as e:
        handle_error(e)


@app.command("scale")
def scale_service(
    service: Annotated[str, typer.Argument(help="Service name to scale")],
    replicas: Annotated[int, typer.Argument(help="Number of replicas")],
    project: Annotated[
        Optional[str],
        typer.Option("--project", "-p", help="Project name (optional if in project directory)"),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """Scale a service to specified number of replicas.

    Adjusts the number of running containers for a service. Displays
    the new container IDs and their status after scaling.
    """
    try:
        pm = get_project_manager()
        sm = get_service_manager()

        if project:
            proj = pm.get_project(project)
        else:
            proj = pm.get_project_by_path(Path.cwd())
            if proj:
                console.print(f"[dim]Auto-detected project: [cyan]{proj.name}[/cyan][/dim]")

        if proj is None:
            if project:
                raise ProjectNotFoundError(project)
            else:
                console.print("[red]Error:[/red] No project specified and none found in current directory.")
                raise typer.Exit(EXIT_GENERAL_ERROR)

        result = sm.scale(proj, service, replicas)
        formatter.print_operation_result(result, as_json=(output_format == OutputFormat.json))

        if not result.success:
            raise typer.Exit(EXIT_OPERATION_FAILED)
    except DokmanError as e:
        handle_error(e)


# -----------------------------------------------------------------------------
# Debugging and Inspection Commands
# -----------------------------------------------------------------------------


@app.command("logs")
def show_logs(
    project: Annotated[
        Optional[str],
        typer.Argument(help="Project name (optional if in project directory)"),
    ] = None,
    service: Annotated[
        Optional[str],
        typer.Option("--service", "-s", help="Specific service to show logs for"),
    ] = None,
    follow: Annotated[
        bool,
        typer.Option("--follow", "-f", help="Follow log output in real-time"),
    ] = False,
    tail: Annotated[
        Optional[int],
        typer.Option("--tail", "-n", help="Number of lines to show from end of logs"),
    ] = None,
) -> None:
    """Display logs from Docker Compose services.

    Shows aggregated logs from all services or a specific service.
    Use --follow to stream logs in real-time.
    """
    try:
        pm = get_project_manager()
        sm = get_service_manager()

        if project:
            proj = pm.get_project(project)
        else:
            proj = pm.get_project_by_path(Path.cwd())
            if proj:
                console.print(f"[dim]Auto-detected project: [cyan]{proj.name}[/cyan][/dim]")

        if proj is None:
            if project:
                raise ProjectNotFoundError(project)
            else:
                console.print("[red]Error:[/red] No project specified and none found in current directory.")
                raise typer.Exit(EXIT_GENERAL_ERROR)

        for line in sm.logs(proj, service=service, follow=follow, tail=tail):
            console.print(line)
    except DokmanError as e:
        handle_error(e)
    except KeyboardInterrupt:
        # Graceful exit on Ctrl+C when following logs
        console.print("\n[dim]Log streaming stopped.[/dim]")


@app.command("exec")
def exec_command(
    service: Annotated[str, typer.Argument(help="Service name")],
    command: Annotated[list[str], typer.Argument(help="Command to execute")],
    project: Annotated[
        Optional[str],
        typer.Option("--project", "-p", help="Project name (optional if in project directory)"),
    ] = None,
    interactive: Annotated[
        bool,
        typer.Option("--interactive", "-i", help="Run in interactive mode with TTY"),
    ] = False,
) -> None:
    """Execute a command inside a running container.

    Runs the specified command in the container for the given service.
    Use --interactive for an interactive shell session.
    """
    try:
        pm = get_project_manager()
        sm = get_service_manager()

        if project:
            proj = pm.get_project(project)
        else:
            proj = pm.get_project_by_path(Path.cwd())
            if proj:
                console.print(f"[dim]Auto-detected project: [cyan]{proj.name}[/cyan][/dim]")

        if proj is None:
            if project:
                raise ProjectNotFoundError(project)
            else:
                console.print("[red]Error:[/red] No project specified and none found in current directory.")
                raise typer.Exit(EXIT_GENERAL_ERROR)

        exit_code = sm.exec(proj, service, command, interactive=interactive)
        raise typer.Exit(exit_code)
    except DokmanError as e:
        handle_error(e)


@app.command("health")
def show_health(
    project: Annotated[
        Optional[str],
        typer.Argument(help="Project name (optional if in project directory)"),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """Display health check status for services.

    Shows health check status for all services with health checks defined.
    """
    try:
        pm = get_project_manager()

        if project:
            proj = pm.get_project(project)
        else:
            proj = pm.get_project_by_path(Path.cwd())
            if proj:
                console.print(f"[dim]Auto-detected project: [cyan]{proj.name}[/cyan][/dim]")

        if proj is None:
            if project:
                raise ProjectNotFoundError(project)
            else:
                console.print("[red]Error:[/red] No project specified and none found in current directory.")
                raise typer.Exit(EXIT_GENERAL_ERROR)

        if output_format == OutputFormat.json:
            health_data = []
            for service in proj.services:
                health_data.append({
                    "service": service.name,
                    "status": service.status.value,
                    "health": service.health or "N/A",
                })
            formatter.print_json(health_data)
        else:
            console.print(f"\n[bold cyan]Health Status: {proj.name}[/bold cyan]\n")
            for service in proj.services:
                status_style = formatter._get_status_style(service.status)
                health = service.health or "[dim]No health check[/dim]"
                console.print(
                    f"  {service.name}: [{status_style}]{service.status.value}[/{status_style}] - {health}"
                )
    except DokmanError as e:
        handle_error(e)


@app.command("events")
def stream_events(
    project: Annotated[
        Optional[str],
        typer.Argument(help="Project name (optional if in project directory)"),
    ] = None,
) -> None:
    """Stream Docker events for a project in real-time.

    Shows container, network, and volume events related to the project.
    Press Ctrl+C to stop streaming.
    """
    try:
        pm = get_project_manager()
        docker = DockerClient()

        if project:
            proj = pm.get_project(project)
        else:
            proj = pm.get_project_by_path(Path.cwd())
            if proj:
                console.print(f"[dim]Auto-detected project: [cyan]{proj.name}[/cyan][/dim]")
        
        if proj is None:
            if project:
                raise ProjectNotFoundError(project)
            else:
                console.print("[red]Error:[/red] No project specified and none found in current directory.")
                raise typer.Exit(EXIT_GENERAL_ERROR)
        
        # We need the project name for filtering
        project_name = proj.name

        console.print(f"[dim]Streaming events for project '{project}'... (Ctrl+C to stop)[/dim]\n")

        # Filter events by project label
        filters = {
            "label": f"com.docker.compose.project={project_name}",
        }

        for event in docker.events(filters=filters):
            event_type = event.get("Type", "unknown")
            action = event.get("Action", "unknown")
            actor = event.get("Actor", {})
            attributes = actor.get("Attributes", {})
            
            service_name = attributes.get("com.docker.compose.service", "")
            container_name = attributes.get("name", actor.get("ID", "")[:12])
            
            timestamp = event.get("time", "")
            
            # Format the event output
            if service_name:
                console.print(
                    f"[dim]{timestamp}[/dim] [{event_type}] {action}: "
                    f"[cyan]{service_name}[/cyan] ({container_name})"
                )
            else:
                console.print(
                    f"[dim]{timestamp}[/dim] [{event_type}] {action}: {container_name}"
                )
    except DokmanError as e:
        handle_error(e)
    except KeyboardInterrupt:
        console.print("\n[dim]Event streaming stopped.[/dim]")


# -----------------------------------------------------------------------------
# Resource Management Commands
# -----------------------------------------------------------------------------


@app.command("images")
def list_images(
    project: Annotated[
        Optional[str],
        typer.Argument(help="Project name (optional, lists all if not provided)"),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """List Docker images used by projects.

    Shows images with their tags, sizes, and which services use them.
    If a project name is provided, only shows images for that project.
    """
    try:
        pm = get_project_manager()
        rm = get_resource_manager()

        proj = None
        if project:
            proj = pm.get_project(project)
            if proj is None:
                raise ProjectNotFoundError(project)
        else:
            # Try to infer, but don't fail if we can't, unless explicit filtering was intended
            # But the logic here says "optional, lists all if not provided"
            # So if not provided, we should probably check if we are in a project dir and list only that project?
            # Or stick to CLI help saying "lists all if not provided"?
            # The user request says "if I run dokman inside a project folder it should be not needed a project name again"
            # This implies if I run `dokman images` inside a project folder, I probably want images for THAT project.
            
            inferred_proj = pm.get_project_by_path(Path.cwd())
            if inferred_proj:
                proj = inferred_proj
                console.print(f"[dim]Auto-detected project: [cyan]{proj.name}[/cyan][/dim]")

        images = rm.list_images(proj)

        if not images:
            console.print("[dim]No images found.[/dim]")
            raise typer.Exit(EXIT_SUCCESS)

        formatter.print_images(images, as_json=(output_format == OutputFormat.json))
    except DokmanError as e:
        handle_error(e)


@app.command("volumes")
def list_volumes(
    project: Annotated[
        Optional[str],
        typer.Argument(help="Project name (optional, lists all if not provided)"),
    ] = None,
    prune: Annotated[
        bool,
        typer.Option("--prune", help="Remove unused volumes after confirmation"),
    ] = False,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """List Docker volumes used by projects.

    Shows volumes with their mount points, sizes, and service associations.
    Use --prune to remove unused volumes.
    """
    try:
        pm = get_project_manager()
        rm = get_resource_manager()

        proj = None
        if project:
            proj = pm.get_project(project)
            if proj is None:
                raise ProjectNotFoundError(project)

        if prune:
            if proj is None:
                console.print("[red]Error:[/red] --prune requires a project name")
                raise typer.Exit(EXIT_GENERAL_ERROR)

            # Confirm before pruning
            confirm = typer.confirm(
                f"Remove unused volumes for project '{project}'?"
            )
            if not confirm:
                console.print("[dim]Prune cancelled.[/dim]")
                raise typer.Exit(EXIT_SUCCESS)

            result = rm.prune_volumes(proj)
            if result["pruned"]:
                console.print(f"[green]✓[/green] Removed volumes: {', '.join(result['pruned'])}")
            else:
                console.print("[dim]No unused volumes to remove.[/dim]")

            if result["errors"]:
                for error in result["errors"]:
                    console.print(f"[red]Error:[/red] {error}")
        else:
            volumes = rm.list_volumes(proj)

            if not volumes:
                console.print("[dim]No volumes found.[/dim]")
                raise typer.Exit(EXIT_SUCCESS)

            formatter.print_volumes(volumes, as_json=(output_format == OutputFormat.json))
    except DokmanError as e:
        handle_error(e)


@app.command("networks")
def list_networks(
    project: Annotated[
        Optional[str],
        typer.Argument(help="Project name (optional, lists all if not provided)"),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """List Docker networks used by projects.

    Shows networks with their subnet, gateway, and connected containers.
    If a project name is provided, only shows networks for that project.
    """
    try:
        pm = get_project_manager()
        rm = get_resource_manager()

        proj = None
        if project:
            proj = pm.get_project(project)
            if proj is None:
                raise ProjectNotFoundError(project)

        networks = rm.list_networks(proj)

        if not networks:
            console.print("[dim]No networks found.[/dim]")
            raise typer.Exit(EXIT_SUCCESS)

        formatter.print_networks(networks, as_json=(output_format == OutputFormat.json))
    except DokmanError as e:
        handle_error(e)


@app.command("stats")
def show_stats(
    project: Annotated[str, typer.Argument(help="Project name")],
    no_stream: Annotated[
        bool,
        typer.Option("--no-stream", help="Display a single snapshot instead of streaming"),
    ] = False,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """Display resource usage statistics for project containers.

    Shows real-time CPU, memory, and network I/O for all services.
    Use --no-stream for a single snapshot.
    """
    try:
        pm = get_project_manager()
        rm = get_resource_manager()

        proj = pm.get_project(project)
        if proj is None:
            raise ProjectNotFoundError(project)

        if no_stream:
            # Single snapshot mode
            stats_list = list(rm.get_stats(proj, stream=False))
            if not stats_list:
                console.print("[dim]No running containers found.[/dim]")
                raise typer.Exit(EXIT_SUCCESS)

            # Flatten the list of lists
            all_stats = [stat for batch in stats_list for stat in batch]
            formatter.print_stats(all_stats, as_json=(output_format == OutputFormat.json))
        else:
            # Streaming mode
            console.print(f"[dim]Streaming stats for '{project}'... (Ctrl+C to stop)[/dim]\n")
            for stats_batch in rm.get_stats(proj, stream=True):
                if output_format == OutputFormat.json:
                    formatter.print_json(stats_batch)
                else:
                    # Clear and redraw for streaming
                    console.clear()
                    console.print(f"[bold cyan]Stats: {project}[/bold cyan]\n")
                    formatter.print_stats(stats_batch, as_json=False)
    except DokmanError as e:
        handle_error(e)
    except KeyboardInterrupt:
        console.print("\n[dim]Stats streaming stopped.[/dim]")


# -----------------------------------------------------------------------------
# Configuration Commands
# -----------------------------------------------------------------------------


@app.command("pull")
def pull_images(
    project: Annotated[str, typer.Argument(help="Project name")],
    service: Annotated[
        Optional[str],
        typer.Option("--service", "-s", help="Specific service to pull"),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """Pull latest images for a project.

    Downloads the latest images for all services or a specific service.
    Shows which images were updated and which were already up-to-date.
    """
    try:
        pm = get_project_manager()
        rm = get_resource_manager()

        proj = pm.get_project(project)
        if proj is None:
            raise ProjectNotFoundError(project)

        console.print(f"[dim]Pulling images for '{project}'...[/dim]")
        result = rm.pull_images(proj, service=service)

        if output_format == OutputFormat.json:
            formatter.print_json(result)
        else:
            if result.updated:
                console.print(f"[green]✓[/green] Updated: {', '.join(result.updated)}")
            if result.up_to_date:
                console.print(f"[dim]Already up-to-date: {', '.join(result.up_to_date)}[/dim]")
            if result.failed:
                console.print("[red]Failed:[/red]")
                for image, error in result.failed:
                    console.print(f"  • {image}: {error}")
                raise typer.Exit(EXIT_OPERATION_FAILED)
    except DokmanError as e:
        handle_error(e)


@app.command("build")
def build_images(
    project: Annotated[str, typer.Argument(help="Project name")],
    service: Annotated[
        Optional[str],
        typer.Option("--service", "-s", help="Specific service to build"),
    ] = None,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Build without using cache"),
    ] = False,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """Build images for services with build context.

    Builds images for all services with a build context defined,
    or a specific service if --service is provided.
    """
    try:
        pm = get_project_manager()
        rm = get_resource_manager()

        proj = pm.get_project(project)
        if proj is None:
            raise ProjectNotFoundError(project)

        console.print(f"[dim]Building images for '{project}'...[/dim]")
        result = rm.build_images(proj, service=service, no_cache=no_cache)

        if output_format == OutputFormat.json:
            formatter.print_json(result)
        else:
            if result.built:
                console.print(f"[green]✓[/green] Built: {', '.join(result.built)}")
            if result.skipped:
                console.print(f"[dim]Skipped (no build context): {', '.join(result.skipped)}[/dim]")
            if result.failed:
                console.print("[red]Failed:[/red]")
                for svc, error in result.failed:
                    console.print(f"  • {svc}: {error}")
                raise typer.Exit(EXIT_OPERATION_FAILED)
    except DokmanError as e:
        handle_error(e)


@app.command("config")
def show_config(
    project: Annotated[str, typer.Argument(help="Project name")],
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """Display the resolved Docker Compose configuration.

    Shows the fully resolved compose configuration with all environment
    variable substitutions applied.
    """
    try:
        pm = get_project_manager()
        compose = ComposeClient()

        proj = pm.get_project(project)
        if proj is None:
            raise ProjectNotFoundError(project)

        config = compose.config(proj.working_dir)

        if output_format == OutputFormat.json:
            formatter.print_json(config)
        else:
            # Pretty print the config as YAML-like output
            import json
            console.print(f"\n[bold cyan]Configuration: {project}[/bold cyan]\n")
            console.print(json.dumps(config, indent=2, default=str))
    except DokmanError as e:
        handle_error(e)


@app.command("env")
def show_env(
    project: Annotated[str, typer.Argument(help="Project name")],
    service: Annotated[
        Optional[str],
        typer.Option("--service", "-s", help="Specific service to show env for"),
    ] = None,
    show_secrets: Annotated[
        bool,
        typer.Option("--show-secrets", help="Show sensitive values unmasked"),
    ] = False,
    export: Annotated[
        bool,
        typer.Option("--export", help="Output in shell export format"),
    ] = False,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """Display environment variables for services.

    Shows environment variables defined for each service.
    Sensitive values are masked unless --show-secrets is provided.
    Use --export for shell-compatible export statements.
    """
    try:
        pm = get_project_manager()
        compose = ComposeClient()

        proj = pm.get_project(project)
        if proj is None:
            raise ProjectNotFoundError(project)

        config = compose.config(proj.working_dir)
        services_config = config.get("services", {})

        # Filter to specific service if requested
        if service:
            if service not in services_config:
                raise ServiceNotFoundError(project, service)
            services_config = {service: services_config[service]}

        for svc_name, svc_config in services_config.items():
            env_vars: dict[str, str] = {}

            # Get environment variables from config
            env_list = svc_config.get("environment", {})
            if isinstance(env_list, dict):
                env_vars = {k: str(v) if v is not None else "" for k, v in env_list.items()}
            elif isinstance(env_list, list):
                for item in env_list:
                    if "=" in item:
                        key, value = item.split("=", 1)
                        env_vars[key] = value
                    else:
                        env_vars[item] = ""

            if not env_vars:
                if not service:  # Only show message if listing all services
                    console.print(f"[dim]{svc_name}: No environment variables defined[/dim]")
                continue

            formatter.print_env(
                env_vars,
                svc_name,
                show_secrets=show_secrets,
                export=export,
                as_json=(output_format == OutputFormat.json),
            )
            console.print()  # Add spacing between services
    except DokmanError as e:
        handle_error(e)


# -----------------------------------------------------------------------------
# Backup and Restore Commands
# -----------------------------------------------------------------------------


@app.command("backup")
def backup_project(
    project: Annotated[
        Optional[str],
        typer.Argument(help="Project name (optional if in project directory)"),
    ] = None,
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for backup file"),
    ] = Path("./backups"),
    service: Annotated[
        Optional[str],
        typer.Option("--service", "-s", help="Specific service to backup volumes for"),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """Backup volumes for a Docker Compose project.

    Creates a tar.gz archive containing all volume data for the project.
    Use --service to backup only volumes used by a specific service.
    """
    try:
        pm = get_project_manager()
        rm = get_resource_manager()

        proj = resolve_project(pm, project)

        console.print(f"[dim]Backing up volumes for '{proj.name}'...[/dim]")
        result = rm.backup_volumes(proj, output, service)

        if output_format == OutputFormat.json:
            formatter.print_json(result.to_dict())
        else:
            if result.success:
                console.print(f"[green]✓[/green] Backup created: [cyan]{result.backup_path}[/cyan]")
                if result.volumes_backed_up:
                    console.print(f"  Volumes: {', '.join(result.volumes_backed_up)}")
            else:
                console.print("[red]✗[/red] Backup failed")
            
            if result.volumes_skipped:
                console.print(f"[yellow]Skipped:[/yellow] {', '.join(result.volumes_skipped)}")
            
            for error in result.errors:
                console.print(f"[red]Error:[/red] {error}")

        if not result.success:
            raise typer.Exit(EXIT_OPERATION_FAILED)
    except DokmanError as e:
        handle_error(e)


@app.command("restore")
def restore_project(
    project: Annotated[
        Optional[str],
        typer.Argument(help="Project name (optional if in project directory)"),
    ] = None,
    backup_from: Annotated[
        Optional[Path],
        typer.Option("--from", help="Path to backup tar.gz file"),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt"),
    ] = False,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """Restore volumes from a backup archive.

    Extracts volume data from a backup tar.gz file and restores it
    to the corresponding Docker volumes. This will OVERWRITE existing data.
    """
    try:
        pm = get_project_manager()
        rm = get_resource_manager()

        proj = resolve_project(pm, project)

        if backup_from is None:
            console.print("[red]Error:[/red] --from option is required. Specify the backup file path.")
            raise typer.Exit(EXIT_GENERAL_ERROR)

        if not backup_from.exists():
            console.print(f"[red]Error:[/red] Backup file not found: {backup_from}")
            raise typer.Exit(EXIT_GENERAL_ERROR)

        # Confirmation prompt
        if not yes:
            console.print(f"[yellow]Warning:[/yellow] This will OVERWRITE volume data for '{proj.name}'")
            confirm = typer.confirm("Are you sure you want to continue?")
            if not confirm:
                console.print("[dim]Restore cancelled.[/dim]")
                raise typer.Exit(EXIT_SUCCESS)

        console.print(f"[dim]Restoring volumes for '{proj.name}'...[/dim]")
        result = rm.restore_volumes(proj, backup_from)

        if output_format == OutputFormat.json:
            formatter.print_json(result.to_dict())
        else:
            if result.success:
                console.print("[green]✓[/green] Restore completed")
                if result.volumes_restored:
                    console.print(f"  Volumes: {', '.join(result.volumes_restored)}")
            else:
                console.print("[red]✗[/red] Restore failed")
            
            for error in result.errors:
                console.print(f"[red]Error:[/red] {error}")

        if not result.success:
            raise typer.Exit(EXIT_OPERATION_FAILED)
    except DokmanError as e:
        handle_error(e)


@app.command("backup-list")
def list_backups(
    project: Annotated[str, typer.Argument(help="Project name")],
    backup_dir: Annotated[
        Path,
        typer.Option("--dir", "-d", help="Directory containing backup files"),
    ] = Path("./backups"),
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """List available backups for a project.

    Scans the backup directory for tar.gz files matching the project name.
    """
    try:
        rm = get_resource_manager()
        backups = rm.list_backups(project, backup_dir)

        if not backups:
            console.print(f"[dim]No backups found for '{project}' in {backup_dir}[/dim]")
            raise typer.Exit(EXIT_SUCCESS)

        if output_format == OutputFormat.json:
            formatter.print_json([b.to_dict() for b in backups])
        else:
            console.print(f"\n[bold cyan]Backups for {project}[/bold cyan]\n")
            for backup in backups:
                size_mb = backup.size_bytes / (1024 * 1024)
                console.print(f"  [cyan]{backup.filename}[/cyan]")
                console.print(f"    Created: {backup.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
                console.print(f"    Size: {size_mb:.2f} MB")
                if backup.volumes:
                    console.print(f"    Volumes: {', '.join(backup.volumes)}")
                console.print()
    except DokmanError as e:
        handle_error(e)


# -----------------------------------------------------------------------------
# Configuration Diff Command
# -----------------------------------------------------------------------------


@app.command("diff")
def diff_project(
    project: Annotated[
        Optional[str],
        typer.Argument(help="Project name (optional if in project directory)"),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show all differences including environment variables"),
    ] = False,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """Compare compose configuration with running container state.

    Detects drift between the docker-compose.yml file and the actual
    running containers. Shows differences in images, ports, and environment.
    """
    from dokman.services.config_manager import ConfigManager
    
    try:
        pm = get_project_manager()
        docker = DockerClient()
        compose = ComposeClient()
        cm = ConfigManager(docker, compose)

        proj = resolve_project(pm, project)

        diff = cm.diff_project(proj)

        if output_format == OutputFormat.json:
            formatter.print_json(diff.to_dict())
        else:
            console.print(f"\n[bold cyan]Configuration Diff: {proj.name}[/bold cyan]\n")
            
            if not diff.has_changes:
                console.print("[green]✓[/green] No drift detected - configuration matches running state")
                raise typer.Exit(EXIT_SUCCESS)
            
            # Missing services (in config but not running)
            if diff.missing_services:
                console.print("[yellow]Services not running:[/yellow]")
                for svc in diff.missing_services:
                    console.print(f"  [red]- {svc}[/red]")
                console.print()
            
            # Extra services (running but not in config)
            if diff.extra_services:
                console.print("[yellow]Extra services (not in config):[/yellow]")
                for svc in diff.extra_services:
                    console.print(f"  [yellow]+ {svc}[/yellow]")
                console.print()
            
            # Modified services
            modified = [s for s in diff.services if s.status == "modified"]
            if modified:
                console.print("[yellow]Modified services:[/yellow]")
                for svc in modified:
                    console.print(f"\n  [cyan]{svc.service_name}[/cyan]:")
                    
                    if svc.image_diff:
                        expected, actual = svc.image_diff
                        console.print("    Image:")
                        console.print(f"      [red]- expected: {expected}[/red]")
                        console.print(f"      [green]+ actual:   {actual}[/green]")
                    
                    if svc.ports_diff:
                        expected, actual = svc.ports_diff
                        console.print("    Ports:")
                        console.print(f"      [red]- expected: {', '.join(expected) or '(none)'}[/red]")
                        console.print(f"      [green]+ actual:   {', '.join(actual) or '(none)'}[/green]")
                    
                    if verbose and svc.env_diff:
                        console.print("    Environment:")
                        for key, (expected, actual) in svc.env_diff.items():
                            exp_val = expected if expected else "(not set)"
                            act_val = actual if actual else "(not set)"
                            console.print(f"      {key}:")
                            console.print(f"        [red]- {exp_val}[/red]")
                            console.print(f"        [green]+ {act_val}[/green]")
                    elif svc.env_diff and not verbose:
                        console.print(f"    [dim]{len(svc.env_diff)} environment variable(s) differ (use -v to see)[/dim]")
                
                console.print()
            
            # Unchanged services count
            unchanged = [s for s in diff.services if s.status == "unchanged"]
            if unchanged:
                console.print(f"[dim]{len(unchanged)} service(s) unchanged[/dim]")

    except DokmanError as e:
        handle_error(e)


if __name__ == "__main__":
    app()
