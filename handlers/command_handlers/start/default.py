# handlers/command_handlers/start/default.py
# -*- coding: utf-8 -*-
import logging
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import CallbackContext, ConversationHandler
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

async def handle_start_default(update: Update, context: CallbackContext) -> int:
    """Handles the /start command without arguments."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    logger.info(f"Handling default /start command from user {user.id} in chat {chat_id}")

    await update.message.reply_text(
        f"Welcome, {user.mention_html()}!\n\n"
        "I am your homie\n"
        "I forward messages and prepare deployment contexts.\n\n"
        "You can use me to deploy tokens or manage your wallet.\n\n", # Your welcome message
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )
    # This is the end of the interaction for a simple /start
    return ConversationHandler.END