from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request
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


@bp.route("/")
@login_required
@admin_required
def dashboard():
    """Admin dashboard page."""
    # Get all content items ordered by creation date
    content_items = Content.query.order_by(Content.created_at.desc()).all()
    return render_template("admin/dashboard.html", content_items=content_items)


@bp.route("/content/create", methods=["POST"])
@login_required
@admin_required
def create_content():
    """Create new content using Firecrawl and OpenAI."""
    url = request.form.get("url")
    context = request.form.get("context")

    if not url:
        flash("URL is required.", "error")
        return redirect(url_for("admin.dashboard"))

    # Check for duplicate URL
    existing_content = Content.query.filter_by(url=url).first()
    if existing_content:
        flash("This URL has already been added as content.", "error")
        return redirect(url_for("admin.dashboard"))

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

    return redirect(url_for("admin.dashboard"))


@bp.route("/content/<int:content_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_content(content_id):
    """Delete content."""
    try:
        content = Content.query.get(content_id)
        if content:
            content.delete()
            flash("Content deleted successfully!", "success")
        else:
            flash("Content not found.", "error")
    except Exception as e:
        flash(f"Error deleting content: {str(e)}", "error")

    return redirect(url_for("admin.dashboard")) 