# Dokman

Dokman is a Python CLI tool for centralized Docker Compose deployment management. It provides a unified interface to manage Docker Compose deployments from any directory without navigating to individual compose file locations.

## Features

- List and monitor all Docker Compose deployments from a single location
- Start, stop, restart, and redeploy services without changing directories
- View logs, execute commands, and inspect container health
- Manage images, volumes, and networks across projects
- Track projects with a local registry for persistent management
- Rich terminal output with table and JSON formatting options

## Requirements

- Python 3.13 or higher
- Docker Engine with Docker Compose v2
- uv (recommended for installation) or pip

## Installation

### Quick Install (Recommended)

The easiest way to install dokman is using the installation script:

```bash
curl -fsSL https://raw.githubusercontent.com/Alg0rix/dokman/main/install.sh | bash
```

This will automatically install [uv](https://docs.astral.sh/uv/) if needed and set up dokman.

### Upgrade

To upgrade to the latest version, run the install script again or use:

```bash
uv tool upgrade dokman
```

### Using uv

If you already have uv installed:

```bash
uv tool install --python 3.13 dokman

# Verify installation
dokman --help
```

### Using pip

```bash
pip install dokman
```

### From Source

```bash
# Clone the repository
git clone https://github.com/Alg0rix/dokman.git
cd dokman

# Install dependencies
uv sync

# Run dokman
uv run dokman --help
```

## Quick Start

### Register a Project

Register an existing Docker Compose project for tracking:

```bash
# Register from compose file path
dokman register /path/to/docker-compose.yml

# Register with custom name
dokman register /path/to/project --name myapp
```

### Start a Project

Start a project directly (auto-registers if needed):

```bash
# Start from current directory
dokman up

# Start from specific path
dokman up -f /path/to/project

# Start with custom name
dokman up -f ./myproject -n myapp
```

### List Projects

```bash
# List registered projects
dokman list

# Include unregistered running projects
dokman list --all

# Output as JSON
dokman list --format json
```

### Manage Services

```bash
# View project details
dokman info myproject

# Start/stop/restart services
dokman start myproject
dokman stop myproject
dokman restart myproject

# Restart specific service
dokman restart myproject --service web

# Stop and remove containers
dokman down myproject

# Remove with volumes
dokman down myproject --volumes
```

### View Logs

```bash
# View all logs
dokman logs myproject

# View specific service logs
dokman logs myproject --service web

# Follow logs in real-time
dokman logs myproject --follow

# Show last N lines
dokman logs myproject --tail 100
```

### Execute Commands

```bash
# Run command in container
dokman exec myproject web ls -la

# Interactive shell
dokman exec myproject web sh --interactive
```

## Commands Reference

### Project Management

| Command | Description |
|---------|-------------|
| `list` | List all Docker Compose projects |
| `info <project>` | Display detailed project information |
| `register <path>` | Register a project for tracking |
| `unregister <project>` | Remove project from tracking |
| `up` | Start a project (auto-registers if needed) |

### Service Lifecycle

| Command | Description |
|---------|-------------|
| `start <project>` | Start services in a project |
| `stop <project>` | Stop services in a project |
| `restart <project>` | Restart services in a project |
| `down <project>` | Stop and remove containers/networks |
| `redeploy <project>` | Redeploy with updated images |
| `scale <project> <service> <replicas>` | Scale a service |

### Debugging and Inspection

| Command | Description |
|---------|-------------|
| `logs <project>` | Display service logs |
| `exec <project> <service> <command>` | Execute command in container |
| `health <project>` | Display health check status |
| `events <project>` | Stream Docker events |
| `config <project>` | Show resolved compose configuration |
| `env <project>` | Display environment variables |

### Resource Management

| Command | Description |
|---------|-------------|
| `images [project]` | List Docker images |
| `volumes [project]` | List Docker volumes |
| `networks [project]` | List Docker networks |
| `stats <project>` | Display resource usage statistics |
| `pull <project>` | Pull latest images |
| `build <project>` | Build images from compose file |

## Command Options

### Global Options

- `--format, -f`: Output format (`table` or `json`)
- `--help`: Show command help

### Common Options

- `--service, -s`: Target specific service
- `--all, -a`: Include all items (registered and unregistered)
- `--volumes, -v`: Include volumes in operation

### Logs Options

- `--follow, -f`: Stream logs in real-time
- `--tail, -n`: Number of lines to show

### Redeploy Options

- `--no-pull`: Skip pulling latest images
- `--strict`: Fail if any image pull fails

### Build Options

- `--no-cache`: Build without using cache

### Stats Options

- `--no-stream`: Display single snapshot instead of streaming

### Environment Options

- `--show-secrets`: Show sensitive values (masked by default)
- `--export`: Output in shell export format

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

## Configuration

Dokman stores its project registry at:

```
~/.config/dokman/projects.json
```

This file tracks registered projects and their compose file locations.

## Architecture

Dokman follows a layered architecture:

```
CLI Layer (Typer) -> Service Layer -> Docker Client Layer -> Storage Layer
```

- CLI Layer: Typer-based commands with Rich output formatting
- Service Layer: Business logic (ProjectManager, ServiceManager, ResourceManager)
- Docker Client Layer: Wraps Docker SDK and compose commands
- Storage Layer: JSON-based project registry

## Development

### Setup Development Environment

```bash
# Install with dev dependencies
uv sync --extra dev
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/properties/test_models_properties.py

# Run with verbose output
uv run pytest -v
```

### Code Quality

```bash
# Lint code
uvx ruff check

# Type check
uvx ty check
```

### Project Structure

```
dokman/
  cli/           # CLI commands and output formatting
  clients/       # Docker SDK and compose command wrappers
  models/        # Data models (Project, Service, etc.)
  services/      # Business logic layer
  storage/       # Project registry persistence
tests/
  properties/    # Property-based tests (Hypothesis)
```

## Dependencies

- typer: CLI framework
- docker: Docker SDK for Python
- rich: Terminal output formatting

### Development Dependencies

- pytest: Testing framework
- hypothesis: Property-based testing
- pytest-mock: Mocking support

## License

MIT License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request