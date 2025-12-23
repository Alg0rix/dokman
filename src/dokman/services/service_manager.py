"""Service manager for Dokman container operations."""

from collections.abc import Iterator

from dokman.clients.compose_client import ComposeClient
from dokman.clients.docker_client import DockerClient
from dokman.exceptions import (
    ServiceNotFoundError,
    ServiceNotRunningError,
)
from dokman.models.enums import ServiceStatus
from dokman.models.project import Project
from dokman.models.results import OperationResult


class ServiceManager:
    """Handles container and service operations.
    
    Provides methods to start, stop, restart, scale, and manage
    Docker Compose services.
    """

    def __init__(
        self,
        docker: DockerClient,
        compose: ComposeClient,
    ) -> None:
        """Initialize ServiceManager.
        
        Args:
            docker: Docker client for container operations
            compose: Compose client for compose operations
        """
        self._docker = docker
        self._compose = compose

    def start(
        self,
        project: Project,
        service: str | None = None,
    ) -> OperationResult:
        """Start services in a project.
        
        Args:
            project: Project to start services in
            service: Specific service to start (None for all)
            
        Returns:
            OperationResult with operation outcome
        """
        services = [service] if service else None
        
        # Validate service exists if specified
        if service:
            self._validate_service_exists(project, service)
        
        result = self._compose.start(project.working_dir, services)
        
        affected = [service] if service else [s.name for s in project.services]
        
        if result.success:
            return OperationResult(
                success=True,
                message=f"Started services in project '{project.name}'",
                affected_services=affected,
                errors=[],
            )
        else:
            return OperationResult(
                success=False,
                message=f"Failed to start services in project '{project.name}'",
                affected_services=affected,
                errors=[result.error] if result.error else [],
            )


    def stop(
        self,
        project: Project,
        service: str | None = None,
    ) -> OperationResult:
        """Stop services in a project.
        
        Args:
            project: Project to stop services in
            service: Specific service to stop (None for all)
            
        Returns:
            OperationResult with operation outcome
        """
        services = [service] if service else None
        
        # Validate service exists if specified
        if service:
            self._validate_service_exists(project, service)
        
        result = self._compose.stop(project.working_dir, services)
        
        affected = [service] if service else [s.name for s in project.services]
        
        if result.success:
            return OperationResult(
                success=True,
                message=f"Stopped services in project '{project.name}'",
                affected_services=affected,
                errors=[],
            )
        else:
            return OperationResult(
                success=False,
                message=f"Failed to stop services in project '{project.name}'",
                affected_services=affected,
                errors=[result.error] if result.error else [],
            )

    def restart(
        self,
        project: Project,
        service: str | None = None,
    ) -> OperationResult:
        """Restart services in a project.
        
        Args:
            project: Project to restart services in
            service: Specific service to restart (None for all)
            
        Returns:
            OperationResult with operation outcome
        """
        services = [service] if service else None
        
        # Validate service exists if specified
        if service:
            self._validate_service_exists(project, service)
        
        result = self._compose.restart(project.working_dir, services)
        
        affected = [service] if service else [s.name for s in project.services]
        
        if result.success:
            return OperationResult(
                success=True,
                message=f"Restarted services in project '{project.name}'",
                affected_services=affected,
                errors=[],
            )
        else:
            return OperationResult(
                success=False,
                message=f"Failed to restart services in project '{project.name}'",
                affected_services=affected,
                errors=[result.error] if result.error else [],
            )

    def down(
        self,
        project: Project,
        remove_volumes: bool = False,
    ) -> OperationResult:
        """Stop and remove containers, networks for a project.
        
        Args:
            project: Project to bring down
            remove_volumes: Also remove associated volumes
            
        Returns:
            OperationResult with operation outcome
        """
        result = self._compose.down(project.working_dir, volumes=remove_volumes)
        
        affected = [s.name for s in project.services]
        
        if result.success:
            msg = f"Stopped and removed containers for project '{project.name}'"
            if remove_volumes:
                msg += " (including volumes)"
            return OperationResult(
                success=True,
                message=msg,
                affected_services=affected,
                errors=[],
            )
        else:
            return OperationResult(
                success=False,
                message=f"Failed to bring down project '{project.name}'",
                affected_services=affected,
                errors=[result.error] if result.error else [],
            )


    def redeploy(
        self,
        project: Project,
        pull: bool = True,
        strict: bool = False,
    ) -> OperationResult:
        """Redeploy a project with updated images.
        
        Pulls latest images (unless --no-pull) and recreates containers.
        
        Args:
            project: Project to redeploy
            pull: Pull latest images before recreating
            strict: Fail if any image pull fails
            
        Returns:
            OperationResult with operation outcome
        """
        errors: list[str] = []
        affected = [s.name for s in project.services]
        
        # Pull images if requested
        if pull:
            pull_result = self._compose.pull(project.working_dir)
            if not pull_result.success:
                if strict:
                    return OperationResult(
                        success=False,
                        message=f"Failed to pull images for project '{project.name}'",
                        affected_services=affected,
                        errors=[pull_result.error] if pull_result.error else [],
                    )
                else:
                    # Continue with local images but record the error
                    if pull_result.error:
                        errors.append(f"Pull warning: {pull_result.error}")
        
        # Recreate containers with up --force-recreate
        up_result = self._compose.up(project.working_dir, detach=True)
        
        if up_result.success:
            msg = f"Redeployed project '{project.name}'"
            if not pull:
                msg += " (using local images)"
            return OperationResult(
                success=True,
                message=msg,
                affected_services=affected,
                errors=errors,
            )
        else:
            errors.append(up_result.error or "Unknown error during redeploy")
            return OperationResult(
                success=False,
                message=f"Failed to redeploy project '{project.name}'",
                affected_services=affected,
                errors=errors,
            )

    def scale(
        self,
        project: Project,
        service: str,
        replicas: int,
    ) -> OperationResult:
        """Scale a service to specified number of replicas.
        
        Args:
            project: Project containing the service
            service: Service name to scale
            replicas: Number of replicas
            
        Returns:
            OperationResult with operation outcome
        """
        # Validate service exists
        self._validate_service_exists(project, service)
        
        result = self._compose.scale(project.working_dir, service, replicas)
        
        if result.success:
            return OperationResult(
                success=True,
                message=f"Scaled service '{service}' to {replicas} replicas",
                affected_services=[service],
                errors=[],
            )
        else:
            return OperationResult(
                success=False,
                message=f"Failed to scale service '{service}'",
                affected_services=[service],
                errors=[result.error] if result.error else [],
            )


    def exec(
        self,
        project: Project,
        service: str,
        command: list[str],
        interactive: bool = False,
    ) -> int:
        """Execute a command in a running container.
        
        Args:
            project: Project containing the service
            service: Service name to execute command in
            command: Command and arguments to execute
            interactive: Run in interactive mode with TTY
            
        Returns:
            Exit code of the command
            
        Raises:
            ServiceNotFoundError: If service doesn't exist in project
            ServiceNotRunningError: If service is not running
        """
        # Validate service exists
        self._validate_service_exists(project, service)
        
        # Check if service is running
        service_obj = self._get_service(project, service)
        if service_obj and service_obj.status != ServiceStatus.RUNNING:
            raise ServiceNotRunningError(service)
        
        return self._compose.exec(
            project.working_dir,
            service,
            command,
            interactive=interactive,
        )

    def logs(
        self,
        project: Project,
        service: str | None = None,
        follow: bool = False,
        tail: int | None = None,
    ) -> Iterator[str]:
        """Stream logs from services.
        
        Args:
            project: Project to get logs from
            service: Specific service to get logs from (None for all)
            follow: Follow log output in real-time
            tail: Number of lines to show from end of logs
            
        Yields:
            Log lines
        """
        services = [service] if service else None
        
        # Validate service exists if specified
        if service:
            self._validate_service_exists(project, service)
        
        yield from self._compose.logs(
            project.working_dir,
            services=services,
            follow=follow,
            tail=tail,
        )

    def _validate_service_exists(self, project: Project, service: str) -> None:
        """Validate that a service exists in the project.
        
        Args:
            project: Project to check
            service: Service name to validate
            
        Raises:
            ServiceNotFoundError: If service doesn't exist
        """
        service_names = {s.name for s in project.services}
        if service not in service_names:
            raise ServiceNotFoundError(project.name, service)

    def _get_service(self, project: Project, service_name: str):
        """Get a service by name from a project.
        
        Args:
            project: Project to search
            service_name: Name of service to find
            
        Returns:
            Service object or None if not found
        """
        for service in project.services:
            if service.name == service_name:
                return service
        return None
