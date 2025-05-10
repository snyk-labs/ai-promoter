from firecrawl import FirecrawlApp
from openai import OpenAI
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
        api_key = current_app.config.get('FIRECRAWL_API_KEY')
        if not api_key:
            raise ValueError("FIRECRAWL_API_KEY not configured in Flask app")
        
        self.firecrawl = FirecrawlApp(api_key=api_key)
        self.openai = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    def process_url(self, url: str, submitted_by_id: int = None):
        """Process a URL and create content."""
        logger.info(f"Processing URL: {url}")
        
        try:
            # First, scrape the URL using Firecrawl
            logger.info("Attempting to scrape URL with Firecrawl...")
            scrape_result = self.firecrawl.scrape_url(url, formats=['markdown', 'html'])
            
            if not scrape_result:
                logger.error("Firecrawl returned empty result")
                raise ValueError("Failed to scrape content from URL - empty result")
            
            # Get the markdown content from the response
            markdown_content = scrape_result.markdown if hasattr(scrape_result, 'markdown') else None
            if not markdown_content:
                logger.error("Firecrawl result missing markdown content")
                raise ValueError("Failed to scrape content from URL - markdown content not available")
            
            logger.info("Successfully scraped content from URL")
            
            # Check for og:image in the Firecrawl response metadata first
            og_image = None
            if hasattr(scrape_result, 'metadata') and isinstance(scrape_result.metadata, dict):
                og_image = scrape_result.metadata.get('og:image')
                if og_image:
                    logger.info("Found og:image in Firecrawl response metadata")
            
            # Use OpenAI to extract relevant information
            content_info = self._extract_content_info(markdown_content, url)
            
            # If we found an og:image, use it instead of any image found in the content
            if og_image:
                content_info['Image URL'] = og_image
            
            # Create the content
            return self._create_content(content_info, url, markdown_content, submitted_by_id=submitted_by_id)
                
        except Exception as e:
            logger.error(f"Error processing URL: {str(e)}", exc_info=True)
            raise ValueError(f"Failed to process URL: {str(e)}")

    def _extract_content_info(self, content: str, url: str) -> dict:
        """Use OpenAI to extract relevant information from the content and determine content type."""
        prompt = f"""Analyze this content and extract the following information:
        - Title
        - Publish date (if available)
        - Description/excerpt
        - Image URL (if available)
        - Any other relevant metadata

        URL: {url}
        Content:
        {content}

        Return the information in JSON format."""

        response = self.openai.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": "You are a content analysis assistant. Analyze the provided content and URL to extract relevant information and determine the content type. Return the information in JSON format."},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" }
        )

        try:
            # Parse the JSON response
            content_info = json.loads(response.choices[0].message.content)
            logger.info(f"Successfully extracted content info: {content_info}")
            return content_info
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI response as JSON: {str(e)}")
            raise ValueError("Failed to parse content information from OpenAI response")

    def _create_content(self, content_info: dict, url: str, scraped_content: str, submitted_by_id: int = None) -> Content:
        """Create a new Content item from the extracted content."""
        image_url = content_info.get('Image URL')
        # If image_url is a list, use the first item
        if isinstance(image_url, list):
            image_url = image_url[0] if image_url else None

        # Handle publish date
        publish_date = datetime.utcnow()  # Default to current time
        publish_date_str = content_info.get('Publish Date')
        if publish_date_str and publish_date_str != 'Not available':
            try:
                publish_date = datetime.strptime(publish_date_str, '%B %d, %Y')
            except ValueError:
                logger.warning(f"Could not parse publish date '{publish_date_str}', using current time")

        content = Content(
            title=content_info.get('Title', ''),
            url=url,
            scraped_content=scraped_content,
            excerpt=content_info.get('Description', ''),
            image_url=image_url,
            publish_date=publish_date,
            submitted_by_id=submitted_by_id
        )
        db.session.add(content)
        db.session.commit()
        return content 