"""
Tests for admin views (views/admin.py)

This test suite follows the project's testing conventions:
- Unit tests with @pytest.mark.unit
- Integration tests with @pytest.mark.integration  
- Clear test organization and naming
- Proper mocking and isolation
- Clean database state per test
"""

import pytest
import uuid
from unittest.mock import patch, MagicMock

from models.user import User
from models.content import Content
from extensions import db


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
        auth_type="password"
    )
    user.set_password("admin_password_123")
    return user


def create_regular_user(unique_id=None):
    """Create a regular user for testing."""
    if not unique_id:
        unique_id = create_unique_id()
        
    user = User(
        email=f"user-{unique_id}@example.com", 
        name=f"Regular User {unique_id}",
        is_admin=False,
        auth_type="password"
    )
    user.set_password("user_password_123")
    return user


def create_form_data(unique_id=None, **overrides):
    """Helper to create form data for content creation."""
    if not unique_id:
        unique_id = create_unique_id()
        
    defaults = {
        "url": f"https://example.com/article-{unique_id}",
        "context": f"Test context for {unique_id}",
        "copy": f"Test copy for {unique_id}",
        "utm_campaign": f"test_campaign_{unique_id}",
    }
    defaults.update(overrides)
    return defaults


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


def login_user(client, user, password="admin_password_123"):
    """Helper to log in a user for testing."""
    return client.post(
        "/auth/login",
        data={"email": user.email, "password": password},
        follow_redirects=True,
    )


# --- Unit Tests ---
@pytest.mark.unit
class TestAdminDecoratorUnit:
    """Unit tests for the admin_required decorator."""

    def test_admin_required_decorator_exists(self):
        """Test that admin_required decorator is importable."""
        from views.admin import admin_required
        assert callable(admin_required)


# --- Integration Tests ---
@pytest.mark.integration
class TestContentCreationIntegration:
    """Integration tests for content creation functionality."""

    def test_create_content_success(self, app, client):
        """Test successful content creation."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)
        
        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()
            
            login_user(client, admin_user)
            
            form_data = create_form_data(unique_id)
            
            with patch("tasks.content.scrape_content_task.delay") as mock_task:
                mock_task.return_value.id = f"task_{unique_id}"
                
                response = client.post("/admin/content/create", data=form_data)
                
                json_data = assert_json_response(response, 202)
                assert json_data["task_id"] == f"task_{unique_id}"
                assert json_data["message"] == "Content processing started."
                assert "content_id" in json_data
                
                # Verify content was created in database
                content = Content.query.filter_by(url=form_data["url"]).first()
                assert content is not None
                assert content.title == "Processing..."
                assert content.submitted_by_id == admin_user.id

    def test_create_content_missing_url(self, app, client):
        """Test content creation with missing URL."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)
        
        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()
            
            login_user(client, admin_user)
            
            form_data = create_form_data(unique_id)
            del form_data["url"]  # Remove URL
            
            response = client.post("/admin/content/create", data=form_data)
            
            json_data = assert_json_response(response, 400)
            assert json_data["error"] == "URL is required."

    def test_create_content_duplicate_url(self, app, client):
        """Test content creation with duplicate URL."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)
        test_url = f"https://example.com/duplicate-{unique_id}"
        
        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()
            
            # Create existing content
            existing_content = Content(
                url=test_url,
                title="Existing Content",
                submitted_by_id=admin_user.id,
            )
            db.session.add(existing_content)
            db.session.commit()
            
            login_user(client, admin_user)
            
            form_data = create_form_data(unique_id, url=test_url)
            
            response = client.post("/admin/content/create", data=form_data)
            
            json_data = assert_json_response(response, 409)
            assert json_data["error"] == "This URL has already been added as content."


@pytest.mark.integration 
class TestTaskStatusIntegration:
    """Integration tests for task status functionality."""

    def test_task_status_pending(self, app, client):
        """Test task status check for pending task."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)
        
        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()
            
            login_user(client, admin_user)
            
            with patch("tasks.content.scrape_content_task.AsyncResult") as mock_result:
                mock_task = MagicMock()
                mock_task.state = "PENDING"
                mock_result.return_value = mock_task
                
                response = client.get(f"/admin/task_status/task_{unique_id}")
                
                json_data = assert_json_response(response, 200)
                assert json_data["task_id"] == f"task_{unique_id}"
                assert json_data["status"] == "PENDING"
                assert json_data["message"] == "Task is pending."

    def test_task_status_success_with_content(self, app, client):
        """Test task status check for successful task with content."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)
        
        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()
            
            # Create test content
            content = Content(
                url=f"https://example.com/success-content-{unique_id}",
                title=f"Test Article {unique_id}",
                excerpt=f"Test excerpt for {unique_id}",
                image_url=f"https://example.com/image-{unique_id}.jpg",
                submitted_by_id=admin_user.id,
            )
            db.session.add(content)
            db.session.commit()
            
            login_user(client, admin_user)
            
            with patch("tasks.content.scrape_content_task.AsyncResult") as mock_result:
                mock_task = MagicMock()
                mock_task.state = "SUCCESS"
                mock_task.result = content.id
                mock_result.return_value = mock_task
                
                response = client.get(f"/admin/task_status/task_{unique_id}")
                
                json_data = assert_json_response(response, 200)
                assert json_data["status"] == "SUCCESS"
                assert json_data["message"] == "Task completed successfully."
                assert json_data["result"] == content.id
                assert "content" in json_data
                
                content_data = json_data["content"]
                assert content_data["id"] == content.id
                assert content_data["title"] == f"Test Article {unique_id}"

    def test_task_status_failure(self, app, client):
        """Test task status check for failed task."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)
        
        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()
            
            login_user(client, admin_user)
            
            error_message = "Failed to scrape content"
            
            with patch("tasks.content.scrape_content_task.AsyncResult") as mock_result:
                mock_task = MagicMock()
                mock_task.state = "FAILURE"
                mock_task.info = error_message
                mock_task.result = None
                mock_result.return_value = mock_task
                
                response = client.get(f"/admin/task_status/task_{unique_id}")
                
                json_data = assert_json_response(response, 200)
                assert json_data["status"] == "FAILURE"
                assert json_data["message"] == error_message

    def test_task_status_exception_handling(self, app, client):
        """Test task status handles exceptions gracefully."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)
        
        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()
            
            login_user(client, admin_user)
            
            with patch("views.admin.scrape_content_task.AsyncResult") as mock_result:
                mock_result.side_effect = Exception("Celery connection error")
                
                response = client.get(f"/admin/task_status/task_{unique_id}")
                
                json_data = assert_json_response(response, 500)
                assert json_data["task_id"] == f"task_{unique_id}"
                assert json_data["status"] == "ERROR"
                assert "server error occurred" in json_data["message"]


@pytest.mark.integration
class TestAuthenticationIntegration:
    """Integration tests for authentication and authorization."""

    def test_create_content_requires_admin_role(self, app, client):
        """Test that create_content requires admin role."""
        unique_id = create_unique_id()
        regular_user = create_regular_user(unique_id)
        
        with app.app_context():
            db.create_all()
            db.session.add(regular_user)
            db.session.commit()
            
            login_user(client, regular_user, "user_password_123")
            
            form_data = create_form_data(unique_id)
            
            response = client.post("/admin/content/create", data=form_data)
            
            # Should redirect to main page
            assert response.status_code == 302

    def test_admin_routes_accept_json_auth_errors(self, app, client):
        """Test that admin routes return JSON errors for JSON requests."""
        unique_id = create_unique_id()
        regular_user = create_regular_user(unique_id)
        
        with app.app_context():
            db.create_all()
            db.session.add(regular_user)
            db.session.commit()
            
            login_user(client, regular_user, "user_password_123")
            
            # Make request with JSON accept header
            headers = {"Accept": "application/json"}
            response = client.post(
                "/admin/content/create",
                data=create_form_data(unique_id),
                headers=headers,
            )
            
            json_data = assert_json_response(response, 403)
            assert json_data["error"] == "Admin access required."


@pytest.mark.integration
class TestEdgeCasesIntegration:
    """Integration tests for edge cases and boundary conditions."""

    @pytest.mark.parametrize("url_type", ["long", "special_chars", "unicode"])
    def test_create_content_with_edge_case_urls(self, app, client, url_type):
        """Test content creation with various edge case URLs."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)
        
        # Create different URL types with unique identifiers
        if url_type == "long":
            test_url = f"https://example.com/very-long-path-{unique_id}/" + "a" * 200
        elif url_type == "special_chars":
            test_url = f"https://example.com/special-chars-{unique_id}?param=value&other=123"
        else:  # unicode
            test_url = f"https://example.com/unicode-{unique_id}"
        
        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()
            
            login_user(client, admin_user)
            
            form_data = create_form_data(unique_id, url=test_url)
            
            with patch("tasks.content.scrape_content_task.delay") as mock_task:
                mock_task.return_value.id = f"task_{unique_id}"
                
                response = client.post("/admin/content/create", data=form_data)
                
                json_data = assert_json_response(response, 202)
                assert json_data["task_id"] == f"task_{unique_id}"
                
                # Verify URL was saved correctly
                content = Content.query.filter_by(url=test_url).first()
                assert content is not None
                assert content.url == test_url

    def test_task_status_with_invalid_content_id(self, app, client):
        """Test task status when content ID doesn't exist."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)
        
        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()
            
            login_user(client, admin_user)
            
            non_existent_id = 99999
            
            with patch("tasks.content.scrape_content_task.AsyncResult") as mock_result:
                mock_task = MagicMock()
                mock_task.state = "SUCCESS"
                mock_task.result = non_existent_id
                mock_result.return_value = mock_task
                
                response = client.get(f"/admin/task_status/task_{unique_id}")
                
                json_data = assert_json_response(response, 200)
                assert json_data["status"] == "SUCCESS"
                assert "content_error" in json_data
                assert f"Content with ID {non_existent_id} not found" in json_data["content_error"]


@pytest.mark.integration
class TestPerformanceIntegration:
    """Performance tests for admin functionality."""

    def test_bulk_content_creation_performance(self, app, client):
        """Test performance with multiple content creation requests."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)
        
        with app.app_context():
            db.create_all()
            # Clear any existing content to ensure clean test state
            Content.query.delete()
            db.session.commit()
            
            db.session.add(admin_user)
            db.session.commit()
            
            login_user(client, admin_user)
            
            num_requests = 3  # Reduced for faster tests
            
            with patch("tasks.content.scrape_content_task.delay") as mock_task:
                for i in range(num_requests):
                    task_id = f"task_{unique_id}_{i}"
                    mock_task.return_value.id = task_id
                    
                    form_data = create_form_data(
                        f"{unique_id}_{i}",  # Unique ID per iteration
                        url=f"https://example.com/bulk-{unique_id}-{i}"
                    )
                    
                    response = client.post("/admin/content/create", data=form_data)
                    json_data = assert_json_response(response, 202)
                    assert json_data["task_id"] == task_id
                
                # Verify all content was created
                assert Content.query.count() == num_requests

    def test_task_status_query_performance(self, app, client):
        """Test performance of task status queries."""
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)
        
        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()
            
            # Create multiple content items
            contents = []
            for i in range(3):
                content = Content(
                    url=f"https://example.com/perf-test-{unique_id}-{i}",
                    title=f"Performance Test {unique_id}_{i}",
                    submitted_by_id=admin_user.id,
                )
                db.session.add(content)
                contents.append(content)
            db.session.commit()
            
            login_user(client, admin_user)
            
            # Test multiple task status requests
            with patch("tasks.content.scrape_content_task.AsyncResult") as mock_result:
                for i, content in enumerate(contents):
                    mock_task = MagicMock()
                    mock_task.state = "SUCCESS"
                    mock_task.result = content.id
                    mock_result.return_value = mock_task
                    
                    task_id = f"task_{unique_id}_{i}"
                    response = client.get(f"/admin/task_status/{task_id}")
                    
                    json_data = assert_json_response(response, 200)
                    assert json_data["status"] == "SUCCESS"
                    assert json_data["content"]["id"] == content.id
