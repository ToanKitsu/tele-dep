# handlers/command_handlers/registration.py
# -*- coding: utf-8 -*-
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext, ConversationHandler

# Import handlers from submodules
from .start.default import handle_start_default
from .start.deep_link import handle_start_deep_link
# --->>> UPDATE IMPORT PATH AND FUNCTION NAME <<<---
from .display.group_display import get_group_display_conversation_handler
# Import future handlers here, e.g.:
# from .wallet.add import handle_wallet_add_start
# from .deploy.token import handle_deploy_token_start

logger = logging.getLogger(__name__)

async def start_command_dispatcher(update: Update, context: CallbackContext) -> int:
    """
    Dispatches the /start command to the appropriate handler
    based on whether context.args exist (deep link payload).
    """
    if context.args:
        # Has payload - likely a deep link
        return await handle_start_deep_link(update, context)
    else:
        # No payload - standard /start command
        return await handle_start_default(update, context)

def register_all_command_handlers(application: Application):
    """Registers all command handlers with the PTB application."""
    logger.info("Registering command handlers...")

    # --- /start Command ---
    application.add_handler(CommandHandler("start", start_command_dispatcher))
    logger.info("Registered /start command dispatcher.")

    # --->>> RENAME AND UPDATE HANDLER REGISTRATION <<<---
    group_display_handler = get_group_display_conversation_handler()
    application.add_handler(group_display_handler)
    logger.info("Registered /display conversation handler.")
    # ----------------------------------------

    # --- Future Command Handlers ---
    # ... (keep existing comments) ...

    logger.info("All command handler registration complete.")