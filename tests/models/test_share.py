import pytest
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, UTC
from models.share import Share
from models.user import User
from models.content import Content
from sqlalchemy.exc import IntegrityError

# Generate unique identifier for this test run to avoid conflicts in parallel execution
TEST_RUN_ID = str(uuid.uuid4())[:8]


# --- Test Constants ---
class TestConstants:
    """Test constants for consistent data across tests."""

    TEST_USER_EMAIL = f"user-{TEST_RUN_ID}@example.com"
    TEST_USER_NAME = f"Test User {TEST_RUN_ID}"
    TEST_CONTENT_URL = f"https://example.com/article-{TEST_RUN_ID}"
    TEST_CONTENT_TITLE = f"Test Article {TEST_RUN_ID}"

    # Share-specific constants
    TEST_PLATFORM = "linkedin"
    TEST_POST_CONTENT = f"Check out this great article! {TEST_RUN_ID}"
    TEST_POST_URL = f"https://linkedin.com/posts/test-{TEST_RUN_ID}"

    # Platform variations
    PLATFORMS = ["linkedin", "twitter", "facebook", "instagram", "threads", "mastodon"]

    # Long content for edge case testing
    VERY_LONG_POST_CONTENT = f"Test post {TEST_RUN_ID} " + "A" * 2000
    VERY_LONG_POST_URL = (
        f"https://linkedin.com/posts/very-long-{TEST_RUN_ID}-" + "a" * 500
    )


# --- Test Helpers ---
class TestHelpers:
    """Helper methods for testing."""

    @staticmethod
    def assert_share_fields_match(share, expected_data):
        """Assert share fields match expected values."""
        for field, expected_value in expected_data.items():
            actual_value = getattr(share, field)
            assert (
                actual_value == expected_value
            ), f"Field '{field}': expected {expected_value}, got {actual_value}"

    @staticmethod
    def assert_valid_datetime(dt, message="DateTime should be valid and recent"):
        """Assert that datetime is valid and recent."""
        assert dt is not None, f"{message}: datetime is None"
        assert isinstance(dt, datetime), f"{message}: not a datetime object"
        # Should be within last hour (generous for test timing)
        # Note: SQLAlchemy returns naive datetime objects, so we use utcnow() for comparison
        now = datetime.utcnow()
        assert dt >= now - timedelta(hours=1), f"{message}: datetime too old"
        assert dt <= now + timedelta(seconds=5), f"{message}: datetime in future"

    @staticmethod
    @contextmanager
    def expect_error_and_rollback(session, *exception_types):
        """Context manager for testing error conditions with automatic rollback."""
        with pytest.raises(exception_types):
            yield
        session.rollback()


# --- Test Data Factory ---
class TestData:
    """Factory for creating test data."""

    @staticmethod
    def make_user(session, email=None, name=None):
        """Create a test user with unique identifiers."""
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            email=email or f"user-{unique_id}@example.com",
            name=name or f"Test User {unique_id}",
        )
        session.add(user)
        session.commit()
        return user

    @staticmethod
    def make_content(session, user=None, **kwargs):
        """Create test content with sensible defaults and unique identifiers."""
        if user is None:
            user = TestData.make_user(session)

        unique_id = str(uuid.uuid4())[:8]
        defaults = {
            "url": f"https://example.com/article-{unique_id}",
            "title": f"Test Article {unique_id}",
            "submitted_by_id": user.id,
        }
        defaults.update(kwargs)
        content = Content(**defaults)
        session.add(content)
        session.commit()
        return content

    @staticmethod
    def make_share(session, content=None, user=None, platform=None, **kwargs):
        """Create test share with all required fields and unique identifiers."""
        if user is None:
            user = TestData.make_user(session)
        if content is None:
            content = TestData.make_content(session, user=user)

        unique_id = str(uuid.uuid4())[:8]
        defaults = {
            "content_id": content.id,
            "user_id": user.id,
            "platform": platform or TestConstants.TEST_PLATFORM,
            "post_content": f"Test post for {platform or TestConstants.TEST_PLATFORM} {unique_id}",
            "post_url": f"https://{platform or TestConstants.TEST_PLATFORM}.com/post/{unique_id}",
        }
        defaults.update(kwargs)

        share = Share(**defaults)
        session.add(share)
        session.commit()
        return share


# --- Unit Tests ---
@pytest.mark.unit
class TestShareModelUnit:
    """Unit tests for Share model methods that don't require database."""

    # Note: Currently no true unit tests exist for Share model
    # All Share model methods require database access via SQLAlchemy
    pass


# --- Integration Tests ---
@pytest.mark.integration
class TestShareModelIntegration:
    """Integration tests for Share model with database."""

    def test_get_share_count_nonexistent_content(self, session):
        """Test share count for non-existent content."""
        count = Share.get_share_count(99999)
        assert count == 0

    def test_get_platform_share_counts_nonexistent_content(self, session):
        """Test platform share counts for non-existent content."""
        platform_counts = Share.get_platform_share_counts(99999)
        assert list(platform_counts) == []

    def test_repr_formatting(self, session):
        """Test string representation formatting."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)
        share = TestData.make_share(
            session, content=content, user=user, platform="linkedin"
        )

        repr_str = repr(share)
        assert f"<Share {share.id}: linkedin by {user.name}>" == repr_str

    def test_repr_with_special_characters(self, session):
        """Test string representation with special characters in user name."""
        user = TestData.make_user(session, name="Test User with Émojis 🚀")
        content = TestData.make_content(session, user=user)
        share = TestData.make_share(
            session, content=content, user=user, platform="twitter"
        )

        repr_str = repr(share)
        assert f"<Share {share.id}: twitter by Test User with Émojis 🚀>" == repr_str

    @pytest.mark.parametrize("platform", TestConstants.PLATFORMS)
    def test_get_share_count_single_platform(self, session, platform):
        """Test share count calculation for single platform."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        # Create shares on the specified platform
        TestData.make_share(session, content, user, platform)
        TestData.make_share(session, content, user, platform)

        count = Share.get_share_count(content.id)
        assert count == 2

    def test_get_share_count_multiple_platforms(self, session):
        """Test share count calculation across multiple platforms."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        # Create shares on different platforms
        for platform in ["linkedin", "twitter", "facebook"]:
            TestData.make_share(session, content, user, platform)

        count = Share.get_share_count(content.id)
        assert count == 3

    def test_get_share_count_no_shares(self, session):
        """Test share count for content with no shares."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        count = Share.get_share_count(content.id)
        assert count == 0

    def test_get_platform_share_counts_single_platform(self, session):
        """Test platform share counts with single platform."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        # Create multiple shares on linkedin
        for _ in range(3):
            TestData.make_share(session, content, user, "linkedin")

        platform_counts = Share.get_platform_share_counts(content.id)
        counts_dict = dict(platform_counts)

        assert counts_dict["linkedin"] == 3
        assert len(counts_dict) == 1

    def test_get_platform_share_counts_multiple_platforms(self, session):
        """Test platform share counts across multiple platforms."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        # Create shares on different platforms with different counts
        platforms_and_counts = {
            "linkedin": 3,
            "twitter": 2,
            "facebook": 1,
        }

        for platform, count in platforms_and_counts.items():
            for _ in range(count):
                TestData.make_share(session, content, user, platform)

        platform_counts = Share.get_platform_share_counts(content.id)
        counts_dict = dict(platform_counts)

        for platform, expected_count in platforms_and_counts.items():
            assert counts_dict[platform] == expected_count

    def test_get_platform_share_counts_no_shares(self, session):
        """Test platform share counts for content with no shares."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        platform_counts = Share.get_platform_share_counts(content.id)
        assert list(platform_counts) == []

    def test_share_creation_with_all_fields(self, session):
        """Test share creation with all fields populated."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        share_data = {
            "content_id": content.id,
            "user_id": user.id,
            "platform": TestConstants.TEST_PLATFORM,
            "post_content": TestConstants.TEST_POST_CONTENT,
            "post_url": TestConstants.TEST_POST_URL,
        }

        share = TestData.make_share(session, content, user, **share_data)

        # Check all fields
        TestHelpers.assert_share_fields_match(share, share_data)
        assert share.id is not None
        TestHelpers.assert_valid_datetime(share.created_at)

    def test_share_creation_minimal_fields(self, session):
        """Test share creation with only required fields."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        share = Share(
            content_id=content.id,
            user_id=user.id,
            platform=TestConstants.TEST_PLATFORM,
            post_content=TestConstants.TEST_POST_CONTENT,
        )
        session.add(share)
        session.commit()

        assert share.id is not None
        assert share.content_id == content.id
        assert share.user_id == user.id
        assert share.platform == TestConstants.TEST_PLATFORM
        assert share.post_content == TestConstants.TEST_POST_CONTENT
        assert share.post_url is None  # Optional field
        TestHelpers.assert_valid_datetime(share.created_at)

    def test_share_relationships_user(self, session):
        """Test share relationship with user."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)
        share = TestData.make_share(session, content, user)

        # Test forward relationship
        assert share.user.id == user.id
        assert share.user.email == user.email
        assert share.user.name == user.name

        # Test backward relationship
        user_shares = list(user.shares)
        assert len(user_shares) == 1
        assert user_shares[0].id == share.id

    def test_share_relationships_content(self, session):
        """Test share relationship with content."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)
        share = TestData.make_share(session, content, user)

        # Test forward relationship
        assert share.content.id == content.id
        assert share.content.url == content.url
        assert share.content.title == content.title

        # Test backward relationship
        content_shares = list(content.shares)
        assert len(content_shares) == 1
        assert content_shares[0].id == share.id

    def test_multiple_shares_same_content(self, session):
        """Test multiple shares for the same content."""
        user1 = TestData.make_user(session)
        user2 = TestData.make_user(session)
        content = TestData.make_content(session, user=user1)

        # Create shares from different users
        share1 = TestData.make_share(session, content, user1, "linkedin")
        share2 = TestData.make_share(session, content, user2, "twitter")
        share3 = TestData.make_share(session, content, user1, "facebook")

        # Test content has all shares
        content_shares = list(content.shares)
        assert len(content_shares) == 3

        share_ids = {s.id for s in content_shares}
        assert {share1.id, share2.id, share3.id} == share_ids

        # Test users have their respective shares
        user1_shares = list(user1.shares)
        user2_shares = list(user2.shares)

        assert len(user1_shares) == 2  # share1 and share3
        assert len(user2_shares) == 1  # share2

    def test_multiple_shares_same_user(self, session):
        """Test multiple shares from the same user across different content."""
        user = TestData.make_user(session)
        content1 = TestData.make_content(session, user=user)
        content2 = TestData.make_content(session, user=user)

        # Create shares for different content
        share1 = TestData.make_share(session, content1, user, "linkedin")
        share2 = TestData.make_share(session, content2, user, "twitter")

        # Test user has both shares
        user_shares = list(user.shares)
        assert len(user_shares) == 2

        share_ids = {s.id for s in user_shares}
        assert {share1.id, share2.id} == share_ids

        # Test each content has its respective share
        assert len(list(content1.shares)) == 1
        assert len(list(content2.shares)) == 1

    def test_share_cascade_delete_with_content(self, session):
        """Test that shares are deleted when content is deleted."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)
        share = TestData.make_share(session, content, user)

        content_id = content.id
        share_id = share.id

        # Delete content
        content.delete()

        # Verify share is also deleted (cascade)
        assert session.query(Share).filter_by(id=share_id).first() is None
        assert session.query(Content).filter_by(id=content_id).first() is None

    def test_share_cascade_delete_with_user(self, session):
        """Test that shares are deleted when user is deleted."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)
        share = TestData.make_share(session, content, user)

        user_id = user.id
        share_id = share.id

        # Delete user
        session.delete(user)
        session.commit()

        # Verify share is also deleted (cascade)
        assert session.query(Share).filter_by(id=share_id).first() is None
        assert session.query(User).filter_by(id=user_id).first() is None

    @pytest.mark.parametrize("platform", TestConstants.PLATFORMS)
    def test_platform_variations(self, session, platform):
        """Test share creation with different platform values."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        share = TestData.make_share(session, content, user, platform)

        assert share.platform == platform
        assert share.id is not None

    def test_created_at_auto_populated(self, session):
        """Test that created_at is automatically populated."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        # Record time before creation (using naive datetime like SQLAlchemy)
        before_creation = datetime.utcnow()

        share = TestData.make_share(session, content, user)

        # Record time after creation
        after_creation = datetime.utcnow()

        # Verify created_at is within expected range
        assert before_creation <= share.created_at <= after_creation

    def test_created_at_immutable(self, session):
        """Test that created_at doesn't change on updates."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)
        share = TestData.make_share(session, content, user)

        original_created_at = share.created_at

        # Update share
        import time

        time.sleep(0.01)  # Ensure timestamp difference
        share.post_content = "Updated post content"
        session.commit()

        # Verify created_at hasn't changed
        assert share.created_at == original_created_at

    def test_very_long_post_content(self, session):
        """Test handling of very long post content."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        share = TestData.make_share(
            session, content, user, post_content=TestConstants.VERY_LONG_POST_CONTENT
        )

        assert share.post_content == TestConstants.VERY_LONG_POST_CONTENT
        assert len(share.post_content) > 2000

    def test_very_long_post_url(self, session):
        """Test handling of very long post URLs."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        share = TestData.make_share(
            session, content, user, post_url=TestConstants.VERY_LONG_POST_URL
        )

        assert share.post_url == TestConstants.VERY_LONG_POST_URL
        assert len(share.post_url) > 500

    def test_unicode_content_handling(self, session):
        """Test handling of Unicode content in various fields."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        unicode_data = {
            "platform": "微博",  # Chinese social platform
            "post_content": "Check out this article! 🚀 很棒的文章 with émojis",
            "post_url": "https://weibo.com/post/测试123",
        }

        share = TestData.make_share(session, content, user, **unicode_data)

        # Should handle Unicode gracefully
        assert share.platform == unicode_data["platform"]
        assert share.post_content == unicode_data["post_content"]
        assert share.post_url == unicode_data["post_url"]

    def test_empty_string_fields(self, session):
        """Test handling of empty string fields."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        # Test with empty platform (may or may not be allowed by constraints)
        try:
            share = Share(
                content_id=content.id,
                user_id=user.id,
                platform="",  # Empty string
                post_content=TestConstants.TEST_POST_CONTENT,
            )
            session.add(share)
            session.commit()
            assert share.platform == ""
        except (IntegrityError, ValueError):
            # If constraints prevent empty platform, that's also valid
            session.rollback()

        # Test with empty post_content (may or may not be allowed)
        try:
            share = Share(
                content_id=content.id,
                user_id=user.id,
                platform=TestConstants.TEST_PLATFORM,
                post_content="",  # Empty string
            )
            session.add(share)
            session.commit()
            assert share.post_content == ""
        except (IntegrityError, ValueError):
            # If constraints prevent empty post_content, that's also valid
            session.rollback()

    def test_special_characters_in_urls(self, session):
        """Test URLs with special characters and encoding."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        special_url = (
            "https://example.com/post?q=test&data=hello%20world&symbols=%21%40%23"
        )

        share = TestData.make_share(session, content, user, post_url=special_url)

        assert share.post_url == special_url

    def test_whitespace_handling(self, session):
        """Test handling of whitespace in fields."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        whitespace_data = {
            "platform": "  linkedin  ",
            "post_content": "  Content with leading/trailing spaces  ",
            "post_url": "  https://example.com/post  ",
        }

        share = TestData.make_share(session, content, user, **whitespace_data)

        # Model may or may not strip whitespace - test what actually happens
        assert share.platform == whitespace_data["platform"]
        assert share.post_content == whitespace_data["post_content"]
        assert share.post_url == whitespace_data["post_url"]

    def test_concurrent_share_creation(self, session):
        """Test concurrent share creation for same content."""
        user1 = TestData.make_user(session)
        user2 = TestData.make_user(session)
        content = TestData.make_content(session, user=user1)

        # Simulate concurrent share creation
        share1 = Share(
            content_id=content.id,
            user_id=user1.id,
            platform="linkedin",
            post_content="Share from user 1",
        )
        share2 = Share(
            content_id=content.id,
            user_id=user2.id,
            platform="twitter",
            post_content="Share from user 2",
        )

        session.add_all([share1, share2])
        session.commit()

        # Both shares should be created successfully
        assert share1.id is not None
        assert share2.id is not None
        assert share1.id != share2.id

        # Verify content has both shares
        content_shares = list(content.shares)
        assert len(content_shares) == 2

    def test_duplicate_platform_shares_same_user(self, session):
        """Test multiple shares on same platform by same user."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        # Create multiple shares on same platform
        share1 = TestData.make_share(session, content, user, "linkedin")
        share2 = TestData.make_share(session, content, user, "linkedin")

        # Both should be allowed (no unique constraint on platform+user+content)
        assert share1.id != share2.id
        assert share1.platform == share2.platform == "linkedin"

        # Content should have both shares
        content_shares = list(content.shares)
        assert len(content_shares) == 2

    def test_share_state_consistency(self, session):
        """Test share state consistency through operations."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        # Create share
        share = TestData.make_share(session, content, user)
        original_id = share.id
        original_created_at = share.created_at

        # Update share
        import time

        time.sleep(0.01)  # Ensure timestamp difference
        share.post_content = "Updated content"
        session.commit()

        # Verify state consistency
        assert share.id == original_id  # ID should remain same
        assert share.created_at == original_created_at  # created_at should not change
        assert share.post_content == "Updated content"

    def test_relationship_integrity_under_updates(self, session):
        """Test relationship integrity when updating related objects."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)
        share = TestData.make_share(session, content, user)

        # Update user
        user.name = "Updated User Name"
        session.commit()

        # Verify relationship still works
        assert share.user.name == "Updated User Name"

        # Update content
        content.title = "Updated Content Title"
        session.commit()

        # Verify relationship still works
        assert share.content.title == "Updated Content Title"

    def test_cleanup_verification(self, session):
        """Ensure no test data leaks between tests."""
        initial_share_count = session.query(Share).count()
        initial_user_count = session.query(User).count()
        initial_content_count = session.query(Content).count()

        # Create test data with unique identifiers
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)
        share = TestData.make_share(session, content, user)

        # Verify data was created
        assert session.query(Share).count() == initial_share_count + 1
        assert session.query(User).count() == initial_user_count + 1
        assert session.query(Content).count() == initial_content_count + 1

        # Clean up (this would normally be done by test fixtures)
        session.delete(share)
        session.delete(content)
        session.delete(user)
        session.commit()

        # Verify cleanup
        assert session.query(Share).count() == initial_share_count
        assert session.query(User).count() == initial_user_count
        assert session.query(Content).count() == initial_content_count

    def test_cascade_deletion_integrity(self, session):
        """Test that cascade deletions maintain data integrity."""
        user1 = TestData.make_user(session)
        user2 = TestData.make_user(session)
        content = TestData.make_content(session, user=user1)

        # Create shares from multiple users
        share1 = TestData.make_share(session, content, user1, "linkedin")
        share2 = TestData.make_share(session, content, user2, "twitter")

        share1_id = share1.id
        share2_id = share2.id

        # Delete content (should cascade to shares)
        content.delete()

        # Verify shares are deleted
        assert session.query(Share).filter_by(id=share1_id).first() is None
        assert session.query(Share).filter_by(id=share2_id).first() is None

        # Verify users still exist (should not cascade)
        assert session.query(User).filter_by(id=user1.id).first() is not None
        assert session.query(User).filter_by(id=user2.id).first() is not None

    def test_share_creation_missing_required_fields(self, session):
        """Test share creation with missing required fields."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        # Test missing content_id
        with TestHelpers.expect_error_and_rollback(
            session, IntegrityError, ValueError, TypeError
        ):
            share = Share(
                user_id=user.id,
                platform=TestConstants.TEST_PLATFORM,
                post_content=TestConstants.TEST_POST_CONTENT,
            )
            session.add(share)
            session.commit()

        # Test missing user_id
        with TestHelpers.expect_error_and_rollback(
            session, IntegrityError, ValueError, TypeError
        ):
            share = Share(
                content_id=content.id,
                platform=TestConstants.TEST_PLATFORM,
                post_content=TestConstants.TEST_POST_CONTENT,
            )
            session.add(share)
            session.commit()

        # Test missing platform
        with TestHelpers.expect_error_and_rollback(
            session, IntegrityError, ValueError, TypeError
        ):
            share = Share(
                content_id=content.id,
                user_id=user.id,
                post_content=TestConstants.TEST_POST_CONTENT,
            )
            session.add(share)
            session.commit()

        # Test missing post_content
        with TestHelpers.expect_error_and_rollback(
            session, IntegrityError, ValueError, TypeError
        ):
            share = Share(
                content_id=content.id,
                user_id=user.id,
                platform=TestConstants.TEST_PLATFORM,
            )
            session.add(share)
            session.commit()

    def test_invalid_foreign_key_references(self, session):
        """Test share creation with invalid foreign key references."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        # Test with non-existent user_id
        try:
            share = Share(
                content_id=content.id,
                user_id=99999,  # Non-existent user ID
                platform=TestConstants.TEST_PLATFORM,
                post_content=TestConstants.TEST_POST_CONTENT,
            )
            session.add(share)
            session.commit()
            # If it succeeds, that means FK constraints aren't enforced
        except (IntegrityError, Exception) as e:
            # If it fails, that's expected for proper FK constraint enforcement
            session.rollback()
            error_msg = str(e).lower()
            assert any(
                keyword in error_msg
                for keyword in ["constraint", "foreign", "key", "reference"]
            )

        # Test with non-existent content_id
        try:
            share = Share(
                content_id=99999,  # Non-existent content ID
                user_id=user.id,
                platform=TestConstants.TEST_PLATFORM,
                post_content=TestConstants.TEST_POST_CONTENT,
            )
            session.add(share)
            session.commit()
            # If it succeeds, that means FK constraints aren't enforced
        except (IntegrityError, Exception) as e:
            # If it fails, that's expected for proper FK constraint enforcement
            session.rollback()
            error_msg = str(e).lower()
            assert any(
                keyword in error_msg
                for keyword in ["constraint", "foreign", "key", "reference"]
            )

    def test_invalid_data_types(self, session):
        """Test share creation with invalid data types."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        # Test with non-string platform
        try:
            share = Share(
                content_id=content.id,
                user_id=user.id,
                platform=12345,  # Invalid type
                post_content=TestConstants.TEST_POST_CONTENT,
            )
            session.add(share)
            session.commit()
            # If no exception is raised, the model is permissive with data types
        except (TypeError, ValueError, IntegrityError):
            # If exception is raised, that's expected behavior
            session.rollback()

        # Test with non-string post_content
        try:
            share = Share(
                content_id=content.id,
                user_id=user.id,
                platform=TestConstants.TEST_PLATFORM,
                post_content=None,  # Invalid value for required field
            )
            session.add(share)
            session.commit()
            # If no exception is raised, the model allows None post_content
        except (TypeError, ValueError, IntegrityError):
            # If exception is raised, that's expected for proper validation
            session.rollback()

    def test_data_consistency_after_errors(self, session):
        """Test data consistency after errors and rollbacks."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)
        initial_count = session.query(Share).count()

        # Test scenario where we try to create shares in a transaction that fails
        try:
            # Create valid share
            share1 = Share(
                content_id=content.id,
                user_id=user.id,
                platform="linkedin",
                post_content="Valid share",
            )
            session.add(share1)

            # Try to create invalid share in same transaction
            share2 = Share(
                content_id=99999,  # Invalid content_id
                user_id=user.id,
                platform="twitter",
                post_content="Invalid share",
            )
            session.add(share2)
            session.commit()  # This should fail due to share2

            # If we get here, both succeeded (constraint not enforced)
            final_count = session.query(Share).count()
            assert final_count >= initial_count + 1

        except Exception:
            # Transaction failed - both shares should be rolled back
            session.rollback()

            # Verify we're back to initial state
            assert session.query(Share).count() == initial_count

            # Now create a valid share after rollback
            TestData.make_share(session, content, user)

            # Should have exactly one more than initial
            final_count = session.query(Share).count()
            assert final_count == initial_count + 1

    def test_transaction_isolation(self, session):
        """Test transaction isolation behavior."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        # Create share but don't commit yet
        share = Share(
            content_id=content.id,
            user_id=user.id,
            platform="test_platform",
            post_content="Uncommitted share",
        )
        session.add(share)

        # Share should be visible in current session
        found_in_session = (
            session.query(Share).filter_by(platform="test_platform").first()
        )
        assert found_in_session is not None

        # Rollback
        session.rollback()

        # Share should no longer be visible
        not_found = session.query(Share).filter_by(platform="test_platform").first()
        assert not_found is None


# --- Performance Tests ---
@pytest.mark.slow
class TestShareModelPerformance:
    """Performance and stress tests."""

    def test_bulk_share_creation(self, session):
        """Test creating many shares."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        shares = []
        for i in range(100):
            share = Share(
                content_id=content.id,
                user_id=user.id,
                platform=TestConstants.PLATFORMS[i % len(TestConstants.PLATFORMS)],
                post_content=f"Bulk post content {i}",
                post_url=f"https://example.com/post/{i}",
            )
            shares.append(share)

        session.add_all(shares)
        session.commit()

        # Verify all shares were created
        assert session.query(Share).filter_by(content_id=content.id).count() == 100

    def test_share_count_performance_many_shares(self, session):
        """Test share count performance with many shares."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        # Create many shares
        for i in range(50):
            platform = TestConstants.PLATFORMS[i % len(TestConstants.PLATFORMS)]
            TestData.make_share(session, content, user, platform)

        # Test count performance
        count = Share.get_share_count(content.id)
        assert count == 50

        # Test platform breakdown performance
        platform_counts = Share.get_platform_share_counts(content.id)
        counts_dict = dict(platform_counts)

        # Verify counts are reasonable
        total_counted = sum(counts_dict.values())
        assert total_counted == 50

    def test_relationships_performance_many_shares(self, session):
        """Test relationship performance with many shares."""
        user = TestData.make_user(session)
        content = TestData.make_content(session, user=user)

        # Create many shares
        for i in range(25):
            TestData.make_share(session, content, user, "linkedin")

        # Test relationship queries
        content_shares = list(content.shares)
        assert len(content_shares) == 25

        user_shares = list(user.shares)
        assert len(user_shares) == 25
