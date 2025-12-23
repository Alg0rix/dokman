"""Property-based tests for project registry operations.

**Feature: docker-compose-cli, Property 2 & 3: Registry operations**
**Validates: Requirements 10.1, 10.2**
"""

import tempfile
from datetime import datetime
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from dockman.models.project import RegisteredProject
from dockman.storage.registry import ProjectRegistry


# Custom strategies for generating valid test data
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
    parts = draw(st.lists(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=20),
        min_size=1,
        max_size=5
    ))
    return Path("/".join(parts))


@st.composite
def project_name_strategy(draw):
    """Generate a valid project name."""
    return draw(st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-",
        min_size=1,
        max_size=50
    ))


@st.composite
def registered_project_strategy(draw):
    """Generate a valid RegisteredProject instance."""
    return RegisteredProject(
        name=draw(project_name_strategy()),
        compose_file=draw(path_strategy()),
        registered_at=draw(datetime_strategy()),
        last_accessed=draw(optional_datetime_strategy()),
    )


# -----------------------------------------------------------------------------
# Property 3: Registry round-trip preserves data
# -----------------------------------------------------------------------------

@given(registered_project_strategy())
@settings(max_examples=100)
def test_registry_round_trip_single_project(project: RegisteredProject):
    """
    **Feature: docker-compose-cli, Property 3: Registry round-trip preserves data**
    **Validates: Requirements 10.1**
    
    *For any* valid RegisteredProject, saving to registry and loading back
    SHALL produce an equivalent RegisteredProject with identical name,
    compose_file path, and registered_at timestamp.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "projects.json"
        registry = ProjectRegistry(config_path=config_path)
        
        # Add project to registry
        registry.add(project)
        
        # Load it back
        loaded = registry.get(project.name)
        
        assert loaded is not None
        assert loaded.name == project.name
        assert loaded.compose_file == project.compose_file
        assert loaded.registered_at == project.registered_at
        assert loaded.last_accessed == project.last_accessed


@given(st.lists(registered_project_strategy(), min_size=1, max_size=10, unique_by=lambda p: p.name))
@settings(max_examples=100)
def test_registry_round_trip_multiple_projects(projects: list[RegisteredProject]):
    """
    **Feature: docker-compose-cli, Property 3: Registry round-trip preserves data**
    **Validates: Requirements 10.1**
    
    *For any* list of valid RegisteredProjects with unique names, saving all
    to registry and loading back SHALL preserve all projects with identical data.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "projects.json"
        registry = ProjectRegistry(config_path=config_path)
        
        # Add all projects
        for project in projects:
            registry.add(project)
        
        # Load all back
        loaded_projects = registry.list_all()
        
        assert len(loaded_projects) == len(projects)
        
        # Create lookup by name
        loaded_by_name = {p.name: p for p in loaded_projects}
        
        for original in projects:
            loaded = loaded_by_name.get(original.name)
            assert loaded is not None
            assert loaded.name == original.name
            assert loaded.compose_file == original.compose_file
            assert loaded.registered_at == original.registered_at
            assert loaded.last_accessed == original.last_accessed


# -----------------------------------------------------------------------------
# Property 2: Registry operations are idempotent and consistent
# -----------------------------------------------------------------------------

@given(st.data())
@settings(max_examples=100)
def test_registry_add_idempotent(data):
    """
    **Feature: docker-compose-cli, Property 2: Registry operations are idempotent and consistent**
    **Validates: Requirements 10.1, 10.2**
    
    *For any* RegisteredProject, adding it multiple times SHALL result in
    exactly one entry in the registry (the last one added).
    """
    project = data.draw(registered_project_strategy())
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "projects.json"
        registry = ProjectRegistry(config_path=config_path)
        
        # Add the same project multiple times
        num_adds = data.draw(st.integers(min_value=2, max_value=5))
        for _ in range(num_adds):
            registry.add(project)
        
        # Should have exactly one entry
        all_projects = registry.list_all()
        assert len(all_projects) == 1
        assert all_projects[0].name == project.name


@given(st.data())
@settings(max_examples=100)
def test_registry_remove_idempotent(data):
    """
    **Feature: docker-compose-cli, Property 2: Registry operations are idempotent and consistent**
    **Validates: Requirements 10.1, 10.2**
    
    *For any* project name, removing it multiple times SHALL succeed on first
    removal and return False on subsequent removals.
    """
    project = data.draw(registered_project_strategy())
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "projects.json"
        registry = ProjectRegistry(config_path=config_path)
        
        # Add project
        registry.add(project)
        
        # First removal should succeed
        result1 = registry.remove(project.name)
        assert result1 is True
        
        # Subsequent removals should return False
        num_removes = data.draw(st.integers(min_value=1, max_value=3))
        for _ in range(num_removes):
            result = registry.remove(project.name)
            assert result is False
        
        # Project should not exist
        assert registry.exists(project.name) is False


@given(st.data())
@settings(max_examples=100)
def test_registry_final_state_deterministic(data):
    """
    **Feature: docker-compose-cli, Property 2: Registry operations are idempotent and consistent**
    **Validates: Requirements 10.1, 10.2**
    
    *For any* sequence of register and unregister operations, the final state
    SHALL be deterministic: a project exists if and only if the last operation
    for that project name was a register operation.
    """
    # Generate a project name
    project_name = data.draw(project_name_strategy())
    
    # Generate a sequence of operations (True = add, False = remove)
    operations = data.draw(st.lists(st.booleans(), min_size=1, max_size=10))
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "projects.json"
        registry = ProjectRegistry(config_path=config_path)
        
        # Execute operations
        for is_add in operations:
            if is_add:
                project = RegisteredProject(
                    name=project_name,
                    compose_file=Path("/test/compose.yaml"),
                    registered_at=datetime.now(),
                    last_accessed=None,
                )
                registry.add(project)
            else:
                registry.remove(project_name)
        
        # Final state should match last operation
        last_was_add = operations[-1]
        assert registry.exists(project_name) == last_was_add


@given(st.data())
@settings(max_examples=100)
def test_registry_no_duplicate_names(data):
    """
    **Feature: docker-compose-cli, Property 2: Registry operations are idempotent and consistent**
    **Validates: Requirements 10.1, 10.2**
    
    *For any* sequence of operations, the registry SHALL contain no duplicate
    project names.
    """
    # Generate multiple projects, some with same names
    num_projects = data.draw(st.integers(min_value=2, max_value=10))
    projects = []
    for _ in range(num_projects):
        project = data.draw(registered_project_strategy())
        projects.append(project)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "projects.json"
        registry = ProjectRegistry(config_path=config_path)
        
        # Add all projects
        for project in projects:
            registry.add(project)
        
        # Check for duplicates
        all_projects = registry.list_all()
        names = [p.name for p in all_projects]
        
        # No duplicates
        assert len(names) == len(set(names))


@given(st.data())
@settings(max_examples=100)
def test_registry_exists_consistent_with_get(data):
    """
    **Feature: docker-compose-cli, Property 2: Registry operations are idempotent and consistent**
    **Validates: Requirements 10.1, 10.2**
    
    *For any* project name, exists() SHALL return True if and only if get()
    returns a non-None value.
    """
    project = data.draw(registered_project_strategy())
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "projects.json"
        registry = ProjectRegistry(config_path=config_path)
        
        # Before adding
        assert registry.exists(project.name) == (registry.get(project.name) is not None)
        
        # After adding
        registry.add(project)
        assert registry.exists(project.name) == (registry.get(project.name) is not None)
        
        # After removing
        registry.remove(project.name)
        assert registry.exists(project.name) == (registry.get(project.name) is not None)
