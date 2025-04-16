# handlers/message_handlers.py
# -*- coding: utf-8 -*-
import asyncio
import logging
import uuid
import html
import re
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
    # ... (Implementation is correct from previous step) ...
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
                         if old_chat_id in group_config._group_settings: del group_config._group_settings[old_chat_id] # Check before deleting
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

        # --- Basic Checks & Info Extraction ---
        if not helpers.has_specific_button(message, settings.BUTTON_TEXT_TO_FIND):
            logger.debug(f"{log_prefix}Skipping: Missing '{settings.BUTTON_TEXT_TO_FIND}' button.")
            return
        try:
            bot_info = await target_bot.get_me(); bot_username = bot_info.username
            if not bot_username: raise ValueError("Bot username missing")
        except Exception as e: logger.error(f"{log_prefix}Could not get bot info: {e}"); return

        original_text = message.text or ""
        media_type = helpers.get_telethon_media_type(message)
        tweet_url = helpers.extract_button_url(message, settings.BUTTON_TEXT_TO_FIND) # Original URL

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
                else: logger.warning(f"{log_prefix}Unknown mode '{mode}' for {chat_id}. Using 'full'."); full_mode_targets.append(chat_id)
            except Exception as e: logger.error(f"{log_prefix}Error processing target {chat_id}: {e}")

        needs_media_processing = bool(full_mode_targets and media_type)
        logger.debug(f"{log_prefix}Targets - FX: {len(fxtwitter_targets)}, Full: {len(full_mode_targets)}. Needs media: {needs_media_processing}")

        # ---> Step 4: Prepare Keyboards (Common Buttons) <---
        # FXTwitter Keyboard (Original tweet URL for button)
        keyboard_rows_fx = []
        if tweet_url: keyboard_rows_fx.append([InlineKeyboardButton(settings.BUTTON_TEXT_TO_FIND, url=tweet_url)])
        keyboard_rows_fx.append([InlineKeyboardButton("🚀 Deploy New Token", url=deploy_deep_link)]) # Using emoji from prev examples
        reply_markup_fx = InlineKeyboardMarkup(keyboard_rows_fx)

        # Full Mode Keyboard (Original tweet URL for button)
        keyboard_rows_full = []
        if tweet_url: keyboard_rows_full.append([InlineKeyboardButton(settings.BUTTON_TEXT_TO_FIND, url=tweet_url)])
        keyboard_rows_full.append([InlineKeyboardButton("🚀 Deploy New Token", url=deploy_deep_link)])
        reply_markup_full = InlineKeyboardMarkup(keyboard_rows_full)

        # ---> Step 5: Prepare Content Templates <---
        # 5a. FXTwitter Content
        send_args_fx_template = None
        if fxtwitter_targets:
            fx_url_inline = helpers.create_fxtwitter_url(tweet_url)
            fxtwitter_text = helpers.format_fxtwitter_message_html(action_type, username, fx_url_inline)
            if not fxtwitter_text:
                 logger.warning(f"{log_prefix}FXTwitter fallback to original text.")
                 fxtwitter_text = f"{helpers.get_action_emoji(None)} {html.escape(original_text[:100])}{'...' if len(original_text) > 100 else ''}"
            send_args_fx_template = {'text': fxtwitter_text, 'reply_markup': reply_markup_fx, 'parse_mode': ParseMode.HTML}

        # 5b. Full Mode Content (Header + Body)
        final_full_content = None
        if full_mode_targets:
            # Prepare Keyboard
            keyboard_rows_full = [];
            if tweet_url: keyboard_rows_full.append([InlineKeyboardButton(settings.BUTTON_TEXT_TO_FIND, url=tweet_url)])
            keyboard_rows_full.append([InlineKeyboardButton("🚀 Deploy New Token", url=deploy_deep_link)])
            reply_markup_full = InlineKeyboardMarkup(keyboard_rows_full)

            # Format the header
            formatted_header = helpers.format_full_mode_header_html(action_type, username, tweet_url)

            # Extract the message body raw
            body_start_index = -1
            if "\n\n" in original_text: body_start_index = original_text.find("\n\n") + 2
            elif "\n" in original_text: body_start_index = original_text.find("\n") + 1
            message_body_raw = original_text[body_start_index:].strip() if body_start_index != -1 else ""

            # Format body: Handle **RT** variations specifically using regex
            formatted_body = ""
            if action_type == "Retweet":
                # Regex to find optional **RT** (with optional spaces) at the beginning
                # Captures the part *after* the RT prefix
                rt_match = re.match(r"\**\s*RT\s*\**\s*(.*)", message_body_raw, re.IGNORECASE | re.DOTALL)
                if rt_match:
                    # Found the RT prefix, bold it and escape the rest
                    prefix = "<b>RT</b>"
                    rest_of_body = rt_match.group(1).strip() # Get content after RT
                    formatted_body = f"{prefix} {html.escape(rest_of_body)}"
                    logger.debug(f"{log_prefix}Applied specific RT formatting.")
                else:
                    # Retweet action, but didn't find the specific RT prefix pattern
                    logger.debug(f"{log_prefix}Retweet action, but RT prefix not found/matched. Escaping full body.")
                    formatted_body = html.escape(message_body_raw)
            else:
                # Not a Retweet, just escape the whole body
                formatted_body = html.escape(message_body_raw)

            # Combine header and formatted body
            if formatted_header:
                 final_full_content = f"{formatted_header}\n\n{formatted_body}".strip()
            else:
                 logger.warning(f"{log_prefix}Failed full mode header format. Using formatted body only.")
                 final_full_content = formatted_body

        # ---> Step 6: Launch FXTwitter Tasks (IMMEDIATELY) <---
        launched_tasks = [] # Collect all task objects here
        if fxtwitter_targets and send_args_fx_template:
            logger.info(f"{log_prefix}Creating and launching {len(fxtwitter_targets)} FXTwitter send tasks...")
            for chat_id in fxtwitter_targets:
                target_log_prefix = f"{log_prefix}Target {chat_id} (FX): "
                send_args_fx = send_args_fx_template.copy()
                send_args_fx['chat_id'] = chat_id
                launched_tasks.append(
                    asyncio.create_task(
                        execute_send(target_bot.send_message, send_args_fx, semaphore, target_log_prefix, message_id, "Send FXTwitter message")
                    )
                )
            logger.info(f"{log_prefix}Launched FXTwitter tasks.")
        elif fxtwitter_targets:
            logger.error(f"{log_prefix}FXTwitter targets exist but template is missing. Skipping FX sends.")


        # ---> Step 7: Process Media (Conditional) <---
        reusable_file_id = None
        media_content_bytes = None
        effective_media_type = media_type

        if needs_media_processing:
            logger.info(f"{log_prefix}Starting media processing ({effective_media_type})...")
            try:
                with error_handler.handle_errors("Media Download", message_id=message_id, raise_exception=True):
                    media_content_bytes = await client.download_media(message, file=bytes)

                if media_content_bytes and full_mode_targets:
                    first_full_target_id = full_mode_targets[0]
                    logger.info(f"{log_prefix}Attempting initial upload to {first_full_target_id} for file_id.")
                    send_info = helpers.get_ptb_send_func_and_arg(effective_media_type)
                    if send_info:
                        upload_func_name, arg_name = send_info
                        upload_func = getattr(target_bot, upload_func_name, None)
                        if upload_func:
                            upload_args = {'chat_id': first_full_target_id, arg_name: media_content_bytes}
                            sent_msg = None
                            with error_handler.handle_errors(f"Initial media upload ({effective_media_type})", chat_id=first_full_target_id, raise_exception=True):
                                sent_msg = await upload_func(**upload_args)
                            if sent_msg:
                                reusable_file_id = helpers.get_media_file_id(sent_msg)
                                if reusable_file_id:
                                    logger.info(f"{log_prefix}Obtained reusable file_id.")
                                    updated_cache_data = context_cache.get_from_cache(context_id) or initial_cache_data
                                    updated_cache_data['file_id'] = reusable_file_id
                                    context_cache.add_to_cache(context_id, updated_cache_data)
                                else: logger.warning(f"{log_prefix}Could not extract file_id.")
                                try: await target_bot.delete_message(first_full_target_id, sent_msg.message_id)
                                except Exception as del_err: logger.warning(f"{log_prefix}Failed delete temp msg: {del_err}")
                            else: logger.error(f"{log_prefix}Initial upload func returned None.")
                        else: logger.error(f"{log_prefix}Upload function {upload_func_name} not found.")
                    else: logger.error(f"{log_prefix}Unsupported media type {effective_media_type} for file_id gen.")
                else: # Download failed or empty
                    logger.warning(f"{log_prefix}Media download failed/empty. Full mode targets get text only.")
                    effective_media_type = None
            except Exception as media_err:
                 logger.error(f"{log_prefix}Media processing failed: {media_err}. Full mode targets get text fallback.", exc_info=True)
                 effective_media_type = None; reusable_file_id = None; media_content_bytes = None
            logger.info(f"{log_prefix}Finished media processing phase.")
        elif full_mode_targets:
             # Log if full mode targets exist but no media processing needed
             logger.info(f"{log_prefix}No media processing needed for full mode targets (original message was text-only).")


        # ---> Step 8: Prepare and Launch Full Mode Tasks <---
        if full_mode_targets:
            logger.info(f"{log_prefix}Creating {len(full_mode_targets)} Full Mode send tasks...")
            send_func_full = None
            base_send_args_full = {'reply_markup': reply_markup_full, 'parse_mode': ParseMode.HTML}
            op_desc_full = ""

            # Determine function based on *effective* media type
            if effective_media_type and (reusable_file_id or media_content_bytes):
                 send_info = helpers.get_ptb_send_func_and_arg(effective_media_type)
                 if send_info:
                     send_func_name, arg_name = send_info
                     send_func_full = getattr(target_bot, send_func_name, None)
                     if send_func_full:
                         base_send_args_full['caption'] = final_full_content # Use the formatted content
                         if reusable_file_id: base_send_args_full[arg_name] = reusable_file_id
                         elif media_content_bytes: base_send_args_full[arg_name] = media_content_bytes
                         else: send_func_full = None
                         if send_func_full: op_desc_full = f"Send full message ({effective_media_type})"
                     else: logger.error(f"{log_prefix}Media func {send_func_name} not found. Fallback."); send_func_full = None
                 else: logger.error(f"{log_prefix}Unsupported media {effective_media_type}. Fallback."); send_func_full = None

            # Setup for text if no media or media failed
            if not send_func_full:
                send_func_full = target_bot.send_message
                base_send_args_full['text'] = final_full_content # Use the formatted content
                op_desc_full = "Send full message (text fallback)"
                if 'caption' in base_send_args_full: del base_send_args_full['caption'] # Ensure no caption if sending text

            # Create tasks
            if send_func_full:
                 for chat_id in full_mode_targets:
                    target_log_prefix = f"{log_prefix}Target {chat_id} (Full): "
                    send_args_full = base_send_args_full.copy()
                    send_args_full['chat_id'] = chat_id
                    launched_tasks.append( # Add to the *same* task list
                        asyncio.create_task(
                            execute_send(send_func_full, send_args_full, semaphore, target_log_prefix, message_id, op_desc_full)
                        )
                    )
                 logger.info(f"{log_prefix}Launched Full Mode tasks.")
            else:
                 logger.error(f"{log_prefix}Could not determine any send function for full mode targets.")


        # ---> Step 9: Wait for All Launched Tasks <---
        if launched_tasks:
            logger.info(f"{log_prefix}Waiting for {len(launched_tasks)} send tasks to complete...")
            results = await asyncio.gather(*launched_tasks, return_exceptions=True)
            success_count = sum(1 for r in results if isinstance(r, bool) and r is True)
            fail_count = len(results) - success_count
            # Log individual errors from gather results
            for i, res in enumerate(results):
                 if isinstance(res, BaseException):
                     # Attempt to find corresponding chat_id (less reliable than logging in execute_send)
                     # This part is tricky as task order isn't guaranteed vs target list order if FX/Full mixed
                     # logger.error(f"{log_prefix}Send task {i+1}/{len(launched_tasks)} failed in gather: {res}", exc_info=isinstance(res, Exception))
                     # Log error without trying to guess chat_id, error is logged in execute_send anyway
                     logger.error(f"{log_prefix}A send task failed in gather: {res}", exc_info=isinstance(res, Exception))
            logger.info(f"{log_prefix}Finished sending. Tasks Succeeded: {success_count}, Tasks Failed: {fail_count}")
        else:
            logger.info(f"{log_prefix}No messages needed to be sent (no targets or tasks created).")


    # --- End of register_handlers ---
    logger.info(f"Registered Telethon handler for messages from source: {settings.SOURCE_BOT_IDENTIFIER}")
    logger.info("Message handler registration complete (using dynamic groups and optimized sending).")