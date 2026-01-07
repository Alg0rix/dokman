"""Main CLI application for Dokman.

This module serves as the entry point for the Dokman CLI, assembling
commands from various modules into a unified application.

Command modules:
- project: Project management (list, info, register, unregister, up)
- lifecycle: Service lifecycle (start, stop, restart, down, redeploy, scale)
- debug: Debugging/inspection (logs, exec, health, events)
- resources: Resource management (images, volumes, networks, stats)
- config: Configuration (pull, build, config, env)
- backup: Backup/restore (backup, restore, backup-list, diff)
- maintenance: System maintenance (prune-registry, doctor)
"""

import typer
from importlib.metadata import version as get_version

from dokman.cli.helpers import console

app = typer.Typer(
    name="dokman",
    help="Centralized Docker Compose deployment management",
    no_args_is_help=True,
)


@app.callback()
def main(ctx: typer.Context) -> None:
    """Dokman - Manage Docker Compose deployments from anywhere."""
    if ctx.resilient_parsing:
        return

    args = ctx.args
    if args:
        first_arg = args[0].lower()
        if first_arg in ("--help", "-h", "--version"):
            return

    try:
        from dokman.services.version_checker import VersionChecker

        checker = VersionChecker()
        update_info = checker.check_for_update()
        if update_info:
            console.print()
            console.print(
                f"[bold cyan]Update available:[/bold cyan] "
                f"dokman [green]{update_info.latest_version}[/green] "
                f"[dim](current: {update_info.current_version})[/dim]"
            )
            console.print(
                f"   Run [yellow]`{update_info.upgrade_command}`[/yellow] to update"
            )
            console.print()
    except Exception:
        pass


@app.command("version")
def print_version() -> None:
    """Print the version of dokman."""
    console.print(f"dokman [bold green]v{get_version('dokman')}[/bold green]")


def _register_commands() -> None:
    """Register all CLI commands. Called lazily to improve startup time."""
    from dokman.cli.commands import (
        backup,
        config,
        debug,
        lifecycle,
        maintenance,
        project,
        resources,
    )

    app.command("list")(project.list_projects)
    app.command("info")(project.info_project)
    app.command("register")(project.register_project)
    app.command("unregister")(project.unregister_project)
    app.command("up")(project.up_project)

    app.command("start")(lifecycle.start_services)
    app.command("stop")(lifecycle.stop_services)
    app.command("restart")(lifecycle.restart_services)
    app.command("down")(lifecycle.down_project)
    app.command("redeploy")(lifecycle.redeploy_project)
    app.command("scale")(lifecycle.scale_service)

    app.command("logs")(debug.show_logs)
    app.command("exec")(debug.exec_command)
    app.command("health")(debug.show_health)
    app.command("events")(debug.stream_events)

    app.command("images")(resources.list_images)
    app.command("volumes")(resources.list_volumes)
    app.command("networks")(resources.list_networks)
    app.command("stats")(resources.show_stats)

    app.command("pull")(config.pull_images)
    app.command("build")(config.build_images)
    app.command("config")(config.show_config)
    app.command("env")(config.show_env)

    app.command("backup")(backup.backup_project)
    app.command("restore")(backup.restore_project)
    app.command("backup-list")(backup.list_backups)
    app.command("diff")(backup.diff_project)

    app.command("prune-registry")(maintenance.prune_registry)
    app.command("doctor")(maintenance.doctor)


_register_commands()


if __name__ == "__main__":
    app()
