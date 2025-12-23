"""Property-based tests for data model serialization round-trip.

**Feature: docker-compose-cli, Property 4: Data model serialization round-trip**
**Validates: Requirements 1.2, 2.1, 2.2, 5.1, 6.1, 6.2, 14.1, 14.2**
"""

from datetime import datetime
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from dockman.models import (
    BuildResult,
    ComposeResult,
    ContainerStats,
    ImageInfo,
    NetworkInfo,
    OperationResult,
    Project,
    ProjectHealth,
    PullResult,
    RegisteredProject,
    Service,
    ServiceStatus,
    VolumeInfo,
)


# Custom strategies for generating valid test data
@st.composite
def service_status_strategy(draw):
    """Generate a valid ServiceStatus."""
    return draw(st.sampled_from(list(ServiceStatus)))


@st.composite
def project_health_strategy(draw):
    """Generate a valid ProjectHealth."""
    return draw(st.sampled_from(list(ProjectHealth)))


@st.composite
def datetime_strategy(draw):
    """Generate a valid datetime."""
    return draw(
        st.datetimes(
            min_value=datetime(2000, 1, 1),
            max_value=datetime(2100, 1, 1),
        )
    )


@st.composite
def optional_datetime_strategy(draw):
    """Generate an optional datetime."""
    return draw(st.none() | datetime_strategy())


@st.composite
def path_strategy(draw):
    """Generate a valid path string."""
    parts = draw(st.lists(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=20), min_size=1, max_size=5))
    return Path("/".join(parts))


@st.composite
def port_strategy(draw):
    """Generate a valid port mapping string."""
    host_port = draw(st.integers(min_value=1, max_value=65535))
    container_port = draw(st.integers(min_value=1, max_value=65535))
    return f"{host_port}:{container_port}"


@st.composite
def service_strategy(draw):
    """Generate a valid Service instance."""
    return Service(
        name=draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=50)),
        container_id=draw(st.none() | st.text(alphabet="abcdef0123456789", min_size=12, max_size=64)),
        image=draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-/:", min_size=1, max_size=100)),
        status=draw(service_status_strategy()),
        ports=draw(st.lists(port_strategy(), max_size=5)),
        health=draw(st.none() | st.sampled_from(["healthy", "unhealthy", "starting"])),
        uptime=draw(optional_datetime_strategy()),
    )


@st.composite
def project_strategy(draw):
    """Generate a valid Project instance."""
    return Project(
        name=draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=50)),
        compose_file=draw(path_strategy()),
        working_dir=draw(path_strategy()),
        services=draw(st.lists(service_strategy(), max_size=5)),
        status=draw(project_health_strategy()),
        created_at=draw(optional_datetime_strategy()),
    )


@st.composite
def registered_project_strategy(draw):
    """Generate a valid RegisteredProject instance."""
    return RegisteredProject(
        name=draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=50)),
        compose_file=draw(path_strategy()),
        registered_at=draw(datetime_strategy()),
        last_accessed=draw(optional_datetime_strategy()),
    )


@st.composite
def image_info_strategy(draw):
    """Generate a valid ImageInfo instance."""
    return ImageInfo(
        id=draw(st.text(alphabet="abcdef0123456789", min_size=12, max_size=64)),
        repository=draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-/", min_size=1, max_size=100)),
        tag=draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789._-", min_size=1, max_size=50)),
        size=draw(st.integers(min_value=0, max_value=10**12)),
        created=draw(datetime_strategy()),
        used_by=draw(st.lists(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=50), max_size=5)),
    )


@st.composite
def volume_info_strategy(draw):
    """Generate a valid VolumeInfo instance."""
    return VolumeInfo(
        name=draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=100)),
        driver=draw(st.sampled_from(["local", "nfs", "overlay"])),
        mountpoint=draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-/", min_size=1, max_size=200)),
        size=draw(st.none() | st.integers(min_value=0, max_value=10**12)),
        used_by=draw(st.lists(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=50), max_size=5)),
    )


@st.composite
def network_info_strategy(draw):
    """Generate a valid NetworkInfo instance."""
    return NetworkInfo(
        name=draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=100)),
        driver=draw(st.sampled_from(["bridge", "host", "overlay", "macvlan"])),
        subnet=draw(st.none() | st.just("172.18.0.0/16")),
        gateway=draw(st.none() | st.just("172.18.0.1")),
        containers=draw(st.lists(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=50), max_size=5)),
    )


@st.composite
def container_stats_strategy(draw):
    """Generate a valid ContainerStats instance."""
    memory_limit = draw(st.integers(min_value=1, max_value=10**12))
    memory_usage = draw(st.integers(min_value=0, max_value=memory_limit))
    memory_percent = (memory_usage / memory_limit) * 100 if memory_limit > 0 else 0.0
    
    return ContainerStats(
        container_id=draw(st.text(alphabet="abcdef0123456789", min_size=12, max_size=64)),
        name=draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=100)),
        cpu_percent=draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)),
        memory_usage=memory_usage,
        memory_limit=memory_limit,
        memory_percent=memory_percent,
        network_rx=draw(st.integers(min_value=0, max_value=10**15)),
        network_tx=draw(st.integers(min_value=0, max_value=10**15)),
    )


@st.composite
def operation_result_strategy(draw):
    """Generate a valid OperationResult instance."""
    return OperationResult(
        success=draw(st.booleans()),
        message=draw(st.text(min_size=0, max_size=500)),
        affected_services=draw(st.lists(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=50), max_size=10)),
        errors=draw(st.lists(st.text(min_size=0, max_size=200), max_size=5)),
    )


@st.composite
def pull_result_strategy(draw):
    """Generate a valid PullResult instance."""
    return PullResult(
        updated=draw(st.lists(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-/:", min_size=1, max_size=100), max_size=5)),
        up_to_date=draw(st.lists(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-/:", min_size=1, max_size=100), max_size=5)),
        failed=draw(st.lists(st.tuples(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-/:", min_size=1, max_size=100),
            st.text(min_size=1, max_size=200)
        ), max_size=3)),
    )


@st.composite
def build_result_strategy(draw):
    """Generate a valid BuildResult instance."""
    return BuildResult(
        built=draw(st.lists(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=50), max_size=5)),
        skipped=draw(st.lists(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=50), max_size=5)),
        failed=draw(st.lists(st.tuples(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=50),
            st.text(min_size=1, max_size=200)
        ), max_size=3)),
    )


@st.composite
def compose_result_strategy(draw):
    """Generate a valid ComposeResult instance."""
    return ComposeResult(
        success=draw(st.booleans()),
        output=draw(st.text(min_size=0, max_size=1000)),
        error=draw(st.none() | st.text(min_size=1, max_size=500)),
        return_code=draw(st.integers(min_value=0, max_value=255)),
    )


# Property tests for round-trip serialization

@given(service_strategy())
@settings(max_examples=100)
def test_service_round_trip(service: Service):
    """
    **Feature: docker-compose-cli, Property 4: Data model serialization round-trip**
    **Validates: Requirements 2.1, 2.2**
    
    *For any* valid Service instance, serializing to dict and deserializing back
    SHALL produce an equivalent Service with identical field values.
    """
    serialized = service.to_dict()
    deserialized = Service.from_dict(serialized)
    
    assert deserialized.name == service.name
    assert deserialized.container_id == service.container_id
    assert deserialized.image == service.image
    assert deserialized.status == service.status
    assert deserialized.ports == service.ports
    assert deserialized.health == service.health
    assert deserialized.uptime == service.uptime


@given(project_strategy())
@settings(max_examples=100)
def test_project_round_trip(project: Project):
    """
    **Feature: docker-compose-cli, Property 4: Data model serialization round-trip**
    **Validates: Requirements 1.2, 2.1, 2.2**
    
    *For any* valid Project instance, serializing to dict and deserializing back
    SHALL produce an equivalent Project with identical field values.
    """
    serialized = project.to_dict()
    deserialized = Project.from_dict(serialized)
    
    assert deserialized.name == project.name
    assert deserialized.compose_file == project.compose_file
    assert deserialized.working_dir == project.working_dir
    assert deserialized.status == project.status
    assert deserialized.created_at == project.created_at
    assert len(deserialized.services) == len(project.services)
    
    for orig, deser in zip(project.services, deserialized.services):
        assert deser.name == orig.name
        assert deser.container_id == orig.container_id
        assert deser.image == orig.image
        assert deser.status == orig.status


@given(registered_project_strategy())
@settings(max_examples=100)
def test_registered_project_round_trip(registered_project: RegisteredProject):
    """
    **Feature: docker-compose-cli, Property 4: Data model serialization round-trip**
    **Validates: Requirements 1.2**
    
    *For any* valid RegisteredProject instance, serializing to dict and deserializing back
    SHALL produce an equivalent RegisteredProject with identical field values.
    """
    serialized = registered_project.to_dict()
    deserialized = RegisteredProject.from_dict(serialized)
    
    assert deserialized.name == registered_project.name
    assert deserialized.compose_file == registered_project.compose_file
    assert deserialized.registered_at == registered_project.registered_at
    assert deserialized.last_accessed == registered_project.last_accessed


@given(image_info_strategy())
@settings(max_examples=100)
def test_image_info_round_trip(image_info: ImageInfo):
    """
    **Feature: docker-compose-cli, Property 4: Data model serialization round-trip**
    **Validates: Requirements 5.1**
    
    *For any* valid ImageInfo instance, serializing to dict and deserializing back
    SHALL produce an equivalent ImageInfo with identical field values.
    """
    serialized = image_info.to_dict()
    deserialized = ImageInfo.from_dict(serialized)
    
    assert deserialized.id == image_info.id
    assert deserialized.repository == image_info.repository
    assert deserialized.tag == image_info.tag
    assert deserialized.size == image_info.size
    assert deserialized.created == image_info.created
    assert deserialized.used_by == image_info.used_by


@given(volume_info_strategy())
@settings(max_examples=100)
def test_volume_info_round_trip(volume_info: VolumeInfo):
    """
    **Feature: docker-compose-cli, Property 4: Data model serialization round-trip**
    **Validates: Requirements 6.1, 6.2**
    
    *For any* valid VolumeInfo instance, serializing to dict and deserializing back
    SHALL produce an equivalent VolumeInfo with identical field values.
    """
    serialized = volume_info.to_dict()
    deserialized = VolumeInfo.from_dict(serialized)
    
    assert deserialized.name == volume_info.name
    assert deserialized.driver == volume_info.driver
    assert deserialized.mountpoint == volume_info.mountpoint
    assert deserialized.size == volume_info.size
    assert deserialized.used_by == volume_info.used_by


@given(network_info_strategy())
@settings(max_examples=100)
def test_network_info_round_trip(network_info: NetworkInfo):
    """
    **Feature: docker-compose-cli, Property 4: Data model serialization round-trip**
    **Validates: Requirements 14.1, 14.2**
    
    *For any* valid NetworkInfo instance, serializing to dict and deserializing back
    SHALL produce an equivalent NetworkInfo with identical field values.
    """
    serialized = network_info.to_dict()
    deserialized = NetworkInfo.from_dict(serialized)
    
    assert deserialized.name == network_info.name
    assert deserialized.driver == network_info.driver
    assert deserialized.subnet == network_info.subnet
    assert deserialized.gateway == network_info.gateway
    assert deserialized.containers == network_info.containers


@given(container_stats_strategy())
@settings(max_examples=100)
def test_container_stats_round_trip(container_stats: ContainerStats):
    """
    **Feature: docker-compose-cli, Property 4: Data model serialization round-trip**
    **Validates: Requirements 15.1**
    
    *For any* valid ContainerStats instance, serializing to dict and deserializing back
    SHALL produce an equivalent ContainerStats with identical field values.
    """
    serialized = container_stats.to_dict()
    deserialized = ContainerStats.from_dict(serialized)
    
    assert deserialized.container_id == container_stats.container_id
    assert deserialized.name == container_stats.name
    assert deserialized.cpu_percent == container_stats.cpu_percent
    assert deserialized.memory_usage == container_stats.memory_usage
    assert deserialized.memory_limit == container_stats.memory_limit
    assert deserialized.memory_percent == container_stats.memory_percent
    assert deserialized.network_rx == container_stats.network_rx
    assert deserialized.network_tx == container_stats.network_tx


@given(operation_result_strategy())
@settings(max_examples=100)
def test_operation_result_round_trip(operation_result: OperationResult):
    """
    **Feature: docker-compose-cli, Property 4: Data model serialization round-trip**
    **Validates: Requirements 2.1**
    
    *For any* valid OperationResult instance, serializing to dict and deserializing back
    SHALL produce an equivalent OperationResult with identical field values.
    """
    serialized = operation_result.to_dict()
    deserialized = OperationResult.from_dict(serialized)
    
    assert deserialized.success == operation_result.success
    assert deserialized.message == operation_result.message
    assert deserialized.affected_services == operation_result.affected_services
    assert deserialized.errors == operation_result.errors


@given(pull_result_strategy())
@settings(max_examples=100)
def test_pull_result_round_trip(pull_result: PullResult):
    """
    **Feature: docker-compose-cli, Property 4: Data model serialization round-trip**
    **Validates: Requirements 5.1**
    
    *For any* valid PullResult instance, serializing to dict and deserializing back
    SHALL produce an equivalent PullResult with identical field values.
    """
    serialized = pull_result.to_dict()
    deserialized = PullResult.from_dict(serialized)
    
    assert deserialized.updated == pull_result.updated
    assert deserialized.up_to_date == pull_result.up_to_date
    assert deserialized.failed == pull_result.failed


@given(build_result_strategy())
@settings(max_examples=100)
def test_build_result_round_trip(build_result: BuildResult):
    """
    **Feature: docker-compose-cli, Property 4: Data model serialization round-trip**
    **Validates: Requirements 5.1**
    
    *For any* valid BuildResult instance, serializing to dict and deserializing back
    SHALL produce an equivalent BuildResult with identical field values.
    """
    serialized = build_result.to_dict()
    deserialized = BuildResult.from_dict(serialized)
    
    assert deserialized.built == build_result.built
    assert deserialized.skipped == build_result.skipped
    assert deserialized.failed == build_result.failed


@given(compose_result_strategy())
@settings(max_examples=100)
def test_compose_result_round_trip(compose_result: ComposeResult):
    """
    **Feature: docker-compose-cli, Property 4: Data model serialization round-trip**
    **Validates: Requirements 2.1**
    
    *For any* valid ComposeResult instance, serializing to dict and deserializing back
    SHALL produce an equivalent ComposeResult with identical field values.
    """
    serialized = compose_result.to_dict()
    deserialized = ComposeResult.from_dict(serialized)
    
    assert deserialized.success == compose_result.success
    assert deserialized.output == compose_result.output
    assert deserialized.error == compose_result.error
    assert deserialized.return_code == compose_result.return_code
