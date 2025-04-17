# handlers/message_handlers.py
# -*- coding: utf-8 -*-
import asyncio
import logging
from telethon import events, TelegramClient
from telegram import Bot
from telegram.ext import Application

from config import settings, group_config, persistent_config
from utils import context_cache, error_handler # Keep error_handler if used elsewhere

from .message_processing import (
    analyze_message,
    format_content_for_targets,
    process_media_for_full_mode,
    # DELETE: send_to_targets, # Không cần import hàm này nữa
    launch_fxtwitter_sends,     # <--- IMPORT Launch function
    launch_full_mode_sends,     # <--- IMPORT Launch function
    MessageAnalysisResult,
    ContentPayload,
    MediaResult,
)

logger = logging.getLogger(__name__)

# --- Telethon Message Handler Registration ---
def register_handlers(application: Application, client: TelegramClient, target_bot: Bot, semaphore: asyncio.Semaphore):
    """Registers the Telethon event handler for new messages."""

    @client.on(events.NewMessage(from_users=settings.SOURCE_BOT_IDENTIFIER))
    async def handle_new_message(event):
        """Processes new messages from the source bot by orchestrating analysis, formatting, and sending."""
        message = event.message
        message_id = message.id
        log_prefix_base = f"Msg {message_id}: "

        # --- Initial Setup & Target Check ---
        current_target_groups = await persistent_config.load_target_groups()
        if not current_target_groups:
            logger.debug(f"{log_prefix_base}No target groups configured. Skipping.")
            return

        context_cache.cleanup_cache()

        # --- Step 1: Analyze Message ---
        analysis_result = await analyze_message(message, target_bot)
        if not analysis_result:
            logger.warning(f"{log_prefix_base}Message analysis failed or returned None. Skipping.")
            return
        log_prefix = analysis_result.log_prefix.replace("[Analyze]", "[Main]")

        # --- Step 1.5: Check Required Button ---
        if not analysis_result.has_required_button:
            logger.debug(f"{log_prefix}Skipping: Missing required button identified during analysis.")
            return

        # --- Step 2: Categorize Targets ---
        fxtwitter_targets = []
        full_mode_targets = []
        # ...(logic categorization giữ nguyên)...
        try:
             for chat_id in current_target_groups:
                 mode = group_config.get_group_mode(chat_id)
                 if mode == group_config.MODE_FXTWITTER:
                     fxtwitter_targets.append(chat_id)
                 elif mode == group_config.MODE_FULL:
                     full_mode_targets.append(chat_id)
                 else:
                     logger.warning(f"{log_prefix}Unknown mode '{mode}' for chat {chat_id}. Defaulting to 'full'.")
                     full_mode_targets.append(chat_id)
        except Exception as e:
             logger.error(f"{log_prefix}Error categorizing target groups: {e}", exc_info=True)
             return

        needs_fxtwitter = bool(fxtwitter_targets)
        needs_full_mode = bool(full_mode_targets)
        needs_media_processing = needs_full_mode and analysis_result.media_type is not None

        logger.debug(f"{log_prefix}Targets - FX: {len(fxtwitter_targets)}, Full: {len(full_mode_targets)}. Needs media: {needs_media_processing}")

        if not needs_fxtwitter and not needs_full_mode:
            logger.info(f"{log_prefix}No targets require processing for this message. Skipping.")
            return

        all_launched_tasks = [] # List to collect all tasks

        # --- Step 3: Format Content (Initial - For FX) ---
        # Format content early, we need fxtwitter_payload now
        fxtwitter_payload, full_mode_payload = format_content_for_targets(
            analysis_result,
            needs_fxtwitter,
            needs_full_mode
        )

        # --- Step 4: Launch FXTwitter Tasks IMMEDIATELY ---
        if needs_fxtwitter:
            log_prefix_send = log_prefix.replace("[Main]", "[Send]")
            fx_tasks = launch_fxtwitter_sends(
                target_bot,
                fxtwitter_payload,
                fxtwitter_targets,
                semaphore,
                log_prefix_send
            )
            all_launched_tasks.extend(fx_tasks)
            logger.info(f"{log_prefix}Launched {len(fx_tasks)} FXTwitter tasks.")

        # --- Step 5: Process Media (Conditional) ---
        media_result = MediaResult(media_type=None) # Default
        if needs_media_processing:
            # This await happens AFTER FX tasks are launched
            first_full_target_id = full_mode_targets[0] if full_mode_targets else None
            media_result = await process_media_for_full_mode(
                analysis_result,
                client,
                target_bot,
                first_full_target_id
            )
        elif needs_full_mode:
            logger.debug(f"{log_prefix}Full mode needed, but no media processing required.")

        # --- Step 6: Launch Full Mode Tasks ---
        if needs_full_mode:
            log_prefix_send = log_prefix.replace("[Main]", "[Send]")
            # We already have full_mode_payload from Step 3
            full_tasks = launch_full_mode_sends(
                target_bot,
                full_mode_payload, # Use the payload formatted earlier
                media_result,      # Pass the result from media processing
                full_mode_targets,
                semaphore,
                log_prefix_send
            )
            all_launched_tasks.extend(full_tasks)
            logger.info(f"{log_prefix}Launched {len(full_tasks)} Full Mode tasks.")


        # --- Step 7: Wait for All Launched Tasks ---
        if all_launched_tasks:
            log_prefix_wait = log_prefix.replace("[Main]", "[Wait]")
            logger.info(f"{log_prefix_wait}Waiting for {len(all_launched_tasks)} total send tasks to complete...")
            results = await asyncio.gather(*all_launched_tasks, return_exceptions=True)
            success_count = sum(1 for r in results if isinstance(r, bool) and r is True)
            fail_count = len(results) - success_count
            # Error details are logged within execute_send
            logger.info(f"{log_prefix_wait}Finished sending for Msg {message_id}. Tasks Succeeded: {success_count}, Tasks Failed: {fail_count}")
        else:
            logger.info(f"{log_prefix}No messages needed to be sent (no tasks created).")

        logger.debug(f"{log_prefix}Finished all processing for message {message_id}.")


    # --- End of register_handlers ---
    logger.info(f"Registered Telethon handler for messages from source: {settings.SOURCE_BOT_IDENTIFIER}")
    logger.info("Message handler registration complete (using modular processing with correct execution order).")