# main.py
# -*- coding: utf-8 -*-
import asyncio
import logging
import signal # For graceful Ctrl+C handling
from telegram import BotCommand

# --- Configure logging BEFORE other imports ---
from utils import logging_config
logging_config.setup_logging()
# ---------------------------------------------

from telethon.errors import SessionPasswordNeededError
from telegram.ext import Application # Import Application from PTB

# Import necessary modules
from config import settings, persistent_config # <-- Import persistent_config
from telegram_clients import setup
from handlers import message_handlers
from handlers.command_handlers import registration as command_registration

logger = logging.getLogger(__name__)

# Global variables to manage client and application
telethon_client = None
ptb_application = None
shutdown_event = asyncio.Event() # Event to signal program stop

async def main():
    global telethon_client, ptb_application

    logger.info("--- Starting Telegram Bot Application ---")

    # Basic configuration check (Telegram and Bot settings)
    # Check for core Telethon/Bot settings first
    if not all([settings.API_ID, settings.API_HASH, settings.PHONE_NUMBER, settings.BOT_TOKEN, settings.SOURCE_BOT_IDENTIFIER]):
        logger.error("One or more critical settings are missing (API_ID, API_HASH, PHONE_NUMBER, BOT_TOKEN, SOURCE_BOT_IDENTIFIER). Please check your .env file.")
        return
    # Note: TARGET_CHAT_IDS_FROM_ENV is now optional

    # 1. Initialize clients & application
    try:
        telethon_client = setup.setup_telethon_client()
        ptb_application = Application.builder().token(settings.BOT_TOKEN).build()
        logger.info("Initialized Telethon client and PTB Application.")
        ptb_bot = ptb_application.bot # Get the bot instance

        # Initialize PTB Application (needed for get_me etc.)
        await ptb_application.initialize()
        logger.info("PTB Application initialized.")

        # Set bot commands
        try:
            logger.info("Setting bot commands list...")
            commands_to_set = [
                BotCommand("start", "Main menu"),
                BotCommand("display", "Configure group display mode"), # Updated command name
                # Add other commands here when needed
            ]
            await ptb_application.bot.set_my_commands(commands_to_set)
            logger.info("Successfully set bot commands list.")
        except Exception as cmd_err:
            logger.error(f"Failed to set bot commands: {cmd_err}", exc_info=True)

    except Exception as e:
        logger.critical(f"Failed to initialize Telegram clients/application: {e}", exc_info=True)
        return # Cannot continue if clients/app fail

    # ---> Load initial groups for logging and potential seeding <---
    try:
        initial_target_groups = await persistent_config.load_target_groups()
        if not initial_target_groups and settings.TARGET_CHAT_IDS_FROM_ENV:
            logger.info(f"No persistent groups file ({persistent_config.TARGET_GROUPS_FILE}) found, seeding with groups from .env")
            # Use list directly from settings as it's already processed
            initial_target_groups = settings.TARGET_CHAT_IDS_FROM_ENV
            # Save this initial list to the JSON file (needs lock)
            async with persistent_config._file_lock:
                await persistent_config._save_target_groups(set(initial_target_groups)) # Use internal save with lock
            # Reload to ensure format is correct and confirm save
            initial_target_groups = await persistent_config.load_target_groups()
            logger.info(f"Seeded and saved {len(initial_target_groups)} groups to {persistent_config.TARGET_GROUPS_FILE}")
        elif not initial_target_groups:
             logger.info(f"No persistent groups file found and no initial groups specified in .env.")
        else:
            logger.info(f"Loaded {len(initial_target_groups)} target groups initially from {persistent_config.TARGET_GROUPS_FILE}.")

    except Exception as load_err:
        logger.error(f"Error loading/seeding initial target groups: {load_err}", exc_info=True)
        # Decide if this is critical. Maybe continue with an empty list?
        initial_target_groups = []
    # -------------------------------------------------------------

    # 2. Create Semaphore
    semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_TASKS)
    logger.info(f"Concurrency limit set to: {settings.MAX_CONCURRENT_TASKS}")

    # 3. Register Handlers
    try:
        command_registration.register_all_command_handlers(ptb_application)
        message_handlers.register_handlers(ptb_application, telethon_client, ptb_bot, semaphore)
        logger.info("Successfully registered command and message handlers.")
    except Exception as e:
        logger.critical(f"Failed to register handlers: {e}", exc_info=True)
        return # Stop if handlers fail to register

    # 4. Run Telethon and PTB concurrently
    ptb_started = False # Flag to track if PTB updater started
    try:
        logger.info("Connecting Telethon client (User Account)...")
        async with telethon_client:
            await telethon_client.start(
                phone=settings.PHONE_NUMBER,
                password=lambda: input('Enter Telegram password (2FA): ') # Prompt for 2FA if needed
            )
            if not await telethon_client.is_user_authorized():
                logger.error("Telethon client authorization failed. Cannot proceed.")
                return

            logger.info("Telethon client authorized and connected successfully.")
            user = await telethon_client.get_me()
            logger.info(f"Telethon client running as user: {user.first_name} (ID: {user.id})")
            logger.info(f"Listening for messages from source bot ID: {settings.SOURCE_BOT_IDENTIFIER}...")

            # ---> Log dynamically loaded count just before starting <---
            try:
                # Load the latest list again right before the main loop starts
                current_dynamic_targets = await persistent_config.load_target_groups()
                targets_str = ', '.join(map(str, current_dynamic_targets[:5]))
                if len(current_dynamic_targets) > 5: targets_str += "..."
                logger.info(f"Will forward messages to {len(current_dynamic_targets)} dynamically managed target chat(s): [{targets_str}]")
            except Exception as log_load_err:
                 logger.error(f"Could not load dynamic target groups for final startup log: {log_load_err}")
            # ------------------------------------------------------------

            if settings.BUTTON_TEXT_TO_FIND:
                logger.info(f"Filtering for original button text: '{settings.BUTTON_TEXT_TO_FIND}'")
            logger.info(f"Generating deep links for bot: @{ptb_application.bot.username}")


            # Start PTB Application and Updater
            logger.info("Starting PTB Application...")
            await ptb_application.start() # Start the application logic

            logger.info("Starting PTB Updater for polling updates...")
            await ptb_application.updater.start_polling(
                 # ---> FIX: Add 'callback_query' AND 'chat_member' <---
                allowed_updates=["message", "callback_query", "chat_member"],
                drop_pending_updates=True
            )
            ptb_started = True
            logger.info(f"Bot is listening for commands as @{ptb_application.bot.username}")

            logger.info("--- Bot is fully running (Telethon Client + PTB Application) ---")
            await shutdown_event.wait() # Wait until shutdown signal
            logger.info("Shutdown signal received...")

    except SessionPasswordNeededError:
        logger.error("Telegram 2FA password is required. Please run the script interactively the first time.")
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received (handled by signal handler).")
        if not shutdown_event.is_set():
            shutdown_event.set()
    except Exception as e:
        logger.critical(f"Critical error during main runtime loop: {e}", exc_info=True)
    finally:
        # Graceful shutdown
        if ptb_application and ptb_started:
            try:
                logger.info("Stopping PTB Application...")
                if hasattr(ptb_application, 'updater') and ptb_application.updater.running:
                    logger.info("Stopping PTB Updater...")
                    await ptb_application.updater.stop()
                await ptb_application.stop()
                logger.info("Shutting down PTB Application...")
                await ptb_application.shutdown()
                logger.info("PTB Application stopped and shut down.")
            except Exception as ptb_stop_err:
                logger.error(f"Error stopping/shutting down PTB application: {ptb_stop_err}")

        # Telethon client disconnects automatically when `async with` block exits
        logger.info("Telethon client will disconnect automatically.")
        logger.info("--- Telegram Bot Application Stopped ---")


def signal_handler(sig, frame):
    """Handles termination signals (Ctrl+C, SIGTERM)."""
    signame = signal.Signals(sig).name
    logger.warning(f"Received signal {signame} ({sig}). Initiating graceful shutdown...")
    if not shutdown_event.is_set():
        shutdown_event.set()
    else:
        logger.warning("Shutdown already in progress. Please wait...")


if __name__ == '__main__':
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler) # Handle termination signal

    try:
        asyncio.run(main())
    except Exception as e:
        # Catch any unexpected errors at the top level
        logger.critical(f"Unhandled top-level exception: {e}", exc_info=True)
    finally:
        print("--- Script execution finished ---")