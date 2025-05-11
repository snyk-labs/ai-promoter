from functools import wraps
from flask import Blueprint, redirect, url_for, flash, request
from flask_login import current_user, login_required
from models.content import Content
from extensions import db
from services.content_processor import ContentProcessor
import logging

logger = logging.getLogger(__name__)

bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(f):
    """Decorator to require admin access for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("You must be an admin to access this page.", "error")
            return redirect(url_for("main.index"))
        return f(*args, **kwargs)
    return decorated_function


@bp.route("/content/create", methods=["POST"])
@login_required
@admin_required
def create_content():
    """Create new content using Firecrawl and OpenAI."""
    url = request.form.get("url")
    context = request.form.get("context")

    # Determine redirect target based on referrer
    # Default to main.index as admin.dashboard is removed.
    final_redirect_url = url_for("main.index") 

    # The user explicitly asked for the redirect to be conditional based on where it was posted FROM.
    # If posted from main.index, stay on main.index. That part should be kept.
    # This check is now somewhat redundant if default is main.index, but harmless.
    if request.referrer and url_for("main.index") in request.referrer:
        final_redirect_url = url_for("main.index")
    # No else needed, as it's already main.index

    if not url:
        flash("URL is required.", "error")
        return redirect(final_redirect_url)

    # Check for duplicate URL
    existing_content = Content.query.filter_by(url=url).first()
    if existing_content:
        flash("This URL has already been added as content.", "error")
        return redirect(final_redirect_url)

    try:
        # Initialize content processor
        processor = ContentProcessor()
        
        # Process the URL and create content
        content = processor.process_url(url, submitted_by_id=current_user.id)
        
        # Add context if provided
        if context:
            content.context = context
            db.session.commit()
        
        if content:
            flash("Content created successfully!", "success")
        else:
            flash("Failed to create content.", "error")
    except Exception as e:
        # Handle unexpected errors
        logger.exception("Unexpected error while adding content")
        flash(f"Error creating content: {str(e)}", "error")

    return redirect(final_redirect_url) 