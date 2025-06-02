"""
Test utilities and helpers for the AI Promoter test suite.

This module provides reusable testing utilities, fixtures, and helper functions
that can be used across different test modules for consistent and maintainable testing.
"""

import uuid
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask.testing import FlaskClient

from models.user import User
from models.content import Content
from extensions import db


class TestDataFactory:
    """Factory for creating test data objects with consistent patterns."""

    @staticmethod
    def create_unique_id() -> str:
        """Generate a unique ID for test isolation."""
        return str(uuid.uuid4())[:8]

    @classmethod
    def create_user(
        cls, unique_id: Optional[str] = None, is_admin: bool = False, **overrides
    ) -> User:
        """Create a user with sensible defaults and optional overrides."""
        if not unique_id:
            unique_id = cls.create_unique_id()

        defaults = {
            "email": f"{'admin' if is_admin else 'user'}-{unique_id}@example.com",
            "name": f"{'Admin' if is_admin else 'Regular'} User {unique_id}",
            "is_admin": is_admin,
            "auth_type": "password",
            "linkedin_authorized": False,
            "autonomous_mode": False,
        }
        defaults.update(overrides)

        user = User(**defaults)
        user.set_password("admin_password_123" if is_admin else "user_password_123")
        return user

    @classmethod
    def create_content(
        cls, unique_id: Optional[str] = None, user: Optional[User] = None, **overrides
    ) -> Content:
        """Create content with sensible defaults and optional overrides."""
        if not unique_id:
            unique_id = cls.create_unique_id()

        defaults = {
            "url": f"https://example.com/article-{unique_id}",
            "title": f"Test Article {unique_id}",
            "excerpt": f"Test excerpt for {unique_id}",
            "image_url": f"https://example.com/image-{unique_id}.jpg",
            "context": f"Test context for {unique_id}",
            "copy": f"Test copy for {unique_id}",
            "utm_campaign": f"test_campaign_{unique_id}",
            "submitted_by_id": user.id if user else None,
        }
        defaults.update(overrides)

        return Content(**defaults)

    @classmethod
    def create_multiple_content(
        cls, count: int, user: User, base_unique_id: Optional[str] = None
    ) -> List[Content]:
        """Create multiple content items for bulk testing."""
        if not base_unique_id:
            base_unique_id = cls.create_unique_id()

        content_items = []
        for i in range(count):
            content = cls.create_content(f"{base_unique_id}_{i}", user=user)
            content_items.append(content)

        return content_items


class DatabaseTestMixin:
    """Mixin providing database testing utilities."""

    @staticmethod
    def setup_database_with_content(
        app: Flask, user: User, content_items: Optional[List[Content]] = None
    ):
        """Set up database with user and optional content items."""
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

    @staticmethod
    def clear_all_content(app: Flask):
        """Clear all content from database."""
        with app.app_context():
            Content.query.delete()
            db.session.commit()

    @staticmethod
    def count_content(app: Flask) -> int:
        """Count total content items in database."""
        with app.app_context():
            return Content.query.count()


class MockFactory:
    """Factory for creating mock objects with consistent patterns."""

    @staticmethod
    def create_celery_task(
        task_id: str, state: str = "PENDING", result: Any = None, info: Any = None
    ) -> MagicMock:
        """Create a mock Celery task result."""
        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.state = state
        mock_task.result = result
        mock_task.info = info
        return mock_task

    @staticmethod
    def create_task_result_success(
        task_id: str, platforms: Dict[str, Any]
    ) -> MagicMock:
        """Create a successful task result mock."""
        return MockFactory.create_celery_task(
            task_id, "SUCCESS", result={"platforms": platforms}
        )

    @staticmethod
    def create_task_result_failure(task_id: str, error_message: str) -> MagicMock:
        """Create a failed task result mock."""
        return MockFactory.create_celery_task(task_id, "FAILURE", info=error_message)


class PerformanceTestMixin:
    """Mixin for performance testing utilities."""

    @contextmanager
    def assert_max_execution_time(self, max_seconds: float):
        """Context manager to assert maximum execution time."""
        start_time = time.time()
        try:
            yield
        finally:
            execution_time = time.time() - start_time
            assert (
                execution_time <= max_seconds
            ), f"Operation took {execution_time:.2f}s, expected <= {max_seconds}s"

    @staticmethod
    def measure_execution_time(func, *args, **kwargs) -> tuple:
        """Measure execution time of a function call."""
        start_time = time.time()
        result = func(*args, **kwargs)
        execution_time = time.time() - start_time
        return result, execution_time


class AuthenticationTestMixin:
    """Mixin for authentication testing utilities."""

    @staticmethod
    def login_user(client: FlaskClient, user: User, password: Optional[str] = None):
        """Log in a user with appropriate password."""
        if password is None:
            password = "admin_password_123" if user.is_admin else "user_password_123"

        return client.post(
            "/auth/login",
            data={"email": user.email, "password": password},
            follow_redirects=True,
        )

    @staticmethod
    def assert_requires_authentication(response, expected_redirect: bool = True):
        """Assert that a response requires authentication."""
        if expected_redirect:
            assert response.status_code in [302, 401]
        else:
            assert response.status_code in [401, 403, 500]


class ValidationTestMixin:
    """Mixin for API response validation utilities."""

    @staticmethod
    def assert_error_response(
        json_data: Dict, expected_status: int, error_substring: str
    ):
        """Assert error response structure and content."""
        assert "error" in json_data
        assert error_substring in json_data["error"]

    @staticmethod
    def assert_success_response(json_data: Dict, expected_message: str):
        """Assert success response structure and content."""
        assert "message" in json_data
        assert json_data["message"] == expected_message

    @staticmethod
    def assert_task_response(json_data: Dict, task_id: str, content_id: int):
        """Assert task creation response structure."""
        assert json_data["task_id"] == task_id
        assert json_data["content_id"] == content_id
        assert "message" in json_data


# Pytest fixtures for common test scenarios
@pytest.fixture
def test_factory():
    """Provide TestDataFactory instance."""
    return TestDataFactory()


@pytest.fixture
def mock_factory():
    """Provide MockFactory instance."""
    return MockFactory()


@pytest.fixture
def admin_user(test_factory):
    """Create an admin user for testing."""
    return test_factory.create_user(is_admin=True)


@pytest.fixture
def regular_user(test_factory):
    """Create a regular user for testing."""
    return test_factory.create_user(is_admin=False)


@pytest.fixture
def test_content(test_factory, admin_user):
    """Create test content associated with admin user."""
    return test_factory.create_content(user=admin_user)


@pytest.fixture
def multiple_content(test_factory, admin_user):
    """Create multiple content items for testing."""
    return test_factory.create_multiple_content(5, admin_user)


@pytest.fixture
def authenticated_admin_session(app, client, admin_user):
    """Provide an authenticated admin client session."""
    with app.app_context():
        db.create_all()
        db.session.add(admin_user)
        db.session.commit()

        AuthenticationTestMixin.login_user(client, admin_user)
        yield client


@pytest.fixture
def authenticated_user_session(app, client, regular_user):
    """Provide an authenticated regular user client session."""
    with app.app_context():
        db.create_all()
        db.session.add(regular_user)
        db.session.commit()

        AuthenticationTestMixin.login_user(client, regular_user)
        yield client


# Test decorators for common patterns
def requires_admin(test_func):
    """Decorator to mark tests that require admin privileges."""
    return pytest.mark.auth(test_func)


def slow_test(test_func):
    """Decorator to mark slow-running tests."""
    return pytest.mark.slow(test_func)


def performance_test(max_seconds: float):
    """Decorator to add performance constraints to tests."""

    def decorator(test_func):
        def wrapper(*args, **kwargs):
            mixin = PerformanceTestMixin()
            with mixin.assert_max_execution_time(max_seconds):
                return test_func(*args, **kwargs)

        wrapper.__name__ = test_func.__name__
        wrapper.__doc__ = test_func.__doc__
        return wrapper

    return decorator
