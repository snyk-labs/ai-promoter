from celery import shared_task
from models.content import Content
from models.user import User  # Assuming current_user will be passed by ID and fetched
from helpers.openai import SocialPostGenerator # Corrected import path
from helpers.openai import validate_post_length # Assuming validate_post_length is here
from extensions import db # For database access if needed, though fetching user might be better in endpoint
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, ignore_result=False, max_retries=3, default_retry_delay=60)
def generate_social_media_post_task(self, content_id: int, user_id: int):
    """
    Celery task to generate social media posts for a given content_id and user_id.
    """
    try:
        content = Content.query.get(content_id)
        user = User.query.get(user_id)

        if not content:
            logger.error(f"Content with ID {content_id} not found.")
            # Optional: raise an exception to mark task as FAILED if content not found
            raise ValueError(f"Content with ID {content_id} not found.") 
        if not user:
            logger.error(f"User with ID {user_id} not found.")
            raise ValueError(f"User with ID {user_id} not found.")

        logger.info(f"Starting social media post generation for content_id: {content_id}, user_id: {user_id}")

        post_generator = SocialPostGenerator()
        generated_posts = post_generator.generate_all_platform_posts(content, user)

        linkedin_post = generated_posts.get("linkedin")
        warnings = []

        if linkedin_post is None:
            warnings.append("LinkedIn: Post generation failed.")
        else:
            is_valid, length = validate_post_length(linkedin_post, "linkedin")
            if not is_valid:
                warnings.append(f"LinkedIn: Post may exceed character limit ({length} characters). Please review and edit if necessary.")
        
        logger.info(f"Successfully generated social media posts for content_id: {content_id}")
        
        return {
            "linkedin": linkedin_post,
            "warnings": warnings,
            "content_id": content_id # Include content_id for reference
        }

    except Exception as e:
        logger.error(f"Error in generate_social_media_post_task for content_id {content_id}, user_id {user_id}: {str(e)}")
        # This will mark the task as FAILED and store the exception info
        raise self.retry(exc=e, countdown=self.default_retry_delay * (2 ** self.request.retries))

# To ensure this task is discoverable by Celery, you might need to import this module
# in your main celery_app.py or within the `include` list of your Celery app.
# Example in celery_app.py:
# import tasks.promote 
# OR celery = Celery(..., include=['tasks.content', 'tasks.promote']) 