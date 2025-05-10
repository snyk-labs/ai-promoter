from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user, login_required
from models.manual_content import ManualContent
from extensions import db

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
    # Get all manual content, ordered by creation date (newest first)
    manual_content = ManualContent.query.order_by(ManualContent.created_at.desc()).all()
    return render_template("admin/dashboard.html", manual_content=manual_content)


@bp.route("/content/create", methods=["POST"])
@login_required
@admin_required
def create_content():
    """Create new manual content."""
    url = request.form.get("url")
    content_type = request.form.get("content_type")

    if not all([url, content_type]):
        flash("URL and content type are required.", "error")
        return redirect(url_for("admin.dashboard"))

    # Create new content
    new_content = ManualContent(
        url=url,
        content_type=content_type,
        created_by_id=current_user.id
    )

    try:
        db.session.add(new_content)
        db.session.commit()
        flash("Content added successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error adding content: {str(e)}", "error")

    return redirect(url_for("admin.dashboard"))


@bp.route("/content/<int:content_id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_content(content_id):
    """Toggle content active status."""
    content = ManualContent.query.get_or_404(content_id)
    content.is_active = not content.is_active

    try:
        db.session.commit()
        status = "activated" if content.is_active else "deactivated"
        flash(f"Content {status} successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating content: {str(e)}", "error")

    return redirect(url_for("admin.dashboard"))


@bp.route("/content/<int:content_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_content(content_id):
    """Delete content."""
    content = ManualContent.query.get_or_404(content_id)

    try:
        db.session.delete(content)
        db.session.commit()
        flash("Content deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting content: {str(e)}", "error")

    return redirect(url_for("admin.dashboard")) 