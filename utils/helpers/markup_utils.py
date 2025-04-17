# utils/helpers/markup_utils.py
import logging
from telethon.tl.types import KeyboardButtonUrl, ReplyInlineMarkup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup # Từ python-telegram-bot

logger = logging.getLogger(__name__)

def extract_button_url(message, button_text_to_find):
    """Trích xuất URL từ nút inline cụ thể trong tin nhắn Telethon."""
    # ... (Code của hàm extract_button_url giữ nguyên) ...
    if not message.reply_markup or not isinstance(message.reply_markup, ReplyInlineMarkup):
        return None

    for row in message.reply_markup.rows:
        for btn in row.buttons:
            if isinstance(btn, KeyboardButtonUrl) and btn.text == button_text_to_find:
                return btn.url
    return None

def create_ptb_inline_markup(button_text, button_url):
    """Tạo InlineKeyboardMarkup cho python-telegram-bot từ text và url."""
    # ... (Code của hàm create_ptb_inline_markup giữ nguyên) ...
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
    # ... (Code của hàm has_specific_button giữ nguyên) ...
    if not message.reply_markup or not isinstance(message.reply_markup, ReplyInlineMarkup):
        return False

    for row in message.reply_markup.rows:
        for btn in row.buttons:
            # Chỉ cần kiểm tra sự tồn tại của nút
            if isinstance(btn, KeyboardButtonUrl) and btn.text == button_text_to_find:
                return True
    return False