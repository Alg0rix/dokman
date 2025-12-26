"""Output formatting utilities for Dokman CLI."""

import json
import re
from typing import Any

from rich.console import Console
from rich.table import Table

from dokman.models import (
    ContainerStats,
    ImageInfo,
    NetworkInfo,
    OperationResult,
    Project,
    ProjectHealth,
    RegisteredProject,
    Service,
    ServiceStatus,
    VolumeInfo,
)

# Patterns for sensitive environment variable keys
SENSITIVE_PATTERNS = [
    re.compile(r".*PASSWORD.*", re.IGNORECASE),
    re.compile(r".*SECRET.*", re.IGNORECASE),
    re.compile(r".*KEY.*", re.IGNORECASE),
    re.compile(r".*TOKEN.*", re.IGNORECASE),
    re.compile(r".*CREDENTIAL.*", re.IGNORECASE),
    re.compile(r".*API_KEY.*", re.IGNORECASE),
]

# Default mask for sensitive values
MASK = "****"


class OutputFormatter:
    """Handles output formatting for Dockman CLI."""

    def __init__(self, console: Console | None = None) -> None:
        """Initialize the formatter with a console instance."""
        self.console = console or Console()

    # -------------------------------------------------------------------------
    # Secret Masking
    # -------------------------------------------------------------------------

    def is_sensitive_key(self, key: str) -> bool:
        """Check if an environment variable key matches sensitive patterns."""
        return any(pattern.match(key) for pattern in SENSITIVE_PATTERNS)

    def mask_value(self, key: str, value: str, show_secrets: bool = False) -> str:
        """Mask a value if the key matches sensitive patterns."""
        if show_secrets:
            return value
        if self.is_sensitive_key(key):
            return MASK
        return value

    def mask_env_vars(
        self, env_vars: dict[str, str], show_secrets: bool = False
    ) -> dict[str, str]:
        """Mask sensitive values in a dictionary of environment variables."""
        return {k: self.mask_value(k, v, show_secrets) for k, v in env_vars.items()}

    # -------------------------------------------------------------------------
    # Shell Export Formatting
    # -------------------------------------------------------------------------

    def escape_shell_value(self, value: str) -> str:
        """Escape special characters for shell export."""
        # Escape backslashes first, then double quotes
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        # Escape dollar signs to prevent variable expansion
        escaped = escaped.replace("$", "\\$")
        # Escape backticks to prevent command substitution
        escaped = escaped.replace("`", "\\`")
        return escaped

    def format_export(self, env_vars: dict[str, str]) -> str:
        """Format environment variables as shell export statements."""
        lines = []
        for key, value in sorted(env_vars.items()):
            escaped_value = self.escape_shell_value(value)
            lines.append(f'export {key}="{escaped_value}"')
        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # JSON Output Formatting
    # -------------------------------------------------------------------------

    def to_json(self, data: Any, indent: int = 2) -> str:
        """Convert data to JSON string."""
        if hasattr(data, "to_dict"):
            data = data.to_dict()
        elif isinstance(data, list):
            data = [item.to_dict() if hasattr(item, "to_dict") else item for item in data]
        return json.dumps(data, indent=indent, default=str)

    def print_json(self, data: Any, indent: int = 2) -> None:
        """Print data as formatted JSON."""
        self.console.print(self.to_json(data, indent))

    # -------------------------------------------------------------------------
    # Table Formatting - Projects
    # -------------------------------------------------------------------------

    def format_projects_table(self, projects: list[Project]) -> Table:
        """Create a table for displaying projects."""
        table = Table(title="Docker Compose Projects")
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Status", style="bold")
        table.add_column("Services", justify="right")
        table.add_column("Compose File", style="dim")

        for project in projects:
            status_style = self.get_health_style(project.status)
            table.add_row(
                project.name,
                f"[{status_style}]{project.status.value}[/{status_style}]",
                str(len(project.services)),
                str(project.compose_file),
            )

        return table

    def print_projects(self, projects: list[Project], as_json: bool = False) -> None:
        """Print projects list."""
        if as_json:
            self.print_json(projects)
        else:
            table = self.format_projects_table(projects)
            self.console.print(table)

    # -------------------------------------------------------------------------
    # Table Formatting - Services
    # -------------------------------------------------------------------------

    def format_services_table(self, services: list[Service], project_name: str) -> Table:
        """Create a table for displaying services."""
        table = Table(title=f"Services in {project_name}")
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Status", style="bold")
        table.add_column("Container ID", style="dim")
        table.add_column("Image")
        table.add_column("Ports")
        table.add_column("Health")

        for service in services:
            status_style = self.get_status_style(service.status)
            container_id = service.container_id[:12] if service.container_id else "-"
            ports = ", ".join(service.ports) if service.ports else "-"
            health = service.health or "-"

            table.add_row(
                service.name,
                f"[{status_style}]{service.status.value}[/{status_style}]",
                container_id,
                service.image,
                ports,
                health,
            )

        return table

    def print_services(
        self, services: list[Service], project_name: str, as_json: bool = False
    ) -> None:
        """Print services list."""
        if as_json:
            self.print_json(services)
        else:
            table = self.format_services_table(services, project_name)
            self.console.print(table)

    # -------------------------------------------------------------------------
    # Table Formatting - Images
    # -------------------------------------------------------------------------

    def format_images_table(self, images: list[ImageInfo]) -> Table:
        """Create a table for displaying images."""
        table = Table(title="Docker Images")
        table.add_column("Repository", style="cyan")
        table.add_column("Tag", style="yellow")
        table.add_column("Image ID", style="dim")
        table.add_column("Size", justify="right")
        table.add_column("Used By")

        for image in images:
            image_id = image.id[:12] if len(image.id) > 12 else image.id
            size = self._format_bytes(image.size)
            used_by = ", ".join(image.used_by) if image.used_by else "-"

            table.add_row(
                image.repository,
                image.tag,
                image_id,
                size,
                used_by,
            )

        return table

    def print_images(self, images: list[ImageInfo], as_json: bool = False) -> None:
        """Print images list."""
        if as_json:
            self.print_json(images)
        else:
            table = self.format_images_table(images)
            self.console.print(table)

    # -------------------------------------------------------------------------
    # Table Formatting - Volumes
    # -------------------------------------------------------------------------

    def format_volumes_table(self, volumes: list[VolumeInfo]) -> Table:
        """Create a table for displaying volumes."""
        table = Table(title="Docker Volumes")
        table.add_column("Name", style="cyan")
        table.add_column("Driver")
        table.add_column("Mountpoint", style="dim")
        table.add_column("Size", justify="right")
        table.add_column("Used By")

        for volume in volumes:
            size = self._format_bytes(volume.size) if volume.size else "-"
            used_by = ", ".join(volume.used_by) if volume.used_by else "-"

            table.add_row(
                volume.name,
                volume.driver,
                volume.mountpoint,
                size,
                used_by,
            )

        return table

    def print_volumes(self, volumes: list[VolumeInfo], as_json: bool = False) -> None:
        """Print volumes list."""
        if as_json:
            self.print_json(volumes)
        else:
            table = self.format_volumes_table(volumes)
            self.console.print(table)

    # -------------------------------------------------------------------------
    # Table Formatting - Networks
    # -------------------------------------------------------------------------

    def format_networks_table(self, networks: list[NetworkInfo]) -> Table:
        """Create a table for displaying networks."""
        table = Table(title="Docker Networks")
        table.add_column("Name", style="cyan")
        table.add_column("Driver")
        table.add_column("Subnet")
        table.add_column("Gateway")
        table.add_column("Containers")

        for network in networks:
            subnet = network.subnet or "-"
            gateway = network.gateway or "-"
            containers = ", ".join(network.containers) if network.containers else "-"

            table.add_row(
                network.name,
                network.driver,
                subnet,
                gateway,
                containers,
            )

        return table

    def print_networks(self, networks: list[NetworkInfo], as_json: bool = False) -> None:
        """Print networks list."""
        if as_json:
            self.print_json(networks)
        else:
            table = self.format_networks_table(networks)
            self.console.print(table)

    # -------------------------------------------------------------------------
    # Table Formatting - Container Stats
    # -------------------------------------------------------------------------

    def format_stats_table(self, stats: list[ContainerStats]) -> Table:
        """Create a table for displaying container statistics."""
        table = Table(title="Container Statistics")
        table.add_column("Container", style="cyan")
        table.add_column("CPU %", justify="right")
        table.add_column("Memory Usage", justify="right")
        table.add_column("Memory Limit", justify="right")
        table.add_column("Memory %", justify="right")
        table.add_column("Net I/O", justify="right")

        for stat in stats:
            net_io = f"{self._format_bytes(stat.network_rx)} / {self._format_bytes(stat.network_tx)}"

            table.add_row(
                stat.name,
                f"{stat.cpu_percent:.2f}%",
                self._format_bytes(stat.memory_usage),
                self._format_bytes(stat.memory_limit),
                f"{stat.memory_percent:.2f}%",
                net_io,
            )

        return table

    def print_stats(self, stats: list[ContainerStats], as_json: bool = False) -> None:
        """Print container statistics."""
        if as_json:
            self.print_json(stats)
        else:
            table = self.format_stats_table(stats)
            self.console.print(table)

    # -------------------------------------------------------------------------
    # Table Formatting - Environment Variables
    # -------------------------------------------------------------------------

    def format_env_table(
        self, env_vars: dict[str, str], service_name: str, show_secrets: bool = False
    ) -> Table:
        """Create a table for displaying environment variables."""
        table = Table(title=f"Environment Variables - {service_name}")
        table.add_column("Key", style="cyan")
        table.add_column("Value")

        masked_vars = self.mask_env_vars(env_vars, show_secrets)
        for key, value in sorted(masked_vars.items()):
            style = "dim" if value == MASK else ""
            table.add_row(key, f"[{style}]{value}[/{style}]" if style else value)

        return table

    def print_env(
        self,
        env_vars: dict[str, str],
        service_name: str,
        show_secrets: bool = False,
        export: bool = False,
        as_json: bool = False,
    ) -> None:
        """Print environment variables."""
        masked_vars = self.mask_env_vars(env_vars, show_secrets)

        if export:
            self.console.print(self.format_export(masked_vars))
        elif as_json:
            self.print_json(masked_vars)
        else:
            table = self.format_env_table(env_vars, service_name, show_secrets)
            self.console.print(table)

    # -------------------------------------------------------------------------
    # Table Formatting - Registered Projects
    # -------------------------------------------------------------------------

    def format_registered_projects_table(
        self, projects: list[RegisteredProject]
    ) -> Table:
        """Create a table for displaying registered projects."""
        table = Table(title="Registered Projects")
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Compose File", style="dim")
        table.add_column("Registered At")
        table.add_column("Last Accessed")

        for project in projects:
            registered = project.registered_at.strftime("%Y-%m-%d %H:%M")
            last_accessed = (
                project.last_accessed.strftime("%Y-%m-%d %H:%M")
                if project.last_accessed
                else "-"
            )

            table.add_row(
                project.name,
                str(project.compose_file),
                registered,
                last_accessed,
            )

        return table

    def print_registered_projects(
        self, projects: list[RegisteredProject], as_json: bool = False
    ) -> None:
        """Print registered projects list."""
        if as_json:
            self.print_json(projects)
        else:
            table = self.format_registered_projects_table(projects)
            self.console.print(table)

    # -------------------------------------------------------------------------
    # Operation Results
    # -------------------------------------------------------------------------

    def print_operation_result(
        self, result: OperationResult, as_json: bool = False
    ) -> None:
        """Print operation result."""
        if as_json:
            self.print_json(result)
        else:
            if result.success:
                self.console.print(f"[green]✓[/green] {result.message}")
            else:
                self.console.print(f"[red]✗[/red] {result.message}")

            if result.affected_services:
                self.console.print(
                    f"  Affected services: {', '.join(result.affected_services)}"
                )

            if result.errors:
                self.console.print("[red]Errors:[/red]")
                for error in result.errors:
                    self.console.print(f"  • {error}")

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def get_health_style(self, health: ProjectHealth) -> str:
        """Get the style for a project health status."""
        styles = {
            ProjectHealth.HEALTHY: "green",
            ProjectHealth.UNHEALTHY: "red",
            ProjectHealth.PARTIAL: "yellow",
            ProjectHealth.UNKNOWN: "dim",
        }
        return styles.get(health, "dim")

    def get_status_style(self, status: ServiceStatus) -> str:
        """Get the style for a service status."""
        styles = {
            ServiceStatus.RUNNING: "green",
            ServiceStatus.STOPPED: "red",
            ServiceStatus.RESTARTING: "yellow",
            ServiceStatus.PAUSED: "yellow",
            ServiceStatus.EXITED: "red",
            ServiceStatus.DEAD: "red bold",
        }
        return styles.get(status, "dim")

    def _format_bytes(self, size: int) -> str:
        """Format bytes into human-readable string."""
        size_float = float(size)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_float < 1024:
                return f"{size_float:.1f} {unit}"
            size_float /= 1024
        return f"{size_float:.1f} PB"
