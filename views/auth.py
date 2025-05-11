from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    jsonify,
    session,
)
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse
import logging

from extensions import db
from models import User
from helpers.arcade import (
    start_linkedin_auth,
    check_auth_status,
    post_to_linkedin,
    LINKEDIN_TOOL,
)
from helpers.openai import validate_post_length

# Set up logging
logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/register", methods=["GET", "POST"])
def register():
    """Register a new user."""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        name = request.form.get("name")

        if not email or not password or not name:
            flash("Email, password, and name are required.", "error")
            return render_template("auth/register.html")

        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("Email already registered.", "error")
            return render_template("auth/register.html")

        # Create new user
        user = User(email=email, name=name, auth_type="password")
        user.set_password(password)

        # Add user to database
        db.session.add(user)
        db.session.commit()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    """Log in an existing user."""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        remember_me = bool(request.form.get("remember_me"))

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("auth/login.html")

        # Validate user credentials
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Invalid email or password.", "error")
            return render_template("auth/login.html")

        # Log in the user
        login_user(user, remember=remember_me)

        # Redirect to the next page or home
        next_page = request.args.get("next")
        if not next_page or urlparse(next_page).netloc != "":
            next_page = url_for("main.index")

        return redirect(next_page)

    return render_template("auth/login.html")


@bp.route("/logout")
@login_required
def logout():
    """Log out the current user."""
    logout_user()
    return redirect(url_for("main.index"))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """View and edit user profile."""
    if request.method == "POST":
        # Update user information
        name = request.form.get("name")
        bio = request.form.get("bio")

        if not name:
            flash("Name is required.", "error")
            return render_template("auth/profile.html")

        # Update the user's profile
        current_user.name = name
        current_user.bio = bio

        db.session.commit()
        flash("Profile updated successfully!", "success")

    return render_template("auth/profile.html")


@bp.route("/linkedin/connect")
@login_required
def linkedin_connect():
    """Start LinkedIn authentication process."""
    try:
        auth_result = start_linkedin_auth(current_user)

        # Redirect user to LinkedIn authorization page if needed
        if auth_result["status"] == "pending":
            return redirect(auth_result["url"])
        else:
            # Update user status
            current_user.linkedin_authorized = True
            db.session.commit()
            flash("LinkedIn connection successful!", "success")
            return redirect(url_for("auth.profile"))
    except Exception as e:
        flash(f"Error connecting to LinkedIn: {str(e)}", "error")
        return redirect(url_for("auth.profile"))


@bp.route("/linkedin/check-auth")
@login_required
def check_linkedin_auth():
    """Check if user is authenticated with LinkedIn."""
    try:
        # Check if user has LinkedIn token
        is_authenticated = check_auth_status(current_user, LINKEDIN_TOOL)

        # Update user status if authenticated
        if is_authenticated and not current_user.linkedin_authorized:
            current_user.linkedin_authorized = True
            db.session.commit()

        return jsonify(
            {
                "authenticated": is_authenticated,
                "status": "completed" if is_authenticated else "pending",
            }
        )
    except Exception as e:
        return jsonify({"authenticated": False, "error": str(e)})


@bp.route("/linkedin/post", methods=["POST"])
@login_required
def linkedin_post():
    """Post content to LinkedIn."""
    try:
        # Get post content
        data = request.get_json()
        post_content = data.get("post")

        if not post_content:
            return jsonify({"success": False, "error": "Post content is required"})

        # Validate post length
        is_valid, length = validate_post_length(post_content, "linkedin")

        if not is_valid:
            return jsonify(
                {
                    "success": False,
                    "error": f"Post exceeds LinkedIn character limit ({length} characters)",
                }
            )

        # Post to LinkedIn
        result = post_to_linkedin(current_user, post_content)

        if result.get("success"):
            return jsonify(
                {"success": True, "message": "Posted to LinkedIn successfully!"}
            )
        else:
            return jsonify(
                {"success": False, "error": result.get("error", "Unknown error")}
            )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@bp.route("/linkedin/disconnect")
@login_required
def linkedin_disconnect():
    """Disconnect LinkedIn account."""
    try:
        # Update user status
        current_user.linkedin_authorized = False
        current_user.linkedin_token = None
        db.session.commit()
        flash("LinkedIn account disconnected successfully!", "success")
    except Exception as e:
        flash(f"Error disconnecting LinkedIn account: {str(e)}", "error")
    return redirect(url_for("auth.profile"))
