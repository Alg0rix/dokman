"""Project manager service for Dokman."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from dokman.clients.compose_client import ComposeClient
from dokman.clients.docker_client import DockerClient
from dokman.exceptions import (
    ComposeFileNotFoundError,
    DokmanError,
)
from dokman.models.enums import ProjectHealth, ServiceStatus
from dokman.models.project import Project, RegisteredProject, Service
from dokman.storage.registry import ProjectRegistry


class ProjectManager:
    """Handles project lifecycle and registry operations.

    Provides methods to list, register, unregister, and discover
    Docker Compose projects.
    """

    def __init__(
        self,
        registry: ProjectRegistry,
        docker: DockerClient,
        compose: ComposeClient,
    ) -> None:
        """Initialize ProjectManager.

        Args:
            registry: Project registry for tracking projects
            docker: Docker client for container operations
            compose: Compose client for compose operations
        """
        self._registry = registry
        self._docker = docker
        self._compose = compose
        self._logger = logging.getLogger(__name__)

    def list_projects(self, include_unregistered: bool = False) -> list[Project]:
        """List all tracked projects.

        Args:
            include_unregistered: If True, also include running projects
                                 that are not registered

        Returns:
            List of Project objects with current status
        """
        registered = self._registry.list_all()
        registered_names = {p.name for p in registered}

        projects: list[Project] = []

        if registered:
            with ThreadPoolExecutor(max_workers=8) as executor:
                future_to_project = {
                    executor.submit(self._build_project_safe, reg): reg
                    for reg in registered
                }
                for future in as_completed(future_to_project):
                    reg = future_to_project[future]
                    try:
                        project = future.result()
                        if project:
                            projects.append(project)
                    except Exception as e:
                        self._logger.debug("Failed to load project %s: %s", reg.name, e)

        if include_unregistered:
            discovered = self.discover_projects()
            for project in discovered:
                if project.name not in registered_names:
                    projects.append(project)

        return projects

    def _build_project_safe(self, reg_project: RegisteredProject) -> Project | None:
        """Build a project safely, catching any exceptions.

        Args:
            reg_project: The registered project to build from

        Returns:
            Project with current status, or None if an error occurred
        """
        try:
            return self._build_project_from_registered(reg_project)
        except Exception as e:
            self._logger.debug("Failed to build project %s: %s", reg_project.name, e)
            return None

    def get_project(self, name: str) -> Project | None:
        """Get a project by name.

        Args:
            name: Project name to look up

        Returns:
            Project object if found, None otherwise
        """
        reg_project = self._registry.get(name)
        if reg_project:
            return self._build_project_from_registered(reg_project)

        containers = self._docker.list_containers(
            filters={"label": f"com.docker.compose.project={name}"}
        )

        if not containers:
            return None

        project = self._build_project_from_containers(name, containers)
        project.status = self.get_project_status(project)
        return project

    def _build_project_from_containers(
        self, project_name: str, containers: list
    ) -> Project:
        """Build a Project from Docker containers.

        Args:
            project_name: Name of the project
            containers: List of Docker container objects

        Returns:
            Project with services populated from containers
        """
        services = []
        working_dir = Path.cwd()

        for container in containers:
            labels = container.labels or {}
            config_files = labels.get("com.docker.compose.project.config_files", "")
            if config_files:
                working_dir = Path(config_files.split(",")[0]).parent

            service = self._build_service_from_container(container)
            services.append(service)

        compose_file = working_dir / "compose.yaml"

        return Project(
            name=project_name,
            compose_file=compose_file,
            working_dir=working_dir,
            services=services,
            status=ProjectHealth.UNKNOWN,
        )

    def get_registered_names(self) -> set[str]:
        """Get the names of all registered projects.

        This is useful for determining which projects from a list
        are registered vs discovered.

        Returns:
            Set of registered project names
        """
        return {p.name for p in self._registry.list_all()}

    def get_stale_projects(self) -> list[tuple[RegisteredProject, list[str]]]:
        """Find registered projects with missing compose files or orphaned containers.

        Returns:
            List of tuples containing (registered_project, list_of_issues)
            where issues can be "missing_compose_file" or "has_orphans"
        """
        stale: list[tuple[RegisteredProject, list[str]]] = []
        registered = self._registry.list_all()

        for reg_project in registered:
            issues: list[str] = []

            # Check if compose file exists
            if not reg_project.compose_file.exists():
                issues.append("missing_compose_file")
                stale.append((reg_project, issues))
                continue

            # Check for orphaned containers (running containers for registered project)
            try:
                containers = self._docker.list_containers(
                    filters={"label": f"com.docker.compose.project={reg_project.name}"}
                )
                if containers:
                    issues.append("has_orphans")
            except DokmanError:
                # Docker error - skip this check
                pass

            if issues:
                stale.append((reg_project, issues))

        return stale

    def find_orphan_containers(self) -> list[dict]:
        """Find containers running for projects that are not registered.

        Returns:
            List of dictionaries containing orphan container information
        """
        # Get all running compose containers
        containers = self._docker.list_containers(
            filters={"label": "com.docker.compose.project"}
        )

        # Get registered project names
        registered_names = self.get_registered_names()

        orphans: list[dict] = []
        for container in containers:
            labels = container.labels or {}
            project_name = labels.get("com.docker.compose.project", "")

            # Skip if project is registered
            if project_name in registered_names:
                continue

            # Skip compose internals
            if project_name.startswith("dokman-"):
                continue

            service_name = labels.get("com.docker.compose.service", container.name)

            # Get container attrs for more info
            attrs = getattr(container, "attrs", {}) or {}
            created = attrs.get("Created", "")[:10] if attrs.get("Created") else None

            orphans.append(
                {
                    "container_id": container.id[:12] if container.id else "",
                    "container_name": container.name,
                    "project_name": project_name,
                    "service_name": service_name,
                    "status": container.status,
                    "created_at": created,
                }
            )

        return orphans

    def prune_stale_entries(self, force: bool = False) -> dict:
        """Remove stale registry entries.

        Args:
            force: If True, remove entries without confirmation

        Returns:
            Dictionary with 'removed' and 'skipped' lists
        """
        stale = self.get_stale_projects()
        removed: list[str] = []
        skipped: list[str] = []

        for reg_project, issues in stale:
            issue_descriptions = ", ".join(
                "missing compose file"
                if i == "missing_compose_file"
                else "has orphan containers"
                for i in issues
            )

            if force:
                self._registry.remove(reg_project.name)
                removed.append(f"{reg_project.name} ({issue_descriptions})")
            else:
                skipped.append(f"{reg_project.name} ({issue_descriptions})")

        return {"removed": removed, "skipped": skipped}

    def get_project_by_path(self, path: Path) -> Project | None:
        """Get a project by its directory path.

        Args:
            path: Path to project directory or file within it

        Returns:
            Project object if found, None otherwise
        """
        # Resolve path
        path = path.resolve()

        # If it's a file, get parent directory
        if path.is_file():
            path = path.parent

        # First check registered projects
        registered = self._registry.list_all()
        for reg_project in registered:
            if not reg_project.compose_file.exists():
                continue

            project_dir = reg_project.compose_file.parent.resolve()
            if path == project_dir:
                return self._build_project_from_registered(reg_project)

        # Check running but unregistered projects
        # This is more expensive as it queries Docker
        discovered = self.discover_projects()
        for project in discovered:
            if project.working_dir.resolve() == path:
                return project

        # Finally, check if the current directory contains a compose file
        # and if so, return it as an unregistered project
        try:
            compose_file = self._find_compose_file_in_dir(path)
            if compose_file.exists():
                # It's a valid project directory, but not registered or running
                # We can return a basic Project object for it
                return Project(
                    name=path.name,
                    compose_file=compose_file,
                    working_dir=path,
                    services=[],
                    status=ProjectHealth.UNKNOWN,
                )
        except Exception:
            pass

        return None

    def register_project(self, path: Path, name: str | None = None) -> Project:
        """Register a Docker Compose project for tracking.

        Args:
            path: Path to compose file or directory containing compose file
            name: Optional custom name for the project

        Returns:
            The registered Project

        Raises:
            ComposeFileNotFoundError: If compose file doesn't exist
            DokmanError: If registration fails
        """
        compose_file = self._resolve_compose_file(path)

        if not compose_file.exists():
            raise ComposeFileNotFoundError(compose_file)

        # Determine project name
        if name is None:
            name = self._get_project_name_from_compose(compose_file)

        # Create registered project
        now = datetime.now()
        reg_project = RegisteredProject(
            name=name,
            compose_file=compose_file,
            registered_at=now,
            last_accessed=now,
        )

        self._registry.add(reg_project)

        # Return full project with status
        project = self._build_project_from_registered(reg_project)
        if project is None:
            # File exists but couldn't build project - return minimal project
            return Project(
                name=name,
                compose_file=compose_file,
                working_dir=compose_file.parent,
                services=[],
                status=ProjectHealth.UNKNOWN,
                created_at=now,
            )
        return project

    def unregister_project(self, name: str) -> bool:
        """Remove a project from tracking.

        Args:
            name: Name of the project to unregister

        Returns:
            True if project was unregistered, False if not found
        """
        return self._registry.remove(name)

    def discover_projects(self) -> list[Project]:
        """Discover running Docker Compose projects.

        Finds all running Docker Compose projects by querying
        Docker for containers with compose labels.

        Returns:
            List of discovered Project objects
        """
        projects: dict[str, Project] = {}

        # Get all containers with compose project label
        containers = self._docker.list_containers(
            filters={"label": "com.docker.compose.project"}
        )

        for container in containers:
            labels = container.labels or {}
            project_name = labels.get("com.docker.compose.project")

            if not project_name:
                continue

            # Get or create project
            if project_name not in projects:
                working_dir_str = labels.get(
                    "com.docker.compose.project.working_dir", ""
                )
                config_files = labels.get("com.docker.compose.project.config_files", "")

                # Parse compose file path
                if config_files:
                    compose_file = Path(config_files.split(",")[0])
                elif working_dir_str:
                    compose_file = self._find_compose_file_in_dir(Path(working_dir_str))
                else:
                    compose_file = Path("unknown")

                working_dir = (
                    Path(working_dir_str) if working_dir_str else compose_file.parent
                )

                projects[project_name] = Project(
                    name=project_name,
                    compose_file=compose_file,
                    working_dir=working_dir,
                    services=[],
                    status=ProjectHealth.UNKNOWN,
                )

            # Add service from container
            service = self._build_service_from_container(container)
            projects[project_name].services.append(service)

        # Calculate health for each project
        for project in projects.values():
            project.status = self.get_project_status(project)

        return list(projects.values())

    def get_project_status(self, project: Project) -> ProjectHealth:
        """Calculate the overall health status of a project.

        Args:
            project: Project to evaluate

        Returns:
            ProjectHealth enum value based on service states
        """
        if not project.services:
            return ProjectHealth.UNKNOWN

        running_count = 0
        unhealthy_count = 0
        stopped_count = 0

        for service in project.services:
            if service.status == ServiceStatus.RUNNING:
                running_count += 1
                # Check health if available
                if service.health and service.health.lower() == "unhealthy":
                    unhealthy_count += 1
            elif service.status in (ServiceStatus.DEAD,):
                unhealthy_count += 1
            elif service.status in (ServiceStatus.STOPPED, ServiceStatus.EXITED):
                stopped_count += 1

        total = len(project.services)

        # Determine overall health
        if unhealthy_count > 0:
            return ProjectHealth.UNHEALTHY
        if running_count == total:
            return ProjectHealth.HEALTHY
        if running_count > 0:
            return ProjectHealth.PARTIAL
        if stopped_count == total:
            return ProjectHealth.UNHEALTHY

        return ProjectHealth.UNKNOWN

    def _build_project_from_registered(
        self, reg_project: RegisteredProject
    ) -> Project | None:
        """Build a full Project from a RegisteredProject.

        Args:
            reg_project: The registered project to build from

        Returns:
            Project with current status, or None if compose file missing
        """
        if not reg_project.compose_file.exists():
            return None

        working_dir = reg_project.compose_file.parent

        # Get services from compose ps
        try:
            containers = self._compose.ps(working_dir)
        except DokmanError:
            containers = []

        services = []
        for container_info in containers:
            service = self._build_service_from_compose_ps(container_info)
            services.append(service)

        project = Project(
            name=reg_project.name,
            compose_file=reg_project.compose_file,
            working_dir=working_dir,
            services=services,
            status=ProjectHealth.UNKNOWN,
        )

        project.status = self.get_project_status(project)
        return project

    def _build_service_from_container(self, container) -> Service:
        """Build a Service from a Docker container object.

        Args:
            container: Docker SDK Container object

        Returns:
            Service instance
        """
        labels = container.labels or {}
        service_name = labels.get("com.docker.compose.service", container.name)

        # Get image name
        image = (
            container.image.tags[0]
            if container.image.tags
            else str(container.image.id)[:12]
        )

        # Map container status to ServiceStatus
        status = self._map_container_status(container.status)

        # Get ports
        ports = []
        if hasattr(container, "ports") and container.ports:
            for port, bindings in container.ports.items():
                if bindings:
                    for binding in bindings:
                        host_port = binding.get("HostPort", "")
                        if host_port:
                            ports.append(f"{host_port}:{port}")
                else:
                    ports.append(port)

        # Get health status
        health = None
        if hasattr(container, "attrs"):
            state = container.attrs.get("State", {})
            health_data = state.get("Health", {})
            health = health_data.get("Status")

        # Get uptime (started at)
        uptime = None
        if hasattr(container, "attrs"):
            state = container.attrs.get("State", {})
            started_at = state.get("StartedAt")
            if started_at and started_at != "0001-01-01T00:00:00Z":
                try:
                    # Parse ISO format, handling timezone
                    uptime = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                except ValueError:
                    pass

        return Service(
            name=service_name,
            container_id=container.id[:12] if container.id else None,
            image=image,
            status=status,
            ports=ports,
            health=health,
            uptime=uptime,
        )

    def _build_service_from_compose_ps(self, container_info: dict) -> Service:
        """Build a Service from docker compose ps output.

        Args:
            container_info: Dictionary from compose ps --format json

        Returns:
            Service instance
        """
        name = container_info.get("Service", container_info.get("Name", "unknown"))
        container_id = (
            container_info.get("ID", "")[:12] if container_info.get("ID") else None
        )
        image = container_info.get("Image", "unknown")

        # Map state to ServiceStatus
        state = container_info.get("State", "").lower()
        status = self._map_compose_state(state)

        # Parse ports
        ports = []
        publishers = container_info.get("Publishers", [])
        if publishers:
            for pub in publishers:
                if isinstance(pub, dict):
                    published = pub.get("PublishedPort", 0)
                    target = pub.get("TargetPort", 0)
                    if published and target:
                        ports.append(f"{published}:{target}")
                    elif target:
                        ports.append(str(target))

        # Get health
        health = container_info.get("Health", None)

        return Service(
            name=name,
            container_id=container_id,
            image=image,
            status=status,
            ports=ports,
            health=health,
            uptime=None,  # Not available from compose ps
        )

    def _map_container_status(self, status: str) -> ServiceStatus:
        """Map Docker container status to ServiceStatus enum.

        Args:
            status: Docker container status string

        Returns:
            ServiceStatus enum value
        """
        status_lower = status.lower()
        mapping = {
            "running": ServiceStatus.RUNNING,
            "exited": ServiceStatus.EXITED,
            "paused": ServiceStatus.PAUSED,
            "restarting": ServiceStatus.RESTARTING,
            "dead": ServiceStatus.DEAD,
            "created": ServiceStatus.STOPPED,
            "removing": ServiceStatus.STOPPED,
        }
        return mapping.get(status_lower, ServiceStatus.STOPPED)

    def _map_compose_state(self, state: str) -> ServiceStatus:
        """Map docker compose state to ServiceStatus enum.

        Args:
            state: State string from compose ps

        Returns:
            ServiceStatus enum value
        """
        mapping = {
            "running": ServiceStatus.RUNNING,
            "exited": ServiceStatus.EXITED,
            "paused": ServiceStatus.PAUSED,
            "restarting": ServiceStatus.RESTARTING,
            "dead": ServiceStatus.DEAD,
            "created": ServiceStatus.STOPPED,
        }
        return mapping.get(state, ServiceStatus.STOPPED)

    def _resolve_compose_file(self, path: Path) -> Path:
        """Resolve path to compose file.

        Args:
            path: Path to compose file or directory

        Returns:
            Path to compose file
        """
        if path.is_file():
            return path.resolve()

        if path.is_dir():
            return self._find_compose_file_in_dir(path)

        # Path doesn't exist yet, assume it's a file path
        return path.resolve()

    def _find_compose_file_in_dir(self, directory: Path) -> Path:
        """Find compose file in a directory.

        Args:
            directory: Directory to search

        Returns:
            Path to compose file (may not exist)
        """
        # Standard compose file names in order of preference
        compose_names = [
            "compose.yaml",
            "compose.yml",
            "docker-compose.yaml",
            "docker-compose.yml",
        ]

        for name in compose_names:
            compose_file = directory / name
            if compose_file.exists():
                return compose_file.resolve()

        # Default to compose.yaml if none found
        return (directory / "compose.yaml").resolve()

    def _get_project_name_from_compose(self, compose_file: Path) -> str:
        """Get project name from compose file or directory.

        Args:
            compose_file: Path to compose file

        Returns:
            Project name (directory name by default)
        """
        # Docker Compose uses the directory name as project name by default
        return compose_file.parent.name
