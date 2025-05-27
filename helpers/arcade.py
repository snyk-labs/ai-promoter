"""
Arcade Helper Module

This module provides functions for interacting with the Arcade API for social media posting.
"""

import os
from arcadepy import Arcade
from flask import current_app
import logging

# Set up logging
logger = logging.getLogger(__name__)


# Initialize Arcade client
# client = Arcade()  # Automatically finds the `ARCADE_API_KEY` env variable
# Instead, create a function to get the client when needed
def get_arcade_client():
    """Get the Arcade client, initializing it if necessary."""
    return Arcade()


LINKEDIN_TOOL = "LinkedIn.CreateTextPost"


def start_linkedin_auth(user):
    """
    Start LinkedIn authorization process through Arcade.

    Args:
        user: The user object to authorize

    Returns:
        A dictionary with authorization status and redirect URL if needed
    """
    try:
        # Get the Arcade client
        client = get_arcade_client()

        auth_response = client.tools.authorize(
            tool_name=LINKEDIN_TOOL,
            user_id=user.email,
        )

        if auth_response.status != "completed":
            logger.info(f"LinkedIn auth started for user {user.email}")
            return {"status": "pending", "url": auth_response.url}
        else:
            user.linkedin_authorized = True
            logger.info(f"LinkedIn auth completed for user {user.email}")
            return {"status": "completed"}
    except Exception as e:
        logger.error(f"Error starting LinkedIn auth for user {user.email}: {str(e)}")
        raise ValueError(f"Failed to start LinkedIn authorization: {str(e)}")


def check_auth_status(user, tool_name):
    """
    Check if authorization is complete for the specified tool.

    Args:
        user: The user object to check authorization for
        tool_name: The name of the tool to check (LINKEDIN_TOOL)

    Returns:
        Boolean indicating if authorization is complete
    """
    try:
        # Get the Arcade client
        client = get_arcade_client()

        auth_response = client.auth.get_status(tool_name=tool_name, user_id=user.email)
        return auth_response.status == "completed"
    except Exception as e:
        logger.error(
            f"Error checking auth status for user {user.email}, tool {tool_name}: {str(e)}"
        )
        return False


def post_to_linkedin(user, content):
    """
    Post content to LinkedIn using Arcade.

    Args:
        user: The user object with authorization
        content: The content to post to LinkedIn

    Returns:
        Response from the Arcade API

    Raises:
        ValueError: If LinkedIn is not authorized or posting fails
    """
    if not user.linkedin_authorized:
        logger.warning(
            f"Attempted to post to LinkedIn for unauthorized user {user.email}"
        )
        raise ValueError("LinkedIn not authorized")

    try:
        # Get the Arcade client
        client = get_arcade_client()

        logger.info(f"Posting to LinkedIn for user {user.email}")
        response = client.tools.execute(
            tool_name=LINKEDIN_TOOL, input={"text": content}, user_id=user.email
        )
        logger.info(f"Successfully posted to LinkedIn for user {user.email}")
        return response
    except Exception as e:
        logger.error(f"Failed to post to LinkedIn for user {user.email}: {str(e)}")
        raise ValueError(f"Failed to post to LinkedIn: {str(e)}")
