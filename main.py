# main.py
# -*- coding: utf-8 -*-
import asyncio
import logging
import signal # For graceful Ctrl+C handling

# --- Configure logging BEFORE other imports ---
from utils import logging_config
logging_config.setup_logging()
# ---------------------------------------------



from telethon.errors import SessionPasswordNeededError
from telegram.ext import Application # Import Application from PTB
from telegram import BotCommand

from config import settings
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
    # Removed blockchain-related checks
    if not all([settings.API_ID, settings.API_HASH, settings.PHONE_NUMBER, settings.BOT_TOKEN, settings.SOURCE_BOT_IDENTIFIER, settings.TARGET_CHAT_IDS]):
        logger.error("One or more critical settings are missing (API_ID, API_HASH, PHONE_NUMBER, BOT_TOKEN, SOURCE_BOT_IDENTIFIER, TARGET_CHAT_IDS). Please check your .env file.")
        return

    # 1. Initialize clients & application
    try:
        telethon_client = setup.setup_telethon_client()
        ptb_application = Application.builder().token(settings.BOT_TOKEN).build()
        logger.info("Initialized Telethon client and PTB Application.")
        ptb_bot = ptb_application.bot # Get the bot instance

        # Initialize PTB Application (needed for get_me etc.)
        await ptb_application.initialize()
        logger.info("PTB Application initialized.")

        # --->>> THÊM ĐOẠN CODE SET COMMANDS TẠI ĐÂY <<<---
        try:
            logger.info("Setting bot commands list...")
            commands_to_set = [
                BotCommand("start", "Main menu"),
                # Khi bạn thêm các command khác (ví dụ /wallet, /deploy),
                # hãy thêm chúng vào danh sách này:
                # BotCommand("wallet", "Manage wallets"),
                # BotCommand("deploy", "Deploy new token"),
                # BotCommand("addlp", "Add liquidity & Buy"),
            ]
            await ptb_application.bot.set_my_commands(commands_to_set)
            logger.info("Successfully set bot commands list.")
        except Exception as cmd_err:
            # Lỗi này thường ít xảy ra nếu token hợp lệ, nhưng vẫn nên bắt lỗi
            logger.error(f"Failed to set bot commands: {cmd_err}", exc_info=True)
        # --->>> KẾT THÚC ĐOẠN CODE SET COMMANDS <<<---

    except Exception as e:
        logger.critical(f"Failed to initialize Telegram clients/application: {e}", exc_info=True)
        return # Cannot continue if clients/app fail

    # 2. Create Semaphore (Still needed for batch sending in message_handlers)
    semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_TASKS)
    logger.info(f"Concurrency limit set to: {settings.MAX_CONCURRENT_TASKS}")

    # 3. Register Handlers
    try:
         # Register PTB command handlers using the new registration module
        command_registration.register_all_command_handlers(ptb_application)

        # Register Telethon event handlers (passing necessary components)
        # (Dòng này giữ nguyên)
        message_handlers.register_handlers(ptb_application, telethon_client, ptb_bot, semaphore)
        logger.info("Successfully registered command and message handlers.")
        # --- KẾT THÚC SỬA ĐỔI ---
    except Exception as e:
        logger.critical(f"Failed to register handlers: {e}", exc_info=True)
        return # Stop if handlers fail to register

    # 4. Run Telethon and PTB concurrently
    ptb_started = False # Flag to track if PTB updater started
    try:
        logger.info("Connecting Telethon client (User Account)...")
        async with telethon_client:
            # Start Telethon client (handles login/2FA)
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
            targets_str = ', '.join(map(str, settings.TARGET_CHAT_IDS[:5]))
            if len(settings.TARGET_CHAT_IDS) > 5: targets_str += "..."
            logger.info(f"Forwarding messages to {len(settings.TARGET_CHAT_IDS)} target chat(s): [{targets_str}]")
            if settings.BUTTON_TEXT_TO_FIND:
                logger.info(f"Filtering for original button text: '{settings.BUTTON_TEXT_TO_FIND}'")
            logger.info(f"Generating deep links for bot: @{ptb_application.bot.username}")


            # Start PTB Application and Updater
            logger.info("Starting PTB Application...")
            await ptb_application.start() # Start the application logic

            logger.info("Starting PTB Updater for polling updates...")
            await ptb_application.updater.start_polling(
                 # Only need message for /start command now
                allowed_updates=["message"], # Removed callback_query
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