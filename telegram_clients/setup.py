# -*- coding: utf-8 -*-
import logging
from telethon import TelegramClient
from telegram import Bot # Từ python-telegram-bot
from telegram.error import InvalidToken
from config import settings

logger = logging.getLogger(__name__)

def setup_telethon_client():
    """Khởi tạo và trả về Telethon client."""
    logger.info(f"Initializing Telethon client with session: {settings.SESSION_NAME}")
    client = TelegramClient(
        settings.SESSION_NAME,
        settings.API_ID,
        settings.API_HASH,
        system_version=settings.TELETHON_SYSTEM_VERSION,
        device_model=settings.TELETHON_DEVICE_MODEL,
        connection_retries=settings.TELETHON_CONNECTION_RETRIES,
        auto_reconnect=settings.TELETHON_AUTO_RECONNECT
    )
    return client

def setup_ptb_bot():
    """Khởi tạo và trả về python-telegram-bot instance."""
    logger.info("Initializing python-telegram-bot instance.")
    try:
        bot = Bot(token=settings.BOT_TOKEN)
        # Thực hiện một lệnh gọi API đơn giản để kiểm tra token
        # loop = asyncio.get_event_loop()
        # bot_info = loop.run_until_complete(bot.get_me()) # Cần chạy trong async context
        logger.info(f"Successfully initialized bot.") # Bỏ qua get_me() để tránh phức tạp khi init
        return bot
    except InvalidToken:
        logger.error("ERROR: Invalid BOT_TOKEN provided. Please check your .env file.")
        raise # Raise lại lỗi để dừng chương trình
    except Exception as e:
        logger.error(f"Could not initialize target bot: {e}")
        raise