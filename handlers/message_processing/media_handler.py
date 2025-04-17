# handlers/message_processing/media_handler.py
import logging
from dataclasses import dataclass
from telethon import TelegramClient
from telegram import Bot

from .analyzer import MessageAnalysisResult
from utils import error_handler, context_cache
from utils.helpers import media_utils # Use specific helpers

logger = logging.getLogger(__name__)

@dataclass
class MediaResult:
    """Holds the results of media processing."""
    media_type: str | None # The effective media type after processing
    file_id: str | None = None
    content_bytes: bytes | None = None # Only if file_id couldn't be obtained


async def process_media_for_full_mode(
    analysis_result: MessageAnalysisResult,
    client: TelegramClient,
    target_bot: Bot,
    first_full_target_id: int | None
) -> MediaResult:
    """
    Downloads media, attempts to upload to get a reusable file_id,
    and updates the cache.
    Returns a MediaResult object.
    """
    media_type = analysis_result.media_type
    log_prefix = analysis_result.log_prefix.replace("[Analyze]", "[Media]")
    context_id = analysis_result.context_id
    message = analysis_result.original_message

    if not media_type:
        logger.debug(f"{log_prefix}No media detected in original message.")
        return MediaResult(media_type=None)

    logger.info(f"{log_prefix}Starting media processing ({media_type})...")
    media_content_bytes = None
    reusable_file_id = None

    try:
        # 1. Download Media
        with error_handler.handle_errors(f"Media Download ({media_type})", message_id=analysis_result.message_id, raise_exception=True):
            # Using file=bytes to get content directly
            media_content_bytes = await client.download_media(message, file=bytes)
            if not media_content_bytes:
                logger.warning(f"{log_prefix}Media download returned empty content.")
                # No point proceeding if download failed/empty
                return MediaResult(media_type=None) # Treat as no media


        # 2. Upload to get File ID (if possible and a target exists)
        if media_content_bytes and first_full_target_id:
            logger.info(f"{log_prefix}Attempting initial upload to chat {first_full_target_id} for file_id.")
            send_info = media_utils.get_ptb_send_func_and_arg(media_type)
            if send_info:
                upload_func_name, arg_name = send_info
                upload_func = getattr(target_bot, upload_func_name, None)
                if upload_func:
                    # Prepare arguments for the upload function
                    # Caption is not strictly needed here, but sending it might ensure the file is processed correctly
                    upload_args = {'chat_id': first_full_target_id, arg_name: media_content_bytes}
                    sent_msg = None
                    with error_handler.handle_errors(f"Initial media upload ({media_type})", chat_id=first_full_target_id, raise_exception=True):
                        sent_msg = await upload_func(**upload_args)

                    if sent_msg:
                        reusable_file_id = media_utils.get_media_file_id(sent_msg)
                        if reusable_file_id:
                            logger.info(f"{log_prefix}Obtained reusable file_id.")
                            # --- Update Cache with File ID ---
                            # Retrieve potentially updated cache data first
                            updated_cache_data = context_cache.get_from_cache(context_id) or analysis_result.initial_cache_data
                            updated_cache_data['file_id'] = reusable_file_id
                            context_cache.add_to_cache(context_id, updated_cache_data)
                            logger.debug(f"{log_prefix}Updated cache for {context_id} with file_id.")
                            # --- Delete Temporary Message ---
                            try:
                                await target_bot.delete_message(first_full_target_id, sent_msg.message_id)
                                logger.debug(f"{log_prefix}Deleted temporary upload message {sent_msg.message_id} from {first_full_target_id}.")
                            except Exception as del_err:
                                logger.warning(f"{log_prefix}Failed to delete temporary upload message: {del_err}")
                        else:
                            logger.warning(f"{log_prefix}Initial upload succeeded but could not extract file_id from sent message.")
                    else:
                        logger.error(f"{log_prefix}Initial upload function returned None or failed silently.")
                else:
                    logger.error(f"{log_prefix}PTB media upload function '{upload_func_name}' not found.")
            else:
                logger.error(f"{log_prefix}Unsupported media type '{media_type}' for PTB file_id generation.")
        elif not first_full_target_id:
             logger.warning(f"{log_prefix}Media downloaded, but no 'Full Mode' target available for initial upload to get file_id.")


    except Exception as media_err:
        logger.error(f"{log_prefix}Media processing failed: {media_err}. Full mode targets might get text fallback.", exc_info=True)
        # Reset media info on error
        media_type = None
        reusable_file_id = None
        media_content_bytes = None # Don't keep bytes if processing failed

    logger.info(f"{log_prefix}Finished media processing phase. Effective Type: {media_type}, File ID: {bool(reusable_file_id)}, Bytes: {bool(media_content_bytes)}")

    # Return result, prioritizing file_id
    if reusable_file_id:
        return MediaResult(media_type=media_type, file_id=reusable_file_id)
    elif media_content_bytes:
        # Only return bytes if file_id wasn't obtained (fallback)
        return MediaResult(media_type=media_type, content_bytes=media_content_bytes)
    else:
        # No media could be successfully processed
        return MediaResult(media_type=None)