# utils/helpers/__init__.py
"""Exports helper functions from submodules for easy access."""

import logging

logger = logging.getLogger(__name__)

try:
    from .batch_utils import process_batch
    from .markup_utils import (
        extract_button_url,
        create_ptb_inline_markup,
        has_specific_button,
    )
    from .media_utils import (
        MEDIA_PHOTO,
        MEDIA_VIDEO,
        MEDIA_DOCUMENT,
        MEDIA_AUDIO,
        MEDIA_VOICE,
        MEDIA_STICKER,
        MEDIA_ANIMATION,
        get_telethon_media_type,
        get_ptb_send_func_and_arg,
        get_media_file_id,
    )
    from .text_utils import (
        extract_action_and_username,
        get_action_emoji,
        format_full_mode_header_html, # Giữ lại để định dạng header
        # Lưu ý: format_fxtwitter_message_html và các format khác sẽ chuyển sang content_formatter
    )
    from .url_utils import (
        create_fxtwitter_url,
    )

    # Optional: Log successful import
    logger.debug("Successfully imported helper submodules.")

except ImportError as e:
    logger.critical(f"Failed to import helper submodules: {e}", exc_info=True)
    # Depending on severity, you might want to raise the error
    # raise ImportError(f"Could not load helper submodules: {e}") from e

__all__ = [
    # Batch
    "process_batch",
    # Markup
    "extract_button_url",
    "create_ptb_inline_markup",
    "has_specific_button",
    # Media
    "MEDIA_PHOTO",
    "MEDIA_VIDEO",
    "MEDIA_DOCUMENT",
    "MEDIA_AUDIO",
    "MEDIA_VOICE",
    "MEDIA_STICKER",
    "MEDIA_ANIMATION",
    "get_telethon_media_type",
    "get_ptb_send_func_and_arg",
    "get_media_file_id",
    # Text
    "extract_action_and_username",
    "get_action_emoji",
    "format_full_mode_header_html",
    # URL
    "create_fxtwitter_url",
]