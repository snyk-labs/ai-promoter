"""
AI Promoter Helpers Package

This package contains helper modules for different components of the AI Promoter application:
- openai: Functions for generating social media content using OpenAI
- arcade: Functions for posting to social media platforms via Arcade API
- okta: Functions for Okta SSO authentication and configuration
- utils: General utility functions used across the application
"""

# Import common helper functions to make them available at the package level
from helpers.openai import (
    generate_social_post,
    validate_post_length,
    LINKEDIN_CHAR_LIMIT,
    URL_CHAR_APPROX,
)
from helpers.prompt_templates import (
    get_platform_config,
    render_user_prompt,
    render_system_prompt,
)
from helpers.arcade import post_to_linkedin, check_auth_status

__all__ = [
    "generate_social_post",
    "validate_post_length",
    "LINKEDIN_CHAR_LIMIT",
    "URL_CHAR_APPROX",
    "get_platform_config",
    "render_user_prompt",
    "render_system_prompt",
    "post_to_linkedin",
    "check_auth_status",
]
