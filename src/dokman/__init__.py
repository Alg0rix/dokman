"""Dokman - Centralized Docker Compose deployment management CLI."""

from importlib.metadata import version as _get_version, PackageNotFoundError
from pathlib import Path


def _get_package_version() -> str:
    """Get package version with fallback for development mode."""
    try:
        return _get_version("dokman")
    except PackageNotFoundError:
        # Development mode: read version from pyproject.toml
        try:
            pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
            if pyproject_path.exists():
                content = pyproject_path.read_text()
                for line in content.splitlines():
                    if line.startswith("version"):
                        # Parse: version = "x.y.z"
                        return line.split("=", 1)[1].strip().strip('"\'')
        except (OSError, IndexError):
            pass
        return "0.0.0"  # Unknown version fallback


__version__ = _get_package_version()
