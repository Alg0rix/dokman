"""Configuration commands."""

import json
from typing import Annotated, Optional

import typer

from dokman.cli.helpers import (
    EXIT_OPERATION_FAILED,
    OutputFormat,
    console,
    formatter,
    get_project_manager,
    get_resource_manager,
    handle_error,
)
from dokman.clients.compose_client import ComposeClient
from dokman.exceptions import (
    DokmanError,
    ProjectNotFoundError,
    ServiceNotFoundError,
)


app = typer.Typer()


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
