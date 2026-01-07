"""Docker SDK client wrapper for Dokman."""

from collections.abc import Iterator
from typing import Any

import docker
from docker.errors import APIError, DockerException, NotFound
from docker.models.containers import Container
from docker.models.images import Image
from docker.models.networks import Network
from docker.models.volumes import Volume

from dokman.exceptions import DokmanError, DockerConnectionError


class DockerClient:
    """Wrapper around Docker SDK for Python.

    Provides a simplified interface to Docker operations and wraps
    Docker SDK exceptions into DokmanError types.
    Supports singleton pattern for connection pooling.
    """

    _shared_instance: "DockerClient | None" = None

    def __init__(self) -> None:
        """Initialize Docker client connection."""
        try:
            self._client = docker.from_env()
            self._client.ping()
        except DockerException as e:
            raise DockerConnectionError(
                f"Failed to connect to Docker daemon: {e}"
            ) from e

    @classmethod
    def get_shared(cls) -> "DockerClient":
        """Get or create a shared DockerClient instance for connection pooling.

        Returns:
            Singleton DockerClient instance.
        """
        if cls._shared_instance is None:
            cls._shared_instance = cls()
        return cls._shared_instance

    @classmethod
    def reset_shared(cls) -> None:
        """Reset the shared instance. Useful for testing."""
        if cls._shared_instance is not None:
            cls._shared_instance.close()
            cls._shared_instance = None

    def ping(self) -> bool:
        """Check if Docker daemon is accessible.

        Returns:
            True if Docker is accessible, False otherwise.
        """
        try:
            self._client.ping()
            return True
        except DockerException:
            return False

    def list_containers(self, filters: dict[str, Any] | None = None) -> list[Container]:
        """List containers with optional filters.

        Args:
            filters: Docker API filters (e.g., {"label": "com.docker.compose.project=myproject"})

        Returns:
            List of Container objects
        """
        try:
            return self._client.containers.list(all=True, filters=filters or {})
        except APIError as e:
            raise DokmanError(f"Failed to list containers: {e}") from e

    def get_container(self, container_id: str) -> Container | None:
        """Get a container by ID or name.

        Args:
            container_id: Container ID or name

        Returns:
            Container object or None if not found
        """
        try:
            return self._client.containers.get(container_id)
        except NotFound:
            return None
        except APIError as e:
            raise DokmanError(f"Failed to get container '{container_id}': {e}") from e

    def inspect_container(self, container_id: str) -> dict[str, Any]:
        """Get detailed information about a container.

        Args:
            container_id: Container ID or name

        Returns:
            Dictionary with container inspection data

        Raises:
            DockmanError: If container not found or inspection fails
        """
        try:
            container = self._client.containers.get(container_id)
            return container.attrs
        except NotFound as e:
            raise DokmanError(f"Container '{container_id}' not found") from e
        except APIError as e:
            raise DokmanError(
                f"Failed to inspect container '{container_id}': {e}"
            ) from e

    def get_container_stats(
        self, container_id: str, stream: bool = True
    ) -> Iterator[dict[str, Any]]:
        """Get resource usage statistics for a container.

        Args:
            container_id: Container ID or name
            stream: If True, stream stats continuously; if False, return single snapshot

        Yields:
            Dictionary with stats data

        Raises:
            DockmanError: If container not found or stats retrieval fails
        """
        try:
            container = self._client.containers.get(container_id)

            if stream:
                # Streaming mode - use decode=True
                stats_stream = container.stats(stream=True, decode=True)
                yield from stats_stream
            else:
                # Non-streaming mode - returns a single dict
                stats = container.stats(stream=False)
                if isinstance(stats, dict):
                    yield stats
        except NotFound as e:
            raise DokmanError(f"Container '{container_id}' not found") from e
        except APIError as e:
            raise DokmanError(
                f"Failed to get stats for container '{container_id}': {e}"
            ) from e

    def list_images(self, filters: dict[str, Any] | None = None) -> list[Image]:
        """List images with optional filters.

        Args:
            filters: Docker API filters

        Returns:
            List of Image objects
        """
        try:
            return self._client.images.list(filters=filters or {})
        except APIError as e:
            raise DokmanError(f"Failed to list images: {e}") from e

    def list_volumes(self, filters: dict[str, Any] | None = None) -> list[Volume]:
        """List volumes with optional filters.

        Args:
            filters: Docker API filters

        Returns:
            List of Volume objects
        """
        try:
            result = self._client.volumes.list(filters=filters or {})
            return result
        except APIError as e:
            raise DokmanError(f"Failed to list volumes: {e}") from e

    def list_networks(self, filters: dict[str, Any] | None = None) -> list[Network]:
        """List networks with optional filters.

        Args:
            filters: Docker API filters

        Returns:
            List of Network objects
        """
        try:
            return self._client.networks.list(filters=filters or {})
        except APIError as e:
            raise DokmanError(f"Failed to list networks: {e}") from e

    def events(self, filters: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        """Stream Docker events.

        Args:
            filters: Docker API filters (e.g., {"type": "container", "event": "start"})

        Yields:
            Dictionary with event data
        """
        try:
            for event in self._client.events(filters=filters or {}, decode=True):
                yield event
        except APIError as e:
            raise DokmanError(f"Failed to stream events: {e}") from e

    def close(self) -> None:
        """Close the Docker client connection."""
        if self._client:
            self._client.close()

    def __enter__(self) -> "DockerClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()
