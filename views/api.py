from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from models import Content
from datetime import datetime, timezone
import logging
from extensions import db  # Import the shared db instance
from tasks.promote import generate_social_media_post_task  # Import the new Celery task
from celery.result import AsyncResult  # To check task status

logger = logging.getLogger(__name__)  # Initialize the logger for this module

# Create a blueprint for API routes
bp = Blueprint("api", __name__, url_prefix="/api")


@bp.route("/promote/<int:content_id>", methods=["POST"])
@login_required
def promote_content(content_id):
    """Dispatch a Celery task to generate social media posts for a content item."""
    try:
        # Ensure content exists, though the task will also check
        content = Content.query.get_or_404(content_id)

        # Dispatch the Celery task
        # Pass current_user.id instead of the full user object
        task = generate_social_media_post_task.delay(
            content_id=content.id, user_id=current_user.id
        )

        logger.info(
            f"Dispatched generate_social_media_post_task for content_id: {content_id}, task_id: {task.id}"
        )

        # Return the task ID to the client for polling
        return (
            jsonify(
                {
                    "task_id": task.id,
                    "message": "Social media post generation has started.",
                    "content_id": content.id,  # Keep content_id for client-side reference if needed
                }
            ),
            202,
        )  # Accepted

    except Exception as e:
        logger.error(
            f"Error dispatching promotion task for content {content_id}: {str(e)}"
        )
        return (
            jsonify(
                {
                    "error": f"An unexpected error occurred while starting post generation: {str(e)}"
                }
            ),
            500,
        )


@bp.route("/promote_task_status/<task_id>", methods=["GET"])
@login_required
def promote_task_status(task_id):
    """Check the status of a generate_social_media_post_task."""
    logger.info(f"Checking promote_task_status for task_id: {task_id}")
    task = generate_social_media_post_task.AsyncResult(task_id)

    response_data = {"task_id": task_id, "status": task.state}

    try:
        logger.debug(f"Promote task {task_id} state: {task.state}")

        if task.state == "PENDING":
            response_data["message"] = "Post generation is pending."
        elif task.state == "FAILURE":
            response_data["message"] = f"Post generation failed: {str(task.info)}"
            logger.error(f"Promote task {task_id} FAILED. Info: {task.info}")
        elif task.state == "SUCCESS":
            response_data["message"] = "Post generation completed successfully."
            result = task.result
            response_data["linkedin"] = result.get("linkedin")
            response_data["warnings"] = result.get("warnings")
            response_data["content_id"] = result.get("content_id")  # From task result
            response_data["linkedin_authorized_for_posting"] = (
                current_user.linkedin_authorized
            )
            logger.info(
                f"Promote task {task_id} SUCCEEDED. Result: {result}, LinkedIn Authorized: {current_user.linkedin_authorized}"
            )
        else:
            response_data["message"] = f"Task is in an unknown state: {task.state}"
            logger.warning(
                f"Promote task {task_id} is in an UNKNOWN state: {task.state}. Info: {task.info}"
            )

    except Exception as e:
        logger.exception(
            f"Unexpected error in promote_task_status for task_id {task_id}"
        )
        response_data["status"] = "ERROR"
        response_data["message"] = f"An server error occurred: {str(e)}"
        return jsonify(response_data), 500

    logger.debug(
        f"Returning promote_task_status response for {task_id}: {response_data}"
    )
    return jsonify(response_data)


@bp.route("/content")
def get_paginated_content():
    """Get paginated content items."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    content_type = request.args.get("type")

    # Build query
    query = Content.query
    if content_type:
        query = query.filter(Content.content_type == content_type)

    # Get paginated results
    pagination = query.order_by(Content.publish_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Convert items to dict
    items = []
    for item in pagination.items:
        created_at_iso = None
        if item.created_at:
            aware_created_at = item.created_at.replace(tzinfo=timezone.utc)
            created_at_iso = aware_created_at.isoformat()

        updated_at_iso = None
        if item.updated_at:
            aware_updated_at = item.updated_at.replace(tzinfo=timezone.utc)
            updated_at_iso = aware_updated_at.isoformat()

        # Get share statistics
        share_count = item.share_count
        platform_share_counts = item.platform_share_counts

        items.append(
            {
                "id": item.id,
                "title": item.title,
                "excerpt": item.excerpt,
                "image_url": item.image_url,
                "publish_date": (
                    item.publish_date.isoformat() if item.publish_date else None
                ),
                "url": item.url,
                "created_at_iso": created_at_iso,
                "updated_at_iso": updated_at_iso,
                "submitted_by_name": (
                    item.submitted_by.name if item.submitted_by else None
                ),
                "submitted_by_id": item.submitted_by_id,
                "share_count": share_count,
                "platform_share_counts": (
                    [
                        {"platform": p.platform, "count": p.count}
                        for p in platform_share_counts
                    ]
                    if platform_share_counts
                    else []
                ),
                "utm_campaign": item.utm_campaign,
                "copy": item.copy,
                "context": item.context,
                "scraped_content": item.scraped_content,
            }
        )

    return jsonify(
        {
            "content": items,
            "has_more": pagination.has_next,
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": page,
        }
    )


@bp.route("/content/<int:content_id>", methods=["PUT"])
@login_required
def update_content(content_id):
    """Update a content item. Only accessible to admin users."""
    if not current_user.is_admin:
        return jsonify({"error": "Unauthorized"}), 403

    content = Content.query.get_or_404(content_id)
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    logging.info(f"Updating content {content_id} with data: {data}")
    logging.info(f"Content before update: {content.__dict__}")

    # Update fields if provided
    if "title" in data:
        content.title = data["title"]
    if "excerpt" in data:
        content.excerpt = data["excerpt"]
    if "url" in data:
        content.url = data["url"]
    if "image_url" in data:
        content.image_url = data["image_url"]
    if "context" in data:
        content.context = data["context"]

    # Handle copy field updates
    if "copy" in data:
        content.copy = data[
            "copy"
        ]  # The model will automatically process this with UTM parameters

    # Handle UTM campaign updates
    if "utm_campaign" in data:
        content.utm_campaign = data["utm_campaign"]
        # If copy exists but wasn't updated in this request, reprocess it with new UTM campaign
        if "copy" not in data and content.copy:
            content.copy = (
                content.copy
            )  # This will trigger the model's UTM parameter processing

    try:
        db.session.flush()  # Try to force a flush to the DB connection
        db.session.commit()
        logging.info(f"Content after update: {content.__dict__}")

        # Return the full content data including the processed copy
        return jsonify(
            {
                "message": "Content updated successfully",
                "content": {
                    "id": content.id,
                    "title": content.title,
                    "url": content.url,
                    "excerpt": content.excerpt,
                    "image_url": content.image_url,
                    "submitted_by_name": (
                        content.submitted_by.name if content.submitted_by else None
                    ),
                    "created_at_iso": content.created_at.isoformat(),
                    "updated_at_iso": content.updated_at.isoformat(),
                    "share_count": content.share_count,
                    "platform_share_counts": [
                        {"platform": p.platform, "count": p.count}
                        for p in content.platform_share_counts
                    ],
                    "utm_campaign": content.utm_campaign,
                    "copy": content.copy,  # This will be the processed copy with UTM parameters
                    "context": content.context,
                },
            }
        )
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error updating content: {str(e)}")
        return jsonify({"error": "Failed to update content"}), 500


@bp.route("/content/<int:content_id>", methods=["DELETE"])
@login_required
def delete_content_api(content_id):
    """Delete a content item. Only accessible to admin users."""
    if not current_user.is_admin:
        return jsonify({"error": "Unauthorized"}), 403

    content = Content.query.get_or_404(content_id)

    try:
        # Instead of content.delete() which might be a custom method not shown,
        # use db.session.delete() and db.session.commit()
        db.session.delete(content)
        db.session.commit()
        logging.info(
            f"Content {content_id} deleted successfully by user {current_user.id}"
        )
        return jsonify({"message": "Content deleted successfully"})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error deleting content {content_id}: {str(e)}")
        return jsonify({"error": "Failed to delete content"}), 500


@bp.route("/notify_content/<int:content_id>", methods=["POST"])
@login_required
def notify_content_api(content_id):
    """Trigger a one-off Slack notification for a specific content item."""
    if not current_user.is_admin:
        logger.warning(
            f"Non-admin user {current_user.id} attempted to trigger notification for content {content_id}."
        )
        return jsonify({"error": "Unauthorized. Admin access required."}), 403

    try:
        content = Content.query.get_or_404(content_id)
        logger.info(
            f"Admin user {current_user.id} is triggering a one-off Slack notification for content: {content.id} - '{content.title}'"
        )

        # Import the task
        from tasks.notifications import send_one_off_content_notification

        # Dispatch the Celery task
        task = send_one_off_content_notification.delay(content_id=content.id)

        logger.info(
            f"Dispatched send_one_off_content_notification task for content_id: {content.id}, Celery task_id: {task.id}"
        )

        return (
            jsonify(
                {
                    "message": "Slack notification task triggered successfully!",
                    "content_id": content.id,
                    "task_id": task.id,
                }
            ),
            202,  # Accepted
        )

    except Exception as e:
        logger.error(
            f"Error dispatching one-off Slack notification task for content {content_id}: {str(e)}",
            exc_info=True,
        )
        return (
            jsonify({"error": f"An unexpected error occurred: {str(e)}"}),
            500,
        )
