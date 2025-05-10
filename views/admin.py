from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import current_user, login_required

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
    return render_template("admin/dashboard.html") 