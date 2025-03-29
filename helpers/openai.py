"""
OpenAI Helper Module

This module provides functions for generating social media content using OpenAI.
"""

import os
from openai import OpenAI
from contextlib import contextmanager
from datetime import datetime
import logging
from enum import Enum, auto


# Initialize the client once
# client = OpenAI()  # This will fail if OPENAI_API_KEY is not set
# Instead, create a function to get the client when needed
def get_openai_client():
    """Get the OpenAI client, initializing it if necessary."""
    return OpenAI()


# Define character limits for different platforms
TWITTER_CHAR_LIMIT = 280
LINKEDIN_CHAR_LIMIT = 3000
URL_CHAR_APPROX = 30


# Define social platform types
class SocialPlatform(Enum):
    TWITTER = auto()
    LINKEDIN = auto()
    GENERIC = auto()  # For web UI when platform is unknown


# Define content types
class ContentType(Enum):
    PODCAST = auto()
    VIDEO = auto()
    BLOG = auto()


# Set up logger
logger = logging.getLogger(__name__)


def get_platform_config(platform):
    """Get the configuration for a specific social platform."""
    if platform == SocialPlatform.TWITTER:
        return {
            "name": "Twitter/X",
            "char_limit": TWITTER_CHAR_LIMIT,
            "content_limit": TWITTER_CHAR_LIMIT - URL_CHAR_APPROX,
            "style": "concise, engaging, to the point",
        }
    elif platform == SocialPlatform.LINKEDIN:
        return {
            "name": "LinkedIn",
            "char_limit": LINKEDIN_CHAR_LIMIT,
            "content_limit": 1000,  # Although LinkedIn allows 3000, we want to keep it reasonably short
            "style": "professional, slightly more detailed, includes insights",
        }
    else:  # GENERIC - conservative approach for web UI
        return {
            "name": "Generic (Twitter-compatible)",
            "char_limit": TWITTER_CHAR_LIMIT,
            "content_limit": TWITTER_CHAR_LIMIT - URL_CHAR_APPROX,
            "style": "concise, engaging, works on all platforms",
        }


def detect_content_type(content_item):
    """Detect the type of content being promoted."""
    from models import Episode, Post, Video

    if isinstance(content_item, Episode):
        return ContentType.PODCAST
    elif isinstance(content_item, Video):
        return ContentType.VIDEO
    elif isinstance(content_item, Post):
        return ContentType.BLOG
    else:
        # Default to podcast if we can't determine
        return ContentType.PODCAST


def generate_social_post(
    content_item, user, platform=SocialPlatform.GENERIC, max_retries=3
):
    """
    Generate a social media post for various content types.

    Args:
        content_item: The content object (Episode, Video, or Blog Post)
        user: The user object with profile info
        platform: The social platform to generate content for (determines character limits)
        max_retries: Maximum number of retries for content generation

    Returns:
        A string containing the generated social post

    Raises:
        Exception: If post generation fails after max_retries
    """
    # Import here to avoid circular imports
    from helpers.prompt_templates import render_system_prompt, render_user_prompt

    # Get the OpenAI client
    client = get_openai_client()

    # Get platform-specific configuration
    platform_config = get_platform_config(platform)

    # Detect content type
    content_type = detect_content_type(content_item)

    # Set content-specific variables
    if content_type == ContentType.PODCAST:
        content_type_name = "podcast episode"
        url_field = content_item.player_url
    elif content_type == ContentType.VIDEO:
        content_type_name = "YouTube video"
        url_field = content_item.url
    elif content_type == ContentType.BLOG:
        content_type_name = "blog post"
        url_field = content_item.url

    # Track retries
    attempts = 0
    post = None
    last_error = None
    last_length = 0

    while attempts < max_retries:
        attempts += 1

        try:
            # Render the system and user prompts using the template system
            system_message = render_system_prompt(
                content_item,
                user,
                platform,
                retry_attempt=attempts,
                last_length=last_length,
            )

            user_message = render_user_prompt(content_item, user, platform)

            # Log the complete prompt being sent to OpenAI with clear separators
            logger.info("=" * 80)
            logger.info(f"OpenAI Prompt Generation - Attempt {attempts}")
            logger.info(f"Content ID: {getattr(content_item, 'id', 'unknown')}")
            logger.info(f"Content Type: {content_type}")
            logger.info(f"Platform: {platform_config['name']}")
            logger.info(f"User: {getattr(user, 'name', 'Unknown')}")
            logger.info("-" * 80)
            logger.info("System Message:")
            logger.info(system_message)
            logger.info("-" * 80)
            logger.info("User Message:")
            logger.info(user_message)
            logger.info("=" * 80)

            # Query OpenAI to generate the social post
            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.7,
                max_tokens=300,
                top_p=1.0,
                frequency_penalty=0.1,
                presence_penalty=0.0,
            )

            # Extract the generated text
            post = response.choices[0].message.content.strip()

            # Log the response from OpenAI with clear separators
            logger.info("=" * 80)
            logger.info("OpenAI Response")
            logger.info(f"Content ID: {getattr(content_item, 'id', 'unknown')}")
            logger.info("-" * 80)
            logger.info("Generated Post:")
            logger.info(post)
            logger.info("=" * 80)

            # Check the length of the generated post
            total_length = len(post)

            # Make sure URL is included
            if url_field not in post:
                total_length += len(url_field) + 1  # +1 for space

            # If within limits, return the post
            if total_length <= platform_config["char_limit"]:
                # Make sure the URL is at the end if not already included
                if url_field not in post:
                    post = f"{post} {url_field}"
                return post

            # If we get here, the post is too long
            last_length = total_length
            logger.warning(
                f"Generated {platform_config['name']} post too long: {total_length} characters (max: {platform_config['char_limit']})"
            )

        except Exception as e:
            last_error = str(e)
            logger.error(
                f"Error generating {platform_config['name']} post (attempt {attempts}): {last_error}"
            )

    # If we've reached max retries, provide a minimal fallback post or raise an exception
    if post and last_length > platform_config["char_limit"]:
        # Attempt to truncate the post as a last resort
        truncation_limit = platform_config["content_limit"] - 3  # -3 for the ellipsis
        truncated_text = post[:truncation_limit].strip() + "..."
        fallback_post = f"{truncated_text} {url_field}"
        logger.warning(
            f"Used truncated fallback {platform_config['name']} post: {len(fallback_post)} characters"
        )
        return fallback_post

    # If we have no post at all, create a minimal fallback
    if not post:
        fallback_post = (
            f"Check out this {content_type_name} {time_context}: {url_field}"
        )
        logger.warning(
            f"Used minimal fallback {platform_config['name']} post: {len(fallback_post)} characters"
        )
        return fallback_post

    # This shouldn't happen with the fallbacks above, but just in case
    raise Exception(
        f"Failed to generate valid {platform_config['name']} post after {max_retries} attempts: {last_error}"
    )


def generate_platform_specific_posts(content_item, user, max_retries=3):
    """
    Generate platform-specific social media posts for content items.

    Args:
        content_item: The content object (Episode, Video, or Blog Post)
        user: The user object with profile info
        max_retries: Maximum number of retries for content generation

    Returns:
        A dictionary containing posts for each platform
    """
    posts = {}

    # Generate Twitter post
    if user.x_authorized:
        try:
            posts["twitter"] = generate_social_post(
                content_item,
                user,
                platform=SocialPlatform.TWITTER,
                max_retries=max_retries,
            )
        except Exception as e:
            logger.error(f"Failed to generate Twitter post: {str(e)}")
            posts["twitter"] = None

    # Generate LinkedIn post
    if user.linkedin_authorized:
        try:
            posts["linkedin"] = generate_social_post(
                content_item,
                user,
                platform=SocialPlatform.LINKEDIN,
                max_retries=max_retries,
            )
        except Exception as e:
            logger.error(f"Failed to generate LinkedIn post: {str(e)}")
            posts["linkedin"] = None

    return posts


def validate_post_length(post, platform=SocialPlatform.GENERIC, url=None):
    """
    Validate if a post is within platform character limits.

    Args:
        post: The post content
        platform: The social platform to validate against
        url: Optional URL to be added to the post if not already included

    Returns:
        Tuple of (is_valid_for_twitter, is_valid_for_linkedin, total_length)
    """
    total_length = len(post)

    # If URL needs to be added and isn't already in the post
    if url and url not in post:
        total_length += len(url) + 1  # +1 for space

    twitter_config = get_platform_config(SocialPlatform.TWITTER)
    linkedin_config = get_platform_config(SocialPlatform.LINKEDIN)

    is_valid_for_twitter = total_length <= twitter_config["char_limit"]
    is_valid_for_linkedin = total_length <= linkedin_config["char_limit"]

    return is_valid_for_twitter, is_valid_for_linkedin, total_length
