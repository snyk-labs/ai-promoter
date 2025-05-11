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
        items.append({
            "id": item.id,
            "content_type": item.content_type,
            "title": item.title,
            "description": item.description,
            "image_url": item.image_url,
            "publish_date": item.publish_date.isoformat() if item.publish_date else None,
            "url": item.url,
            "author": item.author
        })

    return jsonify({
        "items": items,
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": page,
        "has_next": pagination.has_next
    })
