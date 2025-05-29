"""
Tests for the simplified content generator architecture.

This test suite covers the unified ContentGenerator class and related functionality,
consolidating tests from the previous architecture while adding new test coverage.
"""

import pytest
from unittest.mock import Mock, patch
from helpers.content_generator import (
    ContentGenerator,
    Platform,
    PlatformConfig,
    GenerationResult,
    ContentGenerationError,
    validate_post_length,
)


class TestConstants:
    """Test constants and expected values."""

    VALID_API_KEY = "test-api-key"
    CUSTOM_API_KEY = "custom-api-key"
    GEMINI_MODEL_DEFAULT = "gemini-1.5-pro"
    GEMINI_MODEL_FLASH = "gemini-1.5-flash"

    # Platform limits
    LINKEDIN_MAX_LENGTH = 3000
    TWITTER_MAX_LENGTH = 280
    FACEBOOK_MAX_LENGTH = 63206

    # Test content
    SHORT_CONTENT = "Short content"
    LONG_LINKEDIN_CONTENT = "x" * 3000  # At LinkedIn limit
    LONG_TWITTER_CONTENT = "x" * 260  # Over Twitter limit
    GENERATED_CONTENT = "Generated LinkedIn content"

    # Error messages
    API_KEY_ERROR = "GEMINI_API_KEY environment variable not set"
    UNSUPPORTED_PROVIDER_ERROR = "Unsupported AI provider: openai"
    API_FAILURE_ERROR = "Gemini API call failed"
    EMPTY_RESPONSE_ERROR = "Gemini returned empty response"


class ContentGeneratorTestHelpers:
    """Helper methods for content generator testing."""

    @staticmethod
    def create_mock_content_item(**kwargs):
        """Create a mock content item with default values."""
        mock_content = Mock()
        mock_content.title = kwargs.get("title", "Test Article")
        mock_content.excerpt = kwargs.get("excerpt", "Test excerpt")
        mock_content.url = kwargs.get("url", "https://example.com/article")
        return mock_content

    @staticmethod
    def create_mock_user(**kwargs):
        """Create a mock user with default values."""
        mock_user = Mock()
        mock_user.name = kwargs.get("name", "Test User")
        mock_user.bio = kwargs.get("bio", "Test bio")
        mock_user.example_social_posts = kwargs.get("example_posts", "Example posts")
        return mock_user

    @staticmethod
    def create_mock_gemini_response(content=TestConstants.GENERATED_CONTENT):
        """Create a mock Gemini API response."""
        mock_response = Mock()
        mock_response.text = content
        return mock_response

    @staticmethod
    def assert_generation_result_success(
        result, expected_content=TestConstants.GENERATED_CONTENT
    ):
        """Assert that a generation result indicates success."""
        assert result.success is True
        assert result.content == expected_content
        assert result.error_message is None
        assert result.attempts >= 1
        assert result.length == len(expected_content)

    @staticmethod
    def assert_generation_result_failure(result, expected_error_substring=None):
        """Assert that a generation result indicates failure."""
        assert result.success is False
        assert result.content is None
        if expected_error_substring:
            assert expected_error_substring in result.error_message


@pytest.mark.unit
class TestPlatform:
    """Test Platform enum."""

    def test_platform_values(self):
        """Test that Platform enum has expected values."""
        assert Platform.LINKEDIN.value == "linkedin"
        assert Platform.TWITTER.value == "twitter"
        assert Platform.FACEBOOK.value == "facebook"
        assert Platform.INSTAGRAM.value == "instagram"
        assert Platform.TIKTOK.value == "tiktok"

    def test_platform_enum_creation(self):
        """Test creating Platform enum from string values."""
        assert Platform("linkedin") == Platform.LINKEDIN
        assert Platform("twitter") == Platform.TWITTER
        assert Platform("facebook") == Platform.FACEBOOK


@pytest.mark.unit
class TestPlatformConfig:
    """Test PlatformConfig dataclass."""

    def test_platform_config_creation(self):
        """Test creating a PlatformConfig."""
        config = PlatformConfig(max_length=3000, max_tokens=700, style="Professional")
        assert config.max_length == 3000
        assert config.max_tokens == 700
        assert config.style == "Professional"
        assert config.hashtag_style == ""  # Default value

    def test_platform_config_with_hashtag_style(self):
        """Test PlatformConfig with hashtag style."""
        config = PlatformConfig(
            max_length=280, max_tokens=100, style="Concise", hashtag_style="trending"
        )
        assert config.hashtag_style == "trending"


@pytest.mark.unit
class TestGenerationResult:
    """Test GenerationResult dataclass."""

    def test_generation_result_success(self):
        """Test successful GenerationResult."""
        result = GenerationResult(
            content=TestConstants.GENERATED_CONTENT,
            success=True,
            attempts=1,
            length=len(TestConstants.GENERATED_CONTENT),
        )
        ContentGeneratorTestHelpers.assert_generation_result_success(result)

    def test_generation_result_failure(self):
        """Test failed GenerationResult."""
        result = GenerationResult(
            content=None, success=False, error_message="API error", attempts=3
        )
        ContentGeneratorTestHelpers.assert_generation_result_failure(
            result, "API error"
        )
        assert result.attempts == 3
        assert result.length == 0  # Default value


@pytest.mark.unit
class TestContentGeneratorInitialization:
    """Test ContentGenerator initialization."""

    def test_init_without_api_key(self):
        """Test that ContentGenerator raises error without API key."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(
                ContentGenerationError, match=TestConstants.API_KEY_ERROR
            ):
                ContentGenerator()

    def test_init_with_api_key(self):
        """Test ContentGenerator initialization with API key."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": TestConstants.VALID_API_KEY}):
            with patch("google.generativeai.configure") as mock_configure:
                generator = ContentGenerator()
                assert generator.ai_provider == "gemini"
                assert generator.model == TestConstants.GEMINI_MODEL_DEFAULT
                assert generator.api_key == TestConstants.VALID_API_KEY
                mock_configure.assert_called_once_with(
                    api_key=TestConstants.VALID_API_KEY
                )

    def test_init_with_custom_parameters(self):
        """Test ContentGenerator with custom parameters."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": TestConstants.VALID_API_KEY}):
            with patch("google.generativeai.configure"):
                generator = ContentGenerator(
                    ai_provider="gemini",
                    model=TestConstants.GEMINI_MODEL_FLASH,
                    api_key=TestConstants.CUSTOM_API_KEY,
                )
                assert generator.ai_provider == "gemini"
                assert generator.model == TestConstants.GEMINI_MODEL_FLASH
                assert generator.api_key == TestConstants.CUSTOM_API_KEY

    def test_init_unsupported_provider(self):
        """Test initialization with unsupported AI provider."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": TestConstants.VALID_API_KEY}):
            with pytest.raises(
                ContentGenerationError, match=TestConstants.UNSUPPORTED_PROVIDER_ERROR
            ):
                ContentGenerator(ai_provider="openai")


@pytest.mark.unit
class TestContentGeneratorConfiguration:
    """Test ContentGenerator configuration methods."""

    def test_get_platform_config(self):
        """Test getting platform configuration."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": TestConstants.VALID_API_KEY}):
            with patch("google.generativeai.configure"):
                generator = ContentGenerator()

                linkedin_config = generator.get_platform_config(Platform.LINKEDIN)
                assert linkedin_config.max_length == TestConstants.LINKEDIN_MAX_LENGTH
                assert linkedin_config.max_tokens == 700
                assert "Professional" in linkedin_config.style

                twitter_config = generator.get_platform_config(Platform.TWITTER)
                assert twitter_config.max_length == TestConstants.TWITTER_MAX_LENGTH
                assert twitter_config.max_tokens == 100
                assert "Concise" in twitter_config.style

                facebook_config = generator.get_platform_config(Platform.FACEBOOK)
                assert facebook_config.max_length == TestConstants.FACEBOOK_MAX_LENGTH
                assert facebook_config.max_tokens == 800
                assert "Conversational" in facebook_config.style

    def test_get_supported_platforms(self):
        """Test getting supported platforms."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": TestConstants.VALID_API_KEY}):
            with patch("google.generativeai.configure"):
                generator = ContentGenerator()
                platforms = generator.get_supported_platforms()

                assert Platform.LINKEDIN in platforms
                assert Platform.TWITTER in platforms
                assert Platform.FACEBOOK in platforms
                assert len(platforms) == 3  # Only the configured platforms


@pytest.mark.unit
class TestContentGeneratorValidation:
    """Test ContentGenerator validation methods."""

    def test_validate_content_valid(self):
        """Test content validation with valid content."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": TestConstants.VALID_API_KEY}):
            with patch("google.generativeai.configure"):
                generator = ContentGenerator()

                config = generator.get_platform_config(Platform.LINKEDIN)
                assert (
                    generator._validate_content(TestConstants.SHORT_CONTENT, config)
                    is True
                )

    def test_validate_content_invalid(self):
        """Test content validation with invalid content."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": TestConstants.VALID_API_KEY}):
            with patch("google.generativeai.configure"):
                generator = ContentGenerator()

                # Test content too long for LinkedIn
                # (3000 char limit + 30 URL = 3030 max)
                config = generator.get_platform_config(Platform.LINKEDIN)
                assert (
                    generator._validate_content(
                        TestConstants.LONG_LINKEDIN_CONTENT, config
                    )
                    is False
                )

    def test_validate_content_twitter_limits(self):
        """Test content validation for Twitter's strict limits."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": TestConstants.VALID_API_KEY}):
            with patch("google.generativeai.configure"):
                generator = ContentGenerator()

                # Twitter has 280 char limit, so 250 chars + 30 URL = 280 (valid)
                valid_content = "x" * 250
                config = generator.get_platform_config(Platform.TWITTER)
                assert generator._validate_content(valid_content, config) is True

                # 260 chars + 30 URL = 290 (invalid)
                assert (
                    generator._validate_content(
                        TestConstants.LONG_TWITTER_CONTENT, config
                    )
                    is False
                )


@pytest.mark.integration
class TestContentGeneratorGeneration:
    """Integration tests for ContentGenerator content generation methods."""

    @patch.dict("os.environ", {"GEMINI_API_KEY": TestConstants.VALID_API_KEY})
    @patch("google.generativeai.configure")
    @patch("google.generativeai.GenerativeModel")
    def test_generate_content_success(self, mock_model_class, mock_configure):
        """Test successful content generation."""
        # Setup mocks
        mock_response = ContentGeneratorTestHelpers.create_mock_gemini_response()
        mock_model = Mock()
        mock_model.generate_content.return_value = mock_response
        mock_model_class.return_value = mock_model

        # Mock prompt rendering
        with patch("helpers.prompts.render_system_prompt") as mock_system:
            with patch("helpers.prompts.render_user_prompt") as mock_user:
                mock_system.return_value = "System prompt"
                mock_user.return_value = "User prompt"

                generator = ContentGenerator()
                content_item = ContentGeneratorTestHelpers.create_mock_content_item()
                user = ContentGeneratorTestHelpers.create_mock_user()

                result = generator.generate_content(
                    content_item, user, Platform.LINKEDIN, max_retries=1
                )

                ContentGeneratorTestHelpers.assert_generation_result_success(result)

    @patch.dict("os.environ", {"GEMINI_API_KEY": TestConstants.VALID_API_KEY})
    @patch("google.generativeai.configure")
    def test_generate_content_unsupported_platform(self, mock_configure):
        """Test generation with unsupported platform."""
        generator = ContentGenerator()

        # Create a mock platform that's not in PLATFORM_CONFIGS
        unsupported_platform = Mock()
        unsupported_platform.value = "unsupported"

        content_item = ContentGeneratorTestHelpers.create_mock_content_item()
        user = ContentGeneratorTestHelpers.create_mock_user()

        result = generator.generate_content(content_item, user, unsupported_platform)

        ContentGeneratorTestHelpers.assert_generation_result_failure(
            result, "Unsupported platform"
        )
        assert result.attempts == 0

    @patch.dict("os.environ", {"GEMINI_API_KEY": TestConstants.VALID_API_KEY})
    @patch("google.generativeai.configure")
    @patch("google.generativeai.GenerativeModel")
    def test_generate_content_api_failure(self, mock_model_class, mock_configure):
        """Test content generation with API failure."""
        # Setup mocks to fail
        mock_model = Mock()
        mock_model.generate_content.side_effect = Exception("API Error")
        mock_model_class.return_value = mock_model

        with patch("helpers.prompts.render_system_prompt") as mock_system:
            with patch("helpers.prompts.render_user_prompt") as mock_user:
                mock_system.return_value = "System prompt"
                mock_user.return_value = "User prompt"

                generator = ContentGenerator()
                content_item = ContentGeneratorTestHelpers.create_mock_content_item()
                user = ContentGeneratorTestHelpers.create_mock_user()

                result = generator.generate_content(
                    content_item, user, Platform.LINKEDIN, max_retries=1
                )

                ContentGeneratorTestHelpers.assert_generation_result_failure(
                    result, TestConstants.API_FAILURE_ERROR
                )
                assert result.attempts == 1

    @pytest.mark.slow
    @patch.dict("os.environ", {"GEMINI_API_KEY": TestConstants.VALID_API_KEY})
    @patch("google.generativeai.configure")
    @patch("google.generativeai.GenerativeModel")
    def test_generate_content_retry_logic(self, mock_model_class, mock_configure):
        """Test content generation retry logic."""
        # Setup mocks - first call fails, second succeeds
        mock_response_bad = Mock()
        mock_response_bad.text = "x" * 4000  # Too long content

        mock_response_good = ContentGeneratorTestHelpers.create_mock_gemini_response(
            "Good content"
        )

        mock_model = Mock()
        mock_model.generate_content.side_effect = [
            mock_response_bad,
            mock_response_good,
        ]
        mock_model_class.return_value = mock_model

        with patch("helpers.prompts.render_system_prompt") as mock_system:
            with patch("helpers.prompts.render_user_prompt") as mock_user:
                mock_system.return_value = "System prompt"
                mock_user.return_value = "User prompt"

                generator = ContentGenerator()
                content_item = ContentGeneratorTestHelpers.create_mock_content_item()
                user = ContentGeneratorTestHelpers.create_mock_user()

                result = generator.generate_content(
                    content_item, user, Platform.LINKEDIN, max_retries=3
                )

                ContentGeneratorTestHelpers.assert_generation_result_success(
                    result, "Good content"
                )
                assert result.attempts == 2  # First failed, second succeeded


@pytest.mark.unit
class TestValidatePostLength:
    """Test the legacy compatibility function."""

    def test_validate_post_length_valid(self):
        """Test validation of valid post length."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": TestConstants.VALID_API_KEY}):
            with patch("google.generativeai.configure"):
                is_valid, length = validate_post_length(
                    TestConstants.SHORT_CONTENT, "linkedin"
                )
                assert is_valid is True
                assert length == 43  # 13 chars + 30 URL approximation

    def test_validate_post_length_invalid(self):
        """Test validation of invalid post length."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": TestConstants.VALID_API_KEY}):
            with patch("google.generativeai.configure"):
                is_valid, length = validate_post_length(
                    TestConstants.LONG_LINKEDIN_CONTENT, "linkedin"
                )
                assert is_valid is False
                assert length == 3030  # 3000 chars + 30 URL approximation

    def test_validate_post_length_with_url(self):
        """Test validation with explicit URL."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": TestConstants.VALID_API_KEY}):
            with patch("google.generativeai.configure"):
                is_valid, length = validate_post_length(
                    TestConstants.SHORT_CONTENT, "linkedin", "http://example.com"
                )
                assert is_valid is True
                assert length == 43  # 13 chars + 30 URL approximation
                # (URL param ignored in new implementation)

    def test_validate_post_length_unknown_platform(self):
        """Test validation with unknown platform defaults to LinkedIn."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": TestConstants.VALID_API_KEY}):
            with patch("google.generativeai.configure"):
                is_valid, length = validate_post_length(
                    TestConstants.SHORT_CONTENT, "unknown"
                )
                assert is_valid is True
                assert length == 43  # Should default to LinkedIn config

    def test_validate_post_length_twitter(self):
        """Test validation for Twitter's character limits."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": TestConstants.VALID_API_KEY}):
            with patch("google.generativeai.configure"):
                # Valid Twitter post (250 chars + 30 URL = 280, which is the limit)
                valid_content = "x" * 250
                is_valid, length = validate_post_length(valid_content, "twitter")
                assert is_valid is True
                assert length == 280

                # Invalid Twitter post (260 chars + 30 URL = 290, exceeds 280 limit)
                is_valid, length = validate_post_length(
                    TestConstants.LONG_TWITTER_CONTENT, "twitter"
                )
                assert is_valid is False
                assert length == 290


@pytest.mark.unit
class TestBackwardCompatibility:
    """Test backward compatibility with the old architecture."""

    def test_import_compatibility(self):
        """Test that old imports still work."""
        from helpers import SocialPostGenerator, validate_post_length, Platform

        # SocialPostGenerator should be an alias for ContentGenerator
        assert SocialPostGenerator == ContentGenerator

        # validate_post_length should be the function we defined
        assert callable(validate_post_length)

        # Platform should be the enum
        assert Platform.LINKEDIN.value == "linkedin"

    @patch.dict("os.environ", {"GEMINI_API_KEY": TestConstants.VALID_API_KEY})
    @patch("google.generativeai.configure")
    def test_social_post_generator_alias(self, mock_configure):
        """Test that SocialPostGenerator alias works correctly."""
        from helpers import SocialPostGenerator

        # Should be able to create instance using the alias
        generator = SocialPostGenerator()
        assert isinstance(generator, ContentGenerator)
        assert generator.ai_provider == "gemini"


@pytest.mark.unit
class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_content_generation_error_inheritance(self):
        """Test that ContentGenerationError can be raised and caught."""
        with pytest.raises(ContentGenerationError):
            raise ContentGenerationError("Test error")

    @patch.dict("os.environ", {"GEMINI_API_KEY": TestConstants.VALID_API_KEY})
    @patch("google.generativeai.configure")
    def test_empty_response_handling(self, mock_configure):
        """Test handling of empty API responses."""
        with patch("google.generativeai.GenerativeModel") as mock_model_class:
            mock_response = Mock()
            mock_response.text = None  # Empty response

            mock_model = Mock()
            mock_model.generate_content.return_value = mock_response
            mock_model_class.return_value = mock_model

            with patch("helpers.prompts.render_system_prompt") as mock_system:
                with patch("helpers.prompts.render_user_prompt") as mock_user:
                    mock_system.return_value = "System prompt"
                    mock_user.return_value = "User prompt"

                    generator = ContentGenerator()
                    content_item = (
                        ContentGeneratorTestHelpers.create_mock_content_item()
                    )
                    user = ContentGeneratorTestHelpers.create_mock_user()

                    result = generator.generate_content(
                        content_item, user, Platform.LINKEDIN, max_retries=1
                    )

                    ContentGeneratorTestHelpers.assert_generation_result_failure(
                        result, TestConstants.EMPTY_RESPONSE_ERROR
                    )
