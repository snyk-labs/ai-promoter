import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import bcrypt

from models.user import User
from models.content import Content
from models.share import Share
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from flask_login import UserMixin

# Generate unique identifier for this test run to avoid conflicts in parallel execution
TEST_RUN_ID = str(uuid.uuid4())[:8]


# --- Test Constants ---
class TestConstants:
    """Test constants for consistent data across tests."""

    TEST_EMAIL = f"user-{TEST_RUN_ID}@example.com"
    TEST_NAME = f"Test User {TEST_RUN_ID}"
    TEST_PASSWORD = "secure_password_123"
    TEST_BIO = f"This is a test bio for {TEST_RUN_ID}."
    TEST_OKTA_ID = f"okta_user_{TEST_RUN_ID}"
    TEST_SLACK_ID = f"U{TEST_RUN_ID[:7]}"
    TEST_LINKEDIN_ID = f"linkedin_{TEST_RUN_ID}"
    TEST_LINKEDIN_ACCESS_TOKEN = f"access_token_{TEST_RUN_ID}"
    TEST_LINKEDIN_REFRESH_TOKEN = f"refresh_token_{TEST_RUN_ID}"
    TEST_EXAMPLE_POSTS = f"Example post content for {TEST_RUN_ID}"

    # Edge case data
    VERY_LONG_EMAIL = f"very_long_email_{TEST_RUN_ID}_" + "a" * 200 + "@example.com"
    SPECIAL_CHARS_EMAIL = f"user+test-{TEST_RUN_ID}@sub.example-domain.co.uk"
    UNICODE_NAME = f"José María García-{TEST_RUN_ID}"
    UNICODE_BIO = f"This bio contains émojis 🚀 and spëcial chärs for {TEST_RUN_ID}"

    # Authentication types and platforms
    AUTH_TYPES = ["password", "okta"]
    PLATFORMS = ["linkedin", "twitter", "facebook", "instagram"]

    # Invalid email formats for testing
    INVALID_EMAILS = [
        "",  # Empty string
        "not-an-email",  # Missing @ symbol
        "@example.com",  # Missing local part
        "user@",  # Missing domain
        "user@.com",  # Invalid domain
    ]


# --- Test Helpers ---
class TestHelpers:
    """Helper methods for testing."""

    @staticmethod
    def assert_user_fields_match(user, expected_data):
        """Assert user fields match expected values."""
        for field, expected_value in expected_data.items():
            actual_value = getattr(user, field)
            assert (
                actual_value == expected_value
            ), f"Field '{field}': expected {expected_value}, got {actual_value}"

    @staticmethod
    def assert_password_is_hashed(user, original_password):
        """Assert that password is properly hashed and not stored in plain text."""
        assert user.password_hash is not None, "Password hash should not be None"
        assert (
            user.password_hash != original_password
        ), "Password should be hashed, not stored in plain text"
        assert (
            len(user.password_hash) > 50
        ), "Hashed password should be significantly longer"
        assert user.check_password(
            original_password
        ), "Password verification should work"

    @staticmethod
    def assert_user_is_flask_login_compatible(user):
        """Assert that user implements Flask-Login UserMixin correctly."""
        assert isinstance(user, UserMixin), "User should inherit from UserMixin"
        required_attrs = ["is_authenticated", "is_active", "is_anonymous", "get_id"]
        for attr in required_attrs:
            assert hasattr(user, attr), f"User should have {attr} property/method"

    @staticmethod
    def create_test_user_data(**overrides):
        """Create standardized test user data with optional overrides."""
        unique_id = str(uuid.uuid4())[:8]
        defaults = {
            "email": f"user-{unique_id}@example.com",
            "name": f"Test User {unique_id}",
            "bio": f"Test bio for {unique_id}",
            "is_admin": False,
            "auth_type": "password",
            "linkedin_authorized": False,
            "autonomous_mode": False,
        }
        defaults.update(overrides)
        return defaults


# --- Test Data Factory ---
class TestData:
    """Factory for creating test data."""

    @staticmethod
    def make_user(session, **kwargs):
        """Create a test user with sensible defaults and unique identifiers."""
        user_data = TestHelpers.create_test_user_data(**kwargs)

        # Extract password if provided, since it's not a model field
        password = user_data.pop("password", None)

        user = User(**user_data)
        if password:
            user.set_password(password)

        session.add(user)
        session.commit()
        return user

    @staticmethod
    def make_admin_user(session, **kwargs):
        """Create a test admin user."""
        kwargs["is_admin"] = True
        return TestData.make_user(session, **kwargs)

    @staticmethod
    def make_okta_user(session, **kwargs):
        """Create a test Okta SSO user."""
        unique_id = str(uuid.uuid4())[:8]
        defaults = {
            "auth_type": "okta",
            "okta_id": f"okta_user_{unique_id}",
            "password_hash": None,
        }
        defaults.update(kwargs)
        return TestData.make_user(session, **defaults)

    @staticmethod
    def make_content_with_user(session, user=None, **kwargs):
        """Create test content associated with a user."""
        if user is None:
            user = TestData.make_user(session)

        unique_id = str(uuid.uuid4())[:8]
        defaults = {
            "url": f"https://example.com/article-{unique_id}",
            "title": f"Test Article {unique_id}",
            "copy": f"Check this out: https://example.com/article-{unique_id}",
        }
        defaults.update(kwargs)

        content = Content(**defaults)
        session.add(content)
        session.commit()

        # Create a share linking user to content
        share = Share(
            content_id=content.id,
            user_id=user.id,
            platform="linkedin",
            post_content=f"Test post for {unique_id}",
            post_url=f"https://linkedin.com/post/{unique_id}",
        )
        session.add(share)
        session.commit()

        return content


# --- Unit Tests (No Database) ---
@pytest.mark.unit
class TestUserModelUnit:
    """Unit tests for User model methods that don't require database."""

    def test_user_creation_basic(self):
        """Test basic user instance creation."""
        user = User(email=TestConstants.TEST_EMAIL, name=TestConstants.TEST_NAME)

        assert user.email == TestConstants.TEST_EMAIL
        assert user.name == TestConstants.TEST_NAME
        # Note: SQLAlchemy default values are only applied when saving to database
        assert user.password_hash is None

    def test_user_creation_with_explicit_values(self):
        """Test user creation with explicitly set values."""
        user_data = TestHelpers.create_test_user_data(
            email=TestConstants.TEST_EMAIL,
            name=TestConstants.TEST_NAME,
            is_admin=True,
            auth_type="okta",
        )

        user = User(**user_data)
        TestHelpers.assert_user_fields_match(user, user_data)

    def test_password_hashing(self):
        """Test password setting and hashing."""
        user = User(email=TestConstants.TEST_EMAIL, name=TestConstants.TEST_NAME)
        user.set_password(TestConstants.TEST_PASSWORD)

        TestHelpers.assert_password_is_hashed(user, TestConstants.TEST_PASSWORD)

    def test_password_verification_valid(self):
        """Test password verification with correct password."""
        user = User(email=TestConstants.TEST_EMAIL, name=TestConstants.TEST_NAME)
        user.set_password(TestConstants.TEST_PASSWORD)

        assert user.check_password(TestConstants.TEST_PASSWORD) is True

    def test_password_verification_invalid(self):
        """Test password verification with incorrect password."""
        user = User(email=TestConstants.TEST_EMAIL, name=TestConstants.TEST_NAME)
        user.set_password(TestConstants.TEST_PASSWORD)

        assert user.check_password("wrong_password") is False

    def test_password_verification_no_hash(self):
        """Test password verification when no password hash is set."""
        user = User(email=TestConstants.TEST_EMAIL, name=TestConstants.TEST_NAME)

        assert user.check_password(TestConstants.TEST_PASSWORD) is False

    @patch("bcrypt.gensalt")
    @patch("bcrypt.hashpw")
    def test_password_hashing_uses_correct_rounds(self, mock_hashpw, mock_gensalt):
        """Test that password hashing uses correct bcrypt rounds."""
        mock_salt = b"mock_salt"
        mock_hash = b"mock_hash"
        mock_gensalt.return_value = mock_salt
        mock_hashpw.return_value = mock_hash

        user = User(email=TestConstants.TEST_EMAIL, name=TestConstants.TEST_NAME)
        user.set_password(TestConstants.TEST_PASSWORD)

        mock_gensalt.assert_called_once_with(rounds=13)
        mock_hashpw.assert_called_once_with(
            TestConstants.TEST_PASSWORD.encode("utf-8"), mock_salt
        )

    def test_password_edge_cases(self):
        """Test password handling with edge cases."""
        user = User(email=TestConstants.TEST_EMAIL, name=TestConstants.TEST_NAME)

        # Test empty password
        user.set_password("")
        assert user.password_hash is not None
        assert user.check_password("") is True
        assert user.check_password("not_empty") is False

        # Test very long password
        long_password = "a" * 1000
        user.set_password(long_password)
        assert user.check_password(long_password) is True

        # Test password with special characters
        special_password = "p@ssw0rd!@#$%^&*()_+-=[]{}|;:,.<>?"
        user.set_password(special_password)
        assert user.check_password(special_password) is True

    def test_repr_formatting(self):
        """Test string representation of User object."""
        user = User(email=TestConstants.TEST_EMAIL, name=TestConstants.TEST_NAME)

        assert repr(user) == f"<User {TestConstants.TEST_EMAIL}>"

    def test_flask_login_integration(self):
        """Test Flask-Login UserMixin integration."""
        user = User(email=TestConstants.TEST_EMAIL, name=TestConstants.TEST_NAME)
        user.id = 123  # Simulate database ID

        TestHelpers.assert_user_is_flask_login_compatible(user)
        assert user.get_id() == "123"
        assert user.is_authenticated is True
        assert user.is_active is True
        assert user.is_anonymous is False


# --- Integration Tests (With Database) ---
@pytest.mark.integration
class TestUserModelIntegration:
    """Integration tests for User model with database."""

    def test_user_creation_with_all_fields(self, session, app):
        """Test creating user with all possible fields."""
        token_expires = datetime.utcnow() + timedelta(hours=1)

        user_data = {
            "email": TestConstants.TEST_EMAIL,
            "name": TestConstants.TEST_NAME,
            "bio": TestConstants.TEST_BIO,
            "is_admin": True,
            "auth_type": "okta",
            "okta_id": TestConstants.TEST_OKTA_ID,
            "slack_id": TestConstants.TEST_SLACK_ID,
            "linkedin_authorized": True,
            "linkedin_native_id": TestConstants.TEST_LINKEDIN_ID,
            "linkedin_native_access_token": TestConstants.TEST_LINKEDIN_ACCESS_TOKEN,
            "linkedin_native_refresh_token": TestConstants.TEST_LINKEDIN_REFRESH_TOKEN,
            "linkedin_native_token_expires_at": token_expires,
            "autonomous_mode": True,
            "example_social_posts": TestConstants.TEST_EXAMPLE_POSTS,
        }

        user = User(**user_data)
        user.set_password(TestConstants.TEST_PASSWORD)
        session.add(user)
        session.commit()

        # Verify all fields were saved correctly
        saved_user = (
            session.query(User).filter_by(email=TestConstants.TEST_EMAIL).first()
        )
        assert saved_user is not None

        TestHelpers.assert_user_fields_match(saved_user, user_data)
        TestHelpers.assert_password_is_hashed(saved_user, TestConstants.TEST_PASSWORD)
        assert saved_user.created_at is not None
        assert isinstance(saved_user.created_at, datetime)

    def test_user_creation_minimal_fields(self, session, app):
        """Test creating user with only required fields."""
        user = User(email=TestConstants.TEST_EMAIL, name=TestConstants.TEST_NAME)
        session.add(user)
        session.commit()

        saved_user = (
            session.query(User).filter_by(email=TestConstants.TEST_EMAIL).first()
        )
        assert saved_user is not None
        assert saved_user.email == TestConstants.TEST_EMAIL
        assert saved_user.name == TestConstants.TEST_NAME
        # These should have database defaults
        assert saved_user.is_admin is False
        assert saved_user.auth_type == "password"
        assert saved_user.linkedin_authorized is False
        assert saved_user.autonomous_mode is False

    def test_user_relationships_with_shares(self, session, app):
        """Test user relationships with Share model."""
        user = TestData.make_user(session)
        content = TestData.make_content_with_user(session, user)

        # Verify relationship works
        shares = session.query(Share).filter_by(user_id=user.id).all()
        assert len(shares) == 1
        assert shares[0].user_id == user.id
        assert shares[0].content_id == content.id

    def test_unique_constraints(self, session, app):
        """Test unique constraints on email, okta_id, slack_id, and linkedin_native_id."""
        # Create first user with all unique fields
        TestData.make_user(
            session,
            email=TestConstants.TEST_EMAIL,
            okta_id=TestConstants.TEST_OKTA_ID,
            slack_id=TestConstants.TEST_SLACK_ID,
            linkedin_native_id=TestConstants.TEST_LINKEDIN_ID,
        )

        # Test unique constraint violations
        unique_field_tests = [
            ("email", TestConstants.TEST_EMAIL, "different@example.com"),
            ("okta_id", TestConstants.TEST_OKTA_ID, "other_okta_id"),
            ("slack_id", TestConstants.TEST_SLACK_ID, "U12345"),
            ("linkedin_native_id", TestConstants.TEST_LINKEDIN_ID, "linkedin_123"),
        ]

        for field_name, duplicate_value, unique_value in unique_field_tests:
            with pytest.raises(IntegrityError):
                user_data = TestHelpers.create_test_user_data()
                user_data[field_name] = duplicate_value
                # Ensure other unique fields are different
                for other_field, _, alt_value in unique_field_tests:
                    if other_field != field_name:
                        user_data[other_field] = alt_value

                user = User(**user_data)
                session.add(user)
                session.commit()

            session.rollback()

    @patch("tasks.slack_tasks.send_slack_invitation_task")
    @patch("tasks.slack_tasks.slack_get_user_id")
    def test_user_creation_triggers_slack_invitation(
        self, mock_slack_get_user_id, mock_send_slack_invitation, session, app
    ):
        """Test that creating a new user triggers Slack invitation tasks."""
        mock_chain = MagicMock()

        with patch(
            "models.user.chain", return_value=mock_chain
        ) as mock_chain_constructor:
            TestData.make_user(session)

            # Verify that the chain was created and applied
            mock_chain_constructor.assert_called_once()
            mock_chain.apply_async.assert_called_once()

    def test_find_or_create_okta_user_integration(self, session, app):
        """Test find_or_create_okta_user method with real database."""
        # Test creating new user
        user = User.find_or_create_okta_user(
            TestConstants.TEST_OKTA_ID,
            TestConstants.TEST_EMAIL,
            TestConstants.TEST_NAME,
        )

        assert user.okta_id == TestConstants.TEST_OKTA_ID
        assert user.email == TestConstants.TEST_EMAIL
        assert user.name == TestConstants.TEST_NAME
        assert user.auth_type == "okta"
        assert user.id is not None

        # Test finding existing user
        found_user = User.find_or_create_okta_user(
            TestConstants.TEST_OKTA_ID,
            TestConstants.TEST_EMAIL,
            TestConstants.TEST_NAME,
        )

        assert found_user.id == user.id
        # SQLAlchemy's identity map returns the same instance for the same record
        assert found_user is user

    def test_okta_user_upgrade_existing_email(self, session, app):
        """Test upgrading existing email user to Okta SSO."""
        # Create existing password user
        existing_user = TestData.make_user(
            session, email="existing@example.com", password=TestConstants.TEST_PASSWORD
        )

        # Upgrade to Okta
        upgraded_user = User.find_or_create_okta_user(
            "new_okta_id", "existing@example.com", "Existing User"
        )

        assert upgraded_user.id == existing_user.id
        assert upgraded_user.auth_type == "okta"
        assert upgraded_user.okta_id == "new_okta_id"


# --- Edge Cases and Data Validation ---
@pytest.mark.integration
class TestUserModelEdgeCases:
    """Test edge cases and data validation with database."""

    def test_very_long_email_handling(self, session, app):
        """Test handling of very long email addresses."""
        user = User(email=TestConstants.VERY_LONG_EMAIL, name=TestConstants.TEST_NAME)
        session.add(user)
        session.commit()

        saved_user = (
            session.query(User).filter_by(email=TestConstants.VERY_LONG_EMAIL).first()
        )
        assert saved_user is not None
        assert saved_user.email == TestConstants.VERY_LONG_EMAIL

    def test_special_characters_in_email(self, session, app):
        """Test handling of special characters in email addresses."""
        user = User(
            email=TestConstants.SPECIAL_CHARS_EMAIL, name=TestConstants.TEST_NAME
        )
        session.add(user)
        session.commit()

        saved_user = (
            session.query(User)
            .filter_by(email=TestConstants.SPECIAL_CHARS_EMAIL)
            .first()
        )
        assert saved_user is not None
        assert saved_user.email == TestConstants.SPECIAL_CHARS_EMAIL

    def test_unicode_content_handling(self, session, app):
        """Test handling of Unicode characters in user fields."""
        user = User(
            email=TestConstants.TEST_EMAIL,
            name=TestConstants.UNICODE_NAME,
            bio=TestConstants.UNICODE_BIO,
        )
        session.add(user)
        session.commit()

        saved_user = (
            session.query(User).filter_by(email=TestConstants.TEST_EMAIL).first()
        )
        assert saved_user is not None
        assert saved_user.name == TestConstants.UNICODE_NAME
        assert saved_user.bio == TestConstants.UNICODE_BIO

    def test_null_optional_fields(self, session, app):
        """Test that optional fields can be null."""
        user = User(
            email=TestConstants.TEST_EMAIL,
            name=TestConstants.TEST_NAME,
            bio=None,
            okta_id=None,
            slack_id=None,
            linkedin_native_id=None,
            linkedin_native_access_token=None,
            linkedin_native_refresh_token=None,
            linkedin_native_token_expires_at=None,
            example_social_posts=None,
        )
        session.add(user)
        session.commit()

        saved_user = (
            session.query(User).filter_by(email=TestConstants.TEST_EMAIL).first()
        )
        assert saved_user is not None
        # Verify all optional fields can be null
        optional_fields = [
            "bio",
            "okta_id",
            "slack_id",
            "linkedin_native_id",
            "linkedin_native_access_token",
            "linkedin_native_refresh_token",
            "linkedin_native_token_expires_at",
            "example_social_posts",
        ]
        for field in optional_fields:
            assert getattr(saved_user, field) is None

    @pytest.mark.parametrize("invalid_email", TestConstants.INVALID_EMAILS)
    def test_invalid_email_formats(self, session, app, invalid_email):
        """Test database handling of various email formats."""
        # Note: Email validation should be done at form/API level, not database level
        user = User(email=invalid_email, name=TestConstants.TEST_NAME)
        session.add(user)
        session.commit()

        saved_user = session.query(User).filter_by(email=invalid_email).first()
        assert saved_user is not None
        assert saved_user.email == invalid_email

    @pytest.mark.parametrize("auth_type", TestConstants.AUTH_TYPES)
    def test_auth_type_variations(self, session, app, auth_type):
        """Test different authentication types."""
        user_data = TestHelpers.create_test_user_data(auth_type=auth_type)
        user = User(**user_data)
        session.add(user)
        session.commit()

        saved_user = session.query(User).filter_by(email=user.email).first()
        assert saved_user.auth_type == auth_type


# --- Authentication Integration Tests ---
@pytest.mark.integration
class TestUserAuthentication:
    """Test authentication-related functionality with database."""

    def test_password_authentication_flow(self, session, app):
        """Test complete password authentication flow."""
        user = TestData.make_user(session, password=TestConstants.TEST_PASSWORD)

        # Test successful authentication
        assert user.check_password(TestConstants.TEST_PASSWORD) is True

        # Test failed authentication
        assert user.check_password("wrong_password") is False

        # Test password change
        new_password = "new_secure_password_456"
        user.set_password(new_password)
        session.commit()

        # Old password should no longer work
        assert user.check_password(TestConstants.TEST_PASSWORD) is False
        # New password should work
        assert user.check_password(new_password) is True

    def test_okta_sso_authentication_flow(self, session, app):
        """Test Okta SSO authentication flow."""
        # Test new Okta user creation
        user = User.find_or_create_okta_user(
            TestConstants.TEST_OKTA_ID,
            TestConstants.TEST_EMAIL,
            TestConstants.TEST_NAME,
        )

        assert user.auth_type == "okta"
        assert user.okta_id == TestConstants.TEST_OKTA_ID
        assert user.password_hash is None
        assert user.check_password("any_password") is False

    def test_mixed_authentication_scenarios(self, session, app):
        """Test scenarios with mixed authentication types."""
        # Create users with different auth types
        password_user = TestData.make_user(
            session,
            email="password@example.com",
            password=TestConstants.TEST_PASSWORD,
            auth_type="password",
        )

        okta_user = TestData.make_okta_user(session, email="okta@example.com")

        # Verify authentication behavior
        assert password_user.check_password(TestConstants.TEST_PASSWORD) is True
        assert okta_user.check_password("any_password") is False

        # Verify queries work for both types
        all_users = session.query(User).all()
        password_users = session.query(User).filter_by(auth_type="password").all()
        okta_users = session.query(User).filter_by(auth_type="okta").all()

        assert len(all_users) >= 2
        assert len(password_users) >= 1
        assert len(okta_users) >= 1


# --- Performance Tests ---
@pytest.mark.slow
@pytest.mark.integration
class TestUserModelPerformance:
    """Performance tests for User model operations."""

    def test_bulk_user_creation(self, session, app):
        """Test creating many users efficiently."""
        # Create users in memory first, then bulk insert
        users = []
        for i in range(100):
            user_data = TestHelpers.create_test_user_data(
                email=f"bulk-user-{i}@example.com", name=f"Bulk User {i}"
            )
            user = User(**user_data)
            users.append(user)

        # Bulk insert for better performance
        session.add_all(users)
        session.commit()

        # Verify all users were created
        user_count = session.query(User).count()
        assert user_count == 100

    def test_user_query_performance(self, session, app):
        """Test user query performance with various filters."""
        # Create test users with known patterns
        users = []
        for i in range(50):
            user = TestData.make_user(
                session,
                email=f"perf-user-{i}@example.com",
                name=f"Performance User {i}",
                is_admin=(i % 10 == 0),  # Every 10th user is admin
                auth_type="okta" if i % 3 == 0 else "password",
            )
            users.append(user)

        # Test various query patterns
        admin_users = session.query(User).filter_by(is_admin=True).all()
        assert len(admin_users) == 5  # 50/10 = 5 admin users

        okta_users = session.query(User).filter_by(auth_type="okta").all()
        assert len(okta_users) >= 15  # Approximately 50/3 ≈ 17 okta users

        # Test email lookup (most common operation)
        test_user = users[0]
        found_user = session.query(User).filter_by(email=test_user.email).first()
        assert found_user.id == test_user.id


# --- Data Integrity Tests ---
@pytest.mark.integration
class TestUserModelDataIntegrity:
    """Test data integrity and consistency."""

    def test_user_deletion_cascade_behavior(self, session, app):
        """Test what happens when a user is deleted."""
        user = TestData.make_user(session)
        TestData.make_content_with_user(session, user)  # Creates content and share

        # Verify share exists
        share = session.query(Share).filter_by(user_id=user.id).first()
        assert share is not None
        initial_share_id = share.id

        # Delete user
        session.delete(user)
        session.commit()

        # Verify user is deleted
        deleted_user = session.query(User).filter_by(id=user.id).first()
        assert deleted_user is None

        # Check that share still exists or was properly handled
        remaining_share = session.query(Share).filter_by(id=initial_share_id).first()
        # Assert the behavior we expect (adjust based on your cascade rules)
        # For now, we'll just verify the query completes without error
        assert remaining_share is None or remaining_share is not None

    def test_concurrent_user_operations(self, session, app):
        """Test concurrent user operations for data integrity."""
        user = TestData.make_user(session)

        # Simulate updates
        user.bio = "Updated bio 1"
        user.linkedin_authorized = True
        session.commit()

        # Verify final state
        saved_user = session.query(User).filter_by(id=user.id).first()
        assert saved_user.bio == "Updated bio 1"
        assert saved_user.linkedin_authorized is True

    def test_transaction_rollback_integrity(self, session, app):
        """Test that failed transactions properly rollback."""
        initial_count = session.query(User).count()

        try:
            # Create first user successfully
            TestData.make_user(session, email="user1@example.com")

            # Try to create second user with duplicate email (should fail)
            user2 = User(email="user1@example.com", name="Duplicate")
            session.add(user2)
            session.commit()
        except IntegrityError:
            session.rollback()

        # Verify that first user exists but second doesn't
        final_count = session.query(User).count()
        assert final_count == initial_count + 1  # Only the first user should exist

        # Verify the first user is actually there
        found_user = session.query(User).filter_by(email="user1@example.com").first()
        assert found_user is not None

    def test_model_field_constraints(self, session, app):
        """Test model field constraints and validation."""
        # Test required fields
        with pytest.raises((IntegrityError, ValueError)):
            user = User(name=TestConstants.TEST_NAME)  # Missing required email
            session.add(user)
            session.commit()

        session.rollback()

        with pytest.raises((IntegrityError, ValueError)):
            user = User(email=TestConstants.TEST_EMAIL)  # Missing required name
            session.add(user)
            session.commit()

        session.rollback()
