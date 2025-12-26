"""Debugging and inspection commands."""

from pathlib import Path
from typing import Annotated, Optional

import typer

from dokman.cli.helpers import (
    EXIT_GENERAL_ERROR,
    OutputFormat,
    console,
    formatter,
    get_project_manager,
    get_service_manager,
    handle_error,
)
from dokman.clients.docker_client import DockerClient
from dokman.exceptions import DokmanError, ProjectNotFoundError


app = typer.Typer()


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
                status_style = formatter.get_status_style(service.status)
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

        console.print(f"[dim]Streaming events for project '{project_name}'... (Ctrl+C to stop)[/dim]\n")

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
