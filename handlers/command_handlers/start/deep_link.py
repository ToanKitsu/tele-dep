# handlers/command_handlers/start/deep_link.py
# -*- coding: utf-8 -*-
import logging
from telegram import Update, ReplyKeyboardRemove, Bot
from telegram.ext import CallbackContext, ConversationHandler
from telegram.constants import ParseMode

# Assuming utils are in the parent directory structure
from utils import context_cache

logger = logging.getLogger(__name__)



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

        # --->>> SỬ DỤNG HÀM RESEND TỪ CONTEXT_CACHE <<<---
        resent_ok = await context_cache.resend_cached_message(chat_id, context_id, context.bot)
        # -------------------------------------------------

        if resent_ok:
            await update.message.reply_text(
                "Original message context displayed above.\n\n"
                "➡️ Ready to deploy a token based on this context?\n"
                "Type /deploy (or the relevant command) to begin the process.", # Nhắc user dùng lệnh deploy (chưa có)
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