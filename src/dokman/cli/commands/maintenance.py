"""Maintenance commands for Dokman - prune-registry and doctor."""

from typing import Annotated

import typer

from dokman.cli.helpers import (
    EXIT_SUCCESS,
    OutputFormat,
    console,
    formatter,
    get_project_manager,
    handle_error,
)
from dokman.exceptions import DokmanError


app = typer.Typer(
    name="maintenance",
    help="Maintenance commands for registry cleanup and system diagnostics",
    no_args_is_help=True,
)


@app.command("prune-registry")
def prune_registry(
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt"),
    ] = False,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """Remove stale registry entries (projects with missing compose files).

    Scans the registry for projects whose compose files no longer exist
    and removes them from tracking.
    """
    try:
        pm = get_project_manager()

        # Get stale projects
        stale = pm.get_stale_projects()

        if not stale:
            console.print("[green]✓[/green] No stale registry entries found")
            raise typer.Exit(EXIT_SUCCESS)

        # Show what will be removed
        console.print("\n[bold]Stale Registry Entries[/bold]\n")

        for reg_project, issues in stale:
            issue_str = ", ".join(
                "missing compose file"
                if i == "missing_compose_file"
                else "has orphan containers"
                for i in issues
            )
            console.print(f"  [yellow]{reg_project.name}[/yellow]")
            console.print(f"    Compose file: {reg_project.compose_file}")
            console.print(f"    Issues: {issue_str}")
            console.print()

        if not yes:
            confirm = typer.confirm(
                f"Remove {len(stale)} stale entry(ies) from registry?"
            )
            if not confirm:
                console.print("[dim]Cancelled.[/dim]")
                raise typer.Exit(EXIT_SUCCESS)

        # Prune stale entries
        result = pm.prune_stale_entries(force=True)

        if output_format == OutputFormat.json:
            formatter.print_json(result)
        else:
            if result["removed"]:
                console.print(
                    f"\n[green]✓[/green] Removed {len(result['removed'])} entry(ies):"
                )
                for name in result["removed"]:
                    console.print(f"  - {name}")

            if result["skipped"]:
                console.print(f"\n[yellow]Skipped {len(result['skipped'])}:[/yellow]")
                for name in result["skipped"]:
                    console.print(f"  - {name}")

    except DokmanError as e:
        handle_error(e)


@app.command("doctor")
def doctor(
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Automatically fix issues where possible"),
    ] = False,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.table,
) -> None:
    """Run system diagnostics for Dokman and Docker.

    Checks:
    - Docker daemon connectivity
    - Registry integrity
    - Stale registry entries
    - Orphan containers
    - Orphan volumes
    """
    from dokman.clients.docker_client import DockerClient
    from dokman.storage.registry import ProjectRegistry

    issues: list[dict] = []
    checks: list[dict] = []

    # Check 1: Docker daemon connectivity
    try:
        docker = DockerClient.get_shared()
        docker.ping()
        checks.append(
            {
                "check": "Docker Daemon",
                "status": "passed",
                "message": "Docker daemon is accessible",
            }
        )
    except DokmanError as e:
        checks.append(
            {
                "check": "Docker Daemon",
                "status": "failed",
                "message": str(e),
            }
        )
        issues.append(
            {
                "check": "Docker Daemon",
                "status": "failed",
                "message": str(e),
            }
        )

    # Check 2: Registry file
    try:
        registry = ProjectRegistry()
        projects = registry.load()
        checks.append(
            {
                "check": "Registry File",
                "status": "passed",
                "message": f"Registry loaded ({len(projects)} projects)",
            }
        )
    except DokmanError as e:
        checks.append(
            {
                "check": "Registry File",
                "status": "failed",
                "message": str(e),
            }
        )
        issues.append(
            {
                "check": "Registry File",
                "status": "failed",
                "message": str(e),
            }
        )

    # Check 3: Stale registry entries
    try:
        pm = get_project_manager()
        stale = pm.get_stale_projects()

        if stale:
            stale_projects = [p.name for p, _ in stale]
            checks.append(
                {
                    "check": "Stale Registry Entries",
                    "status": "warning",
                    "message": f"{len(stale)} stale entry(ies): {', '.join(stale_projects)}",
                }
            )
            for reg_project, issue_types in stale:
                for issue_type in issue_types:
                    issues.append(
                        {
                            "check": f"Stale Entry: {reg_project.name}",
                            "status": "warning",
                            "message": issue_type.replace("_", " "),
                            "project": reg_project.name,
                            "compose_file": str(reg_project.compose_file),
                        }
                    )
        else:
            checks.append(
                {
                    "check": "Stale Registry Entries",
                    "status": "passed",
                    "message": "No stale entries found",
                }
            )
    except DokmanError as e:
        checks.append(
            {
                "check": "Stale Registry Entries",
                "status": "error",
                "message": str(e),
            }
        )

    # Check 4: Orphan containers
    try:
        pm = get_project_manager()
        orphans = pm.find_orphan_containers()

        if orphans:
            project_names = set(o["project_name"] for o in orphans)
            checks.append(
                {
                    "check": "Orphan Containers",
                    "status": "warning",
                    "message": f"{len(orphans)} orphan container(s) for projects: {', '.join(project_names)}",
                }
            )
            for orphan in orphans:
                issues.append(
                    {
                        "check": f"Orphan Container: {orphan['container_name']}",
                        "status": "warning",
                        "message": f"Project: {orphan['project_name']}, Service: {orphan['service_name']}",
                        "container_id": orphan["container_id"],
                        "project": orphan["project_name"],
                        "service": orphan["service_name"],
                    }
                )
        else:
            checks.append(
                {
                    "check": "Orphan Containers",
                    "status": "passed",
                    "message": "No orphan containers found",
                }
            )
    except DokmanError as e:
        checks.append(
            {
                "check": "Orphan Containers",
                "status": "error",
                "message": str(e),
            }
        )

    # Check 5: Orphan volumes (volumes not used by any registered project)
    try:
        docker = DockerClient.get_shared()
        all_containers = docker.list_containers(
            filters={"label": "com.docker.compose.project"}
        )

        # Get volumes used by registered projects
        pm = get_project_manager()
        registered_projects = pm.get_registered_names()

        used_volumes: set[str] = set()
        for container in all_containers:
            labels = container.labels or {}
            project_name = labels.get("com.docker.compose.project", "")

            if project_name not in registered_projects:
                continue

            attrs = getattr(container, "attrs", {}) or {}
            mounts = attrs.get("Mounts", [])

            for mount in mounts:
                if mount.get("Type") == "volume":
                    used_volumes.add(mount.get("Name", ""))

        # List all volumes and check for orphans
        all_volumes = docker.list_volumes()
        volume_names = {v.name for v in all_volumes}
        orphan_volumes = volume_names - used_volumes

        # Filter out common internal volumes
        internal_prefixes = ("dokman_", "dokman-")
        orphan_volumes = {
            v for v in orphan_volumes if not v.startswith(internal_prefixes)
        }

        if orphan_volumes:
            checks.append(
                {
                    "check": "Orphan Volumes",
                    "status": "warning",
                    "message": f"{len(orphan_volumes)} unused volume(s): {', '.join(list(orphan_volumes)[:5])}",
                }
            )
            for vol_name in orphan_volumes:
                issues.append(
                    {
                        "check": f"Orphan Volume: {vol_name}",
                        "status": "warning",
                        "message": "Volume not used by any registered project",
                        "volume": vol_name,
                    }
                )
        else:
            checks.append(
                {
                    "check": "Orphan Volumes",
                    "status": "passed",
                    "message": "No orphan volumes found",
                }
            )
    except DokmanError as e:
        checks.append(
            {
                "check": "Orphan Volumes",
                "status": "error",
                "message": str(e),
            }
        )

    # Output results
    if output_format == OutputFormat.json:
        formatter.print_json(
            {
                "checks": checks,
                "issues": issues,
                "summary": {
                    "total_checks": len(checks),
                    "passed": sum(1 for c in checks if c["status"] == "passed"),
                    "warnings": sum(1 for c in checks if c["status"] == "warning"),
                    "failed": sum(
                        1 for c in checks if c["status"] in ("failed", "error")
                    ),
                },
            }
        )
    else:
        console.print("\n[bold cyan]Dokman Doctor[/bold cyan]\n")

        # Summary
        passed = sum(1 for c in checks if c["status"] == "passed")
        warnings = sum(1 for c in checks if c["status"] == "warning")
        failed = sum(1 for c in checks if c["status"] in ("failed", "error"))

        console.print(
            f"Checks: [green]{passed}[/green] passed, [yellow]{warnings}[/yellow] warnings, [red]{failed}[/red] failed\n"
        )

        # Detailed checks
        console.print("[bold]System Checks[/bold]\n")
        for check in checks:
            status_icon = {
                "passed": "[green]✓[/green]",
                "warning": "[yellow]⚠[/yellow]",
                "failed": "[red]✗[/red]",
                "error": "[red]✗[/red]",
            }.get(check["status"], "[?][?]")

            console.print(f"  {status_icon} [bold]{check['check']}[/bold]")
            console.print(f"       {check['message']}\n")

        # Issues section
        if issues:
            console.print("\n[bold yellow]Issues Found[/bold yellow]\n")

            # Group by check type
            issue_types: dict[str, list[dict]] = {}
            for issue in issues:
                check = issue["check"]
                if check not in issue_types:
                    issue_types[check] = []
                issue_types[check].append(issue)

            for check, type_issues in issue_types.items():
                console.print(f"  [cyan]{check}[/cyan]:")
                for issue in type_issues:
                    console.print(f"    - {issue['message']}")
                console.print()

            # Auto-fix suggestions
            if fix:
                console.print("\n[bold]Auto-fixing issues...[/bold]\n")

                # Fix stale entries
                stale_to_fix = [i for i in issues if "Stale Entry" in i["check"]]
                if stale_to_fix:
                    result = pm.prune_stale_entries(force=True)
                    console.print(
                        f"  [green]✓[/green] Removed {len(result['removed'])} stale entry(ies)"
                    )
                    issues = [i for i in issues if "Stale Entry" not in i["check"]]

                # Re-check if issues remain
                remaining = sum(1 for i in issues if "Orphan" in i["check"])
                if remaining:
                    console.print(
                        f"\n  [yellow]Note:[/yellow] {remaining} issue(s) require manual intervention"
                    )
                    console.print(
                        "  Run 'dokman prune-registry' to clean stale entries"
                    )
                    console.print(
                        "  Run 'docker compose down --remove-orphans' in project directories for orphan containers"
                    )

        # Recommendations
        if issues:
            console.print("\n[bold]Recommendations[/bold]\n")
            has_stale = any("Stale" in i["check"] for i in issues)
            has_orphan_containers = any(
                "Orphan Container" in i["check"] for i in issues
            )
            has_orphan_volumes = any("Orphan Volume" in i["check"] for i in issues)

            if has_stale:
                console.print(
                    "  Run [cyan]`dokman prune-registry`[/cyan] to clean stale entries"
                )
            if has_orphan_containers:
                console.print(
                    "  Run [cyan]`dokman down --remove-orphans`[/cyan] in project directories"
                )
            if has_orphan_volumes:
                console.print(
                    "  Run [cyan]`docker volume prune`[/cyan] to remove unused volumes (careful!)"
                )
