from flask import current_app

# from slack_sdk import WebClient
# from slack_sdk.errors import SlackApiError


class SlackService:
    def __init__(self):
        """
        Initializes the SlackService.
        It will eventually use the SLACK_BOT_TOKEN from the application config.
        """
        # self.slack_bot_token = current_app.config.get('SLACK_BOT_TOKEN')
        # if not self.slack_bot_token:
        #     current_app.logger.error("SLACK_BOT_TOKEN is not configured.")
        #     # Depending on the app's strictness, could raise an error or operate in a degraded mode.
        #     self.client = None
        # else:
        #     self.client = WebClient(token=self.slack_bot_token)
        pass  # Replace with actual client initialization later

    def handle_event(self, event_payload):
        """
        Processes a Slack event payload.
        This method will differentiate event types and call appropriate handlers.
        """
        event_type = event_payload.get(
            "type"
        )  # This is the outer type (e.g. event_callback)
        event = event_payload.get(
            "event", {}
        )  # This is the inner event (e.g. app_mention)
        inner_event_type = event.get("type")

        current_app.logger.info(
            f"SlackService received event. Outer type: '{event_type}', Inner type: '{inner_event_type}'"
        )

        # Example: Dispatch based on inner event type
        # if inner_event_type == 'app_mention':
        #     self.handle_app_mention(event)
        # elif inner_event_type == 'message':
        #     # Further differentiate message subtypes if needed (e.g., direct message, channel message)
        #     self.handle_message(event)
        # else:
        #     current_app.logger.info(f"No specific handler for inner event type: {inner_event_type}")

        # For now, just log that it was received
        return {"status": "event received by service"}

    def handle_app_mention(self, event_details):
        """
        Handles 'app_mention' events.
        """
        channel_id = event_details.get("channel")
        user_id = event_details.get("user")
        text = event_details.get("text")
        current_app.logger.info(
            f"App mention from user {user_id} in channel {channel_id}: {text}"
        )

        # Example: Send a reply
        # if self.client and channel_id:
        #     self.post_message(channel_id, f"Hello <@{user_id}>, thanks for the mention!")
        pass

    def handle_message(self, event_details):
        """
        Handles 'message' events.
        Needs to be careful about bot messages to avoid loops.
        """
        # Avoid responding to own messages or other bot messages
        if event_details.get("subtype") == "bot_message" or event_details.get("bot_id"):
            return

        channel_id = event_details.get("channel")
        user_id = event_details.get("user")  # User who sent the message
        text = event_details.get("text")
        current_app.logger.info(
            f"Message from user {user_id} in channel {channel_id}: {text}"
        )

        # Example: Basic response to a direct message or specific keyword
        # if self.client and channel_id and "hello" in text.lower():
        #     self.post_message(channel_id, f"Hi <@{user_id}>, you said hello!")
        pass

    def post_message(self, channel_id, text):
        """
        Posts a message to a Slack channel using the WebClient.
        """
        # if not self.client:
        #     current_app.logger.error("Slack client not initialized. Cannot post message.")
        #     return None
        # try:
        #     response = self.client.chat_postMessage(channel=channel_id, text=text)
        #     current_app.logger.info(f"Message posted to {channel_id}. Timestamp: {response.get('ts')}")
        #     return response
        # except SlackApiError as e:
        #     current_app.logger.error(f"Error posting message to Slack channel {channel_id}: {e.response['error']}")
        #     return None
        pass


# Global instance of the service.
# Consider dependency injection for more complex applications or testing.
slack_service = SlackService()
