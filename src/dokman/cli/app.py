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
"""

import typer

from dokman.cli.helpers import console

# Import command modules
from dokman.cli.commands import (
    backup,
    config,
    debug,
    lifecycle,
    project,
    resources,
)


# Main app
app = typer.Typer(
    name="dokman",
    help="Centralized Docker Compose deployment management",
    no_args_is_help=True,
)


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
                f"[bold cyan]Update available:[/bold cyan] "
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
# Register Project Management Commands
# -----------------------------------------------------------------------------

app.command("list")(project.list_projects)
app.command("info")(project.info_project)
app.command("register")(project.register_project)
app.command("unregister")(project.unregister_project)
app.command("up")(project.up_project)


# -----------------------------------------------------------------------------
# Register Service Lifecycle Commands
# -----------------------------------------------------------------------------

app.command("start")(lifecycle.start_services)
app.command("stop")(lifecycle.stop_services)
app.command("restart")(lifecycle.restart_services)
app.command("down")(lifecycle.down_project)
app.command("redeploy")(lifecycle.redeploy_project)
app.command("scale")(lifecycle.scale_service)


# -----------------------------------------------------------------------------
# Register Debugging and Inspection Commands
# -----------------------------------------------------------------------------

app.command("logs")(debug.show_logs)
app.command("exec")(debug.exec_command)
app.command("health")(debug.show_health)
app.command("events")(debug.stream_events)


# -----------------------------------------------------------------------------
# Register Resource Management Commands
# -----------------------------------------------------------------------------

app.command("images")(resources.list_images)
app.command("volumes")(resources.list_volumes)
app.command("networks")(resources.list_networks)
app.command("stats")(resources.show_stats)


# -----------------------------------------------------------------------------
# Register Configuration Commands
# -----------------------------------------------------------------------------

app.command("pull")(config.pull_images)
app.command("build")(config.build_images)
app.command("config")(config.show_config)
app.command("env")(config.show_env)


# -----------------------------------------------------------------------------
# Register Backup and Restore Commands
# -----------------------------------------------------------------------------

app.command("backup")(backup.backup_project)
app.command("restore")(backup.restore_project)
app.command("backup-list")(backup.list_backups)
app.command("diff")(backup.diff_project)


if __name__ == "__main__":
    app()
