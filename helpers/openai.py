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

# Set up logger
logger = logging.getLogger(__name__)

# Define character limits for different platforms
TWITTER_CHAR_LIMIT = 280
LINKEDIN_CHAR_LIMIT = 3000
URL_CHAR_APPROX = 30

# Initialize the client once
# client = OpenAI()  # This will fail if OPENAI_API_KEY is not set
# Instead, create a function to get the client when needed
def get_openai_client():
    """Get an OpenAI client instance."""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    return OpenAI(api_key=api_key)


def detect_content_type(content_item):
    """Detect the type of content being promoted."""
    content_type = content_item.content_type.lower()
    
    if content_type == 'podcast':
        return 'podcast'
    elif content_type == 'video':
        return 'video'
    elif content_type == 'article':
        return 'blog'
    else:
        # Default to blog if we can't determine
        return 'blog'


def generate_social_post(
    content_item, user, platform='generic', max_retries=3
):
    """
    Generate a social media post for various content types.

    Args:
        content_item: The content object
        user: The user object with profile info
        platform: The social platform to generate content for (determines character limits)
        max_retries: Maximum number of retries for content generation

    Returns:
        A string containing the generated social post

    Raises:
        Exception: If post generation fails after max_retries
    """
    # Import here to avoid circular imports
    from helpers.prompt_templates import render_system_prompt, render_user_prompt, get_platform_config

    # Get the OpenAI client
    client = get_openai_client()

    # Get platform-specific configuration
    platform_config = get_platform_config(platform)

    # Detect content type
    content_type = detect_content_type(content_item)

    # Set content-specific variables
    if content_type == 'podcast':
        content_type_name = "podcast episode"
        url_field = content_item.url
    elif content_type == 'video':
        content_type_name = "YouTube video"
        url_field = content_item.url
    elif content_type == 'blog':
        content_type_name = "blog post"
        url_field = content_item.url

    # Track retries
    attempts = 0
    post = None
    last_error = None
    last_length = 0

    while attempts < max_retries:
        try:
            # Generate the post
            response = client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": render_system_prompt(platform)},
                    {"role": "user", "content": render_user_prompt(content_item, user, platform)}
                ],
                temperature=0.7,
                max_tokens=platform_config["max_tokens"]
            )

            post = response.choices[0].message.content.strip()
            length = len(post)

            # Check if the post is within character limits
            if length <= platform_config["max_length"]:
                return post

            # If we're still too long, try again with a more aggressive length reduction
            last_length = length
            attempts += 1

        except Exception as e:
            last_error = e
            attempts += 1
            logger.error(f"Attempt {attempts} failed: {str(e)}")

    # If we've exhausted all retries, raise the last error
    if last_error:
        raise last_error
    else:
        raise ValueError(f"Failed to generate post within {platform_config['max_length']} characters after {max_retries} attempts")


def generate_platform_specific_posts(content_item, user, max_retries=3):
    """
    Generate platform-specific social media posts for content items.

    Args:
        content_item: The content object
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
                platform='twitter',
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
                platform='linkedin',
                max_retries=max_retries,
            )
        except Exception as e:
            logger.error(f"Failed to generate LinkedIn post: {str(e)}")
            posts["linkedin"] = None

    return posts


def validate_post_length(post, platform='generic', url=None):
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

    from helpers.prompt_templates import get_platform_config
    twitter_config = get_platform_config('twitter')
    linkedin_config = get_platform_config('linkedin')

    is_valid_for_twitter = total_length <= twitter_config["max_length"]
    is_valid_for_linkedin = total_length <= linkedin_config["max_length"]

    return is_valid_for_twitter, is_valid_for_linkedin, total_length
