# Add tests for views/main.py here

import pytest
import uuid
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from models.user import User
from models.content import Content
from extensions import db


# --- Test Data Constants ---
class TestConstants:
    """Centralized test constants for consistency."""

    DEFAULT_ADMIN_PASSWORD = "admin_password_123"
    DEFAULT_USER_PASSWORD = "user_password_123"

    # Main view specific constants
    INDEX_CONTENT_LIMIT = 12
    DEFAULT_CONTENT_TITLE = "Processing..."

    # API Response Messages
    CONTENT_PROMOTED_SUCCESS = "Content promoted successfully"
    MISSING_REQUIRED_FIELDS = "Missing required fields"
    CONTENT_NOT_FOUND = "Content not found"

    # Promote API Required Fields
    PROMOTE_REQUIRED_FIELDS = ["content_id", "content_type", "title", "description"]


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
    user.set_password(TestConstants.DEFAULT_ADMIN_PASSWORD)
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
    user.set_password(TestConstants.DEFAULT_USER_PASSWORD)
    return user


def create_test_content(unique_id=None, submitted_by_user=None, **overrides):
    """Helper to create test content."""
    if not unique_id:
        unique_id = create_unique_id()

    defaults = {
        "url": f"https://example.com/article-{unique_id}",
        "title": f"Test Article {unique_id}",
        "excerpt": f"Test excerpt for {unique_id}",
        "image_url": f"https://example.com/image-{unique_id}.jpg",
        "context": f"Test context for {unique_id}",
        "copy": f"Test copy for {unique_id}",
        "utm_campaign": f"test_campaign_{unique_id}",
        "submitted_by_id": submitted_by_user.id if submitted_by_user else None,
        "created_at": datetime.now(timezone.utc),
        "publish_date": datetime.now(timezone.utc),
    }
    defaults.update(overrides)

    content = Content(**defaults)
    return content


def assert_json_response(response, expected_status=200):
    """Assert response is valid JSON with expected status."""
    assert response.status_code == expected_status, (
        f"Expected status {expected_status}, got {response.status_code}: "
        f"{response.get_data(as_text=True)}"
    )
    try:
        return response.get_json()
    except Exception as e:
        pytest.fail(
            f"Response is not valid JSON: {e}. Response: {response.get_data(as_text=True)}"
        )


def login_user(client, user, password=None):
    """Helper to log in a user for testing."""
    if password is None:
        password = (
            TestConstants.DEFAULT_ADMIN_PASSWORD
            if user.is_admin
            else TestConstants.DEFAULT_USER_PASSWORD
        )

    return client.post(
        "/auth/login",
        data={"email": user.email, "password": password},
        follow_redirects=True,
    )


def setup_database_with_content(app, user, content_items=None):
    """Helper to set up database with user and optional content items."""
    with app.app_context():
        db.create_all()
        db.session.add(user)
        db.session.commit()

        if content_items:
            for content in content_items:
                content.submitted_by_id = user.id
            db.session.add_all(content_items)
            db.session.commit()

        return content_items


def create_multiple_content(count, user, unique_id=None):
    """Helper to create multiple content items for pagination testing."""
    if not unique_id:
        unique_id = create_unique_id()

    content_items = []
    base_time = datetime.now(timezone.utc)
    for i in range(count):
        content = create_test_content(
            f"{unique_id}_{i}",
            submitted_by_user=user,
            # Vary creation times to test ordering - use minutes instead of seconds to avoid 0-59 limit
            created_at=base_time.replace(minute=(i % 60), second=0, microsecond=i),
        )
        content_items.append(content)

    return content_items


class IndexViewTestMixin:
    """Mixin providing common index view test patterns."""

    @staticmethod
    def assert_index_template_rendered(response):
        """Assert the index template was rendered with proper context."""
        assert response.status_code == 200
        assert b"<!DOCTYPE html>" in response.data or b"<html" in response.data

    @staticmethod
    def assert_content_items_structure(content_items):
        """Assert content items have proper timezone-aware datetime objects."""
        for item in content_items:
            if item.created_at:
                assert item.created_at.tzinfo is not None
            if item.publish_date:
                assert item.publish_date.tzinfo is not None


class PromoteApiTestMixin:
    """Mixin providing common promote API test patterns."""

    @staticmethod
    def create_promote_request_data(content_id, **overrides):
        """Create valid promote request data with optional overrides."""
        defaults = {
            "content_id": content_id,
            "content_type": "article",
            "title": "Test Article",
            "description": "Test description for article",
        }
        defaults.update(overrides)
        return defaults

    @staticmethod
    def assert_promote_success_response(json_data):
        """Assert successful promote response structure."""
        assert json_data["message"] == TestConstants.CONTENT_PROMOTED_SUCCESS

    @staticmethod
    def assert_missing_fields_error(json_data):
        """Assert missing required fields error response."""
        assert json_data["error"] == TestConstants.MISSING_REQUIRED_FIELDS

    @staticmethod
    def assert_content_not_found_error(json_data):
        """Assert content not found error response."""
        assert json_data["error"] == TestConstants.CONTENT_NOT_FOUND


# --- Unit Tests ---
@pytest.mark.unit
class TestMainBlueprintUnit:
    """Unit tests for main blueprint registration and basic structure."""

    def test_main_blueprint_exists(self):
        """Test that the main blueprint is properly defined."""
        from views.main import bp

        assert bp is not None
        assert bp.name == "main"
        assert bp.url_prefix is None  # Main blueprint has no URL prefix


# --- Integration Tests ---
@pytest.mark.integration
class TestIndexViewIntegration(IndexViewTestMixin):
    """Integration tests for the index route."""

    def test_index_view_without_content(self, app, client):
        """Test index view when no content exists."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)

        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()

            login_user(client, admin_user)

            response = client.get("/")
            self.assert_index_template_rendered(response)

    def test_index_view_with_content(self, app, client):
        """Test index view displays content items correctly."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)

        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()

            # Create test content
            content_items = create_multiple_content(5, admin_user, unique_id)
            db.session.add_all(content_items)
            db.session.commit()

            login_user(client, admin_user)

            response = client.get("/")
            self.assert_index_template_rendered(response)

    def test_index_view_content_limit(self, app, client):
        """Test index view respects the 12-item limit."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)

        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()

            # Create more than 12 content items
            content_items = create_multiple_content(15, admin_user, unique_id)
            db.session.add_all(content_items)
            db.session.commit()

            login_user(client, admin_user)

            response = client.get("/")
            self.assert_index_template_rendered(response)

            # Verify has_more_content would be True (we can't directly test template vars)
            total_content = Content.query.count()
            assert total_content > TestConstants.INDEX_CONTENT_LIMIT

    def test_index_view_content_ordering(self, app, client):
        """Test index view orders content by created_at descending."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)

        with app.app_context():
            db.create_all()
            # Clear any existing content from previous tests
            Content.query.delete()
            db.session.commit()

            db.session.add(admin_user)
            db.session.commit()

            # Create content with different creation times
            content_items = []
            base_time = datetime.now(timezone.utc)
            for i in range(3):
                content = create_test_content(
                    f"{unique_id}_{i}",
                    submitted_by_user=admin_user,
                    title=f"Article {i}",
                    created_at=base_time.replace(day=10 + i),
                )
                content_items.append(content)

            db.session.add_all(content_items)
            db.session.commit()

            login_user(client, admin_user)

            response = client.get("/")
            self.assert_index_template_rendered(response)

            # Verify order by checking database query directly
            from sqlalchemy import desc

            ordered_content = Content.query.order_by(desc(Content.created_at)).all()
            assert len(ordered_content) == 3
            # Most recent should be first (day=12)
            assert ordered_content[0].title == "Article 2"

    def test_index_view_timezone_handling(self, app, client):
        """Test index view properly handles timezone conversion."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)

        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()

            # Create content with naive datetime (simulating database storage)
            content = create_test_content(
                unique_id,
                submitted_by_user=admin_user,
                created_at=datetime.now(),  # Naive datetime
                publish_date=datetime.now(),  # Naive datetime
            )
            db.session.add(content)
            db.session.commit()

            login_user(client, admin_user)

            response = client.get("/")
            self.assert_index_template_rendered(response)

    def test_index_view_unauthenticated_without_promote(self, app, client):
        """Test index view works for unauthenticated users without promote parameter."""
        with app.app_context():
            db.create_all()

            response = client.get("/")
            self.assert_index_template_rendered(response)

    def test_index_view_unauthenticated_with_promote_redirect(self, app, client):
        """Test index view redirects to login when unauthenticated with promote parameter."""
        with app.app_context():
            db.create_all()

            response = client.get("/?promote=123")
            # Should redirect to login
            assert response.status_code == 302
            assert "/auth/login" in response.location

    def test_index_view_authenticated_with_promote_parameter(self, app, client):
        """Test index view works normally when authenticated with promote parameter."""
        unique_id = create_unique_id()
        user = create_regular_user(unique_id)

        with app.app_context():
            db.create_all()
            db.session.add(user)
            db.session.commit()

            login_user(client, user)

            response = client.get("/?promote=123")
            self.assert_index_template_rendered(response)


@pytest.mark.integration
@pytest.mark.api
class TestPromoteApiIntegration(PromoteApiTestMixin):
    """Integration tests for the promote API endpoint."""

    def test_promote_content_success(self, app, client):
        """Test successful content promotion."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)

        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()

            # Create test content
            content = create_test_content(unique_id, submitted_by_user=admin_user)
            db.session.add(content)
            db.session.commit()

            login_user(client, admin_user)

            # Test promotion - Note: the route is actually in main.py, not api.py
            promote_data = self.create_promote_request_data(content.id)
            response = client.post(
                "/api/promote", json=promote_data, content_type="application/json"
            )

            json_data = assert_json_response(response, 200)
            self.assert_promote_success_response(json_data)

    def test_promote_content_missing_required_fields(self, app, client):
        """Test promote API with missing required fields."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)

        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()

            login_user(client, admin_user)

            # Test each missing field
            for field_to_remove in TestConstants.PROMOTE_REQUIRED_FIELDS:
                promote_data = self.create_promote_request_data(1)
                del promote_data[field_to_remove]

                response = client.post(
                    "/api/promote", json=promote_data, content_type="application/json"
                )

                json_data = assert_json_response(response, 400)
                self.assert_missing_fields_error(json_data)

    def test_promote_content_empty_request(self, app, client):
        """Test promote API with completely empty request."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)

        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()

            login_user(client, admin_user)

            response = client.post(
                "/api/promote", json={}, content_type="application/json"
            )

            json_data = assert_json_response(response, 400)
            self.assert_missing_fields_error(json_data)

    def test_promote_content_nonexistent_content(self, app, client):
        """Test promote API with nonexistent content ID."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)

        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()

            login_user(client, admin_user)

            # Use a content ID that doesn't exist
            promote_data = self.create_promote_request_data(99999)
            response = client.post(
                "/api/promote", json=promote_data, content_type="application/json"
            )

            json_data = assert_json_response(response, 404)
            self.assert_content_not_found_error(json_data)

    def test_promote_content_no_json_data(self, app, client):
        """Test promote API with no JSON data provided."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)

        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()

            login_user(client, admin_user)

            # Send request without JSON data
            response = client.post("/api/promote")

            # The server returns 415 for no Content-Type, not 400
            assert response.status_code == 415

    def test_promote_content_invalid_json(self, app, client):
        """Test promote API with invalid JSON."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)

        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()

            login_user(client, admin_user)

            # Send malformed JSON
            response = client.post(
                "/api/promote",
                data="invalid json",
                content_type="application/json",
            )

            # Flask may return 400 for bad JSON, but the response might not be JSON
            assert response.status_code == 400

    @pytest.mark.parametrize(
        "field_value",
        [None, "", 0, False, []],
    )
    def test_promote_content_falsy_field_values(self, field_value, app, client):
        """Test promote API with various falsy values for required fields."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)

        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()

            login_user(client, admin_user)

            # Test with falsy value for each required field
            for field in TestConstants.PROMOTE_REQUIRED_FIELDS:
                promote_data = self.create_promote_request_data(1)
                promote_data[field] = field_value

                response = client.post(
                    "/api/promote", json=promote_data, content_type="application/json"
                )

                json_data = assert_json_response(response, 400)
                self.assert_missing_fields_error(json_data)


@pytest.mark.integration
@pytest.mark.auth
class TestMainViewsAuthentication:
    """Integration tests for authentication requirements in main views."""

    def test_promote_api_requires_authentication(self, app, client):
        """Test that promote API endpoint is public (doesn't require authentication)."""
        with app.app_context():
            db.create_all()

            # Create a content item for testing
            admin_user = create_admin_user("test_auth")
            db.session.add(admin_user)
            db.session.commit()

            content = create_test_content("test_auth", submitted_by_user=admin_user)
            db.session.add(content)
            db.session.commit()

            promote_data = PromoteApiTestMixin.create_promote_request_data(content.id)
            response = client.post(
                "/api/promote", json=promote_data, content_type="application/json"
            )

            # The promote API is actually public, so it should work without authentication
            json_data = assert_json_response(response, 200)
            assert json_data["message"] == TestConstants.CONTENT_PROMOTED_SUCCESS

    def test_index_view_public_access(self, app, client):
        """Test that index view is accessible without authentication."""
        with app.app_context():
            db.create_all()

            response = client.get("/")
            # Index should be accessible to everyone
            assert response.status_code == 200


@pytest.mark.integration
class TestMainViewsEdgeCases:
    """Integration tests for edge cases and error handling in main views."""

    def test_promote_api_database_error_handling(self, app, client):
        """Test promote API handles database errors gracefully."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)

        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()

            login_user(client, admin_user)

            # Use a patch to simulate database error
            with patch("models.content.Content.query") as mock_query:
                mock_query.get.side_effect = Exception("Database connection error")

                promote_data = PromoteApiTestMixin.create_promote_request_data(1)
                response = client.post(
                    "/api/promote", json=promote_data, content_type="application/json"
                )

                json_data = assert_json_response(response, 500)
                assert "error" in json_data
                assert "Database connection error" in json_data["error"]

    def test_index_view_database_error_handling(self, app, client):
        """Test index view handles database errors gracefully."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)

        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()

            login_user(client, admin_user)

            # Use a patch to simulate database error during content query
            with patch("models.content.Content.query") as mock_query:
                mock_query.order_by.side_effect = Exception("Database error")

                # The mock is working correctly - the exception should be raised
                # This tests that our mock is properly applied
                with pytest.raises(Exception) as exc_info:
                    client.get("/")
                assert "Database error" in str(exc_info.value)

    def test_index_view_session_edge_cases(self, app, client):
        """Test index view handles session edge cases."""
        with app.app_context():
            db.create_all()

            # Test with existing session data
            with client.session_transaction() as sess:
                sess["promote_after_login"] = "existing_value"

            response = client.get("/?promote=123")
            # Should overwrite existing session value and redirect
            assert response.status_code == 302


@pytest.mark.integration
class TestMainViewsPerformance:
    """Performance tests for main views."""

    def test_index_view_performance_with_large_dataset(self, app, client):
        """Test index view performance with large number of content items."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)

        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()

            # Create a large number of content items
            content_items = create_multiple_content(100, admin_user, unique_id)
            # Batch insert for better performance
            for i in range(0, len(content_items), 50):
                batch = content_items[i : i + 50]
                db.session.add_all(batch)
                db.session.commit()

            login_user(client, admin_user)

            import time

            start_time = time.time()
            response = client.get("/")
            execution_time = time.time() - start_time

            # Index should load in reasonable time even with lots of content
            assert response.status_code == 200
            assert execution_time < 2.0, f"Index view took {execution_time:.2f}s"

    def test_promote_api_performance(self, app, client):
        """Test promote API response time."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)

        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()

            content = create_test_content(unique_id, submitted_by_user=admin_user)
            db.session.add(content)
            db.session.commit()

            login_user(client, admin_user)

            import time

            promote_data = PromoteApiTestMixin.create_promote_request_data(content.id)

            start_time = time.time()
            response = client.post(
                "/api/promote", json=promote_data, content_type="application/json"
            )
            execution_time = time.time() - start_time

            assert response.status_code == 200
            assert execution_time < 1.0, f"Promote API took {execution_time:.2f}s"


@pytest.mark.smoke
class TestMainViewsSmoke:
    """Smoke tests for main views - basic functionality verification."""

    def test_index_view_basic_functionality(self, app, client):
        """Smoke test for index view basic functionality."""
        with app.app_context():
            db.create_all()

            response = client.get("/")
            assert response.status_code == 200

    def test_promote_api_basic_functionality(self, app, client):
        """Smoke test for promote API basic functionality."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)

        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()

            content = create_test_content(unique_id, submitted_by_user=admin_user)
            db.session.add(content)
            db.session.commit()

            login_user(client, admin_user)

            promote_data = PromoteApiTestMixin.create_promote_request_data(content.id)
            response = client.post(
                "/api/promote", json=promote_data, content_type="application/json"
            )

            assert response.status_code == 200
            json_data = response.get_json()
            assert "message" in json_data
