"""
Unified Content Generator

This module provides a simplified, unified approach to content generation
for multiple social media platforms and AI providers.
"""

import os
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple
import google.generativeai as genai

logger = logging.getLogger(__name__)


class Platform(Enum):
    """Supported social media platforms."""

    LINKEDIN = "linkedin"
    TWITTER = "twitter"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"  # Future
    TIKTOK = "tiktok"  # Future


@dataclass
class PlatformConfig:
    """Platform-specific configuration."""

    max_length: int
    max_tokens: int
    style: str
    hashtag_style: str = ""


@dataclass
class GenerationResult:
    """Result of content generation."""

    content: Optional[str]
    success: bool
    error_message: Optional[str] = None
    attempts: int = 0
    length: int = 0


class ContentGenerationError(Exception):
    """Base exception for content generation errors."""

    pass


class ContentGenerator:
    """Unified content generator supporting multiple AI providers and platforms."""

    PLATFORM_CONFIGS = {
        Platform.LINKEDIN: PlatformConfig(
            max_length=3000,
            max_tokens=700,
            style="Professional and informative, focusing on value and insights",
        ),
        Platform.TWITTER: PlatformConfig(
            max_length=280,
            max_tokens=100,
            style="Concise and engaging, with relevant hashtags",
            hashtag_style="trending",
        ),
        Platform.FACEBOOK: PlatformConfig(
            max_length=63206,
            max_tokens=800,
            style="Conversational and engaging, encouraging discussion",
        ),
    }

    def __init__(self, ai_provider="gemini", model="gemini-1.5-pro", api_key=None):
        """Initialize the content generator."""
        self.ai_provider = ai_provider
        self.model = model
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

        if not self.api_key:
            raise ContentGenerationError("GEMINI_API_KEY environment variable not set")

        self._setup_ai_client()

    def _setup_ai_client(self):
        """Setup the AI client based on provider."""
        if self.ai_provider == "gemini":
            try:
                genai.configure(api_key=self.api_key)
            except Exception as e:
                raise ContentGenerationError(
                    f"Failed to configure Gemini client: {str(e)}"
                )
        else:
            raise ContentGenerationError(f"Unsupported AI provider: {self.ai_provider}")

    def generate_content(
        self, content_item, user, platform: Platform, **kwargs
    ) -> GenerationResult:
        """Generate content for specified platform."""
        if platform not in self.PLATFORM_CONFIGS:
            return GenerationResult(
                content=None,
                success=False,
                error_message=f"Unsupported platform: {platform.value}",
                attempts=0,
            )

        config = self.PLATFORM_CONFIGS[platform]
        max_retries = kwargs.get("max_retries", 3)

        for attempt in range(max_retries):
            try:
                prompt = self._build_prompt(content_item, user, platform, config)
                generated = self._call_ai_api(prompt, config, **kwargs)

                if self._validate_content(generated, config):
                    return GenerationResult(
                        content=generated,
                        success=True,
                        attempts=attempt + 1,
                        length=len(generated),
                    )
                else:
                    logger.warning(
                        f"Attempt {attempt + 1} for {platform.value} was too long "
                        f"({len(generated)}/{config.max_length}). Will retry if attempts remain."
                    )

            except Exception as e:
                logger.error(f"Generation attempt {attempt + 1} failed: {str(e)}")
                if attempt == max_retries - 1:
                    return GenerationResult(
                        content=None,
                        success=False,
                        error_message=str(e),
                        attempts=attempt + 1,
                    )

        return GenerationResult(
            content=None,
            success=False,
            error_message="Max retries exceeded",
            attempts=max_retries,
        )

    def _build_prompt(
        self, content_item, user, platform: Platform, config: PlatformConfig
    ) -> str:
        """Build the prompt for AI generation."""
        # Import here to avoid circular imports
        from helpers.prompts import render_system_prompt, render_user_prompt

        system_prompt = render_system_prompt(platform.value, 0, 0)
        user_prompt = render_user_prompt(content_item, user, platform.value)

        return f"{system_prompt}\n\n{user_prompt}"

    def _call_ai_api(self, prompt: str, config: PlatformConfig, **kwargs) -> str:
        """Call the AI API to generate content."""
        if self.ai_provider == "gemini":
            return self._call_gemini_api(prompt, config, **kwargs)
        else:
            raise ContentGenerationError(f"Unsupported AI provider: {self.ai_provider}")

    def _call_gemini_api(self, prompt: str, config: PlatformConfig, **kwargs) -> str:
        """Call Gemini API for content generation."""
        try:
            model = genai.GenerativeModel(self.model)

            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=kwargs.get("temperature", 0.7),
                    max_output_tokens=config.max_tokens,
                ),
            )

            if not response.text:
                raise ContentGenerationError("Gemini returned empty response")

            return response.text.strip()

        except Exception as e:
            raise ContentGenerationError(f"Gemini API call failed: {str(e)}")

    def _validate_content(self, content: str, config: PlatformConfig) -> bool:
        """Validate generated content against platform requirements."""
        # Account for URL length (approximate)
        url_length = 30  # Approximate length for shortened URLs
        effective_length = len(content) + url_length

        return effective_length <= config.max_length

    def get_platform_config(self, platform: Platform) -> PlatformConfig:
        """Get configuration for a specific platform."""
        return self.PLATFORM_CONFIGS.get(
            platform, self.PLATFORM_CONFIGS[Platform.LINKEDIN]
        )

    def get_supported_platforms(self) -> list[Platform]:
        """Get list of supported platforms."""
        return list(self.PLATFORM_CONFIGS.keys())


# Backward compatibility functions
def validate_post_length(
    content: str, platform_str: str, url: Optional[str] = None
) -> Tuple[bool, int]:
    """Legacy compatibility function for content validation."""
    generator = ContentGenerator()

    # Convert string to Platform enum
    platform_map = {
        "linkedin": Platform.LINKEDIN,
        "twitter": Platform.TWITTER,
        "facebook": Platform.FACEBOOK,
    }

    platform = platform_map.get(platform_str.lower(), Platform.LINKEDIN)
    config = generator.get_platform_config(platform)

    # Calculate length including URL (always include URL approximation for consistency)
    url_length = 30  # Approximate length for shortened URLs
    total_length = len(content) + url_length
    is_valid = total_length <= config.max_length

    return is_valid, total_length
