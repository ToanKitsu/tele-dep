# handlers/command_handlers/display/group_display.py
# -*- coding: utf-8 -*-
import logging
import html # <--- Import html module for escaping

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler
from telegram.constants import ChatMemberStatus, ParseMode, ChatType # <--- Ensure ParseMode is imported

from config import group_config

logger = logging.getLogger(__name__)

CALLBACK_PREFIX_SET_DISPLAY_MODE = "set_display_mode_"
CALLBACK_CANCEL_DISPLAY_CONFIG = "cancel_display_config"

async def is_user_group_admin(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    # ... (function remains the same - already fixed OWNER) ...
    try:
        member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception as e:
        logger.error(f"Error checking admin/owner status for user {user_id} in chat {chat_id}: {e}", exc_info=True)
        return False


async def group_display_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the group display mode configuration conversation."""
    # ... (initial checks remain the same) ...
    user = update.effective_user
    chat = update.effective_chat

    if not chat or chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await update.message.reply_text("This command can only be used in group chats.")
        return ConversationHandler.END

    chat_id = chat.id
    user_id = user.id

    logger.info(f"User {user_id} initiated /display in chat {chat_id} ({chat.title})")

    is_admin_or_owner = await is_user_group_admin(chat_id, user_id, context)
    if not is_admin_or_owner:
        await update.message.reply_text("Only group admins or the owner can change the bot's display mode for this group.")
        logger.warning(f"User {user_id} is not an admin/owner in chat {chat_id}, denied access to /display.")
        return ConversationHandler.END

    current_mode = group_config.get_group_mode(chat_id)
    mode_text = {
        group_config.MODE_FULL: "Full Content (Text + Media)",
        group_config.MODE_FXTWITTER: "FXTwitter Link Only"
    }

    # ---> FIX: Escape chat title for HTML safety
    safe_chat_title = html.escape(chat.title or "this group")
    # ---> FIX: Use HTML bold tags
    current_mode_display = f"<b>{html.escape(mode_text.get(current_mode, 'Unknown'))}</b>"

    text = f"⚙️ Group Display Mode for '{safe_chat_title}'\n\n"
    text += f"Current Mode: {current_mode_display}\n\n" # Use HTML bold
    text += "Choose the desired display mode for forwarded messages:"

    keyboard = [
        [
            InlineKeyboardButton(
                f"✅ {mode_text[group_config.MODE_FULL]}" if current_mode == group_config.MODE_FULL else mode_text[group_config.MODE_FULL],
                callback_data=f"{CALLBACK_PREFIX_SET_DISPLAY_MODE}{group_config.MODE_FULL}"
            )
        ],
        [
            InlineKeyboardButton(
                f"✅ {mode_text[group_config.MODE_FXTWITTER]}" if current_mode == group_config.MODE_FXTWITTER else mode_text[group_config.MODE_FXTWITTER],
                callback_data=f"{CALLBACK_PREFIX_SET_DISPLAY_MODE}{group_config.MODE_FXTWITTER}"
            )
        ],
         [InlineKeyboardButton("Cancel", callback_data=CALLBACK_CANCEL_DISPLAY_CONFIG)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # ---> FIX: Change ParseMode to HTML
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

    return 0 # Single state conversation


async def handle_display_mode_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (initial checks remain the same) ...
    query = update.callback_query
    await query.answer()

    user = query.from_user
    chat = query.message.chat

    if not chat or chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
         await query.edit_message_text("Error: This action must be performed within the group chat.")
         return ConversationHandler.END

    chat_id = chat.id
    user_id = user.id

    is_admin_or_owner = await is_user_group_admin(chat_id, user_id, context)
    if not is_admin_or_owner:
        await query.edit_message_text("Error: You are no longer an admin or the owner in this group.")
        logger.warning(f"User {user_id} attempted callback in chat {chat_id} but is not admin/owner.")
        return ConversationHandler.END

    callback_data = query.data

    if callback_data == CALLBACK_CANCEL_DISPLAY_CONFIG:
        await query.edit_message_text("Display mode configuration cancelled.")
        logger.info(f"User {user_id} cancelled display mode change in chat {chat_id}.")
        return ConversationHandler.END

    if callback_data.startswith(CALLBACK_PREFIX_SET_DISPLAY_MODE):
        new_mode = callback_data[len(CALLBACK_PREFIX_SET_DISPLAY_MODE):]

        if new_mode in group_config.VALID_MODES:
            success = group_config.set_group_mode(chat_id, new_mode)
            if success:
                mode_text = {
                    group_config.MODE_FULL: "Full Content (Text + Media)",
                    group_config.MODE_FXTWITTER: "FXTwitter Link Only"
                }
                # ---> FIX: Use HTML bold tag
                new_mode_display = f"<b>{html.escape(mode_text.get(new_mode))}</b>"
                # ---> FIX: Change ParseMode to HTML
                await query.edit_message_text(f"✅ Display Mode Updated!\nMode set to: {new_mode_display}", parse_mode=ParseMode.HTML)
                logger.info(f"Admin/Owner {user_id} set display mode to '{new_mode}' for chat {chat_id}.")
            else:
                await query.edit_message_text("❌ Error setting display mode. Invalid mode specified.")
                logger.error(f"Admin/Owner {user_id} failed to set invalid mode '{new_mode}' for chat {chat_id}.")
        else:
            await query.edit_message_text("❌ Error: Invalid display mode data received.")
            logger.error(f"Received invalid mode data '{new_mode}' in callback for chat {chat_id}.")
    else:
        await query.edit_message_text("Unknown action.")
        logger.warning(f"Received unknown callback data '{callback_data}' in group display handler.")

    return ConversationHandler.END

async def cancel_display_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (function remains the same) ...
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("Display mode configuration cancelled.")
    elif update.message:
         await update.message.reply_text("Operation cancelled.")

    logger.info(f"Display mode config conversation cancelled for user {update.effective_user.id} in chat {update.effective_chat.id}.")
    return ConversationHandler.END


def get_group_display_conversation_handler() -> ConversationHandler:
    # ... (function remains the same) ...
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("display", group_display_start)],
        states={
            0: [
                CallbackQueryHandler(handle_display_mode_selection, pattern=f"^{CALLBACK_PREFIX_SET_DISPLAY_MODE}"),
                CallbackQueryHandler(cancel_display_config, pattern=f"^{CALLBACK_CANCEL_DISPLAY_CONFIG}$")
                ],
        },
        fallbacks=[CommandHandler("display", group_display_start), CallbackQueryHandler(cancel_display_config)],
        conversation_timeout=300
    )
    return conv_handler