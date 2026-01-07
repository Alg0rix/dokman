"""Configuration manager service for Dokman."""

from dokman.clients.compose_client import ComposeClient
from dokman.clients.docker_client import DockerClient
from dokman.models.diff import ConfigDiff, ResourceLimitsDiff, ServiceDiff
from dokman.models.project import Project


class ConfigManager:
    """Handles configuration comparison and drift detection.

    Provides methods to compare Docker Compose configuration with
    the actual running container state.
    """

    def __init__(
        self,
        docker: DockerClient,
        compose: ComposeClient,
    ) -> None:
        """Initialize ConfigManager.

        Args:
            docker: Docker client for container operations
            compose: Compose client for compose operations
        """
        self._docker = docker
        self._compose = compose

    def diff_project(self, project: Project) -> ConfigDiff:
        """Compare compose config with running container state.

        Analyzes differences between the docker-compose.yml configuration
        and the actual running containers.

        Args:
            project: Project to compare

        Returns:
            ConfigDiff with detected differences
        """
        # Get expected configuration from compose file
        expected = self._get_expected_config(project)

        # Get actual configuration from running containers
        actual = self._get_actual_config(project)

        service_diffs: list[ServiceDiff] = []
        missing_services: list[str] = []
        extra_services: list[str] = []
        has_changes = False

        expected_names = set(expected.keys())
        actual_names = set(actual.keys())

        # Find missing services (in config but not running)
        for name in expected_names - actual_names:
            missing_services.append(name)
            has_changes = True

        # Find extra services (running but not in config)
        for name in actual_names - expected_names:
            extra_services.append(name)
            has_changes = True

        # Compare common services
        for name in expected_names & actual_names:
            exp = expected[name]
            act = actual[name]

            diff = self._compare_service(name, exp, act)
            service_diffs.append(diff)

            if diff.status != "unchanged":
                has_changes = True

        return ConfigDiff(
            project_name=project.name,
            has_changes=has_changes,
            services=service_diffs,
            missing_services=missing_services,
            extra_services=extra_services,
        )

    def _get_expected_config(self, project: Project) -> dict[str, dict]:
        """Get expected configuration from compose file.

        Args:
            project: Project to get config for

        Returns:
            Dictionary mapping service name to configuration
        """
        config = self._compose.config(project.working_dir)
        services = config.get("services", {})

        result: dict[str, dict] = {}

        for name, svc_config in services.items():
            # Extract relevant configuration
            image = svc_config.get("image", "")

            # Handle build context - image might be generated
            if not image and "build" in svc_config:
                image = f"{project.name}-{name}:latest"

            # Get environment variables
            env: dict[str, str] = {}
            env_config = svc_config.get("environment", {})
            if isinstance(env_config, list):
                for item in env_config:
                    if "=" in item:
                        k, v = item.split("=", 1)
                        env[k] = v
            elif isinstance(env_config, dict):
                env = {k: str(v) for k, v in env_config.items()}

            # Get ports
            ports: list[str] = []
            for port in svc_config.get("ports", []):
                if isinstance(port, dict):
                    target = port.get("target", "")
                    published = port.get("published", "")
                    ports.append(f"{published}:{target}")
                else:
                    ports.append(str(port))

            # Get volumes (bind mounts and named volumes)
            volumes: list[str] = []
            for vol in svc_config.get("volumes", []):
                if isinstance(vol, dict):
                    type_val = vol.get("type")
                    if type_val == "volume":
                        source = vol.get("source", "")
                        target = vol.get("target", "")
                        if source:
                            volumes.append(f"{source}:{target}")
                        else:
                            volumes.append(target)
                    elif type_val == "bind":
                        source = vol.get("source", "")
                        target = vol.get("target", "")
                        volumes.append(f"{source}:{target}")
                    elif type_val == "tmpfs":
                        target = vol.get("target", "")
                        volumes.append(f"tmpfs:{target}")
                elif isinstance(vol, str):
                    volumes.append(vol)

            # Get labels
            labels: dict[str, str] = {}
            labels_config = svc_config.get("labels", {})
            if isinstance(labels_config, list):
                for item in labels_config:
                    if "=" in item:
                        k, v = item.split("=", 1)
                        labels[k] = v
            elif isinstance(labels_config, dict):
                labels = {k: str(v) for k, v in labels_config.items()}

            # Get resource limits
            deploy_config = svc_config.get("deploy", {})
            resources = deploy_config.get("resources", {})
            limits = resources.get("limits", {})

            limits_config = {
                "memory": limits.get("memory_bytes"),
                "memory_swap": None,
                "cpu_period": str(limits["cpus"]) if limits.get("cpus") else None,
                "cpu_quota": None,
                "cpu_shares": None,
            }

            result[name] = {
                "image": image,
                "environment": env,
                "ports": sorted(ports),
                "volumes": sorted(volumes),
                "labels": labels,
                "limits": limits_config,
            }

        return result

    def _get_actual_config(self, project: Project) -> dict[str, dict]:
        """Get actual configuration from running containers.

        Args:
            project: Project to get config for

        Returns:
            Dictionary mapping service name to actual configuration
        """
        containers = self._docker.list_containers(
            filters={"label": f"com.docker.compose.project={project.name}"}
        )

        result: dict[str, dict] = {}

        for container in containers:
            labels = container.labels or {}
            service_name = labels.get("com.docker.compose.service")

            if not service_name:
                continue

            # Get container details
            try:
                attrs = container.attrs or {}
            except Exception:
                attrs = {}

            config = attrs.get("Config", {})
            host_config = attrs.get("HostConfig", {})
            mounts = attrs.get("Mounts", [])

            # Get image
            image = config.get("Image", "")

            # Get environment variables
            env: dict[str, str] = {}
            for item in config.get("Env", []):
                if "=" in item:
                    k, v = item.split("=", 1)
                    env[k] = v

            # Get ports from network settings
            ports: list[str] = []
            network_settings = attrs.get("NetworkSettings", {})
            port_bindings = network_settings.get("Ports", {})

            for container_port, bindings in port_bindings.items():
                if bindings:
                    for binding in bindings:
                        host_port = binding.get("HostPort", "")
                        # Format: host_port:container_port
                        port_str = container_port.replace("/tcp", "").replace(
                            "/udp", ""
                        )
                        ports.append(f"{host_port}:{port_str}")

            # Get volumes from mounts
            volumes: list[str] = []
            for mount in mounts:
                type_val = mount.get("Type")
                source = mount.get("Source", "")
                target = mount.get("Target", "")
                if type_val == "volume":
                    if source:
                        volumes.append(f"{source}:{target}")
                    else:
                        volumes.append(target)
                elif type_val == "bind":
                    volumes.append(f"{source}:{target}")
                elif type_val == "tmpfs":
                    volumes.append(f"tmpfs:{target}")

            # Get labels from container config (excluding compose labels)
            container_labels: dict[str, str] = config.get("Labels", {}) or {}
            # Filter out Docker Compose internal labels
            labels_diff: dict[str, str] = {
                k: v
                for k, v in container_labels.items()
                if not k.startswith("com.docker.compose")
                and not k.startswith("org.docker.compose")
            }

            # Get resource limits from host config
            limits_config = {
                "memory": self._format_memory_limit(host_config.get("Memory")),
                "memory_swap": self._format_memory_limit(host_config.get("MemorySwap")),
                "cpu_period": str(host_config["CpuPeriod"])
                if host_config.get("CpuPeriod")
                else None,
                "cpu_quota": str(host_config["CpuQuota"])
                if host_config.get("CpuQuota")
                else None,
                "cpu_shares": str(host_config["CpuShares"])
                if host_config.get("CpuShares")
                else None,
            }

            result[service_name] = {
                "image": image,
                "environment": env,
                "ports": sorted(ports),
                "volumes": sorted(volumes),
                "labels": labels_diff,
                "limits": limits_config,
            }

        return result

    def _format_memory_limit(self, bytes_val: int | None) -> str | None:
        """Format memory limit from bytes to human-readable string."""
        if not bytes_val or bytes_val <= 0:
            return None
        if bytes_val >= 1024 * 1024 * 1024:
            return f"{bytes_val / (1024 * 1024 * 1024):.1f}g"
        elif bytes_val >= 1024 * 1024:
            return f"{bytes_val / (1024 * 1024):.0f}m"
        elif bytes_val >= 1024:
            return f"{bytes_val / 1024:.0f}k"
        return str(bytes_val)

    def _compare_service(
        self,
        name: str,
        expected: dict,
        actual: dict,
    ) -> ServiceDiff:
        """Compare expected vs actual configuration for a service.

        Args:
            name: Service name
            expected: Expected configuration
            actual: Actual configuration

        Returns:
            ServiceDiff with comparison results
        """
        image_diff: tuple[str, str] | None = None
        env_diff: dict[str, tuple[str | None, str | None]] = {}
        ports_diff: tuple[list[str], list[str]] | None = None
        volumes_diff: tuple[list[str], list[str]] | None = None
        labels_diff: dict[str, tuple[str | None, str | None]] = {}
        limits_diff: ResourceLimitsDiff | None = None

        # Compare images
        exp_image = expected.get("image", "")
        act_image = actual.get("image", "")

        # Normalize image names for comparison
        if not self._images_match(exp_image, act_image):
            image_diff = (exp_image, act_image)

        # Compare environment variables
        exp_env = expected.get("environment", {})
        act_env = actual.get("environment", {})

        # Filter out common Docker-injected variables
        ignore_vars = {"PATH", "HOSTNAME", "HOME", "TERM"}

        all_keys = set(exp_env.keys()) | set(act_env.keys())
        for key in all_keys:
            if key in ignore_vars:
                continue

            exp_val = exp_env.get(key)
            act_val = act_env.get(key)

            if exp_val != act_val:
                env_diff[key] = (exp_val, act_val)

        # Compare ports
        exp_ports = expected.get("ports", [])
        act_ports = actual.get("ports", [])

        if sorted(exp_ports) != sorted(act_ports):
            ports_diff = (exp_ports, act_ports)

        # Compare volumes
        exp_volumes = expected.get("volumes", [])
        act_volumes = actual.get("volumes", [])

        if sorted(exp_volumes) != sorted(act_volumes):
            volumes_diff = (exp_volumes, act_volumes)

        # Compare labels
        exp_labels = expected.get("labels", {})
        act_labels = actual.get("labels", {})

        all_label_keys = set(exp_labels.keys()) | set(act_labels.keys())
        for key in all_label_keys:
            exp_val = exp_labels.get(key)
            act_val = act_labels.get(key)

            if exp_val != act_val:
                labels_diff[key] = (exp_val, act_val)

        # Compare resource limits
        exp_limits = expected.get("limits", {})
        act_limits = actual.get("limits", {})

        limits_diffs = ResourceLimitsDiff(
            memory=self._compare_limit(
                exp_limits.get("memory"), act_limits.get("memory")
            ),
            memory_swap=self._compare_limit(
                exp_limits.get("memory_swap"), act_limits.get("memory_swap")
            ),
            cpu_period=self._compare_limit(
                exp_limits.get("cpu_period"), act_limits.get("cpu_period")
            ),
            cpu_quota=self._compare_limit(
                exp_limits.get("cpu_quota"), act_limits.get("cpu_quota")
            ),
            cpu_shares=self._compare_limit(
                exp_limits.get("cpu_shares"), act_limits.get("cpu_shares")
            ),
        )

        if limits_diffs.has_changes():
            limits_diff = limits_diffs

        # Determine status
        if (
            image_diff
            or env_diff
            or ports_diff
            or volumes_diff
            or labels_diff
            or limits_diff
        ):
            status = "modified"
        else:
            status = "unchanged"

        return ServiceDiff(
            service_name=name,
            status=status,
            image_diff=image_diff,
            env_diff=env_diff,
            ports_diff=ports_diff,
            volumes_diff=volumes_diff,
            labels_diff=labels_diff,
            limits_diff=limits_diff,
        )

    def _compare_limit(
        self, expected: str | None, actual: str | None
    ) -> tuple[str | None, str | None] | None:
        """Compare a single limit value."""
        if expected != actual:
            return (expected, actual)
        return None

    def _images_match(self, expected: str, actual: str) -> bool:
        """Check if two image references match.

        Handles implicit :latest tags and registry prefixes.

        Args:
            expected: Expected image reference
            actual: Actual image reference

        Returns:
            True if images match
        """
        if expected == actual:
            return True

        # Normalize by adding :latest if no tag
        def normalize(img: str) -> str:
            if not img:
                return ""
            if ":" not in img.split("/")[-1]:
                return f"{img}:latest"
            return img

        return normalize(expected) == normalize(actual)
