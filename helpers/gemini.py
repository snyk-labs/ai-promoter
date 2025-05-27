"""
Gemini Helper Module

This module provides functions for generating social media content using Google's Gemini API.
"""

import os
import google.generativeai as genai
import logging

# Set up logger
logger = logging.getLogger(__name__)


class SocialPostGenerator:
    """
    A class to generate social media posts using Google's Gemini API.
    """

    def __init__(self, model_name="gemini-1.5-pro", temperature=0.7):
        """Initialize the SocialPostGenerator with a Gemini client and settings."""
        self.model_name = model_name
        self.temperature = temperature
        self.client = self._get_gemini_client()

    def _get_gemini_client(self):
        """Get a Gemini client instance."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        genai.configure(api_key=api_key)
        return genai.GenerativeModel(self.model_name)

    def generate_for_platform(
        self, content_item, user, platform="linkedin", max_retries=3
    ):
        """
        Generate a social media post for a specific platform.

        Args:
            content_item: The content object.
            user: The user object with profile info.
            platform: The social platform to generate content for (e.g., 'linkedin').
            max_retries: Maximum number of retries for content generation.

        Returns:
            A string containing the generated social post.

        Raises:
            Exception: If post generation fails after max_retries.
        """
        # Import here to avoid circular imports and keep them method-specific
        from helpers.prompts import (
            render_system_prompt,
            render_user_prompt,
            get_platform_config,
        )

        platform_config = get_platform_config(platform)

        attempts = 0
        post = None
        last_error = None
        last_length = 0  # Used to inform the model how long the previous attempt was

        while attempts < max_retries:
            try:
                system_prompt_content = render_system_prompt(
                    platform, attempts + 1, last_length
                )
                user_prompt_content = render_user_prompt(content_item, user, platform)

                # Log the prompts for review
                logger.info(
                    f"System Prompt for {platform} (Attempt {attempts + 1}):\n{system_prompt_content}"
                )
                logger.info(
                    f"User Prompt for {platform} (Attempt {attempts + 1}):\n{user_prompt_content}"
                )

                # Combine prompts for Gemini
                full_prompt = f"{system_prompt_content}\n\n{user_prompt_content}"

                response = self.client.generate_content(
                    full_prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=self.temperature,
                        max_output_tokens=platform_config.get("max_tokens", 500),
                    ),
                )

                post = response.text.strip()
                current_length = len(post)

                # Validate length (using platform_config's max_length)
                if current_length <= platform_config["max_length"]:
                    return post

                # If too long, update last_length and retry
                last_length = current_length
                logger.warning(
                    f"Attempt {attempts + 1} for {platform} post for '{content_item.title}' was too long ({current_length}/{platform_config['max_length']}). Retrying."
                )
                attempts += 1

            except Exception as e:
                last_error = e
                attempts += 1
                logger.error(
                    f"Gemini API call attempt {attempts} for {platform} failed: {str(e)}"
                )

        # If we've exhausted all retries
        if last_error:
            logger.error(
                f"Failed to generate {platform} post for '{content_item.title}' after {max_retries} attempts. Last error: {last_error}"
            )
            raise last_error
        else:
            # This case means all retries failed due to length
            error_message = f"Failed to generate {platform} post for '{content_item.title}' within {platform_config['max_length']} characters after {max_retries} attempts. Last attempt length: {last_length}"
            logger.error(error_message)
            raise ValueError(error_message)

    def generate_all_platform_posts(self, content_item, user, max_retries=3):
        """
        Generates social media posts for all configured and authorized platforms.
        Currently, this only supports LinkedIn.

        Args:
            content_item: The content object.
            user: The user object with profile info.
            max_retries: Maximum number of retries for content generation for each platform.

        Returns:
            A dictionary containing posts for each platform, e.g., {"linkedin": "post_content"}.
            If a platform post generation fails, its value will be None.
        """
        posts = {}

        # Generate LinkedIn post - always attempt generation
        try:
            logger.info(
                f"Attempting to generate LinkedIn post for content ID {content_item.id}, user ID {user.id}, regardless of user's LinkedIn authorization status."
            )
            posts["linkedin"] = self.generate_for_platform(
                content_item,
                user,
                platform="linkedin",
                max_retries=max_retries,
            )
        except Exception as e:
            # Logging is done within generate_for_platform for Gemini errors
            # This catch is for other unexpected errors during the call setup or if generate_for_platform re-raises
            logger.error(
                f"Overall failure in generating LinkedIn post for content ID {content_item.id}: {str(e)}"
            )
            posts["linkedin"] = None

        # Log if LinkedIn was not authorized, for informational purposes, even though we attempted generation.
        if hasattr(user, "linkedin_authorized") and not user.linkedin_authorized:
            logger.info(
                f"User {user.id} is not authorized on LinkedIn. Post was generated but direct posting will not be available."
            )

        return posts


def validate_post_length(post, platform="linkedin", url=None):
    """
    Validate if a post is within platform character limits.

    Args:
        post: The post content (string).
        platform: The social platform to validate against (e.g., 'linkedin').
        url: Optional URL string to be considered in the length calculation if not already in the post.

    Returns:
        Tuple of (is_valid, current_length)
    """
    # Import here to ensure it's available and to avoid top-level circular dependency issues.
    from helpers.prompts import get_platform_config

    platform_config = get_platform_config(platform)
    max_len = platform_config["max_length"]

    current_length = len(post)

    # If URL needs to be added and isn't already in the post
    if url and url not in post:
        current_length += len(url) + 1  # +1 for a potential space

    is_valid = current_length <= max_len

    return is_valid, current_length
