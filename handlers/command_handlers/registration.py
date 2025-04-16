# handlers/command_handlers/registration.py
# -*- coding: utf-8 -*-
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext, ConversationHandler

# Import handlers from submodules
from .start.default import handle_start_default
from .start.deep_link import handle_start_deep_link
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
    # Use a dispatcher to handle both cases (with/without args)
    application.add_handler(CommandHandler("start", start_command_dispatcher))
    logger.info("Registered /start command dispatcher.")

    # --- Future Command Handlers ---
    # Example: Register wallet commands (when created)
    # wallet_conv_handler = get_wallet_conversation_handler() # Assume this getter exists in wallet/__init__.py or similar
    # application.add_handler(wallet_conv_handler)
    # logger.info("Registered /wallet conversation handler.")

    # Example: Register deploy commands (when created)
    # deploy_conv_handler = get_deploy_conversation_handler() # Assume this getter exists in deploy/__init__.py or similar
    # application.add_handler(deploy_conv_handler)
    # logger.info("Registered /deploy conversation handler.")

    # Add other command handlers here as you create them...

    logger.info("All command handler registration complete.")