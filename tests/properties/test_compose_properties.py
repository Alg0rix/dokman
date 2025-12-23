"""Property-based tests for compose client operations.

**Feature: docker-compose-cli, Property 6 & 10: Compose command construction and flag propagation**
**Validates: Requirements 3.1, 4.2, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4, 9.2, 12.1, 13.1, 13.4, 15.2, 18.2, 18.3**
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from dokman.clients.compose_client import ComposeClient


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
def service_list_strategy(draw):
    """Generate a list of service names."""
    return draw(st.lists(
        service_name_strategy(),
        min_size=0,
        max_size=5,
        unique=True
    ))


# -----------------------------------------------------------------------------
# Property 10: Compose command construction is correct
# -----------------------------------------------------------------------------

@given(service_list_strategy())
@settings(max_examples=100)
def test_compose_up_command_construction(services: list[str]):
    """
    **Feature: docker-compose-cli, Property 10: Compose command construction is correct**
    **Validates: Requirements 8.1, 8.2**
    
    *For any* list of services, the up command SHALL be constructed with
    the correct arguments and executed in the correct working directory.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        
        # Create a mock compose file
        compose_file = project_dir / "compose.yaml"
        compose_file.write_text("version: '3'\nservices:\n  test:\n    image: nginx\n")
        
        client = ComposeClient()
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            
            services_arg = services if services else None
            client.up(project_dir, services=services_arg, detach=True)
            
            # Verify command was called
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            
            # Verify working directory
            assert call_args.kwargs.get("cwd") == project_dir
            
            # Verify command structure
            cmd = call_args.args[0]
            assert cmd[0:2] == ["docker", "compose"]
            assert "up" in cmd
            assert "-d" in cmd  # detach flag
            
            # Verify services are included if provided
            if services:
                for service in services:
                    assert service in cmd


@given(st.booleans())
@settings(max_examples=100)
def test_compose_down_volumes_flag(remove_volumes: bool):
    """
    **Feature: docker-compose-cli, Property 10: Compose command construction is correct**
    **Validates: Requirements 8.3, 8.4**
    
    *For any* down command, the --volumes flag SHALL be included if and only if
    remove_volumes is True.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        
        # Create a mock compose file
        compose_file = project_dir / "compose.yaml"
        compose_file.write_text("version: '3'\nservices:\n  test:\n    image: nginx\n")
        
        client = ComposeClient()
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            
            client.down(project_dir, volumes=remove_volumes)
            
            mock_run.assert_called_once()
            cmd = mock_run.call_args.args[0]
            
            assert "down" in cmd
            
            if remove_volumes:
                assert "-v" in cmd
            else:
                assert "-v" not in cmd


@given(service_list_strategy())
@settings(max_examples=100)
def test_compose_start_command_construction(services: list[str]):
    """
    **Feature: docker-compose-cli, Property 10: Compose command construction is correct**
    **Validates: Requirements 3.1, 8.1**
    
    *For any* list of services, the start command SHALL include those services
    in the command arguments.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        
        compose_file = project_dir / "compose.yaml"
        compose_file.write_text("version: '3'\nservices:\n  test:\n    image: nginx\n")
        
        client = ComposeClient()
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            
            services_arg = services if services else None
            client.start(project_dir, services=services_arg)
            
            mock_run.assert_called_once()
            cmd = mock_run.call_args.args[0]
            
            assert "start" in cmd
            
            if services:
                for service in services:
                    assert service in cmd


@given(service_list_strategy())
@settings(max_examples=100)
def test_compose_stop_command_construction(services: list[str]):
    """
    **Feature: docker-compose-cli, Property 10: Compose command construction is correct**
    **Validates: Requirements 8.2**
    
    *For any* list of services, the stop command SHALL include those services
    in the command arguments.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        
        compose_file = project_dir / "compose.yaml"
        compose_file.write_text("version: '3'\nservices:\n  test:\n    image: nginx\n")
        
        client = ComposeClient()
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            
            services_arg = services if services else None
            client.stop(project_dir, services=services_arg)
            
            mock_run.assert_called_once()
            cmd = mock_run.call_args.args[0]
            
            assert "stop" in cmd
            
            if services:
                for service in services:
                    assert service in cmd


@given(service_list_strategy())
@settings(max_examples=100)
def test_compose_restart_command_construction(services: list[str]):
    """
    **Feature: docker-compose-cli, Property 10: Compose command construction is correct**
    **Validates: Requirements 3.1**
    
    *For any* list of services, the restart command SHALL include those services
    in the command arguments.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        
        compose_file = project_dir / "compose.yaml"
        compose_file.write_text("version: '3'\nservices:\n  test:\n    image: nginx\n")
        
        client = ComposeClient()
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            
            services_arg = services if services else None
            client.restart(project_dir, services=services_arg)
            
            mock_run.assert_called_once()
            cmd = mock_run.call_args.args[0]
            
            assert "restart" in cmd
            
            if services:
                for service in services:
                    assert service in cmd


@given(service_list_strategy())
@settings(max_examples=100)
def test_compose_pull_command_construction(services: list[str]):
    """
    **Feature: docker-compose-cli, Property 10: Compose command construction is correct**
    **Validates: Requirements 12.1**
    
    *For any* list of services, the pull command SHALL include those services
    in the command arguments.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        
        compose_file = project_dir / "compose.yaml"
        compose_file.write_text("version: '3'\nservices:\n  test:\n    image: nginx\n")
        
        client = ComposeClient()
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            
            services_arg = services if services else None
            client.pull(project_dir, services=services_arg)
            
            mock_run.assert_called_once()
            cmd = mock_run.call_args.args[0]
            
            assert "pull" in cmd
            
            if services:
                for service in services:
                    assert service in cmd


@given(service_list_strategy(), st.booleans())
@settings(max_examples=100)
def test_compose_build_command_construction(services: list[str], no_cache: bool):
    """
    **Feature: docker-compose-cli, Property 10: Compose command construction is correct**
    **Validates: Requirements 13.1, 13.4**
    
    *For any* list of services and no_cache flag, the build command SHALL
    include those services and the --no-cache flag appropriately.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        
        compose_file = project_dir / "compose.yaml"
        compose_file.write_text("version: '3'\nservices:\n  test:\n    image: nginx\n")
        
        client = ComposeClient()
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            
            services_arg = services if services else None
            client.build(project_dir, services=services_arg, no_cache=no_cache)
            
            mock_run.assert_called_once()
            cmd = mock_run.call_args.args[0]
            
            assert "build" in cmd
            
            if no_cache:
                assert "--no-cache" in cmd
            else:
                assert "--no-cache" not in cmd
            
            if services:
                for service in services:
                    assert service in cmd


# -----------------------------------------------------------------------------
# Property 6: Flag parameters are correctly propagated
# -----------------------------------------------------------------------------

@given(st.booleans(), st.none() | st.integers(min_value=1, max_value=1000))
@settings(max_examples=100)
def test_compose_logs_flags(follow: bool, tail: int | None):
    """
    **Feature: docker-compose-cli, Property 6: Flag parameters are correctly propagated**
    **Validates: Requirements 7.3, 7.4**
    
    *For any* logs command, the --follow and --tail flags SHALL be included
    based on the parameter values.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        
        compose_file = project_dir / "compose.yaml"
        compose_file.write_text("version: '3'\nservices:\n  test:\n    image: nginx\n")
        
        client = ComposeClient()
        
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.stdout = iter([])
            mock_process.wait.return_value = 0
            mock_popen.return_value = mock_process
            
            # Consume the generator
            list(client.logs(project_dir, follow=follow, tail=tail))
            
            mock_popen.assert_called_once()
            cmd = mock_popen.call_args.args[0]
            
            assert "logs" in cmd
            
            if follow:
                assert "-f" in cmd
            else:
                assert "-f" not in cmd
            
            if tail is not None:
                assert "--tail" in cmd
                tail_idx = cmd.index("--tail")
                assert cmd[tail_idx + 1] == str(tail)
            else:
                assert "--tail" not in cmd


@given(st.booleans())
@settings(max_examples=100)
def test_compose_exec_interactive_flag(interactive: bool):
    """
    **Feature: docker-compose-cli, Property 6: Flag parameters are correctly propagated**
    **Validates: Requirements 9.2**
    
    *For any* exec command, the -T flag (disable TTY) SHALL be included
    when interactive is False.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        
        compose_file = project_dir / "compose.yaml"
        compose_file.write_text("version: '3'\nservices:\n  test:\n    image: nginx\n")
        
        client = ComposeClient()
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            client.exec(project_dir, "test", ["echo", "hello"], interactive=interactive)
            
            mock_run.assert_called_once()
            cmd = mock_run.call_args.args[0]
            
            assert "exec" in cmd
            
            if interactive:
                assert "-T" not in cmd
            else:
                assert "-T" in cmd


@given(service_name_strategy(), st.integers(min_value=1, max_value=10))
@settings(max_examples=100)
def test_compose_scale_command_construction(service: str, replicas: int):
    """
    **Feature: docker-compose-cli, Property 10: Compose command construction is correct**
    **Validates: Requirements 11.1**
    
    *For any* service and replica count, the scale command SHALL include
    the correct --scale argument.
    """
    # Ensure service name is valid
    assume(len(service) > 0)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        
        compose_file = project_dir / "compose.yaml"
        compose_file.write_text("version: '3'\nservices:\n  test:\n    image: nginx\n")
        
        client = ComposeClient()
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            
            client.scale(project_dir, service, replicas)
            
            mock_run.assert_called_once()
            cmd = mock_run.call_args.args[0]
            
            assert "up" in cmd
            assert "-d" in cmd
            assert "--scale" in cmd
            assert f"{service}={replicas}" in cmd
            assert service in cmd
