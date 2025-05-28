from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    jsonify,
    session,
    current_app,
)
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse
import logging
from datetime import datetime, timedelta

from extensions import db
from models import User, Share
from helpers.linkedin_native import (
    generate_linkedin_auth_url,
    exchange_code_for_token,
    revoke_linkedin_token,
    get_linkedin_user_profile,
)
from helpers.gemini import validate_post_length

# Set up logging
logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/register", methods=["GET", "POST"])
def register():
    """Register a new user."""
    # If Okta is enabled, redirect to login page
    if current_app.config.get("OKTA_ENABLED"):
        flash(
            "Registration is disabled when Okta SSO is enabled. Please use Okta to sign in.",
            "warning",
        )
        return redirect(url_for("auth.login"))

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
        promote_id_after_login = session.pop("promote_after_login", None)
        if promote_id_after_login:
            # If a promotion was pending, redirect to index with the promote ID
            next_page = url_for("main.index", promote=promote_id_after_login)
            return redirect(next_page)

        # Default redirect logic if no promotion was pending
        next_page = request.args.get("next")
        if not next_page or urlparse(next_page).netloc != "":
            next_page = url_for("main.index")

        return redirect(next_page)

    # For GET requests, pass the 'next' parameter to the template
    next_url_for_template = request.args.get("next")
    return render_template("auth/login.html", next_url=next_url_for_template)


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
        example_social_posts = request.form.get("example_social_posts")

        if not name:
            flash("Name is required.", "error")
            return render_template("auth/profile.html")

        # Update the user's profile
        current_user.name = name
        current_user.bio = bio
        current_user.example_social_posts = example_social_posts

        db.session.commit()
        flash("Profile updated successfully!", "success")

    return render_template("auth/profile.html")


@bp.route("/linkedin/connect")
@login_required
def linkedin_connect():
    """Start LinkedIn authentication process using native LinkedIn integration."""
    try:
        auth_url = generate_linkedin_auth_url()
        return redirect(auth_url)
    except ValueError as e:  # Catch errors from get_linkedin_config or CSRF issues
        logger.error(f"Error generating native LinkedIn auth URL: {str(e)}")
        flash(f"Could not start LinkedIn connection: {str(e)}", "error")
        return redirect(url_for("auth.profile"))
    except Exception as e:
        logger.error(f"Unexpected error during native LinkedIn connect: {str(e)}")
        flash("An unexpected error occurred while connecting to LinkedIn.", "error")
        return redirect(url_for("auth.profile"))


@bp.route("/linkedin/callback")
@login_required
def linkedin_callback():
    """Handle callback from LinkedIn OAuth after user authorization."""
    code = request.args.get("code")
    state = request.args.get("state")

    if not code or not state:
        flash("LinkedIn authorization failed: Missing code or state.", "error")
        logger.warning("LinkedIn callback missing code or state.")
        return redirect(url_for("auth.profile"))

    try:
        token_data = exchange_code_for_token(code, state)

        access_token = token_data.get("access_token")
        refresh_token = token_data.get(
            "refresh_token"
        )  # May not always be present on subsequent exchanges
        expires_in = token_data.get("expires_in")

        if not access_token:
            flash("Failed to obtain LinkedIn access token.", "error")
            logger.error(
                f"LinkedIn callback did not receive access_token for user {current_user.id}"
            )
            return redirect(url_for("auth.profile"))

        # Fetch user profile to get their LinkedIn ID (sub)
        profile_data = get_linkedin_user_profile(access_token)
        linkedin_id = profile_data.get(
            "sub"
        )  # 'sub' is the standard OpenID Connect subject identifier

        if not linkedin_id:
            flash("Failed to retrieve LinkedIn user ID.", "error")
            logger.error(
                f"Could not get LinkedIn 'sub' (user ID) for user {current_user.id}"
            )
            return redirect(url_for("auth.profile"))

        # Update user model
        current_user.linkedin_native_id = linkedin_id
        current_user.linkedin_native_access_token = access_token
        if refresh_token:  # Only update if a new one is provided
            current_user.linkedin_native_refresh_token = refresh_token
        if expires_in:
            current_user.linkedin_native_token_expires_at = (
                datetime.utcnow() + timedelta(seconds=expires_in)
            )

        current_user.linkedin_authorized = (
            True  # General flag indicating a LinkedIn connection
        )

        db.session.commit()
        flash("Successfully connected to LinkedIn!", "success")
        logger.info(
            f"User {current_user.id} successfully connected native LinkedIn account {linkedin_id}."
        )

    except ValueError as e:  # Handles CSRF errors, API errors from helpers
        flash(f"LinkedIn authorization error: {str(e)}", "error")
        logger.error(
            f"ValueError during LinkedIn callback for user {current_user.id}: {str(e)}"
        )
    except Exception as e:
        flash("An unexpected error occurred during LinkedIn authorization.", "error")
        logger.error(
            f"Unexpected error in LinkedIn callback for user {current_user.id}: {str(e)}"
        )

    return redirect(url_for("auth.profile"))


@bp.route("/linkedin/check-auth")
@login_required
def check_linkedin_auth():
    """Check if user is authenticated with LinkedIn."""
    is_authenticated = bool(
        current_user.linkedin_native_access_token
        and current_user.linkedin_native_token_expires_at
        and current_user.linkedin_native_token_expires_at > datetime.utcnow()
    )
    # Potentially add token refresh logic here if token is about to expire.
    return jsonify(
        {
            "authenticated": is_authenticated,
            "status": "completed" if is_authenticated else "pending",
            "native": True,
        }
    )


@bp.route("/linkedin/post", methods=["POST"])
@login_required
def linkedin_post():
    """Post content to LinkedIn asynchronously using native LinkedIn integration."""
    try:
        data = request.get_json()
        post_content = data.get("post")
        content_id = data.get("content_id")

        if not post_content:
            return jsonify({"success": False, "error": "Post content is required"})
        if not content_id:
            return jsonify({"success": False, "error": "Content ID is required"})

        is_valid, length = validate_post_length(post_content, "linkedin")
        if not is_valid:
            return jsonify(
                {
                    "success": False,
                    "error": f"Post exceeds LinkedIn character limit ({length} characters)",
                }
            )

        # Dispatch Celery task for LinkedIn posting
        from tasks.promote import post_to_linkedin_task

        task = post_to_linkedin_task.delay(current_user.id, content_id, post_content)

        return jsonify(
            {"success": True, "message": "LinkedIn post started!", "task_id": task.id}
        )

    except Exception as e:
        logger.error(
            f"Error in /linkedin/post route for user {current_user.id}: {str(e)}"
        )
        return jsonify({"success": False, "error": str(e)})


@bp.route("/linkedin/disconnect", methods=["POST"])
@login_required
def linkedin_disconnect():
    """Disconnect LinkedIn account using native LinkedIn integration."""
    try:
        if current_user.linkedin_native_access_token:
            revoke_linkedin_token(current_user.linkedin_native_access_token)
            # Regardless of revocation success, clear local tokens

        current_user.linkedin_native_id = None
        current_user.linkedin_native_access_token = None
        current_user.linkedin_native_refresh_token = None
        current_user.linkedin_native_token_expires_at = None
        current_user.linkedin_authorized = False  # General flag
        db.session.commit()
        flash("LinkedIn account disconnected successfully.", "success")
        logger.info(f"User {current_user.id} disconnected native LinkedIn account.")
    except Exception as e:
        flash(f"Error disconnecting LinkedIn account: {str(e)}", "error")
        logger.error(
            f"Error disconnecting native LinkedIn for user {current_user.id}: {str(e)}"
        )

    return redirect(url_for("auth.profile"))
