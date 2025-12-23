"""Resource manager service for Dockman."""

from collections.abc import Iterator
from datetime import datetime
from typing import Any

from dockman.clients.compose_client import ComposeClient
from dockman.clients.docker_client import DockerClient
from dockman.exceptions import DockmanError
from dockman.models.project import Project
from dockman.models.resources import (
    ContainerStats,
    ImageInfo,
    NetworkInfo,
    VolumeInfo,
)
from dockman.models.results import BuildResult, PullResult


class ResourceManager:
    """Handles images, volumes, networks, and resource statistics.
    
    Provides methods to list, inspect, and manage Docker resources
    associated with Docker Compose projects.
    """

    def __init__(
        self,
        docker: DockerClient,
        compose: ComposeClient,
    ) -> None:
        """Initialize ResourceManager.
        
        Args:
            docker: Docker client for resource operations
            compose: Compose client for compose operations
        """
        self._docker = docker
        self._compose = compose

    def list_images(self, project: Project | None = None) -> list[ImageInfo]:
        """List Docker images, optionally filtered by project.
        
        Args:
            project: If provided, only list images used by this project
            
        Returns:
            List of ImageInfo objects
        """
        filters: dict[str, Any] = {}
        
        if project:
            # Filter by compose project label
            filters["label"] = f"com.docker.compose.project={project.name}"
        
        images = self._docker.list_images(filters=filters if project else None)
        
        # If filtering by project, also include images referenced by services
        project_images: set[str] = set()
        if project:
            for service in project.services:
                project_images.add(service.image)
        
        result: list[ImageInfo] = []
        seen_ids: set[str] = set()
        
        for image in images:
            image_id = image.id[:12] if image.id else ""
            
            if image_id in seen_ids:
                continue
            seen_ids.add(image_id)
            
            # Get repository and tag
            repo = "<none>"
            tag = "<none>"
            if image.tags:
                parts = image.tags[0].rsplit(":", 1)
                repo = parts[0]
                tag = parts[1] if len(parts) > 1 else "latest"
            
            # Get creation time
            created = datetime.now()
            if hasattr(image, "attrs") and image.attrs:
                created_str = image.attrs.get("Created", "")
                if created_str:
                    try:
                        created = datetime.fromisoformat(
                            created_str.replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass
            
            # Get size
            size = 0
            if hasattr(image, "attrs") and image.attrs:
                size = image.attrs.get("Size", 0)
            
            # Determine which services use this image
            used_by: list[str] = []
            if project:
                for service in project.services:
                    if self._image_matches(service.image, image):
                        used_by.append(service.name)
            
            result.append(
                ImageInfo(
                    id=image_id,
                    repository=repo,
                    tag=tag,
                    size=size,
                    created=created,
                    used_by=used_by,
                )
            )
        
        # If project filter, also get images by service reference
        if project and project_images:
            all_images = self._docker.list_images()
            for image in all_images:
                image_id = image.id[:12] if image.id else ""
                if image_id in seen_ids:
                    continue
                
                # Check if any service references this image
                matches_service = False
                used_by = []
                for service in project.services:
                    if self._image_matches(service.image, image):
                        matches_service = True
                        used_by.append(service.name)
                
                if matches_service:
                    seen_ids.add(image_id)
                    
                    repo = "<none>"
                    tag = "<none>"
                    if image.tags:
                        parts = image.tags[0].rsplit(":", 1)
                        repo = parts[0]
                        tag = parts[1] if len(parts) > 1 else "latest"
                    
                    created = datetime.now()
                    if hasattr(image, "attrs") and image.attrs:
                        created_str = image.attrs.get("Created", "")
                        if created_str:
                            try:
                                created = datetime.fromisoformat(
                                    created_str.replace("Z", "+00:00")
                                )
                            except ValueError:
                                pass
                    
                    size = 0
                    if hasattr(image, "attrs") and image.attrs:
                        size = image.attrs.get("Size", 0)
                    
                    result.append(
                        ImageInfo(
                            id=image_id,
                            repository=repo,
                            tag=tag,
                            size=size,
                            created=created,
                            used_by=used_by,
                        )
                    )
        
        return result

    def _image_matches(self, service_image: str, docker_image) -> bool:
        """Check if a Docker image matches a service image reference.
        
        Args:
            service_image: Image reference from service (e.g., "nginx:latest")
            docker_image: Docker SDK Image object
            
        Returns:
            True if the image matches
        """
        if not docker_image.tags:
            return False
        
        for tag in docker_image.tags:
            if tag == service_image:
                return True
            # Handle implicit :latest tag
            if ":" not in service_image and tag == f"{service_image}:latest":
                return True
        
        return False


    def list_volumes(self, project: Project | None = None) -> list[VolumeInfo]:
        """List Docker volumes, optionally filtered by project.
        
        Args:
            project: If provided, only list volumes used by this project
            
        Returns:
            List of VolumeInfo objects
        """
        filters: dict[str, Any] = {}
        
        if project:
            # Filter by compose project label
            filters["label"] = f"com.docker.compose.project={project.name}"
        
        volumes = self._docker.list_volumes(filters=filters if project else None)
        
        result: list[VolumeInfo] = []
        
        for volume in volumes:
            name = volume.name if hasattr(volume, "name") else str(volume)
            
            # Get volume attributes
            driver = "local"
            mountpoint = ""
            
            if hasattr(volume, "attrs") and volume.attrs:
                driver = volume.attrs.get("Driver", "local")
                mountpoint = volume.attrs.get("Mountpoint", "")
            
            # Size is not directly available from Docker API
            # Would need to inspect filesystem, which is expensive
            size = None
            
            # Determine which services use this volume
            used_by: list[str] = []
            if project:
                # Get containers using this volume
                containers = self._docker.list_containers(
                    filters={"volume": name}
                )
                for container in containers:
                    labels = container.labels or {}
                    service_name = labels.get("com.docker.compose.service")
                    container_project = labels.get("com.docker.compose.project")
                    if service_name and container_project == project.name:
                        if service_name not in used_by:
                            used_by.append(service_name)
            
            result.append(
                VolumeInfo(
                    name=name,
                    driver=driver,
                    mountpoint=mountpoint,
                    size=size,
                    used_by=used_by,
                )
            )
        
        return result

    def list_networks(self, project: Project | None = None) -> list[NetworkInfo]:
        """List Docker networks, optionally filtered by project.
        
        Args:
            project: If provided, only list networks used by this project
            
        Returns:
            List of NetworkInfo objects
        """
        filters: dict[str, Any] = {}
        
        if project:
            # Filter by compose project label
            filters["label"] = f"com.docker.compose.project={project.name}"
        
        networks = self._docker.list_networks(filters=filters if project else None)
        
        result: list[NetworkInfo] = []
        
        for network in networks:
            name = network.name if hasattr(network, "name") else str(network)
            
            # Get network attributes
            driver = "bridge"
            subnet = None
            gateway = None
            containers: list[str] = []
            
            if hasattr(network, "attrs") and network.attrs:
                driver = network.attrs.get("Driver", "bridge")
                
                # Get IPAM config for subnet/gateway
                ipam = network.attrs.get("IPAM", {})
                ipam_config = ipam.get("Config", [])
                if ipam_config:
                    subnet = ipam_config[0].get("Subnet")
                    gateway = ipam_config[0].get("Gateway")
                
                # Get connected containers
                network_containers = network.attrs.get("Containers", {})
                for container_id, container_info in network_containers.items():
                    container_name = container_info.get("Name", container_id[:12])
                    containers.append(container_name)
            
            result.append(
                NetworkInfo(
                    name=name,
                    driver=driver,
                    subnet=subnet,
                    gateway=gateway,
                    containers=containers,
                )
            )
        
        return result

    def prune_volumes(self, project: Project) -> dict[str, Any]:
        """Remove unused volumes for a project.
        
        Args:
            project: Project to prune volumes for
            
        Returns:
            Dictionary with pruned volume names and space reclaimed
        """
        # Get volumes for this project
        volumes = self.list_volumes(project)
        
        pruned: list[str] = []
        errors: list[str] = []
        
        for volume in volumes:
            # Only prune volumes not in use
            if not volume.used_by:
                try:
                    # Get the volume object and remove it
                    docker_volumes = self._docker.list_volumes(
                        filters={"name": volume.name}
                    )
                    for dv in docker_volumes:
                        if hasattr(dv, "name") and dv.name == volume.name:
                            dv.remove()
                            pruned.append(volume.name)
                            break
                except Exception as e:
                    errors.append(f"Failed to remove volume '{volume.name}': {e}")
        
        return {
            "pruned": pruned,
            "errors": errors,
        }


    def get_stats(
        self,
        project: Project,
        stream: bool = True,
    ) -> Iterator[list[ContainerStats]]:
        """Get resource usage statistics for project containers.

        Args:
            project: Project to get stats for
            stream: If True, continuously stream stats; if False, single snapshot

        Yields:
            List of ContainerStats objects for all containers (one list per update)
        """
        # Get containers for this project
        containers = self._docker.list_containers(
            filters={"label": f"com.docker.compose.project={project.name}"}
        )

        if not stream:
            # Single snapshot mode - get stats for all containers once
            stats_list: list[ContainerStats] = []
            for container in containers:
                try:
                    stats_iter = self._docker.get_container_stats(
                        container.id, stream=False
                    )
                    for stats in stats_iter:
                        container_stats = self._parse_container_stats(
                            container.id, container.name, stats
                        )
                        stats_list.append(container_stats)
                        break  # Only one snapshot per container
                except DockmanError:
                    # Skip containers that can't provide stats
                    continue
            if stats_list:
                yield stats_list
        else:
            # Streaming mode - collect stats from all containers and yield together
            import threading
            import queue

            # Create a queue for each container's stats
            container_queues: dict[str, queue.Queue] = {}
            for container in containers:
                container_queues[container.id] = queue.Queue()

            def fetch_stats(container_id: str, q: queue.Queue) -> None:
                """Fetch stats for a single container and put in queue."""
                try:
                    for stats in self._docker.get_container_stats(
                        container_id, stream=True
                    ):
                        q.put(stats)
                except Exception:
                    q.put(None)  # Signal completion/error

            # Start threads for all containers
            threads: list[threading.Thread] = []
            for container in containers:
                t = threading.Thread(
                    target=fetch_stats,
                    args=(container.id, container_queues[container.id]),
                    daemon=True,
                )
                t.start()
                threads.append(t)

            # Yield batches of stats from all containers
            try:
                while True:
                    batch: list[ContainerStats] = []
                    all_done = True

                    for container in containers:
                        q = container_queues[container.id]
                        try:
                            # Non-blocking get with timeout to allow checking other queues
                            stats = q.get(timeout=0.5)
                            if stats is None:
                                continue  # Thread finished but keep going
                            container_stats = self._parse_container_stats(
                                container.id, container.name, stats
                            )
                            batch.append(container_stats)
                        except queue.Empty:
                            # No stats yet for this container
                            all_done = False

                    if batch:
                        yield batch

                    # Check if all threads are still alive
                    for t in threads:
                        if t.is_alive():
                            all_done = False
                            break

                    if all_done and not batch:
                        break
            finally:
                # Clean up threads
                for t in threads:
                    t.join(timeout=0.1)

    def _parse_container_stats(
        self,
        container_id: str,
        container_name: str,
        stats: dict[str, Any],
    ) -> ContainerStats:
        """Parse Docker stats response into ContainerStats.
        
        Args:
            container_id: Container ID
            container_name: Container name
            stats: Raw stats dictionary from Docker API
            
        Returns:
            ContainerStats object
        """
        # Calculate CPU percentage
        cpu_percent = 0.0
        cpu_stats = stats.get("cpu_stats", {})
        precpu_stats = stats.get("precpu_stats", {})
        
        cpu_delta = (
            cpu_stats.get("cpu_usage", {}).get("total_usage", 0)
            - precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
        )
        system_delta = (
            cpu_stats.get("system_cpu_usage", 0)
            - precpu_stats.get("system_cpu_usage", 0)
        )
        
        if system_delta > 0 and cpu_delta > 0:
            num_cpus = cpu_stats.get("online_cpus", 1)
            if num_cpus == 0:
                num_cpus = len(cpu_stats.get("cpu_usage", {}).get("percpu_usage", [1]))
            cpu_percent = (cpu_delta / system_delta) * num_cpus * 100.0
        
        # Get memory stats
        memory_stats = stats.get("memory_stats", {})
        memory_usage = memory_stats.get("usage", 0)
        memory_limit = memory_stats.get("limit", 0)
        
        # Calculate memory percentage
        memory_percent = 0.0
        if memory_limit > 0:
            memory_percent = (memory_usage / memory_limit) * 100.0
        
        # Get network stats
        network_rx = 0
        network_tx = 0
        networks = stats.get("networks", {})
        for interface_stats in networks.values():
            network_rx += interface_stats.get("rx_bytes", 0)
            network_tx += interface_stats.get("tx_bytes", 0)
        
        return ContainerStats(
            container_id=container_id[:12],
            name=container_name,
            cpu_percent=round(cpu_percent, 2),
            memory_usage=memory_usage,
            memory_limit=memory_limit,
            memory_percent=round(memory_percent, 2),
            network_rx=network_rx,
            network_tx=network_tx,
        )


    def pull_images(
        self,
        project: Project,
        service: str | None = None,
    ) -> PullResult:
        """Pull latest images for a project.
        
        Args:
            project: Project to pull images for
            service: Specific service to pull (None for all)
            
        Returns:
            PullResult with updated, up_to_date, and failed images
        """
        services = [service] if service else None
        
        # Use compose pull command
        result = self._compose.pull(project.working_dir, services)
        
        # Parse the output to categorize results
        updated: list[str] = []
        up_to_date: list[str] = []
        failed: list[tuple[str, str]] = []
        
        if result.success:
            # Parse output to determine which images were updated
            output = result.output.lower()
            
            # Get list of services/images to check
            if service:
                service_images = [service]
            else:
                service_images = [s.name for s in project.services]
            
            for svc in service_images:
                if "pulled" in output or "downloading" in output:
                    # Assume updated if pull succeeded and had activity
                    updated.append(svc)
                else:
                    up_to_date.append(svc)
            
            # If no specific indicators, assume all are up to date
            if not updated and not up_to_date:
                up_to_date = service_images
        else:
            # Parse errors
            error_msg = result.error or "Unknown error"
            
            if service:
                failed.append((service, error_msg))
            else:
                # Try to identify which services failed
                for svc in project.services:
                    if svc.name.lower() in error_msg.lower():
                        failed.append((svc.name, error_msg))
                    else:
                        # Assume others might have succeeded
                        up_to_date.append(svc.name)
                
                # If no specific failures identified, mark all as failed
                if not failed:
                    for svc in project.services:
                        failed.append((svc.name, error_msg))
                    up_to_date.clear()
        
        return PullResult(
            updated=updated,
            up_to_date=up_to_date,
            failed=failed,
        )

    def build_images(
        self,
        project: Project,
        service: str | None = None,
        no_cache: bool = False,
    ) -> BuildResult:
        """Build images for a project.
        
        Args:
            project: Project to build images for
            service: Specific service to build (None for all)
            no_cache: Build without using cache
            
        Returns:
            BuildResult with built, skipped, and failed services
        """
        services = [service] if service else None
        
        # First, get compose config to identify services with build context
        try:
            config = self._compose.config(project.working_dir)
        except DockmanError:
            config = {}
        
        # Identify services with build context
        services_config = config.get("services", {})
        buildable_services: set[str] = set()
        
        for svc_name, svc_config in services_config.items():
            if "build" in svc_config:
                buildable_services.add(svc_name)
        
        # Use compose build command
        result = self._compose.build(project.working_dir, services, no_cache=no_cache)
        
        built: list[str] = []
        skipped: list[str] = []
        failed: list[tuple[str, str]] = []
        
        # Determine which services to report on
        if service:
            target_services = [service]
        else:
            target_services = [s.name for s in project.services]
        
        if result.success:
            for svc in target_services:
                if svc in buildable_services:
                    built.append(svc)
                else:
                    skipped.append(svc)
        else:
            error_msg = result.error or "Build failed"
            
            for svc in target_services:
                if svc not in buildable_services:
                    skipped.append(svc)
                else:
                    # Check if this specific service failed
                    if svc.lower() in error_msg.lower():
                        failed.append((svc, error_msg))
                    else:
                        # Might have built successfully before failure
                        # Conservative: mark as failed if overall build failed
                        failed.append((svc, error_msg))
        
        return BuildResult(
            built=built,
            skipped=skipped,
            failed=failed,
        )
