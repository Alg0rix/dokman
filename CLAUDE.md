# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Dockman is a Python CLI tool for centralized Docker Compose deployment management. It provides a unified interface to manage Docker Compose deployments from any directory without navigating to individual compose file locations.

- **Entry Point:** `dockman.cli.app:app`
- **Python:** >= 3.13
- **Key Dependencies:** typer (CLI), docker (Docker SDK), rich (output formatting)

## Development Commands

```bash
# Install dependencies
uv sync

# Install with dev dependencies
uv sync --extra dev

# Run tests
pytest

# Run a single test file
pytest tests/properties/test_models_properties.py

# Lint
uvx ruff check

# Type check
uvx ty check

# Run Python file
uv run path/to/file.py

# Run CLI
dockman --help
```

## Architecture

The system follows a layered architecture:

```
CLI Layer (Typer) → Service Layer → Docker Client Layer → Storage Layer
```

**Layer Responsibilities:**
- **CLI Layer** (`dockman/cli/`): Typer commands with Rich output formatting
- **Service Layer** (`dockman/services/`): Business logic (ProjectManager, ServiceManager, ResourceManager)
- **Docker Client Layer** (`dockman/clients/`): Wraps Docker SDK and compose commands
- **Storage Layer** (`dockman/storage/`): JSON-based project registry at `~/.config/dockman/projects.json`

## Key Design Patterns

All data models are dataclasses with `to_dict()` and `from_dict()` methods for serialization round-trips. This pattern ensures data can be serialized for storage/display and deserialized back.

## Data Models

All models are in `dockman/models/`:
- **Enums:** `ServiceStatus` (RUNNING, STOPPED, etc.), `ProjectHealth` (HEALTHY, UNHEALTHY, PARTIAL, UNKNOWN)
- **Core:** `Service`, `Project`, `RegisteredProject`
- **Resources:** `ImageInfo`, `VolumeInfo`, `NetworkInfo`, `ContainerStats`
- **Results:** `OperationResult`, `PullResult`, `BuildResult`, `ComposeResult`

## Custom Exceptions

Defined in `dockman/exceptions.py`:
- `DockmanError` (base)
- `ProjectNotFoundError`, `ServiceNotFoundError`, `ServiceNotRunningError`
- `ComposeFileNotFoundError`, `DockerConnectionError`, `RegistryError`

## Testing Strategy

- **pytest** for unit tests
- **hypothesis** for property-based testing (model serialization round-trips)
- **pytest-mock** for mocking Docker API

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Project not found |
| 3 | Service not found |
| 4 | Docker connection error |
| 5 | Compose file error |
| 6 | Operation failed |

## Implementation Status

Currently implemented: project structure, data models, exceptions.
Not yet implemented: storage layer, Docker client wrappers, service layer, CLI commands.

## Key Design Document

See `.kiro/specs/docker-compose-cli/design.md` for detailed architecture, component interfaces, and correctness properties.
