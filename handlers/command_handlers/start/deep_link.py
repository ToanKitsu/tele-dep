# handlers/command_handlers/start/deep_link.py
# -*- coding: utf-8 -*-
import logging
from telegram import Update, ReplyKeyboardRemove, Bot
from telegram.ext import CallbackContext, ConversationHandler
from telegram.constants import ParseMode

# Assuming utils are in the parent directory structure
from utils import helpers as utils_helpers
from utils import context_cache

logger = logging.getLogger(__name__)

# --- Helper to Resend Cached Message (Moved here) ---
async def resend_cached_message(chat_id: int, context_id: str, bot: Bot) -> bool:
    """Looks up context_id, resends the message content, and removes from cache."""
    logger.info(f"Attempting to resend cached message for context_id: {context_id} to chat {chat_id}")
    cached_data = context_cache.get_from_cache(context_id)

    if not cached_data:
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
            send_info = utils_helpers.get_ptb_send_func_and_arg(media_type)
            if send_info:
                send_func_name, arg_name = send_info
                resend_func = getattr(bot, send_func_name, None)
                if resend_func:
                    resend_args = {'chat_id': chat_id, arg_name: file_id, 'caption': text}
                else: # Fallback if function not found
                    logger.error(f"Resend failed: PTB function {send_func_name} not found.")
                    resend_func = bot.send_message
                    resend_args = {'chat_id': chat_id, 'text': text if text else "(Media content could not be resent)"}
            else: # Fallback if media type not supported
                logger.error(f"Resend failed: Unsupported media type {media_type}")
                resend_func = bot.send_message
                resend_args = {'chat_id': chat_id, 'text': text if text else "(Unsupported media could not be resent)"}
        elif text: # If only text exists
            resend_func = bot.send_message
            resend_args = {'chat_id': chat_id, 'text': text}
        else: # No content to resend
            logger.warning(f"No content found in cache for context ID {context_id} to resend.")
            # No need to remove from cache here, finally block handles it
            return False

        # --- Perform the send ---
        if resend_func:
            await resend_func(**resend_args)
            logger.info(f"Successfully resent content for context ID {context_id} to chat {chat_id}")
            return True # Indicate success
        else:
            logger.error(f"Resend failed: No valid resend function determined for context ID {context_id}.")
            return False

    except Exception as e:
        logger.error(f"Error resending cached message for {context_id}: {e}", exc_info=True)
        return False # Indicate failure
    finally:
        # Always remove from cache after attempting resend
        context_cache.remove_from_cache(context_id)


# --- Handler for /start with deep link payload ---
async def handle_start_deep_link(update: Update, context: CallbackContext) -> int:
    """Handles the /start command with a deep link payload."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    payload = context.args[0] # We know context.args exists here

    logger.info(f"Handling deep link /start command from user {user.id} in chat {chat_id}. Payload: {payload}")

    if payload.startswith("deploy_"):
        context_id = payload.split('_', 1)[1]
        logger.info(f"Deep link 'deploy' with context_id '{context_id}' detected.")

        resent_ok = await resend_cached_message(chat_id, context_id, context.bot)

        if resent_ok:
            await update.message.reply_text(
                "Original message context displayed above.\n\n"
                "➡️ Ready to deploy a token based on this context?\n"
                "Type /deploy (or the relevant command) to begin the process.",
                reply_markup=ReplyKeyboardRemove()
            )
            logger.info(f"Prompted user {user.id} to use /deploy after resending context {context_id}.")
        else:
            await update.message.reply_text(
                "Sorry, the context for that deployment link could not be retrieved (it might have expired or there was an error).\n"
                "You can start a new deployment manually if needed.",
                reply_markup=ReplyKeyboardRemove()
            )
            logger.warning(f"Failed to resend context {context_id} for user {user.id}.")
    else:
        # Handle other potential deep links if necessary, or just treat as unknown
        logger.warning(f"Unknown deep link payload '{payload}' received.")
        await update.message.reply_text(
            f"Welcome, {user.mention_html()}! I received an unknown start parameter: {payload}\n\n"
            "I am your Telegram Scraper & Blockchain Bot.\n"
            "Currently, I forward messages and prepare deployment contexts.",
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardRemove()
        )

    # End the interaction after handling the deep link
    return ConversationHandler.END