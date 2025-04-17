# utils/helpers/batch_utils.py
import asyncio
import logging

logger = logging.getLogger(__name__)

async def process_batch(target_chat_ids, func, args, semaphore, operation_desc="task"):
    """Gửi tin nhắn hàng loạt với giới hạn concurrency."""
    # ... (Code của hàm process_batch giữ nguyên như trong file helpers.py gốc) ...
    async def send_with_limit(chat_id):
        async with semaphore:
            # logger.debug(f"Attempting to {operation_desc} for chat {chat_id}")
            try:
                # Truyền chat_id như là tham số đầu tiên hoặc qua 'chat_id' key
                current_args = args.copy() # Tạo bản sao để tránh xung đột
                if 'chat_id' in current_args:
                    current_args['chat_id'] = chat_id
                    result = await func(**current_args)
                else:
                    # Giả định hàm nhận chat_id làm tham số đầu tiên nếu không có key 'chat_id'
                    # Cần điều chỉnh nếu hàm có cấu trúc khác
                    result = await func(chat_id, **current_args)

                # logger.debug(f"Successfully completed {operation_desc} for chat {chat_id}")
                return result # Trả về kết quả (ví dụ: Message object) hoặc None nếu thành công
            except Exception as e:
                # Lỗi đã được log bên trong handle_errors nếu được sử dụng
                # Chỉ log thêm context nếu cần
                # Lưu ý: Không log chi tiết lỗi ở đây vì execute_send sẽ log rồi
                # logger.warning(f"Failed {operation_desc} for chat {chat_id}: {type(e).__name__}")
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
            # Log chi tiết hơn đã nằm trong send_with_limit hoặc execute_send
            # logger.warning(f"Final status for chat {target_id}: Failed ({type(result).__name__})")
        else:
            successful_sends += 1
            # logger.debug(f"Final status for chat {target_id}: Success")

    # Giảm log không cần thiết nếu execute_send đã log rồi
    # logger.info(f"Batch '{operation_desc}': {successful_sends} successful, {failed_sends} failed out of {len(target_chat_ids)} targets.")
    return results # Trả về list kết quả (message objects hoặc exceptions)