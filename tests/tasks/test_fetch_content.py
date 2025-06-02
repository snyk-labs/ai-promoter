import pytest
import uuid
import xml.etree.ElementTree as ET
from unittest.mock import patch, MagicMock, mock_open
from datetime import datetime
import requests
import feedparser

from tasks.fetch_content import fetch_content_task
from models.content import Content
from models.user import User
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


# Generate unique identifier for this test run to avoid conflicts in parallel execution
TEST_RUN_ID = str(uuid.uuid4())[:8]


# --- Test Constants ---
class TestConstants:
    """Test constants for consistent data across tests."""

    # Feed URLs and content
    TEST_FEED_URL = f"https://example.com/feed-{TEST_RUN_ID}.xml"
    TEST_FEED_URL_2 = f"https://example.com/another-feed-{TEST_RUN_ID}.xml"
    TEST_ENTRY_URL = f"https://example.com/article-{TEST_RUN_ID}"
    TEST_ENTRY_URL_2 = f"https://example.com/article-2-{TEST_RUN_ID}"
    TEST_ENTRY_TITLE = f"Test Article {TEST_RUN_ID}"
    TEST_ENTRY_TITLE_LONG = (
        f"Very Long Article Title That Exceeds Length Limits {TEST_RUN_ID} " + "x" * 200
    )

    # Configuration
    TIMEOUT = 10
    TITLE_MAX_LENGTH = 250
    TITLE_PREFIX_ALLOWANCE = 15  # Extra space for "Processing: " prefix

    # Performance test sizes
    LARGE_FEED_SIZE = 50
    MIXED_CONTENT_SIZE = 25

    # Task messages
    MESSAGES = {
        "no_feeds": "No content feeds configured.",
        "no_url": "No URL found for an entry",
        "already_exists": "already exists. Skipping.",
        "new_content": "New content found:",
        "dispatched": "Dispatched scrape_content_task",
        "failed_fetch": "Failed to fetch RSS feed",
        "malformed_feed": "Feed .* may be malformed. Bozo bit set:",
    }

    # Error scenarios
    ERROR_TYPES = {
        "network_timeout": requests.exceptions.Timeout("Connection timeout"),
        "network_error": requests.exceptions.ConnectionError("Connection failed"),
        "http_error": requests.exceptions.HTTPError("404 Client Error"),
        "invalid_xml": "Invalid XML content",
    }


# --- Test Helpers ---
class TestHelpers:
    """Helper methods for testing."""

    @staticmethod
    def create_test_user(session, **overrides):
        """Create a test user with unique identifiers."""
        unique_id = str(uuid.uuid4())[:8]
        defaults = {
            "email": f"user-{unique_id}@example.com",
            "name": f"Test User {unique_id}",
            "is_admin": False,
            "auth_type": "password",
        }
        defaults.update(overrides)

        user = User(**defaults)
        session.add(user)
        session.commit()
        return user

    @staticmethod
    def create_test_content(session, user=None, **overrides):
        """Create test content with unique identifiers."""
        if user is None:
            user = TestHelpers.create_test_user(session)

        unique_id = str(uuid.uuid4())[:8]
        defaults = {
            "url": f"https://example.com/content-{unique_id}",
            "title": f"Test Content {unique_id}",
            "submitted_by_id": user.id,
        }
        defaults.update(overrides)

        content = Content(**defaults)
        session.add(content)
        session.commit()
        return content

    @staticmethod
    def create_valid_rss_feed(entries=None):
        """Create a valid RSS feed XML string."""
        if entries is None:
            entries = [
                {
                    "title": TestConstants.TEST_ENTRY_TITLE,
                    "link": TestConstants.TEST_ENTRY_URL,
                    "description": f"Test description for {TEST_RUN_ID}",
                }
            ]

        rss_items = ""
        for entry in entries:
            rss_items += f"""
                <item>
                    <title><![CDATA[{entry.get('title', 'Untitled')}]]></title>
                    <link>{entry.get('link', '')}</link>
                    <description><![CDATA[{entry.get('description', '')}]]></description>
                </item>
            """

        return f"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>Test Feed {TEST_RUN_ID}</title>
                <description>Test RSS feed for testing</description>
                <link>https://example.com</link>
                {rss_items}
            </channel>
        </rss>"""

    @staticmethod
    def setup_mock_network_response(mock_get, content=None):
        """Setup a standard mock network response."""
        if content is None:
            content = TestHelpers.create_valid_rss_feed()

        mock_response = MagicMock()
        mock_response.content = (
            content.encode() if isinstance(content, str) else content
        )
        mock_get.return_value = mock_response
        return mock_response

    @staticmethod
    def setup_mock_feed_parsing(mock_parse, entries_data):
        """Setup mock feed parsing with given entries data."""
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_entries = []

        for entry_data in entries_data:
            mock_entry = MagicMock()
            mock_entry.get.side_effect = (
                lambda key, default=None, data=entry_data: data.get(key, default)
            )
            mock_entries.append(mock_entry)

        mock_feed.entries = mock_entries
        mock_parse.return_value = mock_feed
        return mock_feed

    @staticmethod
    def setup_mock_scrape_task(mock_scrape_task):
        """Setup mock scrape task with standard return value."""
        mock_task_result = MagicMock()
        mock_scrape_task.delay.return_value = mock_task_result
        return mock_task_result

    @staticmethod
    def assert_content_created_correctly(
        content, expected_url, expected_title_prefix="Processing:"
    ):
        """Assert that content was created with correct attributes."""
        assert content is not None, "Content should have been created"
        assert (
            content.url == expected_url
        ), f"Expected URL {expected_url}, got {content.url}"
        assert content.title.startswith(
            expected_title_prefix
        ), f"Title should start with '{expected_title_prefix}'"

    @staticmethod
    def assert_scrape_task_called_correctly(mock_scrape_task, content_id, url):
        """Assert that scrape_content_task was called with correct parameters."""
        mock_scrape_task.delay.assert_called_once_with(content_id=content_id, url=url)


# --- Test Data Factory ---
class TestData:
    """Factory for creating test data."""

    @staticmethod
    def make_feed_config(feed_urls=None):
        """Create test feed configuration."""
        if feed_urls is None:
            feed_urls = [TestConstants.TEST_FEED_URL]
        return {"CONTENT_FEEDS": feed_urls}

    @staticmethod
    def make_entry_data(title=None, url=None, description=None):
        """Create test entry data."""
        return {
            "title": title or TestConstants.TEST_ENTRY_TITLE,
            "link": url or TestConstants.TEST_ENTRY_URL,
            "description": description or f"Test description for {TEST_RUN_ID}",
        }

    @staticmethod
    def make_multiple_entries(count, url_prefix="article"):
        """Create multiple test entries."""
        return [
            TestData.make_entry_data(
                title=f"Article {i} {TEST_RUN_ID}",
                url=f"https://example.com/{url_prefix}-{i}-{TEST_RUN_ID}",
                description=f"Description for article {i}",
            )
            for i in range(count)
        ]


# --- Unit Tests (No Database) ---
@pytest.mark.unit
class TestFetchContentTaskUnit:
    """Unit tests for fetch_content_task function."""

    def test_no_content_feeds_configured(self, app):
        """Test behavior when no content feeds are configured."""
        with app.app_context():
            app.config["CONTENT_FEEDS"] = None
            result = fetch_content_task.apply()

        assert result.successful()
        assert result.result == TestConstants.MESSAGES["no_feeds"]

    def test_empty_content_feeds_configured(self, app):
        """Test behavior when content feeds list is empty."""
        with app.app_context():
            app.config["CONTENT_FEEDS"] = []
            result = fetch_content_task.apply()

        assert result.successful()
        assert result.result == TestConstants.MESSAGES["no_feeds"]

    @patch("tasks.fetch_content.requests.get")
    def test_network_timeout_handling(self, mock_get, app):
        """Test handling of network timeouts."""
        with app.app_context():
            app.config.update(TestData.make_feed_config())
            mock_get.side_effect = TestConstants.ERROR_TYPES["network_timeout"]

            with patch("tasks.fetch_content.logger") as mock_logger:
                result = fetch_content_task.apply()

            mock_get.assert_called_once_with(
                TestConstants.TEST_FEED_URL, timeout=TestConstants.TIMEOUT
            )
            mock_logger.error.assert_called()
            error_message = mock_logger.error.call_args[0][0]
            assert "Failed to fetch RSS feed" in error_message
            assert TestConstants.TEST_FEED_URL in error_message
            assert result.successful()

    @patch("tasks.fetch_content.requests.get")
    def test_network_connection_error_handling(self, mock_get, app):
        """Test handling of network connection errors."""
        with app.app_context():
            app.config.update(TestData.make_feed_config())
            mock_get.side_effect = TestConstants.ERROR_TYPES["network_error"]

            with patch("tasks.fetch_content.logger") as mock_logger:
                result = fetch_content_task.apply()

            mock_logger.error.assert_called()
            error_message = mock_logger.error.call_args[0][0]
            assert "Failed to fetch RSS feed" in error_message
            assert result.successful()

    @patch("tasks.fetch_content.requests.get")
    def test_http_error_handling(self, mock_get, app):
        """Test handling of HTTP errors (404, 500, etc.)."""
        with app.app_context():
            app.config.update(TestData.make_feed_config())
            mock_get.side_effect = TestConstants.ERROR_TYPES["http_error"]

            with patch("tasks.fetch_content.logger") as mock_logger:
                result = fetch_content_task.apply()

            mock_logger.error.assert_called()
            error_message = mock_logger.error.call_args[0][0]
            assert "Failed to fetch RSS feed" in error_message
            assert result.successful()

    @patch("tasks.fetch_content.requests.get")
    @patch("tasks.fetch_content.feedparser.parse")
    def test_malformed_feed_warning(self, mock_parse, mock_get, app):
        """Test handling of malformed RSS feeds."""
        with app.app_context():
            app.config.update(TestData.make_feed_config())
            TestHelpers.setup_mock_network_response(mock_get, b"malformed xml")

            # Simulate feedparser detecting malformed feed
            mock_feed = MagicMock()
            mock_feed.bozo = True
            mock_feed.bozo_exception = "XML parsing error"
            mock_feed.entries = []
            mock_parse.return_value = mock_feed

            with patch("tasks.fetch_content.logger") as mock_logger:
                result = fetch_content_task.apply()

            mock_logger.warning.assert_called()
            warning_message = mock_logger.warning.call_args[0][0]
            assert "may be malformed" in warning_message
            assert "Bozo bit set" in warning_message
            assert result.successful()

    @patch("tasks.fetch_content.requests.get")
    @patch("tasks.fetch_content.feedparser.parse")
    def test_feed_entry_without_url(self, mock_parse, mock_get, app):
        """Test handling of feed entries that don't have URLs."""
        with app.app_context():
            app.config.update(TestData.make_feed_config())
            TestHelpers.setup_mock_network_response(mock_get)

            # Create feed with entry missing link
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_entry = MagicMock()
            mock_entry.get.side_effect = lambda key, default=None: (
                None if key == "link" else f"Test Title {TEST_RUN_ID}"
            )
            mock_feed.entries = [mock_entry]
            mock_parse.return_value = mock_feed

            with patch("tasks.fetch_content.logger") as mock_logger:
                result = fetch_content_task.apply()

            mock_logger.warning.assert_called()
            warning_message = mock_logger.warning.call_args[0][0]
            assert "No URL found for an entry" in warning_message
            assert result.successful()

    @pytest.mark.unit
    def test_title_truncation_logic(self):
        """Test that very long titles are properly truncated."""
        long_title = TestConstants.TEST_ENTRY_TITLE_LONG

        # Simulate the truncation logic from the task
        if len(long_title) > TestConstants.TITLE_MAX_LENGTH:
            truncated = long_title[:247] + "..."
        else:
            truncated = long_title

        assert len(truncated) <= TestConstants.TITLE_MAX_LENGTH
        assert truncated.endswith("...")
        assert long_title.startswith(truncated[:-3])  # Check original content preserved

    @patch("tasks.fetch_content.requests.get")
    def test_duplicate_feed_url_deduplication(self, mock_get, app):
        """Test that duplicate feed URLs are processed only once."""
        with app.app_context():
            # Configure with duplicate URLs
            duplicate_urls = [
                TestConstants.TEST_FEED_URL,
                TestConstants.TEST_FEED_URL,  # Duplicate
                TestConstants.TEST_FEED_URL_2,
            ]
            app.config.update(TestData.make_feed_config(duplicate_urls))

            mock_get.side_effect = TestConstants.ERROR_TYPES["network_error"]

            with patch("tasks.fetch_content.logger"):
                result = fetch_content_task.apply()

            # Should only call requests.get twice (unique URLs only)
            assert mock_get.call_count == 2
            calls = [call[0][0] for call in mock_get.call_args_list]
            assert TestConstants.TEST_FEED_URL in calls
            assert TestConstants.TEST_FEED_URL_2 in calls
            assert result.successful()

    @patch("tasks.fetch_content.requests.get")
    def test_empty_feed_url_skipping(self, mock_get, app):
        """Test that empty or None feed URLs are skipped."""
        with app.app_context():
            feed_urls = [
                TestConstants.TEST_FEED_URL,
                "",  # Empty string
                None,  # None value
                TestConstants.TEST_FEED_URL_2,
            ]
            app.config.update(TestData.make_feed_config(feed_urls))

            mock_get.side_effect = TestConstants.ERROR_TYPES["network_error"]

            result = fetch_content_task.apply()

        # Should only call requests.get twice (non-empty URLs only)
        assert mock_get.call_count == 2
        assert result.successful()


# --- Integration Tests (With Database) ---
@pytest.mark.integration
class TestFetchContentTaskIntegration:
    """Integration tests for fetch_content_task with database operations."""

    @patch("tasks.fetch_content.requests.get")
    @patch("tasks.fetch_content.feedparser.parse")
    @patch("tasks.fetch_content.scrape_content_task")
    def test_successful_new_content_processing(
        self, mock_scrape_task, mock_parse, mock_get, session, app
    ):
        """Test successful processing of new content from RSS feed."""
        with app.app_context():
            app.config.update(TestData.make_feed_config())

            # Setup mocks
            TestHelpers.setup_mock_network_response(mock_get)
            entry_data = [TestData.make_entry_data()]
            TestHelpers.setup_mock_feed_parsing(mock_parse, entry_data)
            TestHelpers.setup_mock_scrape_task(mock_scrape_task)

            result = fetch_content_task.apply()

            # Verify content was created in database
            created_content = Content.query.filter_by(
                url=TestConstants.TEST_ENTRY_URL
            ).first()
            TestHelpers.assert_content_created_correctly(
                created_content, TestConstants.TEST_ENTRY_URL
            )

            # Verify scrape task was called
            TestHelpers.assert_scrape_task_called_correctly(
                mock_scrape_task, created_content.id, TestConstants.TEST_ENTRY_URL
            )

            # Verify return message
            assert result.successful()
            assert "Initiated scraping for 1 new items" in result.result

    @patch("tasks.fetch_content.requests.get")
    @patch("tasks.fetch_content.feedparser.parse")
    def test_existing_content_skipping(self, mock_parse, mock_get, session, app):
        """Test that existing content URLs are skipped."""
        with app.app_context():
            # Create existing content in database
            TestHelpers.create_test_content(session, url=TestConstants.TEST_ENTRY_URL)

            app.config.update(TestData.make_feed_config())

            # Setup mocks
            TestHelpers.setup_mock_network_response(mock_get)
            entry_data = [TestData.make_entry_data()]
            TestHelpers.setup_mock_feed_parsing(mock_parse, entry_data)

            with patch("tasks.fetch_content.logger") as mock_logger:
                result = fetch_content_task.apply()

                # Should log that content already exists
                mock_logger.debug.assert_called()
                debug_message = mock_logger.debug.call_args[0][0]
                assert "already exists. Skipping" in debug_message

                # Should not create new content
                content_count = Content.query.filter_by(
                    url=TestConstants.TEST_ENTRY_URL
                ).count()
                assert content_count == 1  # Only the original one

                # Return message should indicate 0 new items
                assert result.successful()
                assert "Initiated scraping for 0 new items" in result.result

    @patch("tasks.fetch_content.requests.get")
    @patch("tasks.fetch_content.feedparser.parse")
    @patch("tasks.fetch_content.scrape_content_task")
    def test_multiple_feeds_processing(
        self, mock_scrape_task, mock_parse, mock_get, session, app
    ):
        """Test processing of multiple RSS feeds."""
        with app.app_context():
            feed_urls = [TestConstants.TEST_FEED_URL, TestConstants.TEST_FEED_URL_2]
            app.config.update(TestData.make_feed_config(feed_urls))

            # Create unique entries for each feed
            entries_feed1 = [
                TestData.make_entry_data(
                    title="Article from first feed",
                    url=f"https://example.com/article-from-feed1-{TEST_RUN_ID}",
                )
            ]
            entries_feed2 = [
                TestData.make_entry_data(
                    title="Article from second feed",
                    url=f"https://example.com/article-from-feed2-{TEST_RUN_ID}",
                )
            ]

            # Setup network responses to return different content for each feed
            call_count = 0

            def mock_get_side_effect(url, timeout):
                nonlocal call_count
                call_count += 1
                entries = entries_feed1 if call_count == 1 else entries_feed2
                rss_content = TestHelpers.create_valid_rss_feed(entries)
                return TestHelpers.setup_mock_network_response(mock_get, rss_content)

            mock_get.side_effect = mock_get_side_effect

            # Setup feed parsing to return the corresponding entries
            parse_call_count = 0

            def mock_parse_side_effect(content):
                nonlocal parse_call_count
                parse_call_count += 1
                entries = entries_feed1 if parse_call_count == 1 else entries_feed2
                return TestHelpers.setup_mock_feed_parsing(mock_parse, entries)

            mock_parse.side_effect = mock_parse_side_effect
            TestHelpers.setup_mock_scrape_task(mock_scrape_task)

            result = fetch_content_task.apply()

            # Verify both feeds were processed
            assert mock_get.call_count == 2
            content_count = Content.query.count()
            assert content_count == 2

            # Verify both pieces of content were created
            content1 = Content.query.filter_by(url=entries_feed1[0]["link"]).first()
            content2 = Content.query.filter_by(url=entries_feed2[0]["link"]).first()
            assert content1 is not None
            assert content2 is not None

            assert result.successful()
            assert "Initiated scraping for 2 new items" in result.result

    @patch("tasks.fetch_content.requests.get")
    @patch("tasks.fetch_content.feedparser.parse")
    @patch("tasks.fetch_content.scrape_content_task")
    def test_database_error_handling(
        self, mock_scrape_task, mock_parse, mock_get, session, app
    ):
        """Test handling of database errors during content creation."""
        with app.app_context():
            app.config.update(TestData.make_feed_config())

            # Setup mocks
            TestHelpers.setup_mock_network_response(mock_get)
            entry_data = [TestData.make_entry_data()]
            TestHelpers.setup_mock_feed_parsing(mock_parse, entry_data)

            # Mock db.session.commit to raise an exception
            with patch("tasks.fetch_content.db.session.commit") as mock_commit:
                mock_commit.side_effect = SQLAlchemyError("Database error")

                with patch("tasks.fetch_content.logger") as mock_logger:
                    result = fetch_content_task.apply()

                    # Should log error about content creation failure
                    mock_logger.error.assert_called()
                    error_message = mock_logger.error.call_args[0][0]
                    assert "Error creating initial content item" in error_message

                    # Should not have created any content
                    content_count = Content.query.filter_by(
                        url=TestConstants.TEST_ENTRY_URL
                    ).count()
                    assert content_count == 0

                    # Should indicate 0 new items processed
                    assert result.successful()
                    assert "Initiated scraping for 0 new items" in result.result

    @patch("tasks.fetch_content.requests.get")
    @patch("tasks.fetch_content.feedparser.parse")
    @patch("tasks.fetch_content.scrape_content_task")
    def test_scrape_task_dispatch_error_handling(
        self, mock_scrape_task, mock_parse, mock_get, session, app
    ):
        """Test handling of errors when dispatching scrape tasks."""
        with app.app_context():
            app.config.update(TestData.make_feed_config())

            # Setup mocks
            TestHelpers.setup_mock_network_response(mock_get)
            entry_data = [TestData.make_entry_data()]
            TestHelpers.setup_mock_feed_parsing(mock_parse, entry_data)

            # Setup scrape task to raise an exception
            mock_scrape_task.delay.side_effect = Exception("Celery error")

            with patch("tasks.fetch_content.logger") as mock_logger:
                result = fetch_content_task.apply()

                # Should log error about scrape task dispatch failure
                mock_logger.error.assert_called()
                error_message = mock_logger.error.call_args[0][0]
                assert "Error creating initial content item" in error_message
                assert "dispatching scrape task" in error_message

                # Should still have created the content item
                created_content = Content.query.filter_by(
                    url=TestConstants.TEST_ENTRY_URL
                ).first()
                assert created_content is not None
                assert result.successful()

    @patch("tasks.fetch_content.requests.get")
    @patch("tasks.fetch_content.feedparser.parse")
    @patch("tasks.fetch_content.scrape_content_task")
    def test_long_title_truncation_integration(
        self, mock_scrape_task, mock_parse, mock_get, session, app
    ):
        """Test that long titles are properly truncated in database operations."""
        with app.app_context():
            app.config.update(TestData.make_feed_config())

            # Setup mocks with long title
            TestHelpers.setup_mock_network_response(mock_get)
            entry_data = [
                TestData.make_entry_data(title=TestConstants.TEST_ENTRY_TITLE_LONG)
            ]
            TestHelpers.setup_mock_feed_parsing(mock_parse, entry_data)
            TestHelpers.setup_mock_scrape_task(mock_scrape_task)

            result = fetch_content_task.apply()

            # Verify content was created with truncated title
            created_content = Content.query.filter_by(
                url=TestConstants.TEST_ENTRY_URL
            ).first()
            assert created_content is not None
            # The title should be truncated but may be slightly longer due to "Processing: " prefix
            assert (
                len(created_content.title)
                <= TestConstants.TITLE_MAX_LENGTH + TestConstants.TITLE_PREFIX_ALLOWANCE
            )
            assert created_content.title.endswith("...")
            assert "Processing:" in created_content.title
            assert result.successful()


# --- Performance Tests ---
@pytest.mark.slow
@pytest.mark.integration
class TestFetchContentTaskPerformance:
    """Performance tests for fetch_content_task."""

    @patch("tasks.fetch_content.requests.get")
    @patch("tasks.fetch_content.feedparser.parse")
    @patch("tasks.fetch_content.scrape_content_task")
    def test_large_feed_processing(
        self, mock_scrape_task, mock_parse, mock_get, session, app
    ):
        """Test processing of feeds with many entries."""
        with app.app_context():
            app.config.update(TestData.make_feed_config())

            # Create large feed
            num_entries = TestConstants.LARGE_FEED_SIZE
            entries = TestData.make_multiple_entries(num_entries)

            # Setup mocks
            TestHelpers.setup_mock_network_response(
                mock_get, TestHelpers.create_valid_rss_feed(entries)
            )
            TestHelpers.setup_mock_feed_parsing(mock_parse, entries)
            TestHelpers.setup_mock_scrape_task(mock_scrape_task)

            result = fetch_content_task.apply()

            # Verify all entries were processed
            content_count = Content.query.count()
            assert content_count == num_entries

            assert result.successful()
            assert f"Initiated scraping for {num_entries} new items" in result.result
            assert mock_scrape_task.delay.call_count == num_entries

    @patch("tasks.fetch_content.requests.get")
    @patch("tasks.fetch_content.feedparser.parse")
    @patch("tasks.fetch_content.scrape_content_task")
    def test_mixed_new_and_existing_content_performance(
        self, mock_scrape_task, mock_parse, mock_get, session, app
    ):
        """Test performance with mix of new and existing content."""
        with app.app_context():
            num_existing = TestConstants.MIXED_CONTENT_SIZE

            # Create existing content
            existing_entries = TestData.make_multiple_entries(num_existing, "existing")
            for entry in existing_entries:
                TestHelpers.create_test_content(session, url=entry["link"])

            # Create new entries
            new_entries = TestData.make_multiple_entries(num_existing, "new")

            # Combine all entries for the feed
            all_entries = existing_entries + new_entries

            app.config.update(TestData.make_feed_config())

            # Setup mocks
            TestHelpers.setup_mock_network_response(
                mock_get, TestHelpers.create_valid_rss_feed(all_entries)
            )
            TestHelpers.setup_mock_feed_parsing(mock_parse, all_entries)
            TestHelpers.setup_mock_scrape_task(mock_scrape_task)

            result = fetch_content_task.apply()

            # Verify correct counts
            content_count = Content.query.count()
            assert content_count == num_existing * 2  # existing + new

            assert result.successful()
            assert f"Initiated scraping for {num_existing} new items" in result.result
            assert mock_scrape_task.delay.call_count == num_existing  # Only new items


# --- Edge Cases and Error Handling ---
@pytest.mark.integration
class TestFetchContentTaskEdgeCases:
    """Test edge cases and error scenarios."""

    @patch("tasks.fetch_content.requests.get")
    @patch("tasks.fetch_content.feedparser.parse")
    def test_feed_with_entries_missing_titles(self, mock_parse, mock_get, session, app):
        """Test handling of feed entries that don't have titles."""
        with app.app_context():
            app.config.update(TestData.make_feed_config())

            TestHelpers.setup_mock_network_response(mock_get)

            # Setup feed parsing with entry missing title
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_entry = MagicMock()
            # Simulate entry.get("title", entry_url) - when title is None, return the default (entry_url)

            def mock_get_side_effect(key, default=None):
                if key == "link":
                    return TestConstants.TEST_ENTRY_URL
                elif key == "title":
                    return default  # This will be entry_url when called from the task
                return None

            mock_entry.get.side_effect = mock_get_side_effect
            mock_feed.entries = [mock_entry]
            mock_parse.return_value = mock_feed

            with patch("tasks.fetch_content.scrape_content_task") as mock_scrape_task:
                TestHelpers.setup_mock_scrape_task(mock_scrape_task)

                result = fetch_content_task.apply()

                # Should still create content with URL as fallback title
                created_content = Content.query.filter_by(
                    url=TestConstants.TEST_ENTRY_URL
                ).first()
                assert created_content is not None
                assert TestConstants.TEST_ENTRY_URL in created_content.title
                assert result.successful()

    @patch("tasks.fetch_content.requests.get")
    @patch("tasks.fetch_content.feedparser.parse")
    def test_feed_with_empty_entries_list(self, mock_parse, mock_get, session, app):
        """Test handling of feeds with no entries."""
        with app.app_context():
            app.config.update(TestData.make_feed_config())

            # Setup mocks with empty entries
            TestHelpers.setup_mock_network_response(
                mock_get, TestHelpers.create_valid_rss_feed([])
            )
            TestHelpers.setup_mock_feed_parsing(mock_parse, [])

            result = fetch_content_task.apply()

            # Should not create any content
            content_count = Content.query.count()
            assert content_count == 0

            assert result.successful()
            assert "Initiated scraping for 0 new items" in result.result

    @patch("tasks.fetch_content.requests.get")
    def test_invalid_xml_response(self, mock_get, session, app):
        """Test handling of invalid XML responses."""
        with app.app_context():
            app.config.update(TestData.make_feed_config())

            # Setup network response with invalid XML
            TestHelpers.setup_mock_network_response(
                mock_get, b"This is not valid XML content"
            )

            with patch("tasks.fetch_content.logger"):
                result = fetch_content_task.apply()

                # feedparser should handle invalid XML gracefully
                content_count = Content.query.count()
                assert content_count == 0
                assert result.successful()

    @pytest.mark.parametrize(
        "feed_config",
        [
            [],  # Empty list
            None,  # None value
            [""],  # List with empty string
            [None],  # List with None
            ["", None, ""],  # Mixed empty values
        ],
    )
    def test_various_empty_feed_configurations(self, session, app, feed_config):
        """Test handling of various empty feed configurations."""
        with app.app_context():
            app.config["CONTENT_FEEDS"] = feed_config

            result = fetch_content_task.apply()

            assert result.successful()
            if not feed_config:
                assert result.result == TestConstants.MESSAGES["no_feeds"]
            else:
                # Should handle gracefully without making any network requests
                assert "Initiated scraping for 0 new items" in result.result

    @patch("tasks.fetch_content.requests.get")
    @patch("tasks.fetch_content.feedparser.parse")
    @patch("tasks.fetch_content.scrape_content_task")
    def test_unicode_content_handling(
        self, mock_scrape_task, mock_parse, mock_get, session, app
    ):
        """Test handling of Unicode characters in feed content."""
        with app.app_context():
            app.config.update(TestData.make_feed_config())

            # Create entry with Unicode content
            unicode_title = f"Article with émojis 🚀 and spëcial chärs {TEST_RUN_ID}"
            unicode_url = f"https://example.com/artículo-{TEST_RUN_ID}"
            unicode_entry = TestData.make_entry_data(
                title=unicode_title,
                url=unicode_url,
                description="Description with Unicode: café naïve résumé",
            )

            # Setup mocks
            TestHelpers.setup_mock_network_response(
                mock_get,
                TestHelpers.create_valid_rss_feed([unicode_entry]).encode("utf-8"),
            )
            TestHelpers.setup_mock_feed_parsing(mock_parse, [unicode_entry])
            TestHelpers.setup_mock_scrape_task(mock_scrape_task)

            result = fetch_content_task.apply()

            # Should handle Unicode content correctly
            created_content = Content.query.filter_by(url=unicode_url).first()
            assert created_content is not None
            assert unicode_title in created_content.title
            assert created_content.url == unicode_url

            # Should have initiated scraping
            TestHelpers.assert_scrape_task_called_correctly(
                mock_scrape_task, created_content.id, unicode_url
            )
            assert result.successful()
