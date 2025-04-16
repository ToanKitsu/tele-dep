# handlers/message_handlers.py
# -*- coding: utf-8 -*-
import asyncio
import logging
import uuid
import html

from telethon import events, TelegramClient
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError, ChatMigrated
from telegram.ext import Application
from telegram.constants import ParseMode, ChatType

# ---> REMOVE settings import if only used for TARGET_CHAT_IDS <---
# from config import settings
# ---> ADD persistent_config import <---
from config import settings, group_config, persistent_config # Keep settings for other values
from utils import helpers, error_handler, context_cache

logger = logging.getLogger(__name__)


# --- Helper function execute_send (remains the same) ---
async def execute_send(
    send_func, send_args: dict, semaphore: asyncio.Semaphore, log_prefix: str, message_id: int, operation_desc: str = "Send message"
):
    # ... (implementation remains the same, including ChatMigrated handling) ...
    async with semaphore:
        current_chat_id = send_args.get("chat_id")
        if not current_chat_id:
            logger.error(f"{log_prefix}Missing chat_id in send_args. Cannot execute send.")
            return False # Indicate failure

        max_retries = 1
        retries = 0
        success = False

        while retries <= max_retries:
            try:
                await send_func(**send_args)
                logger.info(f"{log_prefix}Successfully sent message to chat {current_chat_id}.")
                success = True
                break # Exit loop on success

            except ChatMigrated as cm_error:
                old_chat_id = current_chat_id
                new_chat_id = cm_error.new_chat_id
                logger.warning(f"{log_prefix}Chat migrated from {old_chat_id} to {new_chat_id}. Updating persistent config and retrying...")

                # ---> Update Persistent Config on Migration <---
                removed_old = await persistent_config.remove_target_group(old_chat_id)
                added_new = await persistent_config.add_target_group(new_chat_id)
                logger.info(f"{log_prefix}Persistent group update: removed {old_chat_id} ({removed_old}), added {new_chat_id} ({added_new}).")

                # Update group_config (copy display mode settings)
                try:
                     # Check if the old ID had specific settings before removing
                     if old_chat_id in group_config._group_settings:
                         mode_to_copy = group_config.get_group_mode(old_chat_id)
                         group_config.set_group_mode(new_chat_id, mode_to_copy)
                         # Remove old entry from display config
                         del group_config._group_settings[old_chat_id]
                         logger.info(f"{log_prefix}Copied display mode '{mode_to_copy}' from {old_chat_id} to {new_chat_id} in group_config.")
                     else:
                         # If old group used default 'full', new one will also use default
                         logger.debug(f"{log_prefix}Old chat {old_chat_id} used default mode; new chat {new_chat_id} will inherit default.")

                except Exception as config_update_err:
                     logger.error(f"{log_prefix}Failed to update group_config (display mode) for migration: {config_update_err}")

                # Update chat_id for the retry
                current_chat_id = new_chat_id
                send_args['chat_id'] = current_chat_id
                retries += 1
                log_prefix = f"Msg {message_id}: Target {current_chat_id} (migrated): " # Update log prefix

            except TelegramError as e:
                error_msg = str(e).lower()
                log_level = logging.ERROR
                if any(term in error_msg for term in ["bot was blocked", "user is deactivated", "chat not found", "bot is not a member", "group chat was deactivated", "need administrator rights", "chat_write_forbidden", "have no rights to send"]):
                    log_level = logging.WARNING
                logger.log(log_level, f"{log_prefix}Failed: {operation_desc} - {e}", exc_info=log_level >= logging.ERROR)
                break # Don't retry on these errors
            except Exception as e:
                logger.error(f"{log_prefix}Unexpected error during {operation_desc}: {e}", exc_info=True)
                break # Don't retry on unknown errors

        return success


# --- Telethon Message Handler Registration ---
def register_handlers(application: Application, client: TelegramClient, target_bot: Bot, semaphore: asyncio.Semaphore):
    """Registers the Telethon event handler for new messages."""

    @client.on(events.NewMessage(from_users=settings.SOURCE_BOT_IDENTIFIER))
    async def handle_new_message(event):
        """Processes new messages from the source bot."""
        # ---> Load target groups dynamically <---
        current_target_groups = await persistent_config.load_target_groups()
        if not current_target_groups:
            logger.debug("No target groups configured in persistent storage. Skipping message processing.")
            return
        # ------------------------------------

        context_cache.cleanup_cache()
        message = event.message
        message_id = message.id
        log_prefix = f"Msg {message_id}: "

        sender = await message.get_sender()
        sender_id = sender.id if sender else "Unknown"
        logger.info(f"{log_prefix}Received from source bot (ID: {sender_id})")

        # Essential Checks (Button, Bot Info)
        if not helpers.has_specific_button(message, settings.BUTTON_TEXT_TO_FIND):
            logger.debug(f"{log_prefix}Skipping: Missing '{settings.BUTTON_TEXT_TO_FIND}' button.")
            return
        try:
            bot_info = await target_bot.get_me()
            bot_username = bot_info.username
            if not bot_username:
                logger.error(f"{log_prefix}Target bot username is missing! Cannot create deep links.")
                return
        except Exception as e:
            logger.error(f"{log_prefix}Could not get target bot info: {e}", exc_info=True)
            return

        # Initial Content Extraction
        original_text = message.text or ""
        media_type = helpers.get_telethon_media_type(message)
        tweet_url = helpers.extract_button_url(message, settings.BUTTON_TEXT_TO_FIND)

        # ---> Categorize Targets based on the loaded dynamic list <---
        fxtwitter_targets = []
        full_mode_targets = []
        for chat_id in current_target_groups: # Iterate through loaded list
            try:
                # chat_id is already int from load_target_groups
                mode = group_config.get_group_mode(chat_id)
                if mode == group_config.MODE_FXTWITTER:
                    fxtwitter_targets.append(chat_id)
                elif mode == group_config.MODE_FULL:
                    full_mode_targets.append(chat_id)
                else:
                    logger.warning(f"{log_prefix}Unknown mode '{mode}' configured for chat {chat_id}. Treating as 'full'.")
                    full_mode_targets.append(chat_id)
            except Exception as e: # Catch potential errors during mode lookup for a specific ID
                 logger.error(f"{log_prefix}Error processing target chat ID {chat_id}: {e}", exc_info=True)
                 continue
        # ---------------------------------------------------------

        needs_media_processing = bool(full_mode_targets and media_type)
        logger.debug(f"{log_prefix}FXTwitter targets: {len(fxtwitter_targets)}, Full mode targets: {len(full_mode_targets)}, Needs media: {needs_media_processing}")

        # Prepare Deploy Link and Initial Cache
        context_id = uuid.uuid4().hex
        initial_cache_data = {'text': original_text, 'media_type': media_type, 'file_id': None}
        context_cache.add_to_cache(context_id, initial_cache_data)
        deploy_deep_link = f"https://t.me/{bot_username}?start=deploy_{context_id}"
        logger.debug(f"{log_prefix}Generated deploy deep link: {deploy_deep_link}")

        all_tasks = []

        # --- Phase 1: Send to FXTwitter Targets Immediately ---
        if fxtwitter_targets:
            # ... (FXTwitter message preparation logic remains the same) ...
            username = helpers.extract_username_from_text(original_text)
            fx_url = helpers.create_fxtwitter_url(tweet_url)
            formatted_text = helpers.format_fxtwitter_message_html(username, fx_url)
            send_text = formatted_text or html.escape(original_text if original_text else "(Content unavailable)")
            if not formatted_text:
                 logger.warning(f"{log_prefix}FXTwitter fallback to original text for targets: {fxtwitter_targets}")

            keyboard_rows_fx = []
            button1_text_fx = settings.BUTTON_TEXT_TO_FIND
            button1_url_fx = fx_url if fx_url else tweet_url
            if button1_url_fx:
                 keyboard_rows_fx.append([InlineKeyboardButton(button1_text_fx, url=button1_url_fx)])
            keyboard_rows_fx.append([InlineKeyboardButton("\U0001F680 Deploy New Token", url=deploy_deep_link)])
            reply_markup_fx = InlineKeyboardMarkup(keyboard_rows_fx)

            send_args_fx_template = {'text': send_text, 'reply_markup': reply_markup_fx, 'parse_mode': ParseMode.HTML}

            for chat_id in fxtwitter_targets:
                target_log_prefix = f"{log_prefix}Target {chat_id} (FX): "
                send_args_fx = send_args_fx_template.copy()
                send_args_fx['chat_id'] = chat_id
                all_tasks.append(
                    asyncio.create_task(
                        execute_send(target_bot.send_message, send_args_fx, semaphore, target_log_prefix, message_id, "Send FXTwitter message")
                    )
                )

        # --- Phase 2: Process Media (if needed) and Send to Full Mode Targets ---
        reusable_file_id = None
        media_content_bytes = None
        if needs_media_processing:
            # ... (Media processing logic remains the same, including cache update) ...
            logger.info(f"{log_prefix}Processing media ({media_type}) for {len(full_mode_targets)} full mode targets...")
            with error_handler.handle_errors("Media Download", message_id=message_id):
                media_content_bytes = await client.download_media(message, file=bytes)
            if media_content_bytes:
                first_full_target_id = full_mode_targets[0]
                logger.info(f"{log_prefix}Attempting initial upload of {media_type} to chat {first_full_target_id} to get file_id.")
                # ... (rest of the file_id generation logic) ...
                send_info = helpers.get_ptb_send_func_and_arg(media_type)
                if send_info:
                    upload_func_name, arg_name = send_info
                    upload_func = getattr(target_bot, upload_func_name, None)
                    if upload_func:
                        # ... (upload and get file_id) ...
                        upload_args = {'chat_id': first_full_target_id, arg_name: media_content_bytes, 'caption': None, 'reply_markup': None}
                        sent_message_for_file_id = None
                        with error_handler.handle_errors(f"Initial media upload ({media_type})", chat_id=first_full_target_id):
                            sent_message_for_file_id = await upload_func(**upload_args)
                        if sent_message_for_file_id:
                            reusable_file_id = helpers.get_media_file_id(sent_message_for_file_id)
                            if reusable_file_id:
                                logger.info(f"{log_prefix}Obtained reusable file_id ({media_type})")
                                # Update cache with file_id
                                updated_cache_data = initial_cache_data.copy()
                                updated_cache_data['file_id'] = reusable_file_id
                                context_cache.add_to_cache(context_id, updated_cache_data)
                                logger.info(f"{log_prefix}Updated cache entry {context_id} with file_id.")
                            else:
                                logger.warning(f"{log_prefix}Could not extract file_id from first sent message ({media_type}).")
                            # Delete temporary message
                            try:
                                await target_bot.delete_message(chat_id=first_full_target_id, message_id=sent_message_for_file_id.message_id)
                                logger.debug(f"{log_prefix}Deleted temporary message for file_id gen.")
                            except Exception as del_err:
                                logger.warning(f"{log_prefix}Could not delete temporary message: {del_err}")
                        else:
                            logger.error(f"{log_prefix}Initial media upload function returned None/False.")
                    # ... (handle upload_func not found) ...
                # ... (handle send_info not found) ...
            else:
                logger.warning(f"{log_prefix}Media download failed or empty. Full mode targets will receive text only.")
                media_type = None # Ensure fallback to text for full mode tasks preparation below

        # Prepare and Launch Full Mode Tasks
        if full_mode_targets:
            # ... (Full mode message preparation logic remains the same) ...
            keyboard_rows_full = []
            if tweet_url:
                 keyboard_rows_full.append([InlineKeyboardButton(settings.BUTTON_TEXT_TO_FIND, url=tweet_url)])
            keyboard_rows_full.append([InlineKeyboardButton("\U0001F680 Deploy New Token", url=deploy_deep_link)])
            reply_markup_full = InlineKeyboardMarkup(keyboard_rows_full)

            send_func_full = None
            send_args_full_template = {}
            current_media_type = media_type # Use potentially updated type

            if current_media_type and (reusable_file_id or media_content_bytes):
                # ... (determine media send func and args) ...
                send_info = helpers.get_ptb_send_func_and_arg(current_media_type)
                if send_info:
                    send_func_name, arg_name = send_info
                    send_func_full = getattr(target_bot, send_func_name, None)
                    if send_func_full:
                         if reusable_file_id:
                             send_args_full_template[arg_name] = reusable_file_id
                         elif media_content_bytes: # Check explicitly for bytes here
                             send_args_full_template[arg_name] = media_content_bytes
                         else: # Should not happen if current_media_type is set, but safety check
                             logger.error(f"{log_prefix}Media type {current_media_type} detected but no file_id or bytes available. Forcing text.")
                             current_media_type = None # Force text
                         if current_media_type: # Add caption only if still sending media
                            send_args_full_template['caption'] = html.escape(original_text)
                            send_args_full_template['parse_mode'] = ParseMode.HTML
                    else:
                         logger.error(f"{log_prefix}Send function {send_func_name} not found. Falling back to text.")
                         current_media_type = None
                else:
                     logger.error(f"{log_prefix}Unsupported media type {current_media_type}. Falling back to text.")
                     current_media_type = None

            if not current_media_type: # Text only or fallback
                 send_func_full = target_bot.send_message
                 send_args_full_template['text'] = html.escape(original_text if original_text else "(Content unavailable)")
                 send_args_full_template['parse_mode'] = ParseMode.HTML

            send_args_full_template['reply_markup'] = reply_markup_full

            if send_func_full:
                 for chat_id in full_mode_targets:
                    target_log_prefix = f"{log_prefix}Target {chat_id} (Full): "
                    send_args_full = send_args_full_template.copy()
                    send_args_full['chat_id'] = chat_id
                    all_tasks.append(
                        asyncio.create_task(
                            execute_send(send_func_full, send_args_full, semaphore, target_log_prefix, message_id, f"Send full message ({current_media_type or 'text'})")
                        )
                    )
            else:
                 logger.error(f"{log_prefix}Could not determine any send function for full mode targets.")


        # Gather all tasks
        if all_tasks:
            logger.info(f"{log_prefix}Waiting for {len(all_tasks)} send tasks to complete...")
            results = await asyncio.gather(*all_tasks, return_exceptions=True)
            # ... (logging results remains the same) ...
            success_count = sum(1 for r in results if isinstance(r, bool) and r is True)
            fail_count = len(results) - success_count
            for i, res in enumerate(results):
                 if isinstance(res, BaseException):
                     logger.error(f"{log_prefix}Send task {i+1}/{len(all_tasks)} failed in gather: {res}", exc_info=isinstance(res, Exception))
            logger.info(f"{log_prefix}Finished sending to all targets. Tasks Succeeded: {success_count}, Tasks Failed: {fail_count}")
        else:
            logger.info(f"{log_prefix}No messages needed to be sent.")


    # --- End of register_handlers ---
    logger.info(f"Registered Telethon handler for messages from source: {settings.SOURCE_BOT_IDENTIFIER}")
    logger.info("Message handler registration complete (using dynamic groups and optimized sending).") # Updated log message