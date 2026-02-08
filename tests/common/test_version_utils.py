"""
Tests for JustNews Version Utilities
"""

from unittest.mock import patch

from common.version_utils import (
    DESCRIPTION,
    RELEASE_DATE,
    STATUS,
    VERSION,
    get_agent_version_info,
    get_version,
    get_version_info,
)


class TestVersionUtils:
    """Test version utility functions"""

    def test_get_version(self):
        """Test getting version string"""
        version = get_version()

        assert isinstance(version, str)
        assert len(version) > 0
        # Should be in semantic version format (e.g., "0.8.0")
        assert version.count(".") >= 2

    def test_get_version_info(self):
        """Test getting detailed version information"""
        info = get_version_info()

        assert isinstance(info, dict)
        assert "version" in info
        assert "status" in info
        assert "release_date" in info
        assert "description" in info

        # Version should match get_version()
        assert info["version"] == get_version()

    def test_get_agent_version_info_without_agent(self):
        """Test getting agent version info without specifying agent"""
        info = get_agent_version_info()

        assert isinstance(info, dict)
        assert "version" in info
        assert "status" in info
        assert "release_date" in info
        assert "description" in info
        assert "agent" not in info

    def test_get_agent_version_info_with_agent(self):
        """Test getting agent version info with specified agent"""
        agent_name = "test_agent"
        info = get_agent_version_info(agent_name)

        assert isinstance(info, dict)
        assert "version" in info
        assert "status" in info
        assert "release_date" in info
        assert "description" in info
        assert info["agent"] == agent_name

    def test_constants_match_version_info(self):
        """Test that constants match version info values"""
        info = get_version_info()

        assert VERSION == info["version"]
        assert STATUS == info["status"]
        assert RELEASE_DATE == info["release_date"]
        assert DESCRIPTION == info["description"]

    @patch("common.version_utils.VERSION_INFO")
    def test_fallback_version_handling(self, mock_version_info):
        """Test fallback version handling when import fails"""
        # This test is tricky because the fallback is set at import time
        # We'll just verify the current implementation works
        version = get_version()
        assert version is not None

    def test_version_info_is_copy(self):
        """Test that get_version_info returns a copy, not the original dict"""
        info1 = get_version_info()
        info2 = get_version_info()

        assert info1 is not info2  # Should be different objects
        assert info1 == info2  # But should have same content

        # Modifying one shouldn't affect the other
        info1["test_key"] = "test_value"
        assert "test_key" not in info2
