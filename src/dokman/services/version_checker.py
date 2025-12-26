"""Version checker service for Dokman.

Checks PyPI for newer versions and suggests updates to the user.
"""

import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from packaging.version import parse as parse_version, InvalidVersion

import dokman


# Cache settings (uses same config directory as project registry)
CACHE_DIR = Path.home() / ".config" / "dokman"
CACHE_FILE = CACHE_DIR / "version_cache.json"
CACHE_TTL_SECONDS = 86400  # 24 hours


@dataclass
class UpdateInfo:
    """Information about an available update."""
    
    current_version: str
    latest_version: str
    
    @property
    def upgrade_command(self) -> str:
        """Return the command to upgrade dokman."""
        return "uv tool upgrade dokman --no-cache"


class VersionChecker:
    """Check for newer versions of dokman on PyPI."""
    
    PYPI_URL = "https://pypi.org/pypi/dokman/json"
    
    def __init__(self, timeout: float = 2.0) -> None:
        """Initialize VersionChecker.
        
        Args:
            timeout: Network timeout in seconds for PyPI requests.
        """
        self.timeout = timeout
    
    def get_current_version(self) -> str:
        """Get the currently installed version of dokman."""
        return dokman.__version__
    
    def get_latest_version(self) -> Optional[str]:
        """Fetch the latest version from PyPI.
        
        Returns:
            The latest version string, or None if fetch failed.
        """
        try:
            req = urllib.request.Request(
                self.PYPI_URL,
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read().decode())
                return data.get("info", {}).get("version")
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError):
            # Network errors, invalid JSON, or timeout - fail silently
            return None
    
    def _load_cache(self) -> Optional[dict]:
        """Load version cache from disk."""
        if not CACHE_FILE.exists():
            return None
        try:
            with open(CACHE_FILE) as f:
                cache = json.load(f)
                # Check cache validity
                if time.time() - cache.get("timestamp", 0) < CACHE_TTL_SECONDS:
                    return cache
        except (json.JSONDecodeError, OSError):
            pass
        return None
    
    def _save_cache(self, latest_version: Optional[str]) -> None:
        """Save version check result to cache."""
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, "w") as f:
                json.dump({
                    "timestamp": time.time(),
                    "latest_version": latest_version,
                }, f)
        except OSError:
            # Failed to write cache - not critical
            pass
    
    def _compare_versions(self, current: str, latest: str) -> bool:
        """Check if latest version is newer than current.
        
        Uses packaging.version for proper PEP 440 version comparison.
        
        Returns:
            True if latest > current
        """
        try:
            return parse_version(latest) > parse_version(current)
        except InvalidVersion:
            return False
    
    def check_for_update(self, use_cache: bool = True) -> Optional[UpdateInfo]:
        """Check if a newer version is available.
        
        Args:
            use_cache: Whether to use cached results to avoid repeated network calls.
        
        Returns:
            UpdateInfo if update available, None otherwise.
        """
        current = self.get_current_version()
        
        # Try cache first
        if use_cache:
            cache = self._load_cache()
            if cache:
                latest = cache.get("latest_version")
                if latest and self._compare_versions(current, latest):
                    return UpdateInfo(current_version=current, latest_version=latest)
                return None
        
        # Fetch from PyPI
        latest = self.get_latest_version()
        
        # Save to cache
        if use_cache:
            self._save_cache(latest)
        
        if latest and self._compare_versions(current, latest):
            return UpdateInfo(current_version=current, latest_version=latest)
        
        return None
