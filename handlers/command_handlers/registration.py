# handlers/command_handlers/registration.py
# -*- coding: utf-8 -*-
import logging
from telegram import Update
# ---> FIX: Change ChatMemberUpdatedHandler to ChatMemberHandler <---
from telegram.ext import Application, CommandHandler, CallbackContext, ConversationHandler, ChatMemberHandler

# Import handlers from submodules
from .start.default import handle_start_default
from .start.deep_link import handle_start_deep_link
from .display.group_display import get_group_display_conversation_handler
from ..bot_status_handlers import handle_chat_member_update

logger = logging.getLogger(__name__)

async def start_command_dispatcher(update: Update, context: CallbackContext) -> int:
    # ... (remains the same) ...
    if context.args:
        return await handle_start_deep_link(update, context)
    else:
        return await handle_start_default(update, context)

def register_all_command_handlers(application: Application):
    """Registers all command handlers with the PTB application."""
    logger.info("Registering command handlers...")

    # --- /start Command ---
    application.add_handler(CommandHandler("start", start_command_dispatcher))
    logger.info("Registered /start command dispatcher.")

    # --- /display Command ---
    group_display_handler = get_group_display_conversation_handler()
    application.add_handler(group_display_handler)
    logger.info("Registered /display conversation handler.")

    # ---> FIX: Change ChatMemberUpdatedHandler to ChatMemberHandler <---
    # React specifically to the bot's own status changes in chats
    application.add_handler(ChatMemberHandler(handle_chat_member_update, ChatMemberHandler.MY_CHAT_MEMBER))
    logger.info("Registered ChatMemberHandler for bot status changes.") # Updated log message slightly
    # --------------------------------

    logger.info("All command handler registration complete.")