"""
Unified Social Media Tasks

This module provides unified tasks for content generation and posting
across multiple social media platforms.
"""

import logging
from celery import shared_task
from flask import current_app

from helpers.content_generator import ContentGenerator, Platform
from helpers.platforms import get_platform_manager, is_platform_supported

logger = logging.getLogger(__name__)


@shared_task(bind=True, ignore_result=False, max_retries=3, default_retry_delay=60)
def generate_and_post_content(
    self,
    content_id: int,
    user_id: int,
    platforms: list,
    config: dict = None,
    auto_post: bool = False,
):
    """
    Unified task for content generation and optional posting.

    Args:
        content_id: ID of the content to generate posts for
        user_id: ID of the user requesting generation
        platforms: List of platform names (e.g., ["linkedin", "twitter"])
        config: Optional configuration for generation (model, temperature, etc.)
        auto_post: Whether to automatically post to platforms where user is authorized

    Returns:
        Dict with results for each platform
    """
    try:
        from models import User, Content
        from extensions import db

        # Get user and content
        user = User.query.get(user_id)
        content = Content.query.get(content_id)

        if not user:
            raise ValueError(f"User with ID {user_id} not found.")
        if not content:
            raise ValueError(f"Content with ID {content_id} not found.")

        logger.info(
            f"Starting unified content generation for user {user_id}, content {content_id}, platforms: {platforms}"
        )

        # Initialize content generator
        generator_config = config or {}
        generator = ContentGenerator(
            model=generator_config.get("model_name", "gemini-1.5-pro"),
            api_key=generator_config.get("api_key"),
        )

        results = {}

        # Process each platform
        for platform_name in platforms:
            try:
                # Convert to Platform enum
                platform = Platform(platform_name.lower())

                # Check if platform is supported for posting
                posting_supported = is_platform_supported(platform)

                # Generate content
                generation_result = generator.generate_content(
                    content,
                    user,
                    platform,
                    max_retries=generator_config.get("max_retries", 3),
                    temperature=generator_config.get("temperature", 0.7),
                )

                platform_result = {
                    "generation": {
                        "success": generation_result.success,
                        "content": generation_result.content,
                        "error_message": generation_result.error_message,
                        "attempts": generation_result.attempts,
                        "length": generation_result.length,
                    },
                    "posting": None,
                }

                # Auto-post if requested and generation was successful
                if auto_post and generation_result.success and posting_supported:

                    try:
                        platform_manager = get_platform_manager(platform)

                        # Check authorization
                        if platform_manager.check_authorization(user):
                            post_result = platform_manager.post_content(
                                user, generation_result.content, content_id
                            )

                            platform_result["posting"] = post_result

                            # Create Share record if posting was successful
                            if post_result.get("success"):
                                from models import Share

                                share = Share(
                                    user_id=user_id,
                                    content_id=content_id,
                                    platform=platform_name.lower(),
                                    post_content=generation_result.content,
                                    post_url=post_result.get("post_url"),
                                )
                                db.session.add(share)
                                db.session.commit()

                                logger.info(
                                    f"Successfully posted to {platform_name} and recorded share"
                                )
                        else:
                            platform_result["posting"] = {
                                "success": False,
                                "error_message": f"User not authorized for {platform_name}",
                                "post_id": None,
                                "platform_response": None,
                            }
                    except Exception as post_error:
                        logger.error(
                            f"Error posting to {platform_name}: {str(post_error)}"
                        )
                        platform_result["posting"] = {
                            "success": False,
                            "error_message": str(post_error),
                            "post_id": None,
                            "platform_response": None,
                        }

                results[platform_name] = platform_result

            except ValueError as platform_error:
                logger.error(
                    f"Error processing platform {platform_name}: {str(platform_error)}"
                )
                results[platform_name] = {
                    "generation": {
                        "success": False,
                        "content": None,
                        "error_message": str(platform_error),
                        "attempts": 0,
                        "length": 0,
                    },
                    "posting": None,
                }

        # Determine overall success
        any_success = any(
            result["generation"]["success"] for result in results.values()
        )

        return {
            "status": "SUCCESS" if any_success else "FAILURE",
            "platforms": results,
            "user_id": user_id,
            "content_id": content_id,
            "config": config,
        }

    except Exception as e:
        logger.error(f"Error in generate_and_post_content task: {str(e)}")
        raise self.retry(exc=e)


@shared_task(bind=True, ignore_result=False, max_retries=3, default_retry_delay=60)
def generate_content_only(
    self, content_id: int, user_id: int, platforms: list, config: dict = None
):
    """
    Task for content generation only (no posting).

    This is a convenience wrapper around generate_and_post_content
    with auto_post=False.
    """
    return generate_and_post_content.apply_async(
        args=[content_id, user_id, platforms, config, False]
    ).get()


@shared_task(bind=True, ignore_result=False, max_retries=3, default_retry_delay=60)
def post_generated_content(
    self, user_id: int, content_id: int, platform_name: str, post_content: str
):
    """
    Task for posting already-generated content to a specific platform.

    Args:
        user_id: ID of the user posting
        content_id: ID of the content being posted about
        platform_name: Name of the platform to post to
        post_content: The content to post

    Returns:
        Dict with posting result
    """
    try:
        from models import User, Content, Share
        from extensions import db

        user = User.query.get(user_id)
        content = Content.query.get(content_id)

        if not user:
            raise ValueError(f"User with ID {user_id} not found.")
        if not content:
            raise ValueError(f"Content with ID {content_id} not found.")

        # Convert to Platform enum and get manager
        platform = Platform(platform_name.lower())

        if not is_platform_supported(platform):
            raise ValueError(f"Platform {platform_name} is not supported for posting")

        platform_manager = get_platform_manager(platform)

        # Check authorization
        if not platform_manager.check_authorization(user):
            raise ValueError(f"User not authorized for {platform_name}")

        # Post content
        result = platform_manager.post_content(user, post_content, content_id)

        # Create Share record if successful
        if result.get("success"):
            share = Share(
                user_id=user_id,
                content_id=content_id,
                platform=platform_name.lower(),
                post_content=post_content,
                post_url=result.get("post_url"),
            )
            db.session.add(share)
            db.session.commit()

            logger.info(f"Successfully posted to {platform_name} and recorded share")

        return {
            "status": "SUCCESS" if result.get("success") else "FAILURE",
            "platform": platform_name,
            "result": result,
            "user_id": user_id,
            "content_id": content_id,
        }

    except Exception as e:
        logger.error(f"Error in post_generated_content task: {str(e)}")
        raise self.retry(exc=e)
