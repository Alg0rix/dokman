"""Tests for version checker service."""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dokman.services.version_checker import UpdateInfo, VersionChecker


class TestUpdateInfo:
    """Tests for UpdateInfo dataclass."""

    def test_upgrade_command_returns_uv_command(self):
        """Test that upgrade_command returns the uv tool upgrade command."""
        info = UpdateInfo(current_version="0.1.0", latest_version="0.2.0")
        assert info.upgrade_command == "uv tool upgrade dokman --no-cache"

    def test_stores_versions(self):
        """Test that UpdateInfo stores version information."""
        info = UpdateInfo(current_version="1.0.0", latest_version="2.0.0")
        assert info.current_version == "1.0.0"
        assert info.latest_version == "2.0.0"


class TestVersionChecker:
    """Tests for VersionChecker class."""

    def test_get_current_version_returns_dokman_version(self):
        """Test that get_current_version returns the package version."""
        checker = VersionChecker()
        version = checker.get_current_version()
        assert isinstance(version, str)
        assert len(version) > 0

    def test_compare_versions_newer(self):
        """Test version comparison when latest is newer."""
        checker = VersionChecker()
        assert checker._compare_versions("0.1.0", "0.2.0") is True
        assert checker._compare_versions("0.1.0", "1.0.0") is True
        assert checker._compare_versions("0.1.0", "0.1.1") is True
        assert checker._compare_versions("1.2.3", "1.2.4") is True
        assert checker._compare_versions("1.2.3", "1.3.0") is True
        assert checker._compare_versions("1.2.3", "2.0.0") is True

    def test_compare_versions_same(self):
        """Test version comparison when versions are equal."""
        checker = VersionChecker()
        assert checker._compare_versions("0.1.0", "0.1.0") is False
        assert checker._compare_versions("1.0.0", "1.0.0") is False

    def test_compare_versions_older(self):
        """Test version comparison when latest is older."""
        checker = VersionChecker()
        assert checker._compare_versions("0.2.0", "0.1.0") is False
        assert checker._compare_versions("1.0.0", "0.9.0") is False
        assert checker._compare_versions("2.0.0", "1.9.9") is False

    def test_compare_versions_handles_different_lengths(self):
        """Test version comparison with different version lengths."""
        checker = VersionChecker()
        assert checker._compare_versions("1.0", "1.0.1") is True
        assert checker._compare_versions("1.0.0", "1.1") is True

    def test_get_latest_version_handles_network_error(self):
        """Test that get_latest_version returns None on network error."""
        checker = VersionChecker(timeout=0.001)  # Very short timeout
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = TimeoutError("Connection timed out")
            result = checker.get_latest_version()
            assert result is None

    def test_get_latest_version_handles_invalid_json(self):
        """Test that get_latest_version returns None on invalid JSON."""
        checker = VersionChecker()
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b"not valid json"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response
            result = checker.get_latest_version()
            assert result is None

    def test_get_latest_version_extracts_version_from_pypi(self):
        """Test that get_latest_version extracts version from PyPI response."""
        checker = VersionChecker()
        mock_pypi_response = json.dumps({
            "info": {"version": "1.2.3"},
            "releases": {}
        }).encode()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = mock_pypi_response
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response
            result = checker.get_latest_version()
            assert result == "1.2.3"

    def test_check_for_update_returns_none_when_current(self):
        """Test that check_for_update returns None when already on latest."""
        checker = VersionChecker()
        with patch.object(checker, "get_current_version", return_value="1.0.0"):
            with patch.object(checker, "get_latest_version", return_value="1.0.0"):
                result = checker.check_for_update(use_cache=False)
                assert result is None

    def test_check_for_update_returns_info_when_outdated(self):
        """Test that check_for_update returns UpdateInfo when outdated."""
        checker = VersionChecker()
        with patch.object(checker, "get_current_version", return_value="0.1.0"):
            with patch.object(checker, "get_latest_version", return_value="1.0.0"):
                result = checker.check_for_update(use_cache=False)
                assert result is not None
                assert isinstance(result, UpdateInfo)
                assert result.current_version == "0.1.0"
                assert result.latest_version == "1.0.0"

    def test_check_for_update_returns_none_on_network_error(self):
        """Test that check_for_update returns None on network error."""
        checker = VersionChecker()
        with patch.object(checker, "get_latest_version", return_value=None):
            result = checker.check_for_update(use_cache=False)
            assert result is None


class TestVersionCheckerCache:
    """Tests for version checker caching functionality."""

    def test_cache_is_saved_and_loaded(self):
        """Test that version cache is saved and loaded correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / ".dokman"
            cache_file = cache_dir / "version_cache.json"

            checker = VersionChecker()

            # Patch the cache file location
            with patch("dokman.services.version_checker.CACHE_DIR", cache_dir):
                with patch("dokman.services.version_checker.CACHE_FILE", cache_file):
                    # Save cache
                    checker._save_cache("2.0.0")

                    # Verify file was created
                    assert cache_file.exists()

                    # Load cache
                    cache = checker._load_cache()
                    assert cache is not None
                    assert cache["latest_version"] == "2.0.0"

    def test_expired_cache_returns_none(self):
        """Test that expired cache is not used."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / ".dokman"
            cache_file = cache_dir / "version_cache.json"
            cache_dir.mkdir(parents=True)

            # Create expired cache
            expired_cache = {
                "timestamp": time.time() - 100000,  # Way in the past
                "latest_version": "2.0.0"
            }
            with open(cache_file, "w") as f:
                json.dump(expired_cache, f)

            checker = VersionChecker()

            with patch("dokman.services.version_checker.CACHE_FILE", cache_file):
                cache = checker._load_cache()
                assert cache is None

    def test_check_for_update_uses_cache(self):
        """Test that check_for_update uses cached result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / ".dokman"
            cache_file = cache_dir / "version_cache.json"
            cache_dir.mkdir(parents=True)

            # Create valid cache with newer version
            valid_cache = {
                "timestamp": time.time(),
                "latest_version": "9.9.9"
            }
            with open(cache_file, "w") as f:
                json.dump(valid_cache, f)

            checker = VersionChecker()

            with patch("dokman.services.version_checker.CACHE_FILE", cache_file):
                with patch.object(checker, "get_current_version", return_value="0.1.0"):
                    # Should not call get_latest_version due to cache
                    with patch.object(checker, "get_latest_version") as mock_fetch:
                        result = checker.check_for_update(use_cache=True)
                        mock_fetch.assert_not_called()
                        assert result is not None
                        assert result.latest_version == "9.9.9"
