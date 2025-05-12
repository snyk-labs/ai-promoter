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

    def process_url(self, content_id: int, url: str):
        """Process a URL and update an existing content item."""
        logger.info(f"Processing URL: {url} for content_id: {content_id}")
        
        content_item = Content.query.get(content_id)
        if not content_item:
            logger.error(f"Content item with id {content_id} not found.")
            # Optionally, raise an error or handle as appropriate
            # For now, we'll log and return, or you might want to create it if that's desired.
            # However, the current flow implies it should exist.
            raise ValueError(f"Content item with id {content_id} not found.")

        try:
            # First, scrape the URL using Firecrawl
            logger.info(f"Attempting to scrape URL {url} with Firecrawl...")
            scrape_result = self.firecrawl.scrape_url(url, formats=['markdown', 'html'])
            
            if not scrape_result:
                logger.error("Firecrawl returned empty result")
                raise ValueError("Failed to scrape content from URL - empty result")
            
            # Get the markdown content from the response
            markdown_content = scrape_result.markdown if hasattr(scrape_result, 'markdown') else None
            if not markdown_content:
                logger.error("Firecrawl result missing markdown content")
                raise ValueError("Failed to scrape content from URL - markdown content not available")
            
            logger.info(f"Successfully scraped content from URL {url}")
            
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
            
            # Update the existing content item
            image_url_extracted = content_info.get('Image URL')
            if isinstance(image_url_extracted, list):
                image_url_extracted = image_url_extracted[0] if image_url_extracted else None

            publish_date_val = datetime.utcnow()  # Default to current time
            publish_date_str = content_info.get('Publish Date')
            if publish_date_str and publish_date_str != 'Not available':
                try:
                    publish_date_val = datetime.strptime(publish_date_str, '%B %d, %Y')
                except ValueError:
                    try: # Try another common format
                        publish_date_val = datetime.strptime(publish_date_str, '%Y-%m-%d')
                    except ValueError:
                         logger.warning(f"Could not parse publish date '{publish_date_str}', using current time")
            
            content_item.title = content_info.get('Title', content_item.title or '')
            content_item.scraped_content = markdown_content
            content_item.excerpt = content_info.get('Description', content_item.excerpt or '')
            content_item.image_url = image_url_extracted if image_url_extracted else content_item.image_url
            content_item.publish_date = publish_date_val
            # content_item.url is already set and should not change
            # content_item.submitted_by_id is already set

            db.session.add(content_item)
            db.session.commit()
            logger.info(f"Successfully updated content_id: {content_id} with data from {url}")
            return content_item
                
        except Exception as e:
            logger.error(f"Error processing URL {url} for content_id {content_id}: {str(e)}", exc_info=True)
            # Optionally, revert changes or set a status on content_item
            db.session.rollback() # Rollback on error to prevent partial updates
            raise ValueError(f"Failed to process URL {url} for content_id {content_id}: {str(e)}")

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