"""
Tests for the prompts helper module.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from helpers.prompts import (
    get_platform_config,
    format_time_context,
    get_content_type_info,
    render_system_prompt,
    render_user_prompt,
)


@pytest.mark.unit
class TestGetPlatformConfig:
    """Test get_platform_config function."""

    @patch("helpers.prompts.ContentGenerator")
    def test_get_platform_config_linkedin(self, mock_generator_class):
        """Test getting LinkedIn platform configuration."""
        mock_generator = Mock()
        mock_config = Mock()
        mock_config.max_length = 3000
        mock_config.max_tokens = 700
        mock_config.style = "Professional and informative"
        mock_config.name = "LinkedIn"
        mock_generator.get_platform_config.return_value = mock_config
        mock_generator_class.return_value = mock_generator

        config = get_platform_config("linkedin")

        assert config["name"] == "LinkedIn"
        assert config["max_length"] == 3000
        assert config["max_tokens"] == 700
        assert config["url_char_approx"] == 30
        assert config["style"] == "Professional and informative"

    @patch("helpers.prompts.ContentGenerator")
    def test_get_platform_config_twitter(self, mock_generator_class):
        """Test getting Twitter platform configuration."""
        mock_generator = Mock()
        mock_config = Mock()
        mock_config.max_length = 280
        mock_config.max_tokens = 100
        mock_config.style = "Concise and engaging"
        mock_config.name = "Twitter"
        mock_generator.get_platform_config.return_value = mock_config
        mock_generator_class.return_value = mock_generator

        config = get_platform_config("twitter")

        assert config["name"] == "Twitter"
        assert config["max_length"] == 280
        assert config["max_tokens"] == 100
        assert config["style"] == "Concise and engaging"

    @patch("helpers.prompts.ContentGenerator")
    def test_get_platform_config_facebook(self, mock_generator_class):
        """Test getting Facebook platform configuration."""
        mock_generator = Mock()
        mock_config = Mock()
        mock_config.max_length = 63206
        mock_config.max_tokens = 800
        mock_config.style = "Conversational and engaging"
        mock_config.name = "Facebook"
        mock_generator.get_platform_config.return_value = mock_config
        mock_generator_class.return_value = mock_generator

        config = get_platform_config("facebook")

        assert config["name"] == "Facebook"
        assert config["max_length"] == 63206
        assert config["max_tokens"] == 800
        assert config["style"] == "Conversational and engaging"

    @patch("helpers.prompts.ContentGenerator")
    def test_get_platform_config_generic_defaults_to_linkedin(
        self, mock_generator_class
    ):
        """Test that generic platform defaults to LinkedIn config."""
        mock_generator = Mock()
        mock_config = Mock()
        mock_config.max_length = 3000
        mock_config.max_tokens = 700
        mock_config.style = "Professional"
        mock_generator.get_platform_config.return_value = mock_config
        mock_generator_class.return_value = mock_generator

        config = get_platform_config("generic")

        assert config["max_length"] == 3000  # LinkedIn defaults

    @patch("helpers.prompts.ContentGenerator")
    def test_get_platform_config_fallback_when_generator_fails(
        self, mock_generator_class
    ):
        """Test fallback configuration when ContentGenerator can't be created."""
        mock_generator_class.side_effect = Exception("No API key")

        config = get_platform_config("linkedin")

        # Should use fallback configuration
        assert config["name"] == "LinkedIn"  # Fallback uses proper capitalization
        assert config["max_length"] == 3000
        assert config["max_tokens"] == 700
        assert config["style"] == "Professional"
        assert config["url_char_approx"] == 30


@pytest.mark.unit
class TestFormatTimeContext:
    """Test format_time_context function."""

    def test_format_time_context_none(self):
        """Test time context with None publish date."""
        result = format_time_context(None)
        assert result == "recently"

    def test_format_time_context_future(self):
        """Test time context with future date."""
        future_date = datetime.utcnow() + timedelta(days=1)
        result = format_time_context(future_date)
        assert result == "upcoming"

    def test_format_time_context_today(self):
        """Test time context with today's date."""
        today = datetime.utcnow()
        result = format_time_context(today)
        assert result == "today"

    def test_format_time_context_yesterday(self):
        """Test time context with yesterday's date."""
        yesterday = datetime.utcnow() - timedelta(days=1)
        result = format_time_context(yesterday)
        assert result == "yesterday"

    def test_format_time_context_days_ago(self):
        """Test time context with recent days."""
        three_days_ago = datetime.utcnow() - timedelta(days=3)
        result = format_time_context(three_days_ago)
        assert result == "3 days ago"

    def test_format_time_context_weeks_ago(self):
        """Test time context with weeks ago."""
        two_weeks_ago = datetime.utcnow() - timedelta(days=14)
        result = format_time_context(two_weeks_ago)
        assert result == "2 weeks ago"

        one_week_ago = datetime.utcnow() - timedelta(days=7)
        result = format_time_context(one_week_ago)
        assert result == "1 week ago"

    def test_format_time_context_months_ago(self):
        """Test time context with months ago."""
        two_months_ago = datetime.utcnow() - timedelta(days=60)
        result = format_time_context(two_months_ago)
        assert result == "2 months ago"

        one_month_ago = datetime.utcnow() - timedelta(days=30)
        result = format_time_context(one_month_ago)
        assert result == "1 month ago"

    def test_format_time_context_years_ago(self):
        """Test time context with years ago."""
        two_years_ago = datetime.utcnow() - timedelta(days=730)
        result = format_time_context(two_years_ago)
        assert result == "2 years ago"

        one_year_ago = datetime.utcnow() - timedelta(days=365)
        result = format_time_context(one_year_ago)
        assert result == "1 year ago"


@pytest.mark.unit
class TestGetContentTypeInfo:
    """Test get_content_type_info function."""

    def test_get_content_type_info(self):
        """Test getting content type information."""
        content_item = Mock()
        content_item.url = "https://example.com/article"
        content_item.title = "Test Article Title"

        content_type_string, content_type_name, url_field, content_description = (
            get_content_type_info(content_item)
        )

        assert content_type_string == "content"
        assert content_type_name == "Content Item"
        assert url_field == "https://example.com/article"
        assert content_description == "Test Article Title"


@pytest.mark.unit
class TestRenderSystemPrompt:
    """Test render_system_prompt function."""

    @patch("helpers.prompts.render_template")
    @patch("helpers.prompts.get_platform_config")
    def test_render_system_prompt(self, mock_get_config, mock_render_template):
        """Test rendering system prompt."""
        mock_config = {
            "name": "LinkedIn",
            "max_length": 3000,
            "max_tokens": 700,
            "style": "Professional",
        }
        mock_get_config.return_value = mock_config
        mock_render_template.return_value = "Rendered system prompt"

        result = render_system_prompt("linkedin", retry_attempt=1, last_length=100)

        assert result == "Rendered system prompt"
        mock_get_config.assert_called_once_with("linkedin")
        mock_render_template.assert_called_once_with(
            "prompts/base_system.html",
            platform="linkedin",
            platform_config=mock_config,
            retry_attempt=1,
            last_length=100,
        )


@pytest.mark.integration
class TestRenderUserPrompt:
    """Test render_user_prompt function."""

    @patch("helpers.prompts.render_template")
    @patch("helpers.prompts.get_platform_config")
    def test_render_user_prompt(self, mock_get_config, mock_render_template):
        """Test rendering user prompt."""
        # Setup mocks
        mock_config = {"name": "LinkedIn", "max_length": 3000, "style": "Professional"}
        mock_get_config.return_value = mock_config
        mock_render_template.return_value = "Rendered user prompt"

        # Create mock content item
        content_item = Mock()
        content_item.title = "Test Article"
        content_item.excerpt = "Test excerpt"
        content_item.publish_date = datetime.utcnow() - timedelta(days=1)
        content_item.scraped_content = "Test scraped content"
        content_item.get_url_with_all_utms.return_value = (
            "https://example.com/article?utm_source=test"
        )

        # Create mock user
        user = Mock()
        user.name = "Test User"
        user.bio = "Test bio"
        user.example_social_posts = "Example posts"

        result = render_user_prompt(content_item, user, "linkedin")

        assert result == "Rendered user prompt"
        mock_get_config.assert_called_once_with("linkedin")

        # Verify render_template was called with expected arguments
        call_args = mock_render_template.call_args
        assert call_args[0][0] == "prompts/base_user.html"

        # Check some key arguments
        kwargs = call_args[1]
        assert kwargs["content_description"] == "Test Article"
        assert kwargs["user_name"] == "Test User"
        assert kwargs["user_bio"] == "Test bio"
        assert kwargs["platform"] == "linkedin"

    @patch("helpers.prompts.render_template")
    @patch("helpers.prompts.get_platform_config")
    def test_render_user_prompt_with_defaults(
        self, mock_get_config, mock_render_template
    ):
        """Test rendering user prompt with default values."""
        mock_config = {"name": "LinkedIn"}
        mock_get_config.return_value = mock_config
        mock_render_template.return_value = "Rendered prompt"

        # Content with minimal data
        content_item = Mock()
        content_item.title = "Test"
        content_item.excerpt = None
        content_item.publish_date = None
        content_item.scraped_content = None
        content_item.get_url_with_all_utms.return_value = "https://example.com"

        # User with minimal data - use spec=[] to prevent auto-creation of attributes
        user = Mock(spec=[])

        render_user_prompt(content_item, user)

        # Should handle defaults gracefully
        call_args = mock_render_template.call_args[1]
        assert call_args["user_name"] == "AI Promoter User"  # Default name
        assert call_args["user_bio"] == "Security professional"  # Default bio
        assert call_args["description"] == ""  # Empty excerpt
        assert call_args["time_context"] == "recently"  # Default time context

    @pytest.mark.slow
    @patch("helpers.prompts.render_template")
    @patch("helpers.prompts.get_platform_config")
    def test_render_user_prompt_long_content_truncation(
        self, mock_get_config, mock_render_template
    ):
        """Test that long content gets truncated appropriately."""
        mock_config = {"name": "LinkedIn"}
        mock_get_config.return_value = mock_config
        mock_render_template.return_value = "Rendered prompt"

        content_item = Mock()
        content_item.title = "Test"
        content_item.excerpt = "x" * 500  # Long excerpt
        content_item.scraped_content = "y" * 3000  # Very long scraped content
        content_item.publish_date = None
        content_item.get_url_with_all_utms.return_value = "https://example.com"

        user = Mock()
        user.name = "Test User"
        user.bio = "Test bio"
        user.example_social_posts = ""

        render_user_prompt(content_item, user)

        call_args = mock_render_template.call_args[1]

        # Excerpt should be truncated to 400 chars
        assert len(call_args["description"]) <= 400
        assert call_args["description"].endswith("...")

        # Scraped content should be truncated to 2000 chars
        assert len(call_args["scraped_content"]) <= 2000
        assert call_args["scraped_content"].endswith("...")
