import pytest
import uuid
import json
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import google.generativeai as genai

from services.content_processor import ContentProcessor
from models.content import Content
from models.user import User
from sqlalchemy.exc import SQLAlchemyError

# Generate unique identifier for this test run to avoid conflicts in parallel execution
TEST_RUN_ID = str(uuid.uuid4())[:8]


# --- Test Constants ---
class TestConstants:
    """Test constants for consistent data across tests."""

    TEST_URL = f"https://example.com/article-{TEST_RUN_ID}"
    TEST_TITLE = f"Test Article Title {TEST_RUN_ID}"
    TEST_DESCRIPTION = f"Test article description for {TEST_RUN_ID}"
    TEST_IMAGE_URL = f"https://example.com/image-{TEST_RUN_ID}.jpg"
    TEST_OG_IMAGE_URL = f"https://example.com/og-image-{TEST_RUN_ID}.jpg"
    TEST_MARKDOWN_CONTENT = f"""
# Test Article {TEST_RUN_ID}

This is a test article with markdown content.

![Test Image]({TEST_IMAGE_URL})

## Key Points
- Point 1 for {TEST_RUN_ID}
- Point 2 for {TEST_RUN_ID}
- Point 3 for {TEST_RUN_ID}
"""

    # Firecrawl API responses
    FIRECRAWL_SUCCESS_RESPONSE = {
        "markdown": TEST_MARKDOWN_CONTENT,
        "metadata": {
            "title": TEST_TITLE,
            "description": TEST_DESCRIPTION,
            "og:image": TEST_OG_IMAGE_URL,
        },
    }

    FIRECRAWL_NO_METADATA_RESPONSE = {
        "markdown": TEST_MARKDOWN_CONTENT,
    }

    # Gemini API responses
    GEMINI_SUCCESS_RESPONSE = {
        "Title": TEST_TITLE,
        "Description": TEST_DESCRIPTION,
        "Image URL": TEST_IMAGE_URL,
        "Publish Date": "December 25, 2023",
        "Key Points": [
            f"Key point 1 for {TEST_RUN_ID}",
            f"Key point 2 for {TEST_RUN_ID}",
            f"Key point 3 for {TEST_RUN_ID}",
        ],
        "Target Audience": "Software developers",
        "Tone": "Technical and informative",
    }

    GEMINI_MINIMAL_RESPONSE = {
        "Title": TEST_TITLE,
        "Description": "Not available",
        "Image URL": None,
        "Publish Date": "Not available",
        "Key Points": [],
        "Target Audience": "General",
        "Tone": "Neutral",
    }

    # Error messages
    ERROR_MESSAGES = {
        "no_firecrawl_key": "FIRECRAWL_API_KEY not configured in Flask app",
        "no_gemini_key": "GEMINI_API_KEY environment variable not set",
        "content_not_found": f"Content with ID 999 not found.",
        "firecrawl_empty": "Failed to scrape content from URL - empty result",
        "firecrawl_no_markdown": "Failed to scrape content from URL - markdown content not available",
        "gemini_parse_error": "Failed to parse content information from Gemini response",
    }

    # Date formats for testing
    DATE_FORMATS = [
        ("December 25, 2023", "%B %d, %Y"),
        ("2023-12-25", "%Y-%m-%d"),
        ("Invalid Date", None),  # Should fall back to current time
    ]

    # Additional edge case data
    EDGE_CASE_RESPONSES = {
        "empty_gemini": {},
        "null_fields": {
            "Title": None,
            "Description": None,
            "Image URL": None,
            "Publish Date": None,
        },
        "unicode_content": {
            "Title": f"Tëst Artícle with Ümláuts {TEST_RUN_ID}",
            "Description": f"Dëscription with émojis 🚀 and spëcial chärs {TEST_RUN_ID}",
            "Image URL": f"https://example.com/imägé-{TEST_RUN_ID}.jpg",
            "Publish Date": "December 25, 2023",
        },
    }


# --- Test Helpers ---
class ContentProcessorTestHelpers:
    """Helper methods for testing ContentProcessor."""

    @staticmethod
    def setup_basic_mocks(mock_current_app):
        """Setup basic mock configuration that's used across many tests."""
        mock_config = Mock()
        mock_config.get.return_value = "test-firecrawl-key"
        mock_current_app.config = mock_config

    @staticmethod
    def create_mock_firecrawl_response(**overrides):
        """Create a mock Firecrawl response with customizable fields."""
        mock_response = Mock()
        defaults = TestConstants.FIRECRAWL_SUCCESS_RESPONSE.copy()
        defaults.update(overrides)

        mock_response.markdown = defaults.get("markdown")
        mock_response.metadata = defaults.get("metadata", {})
        return mock_response

    @staticmethod
    def create_mock_gemini_response(response_text, **overrides):
        """Create a mock Gemini response."""
        mock_response = Mock()
        mock_response.text = response_text
        return mock_response

    @staticmethod
    def setup_gemini_mock(mock_genai, response_data):
        """Setup Gemini mock with response data."""
        mock_model = Mock()
        mock_genai.GenerativeModel.return_value = mock_model

        json_response = json.dumps(response_data)
        mock_response = ContentProcessorTestHelpers.create_mock_gemini_response(
            json_response
        )
        mock_model.generate_content.return_value = mock_response

        return mock_model

    @staticmethod
    def create_test_content(session, **overrides):
        """Create a test content item in the database."""
        unique_id = str(uuid.uuid4())[:8]
        defaults = {
            "url": f"https://example.com/article-{unique_id}",
            "title": f"Original Title {unique_id}",
            "excerpt": f"Original excerpt {unique_id}",
        }
        defaults.update(overrides)

        content = Content(**defaults)
        session.add(content)
        session.commit()
        return content

    @staticmethod
    def assert_content_updated_correctly(content, expected_data):
        """Assert that content was updated with expected values."""
        for field, expected_value in expected_data.items():
            actual_value = getattr(content, field)
            assert (
                actual_value == expected_value
            ), f"Field '{field}': expected {expected_value}, got {actual_value}"

    @staticmethod
    def assert_gemini_called_with_correct_prompt(mock_gemini, expected_content):
        """Assert that Gemini was called with the correct prompt format."""
        mock_gemini.generate_content.assert_called_once()
        call_args = mock_gemini.generate_content.call_args
        prompt = call_args[0][0]

        assert "Analyze the following content" in prompt
        assert "JSON format" in prompt
        assert expected_content in prompt
        assert "Title" in prompt
        assert "Description" in prompt
        assert "Image URL" in prompt


# --- Unit Tests (No Database, Pure Logic Testing) ---
@pytest.mark.unit
class TestContentProcessorUnit:
    """Unit tests for ContentProcessor methods that don't require database."""

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    def test_content_processor_initialization_success(self, mock_current_app, app):
        """Test successful ContentProcessor initialization."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)

        with app.app_context():
            with patch("services.content_processor.FirecrawlApp") as mock_firecrawl:
                with patch("services.content_processor.genai") as mock_genai:
                    processor = ContentProcessor()

                    mock_firecrawl.assert_called_once_with(api_key="test-firecrawl-key")
                    mock_genai.configure.assert_called_once_with(
                        api_key="test-gemini-key"
                    )
                    mock_genai.GenerativeModel.assert_called_once_with("gemini-1.5-pro")
                    assert processor.firecrawl is not None
                    assert processor.gemini is not None

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    def test_content_processor_initialization_no_firecrawl_key(
        self, mock_current_app, app
    ):
        """Test ContentProcessor initialization fails without Firecrawl API key."""
        mock_config = Mock()
        mock_config.get.return_value = None
        mock_current_app.config = mock_config

        with app.app_context():
            with pytest.raises(
                ValueError, match=TestConstants.ERROR_MESSAGES["no_firecrawl_key"]
            ):
                ContentProcessor()

    @patch("services.content_processor.current_app")
    def test_content_processor_initialization_no_gemini_key(
        self, mock_current_app, app
    ):
        """Test ContentProcessor initialization fails without Gemini API key."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)

        with app.app_context():
            with patch.dict("os.environ", {}, clear=True):  # Clear GEMINI_API_KEY
                with pytest.raises(
                    ValueError, match=TestConstants.ERROR_MESSAGES["no_gemini_key"]
                ):
                    ContentProcessor()

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    @patch("services.content_processor.genai")
    def test_extract_content_info_success(
        self, mock_genai, mock_firecrawl_app, mock_current_app, app
    ):
        """Test successful content extraction from Gemini."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)
        mock_model = ContentProcessorTestHelpers.setup_gemini_mock(
            mock_genai, TestConstants.GEMINI_SUCCESS_RESPONSE
        )

        with app.app_context():
            processor = ContentProcessor()
            result = processor._extract_content_info(
                TestConstants.TEST_MARKDOWN_CONTENT
            )

            assert result == TestConstants.GEMINI_SUCCESS_RESPONSE
            ContentProcessorTestHelpers.assert_gemini_called_with_correct_prompt(
                mock_model, TestConstants.TEST_MARKDOWN_CONTENT
            )

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    @patch("services.content_processor.genai")
    def test_extract_content_info_json_wrapped_in_markdown(
        self, mock_genai, mock_firecrawl_app, mock_current_app, app
    ):
        """Test content extraction when JSON is wrapped in markdown code blocks."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)

        mock_model = Mock()
        mock_genai.GenerativeModel.return_value = mock_model

        json_response = (
            f"```json\n{json.dumps(TestConstants.GEMINI_SUCCESS_RESPONSE)}\n```"
        )
        mock_response = ContentProcessorTestHelpers.create_mock_gemini_response(
            json_response
        )
        mock_model.generate_content.return_value = mock_response

        with app.app_context():
            processor = ContentProcessor()
            result = processor._extract_content_info(
                TestConstants.TEST_MARKDOWN_CONTENT
            )

            assert result == TestConstants.GEMINI_SUCCESS_RESPONSE

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    @patch("services.content_processor.genai")
    def test_extract_content_info_invalid_json(
        self, mock_genai, mock_firecrawl_app, mock_current_app, app
    ):
        """Test content extraction fails with invalid JSON response."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)

        mock_model = Mock()
        mock_genai.GenerativeModel.return_value = mock_model

        invalid_json = "This is not valid JSON"
        mock_response = ContentProcessorTestHelpers.create_mock_gemini_response(
            invalid_json
        )
        mock_model.generate_content.return_value = mock_response

        with app.app_context():
            processor = ContentProcessor()

            with pytest.raises(
                ValueError, match=TestConstants.ERROR_MESSAGES["gemini_parse_error"]
            ):
                processor._extract_content_info(TestConstants.TEST_MARKDOWN_CONTENT)

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    @patch("services.content_processor.genai")
    def test_extract_content_info_gemini_exception(
        self, mock_genai, mock_firecrawl_app, mock_current_app, app
    ):
        """Test content extraction handles Gemini API exceptions."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)

        mock_model = Mock()
        mock_genai.GenerativeModel.return_value = mock_model
        mock_model.generate_content.side_effect = Exception("Gemini API error")

        with app.app_context():
            processor = ContentProcessor()

            with pytest.raises(Exception, match="Gemini API error"):
                processor._extract_content_info(TestConstants.TEST_MARKDOWN_CONTENT)

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    @patch("services.content_processor.genai")
    def test_extract_content_info_unicode_handling(
        self, mock_genai, mock_firecrawl_app, mock_current_app, app
    ):
        """Test content extraction handles unicode characters correctly."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)
        mock_model = ContentProcessorTestHelpers.setup_gemini_mock(
            mock_genai, TestConstants.EDGE_CASE_RESPONSES["unicode_content"]
        )

        unicode_content = f"Tëst contënt with émojis 🚀 and spëcial chärs {TEST_RUN_ID}"

        with app.app_context():
            processor = ContentProcessor()
            result = processor._extract_content_info(unicode_content)

            assert result == TestConstants.EDGE_CASE_RESPONSES["unicode_content"]
            ContentProcessorTestHelpers.assert_gemini_called_with_correct_prompt(
                mock_model, unicode_content
            )

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    @patch("services.content_processor.genai")
    def test_extract_content_info_empty_response(
        self, mock_genai, mock_firecrawl_app, mock_current_app, app
    ):
        """Test content extraction handles empty Gemini response."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)
        _ = ContentProcessorTestHelpers.setup_gemini_mock(
            mock_genai, TestConstants.EDGE_CASE_RESPONSES["empty_gemini"]
        )

        with app.app_context():
            processor = ContentProcessor()
            result = processor._extract_content_info(
                TestConstants.TEST_MARKDOWN_CONTENT
            )

            assert result == TestConstants.EDGE_CASE_RESPONSES["empty_gemini"]


# --- Integration Tests (With Database and External API Simulation) ---
@pytest.mark.integration
class TestContentProcessorIntegration:
    """Integration tests for ContentProcessor with database operations."""

    def setup_standard_mocks(
        self,
        mock_genai,
        mock_firecrawl_app,
        mock_current_app,
        gemini_response=None,
        og_image=True,
    ):
        """Setup standard mocks used across integration tests."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)

        # Setup Firecrawl mock
        mock_firecrawl_instance = Mock()
        mock_firecrawl_app.return_value = mock_firecrawl_instance

        metadata = (
            TestConstants.FIRECRAWL_SUCCESS_RESPONSE["metadata"] if og_image else {}
        )
        mock_firecrawl_instance.scrape_url.return_value = (
            ContentProcessorTestHelpers.create_mock_firecrawl_response(
                metadata=metadata
            )
        )

        # Setup Gemini mock
        response_data = gemini_response or TestConstants.GEMINI_SUCCESS_RESPONSE
        mock_model = ContentProcessorTestHelpers.setup_gemini_mock(
            mock_genai, response_data
        )

        return mock_firecrawl_instance, mock_model

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    @patch("services.content_processor.genai")
    def test_process_url_success_with_og_image(
        self, mock_genai, mock_firecrawl_app, mock_current_app, session, app
    ):
        """Test successful URL processing with og:image metadata."""
        mock_firecrawl_instance, mock_model = self.setup_standard_mocks(
            mock_genai, mock_firecrawl_app, mock_current_app, og_image=True
        )

        # Create test content
        content = ContentProcessorTestHelpers.create_test_content(session)

        with app.app_context():
            processor = ContentProcessor()
            result = processor.process_url(content.id, TestConstants.TEST_URL)

            # Assertions
            assert result is not None
            assert result.id == content.id
            assert result.title == TestConstants.TEST_TITLE
            assert result.scraped_content == TestConstants.TEST_MARKDOWN_CONTENT
            assert result.excerpt == TestConstants.TEST_DESCRIPTION
            # og:image should take precedence over extracted image
            assert result.image_url == TestConstants.TEST_OG_IMAGE_URL
            assert result.url == content.url  # URL should not change

            # Check Firecrawl was called correctly
            mock_firecrawl_instance.scrape_url.assert_called_once_with(
                TestConstants.TEST_URL, formats=["markdown", "html"]
            )

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    @patch("services.content_processor.genai")
    def test_process_url_success_without_og_image(
        self, mock_genai, mock_firecrawl_app, mock_current_app, session, app
    ):
        """Test successful URL processing without og:image metadata."""
        mock_firecrawl_instance, mock_model = self.setup_standard_mocks(
            mock_genai, mock_firecrawl_app, mock_current_app, og_image=False
        )

        # Create test content
        content = ContentProcessorTestHelpers.create_test_content(session)

        with app.app_context():
            processor = ContentProcessor()
            result = processor.process_url(content.id, TestConstants.TEST_URL)

            # Should use image from Gemini response instead
            assert result.image_url == TestConstants.TEST_IMAGE_URL

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    @patch("services.content_processor.genai")
    @pytest.mark.parametrize("date_str,expected_format", TestConstants.DATE_FORMATS)
    def test_process_url_date_parsing(
        self,
        mock_genai,
        mock_firecrawl_app,
        mock_current_app,
        session,
        app,
        date_str,
        expected_format,
    ):
        """Test URL processing with various date formats."""
        # Create response with specific date
        gemini_response = TestConstants.GEMINI_SUCCESS_RESPONSE.copy()
        gemini_response["Publish Date"] = date_str

        mock_firecrawl_instance, mock_model = self.setup_standard_mocks(
            mock_genai,
            mock_firecrawl_app,
            mock_current_app,
            gemini_response=gemini_response,
        )

        # Create test content
        content = ContentProcessorTestHelpers.create_test_content(session)

        with app.app_context():
            processor = ContentProcessor()
            result = processor.process_url(content.id, TestConstants.TEST_URL)

            if expected_format:
                expected_date = datetime.strptime(date_str, expected_format)
                assert result.publish_date.date() == expected_date.date()
            else:
                # Should fall back to current time for invalid dates
                assert isinstance(result.publish_date, datetime)

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    def test_process_url_content_not_found(
        self, mock_firecrawl_app, mock_current_app, session, app
    ):
        """Test URL processing fails when content ID doesn't exist."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)

        with app.app_context():
            processor = ContentProcessor()
            result = processor.process_url(999, TestConstants.TEST_URL)

            assert result is None

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    def test_process_url_firecrawl_empty_result(
        self, mock_firecrawl_app, mock_current_app, session, app
    ):
        """Test URL processing fails when Firecrawl returns empty result."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)

        # Setup Firecrawl to return None
        mock_firecrawl_instance = Mock()
        mock_firecrawl_app.return_value = mock_firecrawl_instance
        mock_firecrawl_instance.scrape_url.return_value = None

        # Create test content
        content = ContentProcessorTestHelpers.create_test_content(session)

        with app.app_context():
            processor = ContentProcessor()

            with pytest.raises(
                ValueError, match=TestConstants.ERROR_MESSAGES["firecrawl_empty"]
            ):
                processor.process_url(content.id, TestConstants.TEST_URL)

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    def test_process_url_firecrawl_no_markdown(
        self, mock_firecrawl_app, mock_current_app, session, app
    ):
        """Test URL processing fails when Firecrawl returns no markdown content."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)

        # Setup Firecrawl to return result without markdown
        mock_firecrawl_instance = Mock()
        mock_firecrawl_app.return_value = mock_firecrawl_instance
        mock_result = Mock()
        mock_result.markdown = None
        mock_firecrawl_instance.scrape_url.return_value = mock_result

        # Create test content
        content = ContentProcessorTestHelpers.create_test_content(session)

        with app.app_context():
            processor = ContentProcessor()

            with pytest.raises(
                ValueError, match=TestConstants.ERROR_MESSAGES["firecrawl_no_markdown"]
            ):
                processor.process_url(content.id, TestConstants.TEST_URL)

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    def test_process_url_firecrawl_exception(
        self, mock_firecrawl_app, mock_current_app, session, app
    ):
        """Test URL processing handles Firecrawl exceptions."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)

        # Setup Firecrawl to raise exception
        mock_firecrawl_instance = Mock()
        mock_firecrawl_app.return_value = mock_firecrawl_instance
        mock_firecrawl_instance.scrape_url.side_effect = Exception(
            "Firecrawl API error"
        )

        # Create test content
        content = ContentProcessorTestHelpers.create_test_content(session)

        with app.app_context():
            processor = ContentProcessor()

            with pytest.raises(Exception, match="Firecrawl API error"):
                processor.process_url(content.id, TestConstants.TEST_URL)

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    @patch("services.content_processor.genai")
    def test_process_url_preserves_existing_values(
        self, mock_genai, mock_firecrawl_app, mock_current_app, session, app
    ):
        """Test URL processing preserves existing values when extraction fails."""
        mock_firecrawl_instance, mock_model = self.setup_standard_mocks(
            mock_genai,
            mock_firecrawl_app,
            mock_current_app,
            gemini_response=TestConstants.GEMINI_MINIMAL_RESPONSE,
            og_image=False,
        )

        # Create test content with existing values
        content = ContentProcessorTestHelpers.create_test_content(
            session,
            title="Original Title",
            excerpt="Original excerpt",
            image_url="https://original.com/image.jpg",
        )

        with app.app_context():
            processor = ContentProcessor()
            result = processor.process_url(content.id, TestConstants.TEST_URL)

            # Should preserve original values when extraction returns None/"Not available"
            assert result.image_url == "https://original.com/image.jpg"

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    @patch("services.content_processor.genai")
    def test_process_url_database_rollback_on_error(
        self, mock_genai, mock_firecrawl_app, mock_current_app, session, app
    ):
        """Test database rollback when processing fails after content extraction."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)

        # Setup mocks to succeed initially but fail during database commit
        mock_firecrawl_instance = Mock()
        mock_firecrawl_app.return_value = mock_firecrawl_instance
        mock_firecrawl_instance.scrape_url.return_value = (
            ContentProcessorTestHelpers.create_mock_firecrawl_response()
        )

        _ = ContentProcessorTestHelpers.setup_gemini_mock(
            mock_genai, TestConstants.GEMINI_SUCCESS_RESPONSE
        )

        content = ContentProcessorTestHelpers.create_test_content(session)
        original_title = content.title
        content_id = content.id

        with app.app_context():
            with patch(
                "services.content_processor.db.session.commit",
                side_effect=SQLAlchemyError("Database error"),
            ):
                processor = ContentProcessor()

                with pytest.raises(SQLAlchemyError):
                    processor.process_url(content_id, TestConstants.TEST_URL)

                # The database transaction should have been rolled back
                # So a fresh query should show the original values
                # Note: We need to query in a new transaction to check the actual database state
                session.rollback()  # Ensure we're in a clean state
                fresh_content = session.query(Content).filter_by(id=content_id).first()
                assert (
                    fresh_content.title == original_title
                )  # Database should be unchanged

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    @patch("services.content_processor.genai")
    def test_process_url_null_gemini_fields(
        self, mock_genai, mock_firecrawl_app, mock_current_app, session, app
    ):
        """Test URL processing when Gemini returns null values for fields.

        This test verifies that the content processor properly handles null values from Gemini
        by preserving existing values instead of violating database constraints.
        """
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)

        mock_firecrawl_instance = Mock()
        mock_firecrawl_app.return_value = mock_firecrawl_instance
        mock_firecrawl_instance.scrape_url.return_value = (
            ContentProcessorTestHelpers.create_mock_firecrawl_response(
                metadata={}  # No og:image metadata
            )
        )

        _ = ContentProcessorTestHelpers.setup_gemini_mock(
            mock_genai, TestConstants.EDGE_CASE_RESPONSES["null_fields"]
        )

        # Create test content with existing values
        content = ContentProcessorTestHelpers.create_test_content(
            session,
            title="Original Title",
            excerpt="Original excerpt",
            image_url="https://existing.com/image.jpg",
        )

        with app.app_context():
            processor = ContentProcessor()
            result = processor.process_url(content.id, TestConstants.TEST_URL)

            # The content processor should now preserve existing values when Gemini returns null
            assert result is not None
            assert result.title == "Original Title"  # Preserved
            assert result.excerpt == "Original excerpt"  # Preserved
            assert result.image_url == "https://existing.com/image.jpg"  # Preserved
            # But scraped_content should still be updated since that comes from Firecrawl
            assert result.scraped_content == TestConstants.TEST_MARKDOWN_CONTENT

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    @patch("services.content_processor.genai")
    def test_get_safe_value_method(
        self, mock_genai, mock_firecrawl_app, mock_current_app, app
    ):
        """Test the _get_safe_value helper method directly to ensure robust null handling."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)

        with app.app_context():
            processor = ContentProcessor()

            # Test cases for _get_safe_value method
            test_cases = [
                # (content_info, key, current_value, fallback, expected_result)
                ({"Title": "New Title"}, "Title", "Old Title", "Default", "New Title"),
                ({"Title": None}, "Title", "Old Title", "Default", "Old Title"),
                ({"Title": ""}, "Title", "Old Title", "Default", "Old Title"),
                (
                    {"Title": "Not available"},
                    "Title",
                    "Old Title",
                    "Default",
                    "Old Title",
                ),
                ({}, "Title", "Old Title", "Default", "Old Title"),
                ({"Title": None}, "Title", None, "Default", "Default"),
                ({"Title": None}, "Title", "", "Default", "Default"),
                (
                    {"Description": "Valid description"},
                    "Description",
                    None,
                    "",
                    "Valid description",
                ),
            ]

            for content_info, key, current_value, fallback, expected in test_cases:
                result = processor._get_safe_value(
                    content_info, key, current_value, fallback
                )
                assert (
                    result == expected
                ), f"Failed for {content_info}, {key}, {current_value}, {fallback}: got {result}, expected {expected}"

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    @patch("services.content_processor.genai")
    def test_process_url_empty_content_with_fallbacks(
        self, mock_genai, mock_firecrawl_app, mock_current_app, session, app
    ):
        """Test URL processing when content has no existing values and Gemini returns empty/null values."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)

        mock_firecrawl_instance = Mock()
        mock_firecrawl_app.return_value = mock_firecrawl_instance
        mock_firecrawl_instance.scrape_url.return_value = (
            ContentProcessorTestHelpers.create_mock_firecrawl_response(metadata={})
        )

        _ = ContentProcessorTestHelpers.setup_gemini_mock(
            mock_genai, TestConstants.EDGE_CASE_RESPONSES["null_fields"]
        )

        # Create test content with NO existing values (empty/null)
        content = ContentProcessorTestHelpers.create_test_content(
            session,
            title="",  # Empty title
            excerpt="",  # Empty excerpt
            image_url="",  # Empty image URL
        )

        with app.app_context():
            processor = ContentProcessor()
            result = processor.process_url(content.id, TestConstants.TEST_URL)

            # Should use fallback values when both existing and Gemini values are empty/null
            assert result is not None
            assert (
                result.title == "Untitled"
            )  # Should use fallback from _get_safe_value
            assert result.excerpt == ""  # Empty fallback is OK for excerpt
            assert result.image_url == ""  # Should preserve existing empty value
            assert result.scraped_content == TestConstants.TEST_MARKDOWN_CONTENT


# --- Edge Cases and Error Handling ---
@pytest.mark.integration
class TestContentProcessorEdgeCases:
    """Test edge cases and error conditions for ContentProcessor."""

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    @patch("services.content_processor.genai")
    def test_process_url_image_url_as_list(
        self, mock_genai, mock_firecrawl_app, mock_current_app, session, app
    ):
        """Test URL processing when Gemini returns image URL as a list."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)

        # Setup mocks - NO og:image metadata so Gemini result is used
        mock_firecrawl_instance = Mock()
        mock_firecrawl_app.return_value = mock_firecrawl_instance
        mock_firecrawl_instance.scrape_url.return_value = (
            ContentProcessorTestHelpers.create_mock_firecrawl_response(
                metadata={}  # No og:image metadata
            )
        )

        # Create response with image URL as list
        gemini_response = TestConstants.GEMINI_SUCCESS_RESPONSE.copy()
        gemini_response["Image URL"] = [
            TestConstants.TEST_IMAGE_URL,
            "https://example.com/image2.jpg",
        ]
        _ = ContentProcessorTestHelpers.setup_gemini_mock(mock_genai, gemini_response)

        # Create test content
        content = ContentProcessorTestHelpers.create_test_content(session)

        with app.app_context():
            processor = ContentProcessor()
            result = processor.process_url(content.id, TestConstants.TEST_URL)

            # Should use first image from list
            assert result.image_url == TestConstants.TEST_IMAGE_URL

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    @patch("services.content_processor.genai")
    def test_process_url_empty_image_url_list(
        self, mock_genai, mock_firecrawl_app, mock_current_app, session, app
    ):
        """Test URL processing when Gemini returns empty image URL list."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)

        # Setup mocks - NO og:image metadata so Gemini result is used
        mock_firecrawl_instance = Mock()
        mock_firecrawl_app.return_value = mock_firecrawl_instance
        mock_firecrawl_instance.scrape_url.return_value = (
            ContentProcessorTestHelpers.create_mock_firecrawl_response(
                metadata={}  # No og:image metadata
            )
        )

        # Create response with empty image URL list
        gemini_response = TestConstants.GEMINI_SUCCESS_RESPONSE.copy()
        gemini_response["Image URL"] = []
        _ = ContentProcessorTestHelpers.setup_gemini_mock(mock_genai, gemini_response)

        # Create test content with existing image
        content = ContentProcessorTestHelpers.create_test_content(
            session, image_url="https://existing.com/image.jpg"
        )

        with app.app_context():
            processor = ContentProcessor()
            result = processor.process_url(content.id, TestConstants.TEST_URL)

            # Should preserve existing image URL
            assert result.image_url == "https://existing.com/image.jpg"

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    @patch("services.content_processor.genai")
    def test_process_url_very_large_content(
        self, mock_genai, mock_firecrawl_app, mock_current_app, session, app
    ):
        """Test URL processing with very large content."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)

        # Create very large markdown content
        large_content = "# Large Article\n" + "This is a very long paragraph. " * 1000

        mock_firecrawl_instance = Mock()
        mock_firecrawl_app.return_value = mock_firecrawl_instance
        mock_firecrawl_instance.scrape_url.return_value = (
            ContentProcessorTestHelpers.create_mock_firecrawl_response(
                markdown=large_content, metadata={}
            )
        )

        _ = ContentProcessorTestHelpers.setup_gemini_mock(
            mock_genai, TestConstants.GEMINI_SUCCESS_RESPONSE
        )

        content = ContentProcessorTestHelpers.create_test_content(session)

        with app.app_context():
            processor = ContentProcessor()
            result = processor.process_url(content.id, TestConstants.TEST_URL)

            # Should handle large content successfully
            assert result is not None
            assert result.scraped_content == large_content
            assert len(result.scraped_content) > 10000  # Verify it's actually large


# --- Performance and Load Tests ---
@pytest.mark.slow
@pytest.mark.integration
class TestContentProcessorPerformance:
    """Performance tests for ContentProcessor operations."""

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    @patch("services.content_processor.genai")
    def test_multiple_content_processing_efficiency(
        self, mock_genai, mock_firecrawl_app, mock_current_app, session, app
    ):
        """Test processing multiple content items efficiently."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)

        # Setup mocks
        mock_firecrawl_instance = Mock()
        mock_firecrawl_app.return_value = mock_firecrawl_instance
        mock_firecrawl_instance.scrape_url.return_value = (
            ContentProcessorTestHelpers.create_mock_firecrawl_response()
        )

        mock_model = ContentProcessorTestHelpers.setup_gemini_mock(
            mock_genai, TestConstants.GEMINI_SUCCESS_RESPONSE
        )

        # Create multiple test content items
        content_items = []
        for i in range(10):  # Increased from 5 to 10 for better performance testing
            content = ContentProcessorTestHelpers.create_test_content(
                session, url=f"https://example.com/article-{i}"
            )
            content_items.append(content)

        with app.app_context():
            processor = ContentProcessor()

            # Process all items and measure basic efficiency
            results = []
            for content in content_items:
                result = processor.process_url(content.id, content.url)
                results.append(result)

            # Verify all were processed successfully
            assert len(results) == 10
            assert all(result is not None for result in results)
            assert all(
                result.scraped_content == TestConstants.TEST_MARKDOWN_CONTENT
                for result in results
            )

            # Verify mocks were called correct number of times
            assert mock_firecrawl_instance.scrape_url.call_count == 10
            assert mock_model.generate_content.call_count == 10

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key"})
    @patch("services.content_processor.current_app")
    @patch("services.content_processor.FirecrawlApp")
    @patch("services.content_processor.genai")
    def test_concurrent_processing_safety(
        self, mock_genai, mock_firecrawl_app, mock_current_app, session, app
    ):
        """Test that processor handles concurrent-like operations safely."""
        ContentProcessorTestHelpers.setup_basic_mocks(mock_current_app)

        mock_firecrawl_instance = Mock()
        mock_firecrawl_app.return_value = mock_firecrawl_instance
        mock_firecrawl_instance.scrape_url.return_value = (
            ContentProcessorTestHelpers.create_mock_firecrawl_response()
        )

        _ = ContentProcessorTestHelpers.setup_gemini_mock(
            mock_genai, TestConstants.GEMINI_SUCCESS_RESPONSE
        )

        # Create multiple processors to simulate concurrent usage
        content1 = ContentProcessorTestHelpers.create_test_content(session)
        content2 = ContentProcessorTestHelpers.create_test_content(session)

        with app.app_context():
            processor1 = ContentProcessor()
            processor2 = ContentProcessor()

            # Process different content with different processors
            result1 = processor1.process_url(content1.id, TestConstants.TEST_URL)
            result2 = processor2.process_url(content2.id, TestConstants.TEST_URL)

            # Both should succeed independently
            assert result1 is not None
            assert result2 is not None
            assert result1.id != result2.id
