"""
Platform Managers

This module provides platform-specific managers for social media operations
like posting, authorization, and platform-specific features.
"""

from .base import BasePlatformManager
from .linkedin import LinkedInManager

# Future platform managers
# from .twitter import TwitterManager
# from .facebook import FacebookManager

from helpers.content_generator import Platform

# Registry of platform managers
PLATFORM_MANAGERS = {
    Platform.LINKEDIN: LinkedInManager,
    # Platform.TWITTER: TwitterManager,    # Future
    # Platform.FACEBOOK: FacebookManager,  # Future
}


def get_platform_manager(platform: Platform) -> BasePlatformManager:
    """Get the appropriate platform manager for the given platform."""
    if platform not in PLATFORM_MANAGERS:
        raise ValueError(f"No manager available for platform: {platform.value}")

    return PLATFORM_MANAGERS[platform]()


def get_supported_platforms() -> list[Platform]:
    """Get list of platforms with available managers."""
    return list(PLATFORM_MANAGERS.keys())


def is_platform_supported(platform: Platform) -> bool:
    """Check if a platform has an available manager."""
    return platform in PLATFORM_MANAGERS
