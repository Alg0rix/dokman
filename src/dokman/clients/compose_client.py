"""Docker Compose CLI client wrapper for Dokman."""

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from dokman.exceptions import ComposeFileNotFoundError, DokmanError
from dokman.models.results import ComposeResult


class ComposeClient:
    """Wrapper around Docker Compose CLI commands.

    Executes docker compose commands via subprocess and returns
    structured results.
    Supports singleton pattern for connection pooling.
    """

    _shared_instance: "ComposeClient | None" = None

    def __init__(self) -> None:
        """Initialize Compose client."""
        self._compose_cmd = ["docker", "compose"]

    @classmethod
    def get_shared(cls) -> "ComposeClient":
        """Get or create a shared ComposeClient instance.

        Returns:
            Singleton ComposeClient instance.
        """
        if cls._shared_instance is None:
            cls._shared_instance = cls()
        return cls._shared_instance

    @classmethod
    def reset_shared(cls) -> None:
        """Reset the shared instance. Useful for testing."""
        cls._shared_instance = None

    def _run_command(
        self,
        project_dir: Path,
        args: list[str],
        capture_output: bool = True,
        timeout: int | None = None,
    ) -> ComposeResult:
        """Execute a docker compose command.

        Args:
            project_dir: Directory containing the compose file
            args: Command arguments (e.g., ["up", "-d"])
            capture_output: Whether to capture stdout/stderr
            timeout: Command timeout in seconds

        Returns:
            ComposeResult with command output
        """
        if not project_dir.exists():
            raise ComposeFileNotFoundError(project_dir)

        cmd = self._compose_cmd + args

        try:
            result = subprocess.run(
                cmd,
                cwd=project_dir,
                capture_output=capture_output,
                text=True,
                timeout=timeout,
            )
            return ComposeResult(
                success=result.returncode == 0,
                output=result.stdout or "",
                error=result.stderr if result.returncode != 0 else None,
                return_code=result.returncode,
            )
        except subprocess.TimeoutExpired as e:
            raise DokmanError(
                f"Command timed out after {timeout}s: {' '.join(cmd)}"
            ) from e
        except FileNotFoundError as e:
            raise DokmanError("Docker Compose not found. Is Docker installed?") from e
        except subprocess.SubprocessError as e:
            raise DokmanError(f"Failed to execute compose command: {e}") from e

    def up(
        self,
        project_dir: Path,
        services: list[str] | None = None,
        detach: bool = True,
    ) -> ComposeResult:
        """Start services defined in compose file.

        Args:
            project_dir: Directory containing the compose file
            services: Specific services to start (None for all)
            detach: Run in detached mode

        Returns:
            ComposeResult with operation output
        """
        args = ["up"]
        if detach:
            args.append("-d")
        if services:
            args.extend(services)
        return self._run_command(project_dir, args)

    def down(
        self,
        project_dir: Path,
        volumes: bool = False,
    ) -> ComposeResult:
        """Stop and remove containers, networks.

        Args:
            project_dir: Directory containing the compose file
            volumes: Also remove volumes

        Returns:
            ComposeResult with operation output
        """
        args = ["down"]
        if volumes:
            args.append("-v")
        return self._run_command(project_dir, args)

    def start(
        self,
        project_dir: Path,
        services: list[str] | None = None,
    ) -> ComposeResult:
        """Start existing containers.

        Args:
            project_dir: Directory containing the compose file
            services: Specific services to start (None for all)

        Returns:
            ComposeResult with operation output
        """
        args = ["start"]
        if services:
            args.extend(services)
        return self._run_command(project_dir, args)

    def stop(
        self,
        project_dir: Path,
        services: list[str] | None = None,
    ) -> ComposeResult:
        """Stop running containers.

        Args:
            project_dir: Directory containing the compose file
            services: Specific services to stop (None for all)

        Returns:
            ComposeResult with operation output
        """
        args = ["stop"]
        if services:
            args.extend(services)
        return self._run_command(project_dir, args)

    def restart(
        self,
        project_dir: Path,
        services: list[str] | None = None,
    ) -> ComposeResult:
        """Restart containers.

        Args:
            project_dir: Directory containing the compose file
            services: Specific services to restart (None for all)

        Returns:
            ComposeResult with operation output
        """
        args = ["restart"]
        if services:
            args.extend(services)
        return self._run_command(project_dir, args)

    def pull(
        self,
        project_dir: Path,
        services: list[str] | None = None,
    ) -> ComposeResult:
        """Pull service images.

        Args:
            project_dir: Directory containing the compose file
            services: Specific services to pull (None for all)

        Returns:
            ComposeResult with operation output
        """
        args = ["pull"]
        if services:
            args.extend(services)
        return self._run_command(project_dir, args)

    def build(
        self,
        project_dir: Path,
        services: list[str] | None = None,
        no_cache: bool = False,
    ) -> ComposeResult:
        """Build service images.

        Args:
            project_dir: Directory containing the compose file
            services: Specific services to build (None for all)
            no_cache: Build without using cache

        Returns:
            ComposeResult with operation output
        """
        args = ["build"]
        if no_cache:
            args.append("--no-cache")
        if services:
            args.extend(services)
        return self._run_command(project_dir, args)

    def logs(
        self,
        project_dir: Path,
        services: list[str] | None = None,
        follow: bool = False,
        tail: int | None = None,
    ) -> Iterator[str]:
        """Stream logs from services.

        Args:
            project_dir: Directory containing the compose file
            services: Specific services to get logs from (None for all)
            follow: Follow log output
            tail: Number of lines to show from end of logs

        Yields:
            Log lines
        """
        if not project_dir.exists():
            raise ComposeFileNotFoundError(project_dir)

        args = ["logs"]
        if follow:
            args.append("-f")
        if tail is not None:
            args.extend(["--tail", str(tail)])
        if services:
            args.extend(services)

        cmd = self._compose_cmd + args

        try:
            process = subprocess.Popen(
                cmd,
                cwd=project_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            if process.stdout:
                for line in process.stdout:
                    yield line.rstrip("\n")

            process.wait()
        except FileNotFoundError as e:
            raise DokmanError("Docker Compose not found. Is Docker installed?") from e
        except subprocess.SubprocessError as e:
            raise DokmanError(f"Failed to get logs: {e}") from e

    def exec(
        self,
        project_dir: Path,
        service: str,
        command: list[str],
        interactive: bool = False,
    ) -> int:
        """Execute a command in a running container.

        Args:
            project_dir: Directory containing the compose file
            service: Service name to execute command in
            command: Command and arguments to execute
            interactive: Run in interactive mode with TTY

        Returns:
            Exit code of the command
        """
        if not project_dir.exists():
            raise ComposeFileNotFoundError(project_dir)

        args = ["exec"]
        if interactive:
            args.append("-i")
        else:
            args.append("-T")
        args.append(service)
        args.extend(command)

        cmd = self._compose_cmd + args

        try:
            result = subprocess.run(
                cmd,
                cwd=project_dir,
            )
            return result.returncode
        except FileNotFoundError as e:
            raise DokmanError("Docker Compose not found. Is Docker installed?") from e
        except subprocess.SubprocessError as e:
            raise DokmanError(f"Failed to execute command: {e}") from e

    def config(self, project_dir: Path) -> dict[str, Any]:
        """Get the resolved compose configuration.

        Args:
            project_dir: Directory containing the compose file

        Returns:
            Dictionary with resolved compose configuration
        """
        result = self._run_command(project_dir, ["config", "--format", "json"])

        if not result.success:
            raise DokmanError(f"Failed to get config: {result.error}")

        try:
            return json.loads(result.output)
        except json.JSONDecodeError as e:
            raise DokmanError(f"Failed to parse compose config: {e}") from e

    def ps(self, project_dir: Path) -> list[dict[str, Any]]:
        """List containers for the project.

        Args:
            project_dir: Directory containing the compose file

        Returns:
            List of container information dictionaries
        """
        result = self._run_command(project_dir, ["ps", "--format", "json"])

        if not result.success:
            raise DokmanError(f"Failed to list containers: {result.error}")

        if not result.output.strip():
            return []

        try:
            # docker compose ps --format json outputs one JSON object per line
            containers = []
            for line in result.output.strip().split("\n"):
                if line.strip():
                    containers.append(json.loads(line))
            return containers
        except json.JSONDecodeError as e:
            raise DokmanError(f"Failed to parse container list: {e}") from e

    def scale(
        self,
        project_dir: Path,
        service: str,
        replicas: int,
    ) -> ComposeResult:
        """Scale a service to specified number of replicas.

        Args:
            project_dir: Directory containing the compose file
            service: Service name to scale
            replicas: Number of replicas

        Returns:
            ComposeResult with operation output
        """
        args = ["up", "-d", "--scale", f"{service}={replicas}", service]
        return self._run_command(project_dir, args)
