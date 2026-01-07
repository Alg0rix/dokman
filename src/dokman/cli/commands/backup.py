"""Backup and restore commands."""

from pathlib import Path
from typing import Annotated, Optional

import typer

from dokman.cli.helpers import (
    EXIT_GENERAL_ERROR,
    EXIT_OPERATION_FAILED,
    EXIT_SUCCESS,
    OutputFormat,
    console,
    formatter,
    get_project_manager,
    get_resource_manager,
    handle_error,
    resolve_project,
)
from dokman.exceptions import DokmanError


app = typer.Typer()


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


@app.command("diff")
def diff_project(
    project: Annotated[
        Optional[str],
        typer.Argument(help="Project name (optional if in project directory)"),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show all differences including environment variables, volumes, labels, and limits"),
    ] = False,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """Compare compose configuration with running container state.

    Detects drift between the docker-compose.yml file and the actual
    running containers. Shows differences in images, ports, environment,
    volumes, labels, and resource limits.
    """
    from dokman.cli.helpers import get_config_manager

    try:
        pm = get_project_manager()
        cm = get_config_manager()

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

                    if svc.volumes_diff:
                        expected, actual = svc.volumes_diff
                        console.print("    Volumes:")
                        console.print(f"      [red]- expected: {', '.join(expected) or '(none)'}[/red]")
                        console.print(f"      [green]+ actual:   {', '.join(actual) or '(none)'}[/green]")

                    if svc.limits_diff and svc.limits_diff.has_changes():
                        console.print("    Resource Limits:")
                        limits = svc.limits_diff
                        if limits.memory:
                            console.print(f"      Memory: [red]- {limits.memory[0] or '(not set)'}[/red] [green]+ {limits.memory[1] or '(not set)'}[/green]")
                        if limits.memory_swap:
                            console.print(f"      Memory Swap: [red]- {limits.memory_swap[0] or '(not set)'}[/red] [green]+ {limits.memory_swap[1] or '(not set)'}[/green]")
                        if limits.cpu_period:
                            console.print(f"      CPU Period: [red]- {limits.cpu_period[0] or '(not set)'}[/red] [green]+ {limits.cpu_period[1] or '(not set)'}[/green]")
                        if limits.cpu_quota:
                            console.print(f"      CPU Quota: [red]- {limits.cpu_quota[0] or '(not set)'}[/red] [green]+ {limits.cpu_quota[1] or '(not set)'}[/green]")
                        if limits.cpu_shares:
                            console.print(f"      CPU Shares: [red]- {limits.cpu_shares[0] or '(not set)'}[/red] [green]+ {limits.cpu_shares[1] or '(not set)'}[/green]")

                    if svc.labels_diff:
                        if verbose:
                            console.print("    Labels:")
                            for key, (expected, actual) in svc.labels_diff.items():
                                exp_val = expected if expected else "(not set)"
                                act_val = actual if actual else "(not set)"
                                console.print(f"      {key}:")
                                console.print(f"        [red]- {exp_val}[/red]")
                                console.print(f"        [green]+ {act_val}[/green]")
                        else:
                            console.print(f"    [dim]{len(svc.labels_diff)} label(s) differ (use -v to see)[/dim]")

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
