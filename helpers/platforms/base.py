"""
Base Platform Manager

This module defines the base interface that all platform managers must implement.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BasePlatformManager(ABC):
    """Base class for platform-specific operations."""

    @abstractmethod
    def post_content(self, user, content: str, content_id: int) -> Dict[str, Any]:
        """
        Post content to the platform.

        Args:
            user: User object with platform authorization
            content: The content to post
            content_id: ID of the content item being posted

        Returns:
            Dict containing posting result with keys:
            - success: bool
            - post_id: str (if successful)
            - error_message: str (if failed)
            - platform_response: dict (raw platform response)
        """
        pass

    @abstractmethod
    def check_authorization(self, user) -> bool:
        """
        Check if user is authorized for this platform.

        Args:
            user: User object to check authorization for

        Returns:
            bool: True if user is authorized, False otherwise
        """
        pass

    @abstractmethod
    def get_auth_url(self, redirect_uri: Optional[str] = None) -> str:
        """
        Get OAuth authorization URL for this platform.

        Args:
            redirect_uri: Optional redirect URI for OAuth flow

        Returns:
            str: Authorization URL
        """
        pass

    def get_platform_name(self) -> str:
        """Get the name of this platform."""
        return self.__class__.__name__.replace("Manager", "").lower()

    def validate_content(self, content: str) -> Dict[str, Any]:
        """
        Validate content for platform-specific requirements.

        Args:
            content: Content to validate

        Returns:
            Dict with validation result:
            - valid: bool
            - errors: list of error messages
            - warnings: list of warning messages
        """
        return {"valid": True, "errors": [], "warnings": []}
