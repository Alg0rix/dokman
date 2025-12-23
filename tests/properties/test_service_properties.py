"""Property-based tests for service manager operations.

**Feature: docker-compose-cli, Property 5, 7, 15: Service filtering, error results, tail parameter**
**Validates: Requirements 3.1, 3.2, 3.4, 4.4, 7.1, 7.2, 7.4, 12.4, 13.1, 13.2**
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
from dockman.models.results import ComposeResult, OperationResult
from dockman.services.service_manager import ServiceManager


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
def service_strategy(draw, name: str | None = None):
    """Generate a valid Service instance."""
    actual_name = name if name is not None else draw(service_name_strategy())
    return Service(
        name=actual_name,
        container_id=draw(st.none() | st.text(alphabet="abcdef0123456789", min_size=12, max_size=64)),
        image=draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-/:", min_size=1, max_size=100)),
        status=draw(st.sampled_from(list(ServiceStatus))),
        ports=[],
        health=None,
        uptime=None,
    )


@st.composite
def project_with_named_services_strategy(draw, service_names: list[str]):
    """Generate a Project with specific service names."""
    services = [draw(service_strategy(name=name)) for name in service_names]
    
    return Project(
        name=draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=50)),
        compose_file=Path("/test/compose.yaml"),
        working_dir=Path("/test"),
        services=services,
        status=ProjectHealth.UNKNOWN,
        created_at=datetime.now(),
    )


def create_service_manager(compose_result: ComposeResult | None = None) -> ServiceManager:
    """Create a ServiceManager with mocked dependencies."""
    docker = MagicMock(spec=DockerClient)
    compose = MagicMock(spec=ComposeClient)
    
    if compose_result is None:
        compose_result = ComposeResult(success=True, output="", error=None, return_code=0)
    
    compose.start.return_value = compose_result
    compose.stop.return_value = compose_result
    compose.restart.return_value = compose_result
    compose.down.return_value = compose_result
    compose.pull.return_value = compose_result
    compose.up.return_value = compose_result
    compose.scale.return_value = compose_result
    
    return ServiceManager(docker, compose)


# -----------------------------------------------------------------------------
# Property 5: Service filtering is correct
# -----------------------------------------------------------------------------

@given(st.data())
@settings(max_examples=100)
def test_restart_with_service_filter_affects_only_specified(data):
    """
    **Feature: docker-compose-cli, Property 5: Service filtering is correct**
    **Validates: Requirements 3.1, 3.2**
    
    *For any* project with multiple services and a service name filter,
    the restart operation SHALL affect only the specified service.
    """
    # Generate 2-5 unique service names
    service_names = data.draw(st.lists(
        service_name_strategy(),
        min_size=2,
        max_size=5,
        unique=True
    ))
    
    # Pick one service to filter
    target_service = data.draw(st.sampled_from(service_names))
    
    project = data.draw(project_with_named_services_strategy(service_names))
    sm = create_service_manager()
    
    result = sm.restart(project, service=target_service)
    
    # Only the target service should be affected
    assert result.affected_services == [target_service]


@given(st.data())
@settings(max_examples=100)
def test_restart_without_filter_affects_all_services(data):
    """
    **Feature: docker-compose-cli, Property 5: Service filtering is correct**
    **Validates: Requirements 3.1, 3.2**
    
    *For any* project with multiple services and no service filter,
    the restart operation SHALL affect all services.
    """
    # Generate 1-5 unique service names
    service_names = data.draw(st.lists(
        service_name_strategy(),
        min_size=1,
        max_size=5,
        unique=True
    ))
    
    project = data.draw(project_with_named_services_strategy(service_names))
    sm = create_service_manager()
    
    result = sm.restart(project, service=None)
    
    # All services should be affected
    assert set(result.affected_services) == set(service_names)


@given(st.data())
@settings(max_examples=100)
def test_start_with_service_filter_affects_only_specified(data):
    """
    **Feature: docker-compose-cli, Property 5: Service filtering is correct**
    **Validates: Requirements 3.1, 3.2**
    
    *For any* project with multiple services and a service name filter,
    the start operation SHALL affect only the specified service.
    """
    service_names = data.draw(st.lists(
        service_name_strategy(),
        min_size=2,
        max_size=5,
        unique=True
    ))
    
    target_service = data.draw(st.sampled_from(service_names))
    project = data.draw(project_with_named_services_strategy(service_names))
    sm = create_service_manager()
    
    result = sm.start(project, service=target_service)
    
    assert result.affected_services == [target_service]


@given(st.data())
@settings(max_examples=100)
def test_stop_with_service_filter_affects_only_specified(data):
    """
    **Feature: docker-compose-cli, Property 5: Service filtering is correct**
    **Validates: Requirements 3.1, 3.2**
    
    *For any* project with multiple services and a service name filter,
    the stop operation SHALL affect only the specified service.
    """
    service_names = data.draw(st.lists(
        service_name_strategy(),
        min_size=2,
        max_size=5,
        unique=True
    ))
    
    target_service = data.draw(st.sampled_from(service_names))
    project = data.draw(project_with_named_services_strategy(service_names))
    sm = create_service_manager()
    
    result = sm.stop(project, service=target_service)
    
    assert result.affected_services == [target_service]


# -----------------------------------------------------------------------------
# Property 7: Error results contain required context
# -----------------------------------------------------------------------------

@given(st.data())
@settings(max_examples=100)
def test_failed_operation_contains_error_context(data):
    """
    **Feature: docker-compose-cli, Property 7: Error results contain required context**
    **Validates: Requirements 3.4, 4.4, 12.4**
    
    *For any* failed operation, the OperationResult SHALL contain:
    success=False, a non-empty error message, and the list of affected services.
    """
    service_names = data.draw(st.lists(
        service_name_strategy(),
        min_size=1,
        max_size=5,
        unique=True
    ))
    
    error_message = data.draw(st.text(min_size=1, max_size=200))
    
    project = data.draw(project_with_named_services_strategy(service_names))
    
    # Create a failing compose result
    failed_result = ComposeResult(
        success=False,
        output="",
        error=error_message,
        return_code=1
    )
    
    sm = create_service_manager(failed_result)
    
    result = sm.restart(project, service=None)
    
    # Verify error context
    assert result.success is False
    assert len(result.errors) > 0
    assert error_message in result.errors[0]
    assert len(result.affected_services) > 0


@given(st.data())
@settings(max_examples=100)
def test_failed_start_contains_affected_services(data):
    """
    **Feature: docker-compose-cli, Property 7: Error results contain required context**
    **Validates: Requirements 3.4**
    
    *For any* failed start operation, the result SHALL list the affected services.
    """
    service_names = data.draw(st.lists(
        service_name_strategy(),
        min_size=1,
        max_size=5,
        unique=True
    ))
    
    target_service = data.draw(st.sampled_from(service_names))
    project = data.draw(project_with_named_services_strategy(service_names))
    
    failed_result = ComposeResult(
        success=False,
        output="",
        error="Failed to start",
        return_code=1
    )
    
    sm = create_service_manager(failed_result)
    
    result = sm.start(project, service=target_service)
    
    assert result.success is False
    assert target_service in result.affected_services


@given(st.data())
@settings(max_examples=100)
def test_failed_stop_contains_affected_services(data):
    """
    **Feature: docker-compose-cli, Property 7: Error results contain required context**
    **Validates: Requirements 3.4**
    
    *For any* failed stop operation, the result SHALL list the affected services.
    """
    service_names = data.draw(st.lists(
        service_name_strategy(),
        min_size=1,
        max_size=5,
        unique=True
    ))
    
    target_service = data.draw(st.sampled_from(service_names))
    project = data.draw(project_with_named_services_strategy(service_names))
    
    failed_result = ComposeResult(
        success=False,
        output="",
        error="Failed to stop",
        return_code=1
    )
    
    sm = create_service_manager(failed_result)
    
    result = sm.stop(project, service=target_service)
    
    assert result.success is False
    assert target_service in result.affected_services


@given(st.data())
@settings(max_examples=100)
def test_failed_down_contains_all_services(data):
    """
    **Feature: docker-compose-cli, Property 7: Error results contain required context**
    **Validates: Requirements 4.4**
    
    *For any* failed down operation, the result SHALL list all services as affected.
    """
    service_names = data.draw(st.lists(
        service_name_strategy(),
        min_size=1,
        max_size=5,
        unique=True
    ))
    
    project = data.draw(project_with_named_services_strategy(service_names))
    
    failed_result = ComposeResult(
        success=False,
        output="",
        error="Failed to bring down",
        return_code=1
    )
    
    sm = create_service_manager(failed_result)
    
    result = sm.down(project)
    
    assert result.success is False
    assert set(result.affected_services) == set(service_names)


# -----------------------------------------------------------------------------
# Property 15: Tail parameter limits output correctly
# -----------------------------------------------------------------------------

@given(st.integers(min_value=1, max_value=100))
@settings(max_examples=100)
def test_logs_tail_parameter_passed_correctly(tail: int):
    """
    **Feature: docker-compose-cli, Property 15: Tail parameter limits output correctly**
    **Validates: Requirements 7.4**
    
    *For any* logs command with --tail N parameter, the tail value SHALL be
    passed to the compose client.
    """
    docker = MagicMock(spec=DockerClient)
    compose = MagicMock(spec=ComposeClient)
    
    # Mock logs to return an empty iterator
    compose.logs.return_value = iter([])
    
    sm = ServiceManager(docker, compose)
    
    project = Project(
        name="test-project",
        compose_file=Path("/test/compose.yaml"),
        working_dir=Path("/test"),
        services=[Service(
            name="web",
            container_id="abc123",
            image="nginx",
            status=ServiceStatus.RUNNING,
            ports=[],
            health=None,
            uptime=None,
        )],
        status=ProjectHealth.HEALTHY,
        created_at=datetime.now(),
    )
    
    # Consume the generator
    list(sm.logs(project, service=None, follow=False, tail=tail))
    
    # Verify tail was passed
    compose.logs.assert_called_once()
    call_kwargs = compose.logs.call_args.kwargs
    assert call_kwargs.get("tail") == tail


@given(st.data())
@settings(max_examples=100)
def test_logs_with_service_filter(data):
    """
    **Feature: docker-compose-cli, Property 5: Service filtering is correct**
    **Validates: Requirements 7.1, 7.2**
    
    *For any* logs command with a service filter, only that service's logs
    SHALL be requested.
    """
    service_names = data.draw(st.lists(
        service_name_strategy(),
        min_size=2,
        max_size=5,
        unique=True
    ))
    
    target_service = data.draw(st.sampled_from(service_names))
    
    docker = MagicMock(spec=DockerClient)
    compose = MagicMock(spec=ComposeClient)
    compose.logs.return_value = iter([])
    
    sm = ServiceManager(docker, compose)
    
    services = [Service(
        name=name,
        container_id=f"abc{i}",
        image="nginx",
        status=ServiceStatus.RUNNING,
        ports=[],
        health=None,
        uptime=None,
    ) for i, name in enumerate(service_names)]
    
    project = Project(
        name="test-project",
        compose_file=Path("/test/compose.yaml"),
        working_dir=Path("/test"),
        services=services,
        status=ProjectHealth.HEALTHY,
        created_at=datetime.now(),
    )
    
    list(sm.logs(project, service=target_service, follow=False, tail=None))
    
    compose.logs.assert_called_once()
    call_kwargs = compose.logs.call_args.kwargs
    assert call_kwargs.get("services") == [target_service]


@given(st.data())
@settings(max_examples=100)
def test_logs_without_service_filter_requests_all(data):
    """
    **Feature: docker-compose-cli, Property 5: Service filtering is correct**
    **Validates: Requirements 7.1, 7.2**
    
    *For any* logs command without a service filter, logs from all services
    SHALL be requested.
    """
    service_names = data.draw(st.lists(
        service_name_strategy(),
        min_size=1,
        max_size=5,
        unique=True
    ))
    
    docker = MagicMock(spec=DockerClient)
    compose = MagicMock(spec=ComposeClient)
    compose.logs.return_value = iter([])
    
    sm = ServiceManager(docker, compose)
    
    services = [Service(
        name=name,
        container_id=f"abc{i}",
        image="nginx",
        status=ServiceStatus.RUNNING,
        ports=[],
        health=None,
        uptime=None,
    ) for i, name in enumerate(service_names)]
    
    project = Project(
        name="test-project",
        compose_file=Path("/test/compose.yaml"),
        working_dir=Path("/test"),
        services=services,
        status=ProjectHealth.HEALTHY,
        created_at=datetime.now(),
    )
    
    list(sm.logs(project, service=None, follow=False, tail=None))
    
    compose.logs.assert_called_once()
    call_kwargs = compose.logs.call_args.kwargs
    assert call_kwargs.get("services") is None
