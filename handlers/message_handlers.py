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
from telegram.constants import ParseMode, ChatType # Ensure ChatType is imported

from config import settings, group_config
from utils import helpers, error_handler, context_cache

logger = logging.getLogger(__name__)


# --- Helper function for executing the send operation ---
async def execute_send(
    send_func, send_args: dict, semaphore: asyncio.Semaphore, log_prefix: str, message_id: int, operation_desc: str = "Send message"
):
    """Acquires semaphore, executes send, handles ChatMigrated and logs."""
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
                logger.warning(f"{log_prefix}Chat migrated from {old_chat_id} to {new_chat_id}. Updating config (in memory) and retrying...")

                # Update global settings list (in memory)
                try:
                    settings.TARGET_CHAT_IDS = [int(cid) for cid in settings.TARGET_CHAT_IDS]
                    if old_chat_id in settings.TARGET_CHAT_IDS:
                        settings.TARGET_CHAT_IDS.remove(old_chat_id)
                        if new_chat_id not in settings.TARGET_CHAT_IDS:
                            settings.TARGET_CHAT_IDS.append(new_chat_id)
                        logger.info(f"{log_prefix}Updated settings.TARGET_CHAT_IDS (in memory): {settings.TARGET_CHAT_IDS}")
                    else:
                         logger.warning(f"{log_prefix}Old chat ID {old_chat_id} not found in settings.TARGET_CHAT_IDS for removal.")
                except Exception as list_update_err:
                    logger.error(f"{log_prefix}Failed to update settings.TARGET_CHAT_IDS list: {list_update_err}")

                # Update group_config (copy settings)
                try:
                    if old_chat_id in group_config._group_settings:
                        mode_to_copy = group_config.get_group_mode(old_chat_id)
                        group_config.set_group_mode(new_chat_id, mode_to_copy)
                        if old_chat_id in group_config._group_settings:
                            del group_config._group_settings[old_chat_id]
                        logger.info(f"{log_prefix}Copied display mode '{mode_to_copy}' from {old_chat_id} to {new_chat_id} in group_config.")
                except Exception as config_update_err:
                    logger.error(f"{log_prefix}Failed to update group_config for migration: {config_update_err}")

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
        context_cache.cleanup_cache()
        message = event.message
        message_id = message.id
        log_prefix = f"Msg {message_id}: "

        sender = await message.get_sender()
        sender_id = sender.id if sender else "Unknown"
        logger.info(f"{log_prefix}Received from source bot (ID: {sender_id})")

        # --- Essential Checks ---
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

        # --- Initial Content Extraction ---
        original_text = message.text or ""
        media_type = helpers.get_telethon_media_type(message)
        tweet_url = helpers.extract_button_url(message, settings.BUTTON_TEXT_TO_FIND)

        # --- Categorize Targets ---
        fxtwitter_targets = []
        full_mode_targets = []
        for chat_id_str in settings.TARGET_CHAT_IDS:
            try:
                chat_id = int(chat_id_str)
                mode = group_config.get_group_mode(chat_id)
                if mode == group_config.MODE_FXTWITTER:
                    fxtwitter_targets.append(chat_id)
                elif mode == group_config.MODE_FULL:
                    full_mode_targets.append(chat_id)
                else:
                    logger.warning(f"{log_prefix}Unknown mode '{mode}' configured for chat {chat_id}. Treating as 'full'.")
                    full_mode_targets.append(chat_id)
            except (ValueError, TypeError):
                logger.error(f"{log_prefix}Invalid non-integer chat ID found in TARGET_CHAT_IDS: '{chat_id_str}'. Skipping.")
                continue

        needs_media_processing = bool(full_mode_targets and media_type)
        logger.debug(f"{log_prefix}FXTwitter targets: {len(fxtwitter_targets)}, Full mode targets: {len(full_mode_targets)}, Needs media: {needs_media_processing}")

        # --- Prepare Deploy Link and Initial Cache ---
        context_id = uuid.uuid4().hex
        # Store minimal data initially. file_id will be added later if processed.
        initial_cache_data = {
            'text': original_text,
            'media_type': media_type,
            'file_id': None, # Will be updated after media processing if needed
        }
        context_cache.add_to_cache(context_id, initial_cache_data)
        deploy_deep_link = f"https://t.me/{bot_username}?start=deploy_{context_id}"
        logger.debug(f"{log_prefix}Generated deploy deep link: {deploy_deep_link}")

        # --- Prepare and Launch Tasks ---
        all_tasks = []

        # --- Phase 1: Send to FXTwitter Targets Immediately ---
        if fxtwitter_targets:
            logger.info(f"{log_prefix}Preparing {len(fxtwitter_targets)} FXTwitter messages...")
            # Prepare content once
            username = helpers.extract_username_from_text(original_text)
            fx_url = helpers.create_fxtwitter_url(tweet_url)
            formatted_text = helpers.format_fxtwitter_message_html(username, fx_url)
            send_text = formatted_text
            if not formatted_text:
                 logger.warning(f"{log_prefix}Failed to format FXTwitter message. Using original text for FXTwitter targets.")
                 send_text = html.escape(original_text if original_text else "(Content could not be processed)")

            # Prepare keyboard once
            keyboard_rows_fx = []
            button1_text_fx = settings.BUTTON_TEXT_TO_FIND
            button1_url_fx = fx_url if fx_url else tweet_url # Use FX url if available
            if button1_url_fx:
                 keyboard_rows_fx.append([InlineKeyboardButton(button1_text_fx, url=button1_url_fx)])
            keyboard_rows_fx.append([InlineKeyboardButton("\U0001F680 Deploy New Token", url=deploy_deep_link)])
            reply_markup_fx = InlineKeyboardMarkup(keyboard_rows_fx)

            # Create send args template
            send_args_fx_template = {
                'text': send_text,
                'reply_markup': reply_markup_fx,
                'parse_mode': ParseMode.HTML
            }

            # Create tasks
            for chat_id in fxtwitter_targets:
                target_log_prefix = f"{log_prefix}Target {chat_id} (FX): "
                send_args_fx = send_args_fx_template.copy()
                send_args_fx['chat_id'] = chat_id
                all_tasks.append(
                    asyncio.create_task(
                        execute_send(
                            target_bot.send_message,
                            send_args_fx,
                            semaphore,
                            target_log_prefix,
                            message_id,
                            operation_desc="Send FXTwitter message"
                        )
                    )
                )

        # --- Phase 2: Process Media (if needed) and Send to Full Mode Targets ---
        # This part runs sequentially after FXTwitter task creation, but the sends run concurrently via gather

        reusable_file_id = None
        media_content_bytes = None

        # 2a. Process Media
        if needs_media_processing:
            logger.info(f"{log_prefix}Processing media ({media_type}) for {len(full_mode_targets)} full mode targets...")
            # Download
            with error_handler.handle_errors("Media Download", message_id=message_id):
                media_content_bytes = await client.download_media(message, file=bytes)

            # Upload for file_id (only if download succeeded)
            if media_content_bytes:
                first_full_target_id = full_mode_targets[0] # Need one target to upload to
                logger.info(f"{log_prefix}Attempting initial upload of {media_type} to chat {first_full_target_id} to get file_id.")
                send_info = helpers.get_ptb_send_func_and_arg(media_type)
                if send_info:
                    upload_func_name, arg_name = send_info
                    upload_func = getattr(target_bot, upload_func_name, None)
                    if upload_func:
                        upload_args = {'chat_id': first_full_target_id, arg_name: media_content_bytes, 'caption': None, 'reply_markup': None}
                        sent_message_for_file_id = None
                        with error_handler.handle_errors(f"Initial media upload ({media_type})", chat_id=first_full_target_id):
                            sent_message_for_file_id = await upload_func(**upload_args)
                        if sent_message_for_file_id:
                            reusable_file_id = helpers.get_media_file_id(sent_message_for_file_id)
                            if reusable_file_id:
                                logger.info(f"{log_prefix}Obtained reusable file_id ({media_type})")
                                # Update cache ONLY if file_id was obtained
                                updated_cache_data = initial_cache_data.copy()
                                updated_cache_data['file_id'] = reusable_file_id
                                context_cache.add_to_cache(context_id, updated_cache_data) # Overwrite initial entry
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
                    else:
                        logger.error(f"{log_prefix}PTB function {upload_func_name} not found.")
                else:
                    logger.error(f"{log_prefix}Unsupported media type {media_type} for file_id gen.")
            else:
                logger.warning(f"{log_prefix}Media download failed or empty. Full mode targets will receive text only.")
                media_type = None # Ensure fallback to text
        elif full_mode_targets:
             logger.info(f"{log_prefix}Preparing {len(full_mode_targets)} full mode messages (text only)...")


        # 2b. Prepare and Launch Full Mode Tasks
        if full_mode_targets:
            # Prepare keyboard once (uses original tweet URL)
            keyboard_rows_full = []
            if tweet_url:
                 keyboard_rows_full.append([InlineKeyboardButton(settings.BUTTON_TEXT_TO_FIND, url=tweet_url)])
            keyboard_rows_full.append([InlineKeyboardButton("\U0001F680 Deploy New Token", url=deploy_deep_link)])
            reply_markup_full = InlineKeyboardMarkup(keyboard_rows_full)

            # Determine send function and args template
            send_func_full = None
            send_args_full_template = {}
            current_media_type = media_type # Use the potentially updated media_type

            if current_media_type and (reusable_file_id or media_content_bytes):
                send_info = helpers.get_ptb_send_func_and_arg(current_media_type)
                if send_info:
                    send_func_name, arg_name = send_info
                    send_func_full = getattr(target_bot, send_func_name, None)
                    if send_func_full:
                         if reusable_file_id:
                             send_args_full_template[arg_name] = reusable_file_id
                         else: # Must have bytes if we reached here
                             send_args_full_template[arg_name] = media_content_bytes
                         # Caption will be added per task if needed
                         send_args_full_template['caption'] = html.escape(original_text) # Set default caption
                         send_args_full_template['parse_mode'] = ParseMode.HTML # Assume caption needs HTML
                    else:
                         logger.error(f"{log_prefix}Send function {send_func_name} not found for full mode. Falling back to text.")
                         current_media_type = None # Force text fallback
                else:
                     logger.error(f"{log_prefix}Unsupported media type {current_media_type} for full mode. Falling back to text.")
                     current_media_type = None # Force text fallback

            if not current_media_type: # Text only or fallback
                 send_func_full = target_bot.send_message
                 send_args_full_template['text'] = html.escape(original_text if original_text else "(Content unavailable)")
                 send_args_full_template['parse_mode'] = ParseMode.HTML

            # Add common args template
            send_args_full_template['reply_markup'] = reply_markup_full

            # Create tasks for full mode targets
            if send_func_full:
                 for chat_id in full_mode_targets:
                    target_log_prefix = f"{log_prefix}Target {chat_id} (Full): "
                    send_args_full = send_args_full_template.copy()
                    send_args_full['chat_id'] = chat_id
                    # Note: caption/text is already in the template

                    all_tasks.append(
                        asyncio.create_task(
                            execute_send(
                                send_func_full,
                                send_args_full,
                                semaphore,
                                target_log_prefix,
                                message_id,
                                operation_desc=f"Send full message ({current_media_type or 'text'})"
                            )
                        )
                    )
            else:
                 logger.error(f"{log_prefix}Could not determine any send function for full mode targets. Skipping full mode sends.")


        # --- Gather all tasks ---
        if all_tasks:
            logger.info(f"{log_prefix}Waiting for {len(all_tasks)} send tasks to complete...")
            results = await asyncio.gather(*all_tasks, return_exceptions=True)
            # Log final results summary
            success_count = sum(1 for r in results if isinstance(r, bool) and r is True) # execute_send returns True on success
            fail_count = len(results) - success_count
            # Log individual errors if any exceptions were returned by gather
            for i, res in enumerate(results):
                 if isinstance(res, BaseException):
                     # Determine which task failed based on index (less precise than logging in execute_send)
                     logger.error(f"{log_prefix}Send task {i+1}/{len(all_tasks)} failed in gather: {res}", exc_info=isinstance(res, Exception))
            logger.info(f"{log_prefix}Finished sending to all targets. Tasks Succeeded: {success_count}, Tasks Failed: {fail_count}")
        else:
            logger.info(f"{log_prefix}No messages needed to be sent.")


    # --- End of handle_new_message ---

    logger.info(f"Registered Telethon handler for messages from source: {settings.SOURCE_BOT_IDENTIFIER}")
    logger.info("Message handler registration complete (using optimized sending logic).")
# --- End of register_handlers ---