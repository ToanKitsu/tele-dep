# handlers/message_processing/analyzer.py
import logging
import uuid
from dataclasses import dataclass, field
from telethon.tl.custom import Message
from telegram import Bot

# Import helpers from the new structure
from utils.helpers import markup_utils, media_utils, text_utils, url_utils
from utils import context_cache
from config import settings

logger = logging.getLogger(__name__)

@dataclass
class MessageAnalysisResult:
    """Holds the results of analyzing an incoming message."""
    message_id: int
    log_prefix: str
    original_message: Message # Keep the original message object if needed later
    has_required_button: bool
    bot_username: str | None = None
    original_text: str = ""
    media_type: str | None = None
    tweet_url: str | None = None
    action_type: str | None = None
    username: str | None = None
    context_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    deploy_deep_link: str | None = None
    initial_cache_data: dict = field(default_factory=dict)

async def analyze_message(message: Message, target_bot: Bot) -> MessageAnalysisResult | None:
    """
    Analyzes the incoming Telethon message and extracts key information.
    Returns a MessageAnalysisResult object or None if critical info is missing.
    """
    message_id = message.id
    log_prefix = f"Msg {message_id}: [Analyze] "
    logger.info(f"{log_prefix}Starting analysis.")

    # --- Basic Checks & Info Extraction ---
    has_required_button = markup_utils.has_specific_button(message, settings.BUTTON_TEXT_TO_FIND)
    if not has_required_button:
        logger.debug(f"{log_prefix}Skipping: Missing '{settings.BUTTON_TEXT_TO_FIND}' button.")
        # Return None early if the button is strictly required to proceed
        # return None # Or return result with has_required_button=False if you handle it later

    try:
        bot_info = await target_bot.get_me()
        bot_username = bot_info.username
        if not bot_username:
            raise ValueError("Bot username missing")
    except Exception as e:
        logger.error(f"{log_prefix}Could not get bot info: {e}")
        return None # Cannot proceed without bot username for deep links

    original_text = message.text or ""
    media_type = media_utils.get_telethon_media_type(message)
    tweet_url = markup_utils.extract_button_url(message, settings.BUTTON_TEXT_TO_FIND) # Original URL

    # --- Analyze Text Content ---
    action_type, username = text_utils.extract_action_and_username(original_text)
    logger.info(f"{log_prefix}Analyzed text: Action='{action_type}', User='{username}'")

    # --- Prepare Common Data & Initial Cache ---
    context_id = uuid.uuid4().hex
    initial_cache_data = {'text': original_text, 'media_type': media_type, 'file_id': None}
    # Store initial data in cache immediately
    context_cache.add_to_cache(context_id, initial_cache_data)
    logger.debug(f"{log_prefix}Stored initial data in cache (ID: {context_id}).")

    deploy_deep_link = f"https://t.me/{bot_username}?start=deploy_{context_id}"
    logger.debug(f"{log_prefix}Generated deploy deep link: {deploy_deep_link}")

    return MessageAnalysisResult(
        message_id=message_id,
        log_prefix=log_prefix, # Include log_prefix for consistency
        original_message=message,
        has_required_button=has_required_button,
        bot_username=bot_username,
        original_text=original_text,
        media_type=media_type,
        tweet_url=tweet_url,
        action_type=action_type,
        username=username,
        context_id=context_id,
        deploy_deep_link=deploy_deep_link,
        initial_cache_data=initial_cache_data,
    )