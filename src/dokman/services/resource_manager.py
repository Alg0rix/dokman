"""Resource manager service for Dokman."""

import logging
import re
import subprocess
import tarfile
import tempfile
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from dokman.clients.compose_client import ComposeClient
from dokman.clients.docker_client import DockerClient
from dokman.exceptions import DokmanError
from dokman.models.backup import BackupInfo, BackupResult, RestoreResult
from dokman.models.project import Project
from dokman.models.resources import (
    ContainerStats,
    ImageInfo,
    NetworkInfo,
    VolumeInfo,
)
from dokman.models.results import BuildResult, PullResult

logger = logging.getLogger(__name__)

# Regex pattern for validating volume/project names
# Docker volume names must match: [a-zA-Z0-9][a-zA-Z0-9_.-]*
_SAFE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")


def _is_safe_name(name: str) -> bool:
    """Check if a name is safe for use in file paths and Docker commands.
    
    Args:
        name: The name to validate (volume name, project name, etc.)
        
    Returns:
        True if the name is safe, False otherwise
    """
    if not name or len(name) > 255:
        return False
    # Reject path traversal attempts
    if ".." in name or "/" in name or "\\" in name:
        return False
    return bool(_SAFE_NAME_PATTERN.match(name))


def _safe_extract(tar: tarfile.TarFile, path: Path) -> None:
    """Safely extract tar archive with path traversal protection.
    
    This function validates that all extracted files stay within
    the target directory.
    
    Args:
        tar: The tarfile to extract
        path: The target directory for extraction
        
    Raises:
        ValueError: If a member would extract outside the target directory
    """
    path = path.resolve()
    for member in tar.getmembers():
        member_path = (path / member.name).resolve()
        # Check if the resolved path is within the target directory
        if not str(member_path).startswith(str(path)):
            raise ValueError(
                f"Refusing to extract '{member.name}': would escape target directory"
            )
    tar.extractall(path)


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
                except DokmanError:
                    # Skip containers that can't provide stats
                    continue
            if stats_list:
                yield stats_list
        else:
            # Streaming mode - collect stats from all containers and yield together
            import threading
            import queue

            # Single queue for all stats updates
            results_queue: queue.Queue = queue.Queue()

            def fetch_stats(container_id: str, q: queue.Queue) -> None:
                """Fetch stats for a single container and put in queue."""
                try:
                    for stats in self._docker.get_container_stats(
                        container_id, stream=True
                    ):
                        q.put((container_id, stats))
                except Exception:
                    pass
                finally:
                    q.put((container_id, None))  # Signal completion

            # Start threads for all containers
            threads: list[threading.Thread] = []
            for container in containers:
                t = threading.Thread(
                    target=fetch_stats,
                    args=(container.id, results_queue),
                    daemon=True,
                )
                t.start()
                threads.append(t)

            # Cache latest stats for each container
            latest_stats: dict[str, ContainerStats] = {}
            active_sources = len(containers)

            # Yield batches of stats
            try:
                while active_sources > 0:
                    try:
                        # Wait for at least one update with timeout
                        # Timeout allows checking if threads are still alive
                        item = results_queue.get(timeout=0.1)
                        
                        # Process the first item
                        container_id, stats = item
                        if stats is None:
                            active_sources -= 1
                        else:
                            # Update cache (find name from containers list)
                            container_name = next(
                                (c.name for c in containers if c.id == container_id), 
                                container_id[:12]
                            )
                            latest_stats[container_id] = self._parse_container_stats(
                                container_id, container_name, stats
                            )

                        # Drain the queue to process all pending updates (batching)
                        # This prevents flickering and high CPU/redraw usage
                        while True:
                            try:
                                extra_item = results_queue.get_nowait()
                                c_id, s = extra_item
                                if s is None:
                                    active_sources -= 1
                                else:
                                    c_name = next(
                                        (c.name for c in containers if c.id == c_id), 
                                        c_id[:12]
                                    )
                                    latest_stats[c_id] = self._parse_container_stats(
                                        c_id, c_name, s
                                    )
                            except queue.Empty:
                                break
                        
                        # Yield the current view of the world if we have data
                        if latest_stats:
                            # Ensure we yield consistent order or handling? 
                            # List is fine.
                            yield list(latest_stats.values())
                            
                    except queue.Empty:
                        # No updates in this interval, check threads
                        # If active_sources > 0, we just loop again
                        pass
            finally:
                # Clean up threads - they are daemon so they will die, 
                # but we can try to join them if they are done
                pass

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
        except DokmanError:
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

    def backup_volumes(
        self,
        project: Project,
        output_dir: Path,
        service: str | None = None,
    ) -> BackupResult:
        """Backup volumes for a project to a tar archive.
        
        Creates a tar.gz archive containing all volume data for the project.
        Uses docker run with alpine to stream volume data.
        
        Args:
            project: Project to backup volumes for
            output_dir: Directory to save the backup file
            service: Specific service to backup volumes for (None for all)
            
        Returns:
            BackupResult with backup path and status
        """
        # Validate project name to prevent path traversal in backup filename
        if not _is_safe_name(project.name):
            return BackupResult(
                success=False,
                backup_path=None,
                volumes_backed_up=[],
                volumes_skipped=[],
                errors=[f"Invalid project name '{project.name}': contains unsafe characters"],
            )
        
        # Get volumes for this project
        volumes = self.list_volumes(project)
        
        if not volumes:
            return BackupResult(
                success=False,  # Consistent: no backup created = not successful
                backup_path=None,
                volumes_backed_up=[],
                volumes_skipped=[],
                errors=["No volumes found for project"],
            )
        
        # Filter by service if specified
        if service:
            volumes = [v for v in volumes if service in v.used_by]
            if not volumes:
                return BackupResult(
                    success=False,
                    backup_path=None,
                    volumes_backed_up=[],
                    volumes_skipped=[],
                    errors=[f"No volumes found for service '{service}'"],
                )
        
        # Create output directory if needed
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{project.name}_{timestamp}.tar.gz"
        backup_path = output_dir / backup_filename
        
        backed_up: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []
        
        # Create a temporary directory to collect volume data
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir).resolve()
            
            for volume in volumes:
                volume_name = volume.name
                
                # Validate volume name to prevent path traversal
                if not _is_safe_name(volume_name):
                    errors.append(
                        f"Skipping volume '{volume_name}': unsafe name (possible path traversal)"
                    )
                    skipped.append(volume_name)
                    continue
                
                # Ensure the volume directory stays within tmpdir
                volume_dir = (tmpdir_path / volume_name).resolve()
                if not str(volume_dir).startswith(str(tmpdir_path)):
                    errors.append(
                        f"Skipping volume '{volume_name}': path escapes temporary directory"
                    )
                    skipped.append(volume_name)
                    continue
                
                volume_dir.mkdir(exist_ok=True)
                
                try:
                    # Use docker run to copy volume data to temp dir
                    # Volume name is validated above, safe to use in command
                    cmd = [
                        "docker", "run", "--rm",
                        "-v", f"{volume_name}:/source:ro",
                        "-v", f"{volume_dir}:/backup",
                        "alpine",
                        "sh", "-c", "cp -a /source/. /backup/"
                    ]
                    
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=300,  # 5 minute timeout per volume
                    )
                    
                    if result.returncode == 0:
                        backed_up.append(volume_name)
                    else:
                        errors.append(f"Failed to backup '{volume_name}': {result.stderr}")
                        skipped.append(volume_name)
                        
                except subprocess.TimeoutExpired:
                    errors.append(f"Timeout while backing up '{volume_name}'")
                    skipped.append(volume_name)
                except Exception as e:
                    errors.append(f"Error backing up '{volume_name}': {e}")
                    skipped.append(volume_name)
            
            # Create the final tar.gz archive
            if backed_up:
                try:
                    with tarfile.open(backup_path, "w:gz") as tar:
                        for volume_name in backed_up:
                            volume_dir = tmpdir_path / volume_name
                            tar.add(volume_dir, arcname=volume_name)
                except Exception as e:
                    return BackupResult(
                        success=False,
                        backup_path=None,
                        volumes_backed_up=[],
                        volumes_skipped=list(v.name for v in volumes),
                        errors=[f"Failed to create archive: {e}"],
                    )
        
        return BackupResult(
            success=len(backed_up) > 0,
            backup_path=str(backup_path) if backed_up else None,
            volumes_backed_up=backed_up,
            volumes_skipped=skipped,
            errors=errors,
        )

    def restore_volumes(
        self,
        project: Project,
        backup_path: Path,
    ) -> RestoreResult:
        """Restore volumes from a tar archive.
        
        Extracts volume data from a backup archive and restores it to
        the corresponding Docker volumes.
        
        Args:
            project: Project to restore volumes for
            backup_path: Path to the backup tar.gz file
            
        Returns:
            RestoreResult with restored volumes and status
        """
        import subprocess
        import tarfile
        import tempfile
        
        backup_path = Path(backup_path)
        
        if not backup_path.exists():
            return RestoreResult(
                success=False,
                volumes_restored=[],
                errors=[f"Backup file not found: {backup_path}"],
            )
        
        restored: list[str] = []
        errors: list[str] = []
        
        # Extract to temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir).resolve()
            
            try:
                with tarfile.open(backup_path, "r:gz") as tar:
                    # Use safe extraction to prevent path traversal attacks
                    _safe_extract(tar, tmpdir_path)
            except ValueError as e:
                # Path traversal attempt detected
                return RestoreResult(
                    success=False,
                    volumes_restored=[],
                    errors=[f"Security error extracting backup: {e}"],
                )
            except Exception as e:
                return RestoreResult(
                    success=False,
                    volumes_restored=[],
                    errors=[f"Failed to extract backup: {e}"],
                )
            
            # Get list of volumes in backup
            backup_volumes = [d.name for d in tmpdir_path.iterdir() if d.is_dir()]
            
            # Get project volumes
            project_volumes = {v.name for v in self.list_volumes(project)}
            
            for volume_name in backup_volumes:
                # Validate volume name to prevent command injection
                if not _is_safe_name(volume_name):
                    errors.append(
                        f"Skipping volume '{volume_name}': unsafe name in backup"
                    )
                    continue
                
                # Check if volume exists in project
                if volume_name not in project_volumes:
                    errors.append(
                        f"Volume '{volume_name}' from backup not found in project"
                    )
                    continue
                
                volume_dir = tmpdir_path / volume_name
                
                try:
                    # Use docker run to restore volume data
                    # Volume name is validated above, safe to use in command
                    cmd = [
                        "docker", "run", "--rm",
                        "-v", f"{volume_name}:/dest",
                        "-v", f"{volume_dir}:/source:ro",
                        "alpine",
                        "sh", "-c", "rm -rf /dest/* /dest/..?* /dest/.[!.]* 2>/dev/null; cp -a /source/. /dest/"
                    ]
                    
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=300,
                    )
                    
                    if result.returncode == 0:
                        restored.append(volume_name)
                    else:
                        errors.append(f"Failed to restore '{volume_name}': {result.stderr}")
                        
                except subprocess.TimeoutExpired:
                    errors.append(f"Timeout while restoring '{volume_name}'")
                except Exception as e:
                    errors.append(f"Error restoring '{volume_name}': {e}")
        
        return RestoreResult(
            success=len(restored) > 0,
            volumes_restored=restored,
            errors=errors,
        )

    def list_backups(
        self,
        project_name: str,
        backup_dir: Path,
    ) -> list[BackupInfo]:
        """List available backups for a project.
        
        Scans the backup directory for tar.gz files matching the project name.
        
        Args:
            project_name: Name of the project to find backups for
            backup_dir: Directory containing backup files
            
        Returns:
            List of BackupInfo objects sorted by creation date (newest first)
        """
        backup_dir = Path(backup_dir)
        
        if not backup_dir.exists():
            return []
        
        # Validate project name to prevent glob pattern injection
        if not _is_safe_name(project_name):
            logger.warning(
                "Invalid project name '%s' for backup listing: contains unsafe characters",
                project_name
            )
            return []
        
        backups: list[BackupInfo] = []
        failed_count = 0
        
        # Find matching backup files
        pattern = f"{project_name}_*.tar.gz"
        for backup_file in backup_dir.glob(pattern):
            try:
                # Get file stats
                stat = backup_file.stat()
                
                # Parse timestamp from filename
                # Format: projectname_YYYYMMDD_HHMMSS.tar.gz
                name_parts = backup_file.stem.replace(".tar", "").split("_")
                if len(name_parts) >= 3:
                    date_str = f"{name_parts[-2]}_{name_parts[-1]}"
                    try:
                        created_at = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
                    except ValueError:
                        created_at = datetime.fromtimestamp(stat.st_mtime)
                else:
                    created_at = datetime.fromtimestamp(stat.st_mtime)
                
                # Get list of volumes in backup
                volumes: list[str] = []
                try:
                    with tarfile.open(backup_file, "r:gz") as tar:
                        # Get top-level directories (volume names)
                        # Filter for directories only and strip trailing slashes
                        volumes = list({
                            m.name.rstrip("/")
                            for m in tar.getmembers()
                            if m.isdir() and "/" not in m.name.rstrip("/")
                        })
                except Exception as e:
                    # If the backup archive is unreadable or malformed, we still want to
                    # list the backup entry; in that case we simply leave `volumes` empty.
                    logger.debug(
                        "Could not read volume list from backup '%s': %s",
                        backup_file.name, e
                    )
                
                backups.append(BackupInfo(
                    filename=backup_file.name,
                    project_name=project_name,
                    volumes=volumes,
                    created_at=created_at,
                    size_bytes=stat.st_size,
                ))
                
            except Exception as e:
                # Log the error but continue processing other backups
                failed_count += 1
                logger.warning(
                    "Failed to read backup file '%s': %s",
                    backup_file.name, e
                )
                continue
        
        if failed_count > 0:
            logger.info(
                "Skipped %d backup file(s) due to read errors for project '%s'",
                failed_count, project_name
            )
        
        # Sort by creation date (newest first)
        backups.sort(key=lambda b: b.created_at, reverse=True)
        
        return backups
