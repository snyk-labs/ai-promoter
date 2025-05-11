from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from models import Content
from helpers.openai import (
    generate_social_post,
    validate_post_length,
    LINKEDIN_CHAR_LIMIT,
    URL_CHAR_APPROX,
)
from helpers.prompt_templates import get_platform_config
from datetime import datetime
import logging
from extensions import db # Import the shared db instance

# Create a blueprint for API routes
bp = Blueprint("api", __name__, url_prefix="/api")


@bp.route("/promote/<int:content_id>", methods=["POST"])
@login_required
def promote_content(content_id):
    """Generate social media posts for a content item."""
    try:
        # Get content item
        content = Content.query.get_or_404(content_id)
        
        # Get user from request
        user = request.json.get("user", {})
        if not user:
            return jsonify({"error": "User information is required"}), 400

        # Generate LinkedIn post
        linkedin_post = generate_social_post(content, user, "linkedin")

        # Validate post length
        is_valid, length = validate_post_length(linkedin_post, "linkedin")

        # Prepare warnings
        warnings = []
        if not is_valid:
            warnings.append(f"LinkedIn: Post exceeds character limit ({length} characters)")

        return jsonify({
            "linkedin": linkedin_post,
            "warnings": warnings
        })

    except Exception as e:
        logging.error(f"Error promoting content: {str(e)}")
        return jsonify({"error": str(e)}), 500


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

        items.append({
            "id": item.id,
            "title": item.title,
            "excerpt": item.excerpt,
            "image_url": item.image_url,
            "publish_date": item.publish_date.isoformat() if item.publish_date else None,
            "url": item.url,
            "created_at": created_at_iso,
            "submitted_by": {"name": item.submitted_by.name} if item.submitted_by else None 
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
