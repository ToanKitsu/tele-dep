# handlers/bot_status_handlers.py
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatMemberStatus, ChatType

from config import persistent_config # Import the new config module

logger = logging.getLogger(__name__)

async def handle_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles bot being added to or removed from a group."""
    result = update.chat_member
    if not result:
        logger.debug("ChatMember update received but result is None.")
        return

    # Check if the update is about the bot itself
    is_bot_update = result.new_chat_member.user.id == context.bot.id
    chat = result.chat
    chat_id = chat.id

    if not is_bot_update or chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        # Ignore updates about other users or non-group chats
        return

    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status

    logger.info(f"Bot status update in chat {chat_id} ('{chat.title}'): {old_status} -> {new_status}")

    # Bot was added or promoted to admin
    if new_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR] and old_status not in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR]:
        logger.info(f"Bot joined or was promoted in group {chat_id} ('{chat.title}'). Adding to target list.")
        added = await persistent_config.add_target_group(chat_id)
        if added:
             # Optional: Send a welcome message
            try:
                await context.bot.send_message(
                    chat_id,
                    "Hello! 👋 Thanks for adding me.\n"
                    "I will now forward relevant messages to this group.\n"
                    f"Admins can configure the display mode using /display."
                )
            except Exception as send_err:
                logger.error(f"Failed to send welcome message to group {chat_id}: {send_err}")

    # Bot was kicked, left, or demoted from admin (treat demotion as removal for forwarding)
    elif new_status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
        logger.info(f"Bot left or was kicked from group {chat_id} ('{chat.title}'). Removing from target list.")
        await persistent_config.remove_target_group(chat_id)