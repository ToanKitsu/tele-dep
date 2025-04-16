# -*- coding: utf-8 -*-
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

@contextmanager
def handle_errors(operation_name: str, message_id=None, chat_id=None, fallback_value=None, raise_exception=False):
    """
    Context manager để bắt và log lỗi một cách nhất quán.

    Args:
        operation_name (str): Mô tả hoạt động đang thực hiện.
        message_id (int, optional): ID của tin nhắn liên quan. Defaults to None.
        chat_id (int, optional): ID của chat liên quan. Defaults to None.
        fallback_value: Giá trị trả về nếu có lỗi xảy ra. Defaults to None.
        raise_exception (bool): Nếu True, raise lại exception sau khi log. Defaults to False.
    """
    context_info = f"Operation: {operation_name}"
    if message_id:
        context_info += f" | Message ID: {message_id}"
    if chat_id:
        context_info += f" | Chat ID: {chat_id}"

    try:
        yield
    except Exception as e:
        # Phân loại mức độ log dựa trên loại lỗi (ví dụ: lỗi mạng, lỗi bot bị block...)
        log_level = logging.ERROR
        error_msg = str(e).lower()
        if isinstance(e, (ConnectionError, TimeoutError)):
            log_level = logging.WARNING # Lỗi tạm thời
        elif any(term in error_msg for term in ["bot was blocked", "user is deactivated", "chat not found",
                                                "bot is not a member", "group chat was deactivated",
                                                "need administrator rights"]):
            log_level = logging.WARNING # Lỗi liên quan đến quyền hoặc trạng thái chat/user

        logger.log(log_level, f"Error during {context_info}: {e}", exc_info=log_level >= logging.ERROR) # Include traceback for ERROR level

        if raise_exception:
            raise e
        # return fallback_value # Context manager không nên return trực tiếp, yield là đủ
    # return fallback_value # Không cần return ở đây