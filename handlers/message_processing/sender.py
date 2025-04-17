# handlers/message_processing/sender.py
import asyncio
import logging
from telegram import Bot
from telegram.error import TelegramError, ChatMigrated
from config import persistent_config, group_config
from utils.helpers import media_utils

# Import necessary types/classes from other processing modules
from .analyzer import MessageAnalysisResult
from .content_formatter import ContentPayload
from .media_handler import MediaResult

logger = logging.getLogger(__name__)

# --- execute_send function (Moved here, slightly adapted) ---
async def execute_send(
    send_func, send_args: dict, semaphore: asyncio.Semaphore, log_prefix: str, operation_desc: str = "Send message"
) -> bool:
    """
    Executes a single send operation with semaphore, retries, and error handling.
    Returns True on success, False on failure.
    """
    async with semaphore:
        current_chat_id = send_args.get("chat_id")
        if not current_chat_id:
            logger.error(f"{log_prefix}Missing chat_id in send_args. Cannot execute send.")
            return False

        max_retries = 1 # Allow one retry, e.g., after migration
        retries = 0
        success = False
        original_log_prefix = log_prefix # Keep original for logging

        while retries <= max_retries:
            try:
                # Ensure chat_id is correctly set for this attempt
                send_args['chat_id'] = current_chat_id
                log_prefix_attempt = f"{original_log_prefix}Target {current_chat_id}: " # Log with current target

                await send_func(**send_args)
                logger.info(f"{log_prefix_attempt}Successfully sent '{operation_desc}'.")
                success = True
                break # Exit loop on success

            except ChatMigrated as cm_error:
                old_chat_id = current_chat_id
                new_chat_id = cm_error.new_chat_id
                logger.warning(f"{log_prefix_attempt}Chat migrated from {old_chat_id} to {new_chat_id}. Updating config and retrying...")

                # Use persistent config to update the group list
                removed_old = await persistent_config.remove_target_group(old_chat_id)
                added_new = await persistent_config.add_target_group(new_chat_id)
                logger.info(f"{log_prefix_attempt}Persistent group update: removed {old_chat_id} ({removed_old}), added {new_chat_id} ({added_new}).")

                # Update in-memory group mode settings
                try:
                    # Check if old chat had a specific mode set
                    if old_chat_id in group_config._group_settings:
                        mode_to_copy = group_config.get_group_mode(old_chat_id)
                        # Set mode for new chat ID
                        group_config.set_group_mode(new_chat_id, mode_to_copy)
                        # Remove old chat ID from settings AFTER copying
                        del group_config._group_settings[old_chat_id]
                        logger.info(f"{log_prefix_attempt}Copied display mode '{mode_to_copy}' from {old_chat_id} to {new_chat_id}.")
                    else:
                        logger.debug(f"{log_prefix_attempt}Old chat {old_chat_id} used default mode, new chat {new_chat_id} will also use default.")
                except Exception as config_update_err:
                    logger.error(f"{log_prefix_attempt}Failed to update group_config display mode for migration: {config_update_err}")

                # Update chat_id for the retry
                current_chat_id = new_chat_id
                retries += 1 # Consume a retry attempt

            except TelegramError as e:
                error_msg = str(e).lower()
                # Determine log level based on error type
                log_level = logging.ERROR
                permanent_errors = ["bot was blocked", "user is deactivated", "chat not found",
                                    "bot is not a member", "group chat was deactivated",
                                    "need administrator rights", "chat_write_forbidden",
                                    "have no rights to send", "peer_id_invalid"]
                if any(term in error_msg for term in permanent_errors):
                    log_level = logging.WARNING # Treat as non-critical failure for this target
                    logger.log(log_level, f"{log_prefix_attempt}Failed '{operation_desc}' (Permanent Error): {e}. Removing target if applicable.")
                    # Optionally remove the group here if the error indicates removal is appropriate
                    if "bot is not a member" in error_msg or "bot was blocked" in error_msg or "chat not found" in error_msg or "group chat was deactivated" in error_msg:
                         await persistent_config.remove_target_group(current_chat_id)
                         # Also remove from in-memory settings if present
                         if current_chat_id in group_config._group_settings: del group_config._group_settings[current_chat_id]

                else:
                    # Log other TelegramErrors as ERROR
                    logger.log(log_level, f"{log_prefix_attempt}Failed '{operation_desc}': {e}", exc_info=True) # Include traceback

                # Break loop after TelegramError (no more retries needed)
                break
            except Exception as e:
                # Catch any other unexpected errors
                logger.error(f"{log_prefix_attempt}Unexpected error during '{operation_desc}': {e}", exc_info=True)
                # Break loop after unexpected error
                break

        return success


# --- NEW: Function to launch FXTwitter sends ---
def launch_fxtwitter_sends(
    target_bot: Bot,
    fxtwitter_payload: ContentPayload | None,
    fxtwitter_targets: list[int],
    semaphore: asyncio.Semaphore,
    log_prefix_send: str
) -> list[asyncio.Task]:
    """Creates and returns asyncio Tasks for sending FXTwitter messages."""
    tasks = []
    if not fxtwitter_targets or not fxtwitter_payload or not fxtwitter_payload.text:
        if fxtwitter_targets:
            logger.warning(f"{log_prefix_send}FXTwitter targets exist but no valid payload. Skipping FX sends.")
        return tasks # Return empty list

    logger.info(f"{log_prefix_send}Creating {len(fxtwitter_targets)} FXTwitter send tasks...")
    base_send_args = {
        'text': fxtwitter_payload.text,
        'reply_markup': fxtwitter_payload.reply_markup,
        'parse_mode': fxtwitter_payload.parse_mode,
        'disable_web_page_preview': False # Ensure preview is enabled
    }
    for chat_id in fxtwitter_targets:
        send_args_fx = base_send_args.copy()
        send_args_fx['chat_id'] = chat_id
        tasks.append(
            asyncio.create_task(
                execute_send(target_bot.send_message, send_args_fx, semaphore, log_prefix_send, "Send FXTwitter message")
            )
        )
    logger.debug(f"{log_prefix_send}Created {len(tasks)} FXTwitter tasks.")
    return tasks

# --- NEW: Function to launch Full Mode sends ---
def launch_full_mode_sends(
    target_bot: Bot,
    full_mode_payload: ContentPayload | None,
    media_result: MediaResult,
    full_mode_targets: list[int],
    semaphore: asyncio.Semaphore,
    log_prefix_send: str
) -> list[asyncio.Task]:
    """Creates and returns asyncio Tasks for sending Full Mode messages."""
    tasks = []
    if not full_mode_targets or not full_mode_payload:
         if full_mode_targets:
             logger.warning(f"{log_prefix_send}Full mode targets exist but no payload. Skipping Full sends.")
         return tasks

    logger.info(f"{log_prefix_send}Creating {len(full_mode_targets)} Full Mode send tasks...")
    send_func_full = None
    base_send_args_full = {
        'reply_markup': full_mode_payload.reply_markup,
        'parse_mode': full_mode_payload.parse_mode
    }
    op_desc_full = ""
    media_arg_name = None
    media_value = None

    # Determine send function and media argument based on MediaResult
    if media_result.media_type and (media_result.file_id or media_result.content_bytes):
        send_info = media_utils.get_ptb_send_func_and_arg(media_result.media_type)
        if send_info:
            send_func_name, arg_name = send_info
            send_func_full = getattr(target_bot, send_func_name, None)
            if send_func_full:
                media_arg_name = arg_name
                if media_result.file_id:
                    media_value = media_result.file_id
                    base_send_args_full[media_arg_name] = media_value
                    base_send_args_full['caption'] = full_mode_payload.caption
                    op_desc_full = f"Send full message ({media_result.media_type} via file_id)"
                elif media_result.content_bytes:
                    media_value = media_result.content_bytes # Keep as bytes for now
                    base_send_args_full[media_arg_name] = media_value # Set bytes here
                    base_send_args_full['caption'] = full_mode_payload.caption
                    op_desc_full = f"Send full message ({media_result.media_type} via upload)"
                else: send_func_full = None
            else: logger.error(f"{log_prefix_send}Media func '{send_func_name}' not found. Fallback."); send_func_full = None
        else: logger.error(f"{log_prefix_send}Unsupported media '{media_result.media_type}'. Fallback."); send_func_full = None
    else:
        logger.debug(f"{log_prefix_send}No media processed/available. Sending as text.")
        send_func_full = None

    # Setup for text if no media function determined or no media
    if not send_func_full:
        # Check if there's actually text content to send
        if full_mode_payload.text:
            send_func_full = target_bot.send_message
            base_send_args_full['text'] = full_mode_payload.text
            op_desc_full = "Send full message (text fallback)"
            base_send_args_full.pop('caption', None) # Clean up potential args
            if media_arg_name: base_send_args_full.pop(media_arg_name, None)
        else:
            # Neither media nor text available for full mode
            logger.error(f"{log_prefix_send}Cannot send full mode: No media and no text content available.")
            send_func_full = None # Ensure no tasks are created

    # Create tasks if a valid send function exists
    if send_func_full:
        for chat_id in full_mode_targets:
            send_args_full = base_send_args_full.copy()
            send_args_full['chat_id'] = chat_id
            # IMPORTANT: If sending bytes, ensure each task gets a fresh copy or readable stream
            if media_arg_name and isinstance(media_value, bytes):
                 # PTB usually handles bytes correctly, but copying ensures no race conditions
                 send_args_full[media_arg_name] = media_value[:] # Send a copy

            tasks.append(
                asyncio.create_task(
                    execute_send(send_func_full, send_args_full, semaphore, log_prefix_send, op_desc_full)
                )
            )
        logger.debug(f"{log_prefix_send}Created {len(tasks)} Full Mode tasks.")
    else:
         logger.error(f"{log_prefix_send}Could not determine any send function for full mode targets. No tasks created.")

    return tasks