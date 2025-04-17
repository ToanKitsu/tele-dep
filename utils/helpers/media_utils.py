# utils/helpers/media_utils.py
import logging

logger = logging.getLogger(__name__)

# --- Media Type Definitions ---
MEDIA_PHOTO = 'photo'
MEDIA_VIDEO = 'video'
MEDIA_DOCUMENT = 'document'
MEDIA_AUDIO = 'audio'
MEDIA_VOICE = 'voice'
MEDIA_STICKER = 'sticker'
MEDIA_ANIMATION = 'animation' # GIFs gửi dưới dạng document thường là animation

# Ánh xạ loại media Telethon sang chuỗi định danh của chúng ta
def get_telethon_media_type(message):
    """Xác định loại media từ tin nhắn Telethon."""
    # ... (Code của hàm get_telethon_media_type giữ nguyên) ...
    if message.photo:
        return MEDIA_PHOTO
    elif message.video:
        return MEDIA_VIDEO
    # Telethon coi GIF là document có mime_type 'image/gif' hoặc video/mp4
    elif message.document:
        mime_type = getattr(message.document, 'mime_type', '').lower()
        # Check for animated attribute first (more reliable for GIFs)
        is_animated = False
        if message.document.attributes:
            for attr in message.document.attributes:
                if hasattr(attr, 'is_animated') and attr.is_animated:
                    is_animated = True
                    break
        if is_animated or mime_type == 'image/gif':
             return MEDIA_ANIMATION # Treat animated docs/gifs as animation
        elif 'audio' in mime_type:
             return MEDIA_AUDIO
        elif 'video' in mime_type: # Some GIFs might be video mime types
             if is_animated: return MEDIA_ANIMATION
             else: return MEDIA_VIDEO # Actual video file
        # elif 'voice' in mime_type: # Voice is usually a separate type
        #      return MEDIA_VOICE
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
    # ... (Code của hàm get_ptb_send_func_and_arg giữ nguyên) ...
    return MEDIA_SEND_INFO.get(media_type)

def get_media_file_id(ptb_message):
    """Trích xuất file_id từ tin nhắn đã gửi bằng python-telegram-bot."""
    # ... (Code của hàm get_media_file_id giữ nguyên) ...
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