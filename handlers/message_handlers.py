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

from config import settings, group_config, persistent_config
from utils import helpers, error_handler, context_cache

logger = logging.getLogger(__name__)


# --- Helper function execute_send (remains the same) ---
async def execute_send(
    send_func, send_args: dict, semaphore: asyncio.Semaphore, log_prefix: str, message_id: int, operation_desc: str = "Send message"
):
    # ... (implementation remains the same) ...
    async with semaphore:
        current_chat_id = send_args.get("chat_id")
        if not current_chat_id:
            logger.error(f"{log_prefix}Missing chat_id in send_args. Cannot execute send.")
            return False

        max_retries = 1; retries = 0; success = False
        while retries <= max_retries:
            try:
                await send_func(**send_args)
                logger.info(f"{log_prefix}Successfully sent message to chat {current_chat_id}.")
                success = True
                break
            except ChatMigrated as cm_error:
                old_chat_id = current_chat_id; new_chat_id = cm_error.new_chat_id
                logger.warning(f"{log_prefix}Chat migrated from {old_chat_id} to {new_chat_id}. Updating config and retrying...")
                removed_old = await persistent_config.remove_target_group(old_chat_id)
                added_new = await persistent_config.add_target_group(new_chat_id)
                logger.info(f"{log_prefix}Persistent group update: removed {old_chat_id} ({removed_old}), added {new_chat_id} ({added_new}).")
                try:
                     if old_chat_id in group_config._group_settings:
                         mode_to_copy = group_config.get_group_mode(old_chat_id)
                         group_config.set_group_mode(new_chat_id, mode_to_copy)
                         del group_config._group_settings[old_chat_id]
                         logger.info(f"{log_prefix}Copied display mode '{mode_to_copy}' from {old_chat_id} to {new_chat_id}.")
                     else: logger.debug(f"{log_prefix}Old chat {old_chat_id} used default mode.")
                except Exception as config_update_err: logger.error(f"{log_prefix}Failed to update group_config for migration: {config_update_err}")
                current_chat_id = new_chat_id
                send_args['chat_id'] = current_chat_id
                retries += 1
                log_prefix = f"Msg {message_id}: Target {current_chat_id} (migrated): "
            except TelegramError as e:
                error_msg = str(e).lower(); log_level = logging.ERROR
                if any(term in error_msg for term in ["bot was blocked", "user is deactivated", "chat not found", "bot is not a member", "group chat was deactivated", "need administrator rights", "chat_write_forbidden", "have no rights to send"]): log_level = logging.WARNING
                logger.log(log_level, f"{log_prefix}Failed: {operation_desc} - {e}", exc_info=log_level >= logging.ERROR)
                break
            except Exception as e:
                logger.error(f"{log_prefix}Unexpected error during {operation_desc}: {e}", exc_info=True)
                break
        return success

# --- Telethon Message Handler Registration ---
def register_handlers(application: Application, client: TelegramClient, target_bot: Bot, semaphore: asyncio.Semaphore):
    """Registers the Telethon event handler for new messages."""

    @client.on(events.NewMessage(from_users=settings.SOURCE_BOT_IDENTIFIER))
    async def handle_new_message(event):
        """Processes new messages from the source bot."""
        current_target_groups = await persistent_config.load_target_groups()
        if not current_target_groups:
            logger.debug("No target groups configured. Skipping.")
            return

        context_cache.cleanup_cache()
        message = event.message
        message_id = message.id
        log_prefix = f"Msg {message_id}: "
        sender = await message.get_sender()
        sender_id = sender.id if sender else "Unknown"
        logger.info(f"{log_prefix}Received from source bot (ID: {sender_id})")

        # --- Basic Checks ---
        if not helpers.has_specific_button(message, settings.BUTTON_TEXT_TO_FIND):
            logger.debug(f"{log_prefix}Skipping: Missing '{settings.BUTTON_TEXT_TO_FIND}' button.")
            return
        try:
            bot_info = await target_bot.get_me()
            bot_username = bot_info.username
            if not bot_username: raise ValueError("Bot username is missing")
        except Exception as e:
            logger.error(f"{log_prefix}Could not get target bot info: {e}", exc_info=True)
            return

        # --- Extract Core Content ---
        original_text = message.text or ""
        media_type = helpers.get_telethon_media_type(message)
        tweet_url = helpers.extract_button_url(message, settings.BUTTON_TEXT_TO_FIND) # Keep original URL

        # ---> Step 1: Analyze Text Content <---
        action_type, username = helpers.extract_action_and_username(original_text)
        logger.info(f"{log_prefix}Analyzed text: Action='{action_type}', User='{username}'")

        # ---> Step 2: Prepare Common Data & Initial Cache <---
        context_id = uuid.uuid4().hex
        initial_cache_data = {'text': original_text, 'media_type': media_type, 'file_id': None}
        context_cache.add_to_cache(context_id, initial_cache_data) # File ID added later if needed
        deploy_deep_link = f"https://t.me/{bot_username}?start=deploy_{context_id}"
        logger.debug(f"{log_prefix}Generated deploy deep link: {deploy_deep_link}")

        # ---> Step 3: Categorize Targets & Determine Media Needs <---
        fxtwitter_targets = []; full_mode_targets = []
        for chat_id in current_target_groups:
            try:
                mode = group_config.get_group_mode(chat_id)
                if mode == group_config.MODE_FXTWITTER: fxtwitter_targets.append(chat_id)
                elif mode == group_config.MODE_FULL: full_mode_targets.append(chat_id)
                else: logger.warning(f"{log_prefix}Unknown mode '{mode}' for {chat_id}, using 'full'."); full_mode_targets.append(chat_id)
            except Exception as e: logger.error(f"{log_prefix}Error processing target {chat_id}: {e}", exc_info=True)

        needs_media_processing = bool(full_mode_targets and media_type)
        logger.debug(f"{log_prefix}Targets - FX: {len(fxtwitter_targets)}, Full: {len(full_mode_targets)}. Needs media: {needs_media_processing}")

        # ---> Step 4: Prepare Content Templates (Now uses analyzed data) <---

        # 4a. FXTwitter Content Template
        reply_markup_fx = None
        send_args_fx_template = None
        if fxtwitter_targets:
            fx_url_inline = helpers.create_fxtwitter_url(tweet_url) # URL for inline link
            fxtwitter_text = helpers.format_fxtwitter_message_html(action_type, username, fx_url_inline)
            if not fxtwitter_text:
                 logger.warning(f"{log_prefix}Failed to format FXTwitter text. Using fallback.")
                 fxtwitter_text = f"➡️ {html.escape(original_text[:100])}{'...' if len(original_text) > 100 else ''}" # Simple fallback

            keyboard_rows_fx = []
            if tweet_url: # Use ORIGINAL URL for button
                 keyboard_rows_fx.append([InlineKeyboardButton(settings.BUTTON_TEXT_TO_FIND, url=tweet_url)])
            keyboard_rows_fx.append([InlineKeyboardButton("\U0001F680 Deploy New Token", url=deploy_deep_link)])
            reply_markup_fx = InlineKeyboardMarkup(keyboard_rows_fx)

            send_args_fx_template = {'text': fxtwitter_text, 'reply_markup': reply_markup_fx, 'parse_mode': ParseMode.HTML}

        # 4b. Full Mode Content Template
        reply_markup_full = None
        base_caption_full = html.escape(original_text) # Use escaped original text as base caption
        if full_mode_targets:
            keyboard_rows_full = []
            if tweet_url: # Use ORIGINAL URL for button
                 keyboard_rows_full.append([InlineKeyboardButton(settings.BUTTON_TEXT_TO_FIND, url=tweet_url)])
            keyboard_rows_full.append([InlineKeyboardButton("\U0001F680 Deploy New Token", url=deploy_deep_link)])
            reply_markup_full = InlineKeyboardMarkup(keyboard_rows_full)

        # ---> Step 5: Process Media (Conditional) <---
        reusable_file_id = None
        media_content_bytes = None
        if needs_media_processing:
            logger.info(f"{log_prefix}Processing media ({media_type}) for {len(full_mode_targets)} full mode targets...")
            # ... (Media download logic remains the same) ...
            with error_handler.handle_errors("Media Download", message_id=message_id):
                media_content_bytes = await client.download_media(message, file=bytes)

            if media_content_bytes:
                first_full_target_id = full_mode_targets[0]
                logger.info(f"{log_prefix}Attempting initial upload of {media_type} to chat {first_full_target_id} to get file_id.")
                # ... (File ID generation logic remains the same) ...
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
                                # Update cache with file_id
                                updated_cache_data = context_cache.get_from_cache(context_id) or initial_cache_data # Get existing or start fresh
                                updated_cache_data['file_id'] = reusable_file_id
                                context_cache.add_to_cache(context_id, updated_cache_data) # Overwrite entry
                                logger.info(f"{log_prefix}Updated cache entry {context_id} with file_id.")
                            else: logger.warning(f"{log_prefix}Could not extract file_id from temp message.")
                            # Delete temporary message
                            try:
                                await target_bot.delete_message(chat_id=first_full_target_id, message_id=sent_message_for_file_id.message_id)
                                logger.debug(f"{log_prefix}Deleted temporary message for file_id gen.")
                            except Exception as del_err: logger.warning(f"{log_prefix}Could not delete temporary message: {del_err}")
                        else: logger.error(f"{log_prefix}Initial media upload returned None/False.")
                    else: logger.error(f"{log_prefix}Upload function {upload_func_name} not found.")
                else: logger.error(f"{log_prefix}Unsupported media type {media_type} for file_id gen.")
            else:
                logger.warning(f"{log_prefix}Media download failed. Full mode targets get text only.")
                media_type = None # Update effective media type

        # ---> Step 6: Create and Launch Tasks for All Targets <---
        all_tasks = []
        current_effective_media_type = media_type # Use potentially updated type

        for chat_id in current_target_groups:
            mode = group_config.get_group_mode(chat_id) # Get mode again for this specific target
            send_func = None
            send_args = {}
            target_log_prefix = f"{log_prefix}Target {chat_id} ({mode[:4].upper()}): "
            op_desc = f"Send message (mode: {mode})"

            try:
                if mode == group_config.MODE_FXTWITTER:
                    if send_args_fx_template:
                        send_func = target_bot.send_message
                        send_args = send_args_fx_template.copy()
                        send_args['chat_id'] = chat_id
                        op_desc = "Send FXTwitter message"
                    else:
                        logger.error(f"{target_log_prefix}FXTwitter template not prepared. Skipping.")
                        continue

                elif mode == group_config.MODE_FULL:
                    send_args_full = {'chat_id': chat_id, 'reply_markup': reply_markup_full}

                    if current_effective_media_type and (reusable_file_id or media_content_bytes):
                        send_info = helpers.get_ptb_send_func_and_arg(current_effective_media_type)
                        if send_info:
                            send_func_name, arg_name = send_info
                            send_func = getattr(target_bot, send_func_name, None)
                            if send_func:
                                if reusable_file_id: send_args_full[arg_name] = reusable_file_id
                                elif media_content_bytes: send_args_full[arg_name] = media_content_bytes
                                else: send_func = None # Should not happen here, but safety
                                if send_func:
                                     send_args_full['caption'] = base_caption_full
                                     send_args_full['parse_mode'] = ParseMode.HTML
                                     op_desc=f"Send full message ({current_effective_media_type})"
                            else: logger.error(f"{target_log_prefix}Media send func {send_func_name} not found. Fallback."); send_func = None
                        else: logger.error(f"{target_log_prefix}Unsupported media {current_effective_media_type}. Fallback."); send_func = None

                    if not send_func: # Fallback to text for full mode
                        send_func = target_bot.send_message
                        send_args_full['text'] = base_caption_full # Use the escaped original text
                        send_args_full['parse_mode'] = ParseMode.HTML
                        op_desc="Send full message (text fallback)"

                    send_args = send_args_full # Use the prepared args

                else: # Should not happen if categorization worked
                    logger.error(f"{target_log_prefix}Unhandled mode '{mode}'. Skipping.")
                    continue

                # Add task if function determined
                if send_func:
                    all_tasks.append(
                        asyncio.create_task(
                            execute_send(send_func, send_args, semaphore, target_log_prefix, message_id, op_desc)
                        )
                    )
                else:
                     logger.error(f"{target_log_prefix}Final check failed: send_func is None. Skipping task creation.")

            except Exception as task_prep_err:
                logger.error(f"{target_log_prefix}Error preparing task: {task_prep_err}", exc_info=True)


        # ---> Step 7: Gather All Tasks <---
        if all_tasks:
            logger.info(f"{log_prefix}Launching {len(all_tasks)} send tasks concurrently...")
            results = await asyncio.gather(*all_tasks, return_exceptions=True)
            success_count = sum(1 for r in results if isinstance(r, bool) and r is True)
            fail_count = len(results) - success_count
            for i, res in enumerate(results):
                 if isinstance(res, BaseException):
                     # Error already logged in execute_send, just count here
                     pass
            logger.info(f"{log_prefix}Finished sending. Tasks Succeeded: {success_count}, Tasks Failed: {fail_count}")
        else:
            logger.info(f"{log_prefix}No send tasks were created.")


    # --- End of register_handlers ---
    logger.info(f"Registered Telethon handler for messages from source: {settings.SOURCE_BOT_IDENTIFIER}")
    logger.info("Message handler registration complete (using dynamic groups and optimized sending).")