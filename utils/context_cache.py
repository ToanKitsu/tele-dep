# utils/context_cache.py
# -*- coding: utf-8 -*-
import time
import logging
# --->>> THÊM IMPORT <<<---
from telegram import Bot
from . import helpers as utils_helpers # Import helper để dùng get_ptb_send_func_and_arg
# -----------------------

logger = logging.getLogger(__name__)

# Structure: { context_id: {'text': ..., 'media_type': ..., 'file_id': ..., 'timestamp': ...} }
message_context_cache = {}
CACHE_TTL_SECONDS = 600 # Keep context for 10 minutes (tăng lên một chút)

def cleanup_cache():
    # ... (logic giữ nguyên) ...
    """Removes expired entries from the cache."""
    now = time.time()
    expired_keys = [
        key for key, value in message_context_cache.items()
        if now - value.get('timestamp', 0) > CACHE_TTL_SECONDS
    ]
    count = 0
    for key in expired_keys:
        try:
            del message_context_cache[key]
            count += 1
        except KeyError:
            pass # Already removed
    if count > 0:
        logger.debug(f"Removed {count} expired context cache entries.")


def add_to_cache(context_id: str, data: dict):
    # ... (logic giữ nguyên) ...
    """Adds data to the cache with a timestamp."""
    data['timestamp'] = time.time()
    message_context_cache[context_id] = data
    logger.info(f"Stored message context in cache with ID: {context_id}")


def get_from_cache(context_id: str) -> dict | None:
    # ... (logic giữ nguyên) ...
    """Gets data from cache if it exists and is not expired."""
    cached_data = message_context_cache.get(context_id)
    if not cached_data:
        logger.warning(f"Context ID {context_id} not found in cache.")
        return None

    now = time.time()
    if now - cached_data.get('timestamp', 0) > CACHE_TTL_SECONDS:
        logger.warning(f"Context ID {context_id} expired.")
        try: del message_context_cache[context_id] # Clean up expired entry
        except KeyError: pass
        return None

    return cached_data

def remove_from_cache(context_id: str):
    # ... (logic giữ nguyên) ...
    """Removes an entry from the cache."""
    try:
        del message_context_cache[context_id]
        logger.debug(f"Removed context cache key: {context_id}")
    except KeyError:
        pass # Ignore if already removed


# --->>> THÊM HÀM HELPER NÀY VÀO ĐÂY <<<---
async def resend_cached_message(chat_id: int, context_id: str, bot: Bot) -> bool:
    """Looks up context_id, resends the message content, and removes from cache."""
    logger.info(f"Attempting to resend cached message for context_id: {context_id} to chat {chat_id}")
    # Use get_from_cache defined above
    cached_data = get_from_cache(context_id)

    if not cached_data:
        # get_from_cache already logs expiration/not found
        return False # Not found or expired

    logger.info(f"Resending message content for context ID: {context_id}")
    text = cached_data.get('text', '')
    media_type = cached_data.get('media_type')
    file_id = cached_data.get('file_id')
    logger.debug(f"Cache data - text: {bool(text)}, media_type: {media_type}, file_id: {bool(file_id)}")

    resend_func = None
    resend_args = {}

    try:
        if media_type and file_id:
            # Use the imported helper function
            send_info = utils_helpers.get_ptb_send_func_and_arg(media_type)
            if send_info:
                send_func_name, arg_name = send_info
                resend_func = getattr(bot, send_func_name, None)
                if resend_func:
                    resend_args = {'chat_id': chat_id, arg_name: file_id, 'caption': text}
                    logger.debug(f"Prepared to resend media type {media_type} using file_id.")
                else:
                    logger.error(f"Resend failed: PTB function {send_func_name} not found.")
                    # Fallback to text message
                    resend_func = bot.send_message
                    resend_args = {'chat_id': chat_id, 'text': text if text else "(Media content could not be resent)"}
            else:
                logger.error(f"Resend failed: Unsupported media type {media_type}")
                resend_func = bot.send_message
                resend_args = {'chat_id': chat_id, 'text': text if text else "(Unsupported media could not be resent)"}
        elif text:
            resend_func = bot.send_message
            resend_args = {'chat_id': chat_id, 'text': text}
            logger.debug("Prepared to resend text message.")
        else:
            logger.warning(f"No content found in cache for context ID {context_id} to resend.")
            remove_from_cache(context_id) # Use remove_from_cache defined above
            return False

        if resend_func:
            await resend_func(**resend_args)
            logger.info(f"Successfully resent content for context ID {context_id} to chat {chat_id}")
        else:
             logger.error(f"Resend failed: No valid resend function determined for context ID {context_id}.")
             return False # Explicitly return False if no function was found

    except Exception as e:
        logger.error(f"Error resending cached message for {context_id}: {e}", exc_info=True)
        return False # Return False on error
    finally:
        # Always remove from cache after attempting resend (success or fail)
         remove_from_cache(context_id) # Use remove_from_cache defined above

    return True # Return True only if function was found and called without error
# ------------------------------------------------