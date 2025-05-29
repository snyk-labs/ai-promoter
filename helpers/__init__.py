"""
AI Promoter Helpers Package

This package contains helper modules for different components of the AI Promoter application.
The package now uses a simplified, consolidated architecture with full backward compatibility.

Modern Architecture (Recommended):
- content_generator: Unified content generation with built-in platform support
- platforms: Platform-specific managers for social media integrations

Legacy Compatibility (Maintained):
- All legacy function names and classes continue to work unchanged
- SocialPostGenerator is now an alias for ContentGenerator
- validate_post_length is available directly from content_generator

Other Modules:
- prompts: Prompt rendering functions (updated to use new platform config)
- okta: Functions for Okta SSO authentication and configuration
"""

# New simplified architecture (primary exports)
from .content_generator import (
    ContentGenerator,
    Platform,
    PlatformConfig,
    GenerationResult,
    ContentGenerationError,
    validate_post_length,  # Legacy compatibility function
)

from .platforms import (
    get_platform_manager,
    get_supported_platforms,
    is_platform_supported,
)

# Legacy compatibility aliases
SocialPostGenerator = ContentGenerator  # Direct alias for backward compatibility

# Keep existing exports for other modules
from .prompts import render_system_prompt, render_user_prompt, get_platform_config

__all__ = [
    # Modern architecture exports (recommended for new development)
    "ContentGenerator",
    "Platform",
    "PlatformConfig",
    "GenerationResult",
    "ContentGenerationError",
    "validate_post_length",
    "get_platform_config",
    "render_user_prompt",
    "render_system_prompt",
    # Platform management
    "get_platform_manager",
    "get_supported_platforms",
    "is_platform_supported",
    # Legacy compatibility exports (maintained for backward compatibility)
    "SocialPostGenerator",  # Alias for ContentGenerator
]
