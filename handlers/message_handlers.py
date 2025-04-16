# handlers/message_handlers.py
# -*- coding: utf-8 -*-
import asyncio
import logging
import uuid
from telethon import events, TelegramClient
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
# Removed CallbackContext, CallbackQueryHandler, CommandHandler from imports here
from telegram.ext import Application # Keep Application for type hinting if needed
from telegram.constants import ParseMode

from config import settings
# Removed tx_manager, wallet_manager imports
from utils import helpers, error_handler
from utils import context_cache # Use the cache module

# Removed state imports (CHOOSE_DEPLOY_NETWORK, etc.)

logger = logging.getLogger(__name__)

# --- Removed Callback Query Handler (handle_button_click) ---
# The 'addlp' button logic is no longer needed.

# --- Telethon Message Handler ---
def register_handlers(application: Application, client: TelegramClient, target_bot: Bot, semaphore: asyncio.Semaphore):
    """Registers the Telethon event handler for new messages."""

    @client.on(events.NewMessage(from_users=settings.SOURCE_BOT_IDENTIFIER))
    async def handle_new_message(event):
        """Processes new messages from the source bot."""
        context_cache.cleanup_cache() # Cleanup cache periodically

        message = event.message
        sender = await message.get_sender()
        sender_id = sender.id if sender else "Unknown"
        message_id = message.id
        logger.info(f"Received message ID {message_id} from source bot (ID: {sender_id})")

        # --- Essential Check: Filter based on button text ---
        if not helpers.has_specific_button(message, settings.BUTTON_TEXT_TO_FIND):
            logger.debug(f"Skipping message {message_id}: Missing '{settings.BUTTON_TEXT_TO_FIND}' button.")
            return # Exit early

        # --- Get Target Bot Info (needed for deep link) ---
        try:
            bot_info = await target_bot.get_me()
            bot_username = bot_info.username
            if not bot_username:
                logger.error("Target bot username is missing! Cannot create deep links.")
                return # Cannot proceed without username for deep link
        except Exception as e:
            logger.error(f"Could not get target bot info: {e}", exc_info=True)
            return

        # --- Extract Message Content ---
        text_content = message.text or ""
        media_type = helpers.get_telethon_media_type(message)
        tweet_url = helpers.extract_button_url(message, settings.BUTTON_TEXT_TO_FIND) # Keep original button URL
        final_caption = text_content # Base caption/text
        final_text = text_content
        reusable_file_id = None
        media_content_bytes = None # Store downloaded media here if needed later

        # --- Process Media (Download and Try to Get Reusable file_id) ---
        if media_type and message.media:
            logger.info(f"Message {message_id} has media type: {media_type}. Downloading...")
            with error_handler.handle_errors("Media Download", message_id=message_id):
                media_content_bytes = await client.download_media(message, file=bytes)

            if media_content_bytes and settings.TARGET_CHAT_IDS:
                # Try uploading to the first target to get a reusable file_id
                first_target_id = settings.TARGET_CHAT_IDS[0]
                logger.info(f"Attempting initial upload of {media_type} to chat {first_target_id} to get file_id.")
                send_info = helpers.get_ptb_send_func_and_arg(media_type)
                if send_info:
                    upload_func_name, arg_name = send_info
                    upload_func = getattr(target_bot, upload_func_name, None)
                    if upload_func:
                        # Note: Using final_caption here, which might be empty if message only had media
                        upload_args = {
                            'chat_id': first_target_id,
                            arg_name: media_content_bytes,
                            'caption': final_caption, # Use the text content as caption
                            'reply_markup': None # No buttons on this initial upload
                        }
                        with error_handler.handle_errors(f"Initial media upload ({media_type})", chat_id=first_target_id):
                            sent_message = await upload_func(**upload_args)
                            if sent_message:
                                reusable_file_id = helpers.get_media_file_id(sent_message)
                                if reusable_file_id:
                                    logger.info(f"Obtained reusable file_id ({media_type}) for message {message_id}")
                                else:
                                    logger.warning(f"Could not extract file_id from first sent message ({media_type}) for message {message_id}.")
                            else:
                                logger.error(f"Initial media upload function returned None/False for message {message_id}.")
                    else:
                        logger.error(f"PTB function {upload_func_name} not found for initial upload.")
                else:
                    logger.error(f"Unsupported media type for PTB file_id generation: {media_type}")
                # Decide if we keep media_content_bytes or discard after getting file_id
                # If file_id is obtained, we don't need the bytes anymore for other chats.
                # If file_id failed, we *might* need the bytes to send individually.
                if reusable_file_id:
                    media_content_bytes = None # Discard bytes if file_id is ready
            elif not media_content_bytes:
                logger.warning(f"Media download failed or empty for message {message_id}. Treating as text-only.")
                media_type = None # Reset media type if download failed

        # --- Store Context for Deep Link ---
        context_id = uuid.uuid4().hex
        # Store the content *before* adding our custom buttons
        cache_data = {
            'text': final_text, # Original text
            'media_type': media_type, # Original media type (or None)
            'file_id': reusable_file_id, # File ID if obtained, else None
        }
        context_cache.add_to_cache(context_id, cache_data)
        # Logging is handled inside add_to_cache

        # --- Create New Keyboard with Deep Link ---
        keyboard_rows = []
        # 1. Keep the original button if it exists
        if tweet_url:
            keyboard_rows.append([InlineKeyboardButton(settings.BUTTON_TEXT_TO_FIND, url=tweet_url)])

        # 2. Add the "Deploy New Token" button with deep link
        deploy_deep_link = f"https://t.me/{bot_username}?start=deploy_{context_id}"
        keyboard_rows.append([
            InlineKeyboardButton("\U0001F680 Deploy New Token", url=deploy_deep_link)
        ])
        logger.debug(f"Generated deploy deep link for message {message_id}: {deploy_deep_link}")

        # Removed AddLP button logic

        target_reply_markup = InlineKeyboardMarkup(keyboard_rows) if keyboard_rows else None

        # --- Forward Message to Targets with New Keyboard ---
        send_func = None
        send_args = {}
        operation_desc = ""

        # Use file_id if available for media messages
        if reusable_file_id and media_type:
            send_info = helpers.get_ptb_send_func_and_arg(media_type)
            if send_info:
                send_func_name, arg_name = send_info
                send_func = getattr(target_bot, send_func_name)
                send_args = {
                    arg_name: reusable_file_id,
                    'caption': final_caption, # Use original text as caption
                    'reply_markup': target_reply_markup
                }
                operation_desc = f"Forward media ({media_type}) using file_id for original msg {message_id}"
                logger.info(f"Prepared batch send using file_id for message {message_id}.")
            else:
                logger.error(f"Cannot forward media type {media_type} using file_id: No send info found.")
                # Fallback: Try sending as individual files if bytes are available, or just text
                if media_content_bytes:
                     # Fallback logic below will handle this if file_id failed but bytes exist
                     reusable_file_id = None # Ensure we hit the next condition
                     logger.warning(f"Falling back to individual media upload for message {message_id} due to file_id issue.")
                else:
                     # If no file_id and no bytes, send as text only
                     media_type = None
                     logger.warning(f"Falling back to text-only forwarding for message {message_id} due to file_id issue and no media bytes.")


        # Send media individually if file_id wasn't obtained but bytes exist
        if not reusable_file_id and media_content_bytes and media_type:
             send_info = helpers.get_ptb_send_func_and_arg(media_type)
             if send_info:
                 send_func_name, arg_name = send_info
                 send_func = getattr(target_bot, send_func_name)
                 send_args = {
                     arg_name: media_content_bytes, # Send the actual bytes
                     'caption': final_caption,
                     'reply_markup': target_reply_markup
                 }
                 operation_desc = f"Forward media ({media_type}) individually for original msg {message_id}"
                 logger.info(f"Prepared batch send using individual media upload for message {message_id}.")
             else:
                 logger.error(f"Cannot forward media type {media_type} individually: No send info found.")
                 # Fallback to text
                 media_type = None
                 logger.warning(f"Falling back to text-only forwarding for message {message_id} due to send info issue for individual upload.")


        # Send text message if no media (or media failed)
        if not media_type:
            # Ensure there's something to send (text or button)
            if final_text or target_reply_markup:
                send_func = target_bot.send_message
                # Use placeholder if only buttons exist
                send_args = {
                    'text': final_text if final_text else "(See attached actions)",
                    'reply_markup': target_reply_markup
                }
                operation_desc = f"Forward text message for original msg {message_id}"
                logger.info(f"Prepared batch send for text/button message {message_id}.")
            else:
                # This case should be rare if the original message had content or the 'View Tweet' button
                logger.warning(f"Message {message_id} has no text, media, or buttons to forward after processing.")
                send_func = None # Nothing to send


        # Execute the batch send if a function was determined
        if send_func and settings.TARGET_CHAT_IDS:
            logger.info(f"Executing batch: {operation_desc}")
            await helpers.process_batch(
                target_chat_ids=settings.TARGET_CHAT_IDS,
                func=send_func,
                args=send_args,
                semaphore=semaphore,
                operation_desc=operation_desc
            )
        elif not send_func:
             logger.error(f"Could not determine a send function for message {message_id}. Forwarding skipped.")
        elif not settings.TARGET_CHAT_IDS:
             logger.warning(f"No target chats configured. Forwarding skipped for message {message_id}.")


    logger.info(f"Registered Telethon handler for messages from source: {settings.SOURCE_BOT_IDENTIFIER}")
    # --- Removed PTB CallbackQueryHandler registration ---
    # logger.info("Registered PTB handler for button clicks (AddLP).") - Removed
    logger.info("Message handler registration complete.")