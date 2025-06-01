from firecrawl import FirecrawlApp
import google.generativeai as genai
import os
import logging
import json
from datetime import datetime
from models.content import Content
from extensions import db
from flask import current_app

logger = logging.getLogger(__name__)


class ContentProcessor:
    def __init__(self):
        api_key = current_app.config.get("FIRECRAWL_API_KEY")
        if not api_key:
            raise ValueError("FIRECRAWL_API_KEY not configured in Flask app")

        self.firecrawl = FirecrawlApp(api_key=api_key)
        self.gemini = self._get_gemini_client()

    def _get_gemini_client(self):
        """Get a Gemini client instance."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        genai.configure(api_key=api_key)
        return genai.GenerativeModel("gemini-1.5-pro")

    def _get_safe_value(self, content_info, key, current_value, fallback=""):
        """Safely extract a value from content_info, preserving existing values when None/empty."""
        extracted_value = content_info.get(key)

        # If Gemini returned None, empty string, or "Not available", preserve existing value
        if (
            extracted_value is None
            or extracted_value == ""
            or extracted_value == "Not available"
        ):
            return current_value if current_value else fallback

        return extracted_value

    def process_url(self, content_id: int, url: str):
        """Process a URL and update an existing content item."""
        logger.info(f"Processing URL: {url} for content_id: {content_id}")

        content_item = Content.query.get(content_id)
        if not content_item:
            logger.error(f"Content with ID {content_id} not found.")
            return None

        try:
            # First, scrape the URL using Firecrawl
            logger.info(f"Attempting to scrape URL {url} with Firecrawl...")
            scrape_result = self.firecrawl.scrape_url(url, formats=["markdown", "html"])

            if not scrape_result:
                logger.error("Firecrawl returned empty result")
                raise ValueError("Failed to scrape content from URL - empty result")

            # Get the markdown content from the response
            markdown_content = (
                scrape_result.markdown if hasattr(scrape_result, "markdown") else None
            )
            if not markdown_content:
                logger.error("Firecrawl result missing markdown content")
                raise ValueError(
                    "Failed to scrape content from URL - markdown content not available"
                )

            logger.info(f"Successfully scraped content from URL {url}")

            # Check for og:image in the Firecrawl response metadata first
            og_image = None
            if hasattr(scrape_result, "metadata") and isinstance(
                scrape_result.metadata, dict
            ):
                og_image = scrape_result.metadata.get("og:image")
                if og_image:
                    logger.info("Found og:image in Firecrawl response metadata")

            # Use Gemini to extract relevant information
            content_info = self._extract_content_info(markdown_content)

            # If we found an og:image, use it instead of any image found in the content
            if og_image:
                content_info["Image URL"] = og_image

            # Update the existing content item
            image_url_extracted = content_info.get("Image URL")
            if isinstance(image_url_extracted, list):
                image_url_extracted = (
                    image_url_extracted[0] if image_url_extracted else None
                )

            publish_date_val = datetime.utcnow()  # Default to current time
            publish_date_str = content_info.get("Publish Date")
            if publish_date_str and publish_date_str != "Not available":
                try:
                    publish_date_val = datetime.strptime(publish_date_str, "%B %d, %Y")
                except ValueError:
                    try:  # Try another common format
                        publish_date_val = datetime.strptime(
                            publish_date_str, "%Y-%m-%d"
                        )
                    except ValueError:
                        logger.warning(
                            f"Could not parse publish date '{publish_date_str}', using current time"
                        )

            # Use safe value extraction to prevent None values from violating database constraints
            content_item.title = self._get_safe_value(
                content_info, "Title", content_item.title, "Untitled"
            )
            content_item.scraped_content = markdown_content
            content_item.excerpt = self._get_safe_value(
                content_info, "Description", content_item.excerpt, ""
            )
            content_item.image_url = (
                image_url_extracted if image_url_extracted else content_item.image_url
            )
            content_item.publish_date = publish_date_val
            # content_item.url is already set and should not change
            # content_item.submitted_by_id is already set

            db.session.add(content_item)
            db.session.commit()
            logger.info(
                f"Successfully updated content_id: {content_id} with data from {url}"
            )
            return content_item

        except Exception as e:
            logger.error(f"Error processing URL {url}: {str(e)}")
            raise

    def _extract_content_info(self, content):
        """Use Gemini to extract relevant information from the content and determine content type."""
        try:
            prompt = f"""Analyze the following content and extract key information in JSON format:
            {content}

            Return a JSON object with these fields:
            - Title: The main title of the content
            - Description: A brief description or summary
            - Image URL: Any image URLs found in the content
            - Publish Date: The publication date if available, or "Not available"
            - Key Points: An array of 3-5 main points or takeaways
            - Target Audience: Who this content is intended for
            - Tone: The overall tone of the content (e.g., professional, casual, technical)

            IMPORTANT: Your response must be a valid JSON object. Do not include any additional text or explanation."""

            response = self.gemini.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=1000,
                ),
            )

            # Get the response text and clean it
            response_text = response.text.strip()

            # Try to find JSON content if it's wrapped in markdown code blocks
            if "```json" in response_text:
                response_text = (
                    response_text.split("```json")[1].split("```")[0].strip()
                )
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            try:
                content_info = json.loads(response_text)
                logger.info(f"Successfully parsed Gemini response: {content_info}")
                return content_info
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Gemini response as JSON: {str(e)}")
                logger.error(f"Raw response: {response_text}")
                raise ValueError(
                    "Failed to parse content information from Gemini response"
                )

        except Exception as e:
            logger.error(f"Error extracting content info: {str(e)}")
            raise
