"""Service lifecycle commands."""

from typing import Annotated, Optional

import typer

from dokman.cli.helpers import (
    EXIT_OPERATION_FAILED,
    OutputFormat,
    formatter,
    get_project_manager,
    get_service_manager,
    handle_error,
    resolve_project,
)
from dokman.exceptions import DokmanError


app = typer.Typer()


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
        proj = resolve_project(pm, project)

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
        proj = resolve_project(pm, project)

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
        proj = resolve_project(pm, project)

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
        proj = resolve_project(pm, project)

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
        proj = resolve_project(pm, project)

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
        proj = resolve_project(pm, project)

        result = sm.scale(proj, service, replicas)
        formatter.print_operation_result(result, as_json=(output_format == OutputFormat.json))

        if not result.success:
            raise typer.Exit(EXIT_OPERATION_FAILED)
    except DokmanError as e:
        handle_error(e)
