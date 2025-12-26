"""Project management commands."""

from pathlib import Path
from typing import Annotated, Optional

import typer

from dokman.cli.helpers import (
    EXIT_COMPOSE_FILE_ERROR,
    EXIT_GENERAL_ERROR,
    EXIT_OPERATION_FAILED,
    EXIT_SUCCESS,
    OutputFormat,
    console,
    formatter,
    get_project_manager,
    handle_error,
)
from dokman.clients.compose_client import ComposeClient
from dokman.exceptions import DokmanError, ProjectNotFoundError


app = typer.Typer()


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
            console.print(f"  Status: [{formatter.get_health_style(proj.status)}]{proj.status.value}[/{formatter.get_health_style(proj.status)}]")
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
