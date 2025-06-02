# Tests for views/okta_auth.py - Okta Authentication Integration

import os
import pytest
import uuid
from unittest.mock import patch, MagicMock

from models.user import User
from extensions import db


# --- Test Configuration Constants ---
class TestOktaConstants:
    """Centralized constants for Okta authentication testing."""

    # Mock Okta Configuration
    MOCK_CLIENT_ID = "test_client_id_12345"
    MOCK_CLIENT_SECRET = "test_client_secret_67890"
    MOCK_ISSUER = "https://dev-test.okta.com/oauth2/default"
    MOCK_REDIRECT_URI = "http://localhost:5000/auth/okta/callback"
    MOCK_SCOPES = ["openid", "profile", "email"]

    # Mock Tokens & State
    MOCK_ACCESS_TOKEN = "mock_access_token_abc123"
    MOCK_ID_TOKEN = "mock_id_token_def456"
    MOCK_STATE = "mock_state_xyz789"
    MOCK_NONCE = "mock_nonce_uvw456"
    MOCK_AUTH_CODE = "mock_auth_code_rst789"


# --- Custom Test Fixtures ---
@pytest.fixture(scope="function")
def okta_app():
    """
    Create Flask app with Okta enabled for testing.
    Uses environment variable patching instead of module reloading for better performance.
    """
    # Store original environment values
    original_env = {
        var: os.environ.get(var)
        for var in [
            "OKTA_ENABLED",
            "OKTA_CLIENT_ID",
            "OKTA_CLIENT_SECRET",
            "OKTA_ISSUER",
            "OKTA_REDIRECT_URI",
            "TESTING",
        ]
    }

    try:
        # Set Okta environment variables
        test_env = {
            "OKTA_ENABLED": "true",
            "OKTA_CLIENT_ID": TestOktaConstants.MOCK_CLIENT_ID,
            "OKTA_CLIENT_SECRET": TestOktaConstants.MOCK_CLIENT_SECRET,
            "OKTA_ISSUER": TestOktaConstants.MOCK_ISSUER,
            "OKTA_REDIRECT_URI": TestOktaConstants.MOCK_REDIRECT_URI,
            "TESTING": "true",
        }

        for key, value in test_env.items():
            os.environ[key] = value

        # Import and create app after setting environment
        import importlib
        import sys

        for module in ["config", "helpers.okta", "views.okta_auth", "app"]:
            if module in sys.modules:
                importlib.reload(sys.modules[module])

        from app import create_app

        flask_app = create_app()

        # Configure for testing
        flask_app.config.update(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                "WTF_CSRF_ENABLED": False,
                "LOGIN_DISABLED": True,
                "SERVER_NAME": "localhost.localdomain",
                "APPLICATION_ROOT": "/",
                "PREFERRED_URL_SCHEME": "http",
                "CELERY_TASK_ALWAYS_EAGER": True,
                "CELERY_TASK_EAGER_PROPAGATES": True,
                **test_env,
            }
        )

        yield flask_app

    finally:
        # Restore original environment
        for var, original_value in original_env.items():
            if original_value is not None:
                os.environ[var] = original_value
            elif var in os.environ:
                del os.environ[var]


@pytest.fixture()
def okta_client(okta_app):
    """Test client for Okta-enabled app."""
    return okta_app.test_client()


@pytest.fixture()
def okta_db(okta_app):
    """Database fixture for Okta testing with proper cleanup."""
    with okta_app.app_context():
        db.create_all()
        yield db
        db.session.remove()
        db.drop_all()


# --- Test Helper Functions ---
def create_unique_id():
    """Generate unique ID for test isolation."""
    return str(uuid.uuid4())[:8]


def create_test_user(unique_id=None, **overrides):
    """Create test user with sensible defaults."""
    if not unique_id:
        unique_id = create_unique_id()

    defaults = {
        "email": f"test-{unique_id}@example.com",
        "name": f"Test User {unique_id}",
        "okta_id": f"okta_{unique_id}",
        "auth_type": "okta",
        "password_hash": None,
        "is_admin": False,
    }
    defaults.update(overrides)
    return User(**defaults)


def create_mock_tokens(unique_id=None):
    """Create mock Okta token response."""
    return {
        "access_token": f"access_token_{unique_id or create_unique_id()}",
        "id_token": f"id_token_{unique_id or create_unique_id()}",
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": "openid profile email",
    }


def create_mock_claims(unique_id=None, **overrides):
    """Create mock ID token claims."""
    if not unique_id:
        unique_id = create_unique_id()

    defaults = {
        "sub": f"okta_{unique_id}",
        "email": f"test-{unique_id}@example.com",
        "name": f"Test User {unique_id}",
        "given_name": f"Test{unique_id}",
        "family_name": f"User{unique_id}",
        "iss": TestOktaConstants.MOCK_ISSUER,
        "aud": TestOktaConstants.MOCK_CLIENT_ID,
        "exp": 9999999999,
        "iat": 1234567890,
        "nonce": TestOktaConstants.MOCK_NONCE,
    }
    defaults.update(overrides)
    return defaults


def create_mock_profile(unique_id=None, **overrides):
    """Create mock user profile from userinfo endpoint."""
    if not unique_id:
        unique_id = create_unique_id()

    defaults = {
        "sub": f"okta_{unique_id}",
        "email": f"test-{unique_id}@example.com",
        "name": f"Test User {unique_id}",
        "given_name": f"Test{unique_id}",
        "family_name": f"User{unique_id}",
        "preferred_username": f"test-{unique_id}@example.com",
        "updated_at": 1234567890,
    }
    defaults.update(overrides)
    return defaults


def assert_redirect_to(response, expected_location_contains, status_code=302):
    """Assert response redirects to expected location."""
    assert response.status_code == status_code
    location = response.headers.get("Location", "")
    assert (
        expected_location_contains in location
    ), f"Expected '{expected_location_contains}' in '{location}'"


def setup_okta_mocks():
    """Setup common Okta configuration mocks."""
    return {
        "OKTA_ENABLED": True,
        "OKTA_CLIENT_ID": TestOktaConstants.MOCK_CLIENT_ID,
        "OKTA_CLIENT_SECRET": TestOktaConstants.MOCK_CLIENT_SECRET,
        "OKTA_ISSUER": TestOktaConstants.MOCK_ISSUER,
        "OKTA_REDIRECT_URI": TestOktaConstants.MOCK_REDIRECT_URI,
        "OKTA_SCOPES": TestOktaConstants.MOCK_SCOPES,
    }


# --- Unit Tests ---
@pytest.mark.unit
@pytest.mark.auth
class TestOktaAuthBlueprint:
    """Unit tests for Okta auth blueprint."""

    def test_blueprint_registration(self):
        """Test blueprint is properly configured."""
        from views.okta_auth import bp

        assert bp.name == "okta_auth"
        assert bp.url_prefix == "/auth/okta"


# --- Integration Tests ---
@pytest.mark.integration
@pytest.mark.auth
class TestOktaLogin:
    """Integration tests for Okta login flow."""

    def test_authenticated_user_redirected(self, okta_client, okta_db):
        """Authenticated users should be redirected to main page."""
        with patch("views.okta_auth.current_user") as mock_user:
            mock_user.is_authenticated = True
            response = okta_client.get("/auth/okta/login")
            assert_redirect_to(response, "/")

    def test_okta_disabled_redirects_to_login(self, okta_client, okta_db):
        """When Okta disabled, redirect to regular login."""
        with patch("views.okta_auth.OKTA_ENABLED", False):
            response = okta_client.get("/auth/okta/login")
            assert_redirect_to(response, "/auth/login")

    def test_okta_enabled_redirects_to_authorization(self, okta_client, okta_db):
        """When Okta enabled, redirect to Okta authorization."""
        with patch.multiple("views.okta_auth", **setup_okta_mocks()):
            with patch("views.okta_auth.current_user") as mock_user:
                mock_user.is_authenticated = False

                with patch(
                    "views.okta_auth.generate_secure_state_and_nonce"
                ) as mock_gen:
                    mock_gen.return_value = (
                        TestOktaConstants.MOCK_STATE,
                        TestOktaConstants.MOCK_NONCE,
                    )

                    with patch("views.okta_auth.build_authorization_url") as mock_build:
                        mock_build.return_value = (
                            f"{TestOktaConstants.MOCK_ISSUER}/v1/authorize"
                        )

                        response = okta_client.get("/auth/okta/login")
                        assert response.status_code == 302
                        mock_build.assert_called_once()

    def test_session_data_stored(self, okta_client, okta_db):
        """Login should store state, nonce, and next URL in session."""
        with patch.multiple("views.okta_auth", **setup_okta_mocks()):
            with patch("views.okta_auth.current_user") as mock_user:
                mock_user.is_authenticated = False

                with patch(
                    "views.okta_auth.generate_secure_state_and_nonce"
                ) as mock_gen:
                    mock_gen.return_value = (
                        TestOktaConstants.MOCK_STATE,
                        TestOktaConstants.MOCK_NONCE,
                    )

                    okta_client.get("/auth/okta/login?next=/dashboard")

                    with okta_client.session_transaction() as sess:
                        assert sess["okta_state"] == TestOktaConstants.MOCK_STATE
                        assert sess["okta_nonce"] == TestOktaConstants.MOCK_NONCE
                        assert sess["next_url"] == "/dashboard"


@pytest.mark.integration
@pytest.mark.auth
class TestOktaCallback:
    """Integration tests for Okta callback handling."""

    def test_error_parameter_redirects(self, okta_client, okta_db):
        """Okta error parameter should redirect to login with error."""
        response = okta_client.get(
            "/auth/okta/callback?error=access_denied&error_description=User%20denied"
        )
        assert_redirect_to(response, "/auth/login")

    def test_invalid_state_csrf_protection(self, okta_client, okta_db):
        """Invalid state parameter should trigger CSRF protection."""
        with okta_client.session_transaction() as sess:
            sess["okta_state"] = "valid_state"

        response = okta_client.get(
            "/auth/okta/callback?state=invalid_state&code=test_code"
        )
        assert_redirect_to(response, "/auth/login")

    def test_missing_session_state(self, okta_client, okta_db):
        """Missing session state should redirect to login."""
        response = okta_client.get(
            "/auth/okta/callback?state=test_state&code=test_code"
        )
        assert_redirect_to(response, "/auth/login")

    def test_token_exchange_failure(self, okta_client, okta_db):
        """Token exchange failure should redirect to login."""
        with okta_client.session_transaction() as sess:
            sess["okta_state"] = TestOktaConstants.MOCK_STATE

        with patch(
            "views.okta_auth.exchange_code_for_tokens",
            side_effect=Exception("Token exchange failed"),
        ):
            response = okta_client.get(
                f"/auth/okta/callback?state={TestOktaConstants.MOCK_STATE}&code=test_code"
            )
            assert_redirect_to(response, "/auth/login")

    def test_successful_existing_user_login(self, okta_client, okta_db):
        """Successful callback should login existing user."""
        unique_id = create_unique_id()
        existing_user = create_test_user(unique_id)

        okta_db.session.add(existing_user)
        okta_db.session.commit()

        with okta_client.session_transaction() as sess:
            sess["okta_state"] = TestOktaConstants.MOCK_STATE
            sess["okta_nonce"] = TestOktaConstants.MOCK_NONCE
            sess["next_url"] = "/dashboard"

        # Mock the entire flow
        with patch(
            "views.okta_auth.exchange_code_for_tokens",
            return_value=create_mock_tokens(unique_id),
        ):
            with patch(
                "views.okta_auth.validate_id_token",
                return_value=create_mock_claims(
                    unique_id, email=existing_user.email, sub=existing_user.okta_id
                ),
            ):
                with patch(
                    "views.okta_auth.get_user_profile",
                    return_value=create_mock_profile(
                        unique_id, email=existing_user.email, sub=existing_user.okta_id
                    ),
                ):
                    with patch("views.okta_auth.login_user") as mock_login:
                        response = okta_client.get(
                            f"/auth/okta/callback?state={TestOktaConstants.MOCK_STATE}&code=test_code"
                        )

                        assert_redirect_to(response, "/dashboard")
                        mock_login.assert_called_once()

    def test_successful_new_user_creation(self, okta_client, okta_db):
        """Successful callback should create new user."""
        unique_id = create_unique_id()

        with okta_client.session_transaction() as sess:
            sess["okta_state"] = TestOktaConstants.MOCK_STATE
            sess["okta_nonce"] = TestOktaConstants.MOCK_NONCE
            sess["next_url"] = "/"

        claims = create_mock_claims(unique_id)
        profile = create_mock_profile(unique_id)

        with patch(
            "views.okta_auth.exchange_code_for_tokens",
            return_value=create_mock_tokens(unique_id),
        ):
            with patch("views.okta_auth.validate_id_token", return_value=claims):
                with patch("views.okta_auth.get_user_profile", return_value=profile):
                    with patch("views.okta_auth.login_user") as mock_login:
                        response = okta_client.get(
                            f"/auth/okta/callback?state={TestOktaConstants.MOCK_STATE}&code=test_code"
                        )

                        assert_redirect_to(response, "/")
                        mock_login.assert_called_once()

                        # Verify new user created
                        new_user = User.query.filter_by(email=profile["email"]).first()
                        assert new_user is not None
                        assert new_user.name == profile["name"]
                        assert new_user.okta_id == claims["sub"]
                        assert new_user.auth_type == "okta"

    def test_session_cleanup_after_success(self, okta_client, okta_db):
        """Session should be cleaned up after successful authentication."""
        unique_id = create_unique_id()

        with okta_client.session_transaction() as sess:
            sess["okta_state"] = TestOktaConstants.MOCK_STATE
            sess["okta_nonce"] = TestOktaConstants.MOCK_NONCE
            sess["next_url"] = "/"

        with patch(
            "views.okta_auth.exchange_code_for_tokens",
            return_value=create_mock_tokens(unique_id),
        ):
            with patch(
                "views.okta_auth.validate_id_token",
                return_value=create_mock_claims(unique_id),
            ):
                with patch(
                    "views.okta_auth.get_user_profile",
                    return_value=create_mock_profile(unique_id),
                ):
                    with patch("views.okta_auth.login_user"):
                        okta_client.get(
                            f"/auth/okta/callback?state={TestOktaConstants.MOCK_STATE}&code=test_code"
                        )

                        # Verify session cleaned up
                        with okta_client.session_transaction() as sess:
                            assert "okta_state" not in sess
                            assert "okta_nonce" not in sess


@pytest.mark.integration
@pytest.mark.auth
class TestOktaUserHandling:
    """Tests for Okta user data handling and name extraction."""

    @pytest.mark.parametrize(
        "name_data,expected_name",
        [
            ({"name": "Full Name"}, "Full Name"),
            ({"given_name": "John", "family_name": "Doe"}, "John Doe"),
            ({"first_name": "Jane", "last_name": "Smith"}, "Jane Smith"),
            (
                {"preferred_username": "Test User"},
                "Test User",
            ),  # Must contain space to be used as name
        ],
    )
    def test_name_extraction_priority(
        self, name_data, expected_name, okta_client, okta_db
    ):
        """Test name extraction follows correct priority order."""
        unique_id = create_unique_id()
        test_email = f"test-{unique_id}@example.com"

        with okta_client.session_transaction() as sess:
            sess["okta_state"] = TestOktaConstants.MOCK_STATE
            sess["okta_nonce"] = TestOktaConstants.MOCK_NONCE

        # Create minimal profile with only the fields we're testing
        profile = {
            "sub": f"okta_{unique_id}",
            "email": test_email,
            "updated_at": 1234567890,
        }
        profile.update(name_data)

        # Create minimal claims without name fields (to test userinfo priority)
        claims = {
            "sub": f"okta_{unique_id}",
            "email": test_email,
            "iss": TestOktaConstants.MOCK_ISSUER,
            "aud": TestOktaConstants.MOCK_CLIENT_ID,
            "exp": 9999999999,
            "iat": 1234567890,
            "nonce": TestOktaConstants.MOCK_NONCE,
        }

        with patch(
            "views.okta_auth.exchange_code_for_tokens",
            return_value=create_mock_tokens(unique_id),
        ):
            with patch("views.okta_auth.validate_id_token", return_value=claims):
                with patch("views.okta_auth.get_user_profile", return_value=profile):
                    with patch("views.okta_auth.login_user"):
                        okta_client.get(
                            f"/auth/okta/callback?state={TestOktaConstants.MOCK_STATE}&code=test_code"
                        )

                        user = User.query.filter_by(email=test_email).first()
                        assert user is not None
                        assert user.name == expected_name

    def test_existing_user_fields_updated(self, okta_client, okta_db):
        """Existing user fields should be updated during login."""
        unique_id = create_unique_id()
        existing_user = create_test_user(unique_id, name="Old Name")

        okta_db.session.add(existing_user)
        okta_db.session.commit()

        with okta_client.session_transaction() as sess:
            sess["okta_state"] = TestOktaConstants.MOCK_STATE
            sess["okta_nonce"] = TestOktaConstants.MOCK_NONCE

        new_name = f"Updated Name {unique_id}"
        claims = create_mock_claims(
            unique_id, email=existing_user.email, sub=existing_user.okta_id
        )
        profile = create_mock_profile(
            unique_id,
            email=existing_user.email,
            name=new_name,
            sub=existing_user.okta_id,
        )

        with patch(
            "views.okta_auth.exchange_code_for_tokens",
            return_value=create_mock_tokens(unique_id),
        ):
            with patch("views.okta_auth.validate_id_token", return_value=claims):
                with patch("views.okta_auth.get_user_profile", return_value=profile):
                    with patch("views.okta_auth.login_user"):
                        okta_client.get(
                            f"/auth/okta/callback?state={TestOktaConstants.MOCK_STATE}&code=test_code"
                        )

                        updated_user = User.query.filter_by(
                            email=existing_user.email
                        ).first()
                        assert updated_user.id == existing_user.id  # Same user
                        assert updated_user.name == new_name


@pytest.mark.integration
@pytest.mark.auth
class TestOktaErrorHandling:
    """Tests for various Okta error scenarios."""

    @pytest.mark.parametrize(
        "error_type,error_description",
        [
            ("access_denied", "User denied access"),
            ("invalid_request", "Missing required parameter"),
            ("invalid_client", "Client authentication failed"),
            ("invalid_grant", "Authorization grant invalid"),
            ("unauthorized_client", "Client not authorized"),
        ],
    )
    def test_okta_error_types_handled(
        self, error_type, error_description, okta_client, okta_db
    ):
        """Different Okta error types should be handled gracefully."""
        encoded_description = error_description.replace(" ", "%20")
        response = okta_client.get(
            f"/auth/okta/callback?error={error_type}&error_description={encoded_description}"
        )
        assert_redirect_to(response, "/auth/login")

    def test_network_timeout_handled(self, okta_client, okta_db):
        """Network timeouts during token exchange should be handled."""
        with okta_client.session_transaction() as sess:
            sess["okta_state"] = TestOktaConstants.MOCK_STATE

        with patch(
            "views.okta_auth.exchange_code_for_tokens",
            side_effect=Exception("Connection timeout"),
        ):
            response = okta_client.get(
                f"/auth/okta/callback?state={TestOktaConstants.MOCK_STATE}&code=test_code"
            )
            assert_redirect_to(response, "/auth/login")

    def test_malformed_token_response_handled(self, okta_client, okta_db):
        """Malformed token responses should be handled gracefully."""
        with okta_client.session_transaction() as sess:
            sess["okta_state"] = TestOktaConstants.MOCK_STATE
            sess["okta_nonce"] = TestOktaConstants.MOCK_NONCE

        with patch(
            "views.okta_auth.exchange_code_for_tokens",
            return_value={"invalid": "response"},
        ):
            with patch(
                "views.okta_auth.validate_id_token",
                side_effect=KeyError("id_token not found"),
            ):
                response = okta_client.get(
                    f"/auth/okta/callback?state={TestOktaConstants.MOCK_STATE}&code=test_code"
                )
                assert_redirect_to(response, "/auth/login")


@pytest.mark.smoke
@pytest.mark.auth
class TestOktaSmoke:
    """Smoke tests for basic Okta functionality."""

    def test_routes_accessible(self, okta_client, okta_db):
        """Okta routes should be accessible."""
        # Login route
        response = okta_client.get("/auth/okta/login")
        assert response.status_code in [200, 302]

        # Callback route
        response = okta_client.get("/auth/okta/callback")
        assert response.status_code in [200, 302]

    def test_blueprint_registered(self, okta_app):
        """Okta blueprint should be registered with app."""
        blueprint_names = [bp.name for bp in okta_app.blueprints.values()]
        assert "okta_auth" in blueprint_names
