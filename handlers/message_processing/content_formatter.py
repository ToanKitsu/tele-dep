# handlers/message_processing/content_formatter.py
import logging
import html
import re
from dataclasses import dataclass
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from .analyzer import MessageAnalysisResult
from config import settings, group_config
from utils.helpers import text_utils, url_utils # Use specific helpers

logger = logging.getLogger(__name__)

@dataclass
class ContentPayload:
    """Holds the formatted content and markup for a specific mode."""
    text: str | None = None
    caption: str | None = None # Use caption if media is present
    reply_markup: InlineKeyboardMarkup | None = None
    parse_mode: str = ParseMode.HTML
    send_args: dict | None = None # Pre-filled dict for sending (alternative)


def format_fxtwitter_message_html(action_type: str | None, username: str | None, fxtwitter_url: str | None) -> str | None:
    """Formats the short message for FXTwitter mode using HTML and action type."""
    if not username or not fxtwitter_url:
        logger.warning(f"Cannot format FXTwitter message: action='{action_type}', username='{username}', url='{fxtwitter_url}'")
        # Return a fallback or None depending on desired behavior
        action_text_fallback = action_type if action_type else "Action"
        username_fallback = username if username else "Link"
        return f"{text_utils.get_action_emoji(action_type)}<b>{html.escape(action_text_fallback)}</b> from {html.escape(username_fallback)}"


    emoji = text_utils.get_action_emoji(action_type)
    action_text = action_type if action_type else "Action" # Default text if type unknown

    safe_username = html.escape(username)
    safe_url = html.escape(fxtwitter_url) # URL for the inline link
    safe_action_text = html.escape(action_text) # Escape action text just in case

    # Format: Emoji <b>Action</b> from <a href="fxtwitter_url">username</a>
    return f'{emoji}<b>{safe_action_text}</b> from <a href="{safe_url}">{safe_username}</a>'


def format_full_message_body_html(original_text: str, action_type: str | None) -> str:
    """Formats the main body of the message for Full Mode, handling RT prefix."""
    body_start_index = -1
    if "\n\n" in original_text: body_start_index = original_text.find("\n\n") + 2
    elif "\n" in original_text: body_start_index = original_text.find("\n") + 1
    message_body_raw = original_text[body_start_index:].strip() if body_start_index != -1 else original_text # Fallback to full text if no separator

    formatted_body = ""
    if action_type == "Retweet":
        # Regex to find optional **RT** (with optional spaces) at the beginning
        # Captures the part *after* the RT prefix. Case-insensitive, handles multi-line.
        rt_match = re.match(r"^\**\s*RT\s*\**\s*(.*)", message_body_raw, re.IGNORECASE | re.DOTALL)
        if rt_match:
            prefix = "<b>RT</b>"
            rest_of_body = rt_match.group(1).strip() # Get content after RT
            # Escape the rest of the body to prevent unintended HTML
            formatted_body = f"{prefix} {html.escape(rest_of_body)}"
            logger.debug("Applied specific RT formatting.")
        else:
            logger.debug("Retweet action, but RT prefix not found/matched. Escaping full body.")
            formatted_body = html.escape(message_body_raw)
    else:
        # Not a Retweet, just escape the whole body
        formatted_body = html.escape(message_body_raw)

    return formatted_body


def format_content_for_targets(analysis_result: MessageAnalysisResult, needs_fxtwitter: bool, needs_full_mode: bool) -> tuple[ContentPayload | None, ContentPayload | None]:
    """
    Prepares ContentPayload objects for FXTwitter and Full modes based on analysis.
    Returns (fxtwitter_payload, full_mode_payload).
    """
    log_prefix = analysis_result.log_prefix.replace("[Analyze]", "[Format]")
    fxtwitter_payload = None
    full_mode_payload = None

    # --- Prepare Keyboards (Common Buttons) ---
    common_buttons = []
    if analysis_result.tweet_url:
        common_buttons.append(InlineKeyboardButton(settings.BUTTON_TEXT_TO_FIND, url=analysis_result.tweet_url))
    if analysis_result.deploy_deep_link:
        common_buttons.append(InlineKeyboardButton("🚀 Deploy New Token", url=analysis_result.deploy_deep_link))

    reply_markup = InlineKeyboardMarkup([common_buttons]) if common_buttons else None

    # --- Format FXTwitter Content ---
    if needs_fxtwitter:
        logger.debug(f"{log_prefix}Formatting for FXTwitter mode.")
        fx_url_inline = url_utils.create_fxtwitter_url(analysis_result.tweet_url)
        if fx_url_inline:
            fxtwitter_text = format_fxtwitter_message_html(
                analysis_result.action_type,
                analysis_result.username,
                fx_url_inline
            )
            if fxtwitter_text:
                fxtwitter_payload = ContentPayload(
                    text=fxtwitter_text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
            else:
                logger.warning(f"{log_prefix}Failed to format FXTwitter text, using fallback.")
                # Basic fallback if formatting fails but URL exists
                fxtwitter_text = f"{text_utils.get_action_emoji(analysis_result.action_type)} {html.escape(analysis_result.original_text[:100])}{'...' if len(analysis_result.original_text) > 100 else ''}"
                fxtwitter_payload = ContentPayload(text=fxtwitter_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else:
            logger.warning(f"{log_prefix}Could not create FXTwitter URL. Cannot generate FX content.")


    # --- Format Full Mode Content (Header + Body) ---
    if needs_full_mode:
        logger.debug(f"{log_prefix}Formatting for Full mode.")
        # Format the header
        formatted_header = text_utils.format_full_mode_header_html(
            analysis_result.action_type,
            analysis_result.username,
            analysis_result.tweet_url # Use original tweet URL for the link in the header
        )

        # Format the body
        formatted_body = format_full_message_body_html(
            analysis_result.original_text,
            analysis_result.action_type
        )

        # Combine header and formatted body
        final_full_content = ""
        if formatted_header:
            final_full_content = f"{formatted_header}\n\n{formatted_body}".strip()
        else:
            logger.warning(f"{log_prefix}Failed full mode header format. Using formatted body only.")
            final_full_content = formatted_body

        if final_full_content:
             # If media is expected, this text will be used as caption, otherwise as text
            full_mode_payload = ContentPayload(
                caption=final_full_content, # Assume media first, sender will adapt
                text=final_full_content,    # Also set text for fallback
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
        else:
             logger.error(f"{log_prefix}Failed to generate any content for Full mode.")


    return fxtwitter_payload, full_mode_payload