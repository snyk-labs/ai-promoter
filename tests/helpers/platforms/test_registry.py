"""
Tests for the platform registry system.
"""

import pytest
from unittest.mock import Mock
from helpers.platforms import (
    get_platform_manager,
    get_supported_platforms,
    is_platform_supported,
    PLATFORM_MANAGERS,
)
from helpers.platforms.base import BasePlatformManager
from helpers.platforms.linkedin import LinkedInManager
from helpers.content_generator import Platform


class TestPlatformRegistry:
    """Test platform registry functionality."""

    def test_platform_managers_registry(self):
        """Test that PLATFORM_MANAGERS registry is properly configured."""
        assert isinstance(PLATFORM_MANAGERS, dict)
        assert Platform.LINKEDIN in PLATFORM_MANAGERS
        assert PLATFORM_MANAGERS[Platform.LINKEDIN] == LinkedInManager

    def test_get_platform_manager_linkedin(self):
        """Test getting LinkedIn platform manager."""
        manager = get_platform_manager(Platform.LINKEDIN)
        assert isinstance(manager, LinkedInManager)
        assert isinstance(manager, BasePlatformManager)

    def test_get_platform_manager_unsupported(self):
        """Test getting manager for unsupported platform."""
        with pytest.raises(
            ValueError, match="No manager available for platform: twitter"
        ):
            get_platform_manager(Platform.TWITTER)

        with pytest.raises(
            ValueError, match="No manager available for platform: facebook"
        ):
            get_platform_manager(Platform.FACEBOOK)

    def test_get_supported_platforms(self):
        """Test getting list of supported platforms."""
        supported = get_supported_platforms()
        assert isinstance(supported, list)
        assert Platform.LINKEDIN in supported
        assert Platform.TWITTER not in supported  # Not implemented yet
        assert Platform.FACEBOOK not in supported  # Not implemented yet

    def test_is_platform_supported(self):
        """Test checking if platform is supported."""
        assert is_platform_supported(Platform.LINKEDIN) is True
        assert is_platform_supported(Platform.TWITTER) is False
        assert is_platform_supported(Platform.FACEBOOK) is False
        assert is_platform_supported(Platform.INSTAGRAM) is False
        assert is_platform_supported(Platform.TIKTOK) is False

    def test_registry_extensibility(self):
        """Test that registry can be extended (conceptually)."""
        # This test demonstrates how the registry would work with new platforms

        class MockTwitterManager(BasePlatformManager):
            def post_content(self, user, content: str, content_id: int):
                return {"success": True, "post_id": "twitter_123"}

            def check_authorization(self, user):
                return True

            def get_auth_url(self, redirect_uri=None):
                return "https://twitter.com/oauth"

        # Temporarily add to registry for testing
        original_registry = PLATFORM_MANAGERS.copy()
        try:
            PLATFORM_MANAGERS[Platform.TWITTER] = MockTwitterManager

            # Test that it now works
            assert is_platform_supported(Platform.TWITTER) is True
            manager = get_platform_manager(Platform.TWITTER)
            assert isinstance(manager, MockTwitterManager)

            supported = get_supported_platforms()
            assert Platform.TWITTER in supported

        finally:
            # Restore original registry
            PLATFORM_MANAGERS.clear()
            PLATFORM_MANAGERS.update(original_registry)

    def test_manager_instances_are_new(self):
        """Test that get_platform_manager returns new instances each time."""
        manager1 = get_platform_manager(Platform.LINKEDIN)
        manager2 = get_platform_manager(Platform.LINKEDIN)

        # Should return a new instance each time
        assert isinstance(manager1, LinkedInManager)
        assert isinstance(manager2, LinkedInManager)
        assert manager1 is not manager2  # Different instances


class TestPlatformManagerInterface:
    """Test that platform managers conform to the expected interface."""

    def test_linkedin_manager_interface(self):
        """Test that LinkedInManager implements the required interface."""
        manager = get_platform_manager(Platform.LINKEDIN)

        # Test required methods exist
        assert hasattr(manager, "post_content")
        assert hasattr(manager, "check_authorization")
        assert hasattr(manager, "get_auth_url")
        assert hasattr(manager, "get_platform_name")
        assert hasattr(manager, "validate_content")

        # Test methods are callable
        assert callable(manager.post_content)
        assert callable(manager.check_authorization)
        assert callable(manager.get_auth_url)
        assert callable(manager.get_platform_name)
        assert callable(manager.validate_content)

    def test_linkedin_manager_method_signatures(self):
        """Test that LinkedInManager methods have correct signatures."""
        manager = get_platform_manager(Platform.LINKEDIN)

        # Test method signatures by calling with mocks
        user = Mock()

        # These should not raise TypeError for wrong number of arguments
        try:
            manager.check_authorization(user)
            manager.get_auth_url()
            manager.get_auth_url("https://example.com/callback")
            manager.validate_content("test content")
            manager.get_platform_name()
            # post_content requires actual implementation details, so we skip it here
        except (ValueError, AttributeError, Exception) as e:
            # These are expected for mock objects, but TypeError would
            # indicate signature issues
            if isinstance(e, TypeError):
                pytest.fail(f"Method signature error: {e}")


class TestRegistryErrorHandling:
    """Test error handling in the registry system."""

    def test_get_platform_manager_with_invalid_platform(self):
        """Test error handling with invalid platform objects."""

        # Test with None
        with pytest.raises((ValueError, AttributeError)):
            get_platform_manager(None)

        # Test with string instead of Platform enum
        with pytest.raises((ValueError, AttributeError, KeyError)):
            get_platform_manager("linkedin")

    def test_is_platform_supported_with_invalid_platform(self):
        """Test is_platform_supported with invalid inputs."""

        # Test with None
        try:
            result = is_platform_supported(None)
            assert result is False
        except (ValueError, AttributeError, KeyError):
            # Any of these exceptions are acceptable for invalid input
            pass

        # Test with string
        try:
            result = is_platform_supported("linkedin")
            assert result is False
        except (ValueError, AttributeError, KeyError):
            # Any of these exceptions are acceptable for invalid input
            pass

    def test_get_platform_manager_with_unsupported_platform(self):
        """Test error handling with unsupported platform."""
        with pytest.raises(AttributeError, match="'str' object has no attribute"):
            get_platform_manager("unsupported_platform")
