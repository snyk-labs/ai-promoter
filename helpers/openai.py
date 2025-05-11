"""
OpenAI Helper Module

This module provides functions for generating social media content using OpenAI.
"""

import os
from openai import OpenAI
# from contextlib import contextmanager # Not used
# from datetime import datetime # Not used
import logging
# from enum import Enum, auto # Not used

# Set up logger
logger = logging.getLogger(__name__)

# Define character limits for different platforms
# Moved to get_platform_config in prompt_templates.py, but keeping max_tokens here for now as it's specific to OpenAI call
# LINKEDIN_CHAR_LIMIT = 3000 # Defined in prompt_templates.py
# URL_CHAR_APPROX = 30 # Defined in prompt_templates.py


class SocialPostGenerator:
    """
    A class to generate social media posts using OpenAI.
    """
    def __init__(self, model_name="gpt-4-turbo-preview", temperature=0.7):
        """Initialize the SocialPostGenerator with an OpenAI client and settings."""
        self.client = self._get_openai_client()
        self.model_name = model_name
        self.temperature = temperature

    def _get_openai_client(self):
        """Get an OpenAI client instance."""
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            # logger.error("OPENAI_API_KEY environment variable not set") # logging handled by caller or higher level
            raise ValueError("OPENAI_API_KEY environment variable not set")
        return OpenAI(api_key=api_key)

    def generate_for_platform(
        self, content_item, user, platform='linkedin', max_retries=3
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
        from helpers.prompts import render_system_prompt, render_user_prompt, get_platform_config

        platform_config = get_platform_config(platform)

        attempts = 0
        post = None
        last_error = None
        last_length = 0 # Used to inform the model how long the previous attempt was

        while attempts < max_retries:
            try:
                system_prompt_content = render_system_prompt(platform, attempts + 1, last_length)
                user_prompt_content = render_user_prompt(content_item, user, platform)

                # Log the prompts for review
                logger.info(f"System Prompt for {platform} (Attempt {attempts + 1}):\n{system_prompt_content}")
                logger.info(f"User Prompt for {platform} (Attempt {attempts + 1}):\n{user_prompt_content}")

                response = self.client.chat.completions.create(
                    model=self.model_name, # Use instance variable
                    messages=[
                        {"role": "system", "content": system_prompt_content},
                        {"role": "user", "content": user_prompt_content}
                    ],
                    temperature=self.temperature, # Use instance variable
                    max_tokens=platform_config.get("max_tokens", 500) # Ensure max_tokens is fetched
                )

                post = response.choices[0].message.content.strip()
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
                logger.error(f"OpenAI API call attempt {attempts} for {platform} failed: {str(e)}")
        
        # If we've exhausted all retries
        if last_error:
            logger.error(f"Failed to generate {platform} post for '{content_item.title}' after {max_retries} attempts. Last error: {last_error}")
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

        # Generate LinkedIn post
        if hasattr(user, 'linkedin_authorized') and user.linkedin_authorized:
            try:
                posts["linkedin"] = self.generate_for_platform(
                    content_item,
                    user,
                    platform='linkedin',
                    max_retries=max_retries,
                )
            except Exception as e:
                # Logging is done within generate_for_platform
                logger.error(f"Failed to generate LinkedIn post for content ID {content_item.id}: {str(e)}")
                posts["linkedin"] = None
        elif hasattr(user, 'linkedin_authorized') and not user.linkedin_authorized:
            logger.info(f"LinkedIn not authorized for user {user.id}. Skipping LinkedIn post generation for content ID {content_item.id}.")
            posts["linkedin"] = None


        # Placeholder for other platforms if they are added in the future
        # if user.is_platform_authorized('another_platform'):
        # try:
        # posts["another_platform"] = self.generate_for_platform(...)
        # except Exception as e:
        # logger.error(f"Failed to generate another_platform post: {str(e)}")
        # posts["another_platform"] = None

        return posts


def validate_post_length(post, platform='linkedin', url=None):
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
    # This approximates the added length. Real URL shorteners might change this.
    if url and url not in post:
        # A more robust check might be needed if precise URL inclusion is critical
        # For now, assume simple concatenation with a space.
        current_length += len(url) + 1  # +1 for a potential space

    is_valid = current_length <= max_len

    return is_valid, current_length

# Removed old functions:
# get_openai_client (moved into class)
# generate_social_post (moved into class as generate_for_platform)
# generate_platform_specific_posts (moved into class as generate_all_platform_posts)

# Example Usage (for testing, typically not here):
# if __name__ == '__main__':
# class MockContentItem:
# def __init__(self, title, excerpt, scraped_content, url):
# self.title = title
# self.excerpt = excerpt
# self.scraped_content = scraped_content
# self.url = url
# self.publish_date = "2024-01-01"
# self.author = "Test Author"
# self.image_url = "http://example.com/image.png"
# self.context = "Some context"

# class MockUser:
# def __init__(self, id, example_social_posts, linkedin_authorized=True):
# self.id = id
# self.example_social_posts = example_social_posts
# self.linkedin_authorized = linkedin_authorized
# self.name = "Test User" # Assuming name is used in prompts

# # Configure logging for testing
# logging.basicConfig(level=logging.INFO)
# logger.info("Testing SocialPostGenerator...")

# # Create mock objects
# mock_content = MockContentItem(
# title="Exciting New Discoveries in AI",
# excerpt="A brief look at recent advancements.",
# scraped_content="""## Major Breakthroughs
# Detail about breakthrough 1...
# Detail about breakthrough 2...""",
# url="http://example.com/ai-discoveries"
# )
# mock_user = MockUser(id=1, example_social_posts="This is how I usually post about tech.", linkedin_authorized=True)

# generator = SocialPostGenerator()
# try:
# print("\\n--- Generating for LinkedIn ---")
# linkedin_post = generator.generate_for_platform(mock_content, mock_user, platform='linkedin')
# print(f"Generated LinkedIn Post:\\n{linkedin_post}")
# is_valid, length, limit = validate_post_length(linkedin_post, platform='linkedin')
# print(f"LinkedIn Post Valid: {is_valid}, Length: {length}/{limit}")

# print("\\n--- Generating all platform posts ---")
# all_posts = generator.generate_all_platform_posts(mock_content, mock_user)
# print(f"All Generated Posts: {all_posts}")
# if all_posts.get('linkedin'):
# is_valid, length, limit = validate_post_length(all_posts['linkedin'], platform='linkedin')
# print(f"LinkedIn Post (from all) Valid: {is_valid}, Length: {length}/{limit}")

# except ValueError as ve:
# print(f"ValueError during generation: {ve}")
# except Exception as e:
# print(f"An unexpected error occurred: {e}")
# # Test case for API key not set (requires unsetting OPENAI_API_KEY temporarily)
# # current_api_key = os.environ.pop('OPENAI_API_KEY', None)
# # try:
# # print("\\n--- Testing with no API key ---")
# # SocialPostGenerator()
# # except ValueError as e:
# # print(f"Caught expected error: {e}")
# # if current_api_key:
# # os.environ['OPENAI_API_KEY'] = current_api_key
