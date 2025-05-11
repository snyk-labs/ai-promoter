"""
Utility Module

This module provides general utility functions used across the application.
"""

import logging
import re
from bs4 import BeautifulSoup
import urllib.parse
from datetime import datetime

# Set up logging
logger = logging.getLogger(__name__)


def clean_html(html_content):
    """
    Clean HTML content by removing tags and normalizing whitespace.

    Args:
        html_content: The HTML content to clean

    Returns:
        A string with HTML tags removed and whitespace normalized
    """
    if not html_content:
        return ""

    # Parse HTML with BeautifulSoup
    soup = BeautifulSoup(html_content, "html.parser")

    # Get text content
    text = soup.get_text(separator=" ")

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def parse_date(date_string):
    """
    Parse a date string into a datetime object.

    Args:
        date_string: The date string to parse

    Returns:
        A datetime object or None if parsing fails
    """
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",  # RSS standard format
        "%a, %d %b %Y %H:%M:%S %Z",  # RSS with timezone name
        "%Y-%m-%dT%H:%M:%S%z",  # ISO 8601 with timezone
        "%Y-%m-%dT%H:%M:%S.%f%z",  # ISO 8601 with ms and timezone
        "%Y-%m-%dT%H:%M:%SZ",  # ISO 8601 UTC
        "%Y-%m-%dT%H:%M:%S",  # ISO 8601 without timezone
        "%Y-%m-%d %H:%M:%S",  # Simple datetime
        "%Y-%m-%d",  # Simple date
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_string, fmt)
        except ValueError:
            continue

    logger.warning(f"Could not parse date: {date_string}")
    return None


def normalize_url(url):
    """
    Normalize a URL by ensuring proper formatting and escaping.

    Args:
        url: The URL to normalize

    Returns:
        A properly formatted URL
    """
    if not url:
        return ""

    # Parse URL to handle escaping properly
    parsed = urllib.parse.urlparse(url)

    # Rebuild with proper escaping
    normalized = urllib.parse.urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )

    return normalized


def extract_youtube_id(url):
    """
    Extract the YouTube video ID from a URL.

    Args:
        url: The YouTube URL

    Returns:
        The YouTube video ID or None if not found
    """
    if not url:
        return None

    # Patterns for YouTube URLs
    patterns = [
        r'(?:youtube\.com/(?:[^/]+/.+/|(?:v|e(?:mbed)?)/|.*[?&]v=)|youtu\.be/)([^"&?/ ]{11})',  # Standard and embedded
        r'youtube.com/shorts/([^"&?/ ]{11})',  # YouTube Shorts
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


def truncate_text(text, max_length=100, suffix="..."):
    """
    Truncate text to a maximum length.

    Args:
        text: The text to truncate
        max_length: The maximum length
        suffix: The suffix to add when truncated

    Returns:
        The truncated text
    """
    if not text:
        return ""

    if len(text) <= max_length:
        return text

    return text[: max_length - len(suffix)].strip() + suffix


def append_utm_params(url, utm_params):
    """
    Append UTM parameters to a URL.

    Args:
        url: The base URL to append parameters to
        utm_params: String containing UTM parameters (e.g. "utm_source=linkedin&utm_medium=social" or "?utm_source=linkedin")

    Returns:
        URL with UTM parameters appended
    """
    if not url or not utm_params:
        return url

    # Remove leading ? from utm_params if present
    if utm_params.startswith('?'):
        utm_params = utm_params[1:]

    # Parse the URL
    parsed = urllib.parse.urlparse(url)
    
    # Parse existing query parameters
    existing_params = urllib.parse.parse_qs(parsed.query)
    
    # Parse new UTM parameters
    utm_params_dict = urllib.parse.parse_qs(utm_params)
    
    # Merge parameters, with UTM params taking precedence
    merged_params = {**existing_params, **utm_params_dict}
    
    # Rebuild query string
    new_query = urllib.parse.urlencode(merged_params, doseq=True)
    
    # Rebuild URL with new query
    return urllib.parse.urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment
    ))
