"""Smoke test to verify the package can be imported."""

def test_import():
    """Test that the package can be imported."""
    import dokman
    assert dokman.__doc__ is not None and dokman.__doc__.startswith("Dokman")

def test_cli():
    """Test that the CLI entry point works."""
    from dokman.cli.app import app
    assert app is not None

if __name__ == "__main__":
    test_import()
    test_cli()
    print("Smoke test passed!")
