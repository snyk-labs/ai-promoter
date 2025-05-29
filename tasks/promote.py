from celery import shared_task
from flask import current_app
from models.content import Content
from models.user import User
from extensions import db
import logging

# Import new simplified architecture
from helpers.content_generator import ContentGenerator, Platform, GenerationResult
from helpers.platforms import get_platform_manager, is_platform_supported

# Import for LinkedIn posting - native LinkedIn only
from helpers.linkedin_native import post_to_linkedin_native
from services.slack_service import send_slack_dm

logger = logging.getLogger(__name__)


@shared_task(bind=True, ignore_result=False, max_retries=3, default_retry_delay=60)
def generate_content_task(
    self, content_id: int, user_id: int, platforms: list = None, config: dict = None
):
    """
    Modern Celery task to generate content for specified platforms using the new simplified architecture.

    Args:
        content_id: ID of the content to generate posts for
        user_id: ID of the user requesting generation
        platforms: List of platform names (defaults to ["linkedin"])
        config: Generation configuration dict (optional)

    Returns:
        Dict with platform results, warnings, and metadata
    """
    try:
        content = Content.query.get(content_id)
        user = User.query.get(user_id)

        if not content:
            logger.error(f"Content with ID {content_id} not found.")
            raise ValueError(f"Content with ID {content_id} not found.")
        if not user:
            logger.error(f"User with ID {user_id} not found.")
            raise ValueError(f"User with ID {user_id} not found.")

        # Default to LinkedIn if no platforms specified
        platforms = platforms or ["linkedin"]

        logger.info(
            f"Starting content generation for content_id: {content_id}, user_id: {user_id}, platforms: {platforms}"
        )

        # Initialize the new simplified content generator
        generator_config = config or {}
        generator = ContentGenerator(
            model=generator_config.get("model_name", "gemini-1.5-pro"),
            api_key=generator_config.get("api_key"),
        )

        results = {}
        warnings = []
        user_authorizations = {}

        for platform_name in platforms:
            platform_key = platform_name.lower()

            # Convert string to Platform enum
            try:
                platform_enum = Platform(platform_key)
            except ValueError:
                logger.warning(f"Unsupported platform: {platform_name}")
                results[platform_key] = {
                    "content": None,
                    "success": False,
                    "source": "error",
                    "error": f"Unsupported platform: {platform_name}",
                    "attempts": 0,
                    "warnings": [],
                }
                continue

            # Check user authorization for this platform
            if is_platform_supported(platform_enum):
                platform_manager = get_platform_manager(platform_enum)
                user_authorizations[platform_key] = (
                    platform_manager.check_authorization(user)
                )
            else:
                user_authorizations[platform_key] = False

            # Check if user provided custom copy
            if content.copy and content.copy.strip():
                logger.info(
                    f"Using provided copy for content_id: {content_id}, platform: {platform_name}"
                )
                generated_content = content.copy

                # Validate provided copy using new architecture
                config_obj = generator.get_platform_config(platform_enum)
                url_length = 30  # Approximate URL length
                total_length = len(generated_content) + url_length
                is_valid = total_length <= config_obj.max_length

                if not is_valid:
                    warnings.append(
                        f"{platform_name.title()}: Provided copy may exceed character limit ({total_length} characters). Please review and edit if necessary."
                    )

                results[platform_key] = {
                    "content": generated_content,
                    "success": True,
                    "source": "user_provided",
                    "length": len(generated_content),
                    "attempts": 1,
                    "warnings": [],
                }
            else:
                logger.info(
                    f"Generating AI content for content_id: {content_id}, platform: {platform_name}"
                )

                try:
                    # Use new simplified architecture for generation
                    result: GenerationResult = generator.generate_content(
                        content,
                        user,
                        platform_enum,
                        max_retries=generator_config.get("max_retries", 3),
                        temperature=generator_config.get("temperature", 0.7),
                    )

                    if result.success:
                        logger.info(
                            f"Successfully generated {platform_name} content for content_id: {content_id}"
                        )

                        results[platform_key] = {
                            "content": result.content,
                            "success": True,
                            "source": "ai_generated",
                            "length": result.length,
                            "attempts": result.attempts,
                            "warnings": [],
                        }
                    else:
                        logger.error(
                            f"Failed to generate {platform_name} content: {result.error_message}"
                        )

                        results[platform_key] = {
                            "content": None,
                            "success": False,
                            "source": "ai_generated",
                            "error": result.error_message,
                            "attempts": result.attempts,
                            "warnings": [],
                        }

                        # Add warning if user is authorized for this platform
                        if user_authorizations.get(platform_key):
                            warnings.append(
                                f"{platform_name.title()}: Content generation failed - {result.error_message}"
                            )

                except Exception as e:
                    logger.error(
                        f"Exception during {platform_name} content generation: {str(e)}"
                    )

                    results[platform_key] = {
                        "content": None,
                        "success": False,
                        "source": "ai_generated",
                        "error": str(e),
                        "attempts": 1,
                        "warnings": [],
                    }

                    if user_authorizations.get(platform_key):
                        warnings.append(
                            f"{platform_name.title()}: Content generation failed due to unexpected error."
                        )

        logger.info(
            f"Successfully processed content generation for content_id: {content_id}"
        )

        return {
            "platforms": results,
            "warnings": warnings,
            "user_authorizations": user_authorizations,
            "content_id": content_id,
            "user_id": user_id,
            "config": generator_config,
        }

    except Exception as e:
        logger.error(
            f"Error in generate_content_task for content_id {content_id}, user_id {user_id}: {str(e)}"
        )
        # This will mark the task as FAILED and store the exception info
        raise self.retry(
            exc=e, countdown=self.default_retry_delay * (2**self.request.retries)
        )


@shared_task(bind=True, ignore_result=False, max_retries=3, default_retry_delay=60)
def post_to_linkedin_task(self, user_id: int, content_id: int, post_content: str):
    """
    Celery task to post content to LinkedIn for a given user using the new platform manager.
    Args:
        user_id: The ID of the user posting the content
        content_id: The ID of the content being posted about
        post_content: The content to post to LinkedIn
    """
    try:
        from models import User, Content, Share

        user = User.query.get(user_id)
        content = Content.query.get(content_id)

        if not user:
            raise ValueError(f"User with ID {user_id} not found.")
        if not content:
            raise ValueError(f"Content with ID {content_id} not found.")

        logger.info(
            f"Starting LinkedIn post for user_id: {user_id}, content_id: {content_id}"
        )

        # Use new platform manager for posting
        platform_manager = get_platform_manager(Platform.LINKEDIN)

        # Check authorization using platform manager
        if not platform_manager.check_authorization(user):
            raise ValueError(
                "User is not authorized for LinkedIn posting. Please connect/re-connect your LinkedIn account."
            )

        # Post using platform manager
        post_result = platform_manager.post_content(user, post_content, content_id)

        if not post_result.get("success"):
            raise ValueError(
                post_result.get("error_message", "LinkedIn posting failed")
            )

        # Create Share record
        share = Share(
            user_id=user_id,
            content_id=content_id,
            platform="linkedin",
            post_content=post_content,
            post_url=post_result.get("post_url"),
        )
        db.session.add(share)
        db.session.commit()

        logger.info(
            f"Successfully recorded share for LinkedIn post by user {user_id}. Post URL: {post_result.get('post_url')}"
        )

        return {
            "status": "SUCCESS",
            "message": "Posted to LinkedIn successfully!",
            "post_url": post_result.get("post_url"),
        }

    except ValueError as ve:  # Catch specific ValueErrors first (e.g., auth issues)
        logger.error(
            f"ValueError in post_to_linkedin_task for user {user_id}, content {content_id}: {str(ve)}"
        )

        # Check if this is a 401 error (token revoked/expired)
        error_str = str(ve).lower()
        if (
            "401" in error_str
            or "unauthorized" in error_str
            or "token" in error_str
            or "authentication" in error_str
        ):
            # Send Slack DM if user has a Slack ID
            if user and user.slack_id:
                try:
                    base_url = current_app.config.get("BASE_URL", "").rstrip("/")
                    profile_url = f"{base_url}/auth/profile"
                    dm_text = (
                        f"Hi there! We tried to post to LinkedIn for you, but it looks like your authorization has expired or been revoked. "
                        f"Please reconnect your LinkedIn account by visiting your profile page: {profile_url}"
                    )
                    send_slack_dm(user.slack_id, dm_text)
                    logger.info(
                        f"Sent Slack DM to user {user_id} ({user.slack_id}) about LinkedIn re-authentication."
                    )
                except Exception as slack_err:
                    logger.error(
                        f"Failed to send Slack DM to user {user_id} ({user.slack_id}): {str(slack_err)}"
                    )
            else:
                logger.warning(
                    f"User {user_id} requires LinkedIn re-authentication but has no Slack ID for notification."
                )

        # Do not retry on auth errors or configuration issues by default, let it fail.
        raise  # Re-raise to mark task as failed
    except Exception as e:
        logger.error(
            f"Error posting to LinkedIn for user {user_id}, content {content_id}: {str(e)}"
        )
        # Retry for other types of exceptions (network, temporary API issues)
        raise self.retry(exc=e)


# To ensure this task is discoverable by Celery, you might need to import this module
# in your main celery_app.py or within the `include` list of your Celery app.
# Example in celery_app.py:
# import tasks.promote
# OR celery = Celery(..., include=['tasks.content', 'tasks.promote'])
