"""
Tests for the CLI create-admin command.

This module tests the create-admin CLI command which is responsible for:
1. Creating new admin users with email, name, and password
2. Promoting existing users to admin status
3. Handling various edge cases and validation scenarios

Test Organization:
- TestCreateAdminCommand: Tests for the main 'create-admin' command functionality
- TestCreateAdminValidation: Tests for input validation and edge cases
- TestCreateAdminIntegration: Integration tests with database and user model

Test Markers:
- unit: Unit tests that test individual functions in isolation
- integration: Integration tests that test multiple components together
- cli: Tests specifically for CLI command functionality

Example usage:
    # Run all create-admin tests
    pytest tests/cli/test_create_admin.py -v

    # Run with coverage
    pytest tests/cli/test_create_admin.py --cov=cli.create_admin --cov-report=term-missing

    # Run specific test
    pytest tests/cli/test_create_admin.py::TestCreateAdminCommand::test_create_admin_command_exists -v

    # Run only unit tests
    pytest tests/cli/test_create_admin.py -m unit -v

    # Run only integration tests
    pytest tests/cli/test_create_admin.py -m integration -v
"""

import pytest
import os
from typing import Dict, List, Optional, Any
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner

from cli.create_admin import create_admin
from models import User


# Constants for repeated strings to improve maintainability
class TestMessages:
    """Constants for expected test messages and validation."""

    # Success messages
    ALREADY_ADMIN = "is already an admin."
    PROMOTED_TO_ADMIN = "has been promoted to admin."
    NEW_ADMIN_CREATED = "New admin user"
    CREATED_SUCCESSFULLY = "created successfully."

    # Error messages
    NAME_PASSWORD_REQUIRED = (
        "Name and password are required to create a new admin user."
    )

    # Help text
    CREATE_ADMIN_HELP_TEXT = (
        "Create a new admin user or promote an existing user to admin"
    )

    # Command options
    EMAIL_OPTION = "--email"
    NAME_OPTION = "--name"
    PASSWORD_OPTION = "--password"


class TestData:
    """Test data constants and factories for consistent test data management."""

    # Default test data
    DEFAULT_EMAIL = "admin@example.com"
    DEFAULT_NAME = "Admin User"
    DEFAULT_PASSWORD = "secure_password123"

    # Test email formats
    VALID_EMAILS = [
        "user@example.com",
        "test.user+tag@domain.co.uk",
        "admin@subdomain.example.org",
        "user123@test-domain.com",
    ]

    # Test name formats
    VALID_NAMES = [
        "John Doe",
        "María García",
        "李小明",
        "Jean-Pierre O'Connor",
        "Dr. Smith Jr.",
        "A" * 100,  # Long name
    ]

    # Integration test users
    INTEGRATION_USERS = [
        {"email": "test1@example.com", "name": "Test User 1", "password": "pass1"},
        {"email": "test2@example.com", "name": "Test User 2", "password": "pass2"},
        {"email": "test3@example.com", "name": "Test User 3", "password": "pass3"},
    ]

    @classmethod
    def get_sample_user_data(cls) -> Dict[str, str]:
        """Get default sample user data for testing."""
        return {
            "email": cls.DEFAULT_EMAIL,
            "name": cls.DEFAULT_NAME,
            "password": cls.DEFAULT_PASSWORD,
        }

    @classmethod
    def get_unique_user_data(cls, suffix: str) -> Dict[str, str]:
        """Get unique user data with a suffix to avoid conflicts."""
        return {
            "email": f"user_{suffix}@example.com",
            "name": f"Test User {suffix}",
            "password": f"password_{suffix}",
        }


class CreateAdminTestHelpers:
    """Helper methods for create-admin command testing."""

    @staticmethod
    def create_mock_user(
        email: str = "test@example.com",
        name: str = "Test User",
        is_admin: bool = False,
        exists_in_db: bool = True,
    ) -> Mock:
        """
        Create a mock user with specified properties.

        Args:
            email: User email address
            name: User full name
            is_admin: Whether user has admin privileges
            exists_in_db: Whether user exists in database (affects ID)

        Returns:
            Mock user object with specified properties
        """
        mock_user = Mock(spec=User)
        mock_user.email = email
        mock_user.name = name
        mock_user.is_admin = is_admin
        mock_user.auth_type = "password"
        mock_user.set_password = Mock()

        if exists_in_db:
            mock_user.id = 1
        else:
            mock_user.id = None

        return mock_user

    @staticmethod
    def setup_user_query_mock(
        mock_user_query: Mock, user: Optional[Mock] = None
    ) -> Mock:
        """
        Setup User.query mock to return specified user or None.

        Args:
            mock_user_query: Mock User.query object
            user: User to return from query, or None if no user found

        Returns:
            Mock filter_by object for additional assertions
        """
        mock_filter_by = Mock()
        mock_user_query.filter_by.return_value = mock_filter_by
        mock_filter_by.first.return_value = user
        return mock_filter_by

    @staticmethod
    def assert_command_success(
        result: Any, expected_output_fragments: Optional[List[str]] = None
    ) -> None:
        """
        Assert that a CLI command executed successfully.

        Args:
            result: Click test result object
            expected_output_fragments: List of strings that should appear in output
        """
        assert result.exit_code == 0, f"Command failed with output: {result.output}"
        if expected_output_fragments:
            for fragment in expected_output_fragments:
                assert (
                    fragment in result.output
                ), f"Expected '{fragment}' in output: {result.output}"

    @staticmethod
    def assert_command_failure(result: Any, expected_exit_code: int = 1) -> None:
        """
        Assert that a CLI command failed as expected.

        Args:
            result: Click test result object
            expected_exit_code: Expected non-zero exit code
        """
        assert (
            result.exit_code == expected_exit_code
        ), f"Expected exit code {expected_exit_code}, got {result.exit_code}"

    @staticmethod
    def assert_user_created_with_properties(
        mock_user_class: Mock,
        email: str,
        name: str,
        is_admin: bool = True,
        auth_type: str = "password",
    ) -> None:
        """
        Assert that a User was created with the expected properties.

        Args:
            mock_user_class: Mock User class
            email: Expected email address
            name: Expected full name
            is_admin: Expected admin status
            auth_type: Expected authentication type
        """
        mock_user_class.assert_called_once()
        call_kwargs = mock_user_class.call_args[1]
        assert call_kwargs["email"] == email
        assert call_kwargs["name"] == name
        assert call_kwargs["is_admin"] == is_admin
        assert call_kwargs["auth_type"] == auth_type

    @staticmethod
    def cleanup_test_users(session: Any, emails: List[str]) -> None:
        """
        Clean up test users from database after integration tests.

        Args:
            session: Database session
            emails: List of email addresses to clean up
        """
        for email in emails:
            user = session.query(User).filter_by(email=email).first()
            if user:
                session.delete(user)
        session.commit()

    @staticmethod
    def validate_user_properties(user: User, expected_data: Dict[str, Any]) -> None:
        """
        Validate that a user has the expected properties.

        Args:
            user: User object to validate
            expected_data: Dictionary of expected properties
        """
        for key, expected_value in expected_data.items():
            actual_value = getattr(user, key)
            assert (
                actual_value == expected_value
            ), f"Expected {key}={expected_value}, got {actual_value}"


# Pytest fixtures for common test setup
@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a Click CLI runner for testing."""
    return CliRunner()


@pytest.fixture
def mock_user_factory():
    """Provide a factory function for creating mock users."""
    return CreateAdminTestHelpers.create_mock_user


@pytest.fixture
def sample_user_data() -> Dict[str, str]:
    """Provide sample user data for testing."""
    return TestData.get_sample_user_data()


@pytest.fixture
def unique_user_data():
    """Provide a factory for unique user data to avoid test conflicts."""
    counter = 0

    def _get_unique_data():
        nonlocal counter
        counter += 1
        return TestData.get_unique_user_data(str(counter))

    return _get_unique_data


# Skip CLI integration tests during parallel execution
# CLI commands create their own app context which bypasses test fixtures
skip_if_parallel = pytest.mark.skipif(
    os.environ.get("PYTEST_XDIST_WORKER") is not None,
    reason="CLI integration tests are incompatible with parallel execution",
)


@pytest.mark.cli
@pytest.mark.unit
class TestCreateAdminCommand:
    """Test suite for the create-admin CLI command basic functionality."""

    def test_create_admin_command_exists(self, app: Any, cli_runner: CliRunner) -> None:
        """Test that the create-admin command is properly registered."""
        with app.app_context():
            result = cli_runner.invoke(create_admin, ["--help"])
            CreateAdminTestHelpers.assert_command_success(
                result, [TestMessages.CREATE_ADMIN_HELP_TEXT]
            )

    def test_create_admin_command_help_text(
        self, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test that the create-admin command help text is correct."""
        with app.app_context():
            result = cli_runner.invoke(create_admin, ["--help"])
            CreateAdminTestHelpers.assert_command_success(
                result,
                [
                    TestMessages.CREATE_ADMIN_HELP_TEXT,
                    TestMessages.EMAIL_OPTION,
                    TestMessages.NAME_OPTION,
                    TestMessages.PASSWORD_OPTION,
                ],
            )

    @patch("cli.create_admin.User")
    @patch("cli.create_admin.db")
    def test_promote_existing_user_to_admin(
        self,
        mock_db: Mock,
        mock_user_class: Mock,
        app: Any,
        cli_runner: CliRunner,
        mock_user_factory: Any,
        sample_user_data: Dict[str, str],
    ) -> None:
        """Test promoting an existing non-admin user to admin."""
        with app.app_context():
            # Setup existing non-admin user
            existing_user = mock_user_factory(
                email=sample_user_data["email"],
                name=sample_user_data["name"],
                is_admin=False,
            )
            CreateAdminTestHelpers.setup_user_query_mock(
                mock_user_class.query, existing_user
            )

            result = cli_runner.invoke(
                create_admin, [TestMessages.EMAIL_OPTION, sample_user_data["email"]]
            )

            # Verify command succeeded
            CreateAdminTestHelpers.assert_command_success(
                result, [sample_user_data["email"], TestMessages.PROMOTED_TO_ADMIN]
            )

            # Verify user was promoted to admin
            assert existing_user.is_admin is True
            mock_db.session.commit.assert_called_once()

    @patch("cli.create_admin.User")
    @patch("cli.create_admin.db")
    def test_existing_admin_user_no_change(
        self,
        mock_db: Mock,
        mock_user_class: Mock,
        app: Any,
        cli_runner: CliRunner,
        mock_user_factory: Any,
        sample_user_data: Dict[str, str],
    ) -> None:
        """Test that existing admin users are not modified."""
        with app.app_context():
            # Setup existing admin user
            existing_admin = mock_user_factory(
                email=sample_user_data["email"],
                name=sample_user_data["name"],
                is_admin=True,
            )
            CreateAdminTestHelpers.setup_user_query_mock(
                mock_user_class.query, existing_admin
            )

            result = cli_runner.invoke(
                create_admin, [TestMessages.EMAIL_OPTION, sample_user_data["email"]]
            )

            # Verify command succeeded with appropriate message
            CreateAdminTestHelpers.assert_command_success(
                result, [sample_user_data["email"], TestMessages.ALREADY_ADMIN]
            )

            # Verify no database changes were made
            mock_db.session.commit.assert_not_called()

    @patch("cli.create_admin.User")
    @patch("cli.create_admin.db")
    def test_create_new_admin_user_success(
        self,
        mock_db: Mock,
        mock_user_class: Mock,
        app: Any,
        cli_runner: CliRunner,
        sample_user_data: Dict[str, str],
    ) -> None:
        """Test creating a new admin user successfully."""
        with app.app_context():
            # Setup no existing user
            CreateAdminTestHelpers.setup_user_query_mock(mock_user_class.query, None)

            # Mock User constructor
            mock_new_user = Mock(spec=User)
            mock_user_class.return_value = mock_new_user

            result = cli_runner.invoke(
                create_admin,
                [
                    TestMessages.EMAIL_OPTION,
                    sample_user_data["email"],
                    TestMessages.NAME_OPTION,
                    sample_user_data["name"],
                    TestMessages.PASSWORD_OPTION,
                    sample_user_data["password"],
                ],
            )

            # Verify command succeeded
            CreateAdminTestHelpers.assert_command_success(
                result,
                [
                    TestMessages.NEW_ADMIN_CREATED,
                    sample_user_data["email"],
                    TestMessages.CREATED_SUCCESSFULLY,
                ],
            )

            # Verify user was created with correct properties
            CreateAdminTestHelpers.assert_user_created_with_properties(
                mock_user_class, sample_user_data["email"], sample_user_data["name"]
            )

            # Verify password was set and user was saved
            mock_new_user.set_password.assert_called_once_with(
                sample_user_data["password"]
            )
            mock_db.session.add.assert_called_once_with(mock_new_user)
            mock_db.session.commit.assert_called_once()

    @patch("cli.create_admin.User")
    def test_create_new_user_missing_name(
        self,
        mock_user_class: Mock,
        app: Any,
        cli_runner: CliRunner,
        sample_user_data: Dict[str, str],
    ) -> None:
        """Test creating new user fails when name is missing."""
        with app.app_context():
            # Setup no existing user
            CreateAdminTestHelpers.setup_user_query_mock(mock_user_class.query, None)

            result = cli_runner.invoke(
                create_admin,
                [
                    TestMessages.EMAIL_OPTION,
                    sample_user_data["email"],
                    TestMessages.PASSWORD_OPTION,
                    sample_user_data["password"],
                    # Missing --name
                ],
            )

            # Verify command succeeded but with error message
            CreateAdminTestHelpers.assert_command_success(
                result, [TestMessages.NAME_PASSWORD_REQUIRED]
            )

    @patch("cli.create_admin.User")
    def test_create_new_user_missing_password(
        self,
        mock_user_class: Mock,
        app: Any,
        cli_runner: CliRunner,
        sample_user_data: Dict[str, str],
    ) -> None:
        """Test creating new user fails when password is missing."""
        with app.app_context():
            # Setup no existing user
            CreateAdminTestHelpers.setup_user_query_mock(mock_user_class.query, None)

            result = cli_runner.invoke(
                create_admin,
                [
                    TestMessages.EMAIL_OPTION,
                    sample_user_data["email"],
                    TestMessages.NAME_OPTION,
                    sample_user_data["name"],
                    # Missing --password
                ],
            )

            # Verify command succeeded but with error message
            CreateAdminTestHelpers.assert_command_success(
                result, [TestMessages.NAME_PASSWORD_REQUIRED]
            )

    @patch("cli.create_admin.User")
    def test_create_new_user_missing_both_name_and_password(
        self,
        mock_user_class: Mock,
        app: Any,
        cli_runner: CliRunner,
        sample_user_data: Dict[str, str],
    ) -> None:
        """Test creating new user fails when both name and password are missing."""
        with app.app_context():
            # Setup no existing user
            CreateAdminTestHelpers.setup_user_query_mock(mock_user_class.query, None)

            result = cli_runner.invoke(
                create_admin, [TestMessages.EMAIL_OPTION, sample_user_data["email"]]
            )

            # Verify command succeeded but with error message
            CreateAdminTestHelpers.assert_command_success(
                result, [TestMessages.NAME_PASSWORD_REQUIRED]
            )


@pytest.mark.cli
@pytest.mark.unit
class TestCreateAdminValidation:
    """Test suite for create-admin command input validation and edge cases."""

    @pytest.mark.parametrize("email", TestData.VALID_EMAILS)
    @patch("cli.create_admin.User")
    @patch("cli.create_admin.db")
    def test_valid_email_formats(
        self,
        mock_db: Mock,
        mock_user_class: Mock,
        app: Any,
        cli_runner: CliRunner,
        email: str,
    ) -> None:
        """Test that various valid email formats are accepted."""
        with app.app_context():
            # Setup no existing user
            CreateAdminTestHelpers.setup_user_query_mock(mock_user_class.query, None)
            mock_user_class.return_value = Mock(spec=User)

            result = cli_runner.invoke(
                create_admin,
                [
                    TestMessages.EMAIL_OPTION,
                    email,
                    TestMessages.NAME_OPTION,
                    "Test User",
                    TestMessages.PASSWORD_OPTION,
                    "password123",
                ],
            )

            # Verify command succeeded
            CreateAdminTestHelpers.assert_command_success(
                result, [TestMessages.NEW_ADMIN_CREATED, email]
            )

    @pytest.mark.parametrize("name", TestData.VALID_NAMES)
    @patch("cli.create_admin.User")
    @patch("cli.create_admin.db")
    def test_valid_name_formats(
        self,
        mock_db: Mock,
        mock_user_class: Mock,
        app: Any,
        cli_runner: CliRunner,
        name: str,
    ) -> None:
        """Test that various valid name formats are accepted."""
        with app.app_context():
            # Setup no existing user
            CreateAdminTestHelpers.setup_user_query_mock(mock_user_class.query, None)
            mock_user_class.return_value = Mock(spec=User)

            result = cli_runner.invoke(
                create_admin,
                [
                    TestMessages.EMAIL_OPTION,
                    "test@example.com",
                    TestMessages.NAME_OPTION,
                    name,
                    TestMessages.PASSWORD_OPTION,
                    "password123",
                ],
            )

            # Verify command succeeded
            CreateAdminTestHelpers.assert_command_success(
                result, [TestMessages.NEW_ADMIN_CREATED, "test@example.com"]
            )

    @patch("cli.create_admin.User")
    @patch("cli.create_admin.db")
    def test_database_error_handling(
        self,
        mock_db: Mock,
        mock_user_class: Mock,
        app: Any,
        cli_runner: CliRunner,
        sample_user_data: Dict[str, str],
    ) -> None:
        """Test handling of database errors during user creation."""
        with app.app_context():
            # Setup no existing user
            CreateAdminTestHelpers.setup_user_query_mock(mock_user_class.query, None)
            mock_user_class.return_value = Mock(spec=User)

            # Mock database error
            mock_db.session.commit.side_effect = Exception("Database error")

            result = cli_runner.invoke(
                create_admin,
                [
                    TestMessages.EMAIL_OPTION,
                    sample_user_data["email"],
                    TestMessages.NAME_OPTION,
                    sample_user_data["name"],
                    TestMessages.PASSWORD_OPTION,
                    sample_user_data["password"],
                ],
            )

            # Verify command failed due to database error
            assert result.exit_code != 0
            assert result.exception is not None

    @patch("cli.create_admin.User")
    def test_user_query_error_handling(
        self,
        mock_user_class: Mock,
        app: Any,
        cli_runner: CliRunner,
        sample_user_data: Dict[str, str],
    ) -> None:
        """Test handling of database query errors."""
        with app.app_context():
            # Mock query error
            mock_user_class.query.filter_by.side_effect = Exception("Query error")

            result = cli_runner.invoke(
                create_admin, [TestMessages.EMAIL_OPTION, sample_user_data["email"]]
            )

            # Verify command failed due to query error
            assert result.exit_code != 0
            assert result.exception is not None


@pytest.mark.cli
@pytest.mark.integration
@skip_if_parallel
class TestCreateAdminIntegration:
    """Integration tests for create-admin CLI command with real database operations."""

    def test_create_admin_command_with_real_database(
        self,
        app: Any,
        cli_runner: CliRunner,
        session: Any,
        unique_user_data: Any,
        cli_test_env: Any,
    ) -> None:
        """Test create-admin command with actual database operations."""
        with app.app_context():
            user_data = unique_user_data()
            email = user_data["email"]
            name = user_data["name"]
            password = user_data["password"]

            try:
                # Verify user doesn't exist initially
                existing_user = User.query.filter_by(email=email).first()
                assert existing_user is None

                result = cli_runner.invoke(
                    create_admin,
                    [
                        TestMessages.EMAIL_OPTION,
                        email,
                        TestMessages.NAME_OPTION,
                        name,
                        TestMessages.PASSWORD_OPTION,
                        password,
                    ],
                )

                # Verify command succeeded
                CreateAdminTestHelpers.assert_command_success(
                    result,
                    [
                        TestMessages.NEW_ADMIN_CREATED,
                        email,
                        TestMessages.CREATED_SUCCESSFULLY,
                    ],
                )

                # Verify user was actually created in database
                created_user = User.query.filter_by(email=email).first()
                assert created_user is not None

                # Validate user properties
                expected_properties = {
                    "email": email,
                    "name": name,
                    "is_admin": True,
                    "auth_type": "password",
                }
                CreateAdminTestHelpers.validate_user_properties(
                    created_user, expected_properties
                )
                assert created_user.check_password(password) is True

            finally:
                # Cleanup
                CreateAdminTestHelpers.cleanup_test_users(session, [email])

    def test_promote_real_user_to_admin(
        self,
        app: Any,
        cli_runner: CliRunner,
        session: Any,
        unique_user_data: Any,
        cli_test_env: Any,
    ) -> None:
        """Test promoting a real existing user to admin."""
        with app.app_context():
            user_data = unique_user_data()
            email = user_data["email"]
            name = user_data["name"]

            try:
                # Create a non-admin user first
                user = User(
                    email=email, name=name, auth_type="password", is_admin=False
                )
                user.set_password("initial_password")
                session.add(user)
                session.commit()

                # Verify user is not admin initially
                assert user.is_admin is False

                result = cli_runner.invoke(
                    create_admin, [TestMessages.EMAIL_OPTION, email]
                )

                # Verify command succeeded
                CreateAdminTestHelpers.assert_command_success(
                    result, [email, TestMessages.PROMOTED_TO_ADMIN]
                )

                # Verify user was promoted to admin
                session.refresh(user)
                assert user.is_admin is True

            finally:
                # Cleanup
                CreateAdminTestHelpers.cleanup_test_users(session, [email])

    def test_existing_admin_no_change_real_database(
        self,
        app: Any,
        cli_runner: CliRunner,
        session: Any,
        unique_user_data: Any,
        cli_test_env: Any,
    ) -> None:
        """Test that existing admin users are not modified in real database."""
        with app.app_context():
            user_data = unique_user_data()
            email = user_data["email"]
            name = user_data["name"]

            try:
                # Create an admin user first
                user = User(email=email, name=name, auth_type="password", is_admin=True)
                user.set_password("admin_password")
                session.add(user)
                session.commit()

                # Store original values
                original_password_hash = user.password_hash
                original_created_at = user.created_at

                result = cli_runner.invoke(
                    create_admin, [TestMessages.EMAIL_OPTION, email]
                )

                # Verify command succeeded with appropriate message
                CreateAdminTestHelpers.assert_command_success(
                    result, [email, TestMessages.ALREADY_ADMIN]
                )

                # Verify user properties remain unchanged
                session.refresh(user)
                assert user.is_admin is True
                assert user.password_hash == original_password_hash
                assert user.created_at == original_created_at

            finally:
                # Cleanup
                CreateAdminTestHelpers.cleanup_test_users(session, [email])

    def test_command_preserves_app_context(
        self, app: Any, cli_runner: CliRunner, cli_test_env: Any
    ) -> None:
        """Test that create-admin command preserves Flask app context."""
        with app.app_context():
            result = cli_runner.invoke(
                create_admin,
                [
                    TestMessages.EMAIL_OPTION,
                    "context@example.com",
                    TestMessages.NAME_OPTION,
                    "Context Test",
                    TestMessages.PASSWORD_OPTION,
                    "password123",
                ],
            )

            # Verify command succeeded and context is preserved
            CreateAdminTestHelpers.assert_command_success(result)
            # The @with_appcontext decorator should ensure the app context is available

    @pytest.mark.parametrize("user_data", TestData.INTEGRATION_USERS)
    def test_multiple_admin_creation(
        self,
        app: Any,
        cli_runner: CliRunner,
        session: Any,
        user_data: Dict[str, str],
        cli_test_env: Any,
    ) -> None:
        """Test creating multiple admin users in sequence."""
        with app.app_context():
            email = user_data["email"]

            try:
                result = cli_runner.invoke(
                    create_admin,
                    [
                        TestMessages.EMAIL_OPTION,
                        user_data["email"],
                        TestMessages.NAME_OPTION,
                        user_data["name"],
                        TestMessages.PASSWORD_OPTION,
                        user_data["password"],
                    ],
                )

                # Verify command succeeded
                CreateAdminTestHelpers.assert_command_success(
                    result, [TestMessages.NEW_ADMIN_CREATED, user_data["email"]]
                )

                # Verify user was created correctly
                created_user = User.query.filter_by(email=user_data["email"]).first()
                assert created_user is not None
                assert created_user.is_admin is True

            finally:
                # Cleanup
                CreateAdminTestHelpers.cleanup_test_users(session, [email])

    def test_command_imports_and_dependencies(
        self, app: Any, cli_test_env: Any
    ) -> None:
        """Test that all necessary imports and dependencies are available."""
        with app.app_context():
            # Test that the imported modules are accessible
            from cli.create_admin import click, db, User

            # Verify imports are not None
            required_imports = [click, db, User]
            for import_obj in required_imports:
                assert import_obj is not None

            # Verify User model has required methods
            assert hasattr(User, "query")
            assert hasattr(User, "set_password")
            assert callable(getattr(User, "set_password", None))

    def test_user_model_integration(
        self, app: Any, session: Any, unique_user_data: Any, cli_test_env: Any
    ) -> None:
        """Test integration with User model methods and properties."""
        with app.app_context():
            user_data = unique_user_data()
            email = user_data["email"]
            name = user_data["name"]
            password = user_data["password"]

            try:
                # Create user using the same pattern as the CLI command
                user = User(email=email, name=name, auth_type="password", is_admin=True)
                user.set_password(password)
                session.add(user)
                session.commit()

                # Verify all expected properties are set correctly
                expected_properties = {
                    "email": email,
                    "name": name,
                    "is_admin": True,
                    "auth_type": "password",
                }
                CreateAdminTestHelpers.validate_user_properties(
                    user, expected_properties
                )

                assert user.password_hash is not None
                assert user.check_password(password) is True
                assert user.check_password("wrong_password") is False

            finally:
                # Cleanup
                CreateAdminTestHelpers.cleanup_test_users(session, [email])
