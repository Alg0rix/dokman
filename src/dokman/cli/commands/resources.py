"""Resource management commands."""

from pathlib import Path
from typing import Annotated, Optional

import typer

from dokman.cli.helpers import (
    EXIT_GENERAL_ERROR,
    EXIT_SUCCESS,
    OutputFormat,
    console,
    formatter,
    get_project_manager,
    get_resource_manager,
    handle_error,
)
from dokman.exceptions import DokmanError, ProjectNotFoundError


app = typer.Typer()


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
            # Try to infer from current directory
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
