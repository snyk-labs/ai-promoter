import pytest
import uuid
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

from models.user import User
from extensions import db


# --- Test Data Constants ---
class AuthTestConstants:
    """Centralized test constants for auth testing."""

    DEFAULT_ADMIN_PASSWORD = "admin_password_123"
    DEFAULT_USER_PASSWORD = "user_password_123"
    TEST_PASSWORD = "secure_password_123"

    # Auth Messages
    REGISTRATION_SUCCESS = "Registration successful! Please log in."
    LOGIN_SUCCESS_MESSAGE = "Successfully connected to LinkedIn!"
    PROFILE_UPDATED = "Profile updated successfully!"
    LINKEDIN_CONNECTED = "Successfully connected to LinkedIn!"
    LINKEDIN_DISCONNECTED = "LinkedIn account disconnected successfully."

    # Error Messages
    EMAIL_REQUIRED = "Email, password, and name are required."
    EMAIL_PASSWORD_REQUIRED = "Email and password are required."
    NAME_REQUIRED = "Name is required."
    EMAIL_ALREADY_REGISTERED = "Email already registered."
    INVALID_CREDENTIALS = "Invalid email or password."
    REGISTRATION_DISABLED_OKTA = (
        "Registration is disabled when Okta SSO is enabled. Please use Okta to sign in."
    )
    LINKEDIN_AUTH_FAILED = "LinkedIn authorization failed: Missing code or state."
    LINKEDIN_ACCESS_TOKEN_FAILED = "Failed to obtain LinkedIn access token."
    LINKEDIN_USER_ID_FAILED = "Failed to retrieve LinkedIn user ID."
    POST_CONTENT_REQUIRED = "Post content is required"
    CONTENT_ID_REQUIRED = "Content ID is required"

    # LinkedIn Mock Data
    MOCK_AUTH_URL = "https://linkedin.com/oauth/authorize?client_id=test"
    MOCK_EXPIRES_IN = 3600


# --- Fixtures ---
@pytest.fixture
def auth_enabled_app(app):
    """Fixture that ensures authentication is enabled for tests that need it."""
    with app.app_context():
        original_value = app.config.get("LOGIN_DISABLED")
        app.config["LOGIN_DISABLED"] = False
        db.create_all()
        yield app
        app.config["LOGIN_DISABLED"] = original_value


# --- Helper Functions ---
def create_unique_id():
    """Generate a unique ID for each test."""
    return str(uuid.uuid4())[:8]


def create_admin_user(unique_id=None):
    """Create an admin user for testing."""
    if not unique_id:
        unique_id = create_unique_id()

    user = User(
        email=f"admin-{unique_id}@example.com",
        name=f"Admin User {unique_id}",
        is_admin=True,
        auth_type="password",
    )
    user.set_password(AuthTestConstants.DEFAULT_ADMIN_PASSWORD)
    return user


def create_regular_user(unique_id=None):
    """Create a regular user for testing."""
    if not unique_id:
        unique_id = create_unique_id()

    user = User(
        email=f"user-{unique_id}@example.com",
        name=f"Regular User {unique_id}",
        is_admin=False,
        auth_type="password",
    )
    user.set_password(AuthTestConstants.DEFAULT_USER_PASSWORD)
    return user


def create_linkedin_authorized_user(unique_id=None):
    """Create a user with LinkedIn authorization."""
    if not unique_id:
        unique_id = create_unique_id()

    user = create_regular_user(unique_id)
    user.linkedin_authorized = True
    user.linkedin_native_id = f"linkedin_user_{unique_id}"
    user.linkedin_native_access_token = f"mock_access_token_{unique_id}"
    user.linkedin_native_refresh_token = f"mock_refresh_token_{unique_id}"
    user.linkedin_native_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    return user


def assert_response_redirects_to(response, expected_url, expected_status=302):
    """Assert response redirects to expected URL."""
    assert response.status_code == expected_status
    assert response.location
    parsed_url = urlparse(response.location)
    assert expected_url in parsed_url.path


def assert_flash_message_contains(response, message_substring):
    """Assert that response contains a flash message with given substring."""
    assert message_substring.encode() in response.data


def login_user(client, user_email, password):
    """Helper to log in a user for testing using email and password."""
    return client.post(
        "/auth/login",
        data={"email": user_email, "password": password},
        follow_redirects=True,
    )


def setup_user_in_db(app, user):
    """Helper to add user to database with proper context."""
    with app.app_context():
        db.session.add(user)
        db.session.commit()
        # Refresh the user to ensure it's attached to the session
        db.session.refresh(user)
        return user


class AuthResponseValidationMixin:
    """Mixin providing auth-specific response validation utilities."""

    @staticmethod
    def assert_registration_form_rendered(response):
        """Assert registration form is rendered correctly."""
        assert response.status_code == 200
        assert b"register" in response.data.lower()

    @staticmethod
    def assert_login_form_rendered(response):
        """Assert login form is rendered correctly."""
        assert response.status_code == 200
        assert b"login" in response.data.lower()

    @staticmethod
    def assert_profile_form_rendered(response):
        """Assert profile form is rendered correctly."""
        assert response.status_code == 200
        assert b"profile" in response.data.lower()

    @staticmethod
    def assert_json_success_response(response, expected_message=None):
        """Assert a successful JSON response."""
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data.get("success") is True
        if expected_message:
            assert expected_message in json_data.get("message", "")
        return json_data

    @staticmethod
    def assert_json_error_response(response, expected_error=None, expected_status=200):
        """Assert an error JSON response."""
        assert response.status_code == expected_status
        json_data = response.get_json()
        assert json_data.get("success") is False
        if expected_error:
            assert expected_error in json_data.get("error", "")
        return json_data


class LinkedInTestMixin:
    """Mixin for LinkedIn-specific testing patterns."""

    @staticmethod
    def create_mock_token_data(unique_id):
        """Create mock LinkedIn token response data."""
        return {
            "access_token": f"mock_access_token_{unique_id}",
            "refresh_token": f"mock_refresh_token_{unique_id}",
            "expires_in": AuthTestConstants.MOCK_EXPIRES_IN,
        }

    @staticmethod
    def create_mock_profile_data(unique_id):
        """Create mock LinkedIn profile data."""
        return {
            "sub": f"linkedin_user_{unique_id}",
            "name": "LinkedIn User",
            "email": "linkedin@example.com",
        }

    @staticmethod
    def assert_linkedin_connection_success(user, unique_id):
        """Assert user has successful LinkedIn connection."""
        assert user.linkedin_authorized is True
        assert user.linkedin_native_id == f"linkedin_user_{unique_id}"
        assert user.linkedin_native_access_token == f"mock_access_token_{unique_id}"

    @staticmethod
    def assert_linkedin_disconnection(user):
        """Assert user LinkedIn connection is removed."""
        assert user.linkedin_authorized is False
        assert user.linkedin_native_id is None
        assert user.linkedin_native_access_token is None
        assert user.linkedin_native_refresh_token is None
        assert user.linkedin_native_token_expires_at is None


# --- Test Classes ---


@pytest.mark.unit
@pytest.mark.auth
class TestAuthBlueprintUnit:
    """Unit tests for auth blueprint structure and configuration."""

    def test_auth_blueprint_exists(self):
        """Test that auth blueprint is properly registered."""
        from views.auth import bp as auth_bp

        assert auth_bp.name == "auth"
        assert auth_bp.url_prefix == "/auth"

    def test_auth_constants(self):
        """Test that auth constants are properly defined."""
        assert AuthTestConstants.DEFAULT_ADMIN_PASSWORD
        assert AuthTestConstants.DEFAULT_USER_PASSWORD
        assert AuthTestConstants.REGISTRATION_SUCCESS
        assert AuthTestConstants.INVALID_CREDENTIALS


@pytest.mark.unit
@pytest.mark.auth
class TestAuthHelperFunctions:
    """Unit tests for auth helper functions."""

    def test_create_unique_id(self):
        """Test unique ID generation."""
        id1 = create_unique_id()
        id2 = create_unique_id()
        assert id1 != id2
        assert len(id1) == 8

    def test_create_regular_user(self):
        """Test regular user creation."""
        user = create_regular_user()
        assert user.email
        assert user.name
        assert user.is_admin is False
        assert user.auth_type == "password"

    def test_create_admin_user(self):
        """Test admin user creation."""
        user = create_admin_user()
        assert user.email
        assert user.name
        assert user.is_admin is True
        assert user.auth_type == "password"

    def test_create_linkedin_authorized_user(self):
        """Test LinkedIn authorized user creation."""
        user = create_linkedin_authorized_user()
        assert user.linkedin_authorized is True
        assert user.linkedin_native_id
        assert user.linkedin_native_access_token


@pytest.mark.integration
@pytest.mark.auth
class TestUserRegistration(AuthResponseValidationMixin):
    """Integration tests for user registration functionality."""

    def test_registration_form_display(self, app, client):
        """Test that registration form renders correctly."""
        with app.app_context():
            db.create_all()
            response = client.get("/auth/register")
            self.assert_registration_form_rendered(response)

    def test_successful_registration(self, app, client):
        """Test complete user registration flow."""
        unique_id = create_unique_id()

        with app.app_context():
            db.create_all()
            response = client.post(
                "/auth/register",
                data={
                    "email": f"newuser-{unique_id}@example.com",
                    "password": AuthTestConstants.TEST_PASSWORD,
                    "name": f"New User {unique_id}",
                },
                follow_redirects=True,
            )

            assert response.status_code == 200
            assert_flash_message_contains(
                response, AuthTestConstants.REGISTRATION_SUCCESS
            )

            # Verify user creation
            user = User.query.filter_by(
                email=f"newuser-{unique_id}@example.com"
            ).first()
            assert user is not None
            assert user.name == f"New User {unique_id}"
            assert user.check_password(AuthTestConstants.TEST_PASSWORD)

    def test_registration_validation_errors(self, app, client):
        """Test registration form validation."""
        with app.app_context():
            db.create_all()

            # Missing email
            response = client.post(
                "/auth/register",
                data={"password": "password", "name": "Test User"},
            )
            self.assert_registration_form_rendered(response)
            assert_flash_message_contains(response, AuthTestConstants.EMAIL_REQUIRED)

    def test_duplicate_email_registration(self, app, client):
        """Test registration with existing email."""
        regular_user = create_regular_user()
        setup_user_in_db(app, regular_user)

        with app.app_context():
            response = client.post(
                "/auth/register",
                data={
                    "email": regular_user.email,
                    "password": AuthTestConstants.TEST_PASSWORD,
                    "name": "Duplicate User",
                },
            )

            self.assert_registration_form_rendered(response)
            assert_flash_message_contains(
                response, AuthTestConstants.EMAIL_ALREADY_REGISTERED
            )

    @patch("flask.current_app.config.get")
    def test_registration_disabled_with_okta(self, mock_config, app, client):
        """Test registration behavior when Okta SSO is enabled."""
        mock_config.return_value = True

        with app.app_context():
            db.create_all()
            client.post(
                "/auth/register",
                data={
                    "email": "test@example.com",
                    "password": "password123",
                    "name": "Test User",
                },
                follow_redirects=True,
            )

            # User should not be created when Okta is enabled
            user = User.query.filter_by(email="test@example.com").first()
            assert user is None

    def test_authenticated_user_registration_redirect(self, auth_enabled_app, client):
        """Test that authenticated users are redirected from registration."""
        regular_user = create_regular_user()
        setup_user_in_db(auth_enabled_app, regular_user)

        with auth_enabled_app.app_context():
            login_user(
                client, regular_user.email, AuthTestConstants.DEFAULT_USER_PASSWORD
            )
            response = client.get("/auth/register")
            assert_response_redirects_to(response, "/")


@pytest.mark.integration
@pytest.mark.auth
class TestUserLogin(AuthResponseValidationMixin):
    """Integration tests for user login functionality."""

    def test_login_form_display(self, app, client):
        """Test that login form renders correctly."""
        with app.app_context():
            db.create_all()
            response = client.get("/auth/login")
            self.assert_login_form_rendered(response)

    def test_successful_login(self, auth_enabled_app, client):
        """Test successful user authentication."""
        regular_user = create_regular_user()
        setup_user_in_db(auth_enabled_app, regular_user)

        with auth_enabled_app.app_context():
            response = client.post(
                "/auth/login",
                data={
                    "email": regular_user.email,
                    "password": AuthTestConstants.DEFAULT_USER_PASSWORD,
                },
                follow_redirects=True,
            )
            assert response.status_code == 200

    def test_login_with_remember_me(self, auth_enabled_app, client):
        """Test login with remember me functionality."""
        regular_user = create_regular_user()
        setup_user_in_db(auth_enabled_app, regular_user)

        with auth_enabled_app.app_context():
            response = client.post(
                "/auth/login",
                data={
                    "email": regular_user.email,
                    "password": AuthTestConstants.DEFAULT_USER_PASSWORD,
                    "remember_me": "on",
                },
                follow_redirects=True,
            )
            assert response.status_code == 200

    def test_invalid_credentials(self, app, client):
        """Test login with incorrect password."""
        regular_user = create_regular_user()
        setup_user_in_db(app, regular_user)

        with app.app_context():
            response = client.post(
                "/auth/login",
                data={"email": regular_user.email, "password": "wrong_password"},
            )

            self.assert_login_form_rendered(response)
            assert_flash_message_contains(
                response, AuthTestConstants.INVALID_CREDENTIALS
            )

    def test_missing_credentials(self, app, client):
        """Test login with missing form fields."""
        with app.app_context():
            db.create_all()
            response = client.post(
                "/auth/login",
                data={"email": "test@example.com"},  # Missing password
            )

            self.assert_login_form_rendered(response)
            assert_flash_message_contains(
                response, AuthTestConstants.EMAIL_PASSWORD_REQUIRED
            )

    def test_nonexistent_user_login(self, app, client):
        """Test login attempt with non-existent user."""
        with app.app_context():
            db.create_all()
            response = client.post(
                "/auth/login",
                data={
                    "email": "nonexistent@example.com",
                    "password": "password",
                },
            )

            self.assert_login_form_rendered(response)
            assert_flash_message_contains(
                response, AuthTestConstants.INVALID_CREDENTIALS
            )


@pytest.mark.integration
@pytest.mark.auth
class TestUserLogout:
    """Integration tests for user logout functionality."""

    def test_successful_logout(self, auth_enabled_app, client):
        """Test user logout flow."""
        regular_user = create_regular_user()
        setup_user_in_db(auth_enabled_app, regular_user)

        with auth_enabled_app.app_context():
            login_user(
                client, regular_user.email, AuthTestConstants.DEFAULT_USER_PASSWORD
            )
            response = client.get("/auth/logout")
            assert_response_redirects_to(response, "/")

    def test_logout_requires_authentication(self, auth_enabled_app, client):
        """Test logout endpoint requires authentication."""
        with auth_enabled_app.app_context():
            response = client.get("/auth/logout")
            assert response.status_code == 302


@pytest.mark.integration
@pytest.mark.auth
class TestUserProfile(AuthResponseValidationMixin):
    """Integration tests for user profile management."""

    def test_profile_form_display(self, auth_enabled_app, client):
        """Test profile page renders correctly for authenticated user."""
        regular_user = create_regular_user()
        setup_user_in_db(auth_enabled_app, regular_user)

        with auth_enabled_app.app_context():
            login_user(
                client, regular_user.email, AuthTestConstants.DEFAULT_USER_PASSWORD
            )
            response = client.get("/auth/profile")
            self.assert_profile_form_rendered(response)

    def test_successful_profile_update(self, auth_enabled_app, client):
        """Test user can update their profile information."""
        regular_user = create_regular_user()
        setup_user_in_db(auth_enabled_app, regular_user)

        with auth_enabled_app.app_context():
            login_user(
                client, regular_user.email, AuthTestConstants.DEFAULT_USER_PASSWORD
            )
            response = client.post(
                "/auth/profile",
                data={
                    "name": "Updated Name",
                    "bio": "Updated bio content",
                    "example_social_posts": "Updated example posts",
                },
                follow_redirects=True,
            )

            assert response.status_code == 200
            assert_flash_message_contains(response, AuthTestConstants.PROFILE_UPDATED)

            # Verify database update
            updated_user = db.session.get(User, regular_user.id)
            assert updated_user.name == "Updated Name"
            assert updated_user.bio == "Updated bio content"
            assert updated_user.example_social_posts == "Updated example posts"

    def test_profile_update_validation(self, auth_enabled_app, client):
        """Test profile update form validation."""
        regular_user = create_regular_user()
        setup_user_in_db(auth_enabled_app, regular_user)

        with auth_enabled_app.app_context():
            login_user(
                client, regular_user.email, AuthTestConstants.DEFAULT_USER_PASSWORD
            )
            response = client.post(
                "/auth/profile",
                data={"name": "", "bio": "Updated bio"},  # Empty name
            )

            self.assert_profile_form_rendered(response)
            assert_flash_message_contains(response, AuthTestConstants.NAME_REQUIRED)

    def test_profile_requires_authentication(self, auth_enabled_app, client):
        """Test profile page requires user authentication."""
        with auth_enabled_app.app_context():
            response = client.get("/auth/profile")
            assert response.status_code == 302


@pytest.mark.integration
@pytest.mark.auth
class TestLinkedInAuthentication(AuthResponseValidationMixin, LinkedInTestMixin):
    """Integration tests for LinkedIn OAuth integration."""

    @patch("views.auth.generate_linkedin_auth_url")
    def test_linkedin_connect_initiation(self, mock_auth_url, auth_enabled_app, client):
        """Test LinkedIn authentication initiation."""
        mock_auth_url.return_value = AuthTestConstants.MOCK_AUTH_URL
        regular_user = create_regular_user()
        setup_user_in_db(auth_enabled_app, regular_user)

        with auth_enabled_app.app_context():
            login_user(
                client, regular_user.email, AuthTestConstants.DEFAULT_USER_PASSWORD
            )
            response = client.get("/auth/linkedin/connect")

            assert response.status_code == 302
            assert response.location == AuthTestConstants.MOCK_AUTH_URL

    @patch("views.auth.get_linkedin_user_profile")
    @patch("views.auth.exchange_code_for_token")
    def test_linkedin_callback_success(
        self, mock_exchange, mock_profile, auth_enabled_app, client
    ):
        """Test successful LinkedIn OAuth callback handling."""
        unique_id = create_unique_id()
        mock_exchange.return_value = self.create_mock_token_data(unique_id)
        mock_profile.return_value = self.create_mock_profile_data(unique_id)
        regular_user = create_regular_user()
        setup_user_in_db(auth_enabled_app, regular_user)

        with auth_enabled_app.app_context():
            login_user(
                client, regular_user.email, AuthTestConstants.DEFAULT_USER_PASSWORD
            )
            response = client.get(
                "/auth/linkedin/callback?code=auth_code&state=csrf_state"
            )

            assert_response_redirects_to(response, "/auth/profile")

            # Verify LinkedIn data is stored
            updated_user = db.session.get(User, regular_user.id)
            self.assert_linkedin_connection_success(updated_user, unique_id)

    def test_linkedin_auth_status_check(self, auth_enabled_app, client):
        """Test LinkedIn authentication status endpoint."""
        linkedin_user = create_linkedin_authorized_user()
        setup_user_in_db(auth_enabled_app, linkedin_user)

        with auth_enabled_app.app_context():
            login_user(
                client, linkedin_user.email, AuthTestConstants.DEFAULT_USER_PASSWORD
            )
            response = client.get("/auth/linkedin/check-auth")

            assert response.status_code == 200
            json_data = response.get_json()
            assert json_data["authenticated"] is True
            assert json_data["status"] == "completed"
            assert json_data["native"] is True


@pytest.mark.integration
@pytest.mark.auth
class TestLinkedInPosting(AuthResponseValidationMixin, LinkedInTestMixin):
    """Integration tests for LinkedIn content posting."""

    @patch("tasks.promote.post_to_linkedin_task.delay")
    @patch("views.auth.get_platform_manager")
    def test_successful_linkedin_post(
        self, mock_platform_manager, mock_task, auth_enabled_app, client
    ):
        """Test successful LinkedIn post creation."""
        mock_platform_manager.return_value.validate_content.return_value = {
            "valid": True,
            "errors": [],
        }
        mock_task.return_value.id = "task_123"
        linkedin_user = create_linkedin_authorized_user()
        setup_user_in_db(auth_enabled_app, linkedin_user)

        with auth_enabled_app.app_context():
            login_user(
                client, linkedin_user.email, AuthTestConstants.DEFAULT_USER_PASSWORD
            )
            response = client.post(
                "/auth/linkedin/post",
                json={"post": "Test LinkedIn post content", "content_id": 123},
            )

            json_data = self.assert_json_success_response(
                response, "LinkedIn post started!"
            )
            assert json_data["task_id"] == "task_123"

    def test_linkedin_post_validation_errors(self, auth_enabled_app, client):
        """Test LinkedIn post validation error handling."""
        linkedin_user = create_linkedin_authorized_user()
        setup_user_in_db(auth_enabled_app, linkedin_user)

        with auth_enabled_app.app_context():
            login_user(
                client, linkedin_user.email, AuthTestConstants.DEFAULT_USER_PASSWORD
            )

            # Missing post content
            response = client.post(
                "/auth/linkedin/post",
                json={"content_id": 123},
            )
            self.assert_json_error_response(
                response, AuthTestConstants.POST_CONTENT_REQUIRED
            )

            # Missing content ID
            response = client.post(
                "/auth/linkedin/post",
                json={"post": "Test content"},
            )
            self.assert_json_error_response(
                response, AuthTestConstants.CONTENT_ID_REQUIRED
            )

    @patch("views.auth.revoke_linkedin_token")
    def test_linkedin_disconnect(self, mock_revoke, auth_enabled_app, client):
        """Test LinkedIn account disconnection."""
        linkedin_user = create_linkedin_authorized_user()
        setup_user_in_db(auth_enabled_app, linkedin_user)

        with auth_enabled_app.app_context():
            login_user(
                client, linkedin_user.email, AuthTestConstants.DEFAULT_USER_PASSWORD
            )
            response = client.post("/auth/linkedin/disconnect")

            assert_response_redirects_to(response, "/auth/profile")

            # Verify LinkedIn data is cleared
            updated_user = db.session.get(User, linkedin_user.id)
            self.assert_linkedin_disconnection(updated_user)


@pytest.mark.integration
@pytest.mark.auth
class TestAuthenticationBehavior:
    """Integration tests for general authentication behavior."""

    def test_protected_endpoints_require_authentication(self, auth_enabled_app, client):
        """Test that protected endpoints redirect unauthenticated users."""
        protected_endpoints = [
            "/auth/logout",
            "/auth/linkedin/connect",
            "/auth/linkedin/callback",
            "/auth/linkedin/check-auth",
        ]

        with auth_enabled_app.app_context():
            for endpoint in protected_endpoints:
                response = client.get(endpoint)
                assert (
                    response.status_code == 302
                ), f"Endpoint {endpoint} should require authentication"

    def test_public_endpoints_accessibility(self, app, client):
        """Test that public endpoints are accessible without authentication."""
        public_endpoints = ["/auth/register", "/auth/login"]

        with app.app_context():
            db.create_all()
            for endpoint in public_endpoints:
                response = client.get(endpoint)
                assert (
                    response.status_code == 200
                ), f"Endpoint {endpoint} should be public"


@pytest.mark.integration
@pytest.mark.auth
@pytest.mark.slow
class TestAuthPerformance:
    """Performance tests for auth functionality."""

    def test_login_performance(self, auth_enabled_app, client):
        """Test login endpoint performance meets requirements."""
        regular_user = create_regular_user()
        setup_user_in_db(auth_enabled_app, regular_user)

        with auth_enabled_app.app_context():
            import time

            start_time = time.time()
            response = client.post(
                "/auth/login",
                data={
                    "email": regular_user.email,
                    "password": AuthTestConstants.DEFAULT_USER_PASSWORD,
                },
            )
            execution_time = time.time() - start_time

            assert execution_time < 1.0  # Should complete in under 1 second
            assert response.status_code in [200, 302]

    def test_registration_performance(self, app, client):
        """Test registration endpoint performance meets requirements."""
        unique_id = create_unique_id()

        with app.app_context():
            db.create_all()
            import time

            start_time = time.time()
            response = client.post(
                "/auth/register",
                data={
                    "email": f"perftest-{unique_id}@example.com",
                    "password": AuthTestConstants.TEST_PASSWORD,
                    "name": f"Performance Test User {unique_id}",
                },
            )
            execution_time = time.time() - start_time

            assert execution_time < 1.0  # Should complete in under 1 second
            assert response.status_code in [200, 302]


@pytest.mark.integration
@pytest.mark.auth
class TestAuthEdgeCases:
    """Edge case tests for authentication functionality."""

    def test_login_with_session_promotion(self, auth_enabled_app, client):
        """Test login behavior with promote_after_login session variable."""
        regular_user = create_regular_user()
        setup_user_in_db(auth_enabled_app, regular_user)

        with auth_enabled_app.app_context():
            # Set session variable before login
            with client.session_transaction() as sess:
                sess["promote_after_login"] = "content_123"

            response = client.post(
                "/auth/login",
                data={
                    "email": regular_user.email,
                    "password": AuthTestConstants.DEFAULT_USER_PASSWORD,
                },
                follow_redirects=False,
            )

            assert response.status_code == 302
            assert "promote=content_123" in response.location

    def test_password_edge_cases(self, app, client):
        """Test authentication with various password edge cases."""
        regular_user = create_regular_user()
        setup_user_in_db(app, regular_user)

        edge_case_passwords = [
            "",  # Empty password
            " ",  # Whitespace only
            "a" * 1000,  # Very long password
            "пароль",  # Unicode password
        ]

        with app.app_context():
            for password in edge_case_passwords:
                response = client.post(
                    "/auth/login",
                    data={"email": regular_user.email, "password": password},
                )
                assert response.status_code == 200  # Form redisplay
