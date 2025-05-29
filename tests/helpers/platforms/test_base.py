"""
Tests for the base platform manager interface.
"""

import pytest
from unittest.mock import Mock
from helpers.platforms.base import BasePlatformManager


class MockPlatformManager(BasePlatformManager):
    """Mock implementation for testing BasePlatformManager."""

    def __init__(self, platform_name="test"):
        self.platform_name = platform_name

    def post_content(self, user, content: str, content_id: int):
        """Mock implementation."""
        return {
            "success": True,
            "post_id": "mock_post_123",
            "error_message": None,
            "platform_response": {"id": "mock_post_123"},
        }

    def check_authorization(self, user):
        """Mock implementation."""
        return hasattr(user, "authorized") and user.authorized

    def get_auth_url(self, redirect_uri=None):
        """Mock implementation."""
        return (
            f"https://mock-platform.com/oauth?redirect_uri={redirect_uri or 'default'}"
        )


class TestBasePlatformManager:
    """Test BasePlatformManager base class."""

    def test_abstract_methods_must_be_implemented(self):
        """Test that abstract methods must be implemented."""
        with pytest.raises(TypeError):
            # This should fail because abstract methods aren't implemented
            BasePlatformManager()

    def test_concrete_implementation_works(self):
        """Test that concrete implementation works."""
        manager = MockPlatformManager("testplatform")
        assert manager.platform_name == "testplatform"

    def test_get_platform_name_default(self):
        """Test default platform name generation."""
        manager = MockPlatformManager()
        platform_name = manager.get_platform_name()
        assert platform_name == "mockplatform"  # MockPlatformManager -> mockplatform

    def test_post_content_interface(self):
        """Test post_content interface."""
        manager = MockPlatformManager()
        user = Mock()

        result = manager.post_content(user, "Test content", 123)

        assert isinstance(result, dict)
        assert "success" in result
        assert "post_id" in result
        assert "error_message" in result
        assert "platform_response" in result

    def test_check_authorization_interface(self):
        """Test check_authorization interface."""
        manager = MockPlatformManager()

        # Test authorized user
        authorized_user = Mock()
        authorized_user.authorized = True
        assert manager.check_authorization(authorized_user) is True

        # Test unauthorized user
        unauthorized_user = Mock()
        unauthorized_user.authorized = False
        assert manager.check_authorization(unauthorized_user) is False

        # Test user without authorization attribute
        no_auth_user = Mock(spec=[])  # Mock with no attributes
        assert manager.check_authorization(no_auth_user) is False

    def test_get_auth_url_interface(self):
        """Test get_auth_url interface."""
        manager = MockPlatformManager()

        # Test with default redirect URI
        url = manager.get_auth_url()
        assert url.startswith("https://mock-platform.com/oauth")
        assert "redirect_uri=default" in url

        # Test with custom redirect URI
        custom_url = manager.get_auth_url("https://example.com/callback")
        assert "redirect_uri=https://example.com/callback" in custom_url

    def test_validate_content_default_implementation(self):
        """Test default validate_content implementation."""
        manager = MockPlatformManager()

        result = manager.validate_content("Any content")

        assert isinstance(result, dict)
        assert result["valid"] is True
        assert result["errors"] == []
        assert result["warnings"] == []

    def test_validate_content_can_be_overridden(self):
        """Test that validate_content can be overridden."""

        class CustomValidationManager(MockPlatformManager):
            def validate_content(self, content: str):
                if len(content) > 100:
                    return {
                        "valid": False,
                        "errors": ["Content too long"],
                        "warnings": [],
                    }
                return {"valid": True, "errors": [], "warnings": ["Content looks good"]}

        manager = CustomValidationManager()

        # Test valid content
        valid_result = manager.validate_content("Short content")
        assert valid_result["valid"] is True
        assert valid_result["warnings"] == ["Content looks good"]

        # Test invalid content
        invalid_result = manager.validate_content("x" * 150)
        assert invalid_result["valid"] is False
        assert invalid_result["errors"] == ["Content too long"]
