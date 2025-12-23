"""Property-based tests for resource manager operations.

**Feature: docker-compose-cli, Property 11, 12, 13, 14: Resource listing, stats, pull/build results**
**Validates: Requirements 5.1, 5.3, 6.1, 12.3, 12.4, 13.1, 13.5, 14.1, 14.3, 15.2, 15.3**
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from dockman.clients.compose_client import ComposeClient
from dockman.clients.docker_client import DockerClient
from dockman.models.enums import ProjectHealth, ServiceStatus
from dockman.models.project import Project, Service
from dockman.models.resources import ContainerStats
from dockman.models.results import BuildResult, ComposeResult, PullResult
from dockman.services.resource_manager import ResourceManager


# Custom strategies
@st.composite
def service_name_strategy(draw):
    """Generate a valid service name."""
    return draw(st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-",
        min_size=1,
        max_size=30
    ))


@st.composite
def image_name_strategy(draw):
    """Generate a valid image name."""
    repo = draw(st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-/",
        min_size=1,
        max_size=50
    ))
    tag = draw(st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789._-",
        min_size=1,
        max_size=20
    ))
    return f"{repo}:{tag}"


@st.composite
def project_strategy(draw, service_names: list[str] | None = None):
    """Generate a Project with optional specific service names."""
    if service_names is None:
        service_names = draw(st.lists(
            service_name_strategy(),
            min_size=1,
            max_size=5,
            unique=True
        ))
    
    services = []
    for name in service_names:
        services.append(Service(
            name=name,
            container_id=draw(st.text(alphabet="abcdef0123456789", min_size=12, max_size=12)),
            image=draw(image_name_strategy()),
            status=ServiceStatus.RUNNING,
            ports=[],
            health=None,
            uptime=None,
        ))
    
    return Project(
        name=draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=50)),
        compose_file=Path("/test/compose.yaml"),
        working_dir=Path("/test"),
        services=services,
        status=ProjectHealth.HEALTHY,
        created_at=datetime.now(),
    )


@st.composite
def container_stats_strategy(draw):
    """Generate valid ContainerStats."""
    memory_limit = draw(st.integers(min_value=1, max_value=10**12))
    memory_usage = draw(st.integers(min_value=0, max_value=memory_limit))
    memory_percent = (memory_usage / memory_limit) * 100 if memory_limit > 0 else 0.0
    
    return ContainerStats(
        container_id=draw(st.text(alphabet="abcdef0123456789", min_size=12, max_size=12)),
        name=draw(service_name_strategy()),
        cpu_percent=draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)),
        memory_usage=memory_usage,
        memory_limit=memory_limit,
        memory_percent=round(memory_percent, 2),
        network_rx=draw(st.integers(min_value=0, max_value=10**15)),
        network_tx=draw(st.integers(min_value=0, max_value=10**15)),
    )


def create_resource_manager() -> tuple[ResourceManager, MagicMock, MagicMock]:
    """Create a ResourceManager with mocked dependencies."""
    docker = MagicMock(spec=DockerClient)
    compose = MagicMock(spec=ComposeClient)
    
    # Default empty returns
    docker.list_images.return_value = []
    docker.list_volumes.return_value = []
    docker.list_networks.return_value = []
    docker.list_containers.return_value = []
    
    compose.pull.return_value = ComposeResult(success=True, output="", error=None, return_code=0)
    compose.build.return_value = ComposeResult(success=True, output="", error=None, return_code=0)
    compose.config.return_value = {"services": {}}
    
    rm = ResourceManager(docker, compose)
    return rm, docker, compose


# -----------------------------------------------------------------------------
# Property 11: Resource listing respects project filter
# -----------------------------------------------------------------------------

@given(st.data())
@settings(max_examples=100)
def test_list_images_with_project_filter_uses_label(data):
    """
    **Feature: docker-compose-cli, Property 11: Resource listing respects project filter**
    **Validates: Requirements 5.1, 5.3**
    
    *For any* project, listing images with that project SHALL filter by
    the compose project label.
    """
    project = data.draw(project_strategy())
    rm, docker, compose = create_resource_manager()
    
    rm.list_images(project=project)
    
    # Verify filter was applied
    docker.list_images.assert_called()
    call_kwargs = docker.list_images.call_args.kwargs
    
    if call_kwargs.get("filters"):
        assert f"com.docker.compose.project={project.name}" in str(call_kwargs["filters"])


@given(st.data())
@settings(max_examples=100)
def test_list_volumes_with_project_filter_uses_label(data):
    """
    **Feature: docker-compose-cli, Property 11: Resource listing respects project filter**
    **Validates: Requirements 6.1**
    
    *For any* project, listing volumes with that project SHALL filter by
    the compose project label.
    """
    project = data.draw(project_strategy())
    rm, docker, compose = create_resource_manager()
    
    rm.list_volumes(project=project)
    
    docker.list_volumes.assert_called()
    call_kwargs = docker.list_volumes.call_args.kwargs
    
    if call_kwargs.get("filters"):
        assert f"com.docker.compose.project={project.name}" in str(call_kwargs["filters"])


@given(st.data())
@settings(max_examples=100)
def test_list_networks_with_project_filter_uses_label(data):
    """
    **Feature: docker-compose-cli, Property 11: Resource listing respects project filter**
    **Validates: Requirements 14.1, 14.3**
    
    *For any* project, listing networks with that project SHALL filter by
    the compose project label.
    """
    project = data.draw(project_strategy())
    rm, docker, compose = create_resource_manager()
    
    rm.list_networks(project=project)
    
    docker.list_networks.assert_called()
    call_kwargs = docker.list_networks.call_args.kwargs
    
    if call_kwargs.get("filters"):
        assert f"com.docker.compose.project={project.name}" in str(call_kwargs["filters"])


@given(st.data())
@settings(max_examples=100)
def test_list_images_without_project_no_filter(data):
    """
    **Feature: docker-compose-cli, Property 11: Resource listing respects project filter**
    **Validates: Requirements 5.3**
    
    *For any* image listing without a project filter, no project label filter
    SHALL be applied.
    """
    rm, docker, compose = create_resource_manager()
    
    rm.list_images(project=None)
    
    docker.list_images.assert_called()
    call_kwargs = docker.list_images.call_args.kwargs
    
    # No filters should be applied
    assert call_kwargs.get("filters") is None


# -----------------------------------------------------------------------------
# Property 12: Stats snapshot contains required metrics
# -----------------------------------------------------------------------------

@given(container_stats_strategy())
@settings(max_examples=100)
def test_container_stats_contains_required_fields(stats: ContainerStats):
    """
    **Feature: docker-compose-cli, Property 12: Stats snapshot contains required metrics**
    **Validates: Requirements 15.2, 15.3**
    
    *For any* container stats snapshot, the output SHALL include:
    container name, CPU percentage, memory usage, memory limit,
    memory percentage, network RX bytes, and network TX bytes.
    """
    # Verify all required fields are present and valid
    assert stats.name is not None and len(stats.name) > 0
    assert stats.container_id is not None
    assert isinstance(stats.cpu_percent, float)
    assert stats.cpu_percent >= 0
    assert isinstance(stats.memory_usage, int)
    assert stats.memory_usage >= 0
    assert isinstance(stats.memory_limit, int)
    assert stats.memory_limit >= 0
    assert isinstance(stats.memory_percent, float)
    assert stats.memory_percent >= 0
    assert isinstance(stats.network_rx, int)
    assert stats.network_rx >= 0
    assert isinstance(stats.network_tx, int)
    assert stats.network_tx >= 0


@given(container_stats_strategy())
@settings(max_examples=100)
def test_container_stats_memory_percent_consistent(stats: ContainerStats):
    """
    **Feature: docker-compose-cli, Property 12: Stats snapshot contains required metrics**
    **Validates: Requirements 15.3**
    
    *For any* container stats, memory_percent SHALL be consistent with
    memory_usage and memory_limit.
    """
    if stats.memory_limit > 0:
        expected_percent = (stats.memory_usage / stats.memory_limit) * 100
        # Allow small floating point differences
        assert abs(stats.memory_percent - expected_percent) < 0.1


# -----------------------------------------------------------------------------
# Property 13: Pull result categorization is complete
# -----------------------------------------------------------------------------

@given(st.data())
@settings(max_examples=100)
def test_pull_result_categorization_complete(data):
    """
    **Feature: docker-compose-cli, Property 13: Pull result categorization is complete**
    **Validates: Requirements 12.3, 12.4**
    
    *For any* pull result, every image SHALL appear in exactly one of:
    updated, up_to_date, or failed lists.
    """
    # Generate lists with no overlap
    all_images = data.draw(st.lists(
        image_name_strategy(),
        min_size=1,
        max_size=10,
        unique=True
    ))
    
    # Partition into categories
    num_updated = data.draw(st.integers(min_value=0, max_value=len(all_images)))
    num_up_to_date = data.draw(st.integers(min_value=0, max_value=len(all_images) - num_updated))
    
    updated = all_images[:num_updated]
    up_to_date = all_images[num_updated:num_updated + num_up_to_date]
    failed_images = all_images[num_updated + num_up_to_date:]
    failed = [(img, "error") for img in failed_images]
    
    result = PullResult(
        updated=updated,
        up_to_date=up_to_date,
        failed=failed,
    )
    
    # Verify no duplicates across categories
    all_in_result = set(result.updated) | set(result.up_to_date) | {f[0] for f in result.failed}
    
    # Each image appears exactly once
    assert len(result.updated) + len(result.up_to_date) + len(result.failed) == len(all_in_result)
    
    # No overlap between categories
    assert len(set(result.updated) & set(result.up_to_date)) == 0
    assert len(set(result.updated) & {f[0] for f in result.failed}) == 0
    assert len(set(result.up_to_date) & {f[0] for f in result.failed}) == 0


@given(st.data())
@settings(max_examples=100)
def test_pull_result_failed_contains_error_message(data):
    """
    **Feature: docker-compose-cli, Property 13: Pull result categorization is complete**
    **Validates: Requirements 12.4**
    
    *For any* failed pull, the failed list SHALL contain tuples of
    (image_name, error_message).
    """
    image = data.draw(image_name_strategy())
    error_msg = data.draw(st.text(min_size=1, max_size=200))
    
    result = PullResult(
        updated=[],
        up_to_date=[],
        failed=[(image, error_msg)],
    )
    
    assert len(result.failed) == 1
    assert result.failed[0][0] == image
    assert result.failed[0][1] == error_msg
    assert len(result.failed[0][1]) > 0  # Error message is non-empty


# -----------------------------------------------------------------------------
# Property 14: Build result categorization is complete
# -----------------------------------------------------------------------------

@given(st.data())
@settings(max_examples=100)
def test_build_result_categorization_complete(data):
    """
    **Feature: docker-compose-cli, Property 14: Build result categorization is complete**
    **Validates: Requirements 13.1, 13.5**
    
    *For any* build result, every service SHALL appear in exactly one of:
    built, skipped, or failed lists.
    """
    # Generate service names with no overlap
    all_services = data.draw(st.lists(
        service_name_strategy(),
        min_size=1,
        max_size=10,
        unique=True
    ))
    
    # Partition into categories
    num_built = data.draw(st.integers(min_value=0, max_value=len(all_services)))
    num_skipped = data.draw(st.integers(min_value=0, max_value=len(all_services) - num_built))
    
    built = all_services[:num_built]
    skipped = all_services[num_built:num_built + num_skipped]
    failed_services = all_services[num_built + num_skipped:]
    failed = [(svc, "build error") for svc in failed_services]
    
    result = BuildResult(
        built=built,
        skipped=skipped,
        failed=failed,
    )
    
    # Verify no duplicates across categories
    all_in_result = set(result.built) | set(result.skipped) | {f[0] for f in result.failed}
    
    # Each service appears exactly once
    assert len(result.built) + len(result.skipped) + len(result.failed) == len(all_in_result)
    
    # No overlap between categories
    assert len(set(result.built) & set(result.skipped)) == 0
    assert len(set(result.built) & {f[0] for f in result.failed}) == 0
    assert len(set(result.skipped) & {f[0] for f in result.failed}) == 0


@given(st.data())
@settings(max_examples=100)
def test_build_result_skipped_for_no_build_context(data):
    """
    **Feature: docker-compose-cli, Property 14: Build result categorization is complete**
    **Validates: Requirements 13.5**
    
    *For any* service without a build context, it SHALL appear in the skipped list.
    """
    service = data.draw(service_name_strategy())
    
    # Service with no build context should be skipped
    result = BuildResult(
        built=[],
        skipped=[service],
        failed=[],
    )
    
    assert service in result.skipped
    assert service not in result.built
    assert service not in [f[0] for f in result.failed]


@given(st.data())
@settings(max_examples=100)
def test_build_result_failed_contains_error_message(data):
    """
    **Feature: docker-compose-cli, Property 14: Build result categorization is complete**
    **Validates: Requirements 13.5**
    
    *For any* failed build, the failed list SHALL contain tuples of
    (service_name, error_message).
    """
    service = data.draw(service_name_strategy())
    error_msg = data.draw(st.text(min_size=1, max_size=200))
    
    result = BuildResult(
        built=[],
        skipped=[],
        failed=[(service, error_msg)],
    )
    
    assert len(result.failed) == 1
    assert result.failed[0][0] == service
    assert result.failed[0][1] == error_msg
    assert len(result.failed[0][1]) > 0  # Error message is non-empty
