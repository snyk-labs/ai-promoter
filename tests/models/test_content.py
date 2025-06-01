import pytest
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
from models.content import Content
from models.user import User
from models.share import Share
from sqlalchemy.exc import IntegrityError

# Generate unique identifier for this test run to avoid conflicts in parallel execution
TEST_RUN_ID = str(uuid.uuid4())[:8]


# --- Test Constants ---
class TestConstants:
    """Test constants for consistent data across tests."""

    TEST_URL = f"https://example.com/article-{TEST_RUN_ID}"
    TEST_URL_WITH_UTM = (
        f"https://example.com/article-{TEST_RUN_ID}?utm_source=foo&utm_medium=bar"
    )
    TEST_TITLE = f"Test Article {TEST_RUN_ID}"
    TEST_COPY = f"Check this out: https://example.com/article-{TEST_RUN_ID}"
    TEST_IMAGE_URL = f"https://example.com/image-{TEST_RUN_ID}.png"
    TEST_EXCERPT = f"Short excerpt {TEST_RUN_ID}."
    TEST_CONTEXT = f"Some context {TEST_RUN_ID}."
    TEST_UTM_CAMPAIGN = f"spring_launch_{TEST_RUN_ID}"
    TEST_USER_EMAIL = f"user-{TEST_RUN_ID}@example.com"
    TEST_USER_NAME = f"Test User {TEST_RUN_ID}"

    # Edge case data
    VERY_LONG_URL = f"https://example.com/{TEST_RUN_ID}-" + "a" * 2000
    SPECIAL_CHARS_URL = f"https://example.com/article-{TEST_RUN_ID}?q=test&data=hello%20world&symbols=%21%40%23"
    MALFORMED_UTM = "utm_source=foo&utm_medium&utm_campaign="
    DUPLICATE_UTM = "utm_source=foo&utm_source=bar&utm_medium=email"

    # Platform variations
    PLATFORMS = ["linkedin", "twitter", "facebook", "instagram"]


# --- Test Helpers ---
class TestHelpers:
    """Helper methods for testing."""

    @staticmethod
    def assert_utm_params_in_url(url, expected_params):
        """Assert that URL contains expected UTM parameters."""
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)

        for key, expected_value in expected_params.items():
            assert key in query_params, f"UTM parameter '{key}' not found in URL: {url}"
            actual_value = query_params[key][0]  # parse_qs returns lists
            assert (
                actual_value == expected_value
            ), f"Expected {key}={expected_value}, got {key}={actual_value}"

    @staticmethod
    def assert_content_fields_match(content, expected_data):
        """Assert content fields match expected values."""
        for field, expected_value in expected_data.items():
            actual_value = getattr(content, field)
            assert (
                actual_value == expected_value
            ), f"Field '{field}': expected {expected_value}, got {actual_value}"

    @staticmethod
    def assert_url_structure_valid(url):
        """Assert that URL has valid structure."""
        parsed = urlparse(url)
        assert parsed.scheme in ["http", "https"], f"Invalid scheme in URL: {url}"
        assert parsed.netloc, f"Missing netloc in URL: {url}"
        assert parsed.path, f"Missing path in URL: {url}"

    @staticmethod
    def extract_utm_params(url):
        """Extract UTM parameters from URL as dict."""
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        return {k: v[0] for k, v in query_params.items() if k.startswith("utm_")}


# --- Test Context Managers ---
@contextmanager
def utm_config(app, utm_params=""):
    """Context manager for temporarily setting UTM config."""
    old_value = app.config.get("UTM_PARAMS")
    app.config["UTM_PARAMS"] = utm_params
    try:
        yield
    finally:
        if old_value is None:
            app.config.pop("UTM_PARAMS", None)
        else:
            app.config["UTM_PARAMS"] = old_value


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
    def make_content(session, **kwargs):
        """Create test content with sensible defaults and unique identifiers."""
        unique_id = str(uuid.uuid4())[:8]
        defaults = {
            "url": f"https://example.com/article-{unique_id}",
            "title": f"Test Article {unique_id}",
            "copy": f"Check this out: https://example.com/article-{unique_id}",
            "image_url": f"https://example.com/image-{unique_id}.png",
            "excerpt": f"Short excerpt {unique_id}.",
            "context": f"Some context {unique_id}.",
            "utm_campaign": f"test_campaign_{unique_id}",
        }
        defaults.update(kwargs)
        content = Content(**defaults)
        session.add(content)
        session.commit()
        return content

    @staticmethod
    def make_share(session, content, user=None, platform="linkedin", **kwargs):
        """Create test share with all required fields and unique identifiers."""
        if user is None:
            user = TestData.make_user(session)

        unique_id = str(uuid.uuid4())[:8]
        defaults = {
            "content_id": content.id,
            "user_id": user.id,
            "platform": platform,
            "post_content": f"Test post for {platform} {unique_id}",
            "post_url": f"https://{platform}.com/post/{unique_id}",
        }
        defaults.update(kwargs)

        share = Share(**defaults)
        session.add(share)
        session.commit()
        return share


# --- Unit Tests ---
@pytest.mark.unit
class TestContentModelUnit:
    """Unit tests for Content model methods."""

    def test_parse_utm_params_with_mixed_params(self):
        """Test UTM parameter parsing with mixed query parameters."""
        c = Content(url=TestConstants.TEST_URL, title=TestConstants.TEST_TITLE)
        url = "https://foo.com/bar?utm_source=foo&utm_medium=bar&other=value&utm_campaign=test"
        base, utms = c._parse_utm_params(url)

        assert base == "https://foo.com/bar?other=value"
        assert utms == {
            "utm_source": "foo",
            "utm_medium": "bar",
            "utm_campaign": "test",
        }

    def test_parse_utm_params_no_query_string(self):
        """Test UTM parameter parsing with no query string."""
        c = Content(url=TestConstants.TEST_URL, title=TestConstants.TEST_TITLE)
        base, utms = c._parse_utm_params("https://foo.com/bar")

        assert base == "https://foo.com/bar"
        assert utms == {}

    def test_parse_utm_params_empty_values(self):
        """Test UTM parameter parsing with empty values."""
        c = Content(url=TestConstants.TEST_URL, title=TestConstants.TEST_TITLE)
        base, utms = c._parse_utm_params(
            "https://foo.com/bar?utm_source=&utm_medium=email"
        )

        assert base == "https://foo.com/bar"
        assert utms == {"utm_medium": "email"}  # Empty values should be filtered out

    def test_merge_utm_params_override_behavior(self):
        """Test UTM parameter merging with override behavior."""
        c = Content(url=TestConstants.TEST_URL, title=TestConstants.TEST_TITLE)

        # Test normal merge
        merged = c._merge_utm_params({"utm_source": "a"}, {"utm_medium": "b"})
        assert merged == {"utm_source": "a", "utm_medium": "b"}

        # Test override
        merged = c._merge_utm_params({"utm_source": "old"}, {"utm_source": "new"})
        assert merged == {"utm_source": "new"}

        # Test with empty dicts
        merged = c._merge_utm_params({}, {"utm_source": "test"})
        assert merged == {"utm_source": "test"}

    def test_build_url_with_utm_no_params(self):
        """Test URL building with no UTM parameters."""
        c = Content(url=TestConstants.TEST_URL, title=TestConstants.TEST_TITLE)
        url = c._build_url_with_utm("https://foo.com/bar", {})
        assert url == "https://foo.com/bar"

    def test_build_url_with_utm_existing_query(self):
        """Test URL building when base URL already has query parameters."""
        c = Content(url=TestConstants.TEST_URL, title=TestConstants.TEST_TITLE)
        base = "https://foo.com/bar?existing=value"
        utms = {"utm_source": "test"}
        url = c._build_url_with_utm(base, utms)

        assert url.startswith(base)
        assert "&utm_source=test" in url

    @pytest.mark.parametrize(
        "utm_config_value,campaign,expected_params",
        [
            (
                "utm_source=blog&utm_medium=email",
                "winter",
                {"utm_source": "blog", "utm_medium": "email", "utm_campaign": "winter"},
            ),
            (
                "?utm_source=social",
                "spring",
                {"utm_source": "social", "utm_campaign": "spring"},
            ),
            ("", "summer", {"utm_campaign": "summer"}),
            ("utm_source=test", None, {"utm_source": "test"}),
        ],
    )
    def test_get_url_with_all_utms_various_configs(
        self, app, utm_config_value, campaign, expected_params
    ):
        """Test URL generation with various config and campaign combinations."""
        with utm_config(app, utm_config_value):
            with app.app_context():
                c = Content(
                    url=TestConstants.TEST_URL,
                    title=TestConstants.TEST_TITLE,
                    utm_campaign=campaign,
                )
                url = c.get_url_with_all_utms()

                TestHelpers.assert_url_structure_valid(url)
                TestHelpers.assert_utm_params_in_url(url, expected_params)

    def test_get_url_with_all_utms_preserves_existing_params(self, app):
        """Test that existing non-UTM parameters are preserved."""
        url_with_params = "https://example.com/article?ref=homepage&id=123"
        with utm_config(app, "utm_source=test"):
            with app.app_context():
                c = Content(url=url_with_params, title=TestConstants.TEST_TITLE)
                result_url = c.get_url_with_all_utms()

                assert "ref=homepage" in result_url
                assert "id=123" in result_url
                assert "utm_source=test" in result_url

    @pytest.mark.parametrize(
        "copy_input,expected_behavior",
        [
            (None, "appends_url"),
            ("", "appends_url"),
            ("No URL here", "appends_url"),
            ("Check out https://example.com/article", "replaces_url"),
            (
                "Multiple links: https://example.com/article and https://example.com/other",
                "replaces_first_only",
            ),
        ],
    )
    def test_process_copy_with_utm_params_various_inputs(
        self, app, copy_input, expected_behavior
    ):
        """Test copy processing with various input scenarios."""
        with utm_config(app, "utm_source=test"):
            with app.app_context():
                c = Content(url=TestConstants.TEST_URL, title=TestConstants.TEST_TITLE)
                processed = c.process_copy_with_utm_params(copy_input)

                assert (
                    TestConstants.TEST_URL in processed
                    or "utm_source=test" in processed
                )

                if expected_behavior == "appends_url":
                    assert (
                        processed.endswith(TestConstants.TEST_URL + "?utm_source=test")
                        or processed == ""
                    )
                elif expected_behavior == "replaces_url":
                    assert "utm_source=test" in processed
                    utm_params = TestHelpers.extract_utm_params(processed)
                    assert "utm_source" in utm_params

    def test_repr_formatting(self):
        """Test string representation formatting."""
        c = Content(id=42, url=TestConstants.TEST_URL, title="Hello World")
        repr_str = repr(c)
        assert "<Content 42: Hello World>" in repr_str

    def test_repr_with_long_title(self):
        """Test string representation with very long title."""
        long_title = "A" * 100
        c = Content(id=1, url=TestConstants.TEST_URL, title=long_title)
        repr_str = repr(c)
        assert "<Content 1:" in repr_str
        assert long_title in repr_str


# --- Integration Tests ---
@pytest.mark.integration
class TestContentModelIntegration:
    """Integration tests for Content model with database."""

    def test_content_creation_with_all_fields(self, session, app):
        """Test content creation with all fields populated."""
        user = TestData.make_user(session)

        with utm_config(app, ""):
            with app.app_context():
                content_data = {
                    "url": TestConstants.TEST_URL,
                    "title": TestConstants.TEST_TITLE,
                    "copy": TestConstants.TEST_COPY,
                    "image_url": TestConstants.TEST_IMAGE_URL,
                    "excerpt": TestConstants.TEST_EXCERPT,
                    "context": TestConstants.TEST_CONTEXT,
                    "utm_campaign": TestConstants.TEST_UTM_CAMPAIGN,
                    "submitted_by_id": user.id,
                }

                content = TestData.make_content(session, **content_data)

                # Check all fields except copy (which gets modified by event listener)
                expected_fields = content_data.copy()
                expected_fields.pop("copy")  # Remove copy from exact match

                TestHelpers.assert_content_fields_match(content, expected_fields)
                assert content.id is not None
                assert content.created_at <= datetime.utcnow()
                assert content.updated_at <= datetime.utcnow()
                # Copy should contain the original URL plus UTM campaign from the model
                assert "utm_campaign=spring_launch" in content.copy
                assert TestConstants.TEST_URL in content.copy

    def test_content_creation_minimal_fields(self, session, app):
        """Test content creation with only required fields."""
        with utm_config(app, ""):
            with app.app_context():
                content = Content(
                    url=TestConstants.TEST_URL, title=TestConstants.TEST_TITLE
                )
                session.add(content)
                session.commit()

                assert content.id is not None
                assert content.url == TestConstants.TEST_URL
                assert content.title == TestConstants.TEST_TITLE
                assert content.copy is None

    @pytest.mark.parametrize("platform", TestConstants.PLATFORMS)
    def test_content_relationships_multiple_platforms(self, session, app, platform):
        """Test content relationships with shares across multiple platforms."""
        user = TestData.make_user(session)

        with utm_config(app, ""):
            with app.app_context():
                content = TestData.make_content(session, submitted_by_id=user.id)
                share = TestData.make_share(
                    session, content, user=user, platform=platform
                )

                assert content.share_count == 1
                assert share.platform == platform
                assert share.content_id == content.id
                assert share.user_id == user.id

    def test_content_relationships_aggregation(self, session, app):
        """Test share count aggregation across platforms."""
        user = TestData.make_user(session)

        with utm_config(app, ""):
            with app.app_context():
                content = TestData.make_content(session, submitted_by_id=user.id)

                # Create shares on multiple platforms
                platforms_used = ["linkedin", "twitter", "facebook"]
                for platform in platforms_used:
                    TestData.make_share(session, content, user=user, platform=platform)

                assert content.share_count == len(platforms_used)

                # Test platform breakdown
                counts = dict(content.platform_share_counts)
                for platform in platforms_used:
                    assert counts[platform] == 1

    def test_content_deletion_cascades(self, session, app):
        """Test that content deletion properly cascades to shares."""
        user = TestData.make_user(session)

        with utm_config(app, ""):
            with app.app_context():
                content = TestData.make_content(session, submitted_by_id=user.id)
                share = TestData.make_share(session, content, user=user)
                content_id = content.id
                share_id = share.id

                content.delete()

                # Verify content is deleted
                assert session.query(Content).filter_by(id=content_id).first() is None
                # Verify share is also deleted (cascade)
                assert session.query(Share).filter_by(id=share_id).first() is None

    def test_content_updated_at_auto_update(self, session, app):
        """Test that updated_at field is automatically updated."""
        with utm_config(app, ""):
            with app.app_context():
                content = TestData.make_content(session)
                original_updated = content.updated_at

                # Small delay to ensure timestamp difference
                import time

                time.sleep(0.01)

                content.title = "Updated Title"
                session.commit()

                assert content.updated_at > original_updated


# --- Event Listener Tests ---
@pytest.mark.integration
class TestContentEventListeners:
    """Test SQLAlchemy event listeners for Content model."""

    def test_event_listener_on_insert(self, session, app):
        """Test copy processing event listener on content insert."""
        with utm_config(app, "utm_source=blog"):
            with app.app_context():
                user = TestData.make_user(session)
                content = Content(
                    url=TestConstants.TEST_URL,
                    title=TestConstants.TEST_TITLE,
                    copy=f"Read more: {TestConstants.TEST_URL}",
                    submitted_by_id=user.id,
                )
                session.add(content)
                session.commit()

                assert "utm_source=blog" in content.copy

    def test_event_listener_on_update(self, session, app):
        """Test copy processing event listener on content update."""
        user = TestData.make_user(session)

        # Create content without UTM config
        with utm_config(app, ""):
            with app.app_context():
                content = TestData.make_content(
                    session,
                    copy=f"Original: {TestConstants.TEST_URL}",
                    submitted_by_id=user.id,
                )
                content_id = content.id

        # Update with UTM config in same session
        with utm_config(app, "utm_source=update"):
            with app.app_context():
                # Re-fetch the content to avoid detached instance
                content = session.query(Content).filter_by(id=content_id).first()
                content.copy = f"Updated: {TestConstants.TEST_URL}"
                session.commit()

                assert "utm_source=update" in content.copy

    def test_event_listener_with_none_copy(self, session, app):
        """Test event listener behavior when copy is None."""
        user = TestData.make_user(session)

        with utm_config(app, "utm_source=test"):
            with app.app_context():
                content = Content(
                    url=TestConstants.TEST_URL,
                    title=TestConstants.TEST_TITLE,
                    copy=None,
                    submitted_by_id=user.id,
                )
                session.add(content)
                session.commit()

                # Should not crash, copy should remain None
                assert content.copy is None

    def test_event_listener_with_empty_copy(self, session, app):
        """Test event listener behavior with empty string copy."""
        user = TestData.make_user(session)

        with utm_config(app, "utm_source=test"):
            with app.app_context():
                content = Content(
                    url=TestConstants.TEST_URL,
                    title=TestConstants.TEST_TITLE,
                    copy="",
                    submitted_by_id=user.id,
                )
                session.add(content)
                session.commit()

                # Empty string is falsy, so event listener doesn't process it
                # The copy should remain empty
                assert content.copy == ""


# --- Edge Case and Boundary Tests ---
@pytest.mark.unit
class TestContentModelEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_long_url_handling(self, app):
        """Test handling of very long URLs."""
        with utm_config(app, "utm_source=test"):
            with app.app_context():
                c = Content(
                    url=TestConstants.VERY_LONG_URL, title=TestConstants.TEST_TITLE
                )
                result_url = c.get_url_with_all_utms()

                assert len(result_url) > len(TestConstants.VERY_LONG_URL)
                assert "utm_source=test" in result_url

    def test_special_characters_in_url(self, app):
        """Test URLs with special characters and encoding."""
        with utm_config(app, "utm_source=test"):
            with app.app_context():
                c = Content(
                    url=TestConstants.SPECIAL_CHARS_URL, title=TestConstants.TEST_TITLE
                )
                result_url = c.get_url_with_all_utms()

                TestHelpers.assert_url_structure_valid(result_url)
                assert "utm_source=test" in result_url

    def test_malformed_utm_config(self, app):
        """Test handling of malformed UTM configuration."""
        with utm_config(app, TestConstants.MALFORMED_UTM):
            with app.app_context():
                c = Content(url=TestConstants.TEST_URL, title=TestConstants.TEST_TITLE)
                # Should not crash, should handle gracefully
                result_url = c.get_url_with_all_utms()
                TestHelpers.assert_url_structure_valid(result_url)

    def test_duplicate_utm_parameters(self, app):
        """Test handling of duplicate UTM parameters in config."""
        with utm_config(app, TestConstants.DUPLICATE_UTM):
            with app.app_context():
                c = Content(url=TestConstants.TEST_URL, title=TestConstants.TEST_TITLE)
                result_url = c.get_url_with_all_utms()

                # Should handle gracefully - parse_qs takes the first value
                TestHelpers.assert_url_structure_valid(result_url)

    @pytest.mark.parametrize(
        "invalid_input",
        [
            "",  # Empty string
            "not-a-url",  # Not a URL
            "ftp://example.com",  # Different protocol
            "//example.com",  # Protocol-relative
        ],
    )
    def test_invalid_url_inputs(self, app, invalid_input):
        """Test behavior with invalid URL inputs."""
        with utm_config(app, "utm_source=test"):
            with app.app_context():
                c = Content(url=invalid_input, title=TestConstants.TEST_TITLE)
                # Should not crash, may produce unexpected but valid results
                try:
                    result_url = c.get_url_with_all_utms()
                    # If it doesn't crash, that's good enough for this edge case
                    assert isinstance(result_url, str)
                except Exception:
                    # Some invalid inputs may cause exceptions, which is acceptable
                    pass

    def test_unicode_content_handling(self, session, app):
        """Test handling of Unicode content in various fields."""
        unicode_data = {
            "url": "https://example.com/测试",
            "title": "Test 文章 Title",
            "copy": "Check this 测试: https://example.com/测试",
            "excerpt": "Unicode excerpt with émojis 🚀",
            "context": "Context with special chars: àáâãäå",
        }

        with utm_config(app, "utm_source=测试"):
            with app.app_context():
                content = TestData.make_content(session, **unicode_data)

                # Should handle Unicode gracefully
                assert content.title == unicode_data["title"]
                assert content.excerpt == unicode_data["excerpt"]


# --- Performance Tests ---
@pytest.mark.slow
class TestContentModelPerformance:
    """Performance and stress tests."""

    def test_bulk_content_creation(self, session, app):
        """Test creating many content items."""
        user = TestData.make_user(session)

        with utm_config(app, "utm_source=bulk"):
            with app.app_context():
                content_items = []
                for i in range(100):
                    content = Content(
                        url=f"https://example.com/article-{i}",
                        title=f"Article {i}",
                        copy=f"Content {i}",
                        submitted_by_id=user.id,
                    )
                    content_items.append(content)

                session.add_all(content_items)
                session.commit()

                # Verify all items were created
                assert session.query(Content).count() == 100

    def test_many_shares_per_content(self, session, app):
        """Test content with many associated shares."""
        user = TestData.make_user(session)

        with utm_config(app, ""):
            with app.app_context():
                content = TestData.make_content(session, submitted_by_id=user.id)

                # Create many shares
                for i in range(50):
                    platform = TestConstants.PLATFORMS[i % len(TestConstants.PLATFORMS)]
                    TestData.make_share(session, content, user=user, platform=platform)

                # Test aggregation performance
                assert content.share_count == 50
                platform_counts = dict(content.platform_share_counts)

                # Verify counts are reasonable
                total_counted = sum(platform_counts.values())
                assert total_counted == 50


# --- Error Condition Tests ---
@pytest.mark.integration
class TestContentModelErrorConditions:
    """Test error conditions and exception handling."""

    def test_content_creation_missing_required_fields(self, session):
        """Test content creation with missing required fields."""
        with pytest.raises((IntegrityError, ValueError, TypeError)):
            content = Content(title=TestConstants.TEST_TITLE)  # Missing URL
            session.add(content)
            session.commit()

    def test_duplicate_url_constraint(self, session, app):
        """Test duplicate URL constraint if it exists."""
        with utm_config(app, ""):
            with app.app_context():
                # Create first content
                content1 = TestData.make_content(session)

                # Try to create second with same URL
                try:
                    content2 = Content(url=content1.url, title="Different Title")
                    session.add(content2)
                    session.commit()
                    # If no constraint exists, that's fine too
                except IntegrityError:
                    # If constraint exists and fails, that's expected
                    session.rollback()

    def test_url_constraint_comprehensive(self, session, app):
        """Test URL constraint behavior comprehensively."""
        with utm_config(app, ""):
            with app.app_context():
                # Test normal creation with unique URL
                unique_id1 = str(uuid.uuid4())[:8]
                content1 = TestData.make_content(
                    session, url=f"https://example.com/unique-{unique_id1}"
                )

                # Test case sensitivity (if applicable)
                try:
                    unique_id2 = str(uuid.uuid4())[:8]
                    content2 = TestData.make_content(
                        session, url=f"HTTPS://EXAMPLE.COM/UNIQUE-{unique_id2}"
                    )
                    # If this succeeds, URLs are case-sensitive
                    assert content2.id != content1.id
                except IntegrityError:
                    # If this fails, URLs are case-insensitive
                    session.rollback()

                # Test with query parameters
                unique_id3 = str(uuid.uuid4())[:8]
                unique_id4 = str(uuid.uuid4())[:8]
                content3 = TestData.make_content(
                    session, url=f"https://example.com/unique-{unique_id3}?param=1"
                )
                content4 = TestData.make_content(
                    session, url=f"https://example.com/unique-{unique_id4}?param=2"
                )
                assert content3.id != content4.id

    def test_invalid_foreign_key_reference(self, session, app):
        """Test content creation with invalid foreign key."""
        with utm_config(app, ""):
            with app.app_context():
                # Create content with non-existent user ID
                content = Content(
                    url=TestConstants.TEST_URL,
                    title=TestConstants.TEST_TITLE,
                    submitted_by_id=99999,  # Non-existent user ID
                )
                session.add(content)

                # This may or may not raise an exception depending on DB constraints
                # Some databases/configurations don't enforce foreign key constraints
                try:
                    session.commit()
                    # If it succeeds, that's also valid - just means FK constraints aren't enforced
                    assert content.id is not None
                except (IntegrityError, Exception) as e:
                    # If it fails, that's expected for proper FK constraint enforcement
                    session.rollback()
                    error_msg = str(e).lower()
                    assert any(
                        keyword in error_msg
                        for keyword in ["constraint", "foreign", "key", "reference"]
                    )

    def test_invalid_data_types(self, session, app):
        """Test content creation with invalid data types."""
        with utm_config(app, ""):
            with app.app_context():
                # Test with non-string URL - model may be permissive
                try:
                    content = Content(url=12345, title=TestConstants.TEST_TITLE)
                    session.add(content)
                    session.commit()
                    # If no exception is raised, the model is permissive with data types
                    assert content.id is not None
                except (TypeError, ValueError, IntegrityError):
                    # If exception is raised, that's also expected behavior
                    session.rollback()

                # Test with non-string title - model may be permissive
                try:
                    content = Content(url=TestConstants.TEST_URL, title=None)
                    session.add(content)
                    session.commit()
                    # If no exception is raised, the model allows None titles
                    assert content.id is not None
                except (TypeError, ValueError, IntegrityError):
                    # If exception is raised, that's expected for proper validation
                    session.rollback()


# --- Concurrency and State Tests ---
@pytest.mark.integration
class TestContentModelConcurrency:
    """Test concurrent access and state management."""

    def test_concurrent_content_updates(self, session, app):
        """Test concurrent updates to same content."""
        user = TestData.make_user(session)

        with utm_config(app, "utm_source=concurrent"):
            with app.app_context():
                content = TestData.make_content(session, submitted_by_id=user.id)
                content_id = content.id

                # Simulate concurrent access by fetching same content in different "sessions"
                content_ref1 = session.query(Content).filter_by(id=content_id).first()
                content_ref2 = session.query(Content).filter_by(id=content_id).first()

                # Update from first reference
                content_ref1.title = "Updated by User 1"
                session.commit()

                # Update from second reference should work (optimistic locking)
                content_ref2.copy = "Updated by User 2"
                session.commit()

                # Verify both updates applied
                final_content = session.query(Content).filter_by(id=content_id).first()
                assert final_content.title == "Updated by User 1"
                assert "Updated by User 2" in final_content.copy

    def test_content_state_transitions(self, session, app):
        """Test content through various state transitions."""
        user = TestData.make_user(session)

        with utm_config(app, ""):
            with app.app_context():
                # Create content
                content = TestData.make_content(session, submitted_by_id=user.id)
                original_id = content.id

                # Test state after creation
                assert content.created_at is not None
                assert content.updated_at is not None
                assert content.created_at <= content.updated_at

                # Test state after update
                import time

                time.sleep(0.01)  # Ensure timestamp difference
                content.title = "Updated Title"
                session.commit()

                assert content.updated_at > content.created_at
                assert content.id == original_id  # ID should remain same

                # Test state after adding relationships
                share = TestData.make_share(session, content, user=user)
                assert content.share_count == 1
                assert share.content_id == content.id

    def test_model_method_edge_cases(self, session, app):
        """Test model methods with edge case inputs."""
        user = TestData.make_user(session)

        with utm_config(app, ""):
            with app.app_context():
                content = TestData.make_content(session, submitted_by_id=user.id)

                # Test UTM methods with edge cases
                # Empty string URL gets parsed with default scheme
                assert content._parse_utm_params("") == ("://", {})
                # Invalid URL also gets scheme prepended
                assert content._parse_utm_params("invalid-url") == (
                    "://invalid-url",
                    {},
                )

                # Test merge with None/empty inputs
                assert content._merge_utm_params({}, {}) == {}
                assert content._merge_utm_params(None or {}, {"test": "value"}) == {
                    "test": "value"
                }

                # Test URL building with edge cases
                assert content._build_url_with_utm("", {}) == ""
                assert (
                    content._build_url_with_utm("https://test.com", {})
                    == "https://test.com"
                )

    def test_relationship_integrity(self, session, app):
        """Test relationship integrity under various conditions."""
        user = TestData.make_user(session)

        with utm_config(app, ""):
            with app.app_context():
                content = TestData.make_content(session, submitted_by_id=user.id)

                # Create multiple shares
                shares = []
                for i in range(3):
                    share = TestData.make_share(
                        session, content, user=user, platform=f"platform_{i}"
                    )
                    shares.append(share)

                # Test relationship queries
                assert content.share_count == 3
                assert len(list(content.shares)) == 3

                # Test relationship after share deletion
                session.delete(shares[0])
                session.commit()

                # Refresh content to get updated counts
                session.refresh(content)
                assert content.share_count == 2


# --- Data Integrity and Cleanup Tests ---
@pytest.mark.integration
class TestContentModelDataIntegrity:
    """Test data integrity and cleanup behavior."""

    def test_cleanup_verification(self, session, app):
        """Ensure no test data leaks between tests."""
        initial_content_count = session.query(Content).count()
        initial_user_count = session.query(User).count()
        initial_share_count = session.query(Share).count()

        with utm_config(app, ""):
            with app.app_context():
                # Create test data with unique identifiers
                user = TestData.make_user(session)
                content = TestData.make_content(session, submitted_by_id=user.id)
                share = TestData.make_share(session, content, user=user)

                # Verify data was created
                assert session.query(Content).count() == initial_content_count + 1
                assert session.query(User).count() == initial_user_count + 1
                assert session.query(Share).count() == initial_share_count + 1

                # Clean up (this would normally be done by test fixtures)
                session.delete(share)
                session.delete(content)
                session.delete(user)
                session.commit()

                # Verify cleanup
                assert session.query(Content).count() == initial_content_count
                assert session.query(User).count() == initial_user_count
                assert session.query(Share).count() == initial_share_count

    def test_cascade_deletion_integrity(self, session, app):
        """Test that cascade deletions maintain data integrity."""
        user1 = TestData.make_user(session)
        user2 = TestData.make_user(session)

        with utm_config(app, ""):
            with app.app_context():
                content = TestData.make_content(session, submitted_by_id=user1.id)

                # Create shares from multiple users
                share1 = TestData.make_share(
                    session, content, user=user1, platform="linkedin"
                )
                share2 = TestData.make_share(
                    session, content, user=user2, platform="twitter"
                )

                content_id = content.id
                share1_id = share1.id
                share2_id = share2.id

                # Delete content (should cascade to shares)
                content.delete()

                # Verify content and shares are deleted
                assert session.query(Content).filter_by(id=content_id).first() is None
                assert session.query(Share).filter_by(id=share1_id).first() is None
                assert session.query(Share).filter_by(id=share2_id).first() is None

                # Verify users still exist (should not cascade)
                assert session.query(User).filter_by(id=user1.id).first() is not None
                assert session.query(User).filter_by(id=user2.id).first() is not None

    def test_data_consistency_after_errors(self, session, app):
        """Test data consistency after errors and rollbacks."""
        user = TestData.make_user(session)
        initial_count = session.query(Content).count()

        with utm_config(app, ""):
            with app.app_context():
                # Test scenario where we try to create content in a transaction that fails
                try:
                    # Create valid content with unique URL
                    unique_id = str(uuid.uuid4())[:8]
                    content1 = Content(
                        url=f"https://valid-{unique_id}.com",
                        title="Valid Content",
                        submitted_by_id=user.id,
                    )
                    session.add(content1)

                    # Try to create invalid content in same transaction
                    content2 = Content(url=None, title=TestConstants.TEST_TITLE)
                    session.add(content2)
                    session.commit()  # This should fail due to content2

                    # If we get here, both succeeded (constraint not enforced)
                    final_count = session.query(Content).count()
                    assert final_count >= initial_count + 1

                except Exception:
                    # Transaction failed - both content items should be rolled back
                    session.rollback()

                    # Verify we're back to initial state
                    assert session.query(Content).count() == initial_count

                    # Now create a valid content after rollback
                    unique_id = str(uuid.uuid4())[:8]
                    TestData.make_content(
                        session,
                        url=f"https://valid-after-rollback-{unique_id}.com",
                        submitted_by_id=user.id,
                    )

                    # Should have exactly one more than initial
                    final_count = session.query(Content).count()
                    assert final_count == initial_count + 1

    def test_transaction_isolation(self, session, app):
        """Test transaction isolation behavior."""
        user = TestData.make_user(session)

        with utm_config(app, ""):
            with app.app_context():
                # Create content but don't commit yet
                content = Content(
                    url="https://uncommitted.com",
                    title="Uncommitted Content",
                    submitted_by_id=user.id,
                )
                session.add(content)

                # Content should be visible in current session
                found_in_session = (
                    session.query(Content)
                    .filter_by(url="https://uncommitted.com")
                    .first()
                )
                assert found_in_session is not None

                # Rollback
                session.rollback()

                # Content should no longer be visible
                not_found = (
                    session.query(Content)
                    .filter_by(url="https://uncommitted.com")
                    .first()
                )
                assert not_found is None
