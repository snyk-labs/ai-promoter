from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from models import Content
from helpers.openai import (
    SocialPostGenerator,
    validate_post_length,
)
from helpers.prompts import get_platform_config
from datetime import datetime
import logging
from extensions import db # Import the shared db instance
from tasks.promote import generate_social_media_post_task # Import the new Celery task
from celery.result import AsyncResult # To check task status

logger = logging.getLogger(__name__) # Initialize the logger for this module

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
        task = generate_social_media_post_task.delay(content_id=content.id, user_id=current_user.id)
        
        logger.info(f"Dispatched generate_social_media_post_task for content_id: {content_id}, task_id: {task.id}")
        
        # Return the task ID to the client for polling
        return jsonify({
            "task_id": task.id,
            "message": "Social media post generation has started.",
            "content_id": content.id # Keep content_id for client-side reference if needed
        }), 202 # Accepted

    except Exception as e:
        logger.error(f"Error dispatching promotion task for content {content_id}: {str(e)}")
        return jsonify({"error": f"An unexpected error occurred while starting post generation: {str(e)}"}), 500


@bp.route("/promote_task_status/<task_id>", methods=["GET"])
@login_required
def promote_task_status(task_id):
    """Check the status of a generate_social_media_post_task."""
    logger.info(f"Checking promote_task_status for task_id: {task_id}")
    task = generate_social_media_post_task.AsyncResult(task_id)
    
    response_data = {
        'task_id': task_id,
        'status': task.state
    }
    
    try:
        logger.debug(f"Promote task {task_id} state: {task.state}")

        if task.state == 'PENDING':
            response_data['message'] = 'Post generation is pending.'
        elif task.state == 'FAILURE':
            response_data['message'] = f"Post generation failed: {str(task.info)}"
            logger.error(f"Promote task {task_id} FAILED. Info: {task.info}")
        elif task.state == 'SUCCESS':
            response_data['message'] = 'Post generation completed successfully.'
            result = task.result
            response_data['linkedin'] = result.get('linkedin')
            response_data['warnings'] = result.get('warnings')
            response_data['content_id'] = result.get('content_id') # From task result
            logger.info(f"Promote task {task_id} SUCCEEDED. Result: {result}")
        else:
            response_data['message'] = f"Task is in an unknown state: {task.state}"
            logger.warning(f"Promote task {task_id} is in an UNKNOWN state: {task.state}. Info: {task.info}")

    except Exception as e:
        logger.exception(f"Unexpected error in promote_task_status for task_id {task_id}")
        response_data['status'] = 'ERROR'
        response_data['message'] = f"An server error occurred: {str(e)}"
        return jsonify(response_data), 500

    logger.debug(f"Returning promote_task_status response for {task_id}: {response_data}")
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
            # Ensure created_at is timezone-aware (UTC) before converting to ISO string
            aware_created_at = item.created_at.replace(tzinfo=datetime.timezone.utc)
            created_at_iso = aware_created_at.isoformat()

        # Get share statistics
        share_count = item.share_count
        platform_share_counts = item.platform_share_counts

        items.append({
            "id": item.id,
            "title": item.title,
            "excerpt": item.excerpt,
            "image_url": item.image_url,
            "publish_date": item.publish_date.isoformat() if item.publish_date else None,
            "url": item.url,
            "created_at": created_at_iso,
            "submitted_by": {"name": item.submitted_by.name} if item.submitted_by else None,
            "share_count": share_count,
            "platform_share_counts": platform_share_counts
        })

    return jsonify({
        "items": items,
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": page,
        "has_next": pagination.has_next
    })


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

    try:
        db.session.flush()       # Try to force a flush to the DB connection
        db.session.commit()
        logging.info(f"Content after update: {content.__dict__}")
        return jsonify({"message": "Content updated successfully"})
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
        logging.info(f"Content {content_id} deleted successfully by user {current_user.id}")
        return jsonify({"message": "Content deleted successfully"})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error deleting content {content_id}: {str(e)}")
        return jsonify({"error": "Failed to delete content"}), 500
