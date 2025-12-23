"""Property-based tests for output formatting operations.

**Feature: docker-compose-cli, Property 8 & 9: Secret masking and export format**
**Validates: Requirements 18.2, 18.3**
"""

import re

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from dockman.cli.formatter import OutputFormatter, MASK, SENSITIVE_PATTERNS


# Custom strategies
@st.composite
def env_key_strategy(draw):
    """Generate a valid environment variable key (must start with letter or underscore)."""
    # First character must be letter or underscore
    first_char = draw(st.text(
        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ_",
        min_size=1,
        max_size=1
    ))
    # Rest can include numbers
    rest = draw(st.text(
        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_",
        min_size=0,
        max_size=49
    ))
    return first_char + rest


@st.composite
def env_value_strategy(draw):
    """Generate a valid environment variable value (no newlines for shell compatibility)."""
    # Exclude newlines as they break shell export format
    return draw(st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789 !@#$%^&*()-_+=[]{}|;:',.<>?/\\\"'`~",
        min_size=0,
        max_size=200
    ))


@st.composite
def sensitive_key_strategy(draw):
    """Generate a key that matches sensitive patterns."""
    base = draw(st.sampled_from([
        "PASSWORD", "SECRET", "KEY", "TOKEN", "CREDENTIAL", "API_KEY"
    ]))
    prefix = draw(st.text(
        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ_",
        min_size=0,
        max_size=10
    ))
    suffix = draw(st.text(
        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ_",
        min_size=0,
        max_size=10
    ))
    return f"{prefix}{base}{suffix}"


@st.composite
def non_sensitive_key_strategy(draw):
    """Generate a key that does NOT match sensitive patterns."""
    # Use words that don't contain PASSWORD, SECRET, KEY, TOKEN, CREDENTIAL, API_KEY
    safe_words = ["HOST", "PORT", "NAME", "USER", "PATH", "URL", "DEBUG", "LOG", "MODE"]
    base = draw(st.sampled_from(safe_words))
    prefix = draw(st.text(
        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ_",
        min_size=0,
        max_size=5
    ))
    suffix = draw(st.text(
        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ_",
        min_size=0,
        max_size=5
    ))
    key = f"{prefix}{base}{suffix}"
    
    # Ensure it doesn't accidentally match sensitive patterns
    for pattern in SENSITIVE_PATTERNS:
        assume(not pattern.match(key))
    
    return key


@st.composite
def env_vars_strategy(draw):
    """Generate a dictionary of environment variables."""
    keys = draw(st.lists(
        env_key_strategy(),
        min_size=1,
        max_size=10,
        unique=True
    ))
    values = [draw(env_value_strategy()) for _ in keys]
    return dict(zip(keys, values))


# -----------------------------------------------------------------------------
# Property 8: Secret masking is applied correctly
# -----------------------------------------------------------------------------

@given(sensitive_key_strategy(), env_value_strategy())
@settings(max_examples=100)
def test_sensitive_key_masked_without_show_secrets(key: str, value: str):
    """
    **Feature: docker-compose-cli, Property 8: Secret masking is applied correctly**
    **Validates: Requirements 18.2**
    
    *For any* environment variable with a key matching sensitive patterns,
    the displayed value SHALL be masked unless --show-secrets flag is provided.
    """
    formatter = OutputFormatter()
    
    # Without show_secrets, value should be masked
    masked = formatter.mask_value(key, value, show_secrets=False)
    assert masked == MASK


@given(sensitive_key_strategy(), env_value_strategy())
@settings(max_examples=100)
def test_sensitive_key_shown_with_show_secrets(key: str, value: str):
    """
    **Feature: docker-compose-cli, Property 8: Secret masking is applied correctly**
    **Validates: Requirements 18.2**
    
    *For any* environment variable with a key matching sensitive patterns,
    the displayed value SHALL be shown when --show-secrets flag is provided.
    """
    formatter = OutputFormatter()
    
    # With show_secrets, value should be shown
    shown = formatter.mask_value(key, value, show_secrets=True)
    assert shown == value


@given(non_sensitive_key_strategy(), env_value_strategy())
@settings(max_examples=100)
def test_non_sensitive_key_not_masked(key: str, value: str):
    """
    **Feature: docker-compose-cli, Property 8: Secret masking is applied correctly**
    **Validates: Requirements 18.2**
    
    *For any* environment variable with a key NOT matching sensitive patterns,
    the displayed value SHALL NOT be masked regardless of --show-secrets flag.
    """
    formatter = OutputFormatter()
    
    # Non-sensitive keys should never be masked
    masked = formatter.mask_value(key, value, show_secrets=False)
    assert masked == value
    
    shown = formatter.mask_value(key, value, show_secrets=True)
    assert shown == value


@given(st.data())
@settings(max_examples=100)
def test_mask_env_vars_masks_all_sensitive(data):
    """
    **Feature: docker-compose-cli, Property 8: Secret masking is applied correctly**
    **Validates: Requirements 18.2**
    
    *For any* dictionary of environment variables, all sensitive keys SHALL
    be masked when show_secrets is False.
    """
    # Generate mix of sensitive and non-sensitive keys
    num_sensitive = data.draw(st.integers(min_value=1, max_value=5))
    num_non_sensitive = data.draw(st.integers(min_value=0, max_value=5))
    
    env_vars = {}
    sensitive_keys = set()
    
    for _ in range(num_sensitive):
        key = data.draw(sensitive_key_strategy())
        value = data.draw(env_value_strategy())
        env_vars[key] = value
        sensitive_keys.add(key)
    
    for _ in range(num_non_sensitive):
        key = data.draw(non_sensitive_key_strategy())
        # Ensure no collision with sensitive keys
        assume(key not in env_vars)
        value = data.draw(env_value_strategy())
        env_vars[key] = value
    
    formatter = OutputFormatter()
    masked = formatter.mask_env_vars(env_vars, show_secrets=False)
    
    # All sensitive keys should be masked
    for key in sensitive_keys:
        assert masked[key] == MASK
    
    # Non-sensitive keys should not be masked
    for key in env_vars:
        if key not in sensitive_keys:
            assert masked[key] == env_vars[key]


@given(st.sampled_from(["PASSWORD", "DB_PASSWORD", "MY_SECRET", "API_KEY", "AUTH_TOKEN", "USER_CREDENTIAL"]))
@settings(max_examples=100)
def test_common_sensitive_patterns_detected(key: str):
    """
    **Feature: docker-compose-cli, Property 8: Secret masking is applied correctly**
    **Validates: Requirements 18.2**
    
    Common sensitive key patterns SHALL be detected and masked.
    """
    formatter = OutputFormatter()
    
    assert formatter.is_sensitive_key(key) is True


# -----------------------------------------------------------------------------
# Property 9: Export format is valid shell syntax
# -----------------------------------------------------------------------------

@given(env_vars_strategy())
@settings(max_examples=100)
def test_export_format_valid_shell_syntax(env_vars: dict[str, str]):
    """
    **Feature: docker-compose-cli, Property 9: Export format is valid shell syntax**
    **Validates: Requirements 18.3**
    
    *For any* set of environment variables, the --export output SHALL produce
    valid shell export statements.
    """
    formatter = OutputFormatter()
    
    export_output = formatter.format_export(env_vars)
    
    # Each line should match export KEY="VALUE" pattern
    lines = export_output.split("\n") if export_output else []
    
    for line in lines:
        if line.strip():
            # Should start with "export "
            assert line.startswith("export "), f"Line doesn't start with 'export ': {line}"
            
            # Should have KEY="VALUE" format
            rest = line[7:]  # Remove "export "
            assert "=" in rest, f"Line missing '=': {line}"
            
            key_part, value_part = rest.split("=", 1)
            
            # Key should be valid identifier
            assert re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', key_part), f"Invalid key: {key_part}"
            
            # Value should be quoted
            assert value_part.startswith('"') and value_part.endswith('"'), f"Value not quoted: {value_part}"


@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789 !@#%^&*()-+=[]{}|;:',.<>?/", min_size=1, max_size=100))
@settings(max_examples=100)
def test_export_escapes_special_characters(value: str):
    """
    **Feature: docker-compose-cli, Property 9: Export format is valid shell syntax**
    **Validates: Requirements 18.3**
    
    *For any* value containing special characters (excluding newlines),
    the export format SHALL properly escape them.
    """
    formatter = OutputFormatter()
    
    env_vars = {"TEST_VAR": value}
    export_output = formatter.format_export(env_vars)
    
    # Should produce valid output
    assert 'export TEST_VAR="' in export_output
    
    # The escaped value should be between quotes
    match = re.search(r'export TEST_VAR="(.*)"$', export_output, re.DOTALL)
    assert match is not None


@given(st.sampled_from([
    'simple',
    'with spaces',
    'with"quotes',
    'with$dollar',
    'with`backtick`',
    'with\\backslash',
    'complex"$`\\all',
]))
@settings(max_examples=100)
def test_export_handles_problematic_values(value: str):
    """
    **Feature: docker-compose-cli, Property 9: Export format is valid shell syntax**
    **Validates: Requirements 18.3**
    
    Specific problematic values SHALL be properly escaped in export format.
    """
    formatter = OutputFormatter()
    
    env_vars = {"TEST_VAR": value}
    export_output = formatter.format_export(env_vars)
    
    # Should produce valid output without syntax errors
    assert export_output.startswith('export TEST_VAR="')
    assert export_output.endswith('"')
    
    # Verify escaping
    escaped_value = formatter.escape_shell_value(value)
    assert f'export TEST_VAR="{escaped_value}"' == export_output


@given(env_vars_strategy())
@settings(max_examples=100)
def test_export_sorted_alphabetically(env_vars: dict[str, str]):
    """
    **Feature: docker-compose-cli, Property 9: Export format is valid shell syntax**
    **Validates: Requirements 18.3**
    
    *For any* set of environment variables, the export output SHALL be
    sorted alphabetically by key.
    """
    formatter = OutputFormatter()
    
    export_output = formatter.format_export(env_vars)
    lines = [line for line in export_output.split("\n") if line.strip()]
    
    # Extract keys from each line
    keys = []
    for line in lines:
        if line.startswith("export "):
            rest = line[7:]
            key = rest.split("=", 1)[0]
            keys.append(key)
    
    # Keys should be sorted
    assert keys == sorted(keys)


@given(st.data())
@settings(max_examples=100)
def test_escape_shell_value_handles_all_special_chars(data):
    """
    **Feature: docker-compose-cli, Property 9: Export format is valid shell syntax**
    **Validates: Requirements 18.3**
    
    The escape function SHALL handle all shell special characters.
    """
    # Generate a value with various special characters
    special_chars = data.draw(st.text(
        alphabet='"\\$`',
        min_size=0,
        max_size=10
    ))
    normal_chars = data.draw(st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789 ",
        min_size=0,
        max_size=20
    ))
    
    value = normal_chars + special_chars
    
    formatter = OutputFormatter()
    escaped = formatter.escape_shell_value(value)
    
    # Backslashes should be escaped
    assert "\\\\" in escaped or "\\" not in value
    
    # Double quotes should be escaped
    assert '\\"' in escaped or '"' not in value
    
    # Dollar signs should be escaped
    assert "\\$" in escaped or "$" not in value
    
    # Backticks should be escaped
    assert "\\`" in escaped or "`" not in value
