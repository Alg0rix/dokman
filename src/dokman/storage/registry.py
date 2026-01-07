"""Project registry for tracking Docker Compose projects."""

import json
import threading
from pathlib import Path

from dokman.exceptions import RegistryError
from dokman.models.project import RegisteredProject


class ProjectRegistry:
    """Manages the local project tracking database.

    Stores registered projects in a JSON file at ~/.config/dokman/projects.json
    Uses in-memory caching for faster repeated access.
    """

    def __init__(self, config_path: Path | None = None):
        """Initialize the registry.

        Args:
            config_path: Optional custom path for the registry file.
                        Defaults to ~/.config/dokman/projects.json
        """
        self._config_path = (
            config_path or Path.home() / ".config" / "dokman" / "projects.json"
        )
        self._cache: dict[str, RegisteredProject] | None = None
        self._lock = threading.RLock()

    @property
    def config_path(self) -> Path:
        """Return the path to the registry file."""
        return self._config_path

    def _ensure_cache_loaded(self) -> None:
        """Ensure cache is loaded from disk. Thread-safe."""
        if self._cache is None:
            with self._lock:
                if self._cache is None:
                    self._cache = self._load_from_disk()

    def _load_from_disk(self) -> dict[str, RegisteredProject]:
        """Load projects from disk without using cache.

        Returns:
            Dictionary mapping project names to RegisteredProject instances.
        """
        if not self._config_path.exists():
            return {}

        try:
            with open(self._config_path, "r") as f:
                data = json.load(f)

            return {
                name: RegisteredProject.from_dict(project_data)
                for name, project_data in data.items()
            }
        except json.JSONDecodeError as e:
            raise RegistryError(f"Failed to parse registry file: {e}")
        except (OSError, IOError) as e:
            raise RegistryError(f"Failed to read registry file: {e}")

    def clear_cache(self) -> None:
        """Clear the in-memory cache. Useful for testing."""
        with self._lock:
            self._cache = None

    def load(self) -> dict[str, RegisteredProject]:
        """Load all registered projects from the registry file.

        Returns:
            Dictionary mapping project names to RegisteredProject instances.

        Raises:
            RegistryError: If the file exists but cannot be read or parsed.
        """
        self._ensure_cache_loaded()
        cache = self._cache
        assert cache is not None
        return cache.copy()

    def save(self, projects: dict[str, RegisteredProject]) -> None:
        """Save projects to the registry file.

        Args:
            projects: Dictionary mapping project names to RegisteredProject instances.

        Raises:
            RegistryError: If the file cannot be written.
        """
        with self._lock:
            try:
                self._config_path.parent.mkdir(parents=True, exist_ok=True)
                data = {name: project.to_dict() for name, project in projects.items()}
                with open(self._config_path, "w") as f:
                    json.dump(data, f, indent=2)
                self._cache = projects.copy()
            except (OSError, IOError) as e:
                raise RegistryError(f"Failed to write registry file: {e}")

    def add(self, project: RegisteredProject) -> None:
        """Add a project to the registry.

        Args:
            project: The RegisteredProject to add.

        Raises:
            RegistryError: If the registry cannot be updated.
        """
        with self._lock:
            self._ensure_cache_loaded()
            assert self._cache is not None
            self._cache[project.name] = project
            self.save(self._cache)

    def remove(self, name: str) -> bool:
        """Remove a project from the registry.

        Args:
            name: The name of the project to remove.

        Returns:
            True if the project was removed, False if it didn't exist.

        Raises:
            RegistryError: If the registry cannot be updated.
        """
        with self._lock:
            self._ensure_cache_loaded()
            cache = self._cache
            assert cache is not None
            if name not in cache:
                return False
            del cache[name]
            self.save(cache)
            return True

    def get(self, name: str) -> RegisteredProject | None:
        """Get a project by name.

        Args:
            name: The name of the project to retrieve.

        Returns:
            The RegisteredProject if found, None otherwise.

        Raises:
            RegistryError: If the registry cannot be read.
        """
        self._ensure_cache_loaded()
        cache = self._cache
        assert cache is not None
        return cache.get(name)

    def list_all(self) -> list[RegisteredProject]:
        """List all registered projects.

        Returns:
            List of all RegisteredProject instances.

        Raises:
            RegistryError: If the registry cannot be read.
        """
        self._ensure_cache_loaded()
        cache = self._cache
        assert cache is not None
        return list(cache.values())

    def exists(self, name: str) -> bool:
        """Check if a project exists in the registry.

        Args:
            name: The name of the project to check.

        Returns:
            True if the project exists, False otherwise.

        Raises:
            RegistryError: If the registry cannot be read.
        """
        self._ensure_cache_loaded()
        cache = self._cache
        assert cache is not None
        return name in cache
