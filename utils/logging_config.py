# -*- coding: utf-8 -*-
import logging
import sys
from config import settings

def setup_logging():
    """Cấu hình hệ thống logging."""
    log_level = getattr(logging, settings.LOG_LEVEL, logging.INFO)

    # Định dạng log
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(log_format)

    # Handler cho console
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    # Cấu hình root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(stream_handler)

    # Giảm độ chi tiết của các thư viện bên ngoài
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING) # Thường dùng bởi python-telegram-bot

    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured with level: {settings.LOG_LEVEL}")

    # Có thể thêm FileHandler ở đây nếu muốn ghi log ra file
    # file_handler = logging.FileHandler("bot.log")
    # file_handler.setFormatter(formatter)
    # root_logger.addHandler(file_handler)