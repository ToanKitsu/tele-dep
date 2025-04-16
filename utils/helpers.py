# -*- coding: utf-8 -*-
import asyncio
import logging
from telethon.tl.types import KeyboardButtonUrl, ReplyInlineMarkup, MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage
from telegram import InlineKeyboardButton, InlineKeyboardMarkup # Từ python-telegram-bot

logger = logging.getLogger(__name__)

# --- Media Type Definitions ---
MEDIA_PHOTO = 'photo'
MEDIA_VIDEO = 'video'
MEDIA_DOCUMENT = 'document'
MEDIA_AUDIO = 'audio'
MEDIA_VOICE = 'voice'
MEDIA_STICKER = 'sticker'
MEDIA_ANIMATION = 'animation' # GIFs gửi dưới dạng document thường là animation

# --- Media Handling ---
# Ánh xạ loại media Telethon sang chuỗi định danh của chúng ta
def get_telethon_media_type(message):
    """Xác định loại media từ tin nhắn Telethon."""
    if message.photo:
        return MEDIA_PHOTO
    elif message.video:
        return MEDIA_VIDEO
    # Telethon coi GIF là document có mime_type 'image/gif' hoặc video/mp4
    elif message.document:
        mime_type = getattr(message.document, 'mime_type', '').lower()
        if mime_type == 'image/gif' or getattr(message.document.attributes[-1], 'is_animated', False):
             return MEDIA_ANIMATION # Hoặc MEDIA_DOCUMENT tùy logic xử lý GIF
        elif 'audio' in mime_type:
             return MEDIA_AUDIO
        elif 'voice' in mime_type:
             return MEDIA_VOICE
        elif 'sticker' in mime_type:
            return MEDIA_STICKER
        else:
            return MEDIA_DOCUMENT # Các loại file khác
    elif message.audio: # Trường hợp audio riêng biệt (ít gặp hơn document)
        return MEDIA_AUDIO
    elif message.voice:
        return MEDIA_VOICE
    elif message.sticker:
        return MEDIA_STICKER
    # Thêm các loại media khác nếu cần (game, poll, location,...)
    return None

# Ánh xạ loại media sang hàm gửi của python-telegram-bot và tên tham số file_id/input_media
# Lưu ý: tên tham số có thể khác nhau (photo, video, document, audio, voice, animation, sticker)
MEDIA_SEND_INFO = {
    MEDIA_PHOTO: ('send_photo', 'photo'),
    MEDIA_VIDEO: ('send_video', 'video'),
    MEDIA_DOCUMENT: ('send_document', 'document'),
    MEDIA_AUDIO: ('send_audio', 'audio'),
    MEDIA_VOICE: ('send_voice', 'voice'),
    MEDIA_ANIMATION: ('send_animation', 'animation'),
    MEDIA_STICKER: ('send_sticker', 'sticker'),
}

def get_ptb_send_func_and_arg(media_type):
    """Lấy hàm gửi và tên tham số media cho python-telegram-bot."""
    return MEDIA_SEND_INFO.get(media_type)

def get_media_file_id(ptb_message):
    """Trích xuất file_id từ tin nhắn đã gửi bằng python-telegram-bot."""
    if ptb_message.photo:
        return ptb_message.photo[-1].file_id # Lấy ảnh chất lượng cao nhất
    elif ptb_message.video:
        return ptb_message.video.file_id
    elif ptb_message.document:
        return ptb_message.document.file_id
    elif ptb_message.audio:
        return ptb_message.audio.file_id
    elif ptb_message.voice:
        return ptb_message.voice.file_id
    elif ptb_message.animation:
        return ptb_message.animation.file_id
    elif ptb_message.sticker:
        return ptb_message.sticker.file_id
    return None

# --- Markup Handling ---
def extract_button_url(message, button_text_to_find):
    """Trích xuất URL từ nút inline cụ thể trong tin nhắn Telethon."""
    if not message.reply_markup or not isinstance(message.reply_markup, ReplyInlineMarkup):
        return None

    for row in message.reply_markup.rows:
        for btn in row.buttons:
            if isinstance(btn, KeyboardButtonUrl) and btn.text == button_text_to_find:
                return btn.url
    return None

def create_ptb_inline_markup(button_text, button_url):
    """Tạo InlineKeyboardMarkup cho python-telegram-bot từ text và url."""
    if not button_text or not button_url:
        return None
    try:
        button = InlineKeyboardButton(text=button_text, url=button_url)
        return InlineKeyboardMarkup([[button]])
    except Exception as e:
        logger.error(f"Error creating InlineKeyboardMarkup: {e}")
        return None

def has_specific_button(message, button_text_to_find):
    """Kiểm tra tin nhắn Telethon có nút inline với text cụ thể không."""
    if not message.reply_markup or not isinstance(message.reply_markup, ReplyInlineMarkup):
        return False

    for row in message.reply_markup.rows:
        for btn in row.buttons:
            # Chỉ cần kiểm tra sự tồn tại của nút
            if isinstance(btn, KeyboardButtonUrl) and btn.text == button_text_to_find:
                return True
    return False

# --- Batch Processing ---
async def process_batch(target_chat_ids, func, args, semaphore, operation_desc="task"):
    """Gửi tin nhắn hàng loạt với giới hạn concurrency."""
    async def send_with_limit(chat_id):
        async with semaphore:
            # logger.debug(f"Attempting to {operation_desc} for chat {chat_id}")
            try:
                # Truyền chat_id như là tham số đầu tiên hoặc qua 'chat_id' key
                if 'chat_id' in args:
                    args['chat_id'] = chat_id
                    result = await func(**args)
                else:
                    # Giả định hàm nhận chat_id làm tham số đầu tiên nếu không có key 'chat_id'
                    # Cần điều chỉnh nếu hàm có cấu trúc khác
                    temp_args = args.copy() # Tránh thay đổi dict gốc trong các lần gọi đồng thời
                    result = await func(chat_id, **temp_args)

                # logger.debug(f"Successfully completed {operation_desc} for chat {chat_id}")
                return result # Trả về kết quả (ví dụ: Message object) hoặc None nếu thành công
            except Exception as e:
                # Lỗi đã được log bên trong handle_errors nếu được sử dụng
                # Chỉ log thêm context nếu cần
                logger.warning(f"Failed {operation_desc} for chat {chat_id}: {e}")
                return e # Trả về exception để xử lý bên ngoài

    tasks = [send_with_limit(chat_id) for chat_id in target_chat_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True) # Vẫn bắt exception ở đây để gather không bị dừng

    # Xử lý kết quả (log chi tiết hơn nếu muốn)
    successful_sends = 0
    failed_sends = 0
    for i, result in enumerate(results):
        target_id = target_chat_ids[i]
        if isinstance(result, Exception):
            failed_sends += 1
            # Log chi tiết hơn đã nằm trong send_with_limit hoặc handle_errors
            # logger.warning(f"Final status for chat {target_id}: Failed ({result})")
        else:
            successful_sends += 1
            # logger.debug(f"Final status for chat {target_id}: Success")

    logger.info(f"Batch '{operation_desc}': {successful_sends} successful, {failed_sends} failed out of {len(target_chat_ids)} targets.")
    return results # Trả về list kết quả (message objects hoặc exceptions)