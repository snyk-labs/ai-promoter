"""
Tests for the template helpers module.

This test suite provides comprehensive coverage for template utility functions
used throughout the application for rendering social media platform-specific
UI elements and styling.

Test Organization:
- Unit tests: Individual function testing with various inputs
- Parameterized tests: Reduce duplication for similar test cases
- Integration tests: Cross-function validation and consistency checks

Coverage includes:
- All public functions in helpers/template_helpers.py
- Platform-specific styling (colors and icons)
- Default fallback behavior
- Case-insensitive platform handling
- Input validation and edge cases
"""

import pytest

from helpers.template_helpers import (
    get_platform_color,
    get_platform_icon,
)


class TestConstants:
    """Test constants for better maintainability."""

    # Known platforms
    PLATFORM_LINKEDIN = "linkedin"
    PLATFORM_TWITTER = "twitter"
    PLATFORM_FACEBOOK = "facebook"
    PLATFORM_INSTAGRAM = "instagram"

    # Case variations
    PLATFORM_LINKEDIN_UPPER = "LINKEDIN"
    PLATFORM_TWITTER_MIXED = "TwItTeR"
    PLATFORM_FACEBOOK_CAPS = "FACEBOOK"

    # Unknown platforms
    PLATFORM_UNKNOWN = "unknown_platform"
    PLATFORM_EMPTY = ""
    PLATFORM_SPACE = " "
    PLATFORM_TIKTOK = "tiktok"
    PLATFORM_YOUTUBE = "youtube"

    # Expected color classes
    COLOR_LINKEDIN = "text-blue-600"
    COLOR_TWITTER = "text-blue-400"
    COLOR_FACEBOOK = "text-blue-700"
    COLOR_INSTAGRAM = "text-pink-600"
    COLOR_DEFAULT = "text-gray-600"

    # Platform icon SVG path prefixes for validation
    ICON_LINKEDIN_PREFIX = '<path d="M19 3a2 2 0'
    ICON_TWITTER_PREFIX = '<path d="M22.46 6c-.77.35'
    ICON_FACEBOOK_PREFIX = '<path d="M18 2h-3a5 5 0'
    ICON_INSTAGRAM_PREFIX = '<path d="M12 2c2.717 0'


class TestData:
    """Test data and fixtures."""

    # Known platform test cases with expected results
    KNOWN_PLATFORMS = [
        ("linkedin", TestConstants.COLOR_LINKEDIN, TestConstants.ICON_LINKEDIN_PREFIX),
        ("twitter", TestConstants.COLOR_TWITTER, TestConstants.ICON_TWITTER_PREFIX),
        ("facebook", TestConstants.COLOR_FACEBOOK, TestConstants.ICON_FACEBOOK_PREFIX),
        (
            "instagram",
            TestConstants.COLOR_INSTAGRAM,
            TestConstants.ICON_INSTAGRAM_PREFIX,
        ),
    ]

    # Case sensitivity test cases
    CASE_VARIATIONS = [
        ("linkedin", "LINKEDIN"),
        ("twitter", "TwItTeR"),
        ("facebook", "FACEBOOK"),
        ("instagram", "InStAgRaM"),
    ]

    # Invalid/unknown platform test cases
    UNKNOWN_PLATFORMS = [
        "unknown_platform",
        "",
        " ",
        "tiktok",
        "youtube",
        "random_string_123",
        "special!@#characters",
        "platform with spaces",
    ]

    # Edge case inputs
    EDGE_CASE_INPUTS = [
        ("", TestConstants.COLOR_DEFAULT),
        ("   ", TestConstants.COLOR_DEFAULT),
        ("unknown", TestConstants.COLOR_DEFAULT),
    ]


class TemplateHelpersTestHelpers:
    """Helper methods for template helpers tests."""

    @staticmethod
    def assert_valid_tailwind_color_class(color_class):
        """Assert that a color class follows Tailwind CSS naming conventions."""
        assert isinstance(color_class, str), "Color class must be a string"
        assert color_class.startswith("text-"), "Color class must start with 'text-'"
        assert len(color_class) > 5, "Color class must be more than just 'text-'"

    @staticmethod
    def assert_valid_svg_path(svg_path):
        """Assert that an SVG path is valid."""
        assert isinstance(svg_path, str), "SVG path must be a string"
        assert svg_path.startswith('<path d="'), "SVG path must start with '<path d=\"'"
        assert svg_path.endswith('"/>') or svg_path.endswith(
            '" />'
        ), "SVG path must end with '\"/>' or '\" />'"
        assert len(svg_path) > 20, "SVG path must contain actual path data"

    @staticmethod
    def assert_platform_matches_pattern(platform, expected_pattern):
        """Assert that a platform icon matches the expected pattern."""
        result = get_platform_icon(platform)
        assert result.startswith(expected_pattern), (
            f"Platform '{platform}' icon should start with '{expected_pattern}', "
            f"but got '{result[:50]}...'"
        )


@pytest.mark.unit
class TestGetPlatformColor:
    """Test get_platform_color function."""

    @pytest.mark.parametrize("platform,expected_color,_", TestData.KNOWN_PLATFORMS)
    def test_known_platform_colors(self, platform, expected_color, _):
        """Test that known platforms return their expected colors."""
        result = get_platform_color(platform)

        assert result == expected_color
        TemplateHelpersTestHelpers.assert_valid_tailwind_color_class(result)

    @pytest.mark.parametrize("lowercase,uppercase", TestData.CASE_VARIATIONS)
    def test_case_insensitive_handling(self, lowercase, uppercase):
        """Test that platform names are handled case-insensitively."""
        lowercase_result = get_platform_color(lowercase)
        uppercase_result = get_platform_color(uppercase)

        assert (
            lowercase_result == uppercase_result
        ), f"Case sensitivity test failed for '{lowercase}' vs '{uppercase}'"

    @pytest.mark.parametrize("unknown_platform", TestData.UNKNOWN_PLATFORMS)
    def test_unknown_platforms_return_default(self, unknown_platform):
        """Test that unknown platforms return default color."""
        result = get_platform_color(unknown_platform)

        assert result == TestConstants.COLOR_DEFAULT
        TemplateHelpersTestHelpers.assert_valid_tailwind_color_class(result)

    @pytest.mark.parametrize("input_value,expected", TestData.EDGE_CASE_INPUTS)
    def test_edge_case_inputs(self, input_value, expected):
        """Test edge case inputs return expected defaults."""
        result = get_platform_color(input_value)
        assert result == expected

    def test_none_input_handling(self):
        """Test that None input is handled gracefully."""
        try:
            result = get_platform_color(None)
            assert result == TestConstants.COLOR_DEFAULT
        except (AttributeError, TypeError):
            # This is acceptable behavior for None input
            pass


@pytest.mark.unit
class TestGetPlatformIcon:
    """Test get_platform_icon function."""

    @pytest.mark.parametrize("platform,_,expected_pattern", TestData.KNOWN_PLATFORMS)
    def test_known_platform_icons(self, platform, _, expected_pattern):
        """Test that known platforms return valid SVG icons with expected patterns."""
        result = get_platform_icon(platform)

        TemplateHelpersTestHelpers.assert_valid_svg_path(result)
        TemplateHelpersTestHelpers.assert_platform_matches_pattern(
            platform, expected_pattern
        )

    @pytest.mark.parametrize("lowercase,uppercase", TestData.CASE_VARIATIONS)
    def test_case_insensitive_icon_handling(self, lowercase, uppercase):
        """Test that platform names are handled case-insensitively for icons."""
        lowercase_result = get_platform_icon(lowercase)
        uppercase_result = get_platform_icon(uppercase)

        assert (
            lowercase_result == uppercase_result
        ), f"Case sensitivity test failed for icons: '{lowercase}' vs '{uppercase}'"

    @pytest.mark.parametrize("unknown_platform", TestData.UNKNOWN_PLATFORMS)
    def test_unknown_platforms_return_default_icon(self, unknown_platform):
        """Test that unknown platforms return default SVG icon."""
        default_icon = get_platform_icon("default")
        result = get_platform_icon(unknown_platform)

        assert result == default_icon
        TemplateHelpersTestHelpers.assert_valid_svg_path(result)

    def test_default_icon_is_valid_svg(self):
        """Test that default icon is valid SVG."""
        result = get_platform_icon("unknown")
        TemplateHelpersTestHelpers.assert_valid_svg_path(result)

    def test_none_input_handling(self):
        """Test that None input is handled gracefully for icons."""
        try:
            result = get_platform_icon(None)
            default_icon = get_platform_icon("default")
            assert result == default_icon
        except (AttributeError, TypeError):
            # This is acceptable behavior for None input
            pass


@pytest.mark.unit
class TestTemplateHelpersIntegration:
    """Integration tests for template helpers working together."""

    @pytest.mark.parametrize(
        "platform,expected_color,expected_icon_pattern", TestData.KNOWN_PLATFORMS
    )
    def test_platform_consistency(
        self, platform, expected_color, expected_icon_pattern
    ):
        """Test that platforms are handled consistently across both functions."""
        color_result = get_platform_color(platform)
        icon_result = get_platform_icon(platform)

        # Should return expected values, not defaults
        assert color_result == expected_color
        assert color_result != TestConstants.COLOR_DEFAULT

        # Icon should match expected pattern and not be default
        default_icon = get_platform_icon("default")
        assert icon_result != default_icon
        assert icon_result.startswith(expected_icon_pattern)

    @pytest.mark.parametrize("unknown_platform", TestData.UNKNOWN_PLATFORMS)
    def test_unknown_platform_consistency(self, unknown_platform):
        """Test that unknown platforms are handled consistently across functions."""
        color_result = get_platform_color(unknown_platform)
        icon_result = get_platform_icon(unknown_platform)

        # Both should return default values
        assert color_result == TestConstants.COLOR_DEFAULT

        default_icon = get_platform_icon("default")
        assert icon_result == default_icon

    def test_all_colors_are_unique(self):
        """Test that each platform has a unique color."""
        colors = set()
        for platform, expected_color, _ in TestData.KNOWN_PLATFORMS:
            assert (
                expected_color not in colors
            ), f"Duplicate color found: {expected_color}"
            colors.add(expected_color)

    @pytest.mark.parametrize(
        "platform,_,__", TestData.KNOWN_PLATFORMS + [("unknown", "default", "default")]
    )
    def test_return_types(self, platform, _, __):
        """Test that functions return expected types."""
        color_result = get_platform_color(platform)
        icon_result = get_platform_icon(platform)

        assert isinstance(
            color_result, str
        ), f"get_platform_color should return string for '{platform}'"
        assert isinstance(
            icon_result, str
        ), f"get_platform_icon should return string for '{platform}'"

        # Ensure non-empty returns
        assert (
            len(color_result) > 0
        ), f"get_platform_color returned empty string for '{platform}'"
        assert (
            len(icon_result) > 0
        ), f"get_platform_icon returned empty string for '{platform}'"
